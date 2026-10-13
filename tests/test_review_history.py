"""Adjacent ledger semantics, without granting authority to fixture JSON."""
import copy
import pytest
from compertum.data.errors import DataError
from compertum.review_runs import ReviewRuns


def pair(reason,code,timed_out,status):
    before={'state':'RUNNING','updated_at':'2026-10-10T12:00:00+00:00','last_transition':'EXIT_RECORDED',
        'attempts':[{'status':'RUNNING','reason':None,'job_receipt':{'exit_code':code,'timed_out':timed_out}}]}
    after=copy.deepcopy(before);after.update(state=status,last_transition='INTERRUPTED',updated_at='2026-10-10T12:00:01+00:00');after['attempts'][-1].update(status=status,reason=reason)
    return before,after


@pytest.mark.parametrize('reason,code,timed_out',[('REVIEW_REJECTED',6,False),('WORKER_FAILED',6,False),('JOB_TIMEOUT',0,False)])
def test_rehashed_original_rejection_cannot_gain_retry(reason,code,timed_out):
    before,after=pair(reason,code,timed_out,'INTERRUPTED')
    with pytest.raises(DataError):ReviewRuns._transition(before,after)


@pytest.mark.parametrize('reason,code,timed_out,status',[('REVIEW_REJECTED',6,False,'BLOCKED'),('WORKER_FAILED',5,False,'INTERRUPTED'),('JOB_TIMEOUT',124,True,'INTERRUPTED')])
def test_actual_worker_classification_has_its_documented_transition(reason,code,timed_out,status):
    before,after=pair(reason,code,timed_out,status);ReviewRuns._transition(before,after)


@pytest.mark.parametrize('reason',['OPERATOR_PAUSE','PAUSE_BOOKKEEPING_FAILURE','REVIEW_ACCEPTANCE_FAILED','LAUNCH_FAILED'])
def test_other_reason_cannot_hide_recorded_integrity_failure(reason):
    before,after=pair(reason,6,False,'INTERRUPTED')
    with pytest.raises(DataError):ReviewRuns._transition(before,after)


def test_owner_restart_cannot_hide_recorded_integrity_failure():
    before,after=pair('OWNER_RESTART',6,False,'INTERRUPTED');after['last_transition']='OWNER_RESTART'
    with pytest.raises(DataError):ReviewRuns._transition(before,after)
    after['state']='BLOCKED';after['attempts'][-1]['status']='BLOCKED'
    ReviewRuns._transition(before,after)


@pytest.mark.parametrize('reason',['REVIEW_ACCEPTANCE_FAILED','LAUNCH_FAILED','PAUSE_BOOKKEEPING_FAILURE'])
def test_owner_integrity_failure_cause_does_not_grant_retry(reason):
    before,after=pair(reason,0,False,'INTERRUPTED')
    if reason=='LAUNCH_FAILED':before['attempts'][-1]['job_receipt']=after['attempts'][-1]['job_receipt']=None
    with pytest.raises(DataError):ReviewRuns._transition(before,after)
    after['state']='BLOCKED';after['attempts'][-1]['status']='BLOCKED';ReviewRuns._transition(before,after)
