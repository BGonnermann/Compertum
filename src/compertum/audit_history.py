"""Bounded unit-audit history consistency; JSON alone is not native authority."""
from copy import deepcopy
from datetime import datetime
import hashlib,json,re
from uuid import UUID
from .data.encoding import canonical
from .data.errors import DataError
from .review_evidence import successful_receipt
from .runtime.job_identity import validate_execution_identity,same_process


def _check(condition,code='AUDITOR_HISTORY_CORRUPT'):
    if not condition:raise DataError(code)


def _hash(v):return hashlib.sha256(canonical(v)).hexdigest()
def _uuid(v):_check(type(v) is str and str(UUID(v))==v)
def successful_exit(r):return successful_receipt(r,r['execution_identity'])


def receipt_terminal(receipt):
    if receipt is not None and not receipt['timed_out'] and receipt['exit_code'] not in (0,5,125):
        return 'FAILED' if receipt['exit_code']==4 else 'BLOCKED'
    return None


def validate_receipt(r):successful_receipt(r,r['execution_identity'])


def validate_state(s):
    _check(set(s)=={'task_id','request','request_sha256','state','owner','attempts','artifact','audit_sha256','financial_accepted','last_transition','updated_at'})
    _uuid(s['task_id']);_check(_hash(s['request'])==s['request_sha256'] and s['financial_accepted'] is False and len(s['attempts'])<=2)
    _check(type(s['attempts']) is list and type(s['owner']) is str and 0<len(s['owner'])<=256)
    _check(type(s['last_transition']) is str and re.fullmatch('[A-Z][A-Z0-9_]{0,95}',s['last_transition']) is not None);datetime.fromisoformat(s['updated_at'])
    _check(s['state'] in ('READY','RUNNING','INTERRUPTED','BLOCKED','FAILED','COMPLETED'))
    for n,a in enumerate(s['attempts'],1):
        required={'number','status','output_path','reservation_id','task','native_execution'}
        _check(type(a) is dict and required<=set(a)<=required|{'job_receipt','reason'})
        if 'reason' in a:_check(type(a['reason']) is str and re.fullmatch('[A-Z][A-Z0-9_]{0,95}',a['reason']) is not None)
        _check(type(a['number']) is int and a['number']==n and a['output_path']==f"artifacts/runs/{s['task_id']}/audit/attempt-{n}.json" and a['status'] in ('RUNNING','INTERRUPTED','BLOCKED','FAILED','COMPLETED'))
        native=a['native_execution'];validate_execution_identity(native)
        _check(native['task_id']==s['task_id'] and native['role']=='experiment_auditor' and native['task_sha256']==_hash(a['task'])
            and native['code_sha256']==s['request']['identity']['package_sha256'] and native['lock_sha256']==s['request']['identity']['lock_sha256'])
        _check(not same_process(native,s['request']['author_execution']) and (s['request']['fit_execution'] is None or not same_process(native,s['request']['fit_execution'])))
        if 'job_receipt' in a:
            validate_receipt(a['job_receipt']);_check(a['job_receipt'].get('execution_identity')==native)
        if a['status']=='COMPLETED':_check('job_receipt' in a and successful_exit(a['job_receipt']))
    if s['state']=='RUNNING':_check(s['attempts'] and s['attempts'][-1]['status']=='RUNNING')
    if s['state']=='COMPLETED':_check(s['attempts'] and s['attempts'][-1]['status']=='COMPLETED' and s['artifact'] is not None and s['audit_sha256'] is not None)
    else:_check(s['artifact'] is None and s['audit_sha256'] is None)


def transition(before,after):
    reason=after['last_transition']
    if before is None:
        _check(reason=='REGISTERED' and after['state']=='READY' and after['attempts']==[] and after['artifact'] is None and after['audit_sha256'] is None);return
    _check(type(after['attempts']) is list and len(after['attempts'])>=len(before['attempts']))
    _check(datetime.fromisoformat(after['updated_at'])>=datetime.fromisoformat(before['updated_at']))
    expected=deepcopy(before);expected.update(updated_at=after['updated_at'],last_transition=reason)
    if reason=='ATTEMPT_STARTED':
        _check(before['state']=='READY' and len(before['attempts'])<2 and len(after['attempts'])==len(before['attempts'])+1)
        a=after['attempts'][-1];_check(a['status']=='RUNNING' and 'job_receipt' not in a and 'reason' not in a)
        expected['attempts'].append(a);expected.update(state='RUNNING',owner=after['owner'])
    elif reason=='EXIT_RECORDED':
        _check(before['state']=='RUNNING' and 'job_receipt' not in before['attempts'][-1] and 'job_receipt' in after['attempts'][-1])
        expected['attempts'][-1]['job_receipt']=after['attempts'][-1]['job_receipt']
    elif reason in ('INTERRUPTED','BLOCKED','FAILED'):
        _check(before['state']=='RUNNING' and after['state']==reason)
        cause=after['attempts'][-1].get('reason');r=before['attempts'][-1].get('job_receipt');terminal=receipt_terminal(r)
        _check(cause in ('LAUNCH_FAILED','JOB_TIMEOUT','WORKER_FAILED','AUDIT_REJECTED','AUDIT_INTEGRITY_FAILURE','OPERATOR_PAUSE','PAUSE_BOOKKEEPING_FAILURE','PAUSE_IO_FAILURE'))
        if terminal:_check(after['state']==terminal)
        if cause in ('AUDIT_INTEGRITY_FAILURE','LAUNCH_FAILED','PAUSE_BOOKKEEPING_FAILURE'):_check(after['state']==(terminal or 'BLOCKED'))
        if reason=='INTERRUPTED':_check(len(before['attempts'])<2)
        if reason=='FAILED':_check(len(before['attempts'])==2 or terminal=='FAILED')
        if cause=='AUDIT_REJECTED':_check(terminal=='FAILED')
        if cause=='LAUNCH_FAILED':_check(r is None)
        if cause=='JOB_TIMEOUT':_check(r is not None and r['timed_out'])
        if cause=='OPERATOR_PAUSE':_check(r is not None and not r['timed_out'] and r['exit_code'] in (0,125))
        expected['state']=reason;expected['attempts'][-1].update(status=reason,reason=cause)
    elif reason=='OWNER_RESTART':
        _check(before['state']=='RUNNING');terminal=receipt_terminal(before['attempts'][-1].get('job_receipt'));exhausted=len(before['attempts'])==2
        expected['state']=terminal or ('FAILED' if exhausted else 'INTERRUPTED')
        cause=('AUDIT_REJECTED' if terminal=='FAILED' else 'AUDIT_INTEGRITY_FAILURE') if terminal else ('TRANSIENT_ATTEMPTS_EXHAUSTED' if exhausted else 'OWNER_RESTART')
        expected['attempts'][-1].update(status=expected['state'],reason=cause)
    elif reason=='RESUMED':
        _check(before['state']=='INTERRUPTED' and 0<len(before['attempts'])<2);expected['state']='READY'
    elif reason=='COMPLETED':
        _check(before['state']=='RUNNING' and successful_exit(before['attempts'][-1]['job_receipt']))
        expected['attempts'][-1]['status']='COMPLETED';expected.update(state='COMPLETED',artifact=after['artifact'],audit_sha256=after['audit_sha256'])
    else:raise DataError('AUDITOR_HISTORY_TRANSITION_INVALID')
    _check(canonical(after)==canonical(expected))


def reconstruct(final_state,records):
    _check(type(final_state) is bytes and 0<len(final_state)<=32*1024 and type(records) is list and 0<len(records)<=32)
    before=None;previous=None
    for expected,r in enumerate(records,1):
        _check(type(r) is dict and set(r)=={'seq','body','sha256','previous_sha256'})
        raw=r['body'].encode();_check(type(r['seq']) is int and r['seq']==expected and 0<len(raw)<=32*1024 and r['previous_sha256']==previous and hashlib.sha256(raw).hexdigest()==r['sha256'])
        current=json.loads(raw);_check(canonical(current)==raw);validate_state(current);transition(before,current);before=current;previous=r['sha256']
    _check(canonical(before)==final_state)
    return before
