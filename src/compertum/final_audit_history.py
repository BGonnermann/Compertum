"""Bounded consumed-Final audit history. Records never substitute for native proof."""
from copy import deepcopy
from datetime import datetime,timedelta
import json
from .data.encoding import canonical
from .data.errors import DataError
from .evaluation_protocol import identifier,digest,identity
from .final_audit_request import artifact
from .review_evidence import sha,successful_receipt
from .runtime.auditor_environment import validate_expected
from .runtime.job_identity import validate_execution_identity

MAXIMUM=24*1024
FIELDS=set('schema task_id seal_id evaluation_id original_sha256 manifest auditor_environment auditor_runtime owner state attempts artifact audit_sha256 financial_accepted full_M3 updated_at last_transition'.split())
ATTEMPT_FIELDS=set('number status request_artifact task_artifact reservation_id output_path native_execution job_receipt exit_observation closed_unbound started_at reason'.split())
STATES={'READY','PREPARED','RUNNING','EXIT_UNVERIFIED','INTERRUPTED','BLOCKED','FAILED','STOPPED','COMPLETED'}
CAUSES={'JOB_TIMEOUT','WORKER_IO_FAILURE','OPERATOR_PAUSE','OPERATOR_STOP','AUDIT_REJECTED','AUDIT_INTEGRITY_FAILURE','LAUNCH_FAILED','OWNER_RESTART','PUBLICATION_FAILED','BOOKKEEPING_FAILED'}


def check(ok):
    if not ok:raise DataError('FINAL_AUDIT_HISTORY_INVALID')


def _time(v):
    check(type(v) is str);d=datetime.fromisoformat(v);check(d.tzinfo is not None and d.utcoffset()==timedelta(0));return d


def closed_receipt(receipt,native):
    """Validate an authoritative receipt's shape and closed process set, not success."""
    successful_receipt(receipt,native)
    check(receipt['active_processes']==0 and receipt['observed_children_exited'] is True and receipt['assigned_before_resume'] is True and receipt['memory_limit']==4*1024**3 and receipt['observed_child_pids']==[])
    return receipt


def validate_unbound(proof,task,attempt):
    check(type(proof) is dict and set(proof)==set('schema task_id number reservation_id child_created pid assigned process_exit_observed job_active_processes result_usable retry_allowed'.split()))
    check(proof['schema']=='closed-unbound-final-audit-v1' and proof['task_id']==task and type(proof['number']) is int and proof['number']==attempt['number'] and proof['reservation_id']==attempt['reservation_id'])
    check(all(type(proof[k]) is bool for k in ('child_created','assigned','process_exit_observed','result_usable','retry_allowed')))
    check(type(proof['job_active_processes']) is int and proof['job_active_processes']==0 and not proof['result_usable'] and not proof['retry_allowed'])
    if proof['child_created']:check(type(proof['pid']) is int and proof['pid']>0 and proof['process_exit_observed'])
    else:check(proof['pid'] is None and not proof['assigned'] and not proof['process_exit_observed'])
    return proof


def validate_state(s):
    try:
        check(type(s) is dict and set(s)==FIELDS and len(canonical(s))<=MAXIMUM and s['schema']=='consumed-final-audit-state-v1')
        for k in ('task_id','seal_id','evaluation_id','owner'):identifier(s[k])
        check(s['task_id']!=s['evaluation_id']);digest(s['original_sha256']);identity(s['auditor_runtime'])
        check(s['financial_accepted'] is False and s['full_M3'] is False and s['state'] in STATES)
        check(type(s['last_transition']) is str and len(s['last_transition'])<=32);_time(s['updated_at'])
        a=artifact(s['manifest'],4*1024**2);check(a['task_id']==s['task_id'] and a['path']==f"artifacts/runs/{s['task_id']}/final_audit/input/environment.json")
        expected=validate_expected(s['auditor_environment']);check(expected['task_id']==s['task_id'] and expected['manifest_sha256']==a['sha256'])
        check(type(s['attempts']) is list and len(s['attempts'])<=2)
        for n,a in enumerate(s['attempts'],1):
            check(type(a) is dict and set(a)==ATTEMPT_FIELDS and type(a['number']) is int and a['number']==n and a['status'] in STATES-{'READY'})
            _time(a['started_at']);identifier(a['reservation_id']);check(a['output_path']==f"artifacts/runs/{s['task_id']}/final_audit/attempt-{n:02}.audit")
            for field,stem,bound in [('request_artifact','attempt-',65536),('task_artifact','task-attempt-',65536)]:
                item=artifact(a[field],bound);check(item['task_id']==s['task_id'] and item['path']==f"artifacts/runs/{s['task_id']}/final_audit/input/{stem}{n:02}.json")
            native=a['native_execution'];receipt=a['job_receipt'];check(a['reason'] is None or a['reason'] in CAUSES)
            if native is not None:
                validate_execution_identity(native)
                check(native['schema']=='native-template-final-auditor-v1' and native['task_id']==s['task_id'] and native['role']=='experiment_auditor' and native['task_sha256']==a['task_artifact']['sha256'])
                check(native['code_sha256']==s['auditor_runtime']['package_sha256'] and native['lock_sha256']==s['auditor_runtime']['lock_sha256'] and native['auditor_environment']==expected)
            if receipt is not None:check(native is not None);closed_receipt(receipt,native)
            if a['exit_observation'] is not None:
                from .final_attempts import validate_process_exit
                check(native is not None and receipt is None and a['status']=='BLOCKED');validate_process_exit(a['exit_observation'],native,a['started_at'],s['updated_at'])
            if a['closed_unbound'] is not None:
                check(native is None and receipt is None and a['exit_observation'] is None and a['status']=='BLOCKED' and a['reason']=='LAUNCH_FAILED')
                validate_unbound(a['closed_unbound'],s['task_id'],a)
            if a['status']=='PREPARED':check(native is None and receipt is None and a['exit_observation'] is None)
            if a['status']=='RUNNING':check(native is not None)
            if a['status']=='EXIT_UNVERIFIED':check(receipt is None)
            if a['status'] in ('INTERRUPTED','FAILED','COMPLETED','STOPPED'):check(receipt is not None)
            if a['status']=='COMPLETED':check(successful_receipt(receipt,native))
            if n<len(s['attempts']):check(a['status']=='INTERRUPTED' and receipt is not None)
        if s['state']=='READY':check(not s['attempts'] or (len(s['attempts'])==1 and s['attempts'][-1]['status']=='INTERRUPTED'))
        elif s['state']=='STOPPED' and not s['attempts']:pass
        else:check(s['attempts'] and s['attempts'][-1]['status']==s['state'])
        if s['state']=='COMPLETED':
            a=artifact(s['artifact'],2*1024**2);check(a['task_id']==s['task_id'] and a['path']==s['attempts'][-1]['output_path']);digest(s['audit_sha256'])
        else:check(s['artifact'] is None and s['audit_sha256'] is None)
        return s
    except (ValueError,TypeError,KeyError,AttributeError,OverflowError,RecursionError):raise DataError('FINAL_AUDIT_HISTORY_INVALID') from None


def transition(before,after):
    validate_state(after);reason=after['last_transition']
    if before is None:
        check(reason=='REGISTERED' and after['state']=='READY' and after['attempts']==[]);return
    validate_state(before);check(_time(after['updated_at'])>=_time(before['updated_at']))
    e=deepcopy(before);e.update(updated_at=after['updated_at'],last_transition=reason)
    if reason=='PREPARED':
        check(before['state']=='READY' and len(before['attempts'])<2 and len(after['attempts'])==len(before['attempts'])+1)
        a=after['attempts'][-1];check(a['status']=='PREPARED' and a['reason'] is None)
        e['attempts'].append(a);e.update(state='PREPARED',owner=after['owner'])
    elif reason=='NATIVE_BOUND':
        check(before['state']=='PREPARED' and after['attempts'][-1]['native_execution'] is not None)
        e['attempts'][-1].update(status='RUNNING',native_execution=after['attempts'][-1]['native_execution']);e['state']='RUNNING'
    elif reason in ('EXIT_UNVERIFIED','OWNER_RESTART'):
        check(before['state'] in ('PREPARED','RUNNING') and before['attempts'][-1]['job_receipt'] is None)
        check(after['attempts'][-1]['reason'] in CAUSES)
        if reason=='OWNER_RESTART':check(after['attempts'][-1]['reason']=='OWNER_RESTART')
        e['attempts'][-1].update(status='EXIT_UNVERIFIED',reason=after['attempts'][-1]['reason']);e['state']='EXIT_UNVERIFIED'
    elif reason=='EXIT_RECORDED':
        check(before['state'] in ('RUNNING','EXIT_UNVERIFIED') and before['attempts'][-1]['native_execution'] is not None and before['attempts'][-1]['job_receipt'] is None)
        receipt=after['attempts'][-1]['job_receipt'];check(receipt is not None)
        e['attempts'][-1].update(status='RUNNING',job_receipt=receipt,reason=None);e['state']='RUNNING'
    elif reason in ('INTERRUPTED','BLOCKED','FAILED','STOPPED'):
        check(before['state'] in ('PREPARED','RUNNING'));a=before['attempts'][-1];r=a['job_receipt'];cause=after['attempts'][-1]['reason'];check(cause in CAUSES)
        if r is None:check(reason=='BLOCKED' and before['state']=='PREPARED' and cause=='LAUNCH_FAILED')
        else:
            closed_receipt(r,a['native_execution'])
            terminal=not r['timed_out'] and r['exit_code'] not in (0,5,125)
            if terminal:check(reason==('FAILED' if r['exit_code']==4 else 'BLOCKED'))
            if reason=='INTERRUPTED':check(not terminal and len(before['attempts'])<2 and cause in ('JOB_TIMEOUT','WORKER_IO_FAILURE','OPERATOR_PAUSE','OWNER_RESTART'))
            if reason=='FAILED':check(r['exit_code']==4 or len(before['attempts'])==2)
            if reason=='STOPPED':check(cause=='OPERATOR_STOP' and not terminal)
            if cause=='JOB_TIMEOUT':check(r['timed_out'])
            if cause=='WORKER_IO_FAILURE':check(r['exit_code']==5 and not r['timed_out'])
            if cause=='OPERATOR_PAUSE':check(not r['timed_out'] and r['exit_code'] in (0,125))
            if cause=='AUDIT_REJECTED':check(not r['timed_out'] and r['exit_code']==4)
        e['attempts'][-1].update(status=reason,reason=cause);e['state']=reason
    elif reason=='UNBOUND_CLOSED':
        check(before['state'] in ('PREPARED','EXIT_UNVERIFIED') and before['attempts'][-1]['native_execution'] is None and before['attempts'][-1]['closed_unbound'] is None)
        proof=after['attempts'][-1]['closed_unbound'];check(proof is not None);validate_unbound(proof,before['task_id'],before['attempts'][-1])
        e['attempts'][-1].update(status='BLOCKED',reason='LAUNCH_FAILED',closed_unbound=proof);e['state']='BLOCKED'
    elif reason=='EXIT_OBSERVED':
        check(before['state']=='EXIT_UNVERIFIED' and before['attempts'][-1]['native_execution'] is not None and before['attempts'][-1]['job_receipt'] is None)
        check(after['attempts'][-1]['exit_observation'] is not None)
        e['attempts'][-1].update(status='BLOCKED',exit_observation=after['attempts'][-1]['exit_observation']);e['state']='BLOCKED'
    elif reason=='RESUMED':
        check(before['state']=='INTERRUPTED' and len(before['attempts'])==1);e['state']='READY';e['owner']=after['owner']
    elif reason=='CANCELLED':
        check(before['state'] in ('READY','INTERRUPTED') and len(before['attempts'])<=1)
        if e['attempts']:
            check(e['attempts'][-1]['status']=='INTERRUPTED' and e['attempts'][-1]['job_receipt'] is not None)
            e['attempts'][-1].update(status='STOPPED',reason='OPERATOR_STOP')
        e.update(state='STOPPED',owner=after['owner'])
    elif reason=='COMPLETED':
        check(before['state']=='RUNNING' and successful_receipt(before['attempts'][-1]['job_receipt'],before['attempts'][-1]['native_execution']))
        e['attempts'][-1].update(status='COMPLETED',reason=None);e.update(state='COMPLETED',artifact=after['artifact'],audit_sha256=after['audit_sha256'])
    else:raise DataError('FINAL_AUDIT_HISTORY_INVALID')
    check(canonical(e)==canonical(after))


def reconstruct(raw,records):
    check(type(raw) is bytes and 0<len(raw)<=MAXIMUM and type(records) is list and 0<len(records)<=32)
    before=None;previous=None
    for index,row in enumerate(records,1):
        check(type(row) is dict and set(row)=={'seq','body','sha256','previous_sha256'} and type(row['seq']) is int and row['seq']==index and type(row['body']) is str)
        body=row['body'].encode();check(0<len(body)<=MAXIMUM and row['previous_sha256']==previous and sha(body)==row['sha256'])
        value=json.loads(body);check(canonical(value)==body);transition(before,value);before=value;previous=row['sha256']
    check(canonical(before)==raw);return before
