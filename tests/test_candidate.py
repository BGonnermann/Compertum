"""Annual synthetic candidate units; no campaign or strategy admission implied."""
import json
from decimal import Decimal as D
from dataclasses import replace
import hashlib
import pytest
from compertum.data.errors import DataError
from compertum.data.calendar import session_times
from compertum.modeling.candidate import evaluate_candidate
from compertum.modeling.registry import VARIANTS,FEATURES
from compertum.modeling.ridge import RidgeArtifact,predict
from compertum.simulation.engine import replay
from helpers.model_campaign_fixture import campaign_fixture,SECTORS
from helpers.simulation_fixture import changed

def run(candidate='ridge-h01-a001',**kw):
    chunks,ts,te,start,end,asof=campaign_fixture()
    args=dict(chunks=chunks,sectors=SECTORS,training_start=ts,training_end=te,start=start,end=end,candidate_id=candidate,scoring_as_of=asof);args.update(kw)
    return evaluate_candidate(**args)

def test_ridge_fit_score_and_ledger_are_bound_and_separate():
    result=run();v=json.loads(result.content)
    assert v['financial_accepted'] is False and v['full_M2'] is False
    assert len(v['registered_family'])==12 and v['candidate']['alpha']==1
    assert v['coverage_status']=='DIAGNOSTIC_PARTIAL_DEVELOPMENT_FOLD'
    assert v['model']['fit_manifest_sha256']==v['fit_manifest_sha256']
    assert v['fit_manifest']['cutoff']=='2021-01-04T12:00:00+00:00'
    assert len(v['fit_manifest']['excluded'])==6
    p=v['prediction_report'];assert p['coverage']['candidate_rows']==31*12
    assert p['coverage']['scored_rows']==30*3 and len(p['omissions'])==31*12-90
    assert p['momentum_metrics']['observations']==p['metrics']['observations']==90
    assert set(v['replays'])=={'10','20'}
    for c,r in v['replays'].items():
        assert r['candidate_id']=='ridge-h01-a001' and r['cost_bps']==int(c)
        assert 'strategy' in r['portfolios'] and 'momentum' not in r['portfolios']
        assert len(r['portfolios']['strategy']['days'])==31
    model=RidgeArtifact(__import__('compertum.data.encoding',fromlist=['canonical']).canonical(v['model']),v['model_sha256'])
    row=p['rows'][0];assert predict(model,[row['features']],feature_names=FEATURES)[0]==float(row['prediction'])
    assert all(r['label_available_at']>=r['exit_at'] for r in p['rows'])

@pytest.mark.parametrize('h',[1,5,21])
def test_momentum_ledger_exactly_preserves_existing_simulator(h):
    chunks,_,_,start,end,_=campaign_fixture();v=json.loads(run(f'momentum-h{h:02}').content)
    for c in [10,20]:
        old=json.loads(replay(chunks,SECTORS,start,end,h,cost_bps=c).content)
        assert v['replays'][str(c)]['portfolios']['strategy']==old['portfolios']['momentum']
    assert v['model'] is None and v['fit_manifest'] is None
    assert v['prediction_report']['metrics']==v['prediction_report']['momentum_metrics']
    assert v['prediction_report']['coverage']['scored_rows']==(31-h)*3

def test_future_evaluation_label_changes_never_change_fit_or_predictions():
    chunks,ts,te,start,end,asof=campaign_fixture();nextday=session_times(start).next_date
    def edit(v):
        for b in v['bars']:
            if b['reference']=='entry' and b['session_date']==nextday:
                for k in ['open','high','low','close']:b[k]=str(D(b[k])*D('1.01'))
    a=json.loads(run().content);b=json.loads(run(chunks=changed(chunks,edit)).content)
    assert a['model_sha256']==b['model_sha256']
    assert [(r['session'],r['symbol'],r['prediction']) for r in a['prediction_report']['rows']]==[(r['session'],r['symbol'],r['prediction']) for r in b['prediction_report']['rows']]
    assert a['prediction_report']['rows'][0]['target']!=b['prediction_report']['rows'][0]['target']

def test_scoring_before_label_availability_is_explicit():
    _,_,_,start,_,_=campaign_fixture();v=json.loads(run(scoring_as_of=session_times(start).decision.isoformat()).content)
    assert v['prediction_report']['metrics']['observations']==0
    assert {'LABEL_UNAVAILABLE','DECISION_UNAVAILABLE'}<={r['reason'] for r in v['prediction_report']['omissions']}

@pytest.mark.parametrize('kw',[{'candidate_id':'ridge-h01-a002'},{'start':'2024-01-02','end':'2024-01-03'},{'training_end':'2021-01-04'},{'end':'2020-12-31'},{'chunks':[object()]}])
def test_invalid_protocol_and_provider_refused(kw):
    with pytest.raises(DataError):run(**kw)
