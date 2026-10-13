"""Simulated Win32 cleanup failures; no native acceptance is inferred."""
from types import SimpleNamespace
from uuid import uuid4
import pytest
from compertum.runtime import audit_job_lifetime as m
from compertum.runtime.errors import RuntimeRefused
from compertum.runtime import jobs


class API:
    def __init__(self):self.alive=False;self.active_count=0;self.wait_failure=False;self.terminate_failure=False;self.close_failure=None;self.closed=[]
    def checked(self,ok,operation):
        if not ok:raise RuntimeRefused(operation)
        return ok
    def WaitForSingleObject(self,h,ms):return 258 if self.wait_failure or self.alive else 0
    def TerminateProcess(self,h,code):
        if self.terminate_failure:return False
        self.alive=False;return True
    def TerminateJobObject(self,h,code):self.active_count=0;return True
    def active(self,h):return self.active_count
    def CloseHandle(self,h):
        if h==self.close_failure:return False
        self.closed.append(h);return True


@pytest.fixture
def pending():
    api=API();lease=SimpleNamespace(project_id=str(uuid4()));prepared=dict(task_id=str(uuid4()),number=1,reservation_id=str(uuid4()))
    job=SimpleNamespace(api=api,lease=lease,process=None,pid=None,job=m.OwnedHandle(api,10),children={},closed=False,monitor_error=False,budget_calls=0)
    def monitor():
        if job.monitor_error:raise RuntimeRefused('JOB_MONITOR_UNVERIFIED')
    def budget():job.budget_calls+=1
    job._stop_monitor=monitor;job._finish_budget=budget
    writer=SimpleNamespace(closed=False);m.enable(job,prepared,writer);jobs._ACTIVE[lease.project_id]=job
    yield job
    jobs._ACTIVE.pop(lease.project_id,None)


def child(job):
    m.adopt_child(job,SimpleNamespace(process=11,thread=12,pid=123));job.api.alive=True


def test_precreation_closure_has_no_result_or_retry_authority(pending):
    j=pending;m.close(j);proof=m.closed_unbound(j)
    assert j.closed and j.budget_calls==1 and proof['child_created'] is False and proof['pid'] is None
    assert not proof['result_usable'] and not proof['retry_allowed'] and not j.audit_lifetime.writer.closed


def test_created_unassigned_child_is_terminated_before_handle_disposal(pending):
    j=pending;child(j);m.close(j);proof=m.closed_unbound(j)
    assert j.api.closed==[12,11,10] and proof['process_exit_observed'] and not proof['assigned']
    assert j.lease.project_id not in jobs._ACTIVE


@pytest.mark.parametrize('failure',['terminate','wait','monitor'])
def test_uncertain_exit_retains_every_handle_writer_and_slot(pending,failure):
    j=pending;child(j)
    if failure=='terminate':j.api.terminate_failure=True
    elif failure=='wait':j.api.wait_failure=True
    else:j.monitor_error=True
    with pytest.raises(RuntimeRefused):m.close(j)
    assert not j.closed and j.api.closed==[] and not j.audit_lifetime.writer.closed and jobs._ACTIVE[j.lease.project_id] is j and j.budget_calls==0
    j.api.terminate_failure=False;j.api.wait_failure=False;j.monitor_error=False
    m.close(j);assert j.closed and j.budget_calls==1


def test_close_handle_failure_never_blindly_retries_numeric_handle(pending):
    j=pending;child(j);j.api.close_failure=11
    with pytest.raises(RuntimeRefused):m.close(j)
    assert j.audit_lifetime.exit_verified and j.audit_lifetime.cleanup_uncertain and not j.closed and jobs._ACTIVE[j.lease.project_id] is j
    j.api.close_failure=None
    with pytest.raises(RuntimeRefused):m.close(j)
    assert j.api.closed==[12] and j.budget_calls==0


@pytest.mark.parametrize('flag',['durably_bound','resume_attempted'])
def test_bound_or_resumed_launch_cannot_use_unbound_disposition(pending,flag):
    j=pending;child(j);setattr(j.audit_lifetime,flag,True);m.close(j)
    with pytest.raises(RuntimeRefused):m.closed_unbound(j)


def test_shared_slot_releases_only_after_budget_settlement(pending):
    j=pending;child(j)
    def fail():raise OSError('simulated ledger failure')
    j._finish_budget=fail
    with pytest.raises(OSError):m.close(j)
    assert not j.closed and jobs._ACTIVE[j.lease.project_id] is j and not j.audit_lifetime.writer.closed
    j._finish_budget=lambda:None;m.close(j);assert j.closed


@pytest.mark.parametrize('phase',['exit_verified','closed','cleanup_uncertain'])
def test_child_cannot_be_added_after_closure_or_uncertainty(pending,phase):
    j=pending
    if phase=='exit_verified':m.prove_exit(j)
    elif phase=='closed':m.close(j)
    else:j.audit_lifetime.cleanup_uncertain=True
    slot_before=jobs._ACTIVE.get(j.lease.project_id);closed_before=list(j.api.closed)
    with pytest.raises(RuntimeRefused):m.adopt_child(j,SimpleNamespace(process=11,thread=12,pid=123))
    assert j.process is None and j.pid is None and not j.audit_lifetime.child_created
    assert j.api.closed==closed_before and jobs._ACTIVE.get(j.lease.project_id) is slot_before
    if phase!='closed':
        with pytest.raises(RuntimeRefused):m.closed_unbound(j)
    else:assert m.closed_unbound(j)['child_created'] is False


def test_already_closed_job_cannot_enable_auditor_lifetime(pending):
    j=pending;j.closed=True;del j.audit_lifetime
    with pytest.raises(RuntimeRefused):m.enable(j,{},object())
