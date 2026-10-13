"""Simulated orchestration with real artifact/history validation, not native Jobs."""
from types import SimpleNamespace
from uuid import uuid4
import pytest
from test_final_audit_runs import owner,saved,environment,native,receipt,report
from compertum import final_audit_controller as m
from compertum.runtime.audit_job_lifetime import AuditLaunch,AuditLaunchFailed
from compertum.runtime.errors import RuntimeRefused
from compertum.data.errors import DataError


@pytest.fixture
def controller(owner,monkeypatch):
    o=owner;monkeypatch.setattr(m,'FinalAuditRuns',lambda storage:o.runs)
    c=m.FinalAuditController(SimpleNamespace(status=lambda:dict(research_state='RUNNING'),require_health=lambda:None),o.storage)
    monkeypatch.setattr(m,'preflight_campaign',lambda lease:o.runs.barrier());monkeypatch.setattr(m,'job_slot_busy',lambda lease:False)
    monkeypatch.setattr(m,'adopt_fixture_bytes',lambda writer,job:writer.written)
    def prove(job):
        if job.fail_exit:raise RuntimeRefused('JOB_EXIT_UNVERIFIED')
        job.audit_lifetime.exit_verified=True;job.alive=False
    monkeypatch.setattr(m,'prove_exit',prove)
    def launch(lease,spec,argv,*,writer,final_audit_request,before_resume):
        p=final_audit_request;t=spec.to_payload();n=native(o,t);o.runs.bind_native(p,n);before_resume(n)
        job=SimpleNamespace(pid=321,closed=False,alive=False,fail_exit=False,fail_close=False,wait_failure=False,job=object(),audit_lifetime=SimpleNamespace(exit_verified=False,cleanup_uncertain=False),result=receipt(n))
        job.api=SimpleNamespace(active=lambda _:int(job.alive))
        def wait():
            if job.wait_failure:raise RuntimeRefused('JOB_EXIT_UNVERIFIED')
            return job.result
        def close():
            prove(job)
            if job.fail_close:raise RuntimeRefused('FINAL_AUDIT_CLEANUP_UNVERIFIED')
            job.closed=True
        job.wait=wait;job.close=close;writer.write(report(o,p,n));o.writers.append(writer);return job
    monkeypatch.setattr(m,'launch_bounded',launch)
    return o,c


def test_success_publishes_once_and_keeps_financial_gates_closed(controller,monkeypatch):
    o,c=controller;assert c.step(o.task)['state']=='RUNNING';job=c.active[-1];c.tick()
    assert c.active is None and job.closed and c.runs.completed(o.task)['financial_accepted'] is False
    monkeypatch.setattr(m,'launch_bounded',lambda *a,**kw:pytest.fail('redispatch'))
    assert c.step(o.task)['state']=='COMPLETED';assert c.recover(o.task)['state']=='COMPLETED'


@pytest.mark.parametrize('code,timed,status',[(4,False,'FAILED'),(6,False,'BLOCKED'),(5,False,'INTERRUPTED'),(124,True,'INTERRUPTED')])
def test_worker_failure_classification_preserves_exit_and_no_artifact(controller,code,timed,status):
    o,c=controller;c.step(o.task);p,w,j=c.active;j.result.update(exit_code=code,timed_out=timed);c.tick()
    s=c.runs.status(o.task);assert s['state']==status and s['artifact'] is None and s['attempts'][0]['job_receipt']==j.result and j.closed and w.closed


@pytest.mark.parametrize('terminal,status',[(False,'INTERRUPTED'),(True,'STOPPED')])
def test_operator_pause_or_stop_waits_before_disposal(controller,terminal,status):
    o,c=controller;c.step(o.task);p,w,j=c.active;j.alive=True;j.result['exit_code']=125;c.pause(terminal=terminal)
    assert c.runs.status(o.task)['state']==status and c.active is None and j.closed and w.closed


def test_unknown_exit_retains_writer_job_and_blocks_next_attempt(controller):
    o,c=controller;c.step(o.task);p,w,j=c.active;j.wait_failure=True;c.tick()
    assert c.active is not None and not j.closed and not w.closed and c.runs.status(o.task)['state']=='EXIT_UNVERIFIED'
    with pytest.raises(RuntimeRefused,match='JOB_SLOT_BUSY'):c.step(o.task)
    j.wait_failure=False;j.result['exit_code']=125;c.recover(o.task)
    assert c.active is None and c.runs.status(o.task)['state']=='INTERRUPTED'


def test_failed_handle_cleanup_retains_controller_until_recovered(controller):
    o,c=controller;c.step(o.task);p,w,j=c.active;j.fail_close=True;c.tick()
    assert c.active is not None and not j.closed and c.runs.status(o.task)['state']=='COMPLETED'
    j.fail_close=False;c.recover(o.task);assert c.active is None and j.closed


def test_precreation_launch_failure_is_closed_but_never_retryable(controller,monkeypatch):
    o,c=controller
    def fail(lease,spec,argv,*,writer,final_audit_request,**kwargs):raise AuditLaunchFailed(AuditLaunch(final_audit_request,writer))
    monkeypatch.setattr(m,'launch_bounded',fail)
    with pytest.raises(AuditLaunchFailed):c.step(o.task)
    s=c.runs.status(o.task);assert s['state']=='BLOCKED' and s['attempts'][0]['closed_unbound']['child_created'] is False
    c.runs.barrier();assert c.active is None


def test_bad_report_never_publishes(controller):
    o,c=controller;c.step(o.task);p,w,j=c.active;w.stream.seek(0);w.stream.write(b'bad');w.stream.flush();c.tick()
    assert c.runs.status(o.task)['state']=='BLOCKED' and not w.destination.exists() and c.active is None


def test_published_result_recovery_finishes_without_redispatch(controller,monkeypatch):
    o,c=controller;c.step(o.task);accept=c.runs.accept
    monkeypatch.setattr(c.runs,'accept',lambda *a:(_ for _ in ()).throw(OSError('simulated commit failure')))
    c.tick();assert c.active is None and c.runs.status(o.task)['state']=='RUNNING'
    monkeypatch.setattr(c.runs,'accept',accept);monkeypatch.setattr(m,'launch_bounded',lambda *a,**kw:pytest.fail('redispatch'))
    assert c.recover(o.task)['state']=='COMPLETED'


@pytest.mark.parametrize('payload',[{},None,{'operation':'launch','task_id':'x'},{'operation':'status','task_id':str(uuid4()),'raw':b'no'},{'operation':'register','task_id':str(uuid4()),'seal_id':str(uuid4()),'manifest':b'no'}])
def test_public_control_rejects_unknown_fields_and_raw_evidence(controller,payload):
    o,c=controller
    with pytest.raises((DataError,RuntimeRefused)):c.control(payload)
    assert c.runs.status(o.task)['state']=='READY'


def test_status_remains_compact_without_reading_heavy_evidence(controller,monkeypatch):
    o,c=controller;monkeypatch.setattr(c.runs,'current',lambda *a:pytest.fail('heavy read'))
    assert set(c.control(dict(operation='status',task_id=o.task)))==set('task_id seal_id evaluation_id state attempt_count reason artifact audit_sha256 financial_accepted full_M3'.split())


@pytest.mark.parametrize('refusal',['paused','health','busy'])
def test_refused_resume_preserves_interrupted_state(controller,monkeypatch,refusal):
    o,c=controller;c.step(o.task);c.active[-1].result['exit_code']=125;c.pause();before=c.runs.status(o.task)
    if refusal=='paused':c.coordinator.status=lambda:dict(research_state='PAUSED')
    elif refusal=='health':c.coordinator.require_health=lambda:(_ for _ in ()).throw(RuntimeRefused('HEALTH_NOT_READY'))
    else:monkeypatch.setattr(m,'job_slot_busy',lambda lease:True)
    with pytest.raises(RuntimeRefused):c.control(dict(operation='resume',task_id=o.task))
    assert c.runs.status(o.task)==before


@pytest.mark.parametrize('interrupted',[False,True])
def test_stop_idle_is_durable_and_prevents_later_dispatch(controller,interrupted):
    o,c=controller
    if interrupted:c.step(o.task);c.active[-1].result['exit_code']=125;c.pause()
    assert c.control(dict(operation='stop',task_id=o.task))['state']=='STOPPED'
    assert c.control(dict(operation='stop',task_id=o.task))['state']=='STOPPED'
    with pytest.raises((DataError,RuntimeRefused)):c.step(o.task)
    with pytest.raises((DataError,RuntimeRefused)):c.control(dict(operation='resume',task_id=o.task))


@pytest.mark.parametrize('code,timed,status',[(5,False,'STOPPED'),(124,True,'STOPPED'),(4,False,'FAILED'),(6,False,'BLOCKED')])
def test_stop_is_terminal_even_for_retryable_worker_failures(controller,code,timed,status):
    o,c=controller;c.step(o.task);c.active[-1].result.update(exit_code=code,timed_out=timed);c.pause(terminal=True)
    assert c.runs.status(o.task)['state']==status
    with pytest.raises((RuntimeRefused,DataError)):c.control(dict(operation='resume',task_id=o.task))


def test_checkpoint_refuses_unresolved_attempt_after_restart_before_reservation(controller):
    from compertum.runtime.supervisor import Supervisor
    from compertum.final_audit_runs import FinalAuditRuns
    from test_final_audit_runs import prepare
    o,c=controller;prepare(o);o.storage.lease.identity.process_instance_id=str(uuid4());restarted=FinalAuditRuns(o.storage)
    assert restarted.status(o.task)['state']=='EXIT_UNVERIFIED'
    reservations=o.db.execute('SELECT count(*) FROM reservations').fetchone()[0]
    supervisor=object.__new__(Supervisor);supervisor.halt=lambda reason:None;supervisor.store=o.storage.store;supervisor.coordinator_lease=o.storage.lease;supervisor.partial_fixture=True;supervisor.storage=o.storage
    with pytest.raises(RuntimeRefused):supervisor.checkpoint()
    assert o.db.execute('SELECT count(*) FROM reservations').fetchone()[0]==reservations
