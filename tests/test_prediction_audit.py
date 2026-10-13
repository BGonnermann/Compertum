"""Independent original-source, causal, fitted and served prediction audit."""
from dataclasses import replace
from decimal import Decimal as D
from functools import lru_cache
import hashlib,json,math
import pytest
from compertum.data.calendar import session_times
from compertum.data.encoding import canonical
from compertum.data.errors import DataError
from compertum.modeling.candidate import evaluate_candidate
from compertum.modeling.registry import VARIANTS
from compertum.simulation.market import load_market
from compertum.audit_predictions import audit_candidate_predictions,SourceEvidence,reconstruct_errors,reconstruct_rank,_fit_equations
from helpers.model_campaign_fixture import campaign_fixture,SECTORS
from helpers.simulation_fixture import changed

@lru_cache(maxsize=12)
def sample(candidate='ridge-h01-a001'):
    chunks,ts,te,start,end,asof=campaign_fixture()
    args=dict(candidate_id=candidate,year=2021,training_start=ts,training_end=te,start=start,end=end,scoring_as_of=asof)
    result=evaluate_candidate(chunks,SECTORS,ts,te,start,end,candidate,scoring_as_of=asof)
    return chunks,args,result

def edited(result,fn):
    v=json.loads(result.content);fn(v);raw=canonical(v)
    return replace(result,content=raw,sha256=hashlib.sha256(raw).hexdigest())

@pytest.mark.parametrize('candidate',[c.candidate_id for c in VARIANTS])
def test_all_registered_candidates_audit_original_source(candidate):
    chunks,args,result=sample(candidate);report=audit_candidate_predictions(chunks,SECTORS,result,**args);v=json.loads(report.content)
    assert v['status']=='VERIFIED_PASS' and not v['financial_accepted'] and not v['full_M3']
    assert v['scope']=='SYNTHETIC_CAUSAL_PREDICTION_AND_FIT' and v['candidate_sha256']==result.sha256
    assert v['coverage']['candidate_rows']==31*12 and v['coverage']['scored_rows']==3*(31-int(args['candidate_id'].split('-h')[1][:2]))
    assert v['gates']['fit_activation']=='UNVERIFIED' and v['gates']['complete_campaign_shortlist']=='UNVERIFIED'
    assert hashlib.sha256(report.content).hexdigest()==report.sha256

@pytest.mark.parametrize('field,value',[('candidate_id','momentum-h01'),('year',2022),('training_start','2020-12-01'),('start','2021-01-05'),('end','2021-02-16'),('scoring_as_of','2021-02-17T14:25:00+00:00')])
def test_expected_original_fold_cannot_be_changed_by_result(field,value):
    chunks,args,result=sample();bad=dict(args);bad[field]=value
    with pytest.raises(DataError):audit_candidate_predictions(chunks,SECTORS,result,**bad)

@pytest.mark.parametrize('mutation',[
 lambda v:v['prediction_report']['rows'][0].__setitem__('feature_sha256','a'*64),
 lambda v:v['prediction_report']['rows'][0]['features'].__setitem__(0,0.9),
 lambda v:v['prediction_report']['rows'][0].__setitem__('entry_revision','invented-new'),
 lambda v:v['prediction_report']['rows'][0].__setitem__('label_available_at',v['prediction_report']['rows'][0]['exit_at']),
 lambda v:v['prediction_report']['rows'][0].__setitem__('target','0.9'),
 lambda v:v['prediction_report']['rows'][0].__setitem__('prediction','0.9'),
 lambda v:v['prediction_report']['coverage'].__setitem__('eligible_rows',0),
 lambda v:v['prediction_report']['omissions'].pop(),
 lambda v:v['prediction_report']['metrics'].__setitem__('mse','0.9'),
 lambda v:v['prediction_report']['daily_rank_correlation'][0].__setitem__('spearman','0'),
 lambda v:v['fit_rows']['rows'][0]['features'].__setitem__(0,True),
 lambda v:v['fit_rows']['rows'][0].__setitem__('target',0.9),
 lambda v:v['fit_manifest']['included'].pop(),
 lambda v:v['dataset_assembly']['row_provenance'][0].__setitem__('feature_sha256','b'*64),
 lambda v:v['model']['scaler']['mean'].__setitem__(0,0.9),
 lambda v:v['model']['ridge']['coef'].__setitem__(0,0.9),
])
def test_rehashed_corruption_fails_original_evidence(mutation):
    chunks,args,result=sample()
    def corrupt(v):
        mutation(v)
        if v['fit_rows'] is not None:
            digest=hashlib.sha256(canonical(v['fit_rows'])).hexdigest();v['dataset_assembly']['fit_rows_sha256']=digest;v['fit_manifest']['bundle_sha256']=digest;v['model']['bundle_sha256']=digest
            v['fit_manifest_sha256']=hashlib.sha256(canonical(v['fit_manifest'])).hexdigest();v['model']['fit_manifest_sha256']=v['fit_manifest_sha256'];v['model_sha256']=hashlib.sha256(canonical(v['model'])).hexdigest()
            for replay in v['replays'].values():replay['model_sha256']=v['model_sha256']
    with pytest.raises(DataError):audit_candidate_predictions(chunks,SECTORS,edited(result,corrupt),**args)

def test_independent_feature_hand_equations():
    chunks,args,_=sample();day=args['start'];prior=session_times(day).previous_date
    def edit(v):
        for row in v['bars']:
            if row['reference']=='daily':
                price='110' if row['session_date']==prior else '100'
                row.update(open=price,high=price,low=price,close=price,volume='40000' if row['session_date']==prior else '20000')
    e=SourceEvidence(load_market(changed(chunks,edit),SECTORS));v=e.features('AAPL',day)['values']
    assert v[:4]==pytest.approx([.1]*4,abs=1e-10,rel=1e-8)
    assert v[4:6]==pytest.approx([.1*math.sqrt(252/h) for h in (20,63)],abs=1e-10,rel=1e-8)
    assert v[6:9]==pytest.approx([19/201,62/631,40/21],abs=1e-10,rel=1e-8)

def test_split_label_excludes_dividend_hand_equation():
    chunks,args,_=sample();market=load_market(chunks,SECTORS);day=args['start'];exit=session_times(day).next_date
    market.rows[('AAPL',day,'entry')]=dict(market.rows[('AAPL',day,'entry')],open='100')
    market.rows[('AAPL',exit,'entry')]=dict(market.rows[('AAPL',exit,'entry')],open='55')
    market.actions=({'symbol':'AAPL','kind':'SPLIT','action_id':'split','factor':'2','effective_session':exit,'simulated_known_at':session_times(day).decision.isoformat()},
                    {'symbol':'AAPL','kind':'DIVIDEND','action_id':'dividend','amount':'9','effective_session':exit,'simulated_known_at':session_times(day).decision.isoformat()})
    label=SourceEvidence(market).label('AAPL',day,exit,1)
    assert label['target']==D('.10') and label['split_actions']==['split']
    assert label['available']==session_times(session_times(exit).next_date).decision

@pytest.mark.parametrize('alpha',[1,10,100])
def test_ridge_hand_equation(alpha):
    result=_fit_equations([[-1.0],[1.0]],[.02,.04],alpha)
    assert result['mean']==[0.] and result['scale']==[1.]
    assert result['coef']==pytest.approx([.02/(2+alpha)],abs=1e-10,rel=1e-8)
    assert result['intercept']==pytest.approx(.03,abs=1e-10,rel=1e-8)

def test_error_and_rank_hand_equations():
    v=reconstruct_errors([D(0),D(2)],[D(1),D(1)])
    assert v['mse']=='1' and v['mae']=='1' and v['mean_signed_error']=='0' and v['mse_improvement']=='0'
    assert reconstruct_errors([],[])['status']=='NO_SCORED_ROWS'
    assert reconstruct_errors([D(1)],[D(0)])['mse_improvement'] is None
    assert D(reconstruct_rank([D(1),D(1),D(3)],[D(1),D(2),D(3)]))==pytest.approx(D(3).sqrt()/2,abs=D('1e-10'),rel=D('1e-8'))
    assert reconstruct_rank([D(1),D(1)],[D(1),D(2)]) is None

@pytest.mark.parametrize('late',[False,True])
def test_source_revision_cutoff_boundary_purges_complete_date(late):
    from datetime import timedelta
    from compertum.modeling.registry import annual_cutoff
    chunks,args,_=sample();at=annual_cutoff(2021)+timedelta(seconds=int(late))
    def edit(v):
        for row in v['bars']:
            if row['asset_id']=='AAPL' and row['reference']=='entry' and row['session_date']=='2020-12-30':row['simulated_revision_available_at']=at.isoformat()
    original=changed(chunks,edit)
    result=evaluate_candidate(original,SECTORS,args['training_start'],args['training_end'],args['start'],args['end'],args['candidate_id'],scoring_as_of=args['scoring_as_of'])
    report=audit_candidate_predictions(original,SECTORS,result,**args);assert json.loads(report.content)['status']=='VERIFIED_PASS'
    manifest=json.loads(result.content)['fit_manifest'];key='excluded' if late else 'included'
    selected=[r for r in manifest[key] if r['decision_at'].startswith('2020-12-29')]
    assert len(selected)==3
    if late:assert all('SAME_DATE_PURGE' in r['reasons'] for r in selected)


def test_missing_original_label_purges_other_symbols_on_that_date():
    chunks,args,_=sample()
    def edit(v):
        if v['assets'][0]['asset_id']!='AAPL':return
        # Snapshots require complete declared sessions. Omit one entire source
        # session, retaining the preceding entry but removing its next exit.
        v['feature_sessions']=[day for day in v['feature_sessions'] if day!='2020-12-29']
        v['bars']=[row for row in v['bars'] if not((row['reference']=='entry' and row['session_date']=='2020-12-30') or (row['reference']!='entry' and row['session_date']=='2020-12-29'))]
    original=changed(chunks,edit)
    result=evaluate_candidate(original,SECTORS,args['training_start'],args['training_end'],args['start'],args['end'],args['candidate_id'],scoring_as_of=args['scoring_as_of'])
    assert json.loads(audit_candidate_predictions(original,SECTORS,result,**args).content)['status']=='VERIFIED_PASS'
    omissions=[r for r in json.loads(result.content)['dataset_assembly']['omissions'] if r['decision_at'].startswith('2020-12-29')]
    assert len(omissions)==12 and sum('SAME_DATE_LABEL_PURGE' in r['reasons'] for r in omissions)==3


def test_no_scores_before_label_availability():
    chunks,args,_=sample('momentum-h01');args=dict(args,scoring_as_of=session_times(args['start']).decision.isoformat())
    result=evaluate_candidate(chunks,SECTORS,args['training_start'],args['training_end'],args['start'],args['end'],args['candidate_id'],scoring_as_of=args['scoring_as_of'])
    report=json.loads(audit_candidate_predictions(chunks,SECTORS,result,**args).content)
    assert report['coverage']['scored_rows']==0 and report['prediction_metrics']['status']=='NO_SCORED_ROWS'

@pytest.mark.parametrize('mutation',[
 lambda v:v['prediction_report']['rows'][0]['features'].__setitem__(0,str(v['prediction_report']['rows'][0]['features'][0])),
 lambda v:v['model']['resolved']['ridge'].__setitem__('tol',0.00010000001),
])
def test_feature_numeric_types_and_resolved_parameters_are_exact(mutation):
    chunks,args,result=sample()
    def change(v):
        mutation(v);v['model_sha256']=hashlib.sha256(canonical(v['model'])).hexdigest()
        for replay in v['replays'].values():replay['model_sha256']=v['model_sha256']
    with pytest.raises(DataError):audit_candidate_predictions(chunks,SECTORS,edited(result,change),**args)


def test_tiny_input_perturbation_cannot_amplify_through_scaler_and_refit():
    from compertum.modeling.ridge import freeze_rows,prepare_fit,fit_ridge,predict
    from compertum.modeling.registry import FEATURES
    from compertum.simulation.prediction import error_metrics,rank_correlation
    chunks,args,result=sample()
    def change(v):
        data=v['fit_rows']['rows']
        for i,row in enumerate(data):row['features'][8]+=5e-11*(i%2)
        bundle=freeze_rows(data,horizon=1,feature_names=FEATURES);manifest=prepare_fit(bundle,2021);model=fit_ridge(bundle,manifest,args['candidate_id'])
        v['fit_rows']=json.loads(bundle.content);v['dataset_assembly']['fit_rows_sha256']=bundle.sha256
        v['fit_manifest']=json.loads(manifest.content);v['fit_manifest_sha256']=manifest.sha256;v['model']=json.loads(model.content);v['model_sha256']=model.sha256
        p=v['prediction_report']
        predictions=predict(model,[r['features'] for r in p['rows']],feature_names=FEATURES)
        for row,prediction in zip(p['rows'],predictions):row['prediction']=str(prediction);row['signed_error']=str(D(row['prediction'])-D(row['target']))
        p['metrics']=error_metrics([D(r['prediction']) for r in p['rows']],[D(r['target']) for r in p['rows']])
        p['ml_contribution_gate']='PASS' if D(p['metrics']['mse_improvement'])>=D('.01') else 'FAIL'
        for d in p['daily_rank_correlation']:
            rows=[r for r in p['rows'] if r['session']==d['session']];corr=rank_correlation([D(r['prediction']) for r in rows],[D(r['target']) for r in rows]);d['spearman']=corr;d['status']='NO_SCORED_ROWS' if not rows else 'DEFINED' if corr is not None else 'UNDEFINED_CONSTANT_OR_TOO_FEW_ROWS'
        for replay in v['replays'].values():replay['model_sha256']=model.sha256
    with pytest.raises(DataError):audit_candidate_predictions(chunks,SECTORS,edited(result,change),**args)

@pytest.mark.parametrize('change_momentum',[False,True])
def test_recorded_nearby_predictions_cannot_break_exact_baseline_or_rank_ties(change_momentum):
    chunks,args,_=sample('momentum-h01')
    def align_daily(v):
        for row in v['bars']:
            if row['reference']=='daily':row.update(open='100',close='100',high='100',low='100')
    original=changed(chunks,align_daily)
    result=evaluate_candidate(original,SECTORS,args['training_start'],args['training_end'],args['start'],args['end'],args['candidate_id'],scoring_as_of=args['scoring_as_of'])
    assert json.loads(audit_candidate_predictions(original,SECTORS,result,**args).content)['status']=='VERIFIED_PASS'
    def perturb(v):
        row=v['prediction_report']['rows'][0];row['prediction']='0.000000000000001';row['signed_error']=str(D(row['prediction'])-D(row['target']))
        if change_momentum:row['momentum_prediction']=row['prediction']
    with pytest.raises(DataError):audit_candidate_predictions(original,SECTORS,edited(result,perturb),**args)

