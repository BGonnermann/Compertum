"""Independent immutable campaign history and aggregate arithmetic checks.

A consistency pass does not authenticate an author or grant shortlist authority.
"""
from collections import Counter
from copy import deepcopy
from dataclasses import asdict,dataclass
from decimal import Decimal as D,DecimalException
import hashlib,json,re
from uuid import UUID
from .data.encoding import canonical
from .data.errors import DataError
from .data.calendar import utc_time
from .modeling.campaign import UNITS,read_campaign
from .modeling.registry import VARIANTS,variant,FEATURES
from .audit import _precision,reconstruct_metrics,_metrics,_number,_decimal,_near
from .audit_predictions import reconstruct_errors,reconstruct_rank,_numeric_report,_exact,_dates,_cutoff
from .simulation.market import WATCHLIST
from .runtime.startup_record import outcome_proof
from .runtime.campaign_environment import outcome_environment,validate_expected,check_native,check_input_state

MIB=1024**2
YEARS=(2021,2022,2023)

@dataclass(frozen=True)
class CampaignAudit:
    content:bytes
    sha256:str


def _check(condition):
    if not condition:raise DataError('AUDIT_CAMPAIGN_MISMATCH')


def _sha(raw):return hashlib.sha256(raw).hexdigest()
def _hash(value):return _sha(canonical(value))
def _digest(value):return type(value) is str and re.fullmatch('[0-9a-f]{64}',value) is not None
def _reason(value):return type(value) is str and re.fullmatch('[A-Z][A-Z0-9_]{0,95}',value) is not None


def _json(raw,maximum):
    _check(type(raw) is bytes and 0<len(raw)<=maximum)
    v=json.loads(raw);_check(canonical(v)==raw);return v


def _artifact(value,run,path,maximum):
    _check(type(value) is dict and set(value)=={'artifact_id','path','size_bytes','sha256','task_id'})
    _check(str(UUID(value['artifact_id']))==value['artifact_id'] and value['task_id']==run and value['path']==path)
    _check(type(value['size_bytes']) is int and 0<value['size_bytes']<=maximum and _digest(value['sha256']))


def _receipt(r):
    integers={'pid','exit_code','active_processes','affinity','memory_limit','peak_job_memory'}
    booleans={'timed_out','assigned_before_resume','observed_children_exited'}
    _check(type(r) is dict and integers|booleans|{'observed_child_pids'}<=set(r)<=integers|booleans|{'observed_child_pids','execution_identity'} and len(canonical(r))<=2048)
    _check(all(type(r[k]) is int and 0<=r[k]<2**64 for k in integers) and all(type(r[k]) is bool for k in booleans))
    if 'execution_identity' in r:
        from .runtime.job_identity import validate_execution_identity
        validate_execution_identity(r['execution_identity']);_check(r['execution_identity']['process']['pid']==r['pid'])
    _check(type(r['observed_child_pids']) is list and len(r['observed_child_pids'])<=64 and all(type(p) is int and 0<p<2**32 for p in r['observed_child_pids']))


def _state(s):
    required={'run_id','state','active_owner','request_sha256','identity','maximum_bytes','input_artifact','attempts','results','input_kind','campaign_version','outcomes','updated_at','last_transition'}
    _check(type(s) is dict and required<=set(s)<=required|{'protocol_seal','clean_environment'})
    _check(str(UUID(s['run_id']))==s['run_id'] and _digest(s['request_sha256']) and s['input_kind']=='synthetic-campaign' and type(s['campaign_version']) is int and s['campaign_version']==1)
    _check(type(s['maximum_bytes']) is int and 0<s['maximum_bytes']<=128*MIB and s['results']==[])
    _check(type(s['active_owner']) is str and 0<len(s['active_owner'])<=256)
    _check(s['state'] in ('PREPARING','PAUSED','READY','RUNNING','INTERRUPTED','BLOCKED','COMPLETED','STOPPED','FAILED'))
    utc_time(s['updated_at']);_check(_reason(s['last_transition']))
    attempts=s['attempts'];outcomes=s['outcomes'];_check(type(attempts) is list and len(attempts)<=126 and type(outcomes) is dict and len(outcomes)<=63)
    _check(set(outcomes)=={u.key for u in UNITS[:len(outcomes)]})
    if s['input_artifact'] is not None:_artifact(s['input_artifact'],s['run_id'],f"artifacts/runs/{s['run_id']}/baseline/inputs.json",20*MIB)
    clean=s.get('clean_environment')
    if 'clean_environment' in s:
        validate_expected(clean);_check(clean['run_id']==s['run_id'] and 'protocol_seal' in s)
    grouped={};previous=-1
    for a in attempts:
        keys={'unit','identity','attempt','status','input_sha256','dependency_sha256','output_path','reservation_id'}
        _check(type(a) is dict and keys<=set(a)<=keys|{'reason','job_receipt','native_execution'})
        i=a['unit'];_check(type(i) is int and previous<=i<63 and i>=0);previous=i;u=UNITS[i];prior=grouped.setdefault(i,[])
        _check(not prior or prior[-1]['status']=='INTERRUPTED');prior.append(a)
        _check(len(prior)<=2 and type(a['attempt']) is int and a['attempt']==len(prior) and a['identity']==asdict(u))
        _check(a['status'] in ('RUNNING','COMPLETED','FAILED','INTERRUPTED','BLOCKED') and a['input_sha256']==s['request_sha256'])
        _check(a['output_path']==f"artifacts/runs/{s['run_id']}/baseline/unit-{i:02}-attempt-{a['attempt']}.campaign")
        _check(a['reservation_id'] is None or str(UUID(a['reservation_id']))==a['reservation_id'])
        if 'reason' in a:_check(_reason(a['reason']))
        parent=outcomes.get(UNITS[u.fit_unit].key) if u.fit_unit is not None else None
        _check(u.fit_unit is None or parent is not None and parent['status']=='COMPLETED')
        _check(a['dependency_sha256']==(parent['payload_sha256'] if parent else None))
        if 'native_execution' in a:
            from .runtime.job_identity import validate_execution_identity
            n=a['native_execution'];validate_execution_identity(n);check_native(n,clean)
            _check(n['role']=='experiment_runner' and n['task_id']==s['run_id'] and n['code_sha256']==s['identity']['package_sha256'] and n['lock_sha256']==s['identity']['lock_sha256'])
        if clean is not None and a['status']=='COMPLETED':_check('native_execution' in a)
        if 'native_execution' in a and a['status']=='COMPLETED':_check('job_receipt' in a)
        if 'job_receipt' in a:
            _check(a['job_receipt'].get('execution_identity')==a.get('native_execution'))
            r=a['job_receipt'];_receipt(r)
            if a['status']=='COMPLETED':_check(r['exit_code']==0 and not r['timed_out'] and r['active_processes']==0 and r['assigned_before_resume'] and r['observed_children_exited'])
    for key,o in outcomes.items():
        i=o['unit'];_check(type(i) is int and 0<=i<63);u=UNITS[i];_check(key==u.key and o['identity']==asdict(u))
        _check(o['status'] in ('COMPLETED','FAILED','SKIPPED'))
        if o['status']=='SKIPPED':
            _check(set(o)=={'unit','identity','status','reason'} and u.fit_unit is not None and i not in grouped and outcomes[UNITS[u.fit_unit].key]['status']=='FAILED' and o['reason']=='DEPENDENCY_FAILED');continue
        _check(i in grouped and grouped[i][-1]['status']==o['status']);last=grouped[i][-1]
        if o['status']=='COMPLETED':
            _check(set(o)=={'unit','identity','status','artifact','payload_sha256','dependency_sha256'} and _digest(o['payload_sha256']) and o['dependency_sha256']==last['dependency_sha256'])
            _artifact(o['artifact'],s['run_id'],last['output_path'],16*MIB)
        else:_check(set(o)=={'unit','identity','status','reason'} and _reason(o['reason']) and o['reason']==last['reason'])
    pending=[items[-1] for i,items in grouped.items() if UNITS[i].key not in outcomes];_check(len(pending)<=1)
    if pending:_check(pending[0] is attempts[-1] and pending[0]['unit']==len(outcomes) and pending[0]['status'] in ('RUNNING','INTERRUPTED','BLOCKED'))
    _check(s['state']!='RUNNING' or len(pending)==1 and pending[0]['status']=='RUNNING')
    _check(s['state']=='RUNNING' or not pending or pending[0]['status']!='RUNNING')
    if s['state']=='COMPLETED':_check(len(outcomes)==63)
    if s['state']=='READY':_check(len(outcomes)<63)


def _terminal_failure(expected,reason):
    _check(_reason(reason));a=expected['attempts'][-1];a.update(status='FAILED',reason=reason);i=a['unit'];u=UNITS[i]
    expected['outcomes'][u.key]={'unit':i,'identity':asdict(u),'status':'FAILED','reason':reason}
    for j,child in enumerate(UNITS):
        if child.fit_unit==i:expected['outcomes'][child.key]={'unit':j,'identity':asdict(child),'status':'SKIPPED','reason':'DEPENDENCY_FAILED'}
    expected['state']='COMPLETED' if len(expected['outcomes'])==63 else 'READY'


def _transition(before,after):
    reason=after['last_transition'];_state(after)
    if before is None:
        _check(reason=='REGISTERED' and after['state']=='PREPARING' and not after['attempts'] and not after['outcomes'] and after['input_artifact'] is None);return
    _check(utc_time(after['updated_at'])>=utc_time(before['updated_at']))
    expected=deepcopy(before);expected.update(updated_at=after['updated_at'],last_transition=reason)
    if reason=='INPUTS_PUBLISHED':
        _check(before['state']=='PREPARING' and after['input_artifact'] is not None);expected.update(state='PAUSED',input_artifact=after['input_artifact'])
    elif reason=='PREPARATION_FAILED':
        _check(before['state']=='PREPARING');expected.update(state='FAILED',input_artifact=None)
    elif reason=='UNIT_STARTED':
        _check(before['state']=='READY' and len(after['attempts'])==len(before['attempts'])+1)
        a=after['attempts'][-1];_check(a['unit']==len(before['outcomes']) and a['status']=='RUNNING' and set(a)=={'unit','identity','attempt','status','input_sha256','dependency_sha256','output_path','reservation_id'})
        expected['attempts'].append(a);expected.update(state='RUNNING',active_owner=after['active_owner'])
    elif reason=='NATIVE_EXECUTION_BOUND':
        _check(before['state']=='RUNNING' and 'native_execution' not in before['attempts'][-1] and 'job_receipt' not in before['attempts'][-1]);expected['attempts'][-1]['native_execution']=after['attempts'][-1]['native_execution']
    elif reason=='JOB_EXIT_VERIFIED':
        _check(before['state']=='RUNNING' and 'job_receipt' not in before['attempts'][-1]);expected['attempts'][-1]['job_receipt']=after['attempts'][-1]['job_receipt']
    elif reason=='UNIT_CHECKPOINTED':
        _check(before['state']=='RUNNING');a=expected['attempts'][-1];u=UNITS[a['unit']];_check(u.key not in before['outcomes'])
        o=after['outcomes'][u.key];_check(o['status']=='COMPLETED');a['status']='COMPLETED';expected['outcomes'][u.key]=o
        expected['state']='COMPLETED' if len(expected['outcomes'])==63 else 'READY'
    elif reason in ('UNIT_READY','UNIT_COMPLETED'):
        _check(before['state']=='RUNNING' and after['attempts'][-1]['reason'] not in ('UNIT_INTEGRITY_FAILURE','LAUNCH_FAILED','HEALTH_HALT'));_terminal_failure(expected,after['attempts'][-1]['reason']);_check(reason=='UNIT_'+expected['state'])
    elif reason in ('UNIT_INTERRUPTED','UNIT_BLOCKED'):
        _check(before['state']=='RUNNING');a=after['attempts'][-1];_check(_reason(a['reason']))
        blocked=a['reason'] in ('LAUNCH_FAILED','HEALTH_HALT','UNIT_INTEGRITY_FAILURE');_check(blocked==(reason=='UNIT_BLOCKED'))
        if not blocked:_check(not(a['reason']=='WORKER_FAILED' and a['attempt']==2))
        expected['state']='BLOCKED' if blocked else 'INTERRUPTED';expected['attempts'][-1].update(status=expected['state'],reason=a['reason'])
    elif reason=='OWNER_RESTART':
        _check(before['state'] in ('RUNNING','PREPARING'));expected['state']='INTERRUPTED' if before['input_artifact'] else 'FAILED'
        if expected['attempts'] and expected['attempts'][-1]['status']=='RUNNING':expected['attempts'][-1].update(status='INTERRUPTED',reason='OWNER_RESTART')
    elif reason=='SUPERVISOR_START_PAUSED':
        _check(before['state']=='READY');expected['state']='PAUSED'
    elif reason in ('RESUME','PAUSE','STOP'):
        _check(before['state'] not in ('PREPARING','RUNNING','FAILED','STOPPED','COMPLETED'))
        if reason=='RESUME':
            if expected['attempts']:
                a=expected['attempts'][-1]
                if UNITS[a['unit']].key not in expected['outcomes'] and a['status']=='BLOCKED':
                    _check(a['reason'] in ('LAUNCH_FAILED','HEALTH_HALT'));a['status']='INTERRUPTED'
                if a['attempt']==2 and a['status']=='INTERRUPTED':_terminal_failure(expected,'TRANSIENT_ATTEMPTS_EXHAUSTED')
            if expected['state']!='COMPLETED':expected['state']='READY'
        else:expected['state']='PAUSED' if reason=='PAUSE' else 'STOPPED'
    else:raise DataError('AUDIT_HISTORY_TRANSITION')
    _exact(after,expected)


def _compact(s):
    counts=Counter(o['status'] for o in s['outcomes'].values())
    return dict(run_id=s['run_id'],state=s['state'],completed_units=counts['COMPLETED'],resolved_units=len(s['outcomes']),total_units=63,failed_units=counts['FAILED'],skipped_units=counts['SKIPPED'],input_artifact=s['input_artifact'],input_kind='synthetic-campaign',request_sha256=s['request_sha256'],maximum_bytes=s['maximum_bytes'],last_transition=s['last_transition'],financial_acceptance='UNVERIFIED',control_boundary='BETWEEN_COMPLETE_CAMPAIGN_UNITS',protocol_status='SEALED_SYNTHETIC_DEVELOPMENT' if 'protocol_seal' in s else 'UNSEALED_DIAGNOSTIC')


def reconstruct_history(final_state,history,controls):
    """Rebuild delta states and require semantic append-only transitions."""
    final=_json(final_state,512*1024);_check(type(history) is list and 1<=len(history)<=1024 and type(controls) is list and len(controls)<=128)
    _check(sum(len(canonical(r)) for r in history)<=16*MIB)
    state=None;control_states=[];transition_counts=Counter()
    for seq,record in enumerate(history,1):
        _check(type(record) is dict and set(record)=={'seq','body','sha256'} and type(record['seq']) is int and record['seq']==seq and type(record['body']) is str)
        event=_json(record['body'].encode(),512*1024);_check(set(event)=={'schema','previous_sha256','fields','attempts','outcomes','state_sha256'} and event['schema']=='campaign-history-delta-v1')
        _check(event['previous_sha256']==(_hash(state) if state is not None else None))
        _check(type(event['fields']) is dict and not {'attempts','outcomes'}&set(event['fields']) and type(event['attempts']) is dict and type(event['outcomes']) is dict)
        before=state;state=deepcopy(state) if state is not None else {};state.update(event['fields']);state.setdefault('attempts',[]);state.setdefault('outcomes',{})
        _check(all(type(k) is str and re.fullmatch('0|[1-9][0-9]{0,2}',k) for k in event['attempts']))
        for key,attempt in sorted(event['attempts'].items(),key=lambda pair:int(pair[0])):
            index=int(key);_check(0<=index<=len(state['attempts']))
            if index==len(state['attempts']):state['attempts'].append(attempt)
            else:state['attempts'][index]=attempt
        state['outcomes'].update(event['outcomes']);_check(_hash(state)==record['sha256']==event['state_sha256'])
        _transition(before,state);transition_counts[state['last_transition']]+=1
        if state['last_transition'] in ('RESUME','PAUSE','STOP'):control_states.append((state['last_transition'].lower(),canonical(_compact(state))))
    _exact(state,final);actual=[];requests=set();legacy=0
    for c in controls:
        _check(type(c) is dict and set(c)=={'request_id','action','receipt'} and str(UUID(c['request_id']))==c['request_id'] and c['request_id'] not in requests);requests.add(c['request_id'])
        _check(c['action'] in ('resume','pause','stop') and type(c['receipt']) is str);v=_json(c['receipt'].encode(),4096)
        if 'protocol_status' not in v:
            _check('protocol_seal' not in final and set(v)==set(_compact(final))-{'protocol_status'});v['protocol_status']='UNSEALED_DIAGNOSTIC';legacy+=1
        actual.append((c['action'],canonical(v)))
    _check(Counter(actual)==Counter(control_states))
    return state,{'events':len(history),'controls':len(controls),'legacy_receipt_count':legacy,'attempts':len(state['attempts']),'transition_counts':dict(sorted(transition_counts.items())),'final_state_sha256':_sha(final_state),'history_sha256':_hash(history),'controls_sha256':_hash(controls)}


def _fit_binding(v,fold,c,year):
    rows=v['fit_rows'];manifest=v['fit_manifest'];model=v['model'];assembly=v['dataset_assembly'];cutoff=_cutoff(year).isoformat()
    _check(c.kind=='ridge' and type(rows['horizon']) is int and rows['horizon']==c.horizon)
    _check(rows['schema']=='fit-rows-v1' and rows['input_kind']=='SYNTHETIC_ENGINEERING' and rows['availability_basis']=='SIMULATED_AVAILABILITY')
    for part in (rows,manifest,model,assembly):_exact(part['feature_order'],list(FEATURES))
    _check(manifest['schema']=='engineering-fit-manifest-v1' and manifest['status']=='SYNTHETIC_ENGINEERING' and type(manifest['year']) is int and manifest['year']==year and type(manifest['horizon']) is int and manifest['horizon']==c.horizon)
    _check(manifest['cutoff']==cutoff and manifest['bundle_sha256']==_hash(rows) and manifest['registry_sha256']==_hash([asdict(c) for c in VARIANTS]))
    _check(model['schema']=='ridge-engineering-v1' and model['status']=='SYNTHETIC_ENGINEERING' and model['financial_accepted'] is False and model['candidate_id']==c.candidate_id and type(model['horizon']) is int and model['horizon']==c.horizon)
    _check(model['fit_cutoff']==cutoff and model['bundle_sha256']==_hash(rows) and model['fit_manifest_sha256']==_hash(manifest) and type(model['observations']) is int and model['observations']==len(manifest['included']))
    _check(type(model['resolved']['ridge']['alpha']) is int and model['resolved']['ridge']['alpha']==c.alpha)
    _check(assembly['source_market_sha256']==fold['market_sha256'] and assembly['start']==fold['training_start'] and assembly['end']==fold['training_end'] and type(assembly['horizon']) is int and assembly['horizon']==c.horizon)
    _check(assembly['fit_rows_sha256']==_hash(rows) and _hash(manifest)==v['fit_manifest_sha256'] and _hash(model)==v['model_sha256'])


def _grid(v,fold,c):
    dates=_dates(fold['start'],fold['end']);_check(set(v['replays'])=={'10','20'})
    for cost,r in v['replays'].items():
        _check(r['candidate_id']==c.candidate_id and type(r['horizon']) is int and r['horizon']==c.horizon and type(r['cost_bps']) is int and r['cost_bps']==int(cost))
        _check(r['start']==fold['start'] and r['end']==fold['end'] and r['market_sha256']==fold['market_sha256'] and r['model_sha256']==v['model_sha256'] and r['financial_accepted'] is False)
        _check(set(r['portfolios'])=={'strategy','spy60','spy100','equal60','zero'})
        for p in r['portfolios'].values():
            _exact([row['session'] for row in p['days']],dates)
            _check(type(p['completed_intervals']) is int and p['completed_intervals']>=0 and type(p['checkpoints']) is list)
            _check(all(type(i) is int and 0<=i<len(dates) for i in p['checkpoints']) and p['checkpoints']==sorted(set(p['checkpoints'])))
            _check(all(_decimal(t['turnover'])>=0 for t in p['trades']))
    report=v['prediction_report'];rows=report['rows'];omissions=report['omissions'];identities=[(r['session'],r['symbol']) for r in rows+omissions]
    expected={(day,symbol) for day in dates for symbol in WATCHLIST};_check(len(identities)==len(expected) and set(identities)==expected)
    coverage=report['coverage'];_check(set(coverage)=={'candidate_rows','feature_eligible_rows','eligible_rows','scored_rows','omitted_rows'} and all(type(n) is int for n in coverage.values()))
    _check(coverage['candidate_rows']==len(expected) and coverage['scored_rows']==len(rows) and coverage['omitted_rows']==len(omissions) and 0<=len(rows)<=coverage['eligible_rows']<=coverage['feature_eligible_rows']<=len(expected))


def _frames(state,campaign,frames):
    _check(type(frames) is dict and len(frames)<=63 and sum(len(raw) for raw in frames.values())<=128*MIB)
    wanted={o['artifact']['path'] for o in state['outcomes'].values() if o['status']=='COMPLETED'};_check(set(frames)==wanted)
    bodies={};results={};failures={}
    for index,u in enumerate(UNITS):
        o=state['outcomes'][u.key]
        if o['status']!='COMPLETED':
            if u.phase=='evaluate':failures[(u.candidate_id,u.year)]=o['reason']
            continue
        raw=frames[o['artifact']['path']];_check(type(raw) is bytes and len(raw)==o['artifact']['size_bytes'] and _sha(raw)==o['artifact']['sha256'])
        at=raw.index(b'\n',0,4096);body=raw[at+1:];v=_json(body,16*MIB)
        expected=dict(format='compertum-campaign-unit-v1',unit=index,**asdict(u),input_sha256=state['request_sha256'],dependency_sha256=o['dependency_sha256'],financial_accepted=False,payload_sha256=_sha(body),payload_bytes=len(body))
        startup=outcome_proof(state,index)
        if startup is not None:expected.update(format='compertum-campaign-unit-v2',startup=startup)
        environment=outcome_environment(state,index)
        if environment is not None:expected.update(format='compertum-campaign-unit-v3',environment=environment)
        _check(raw[:at]==canonical(expected) and _sha(body)==o['payload_sha256'])
        fold=campaign['folds'][YEARS.index(u.year)];_check(v['status']=='SYNTHETIC_ENGINEERING' and v['financial_accepted'] is False and type(v['year']) is int and v['year']==u.year)
        _check(v['training_start']==fold['training_start'] and v['training_end']==fold['training_end'])
        if u.phase=='fit':
            _check(v['schema']=='synthetic-fit-checkpoint-v1' and v['candidate_id']==u.candidate_id and v['source_market_sha256']==fold['market_sha256'])
            _check(_hash(v['fit_rows'])==v['fit_rows_sha256']==v['dataset_assembly']['fit_rows_sha256'] and _hash(v['fit_manifest'])==v['fit_manifest_sha256'] and _hash(v['model'])==v['model_sha256'])
            _check(v['model']['bundle_sha256']==v['fit_rows_sha256'] and v['model']['fit_manifest_sha256']==v['fit_manifest_sha256']);_fit_binding(v,fold,variant(u.candidate_id),u.year);bodies[index]=v
        else:
            _check(v['schema']=='synthetic-candidate-fold-v1' and v['candidate']==asdict(variant(u.candidate_id)) and v['full_M2'] is False and v['registered_family']==[asdict(c) for c in VARIANTS])
            _check(all(v[k]==fold[k] for k in ('start','end','market_sha256')) and v['prediction_report']['scoring_as_of']==fold['scoring_as_of'])
            _grid(v,fold,variant(u.candidate_id))
            if u.fit_unit is not None:
                parent=bodies.pop(u.fit_unit);_check(all(v[k]==parent[k] for k in ('dataset_assembly','fit_rows','fit_manifest','fit_manifest_sha256','model','model_sha256')))
            results[(u.candidate_id,u.year)]=(v,o['payload_sha256'])
    return results,failures


def _aggregate_trades(folds,cost):
    nav=[D(10000)];benchmark=[D(10000)];turnover=D(0);checkpoints=intervals=0;annual=[]
    for fold in folds:
        p=fold['replays'][cost]['portfolios'];strategy=p['strategy'];spy=p['spy60'];prior=prior_spy=D(10000)
        _check(len(strategy['days'])==len(spy['days']) and len(strategy['days'])>0)
        original=[D(10000)];original_spy=[D(10000)]
        for a,b in zip(strategy['days'],spy['days']):
            _check(a['session']==b['session']);n=_decimal(a['nav']);bn=_decimal(b['nav']);_check(n>0 and bn>0)
            nav.append(nav[-1]*n/prior);benchmark.append(benchmark[-1]*bn/prior_spy);prior=n;prior_spy=bn;original.append(n);original_spy.append(bn)
        own=reconstruct_metrics(original,original_spy);_metrics(strategy['metrics'],own)
        turnover+=sum(_decimal(t['turnover']) for t in strategy['trades']);checkpoints+=len(strategy['checkpoints']);intervals+=strategy['completed_intervals']
        annual.append({'year':fold['year'],'annual_mean_excess':own['annual_mean_excess']})
    return dict(method='CONCATENATED_FOLD_DAILY_RETURNS',observations=len(nav)-1,metrics=reconstruct_metrics(nav,benchmark),total_turnover=_number(turnover),rebalance_checkpoints=checkpoints,completed_intervals=intervals,fold_excess=annual)


def _prediction(folds,candidate):
    rows=[r for fold in folds for r in fold['prediction_report']['rows']];p=[r['prediction'] for r in rows];targets=[r['target'] for r in rows]
    metrics=reconstruct_errors(p,targets);momentum=reconstruct_errors([r['momentum_prediction'] for r in rows],targets);daily=[]
    for fold in folds:
        report=fold['prediction_report']
        for day in (r['session'] for r in fold['replays']['10']['portfolios']['strategy']['days']):
            chosen=[r for r in report['rows'] if r['session']==day];rank=reconstruct_rank([r['prediction'] for r in chosen],[r['target'] for r in chosen])
            daily.append(dict(session=day,observations=len(chosen),spearman=rank,status='NO_SCORED_ROWS' if not chosen else 'DEFINED' if rank is not None else 'UNDEFINED_CONSTANT_OR_TOO_FEW_ROWS'))
    keys={'candidate_rows','feature_eligible_rows','eligible_rows','scored_rows','omitted_rows'};coverage={k:0 for k in keys}
    for f in folds:
        record=f['prediction_report']['coverage'];_check(set(record)==keys and all(type(n) is int and n>=0 for n in record.values()))
        _check(record['scored_rows']==len(f['prediction_report']['rows']) and record['omitted_rows']==len(f['prediction_report']['omissions']))
        for k in keys:coverage[k]+=record[k]
    improvement=metrics['mse_improvement'];gate='NOT_APPLICABLE' if candidate.kind=='momentum' else 'UNDEFINED' if improvement is None else 'PASS' if D(improvement)>=D('.01') else 'FAIL'
    return dict(metrics=metrics,momentum_metrics=momentum,coverage=coverage,daily_rank_correlation=daily,ml_contribution_gate=gate)


def _rank(row):
    t=row['trading']['10'];c=variant(row['candidate_id'])
    return (-D(t['metrics']['annual_mean_excess']),D(t['total_turnover']),c.kind!='momentum',c.candidate_id)


@_precision
def reconstruct_aggregate(results,failures):
    """Reconstruct all36 slots without calling the producer scorecard builder."""
    history=[];candidates=[]
    for c in VARIANTS:
        folds=[results[(c.candidate_id,y)][0] for y in YEARS if (c.candidate_id,y) in results]
        missing=[y for y in YEARS if (c.candidate_id,y) not in results and (c.candidate_id,y) not in failures]
        errors=[{'year':y,'reason':failures[(c.candidate_id,y)]} for y in YEARS if (c.candidate_id,y) in failures]
        candidates.append(dict(candidate_id=c.candidate_id,kind=c.kind,horizon=c.horizon,state='FAILED' if errors else 'COMPLETE_DIAGNOSTIC' if len(folds)==3 else 'PENDING',completed_years=[f['year'] for f in folds],missing_years=missing,failed_folds=errors,trading={cost:_aggregate_trades(folds,cost) for cost in ('10','20')} if folds else None,prediction=_prediction(folds,c) if folds else None))
        for year in YEARS:
            key=(c.candidate_id,year);history.append(dict(candidate_id=c.candidate_id,year=year,state='COMPLETED' if key in results else 'FAILED' if key in failures else 'PENDING',artifact_sha256=results[key][1] if key in results else None,failure_reason=failures.get(key)))
    rankings={str(h):[r['candidate_id'] for r in sorted((r for r in candidates if r['horizon']==h and r['state']=='COMPLETE_DIAGNOSTIC'),key=_rank)] for h in (1,5,21)}
    return dict(schema='synthetic-campaign-scorecard-v1',financial_accepted=False,full_M2=False,registered_family=[asdict(c) for c in VARIANTS],family_size=12,counts={'completed':len(results),'failed':len(failures),'pending':36-len(results)-len(failures)},search_history=history,candidates=candidates,diagnostic_rankings=rankings,shortlist=[],selection_status='UNQUALIFIED_SYNTHETIC_EVIDENCE',trust_basis='HASH_BOUND_TRUSTED_ENGINE_OUTPUTS_NOT_AUTHENTICATED_ORIGIN')


def _aggregate_compare(actual,expected):
    _check(type(actual) is dict and set(actual)==set(expected))
    for k in set(expected)-{'candidates'}:_exact(actual[k],expected[k])
    _check(type(actual['candidates']) is list and len(actual['candidates'])==12)
    for a,b in zip(actual['candidates'],expected['candidates']):
        _check(type(a) is dict and set(a)==set(b))
        for k in set(b)-{'trading','prediction'}:_exact(a[k],b[k])
        if b['trading'] is None:_exact(a['trading'],None);_exact(a['prediction'],None);continue
        _check(set(a['trading'])=={'10','20'})
        for cost in ('10','20'):
            at=a['trading'][cost];bt=b['trading'][cost];_check(set(at)==set(bt))
            for k in ('method','observations','rebalance_checkpoints','completed_intervals'):_exact(at[k],bt[k])
            _metrics(at['metrics'],bt['metrics']);_near(at['total_turnover'],D(bt['total_turnover']));_check(len(at['fold_excess'])==len(bt['fold_excess']))
            for x,y in zip(at['fold_excess'],bt['fold_excess']):_check(set(x)==set(y));_exact(x['year'],y['year']);_near(x['annual_mean_excess'],D(y['annual_mean_excess']))
        ap=a['prediction'];bp=b['prediction'];_check(set(ap)==set(bp))
        for k in ('metrics','momentum_metrics'):_numeric_report(ap[k],bp[k])
        for k in ('coverage','ml_contribution_gate'):_exact(ap[k],bp[k])
        _check(len(ap['daily_rank_correlation'])==len(bp['daily_rank_correlation']))
        for x,y in zip(ap['daily_rank_correlation'],bp['daily_rank_correlation']):
            _check(set(x)==set(y))
            for k in ('session','observations','status'):_exact(x[k],y[k])
            if y['spearman'] is None:_exact(x['spearman'],None)
            else:_near(x['spearman'],D(y['spearman']))
        reported=ap['metrics']['mse_improvement'];c=variant(a['candidate_id'])
        gate='NOT_APPLICABLE' if c.kind=='momentum' else 'UNDEFINED' if reported is None else 'PASS' if D(reported)>=D('.01') else 'FAIL';_exact(gate,ap['ml_contribution_gate'])
    for h in (1,5,21):_exact([r['candidate_id'] for r in sorted((r for r in actual['candidates'] if r['horizon']==h and r['state']=='COMPLETE_DIAGNOSTIC'),key=_rank)],expected['diagnostic_rankings'][str(h)])


@_precision
def audit_campaign(campaign,final_state,history,controls,frames,scorecard,*,expected_campaign_sha256,expected_identity):
    """Pure history/aggregate consistency, with no native or selection authority."""
    try:
        check_input_state(campaign,expected_campaign_sha256,_json(final_state,512*1024))
        bundle=read_campaign(campaign,expected_sha256=expected_campaign_sha256,identity=expected_identity)
        state,history_report=reconstruct_history(final_state,history,controls)
        _check(state['state']=='COMPLETED' and len(state['outcomes'])==63 and state['identity']==bundle['identity'] and state['request_sha256']==expected_campaign_sha256 and state['maximum_bytes']==bundle['maximum_bytes'])
        _check(state['input_artifact']['sha256']==_sha(campaign) and state['input_artifact']['size_bytes']==len(campaign))
        _check(len(campaign)+sum(len(raw) for raw in frames.values())<=state['maximum_bytes'])
        results,failures=_frames(state,bundle,frames);_check(len(results)+len(failures)==36)
        reconstructed=reconstruct_aggregate(results,failures);_aggregate_compare(_json(scorecard,16*MIB),reconstructed)
        counts=Counter(o['status'] for o in state['outcomes'].values())
        report=dict(schema='synthetic-campaign-history-audit-v1',status='VERIFIED_PASS',scope='IMMUTABLE_HISTORY_AND_AGGREGATE_CONSISTENCY',financial_accepted=False,full_M3=False,run_id=state['run_id'],campaign_sha256=expected_campaign_sha256,scorecard_sha256=_sha(scorecard),reconstructed_scorecard_sha256=_hash(reconstructed),history=history_report,attempts=len(state['attempts']),unit_counts={k:counts[k] for k in ('COMPLETED','FAILED','SKIPPED')},scorecard_counts=reconstructed['counts'],registered_family=[asdict(c) for c in VARIANTS],diagnostic_rankings=reconstructed['diagnostic_rankings'],shortlist=[],frame_pins={p:_sha(raw) for p,raw in sorted(frames.items())},gates={k:'UNVERIFIED' for k in ('per_fold_source_execution_audits','native_authorship','native_resource_authenticity','current_seal_authority','clean_locked_campaign_reruns','frozen_shortlist','financial_qualification')},limitations=['HASHES_DO_NOT_AUTHENTICATE_AUTHOR','SYNTHETIC_PARTIAL_WINDOWS','CONSISTENCY_PASS_IS_NOT_FULL_CAMPAIGN_AUDIT'])
        raw=canonical(report);_check(len(raw)<=16*MIB);return CampaignAudit(raw,_sha(raw))
    except (ValueError,TypeError,KeyError,AttributeError,IndexError,OverflowError,DecimalException,RecursionError) as exc:
        if isinstance(exc,DataError):raise
        raise DataError('AUDIT_CAMPAIGN_INVALID') from None
