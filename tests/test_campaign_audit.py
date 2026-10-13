import copy,hashlib,json
from pathlib import Path
from uuid import uuid4
import pytest
from compertum.audit_campaign import audit_campaign,reconstruct_history,reconstruct_aggregate
from compertum.data.encoding import canonical
from compertum.data.errors import DataError
from compertum.modeling.campaign import UNITS
from compertum.simulation.runs import SavedRuns
from compertum.runtime.identity import resolve_project
from compertum.runtime.owners import acquire_owner,release_owner
from test_storage import manager
from helpers.saved_campaign_fixture import campaign_folds


def sha(raw):return hashlib.sha256(raw).hexdigest()

@pytest.fixture(scope='module')
def evidence(tmp_path_factory):
    root=tmp_path_factory.mktemp('complete-failure-history');project=resolve_project(root);lease=acquire_owner(project,'coordinator')
    try:
        storage=manager((project,{'coordinator':lease}));runs=SavedRuns(storage);run=str(uuid4());runs.create_campaign(run,campaign_folds())
        def control(action):return runs.control(run,str(uuid4()),action)
        control('resume');runs.begin_campaign(run,runs.prepare_campaign(run))
        from compertum.simulation.campaign_runs import interrupt
        interrupt(runs,run,'WORKER_FAILED');control('resume');runs.step(run);control('pause');control('resume')
        while runs.summary(run)['state']!='COMPLETED':runs.step(run)
        state=runs._load(run);card=runs.campaign_scorecard(run)
        history=[{'seq':seq,'body':body,'sha256':digest} for seq,body,digest in storage.store.conn.execute('SELECT seq,body,sha256 FROM baseline_history WHERE run_id=? ORDER BY seq',(run,))]
        controls=[{'request_id':request,'action':action,'receipt':receipt} for request,action,receipt in storage.store.conn.execute('SELECT request_id,action,receipt FROM baseline_controls WHERE run_id=? ORDER BY request_id',(run,))]
        frames={o['artifact']['path']:(root/o['artifact']['path']).read_bytes() for o in state['outcomes'].values() if o['status']=='COMPLETED'}
        campaign=(root/state['input_artifact']['path']).read_bytes()
        return dict(campaign=campaign,final_state=canonical(state),history=history,controls=controls,frames=frames,scorecard=card.content,expected_campaign_sha256=sha(campaign),expected_identity=state['identity'])
    finally:release_owner(lease)


def test_complete_failure_campaign_retains_every_trial_and_retry(evidence):
    audit=audit_campaign(**evidence);v=json.loads(audit.content)
    assert sha(audit.content)==audit.sha256 and v['status']=='VERIFIED_PASS'
    assert v['unit_counts']=={'COMPLETED':9,'FAILED':27,'SKIPPED':27}
    assert v['attempts']==37 and v['scorecard_counts']=={'completed':9,'failed':27,'pending':0}
    assert v['financial_accepted'] is False and v['full_M3'] is False and v['shortlist']==[]
    assert v['gates']['per_fold_source_execution_audits']=='UNVERIFIED'
    assert v['gates']['native_authorship']=='UNVERIFIED'


@pytest.mark.parametrize('case',['history_gap','history_reorder','history_truncated','delta_hash','final_hash','erased_control','duplicate_control','changed_control','orphan','missing_frame','frame_header','frame_payload','wrong_input','wrong_identity','erased_failure','promoted_shortlist','counts','ranking','candidate_state','turnover','checkpoint_count','coverage'])
def test_corrupted_campaign_evidence_is_rejected(evidence,case):
    v=copy.deepcopy(evidence)
    if case=='history_gap':v['history'][1]['seq']+=1
    elif case=='history_reorder':v['history'][2:4]=reversed(v['history'][2:4])
    elif case=='history_truncated':v['history']=v['history'][1:]
    elif case=='delta_hash':v['history'][3]['sha256']='0'*64
    elif case=='final_hash':s=json.loads(v['final_state']);s['last_transition']='FORGED';v['final_state']=canonical(s)
    elif case=='erased_control':v['controls'].pop()
    elif case=='duplicate_control':v['controls'].append(v['controls'][0])
    elif case=='changed_control':v['controls'][0]['action']='stop'
    elif case=='orphan':v['frames']['artifacts/runs/orphan.campaign']=next(iter(v['frames'].values()))
    elif case=='missing_frame':v['frames'].pop(next(iter(v['frames'])))
    elif case in ('frame_header','frame_payload'):
        key=next(iter(v['frames']));header,body=v['frames'][key].split(b'\n',1)
        if case=='frame_header':h=json.loads(header);h['payload_sha256']='0'*64;header=canonical(h)
        else:b=json.loads(body);b['start']='2021-01-05';body=canonical(b)
        v['frames'][key]=header+b'\n'+body
    elif case=='wrong_input':v['expected_campaign_sha256']='0'*64
    elif case=='wrong_identity':v['expected_identity']['package_sha256']='0'*64
    else:
        card=json.loads(v['scorecard'])
        if case=='erased_failure':card['search_history']=[r for r in card['search_history'] if r['state']!='FAILED']
        elif case=='promoted_shortlist':card['shortlist']=['momentum-h01']
        elif case=='counts':card['counts']['failed']-=1
        elif case=='ranking':card['diagnostic_rankings']['1']=[]
        elif case=='candidate_state':card['candidates'][3]['state']='COMPLETE_DIAGNOSTIC'
        elif case=='turnover':card['candidates'][0]['trading']['10']['total_turnover']='1'
        elif case=='checkpoint_count':card['candidates'][0]['trading']['10']['rebalance_checkpoints']+=1
        elif case=='coverage':card['candidates'][0]['prediction']['coverage']['candidate_rows']-=1
        v['scorecard']=canonical(card)
    with pytest.raises(DataError):audit_campaign(**v)


def states(evidence):
    state={};result=[]
    for record in evidence['history']:
        event=json.loads(record['body']);state.update(event['fields']);state.setdefault('attempts',[]);state.setdefault('outcomes',{})
        for index,a in sorted(event['attempts'].items(),key=lambda x:int(x[0])):
            if int(index)==len(state['attempts']):state['attempts'].append(a)
            else:state['attempts'][int(index)]=a
        state['outcomes'].update(event['outcomes']);result.append(copy.deepcopy(state))
    return result


def rechain(values):
    history=[];before={}
    for seq,state in enumerate(values,1):
        event={'schema':'campaign-history-delta-v1','previous_sha256':sha(canonical(before)) if before else None,'fields':{k:v for k,v in state.items() if k not in ('attempts','outcomes') and (k not in before or before[k]!=v)},'attempts':{str(i):v for i,v in enumerate(state['attempts']) if i>=len(before.get('attempts',[])) or before['attempts'][i]!=v},'outcomes':{k:v for k,v in state['outcomes'].items() if before.get('outcomes',{}).get(k)!=v},'state_sha256':sha(canonical(state))}
        history.append({'seq':seq,'body':canonical(event).decode(),'sha256':event['state_sha256']});before=state
    return history


@pytest.mark.parametrize('case',['erase_retry','rewrite_old_reason','rewrite_old_artifact','identity_midstream','jump_completion','fake_transition','skip_with_attempt'])
def test_correctly_rehashed_invalid_history_is_rejected(evidence,case):
    v=copy.deepcopy(evidence);values=states(v)
    if case=='erase_retry':
        for state in values:
            if state['attempts']:state['attempts']=state['attempts'][1:]
    elif case=='jump_completion':values=values[:3]+values[-1:]
    else:
        state=values[-1]
        if case=='rewrite_old_reason':state['attempts'][0]['reason']='CHANGED'
        elif case=='rewrite_old_artifact':next(o for o in state['outcomes'].values() if o['status']=='COMPLETED')['artifact']['sha256']='0'*64
        elif case=='identity_midstream':state['identity']['package_sha256']='0'*64
        elif case=='fake_transition':state['last_transition']='BOUNDED_STATE_FIXTURE'
        elif case=='skip_with_attempt':state['attempts'][-1]['unit']=62
    v['history']=rechain(values);v['final_state']=canonical(values[-1])
    with pytest.raises(DataError):audit_campaign(**v)


def test_delta_digest_is_state_digest_not_body_digest(evidence):
    assert evidence['history'][0]['sha256']!=sha(evidence['history'][0]['body'].encode())
    state,report=reconstruct_history(evidence['final_state'],evidence['history'],evidence['controls'])
    assert canonical(state)==evidence['final_state'] and report['attempts']==37


@pytest.mark.parametrize('reason',['UNIT_INTEGRITY_FAILURE','LAUNCH_FAILED','HEALTH_HALT'])
def test_global_block_cannot_be_rewritten_as_terminal_fit_failure(evidence,reason):
    v=copy.deepcopy(evidence);values=states(v)
    for state in values:
        for a in state['attempts']:
            if a['unit']==3 and a['status']=='FAILED':a['reason']=reason
        if UNITS[3].key in state['outcomes']:state['outcomes'][UNITS[3].key]['reason']=reason
    card=json.loads(v['scorecard'])
    for row in card['search_history']:
        if row['candidate_id']=='ridge-h01-a001' and row['year']==2021:row['failure_reason']='DEPENDENCY_FAILED'
    v['history']=rechain(values);v['final_state']=canonical(values[-1]);v['scorecard']=canonical(card)
    with pytest.raises(DataError):audit_campaign(**v)


def test_failure_transition_name_matches_derived_state(evidence):
    values=states(evidence);state=next(s for s in values if s['last_transition']=='UNIT_READY');state['last_transition']='UNIT_COMPLETED'
    with pytest.raises(DataError):reconstruct_history(canonical(values[-1]),rechain(values),evidence['controls'])


def rewrite_first_frame(evidence,edit):
    v=copy.deepcopy(evidence);values=states(v);o=values[-1]['outcomes'][UNITS[0].key];path=o['artifact']['path'];header,body=v['frames'][path].split(b'\n',1);h=json.loads(header);b=json.loads(body);edit(b)
    raw=canonical(b);h.update(payload_sha256=sha(raw),payload_bytes=len(raw));frame=canonical(h)+b'\n'+raw;v['frames'][path]=frame
    for state in values:
        if UNITS[0].key in state['outcomes']:
            outcome=state['outcomes'][UNITS[0].key];outcome['payload_sha256']=sha(raw);outcome['artifact'].update(sha256=sha(frame),size_bytes=len(frame))
    v['history']=rechain(values);v['final_state']=canonical(values[-1]);card=json.loads(v['scorecard']);card['search_history'][0]['artifact_sha256']=sha(raw);v['scorecard']=canonical(card)
    return v


@pytest.mark.parametrize('case',['duplicate_dates','wrong_candidate_rows','duplicate_omission'])
def test_coherently_rehashed_fold_grid_contradictions_are_rejected(evidence,case):
    def edit(b):
        if case=='duplicate_dates':
            for replay in b['replays'].values():
                for p in replay['portfolios'].values():p['days'][0]['session']=b['end']
        elif case=='wrong_candidate_rows':b['prediction_report']['coverage']['candidate_rows']-=1
        else:b['prediction_report']['omissions'][1]=b['prediction_report']['omissions'][0]
    v=rewrite_first_frame(evidence,edit);card=json.loads(v['scorecard']);p=card['candidates'][0]['prediction']
    if case=='duplicate_dates':p['daily_rank_correlation'][0]['session']=p['daily_rank_correlation'][1]['session']
    elif case=='wrong_candidate_rows':p['coverage']['candidate_rows']-=1
    v['scorecard']=canonical(card)
    with pytest.raises(DataError):audit_campaign(**v)


def test_rechaining_unchanged_history_preserves_valid_evidence(evidence):
    v=copy.deepcopy(evidence);v['history']=rechain(states(v))
    assert json.loads(audit_campaign(**v).content)['status']=='VERIFIED_PASS'


@pytest.fixture(scope='module')
def fit_pair():
    from compertum.modeling.checkpoints import prepare_fit_checkpoint
    from compertum.modeling.candidate import evaluate_candidate
    from helpers.model_campaign_fixture import campaign_fixture,SECTORS
    chunks,ts,te,start,end,asof=campaign_fixture();fit=prepare_fit_checkpoint(chunks,SECTORS,ts,te,2021,'ridge-h01-a001')
    result=evaluate_candidate(chunks,SECTORS,ts,te,start,end,'ridge-h01-a001',scoring_as_of=asof,fit_checkpoint=fit,expected_fit_sha256=fit.sha256)
    return json.loads(fit.content),json.loads(result.content)


def pair_frames(fit_pair,edit=lambda f:None):
    from compertum.simulation.campaign_record import pack_result
    f,v=copy.deepcopy(fit_pair);edit(f)
    f['fit_rows_sha256']=sha(canonical(f['fit_rows']));f['fit_manifest_sha256']=sha(canonical(f['fit_manifest']));f['model_sha256']=sha(canonical(f['model']))
    for k in ('dataset_assembly','fit_rows','fit_manifest','fit_manifest_sha256','model','model_sha256'):v[k]=copy.deepcopy(f[k])
    for replay in v['replays'].values():replay['model_sha256']=v['model_sha256']
    request='a'*64;run='00000000-0000-4000-8000-000000000001';outcomes={u.key:dict(status='FAILED',reason='TEST_FAILURE') for u in UNITS};frames={}
    for i,b,dependency in ((3,f,None),(4,v,sha(canonical(f)))):
        raw=pack_result(canonical(b),request,i,dependency);path=f'artifacts/runs/{run}/baseline/unit-{i:02}-attempt-1.campaign';frames[path]=raw
        outcomes[UNITS[i].key]=dict(status='COMPLETED',artifact={'path':path,'size_bytes':len(raw),'sha256':sha(raw)},dependency_sha256=dependency,payload_sha256=sha(canonical(b)))
    state=dict(outcomes=outcomes,request_sha256=request,attempts=[]);fold={k:v[k] for k in ('training_start','training_end','start','end','market_sha256')};fold['scoring_as_of']=v['prediction_report']['scoring_as_of']
    return state,dict(folds=[fold,{},{}]),frames


def test_valid_committed_fit_pair_binding(fit_pair):
    from compertum.audit_campaign import _frames
    results,failures=_frames(*pair_frames(fit_pair));assert len(results)==1 and len(failures)==35


@pytest.mark.parametrize('case',['model_candidate','model_horizon','model_cutoff','manifest_year','manifest_bundle','rows_horizon'])
def test_rehashed_nested_fit_identity_conflicts_are_rejected(fit_pair,case):
    from compertum.audit_campaign import _frames
    def edit(f):
        if case=='model_candidate':f['model']['candidate_id']='ridge-h05-a001'
        elif case=='model_horizon':f['model']['horizon']=5
        elif case=='model_cutoff':f['model']['fit_cutoff']='2021-01-05T12:00:00+00:00'
        elif case=='manifest_year':
            f['fit_manifest']['year']=2022;f['model']['fit_manifest_sha256']=sha(canonical(f['fit_manifest']))
        elif case=='manifest_bundle':
            f['fit_manifest']['bundle_sha256']='0'*64;f['model']['fit_manifest_sha256']=sha(canonical(f['fit_manifest']))
        else:
            f['fit_rows']['horizon']=5;h=sha(canonical(f['fit_rows']));f['model']['bundle_sha256']=h;f['fit_manifest']['bundle_sha256']=h;f['dataset_assembly']['fit_rows_sha256']=h;f['model']['fit_manifest_sha256']=sha(canonical(f['fit_manifest']))
    with pytest.raises(DataError):_frames(*pair_frames(fit_pair,edit))


def test_coherently_rehashed_run_cannot_exceed_declared_budget(evidence):
    v=copy.deepcopy(evidence);bundle=json.loads(v['campaign']);maximum=len(v['campaign'])+sum(map(len,v['frames'].values()))-4096;bundle['maximum_bytes']=maximum;v['campaign']=canonical(bundle);digest=sha(v['campaign']);v['expected_campaign_sha256']=digest
    frame_hashes={}
    for path,raw in v['frames'].items():
        h,b=raw.split(b'\n',1);header=json.loads(h);header['input_sha256']=digest;frame=canonical(header)+b'\n'+b;v['frames'][path]=frame;frame_hashes[path]=sha(frame)
    values=states(v)
    for state in values:
        state.update(request_sha256=digest,maximum_bytes=maximum)
        if state['input_artifact']:state['input_artifact'].update(sha256=digest,size_bytes=len(v['campaign']))
        for a in state['attempts']:a['input_sha256']=digest
        for o in state['outcomes'].values():
            if o['status']=='COMPLETED':o['artifact']['sha256']=frame_hashes[o['artifact']['path']]
    for c in v['controls']:
        r=json.loads(c['receipt']);r.update(request_sha256=digest,maximum_bytes=maximum);r['input_artifact'].update(sha256=digest,size_bytes=len(v['campaign']));c['receipt']=canonical(r).decode()
    v['history']=rechain(values);v['final_state']=canonical(values[-1])
    with pytest.raises(DataError):audit_campaign(**v)


def test_legacy_unsealed_receipts_are_explicit_and_preserved(evidence):
    v=copy.deepcopy(evidence)
    for c in v['controls']:
        r=json.loads(c['receipt']);r.pop('protocol_status');c['receipt']=canonical(r).decode()
    report=json.loads(audit_campaign(**v).content)
    assert report['history']['legacy_receipt_count']==len(v['controls']) and evidence['controls']!=v['controls']


@pytest.mark.parametrize('case',['wrong_present','other_missing','extra','sealed_missing'])
def test_legacy_receipt_exception_is_narrow(evidence,case):
    v=copy.deepcopy(evidence);r=json.loads(v['controls'][0]['receipt'])
    if case=='wrong_present':r['protocol_status']='SEALED_SYNTHETIC_DEVELOPMENT'
    elif case=='other_missing':r.pop('maximum_bytes')
    elif case=='extra':r['extra']=True
    else:
        values=states(v)
        for state in values:state['protocol_seal']={'fixture':'immutable-seal'}
        v['history']=rechain(values);v['final_state']=canonical(values[-1]);r.pop('protocol_status')
    v['controls'][0]['receipt']=canonical(r).decode()
    with pytest.raises(DataError):audit_campaign(**v)


def hand_fold(year,navs,targets):
    from decimal import Decimal as D
    from compertum.simulation.metrics import metrics
    from compertum.data.calendar import session_times
    day={2021:'2021-01-04',2022:'2022-01-03',2023:'2023-01-03'}[year];dates=[day]
    for _ in navs[1:]:dates.append(session_times(dates[-1]).next_date)
    strategy=dict(days=[{'session':d,'nav':n} for d,n in zip(dates,navs)],trades=[{'turnover':'0.2'}],checkpoints=[0],completed_intervals=1,metrics=metrics([D(10000)]+list(map(D,navs)),[D(10000)]*(len(navs)+1)))
    spy={'days':[{'session':d,'nav':'10000'} for d in dates]}
    rows=[{'session':dates[i],'symbol':'AAPL','prediction':'0','momentum_prediction':'0','target':str(t)} for i,t in enumerate(targets)]
    return {'year':year,'replays':{cost:{'portfolios':{'strategy':strategy,'spy60':spy}} for cost in ('10','20')},'prediction_report':{'rows':rows,'omissions':[],'coverage':{'candidate_rows':len(rows),'feature_eligible_rows':len(rows),'eligible_rows':len(rows),'scored_rows':len(rows),'omitted_rows':0}}}


def test_nonzero_unequal_fold_returns_and_predictions_use_individual_observations():
    from decimal import Decimal as D
    f1=hand_fold(2021,['11000','9900'],[1,3]);f2=hand_fold(2022,['12000'],[2])
    card=reconstruct_aggregate({('momentum-h01',2021):(f1,'1'*64),('momentum-h01',2022):(f2,'2'*64)},{});row=card['candidates'][0];trade=row['trading']['10']
    assert list(map(D,trade['metrics']['returns']))==[D('.1'),D('-.1'),D('.2')]
    assert D(trade['metrics']['annual_mean_excess'])==D('16.8') and D(trade['total_turnover'])==D('.4')
    assert D(trade['metrics']['max_drawdown'])==D('.1') and trade['observations']==3 and trade['completed_intervals']==2
    assert D(row['prediction']['metrics']['mse'])==D(14)/3 and D(row['prediction']['metrics']['mae'])==2
    assert row['state']=='PENDING' and card['diagnostic_rankings']['1']==[]
    assert abs(D(trade['metrics']['cagr'])-(D('1.188')**84-1))<D('1e-10')


def test_tolerated_scalar_change_cannot_change_exact_ranking():
    from compertum.audit_campaign import _aggregate_compare
    results={}
    for candidate in ('momentum-h01','ridge-h01-a001','ridge-h01-a010'):
        for year in (2021,2022,2023):results[(candidate,year)]=(hand_fold(year,['10000'],[1]),'1'*64)
    expected=reconstruct_aggregate(results,{});actual=copy.deepcopy(expected)
    assert expected['diagnostic_rankings']['1']==['momentum-h01','ridge-h01-a001','ridge-h01-a010']
    actual['candidates'][3]['trading']['10']['metrics']['annual_mean_excess']='0.00000000001'
    with pytest.raises(DataError):_aggregate_compare(actual,expected)
