"""Pure state-transition consistency fixtures carry no native authority."""
import copy
import pytest
from compertum.audit_history import transition
from compertum.data.errors import DataError


def pair(code=6,state='INTERRUPTED',reason='WORKER_FAILED'):
    before={'state':'RUNNING','updated_at':'2026-10-10T12:00:00+00:00','last_transition':'EXIT_RECORDED','request_sha256':'a'*64,
        'attempts':[{'status':'RUNNING','job_receipt':{'exit_code':code,'timed_out':False}}]}
    after=copy.deepcopy(before);after.update(state=state,last_transition=state,updated_at='2026-10-10T12:00:01+00:00');after['attempts'][-1].update(status=state,reason=reason)
    return before,after


@pytest.mark.parametrize('code,state',[(4,'FAILED'),(6,'BLOCKED')])
def test_recorded_rejection_survives_bookkeeping_failure(code,state):
    before,after=pair(code,state);transition(before,after)
    after.update(state='INTERRUPTED',last_transition='INTERRUPTED');after['attempts'][-1]['status']='INTERRUPTED'
    with pytest.raises(DataError):transition(before,after)


@pytest.mark.parametrize('case',['erase','change_request','reset_terminal','rewrite_receipt'])
def test_append_only_transition_refuses_rehashed_history_edits(case):
    before,after=pair(5)
    if case=='erase':after['attempts']=[]
    elif case=='change_request':after['request_sha256']='b'*64
    elif case=='reset_terminal':before['state']='FAILED'
    else:after['attempts'][-1]['job_receipt']['exit_code']=0
    with pytest.raises(DataError):transition(before,after)


@pytest.mark.parametrize('code,state,reason',[(4,'FAILED','AUDIT_REJECTED'),(6,'BLOCKED','AUDIT_INTEGRITY_FAILURE'),(0,'INTERRUPTED','OWNER_RESTART')])
def test_restart_preserves_result_and_incomplete_success_is_not_adopted(code,state,reason):
    before,after=pair(code,state,reason);after['last_transition']='OWNER_RESTART';transition(before,after)


@pytest.mark.parametrize('reason',['AUDIT_INTEGRITY_FAILURE','LAUNCH_FAILED','PAUSE_BOOKKEEPING_FAILURE'])
def test_owner_integrity_failures_cannot_be_rewritten_as_retry(reason):
    before,after=pair(0,'INTERRUPTED',reason)
    if reason=='LAUNCH_FAILED':
        del before['attempts'][-1]['job_receipt'];del after['attempts'][-1]['job_receipt']
    with pytest.raises(DataError):transition(before,after)
    after.update(state='BLOCKED',last_transition='BLOCKED');after['attempts'][-1]['status']='BLOCKED';transition(before,after)
