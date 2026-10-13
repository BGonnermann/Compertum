"""Cooperative campaign failure cleanup preserves evidence and detaches resources."""
from uuid import uuid4
import pytest
from test_persistence import owned
from test_saved_campaigns import setup,control
from test_campaign_job import controller_for
from compertum.runtime.errors import RuntimeRefused


def close_then_raise(target,monkeypatch):
    original=target.close
    def broken():
        original()
        raise OSError('injected_after_real_close')
    monkeypatch.setattr(target,'close',broken)


def test_cancelled_admission_cleanup_error_requires_restart(owned,monkeypatch):
    storage,runs,run,_=setup(owned);controller=controller_for(storage)
    controller.cooperative=True
    controller.control(run,str(uuid4()),'resume');proof=controller.pending.proof;controller.tick()
    close_then_raise(proof,monkeypatch)
    with pytest.raises(RuntimeRefused,match='CAMPAIGN_RECOVERY_REQUIRED'):controller.pause()
    assert controller.pending is None and controller.active is None and proof.closed
    assert controller.last_operation_error['recovery_required'] is True
    assert controller.runs.summary(run)['attempts']==[]
    controller.tick()
    with pytest.raises(RuntimeRefused,match='CAMPAIGN_RECOVERY_REQUIRED'):controller.step(run)
    with pytest.raises(RuntimeRefused,match='CAMPAIGN_RECOVERY_REQUIRED'):controller.control(run,str(uuid4()),'resume')


@pytest.mark.parametrize('accept_error',[False,True])
def test_completion_cleanup_error_detaches_and_keeps_result(owned,monkeypatch,accept_error):
    storage,runs,run,_=setup(owned);controller=controller_for(storage);control(controller.runs,run,'resume')
    controller.step(run);_,writer,job=controller.active;assert job.wait()['exit_code']==0
    if accept_error:
        def refuse(*a,**k):raise ValueError('injected_accept_failure')
        monkeypatch.setattr(controller.runs,'accept',refuse)
    close_then_raise(writer,monkeypatch)
    controller.tick()
    state=controller.runs.summary(run)
    assert controller.pending is None and controller.active is None and job.closed and writer.closed
    assert state['state']==('BLOCKED' if accept_error else 'READY')
    assert state['completed_units']==(0 if accept_error else 1)
    assert state['attempts'][0]['job_receipt']['exit_code']==0
    assert controller.last_operation_error['recovery_required'] is True
    if accept_error:assert controller.last_operation_error['reason']=='CAMPAIGN_PREPARATION_FAILED'
    controller.tick()
    assert controller.runs.summary(run)==state
    with pytest.raises(RuntimeRefused,match='CAMPAIGN_RECOVERY_REQUIRED'):controller.step(run)


def test_launch_cleanup_error_stays_latched_after_worker_completion(owned,monkeypatch):
    storage,runs,run,_=setup(owned);controller=controller_for(storage);control(controller.runs,run,'resume')
    controller.cooperative=True;controller.step(run);proof=controller.pending.proof
    while controller.pending.phase!='LAUNCH':controller.tick()
    close_then_raise(proof,monkeypatch);controller.tick()
    assert controller.pending is None and controller.active is not None
    assert controller.last_operation_error['recovery_required'] is True
    original=dict(controller.last_operation_error);job=controller.active[2];assert job.wait()['exit_code']==0
    while controller.active is not None or controller.pending is not None:controller.tick()
    assert controller.runs.summary(run)['completed_units']==1 and controller.last_operation_error==original
    assert controller.busy
    with pytest.raises(RuntimeRefused,match='CAMPAIGN_RECOVERY_REQUIRED'):controller.step(run)
