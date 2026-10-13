"""Strict final-attempt journal replay. Record validation grants no authority.

Native launch/exit and publication must be independently observed by owners.
This module never launches work, reads generated prices or decodes results.
"""
from copy import deepcopy
from datetime import datetime,timedelta
from uuid import UUID,uuid5
from .data.encoding import canonical
from .data.errors import DataError
from .evaluation_protocol import identifier,digest
from .runtime.job_identity import validate_execution_identity,same_process
from .review_evidence import successful_receipt

OPERATIONS=frozenset({'START_FINAL_BATCH','INTERRUPT_FINAL_BATCH','TERMINATE_FINAL_BATCH','ABANDON_FINAL_BATCH','ABANDON_FINAL_PREPARATION'})
COMMON={'operation','seal_id','created_at','owner_instance','owner_generation'}
ATTEMPT_FIELDS={'number','attempt_id','evaluation_id','checkpoint_id','plan_sha256','consumption_sha256','task_sha256','reservation_id','output_path','native_execution','charged_before_ms','started_at','deadline_at'}
BUDGET_MS=120000
# TaskSpec schedules whole seconds; subsecond credit cannot fund another attempt.
MINIMUM_ATTEMPT_MS=1000

def _check(ok):
    if not ok:raise DataError('FINAL_ATTEMPT_INVALID')

def _time(value):
    _check(type(value) is str and len(value)<=40)
    value=datetime.fromisoformat(value)
    _check(value.tzinfo is not None and value.utcoffset()==timedelta(0))
    return value

def _integer(value,low=0,high=2**53):
    _check(type(value) is int and low<=value<=high)
    return value

def remaining_slots(row):
    if row['status']!='SEALED' or not row.get('final') or row.get('final_complete') is not None:return 0
    return 4-sum(1+(a['close'] is not None) for a in row.get('final_attempts',[]))

def _publication(value,attempt):
    _check(type(value) is dict and set(value)=={'artifact','payload_sha256','payload_bytes'})
    a=value['artifact'];_check(type(a) is dict and set(a)=={'artifact_id','task_id','path','size_bytes','sha256'})
    identifier(a['artifact_id']);identifier(a['task_id']);digest(a['sha256']);digest(value['payload_sha256'])
    _check(a['task_id']==attempt['evaluation_id'] and a['path']==attempt['output_path'])
    _integer(a['size_bytes'],1,16*1024**2);_integer(value['payload_bytes'],1,a['size_bytes']-1)

def _start(row,record,*,preparation=False):
    _check(set(record)==COMMON|{'attempt'})
    a=record['attempt'];_check(type(a) is dict and set(a)==ATTEMPT_FIELDS)
    plan=row['final']['plan'];prior=row.get('final_attempts',[])
    from .final_recipe import recipe
    _check(canonical(plan['recipe'])==canonical(recipe(version=2)))
    _check(bool(plan['selected']) and row.get('final_complete') is None)
    _integer(a['number'],1,2);_check(a['number']==len(prior)+1)
    _check(not prior or prior[-1]['close'] is not None and prior[-1]['close']['outcome']=='INTERRUPTED')
    charged=prior[-1]['close']['charged_ms'] if prior else 0
    _integer(a['charged_before_ms']);_check(a['charged_before_ms']==charged<=BUDGET_MS-MINIMUM_ATTEMPT_MS)
    for name in ('evaluation_id','checkpoint_id'):_check(identifier(a[name])==plan[name])
    _check(identifier(a['attempt_id'])==str(uuid5(UUID(plan['evaluation_id']),f"synthetic-final-attempt-{a['number']}")))
    _check(digest(a['plan_sha256'])==row['final']['plan_sha256']);digest(a['consumption_sha256']);digest(a['task_sha256']);identifier(a['reservation_id'])
    _check(a['output_path']==f"artifacts/runs/{plan['evaluation_id']}/final/attempt-{a['number']:02}.final")
    start=_time(a['started_at']);deadline=_time(a['deadline_at']);created=_time(record['created_at'])
    _check(start<=created<deadline and timedelta(0)<deadline-start<=timedelta(milliseconds=BUDGET_MS-charged))
    if prior:
        old=prior[-1]['start']['attempt']
        _check(a['consumption_sha256']==old['consumption_sha256'] and a['reservation_id']!=old['reservation_id'])
        _check(start>=_time(prior[-1]['close']['created_at']))
    n=a['native_execution']
    if preparation and n is None:return dict(start=deepcopy(record),close=None)
    validate_execution_identity(n)
    _check(n['schema']=='native-template-execution-v3' and n['role']=='experiment_runner' and n['task_id']==plan['evaluation_id'] and n['task_sha256']==a['task_sha256'])
    _check(n['code_sha256']==plan['runtime']['package_sha256'] and n['lock_sha256']==plan['runtime']['lock_sha256'])
    ticket=row['freeze']['ticket'];member=ticket['pair']['source']
    _check(n['clean_environment']==dict(schema='expected-clean-campaign-v1',pair_sha256=ticket['pair_sha256'],manifest_sha256=member['manifest_sha256'],lane='source',run_id=member['run_id']))
    if prior:
        old=prior[-1]['start']['attempt']
        _check(a['consumption_sha256']==old['consumption_sha256'] and a['reservation_id']!=old['reservation_id'])
        _check(start>=_time(prior[-1]['close']['created_at']) and not same_process(n,old['native_execution']))
    return dict(start=deepcopy(record),close=None)

def _close(row,record):
    _check(set(record)==COMMON|{'attempt_id','outcome','charged_ms','job_receipt','publication'})
    prior=row.get('final_attempts',[]);_check(bool(prior) and prior[-1]['close'] is None and row.get('final_complete') is None)
    a=prior[-1]['start']['attempt'];_check(identifier(record['attempt_id'])==a['attempt_id'])
    charged=_integer(record['charged_ms']);closed=_time(record['created_at']);duration=closed-_time(a['started_at'])
    _check(closed>=_time(prior[-1]['start']['created_at']))
    elapsed=duration.days*86400000+duration.seconds*1000+(duration.microseconds+999)//1000
    _check(elapsed>=0 and charged>=a['charged_before_ms']+elapsed)
    receipt=record['job_receipt'];success=successful_receipt(receipt,a['native_execution'])
    _check(len(canonical(receipt))<=2048)
    _check(receipt['active_processes']==0 and receipt['assigned_before_resume'] and receipt['observed_children_exited'])
    _check(receipt['memory_limit']==4*1024**3 and 0<receipt['peak_job_memory']<=4*1024**3 and 0<receipt['affinity'].bit_count()<=4)
    children=receipt['observed_child_pids'];_check(len(children)==len(set(children)) and receipt['pid'] not in children)
    outcome=record['outcome'];_check(type(outcome) is str)
    if record['operation']=='INTERRUPT_FINAL_BATCH':
        _check(outcome=='INTERRUPTED' and a['number']==1 and charged<=BUDGET_MS-MINIMUM_ATTEMPT_MS and not receipt['timed_out'] and receipt['exit_code'] in (0,5,125))
    else:
        _check(outcome in {'COMPLETED','REJECTED','STOPPED','EXHAUSTED'})
        if outcome=='COMPLETED':_check(success and charged<=BUDGET_MS)
        elif outcome=='EXHAUSTED':_check(a['number']==2 or charged>BUDGET_MS-MINIMUM_ATTEMPT_MS)
    if outcome=='COMPLETED':_publication(record['publication'],a)
    else:_check(record['publication'] is None)
    return deepcopy(record)

def validate_process_exit(proof,native,started,closed):
    """Validate a retained observation; only the owner may obtain this proof."""
    _check(type(proof) is dict and set(proof)=={'schema','process','status','observed_at','observed_creation_filetime','wait_result'})
    _check(proof['schema']=='final-root-exit-v1' and canonical(proof['process'])==canonical(native['process']))
    _check(_time(started)<=_time(proof['observed_at'])<=_time(closed))
    status=proof['status'];creation=proof['observed_creation_filetime'];wait=proof['wait_result']
    if status=='VERIFIED_ABSENT':_check(creation is None and wait is None)
    else:
        _integer(creation,1,2**64-1);_integer(wait,0,258);_check(wait in (0,258))
        if status=='VERIFIED_PID_REUSED':_check(creation!=native['process']['creation_filetime'])
        else:_check(status=='VERIFIED_EXIT' and creation==native['process']['creation_filetime'] and wait==0)


def _abandon(row,record):
    _check(set(record)==COMMON|{'attempt_id','outcome','charged_ms','budget_basis','process_exit','publication'})
    prior=row.get('final_attempts',[]);_check(bool(prior) and prior[-1]['close'] is None and row.get('final_complete') is None)
    a=prior[-1]['start']['attempt'];_check(identifier(record['attempt_id'])==a['attempt_id'])
    _check(record['outcome']=='EXHAUSTED' and _integer(record['charged_ms'])==BUDGET_MS and record['budget_basis']=='UNKNOWN_EXIT_FORFEITS_TOTAL' and record['publication'] is None)
    validate_process_exit(record['process_exit'],a['native_execution'],prior[-1]['start']['created_at'],record['created_at'])
    return deepcopy(record)


def _abandon_preparation(row,record):
    _check(set(record)==COMMON|{'attempt','dispatch_sha256','process_exit','reason'} and record['reason']=='STATUS_UNCERTAIN')
    digest(record['dispatch_sha256']);a=record['attempt']
    candidate={k:record[k] for k in COMMON};candidate.update(operation='START_FINAL_BATCH',created_at=a['started_at'],attempt=a)
    _start(row,candidate,preparation=True)
    _check(_time(record['created_at'])>=_time(a['started_at']))
    if a['native_execution'] is None:_check(record['process_exit'] is None)
    else:validate_process_exit(record['process_exit'],a['native_execution'],a['started_at'],record['created_at'])


def replay_attempt(seals,seal_id,record,sequence):
    """Apply one validated event atomically to an already verified seal state."""
    try:
        _integer(sequence,1,256);_check(type(record) is dict and record.get('operation') in OPERATIONS)
        _check(record['seal_id']==identifier(seal_id));identifier(record['owner_instance']);_integer(record['owner_generation'],1);_time(record['created_at'])
        row=seals[seal_id];_check(row['status']=='SEALED' and row.get('final') is not None and row.get('final_complete') is None)
        prior=row.get('final_attempts',[])
        previous=(prior[-1]['close_sequence'] or prior[-1]['start_sequence']) if prior else row.get('final_sequence',0)
        _check(sequence>previous)
        pair=row['freeze']['ticket']['pair'];_check(pair['source']['seal_id']==seal_id and all(seals[pair[l]['seal_id']]['status']=='SEALED' for l in ('source','wheel')))
        if record['operation']=='ABANDON_FINAL_PREPARATION':
            _abandon_preparation(row,record)
            row.update(status='INVALIDATED',invalidation=deepcopy(record))
        elif record['operation']=='START_FINAL_BATCH':
            attempt=_start(row,record);attempt['start_sequence']=sequence;attempt['close_sequence']=None
            row.setdefault('final_attempts',[]).append(attempt)
        else:
            closed=_abandon(row,record) if record['operation']=='ABANDON_FINAL_BATCH' else _close(row,record)
            result=None
            if closed['operation'] in ('TERMINATE_FINAL_BATCH','ABANDON_FINAL_BATCH'):
                plan=row['final']['plan']
                result=dict(schema='synthetic-final-result-reference-v1',evaluation_id=plan['evaluation_id'],checkpoint_id=plan['checkpoint_id'],status=closed['outcome'],publication=closed['publication'],financial_accepted=False,full_M3=False)
            row['final_attempts'][-1].update(close=closed,close_sequence=sequence)
            if result is not None:
                import hashlib
                row.update(final_complete={**closed,'result':result,'result_sha256':hashlib.sha256(canonical(result)).hexdigest()},final_complete_sequence=sequence)
    except (ValueError,TypeError,KeyError,AttributeError,OverflowError,RecursionError):
        raise DataError('FINAL_ATTEMPT_INVALID') from None
