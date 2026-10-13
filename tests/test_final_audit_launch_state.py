"""Simulated durable launch dispositions; no native acceptance is inferred."""
from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4
import pytest
from test_final_audit_runs import owner,saved,environment,prepare,bound
from compertum.final_audit_runs import require_closed_audits,FinalAuditRuns
from compertum.runtime.audit_job_lifetime import AuditLaunch,no_child_disposition
from compertum.data.errors import DataError


def proof(o,p):return no_child_disposition(AuditLaunch(p,None))


def test_closed_precreation_attempt_is_terminal_and_cannot_reset_budget(owner):
    o=owner;p,t,w=prepare(o);d=proof(o,p)
    with pytest.raises(DataError):o.runs.barrier()
    result=o.runs.record_unbound(p,d);assert result['state']=='BLOCKED'
    o.runs.barrier()
    for action in (lambda:o.runs.resume(o.task),lambda:prepare(o),lambda:o.runs.record_unbound(p,d)):
        with pytest.raises(DataError):action()
    o.storage.lease.identity.process_instance_id=str(uuid4())
    again=FinalAuditRuns(o.storage);assert again.status(o.task)['state']=='BLOCKED';again.barrier()


@pytest.mark.parametrize('change',[
    {'task_id':str(uuid4())},{'number':2},{'reservation_id':str(uuid4())},
    {'pid':17},{'assigned':True},{'process_exit_observed':True},{'job_active_processes':1},
    {'result_usable':True},{'retry_allowed':True},{'child_created':True},{'extra':0},
])
def test_unbound_disposition_rejects_malformed_or_foreign_proof(owner,change):
    o=owner;p,t,w=prepare(o);d=proof(o,p);d.update(change)
    with pytest.raises(DataError):o.runs.record_unbound(p,d)
    assert o.runs.status(o.task)['state']=='PREPARED'
    with pytest.raises(DataError):o.runs.barrier()


def test_created_unassigned_child_needs_exact_observed_exit(owner):
    o=owner;p,t,w=prepare(o);d=proof(o,p);d.update(child_created=True,pid=123,process_exit_observed=True)
    assert o.runs.record_unbound(p,d)['state']=='BLOCKED';o.runs.barrier()


def test_bound_worker_cannot_be_closed_as_unbound(owner):
    o=owner;p,t,w,n=bound(o)
    with pytest.raises(DataError):o.runs.record_unbound(p,proof(o,p))
    with pytest.raises(DataError):o.runs.barrier()


def test_only_exact_prepared_attempt_can_pass_launch_barrier(owner):
    o=owner;p,t,w=prepare(o);store=o.storage.store;who=o.storage.lease.identity.process_instance_id
    require_closed_audits(store,who,p)
    for candidate,caller in [(None,who),(dict(p,number=2),who),(dict(p,reservation_id=str(uuid4())),who),(p,str(uuid4()))]:
        with pytest.raises(DataError):require_closed_audits(store,caller,candidate)
    o.runs.uncertain(o.task,'LAUNCH_FAILED')
    with pytest.raises(DataError):require_closed_audits(store,who,p)


def test_restart_unknown_preparation_has_no_automatic_closure(owner):
    o=owner;prepare(o);o.storage.lease.identity.process_instance_id=str(uuid4());new=FinalAuditRuns(o.storage)
    assert new.status(o.task)['state']=='EXIT_UNVERIFIED'
    with pytest.raises(DataError):new.barrier()
    with pytest.raises(DataError):new.recover_exit(o.task)
