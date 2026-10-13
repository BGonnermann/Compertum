"""Unexpected owner-side acceptance failures cannot leave a dead RUNNING attempt."""
import pytest
from test_persistence import owned
from test_saved_campaigns import setup,control
from test_campaign_job import controller_for
from compertum.data.errors import DataError

@pytest.mark.parametrize('error',[KeyError('missing_campaign_binding'),ValueError('invalid_campaign_binding')])
def test_unexpected_acceptance_failure_blocks_and_keeps_orphan(owned,monkeypatch,error):
    storage,runs,run,_=setup(owned);controller=controller_for(storage);control(controller.runs,run,'resume')
    controller.step(run);job=controller.active[2];assert job.wait()['exit_code']==0
    def broken(*args,**kwargs):raise error
    monkeypatch.setattr(controller.runs,'accept',broken)
    try:
        controller.tick()
        state=controller.runs.summary(run)
        assert controller.active is None and job.closed and state['state']=='BLOCKED'
        assert state['resolved_units']==0 and len(state['attempts'])==1
        assert state['attempts'][0]['reason']=='UNIT_INTEGRITY_FAILURE'
        assert len(list((storage.root/f'artifacts/runs/{run}/baseline').glob('unit-*.campaign')))==1
        with pytest.raises(DataError,match='RUN_BLOCKED'):control(controller.runs,run,'resume')
    finally:controller.pause()

def test_error_after_acceptance_keeps_committed_result(owned,monkeypatch):
    storage,runs,run,_=setup(owned);controller=controller_for(storage);control(controller.runs,run,'resume')
    original=controller.runs.accept
    def committed(*args,**kwargs):
        original(*args,**kwargs);raise ValueError('after_commit')
    monkeypatch.setattr(controller.runs,'accept',committed)
    controller.step(run);job=controller.active[2];assert job.wait()['exit_code']==0
    try:
        controller.tick();state=controller.runs.status(run)
        assert controller.active is None and job.closed and state['state']=='READY'
        assert state['completed_units']==1 and state['attempts'][0]['status']=='COMPLETED'
    finally:controller.pause()
