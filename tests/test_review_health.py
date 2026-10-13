"""Explicit health refresh never replaces the normal freshness validation."""
import time
import pytest
from test_coordinator import coordinator
from compertum.runtime.errors import RuntimeRefused


def test_ordinary_health_check_does_not_refresh_or_reenter_halt(coordinator):
    coordinator.health=lambda:dict(status='HEALTHY',observed_monotonic=time.monotonic())
    def forbidden():pytest.fail('ordinary health checks must remain cached')
    coordinator.refresh_health=forbidden
    assert coordinator.require_health()['status']=='HEALTHY'


@pytest.mark.parametrize('observation',['stale','future','unhealthy','missing'])
def test_refresh_still_rejects_unverified_observations(coordinator,observation):
    cache={};calls=[]
    def refresh():
        calls.append(True)
        cache.update(status='RESEARCH_BLOCKED' if observation=='unhealthy' else 'HEALTHY')
        if observation!='missing':cache['observed_monotonic']=time.monotonic()+(-6 if observation=='stale' else 6 if observation=='future' else 0)
    coordinator.refresh_health=refresh;coordinator.health=lambda:dict(cache)
    with pytest.raises(RuntimeRefused,match='HEALTH_UNVERIFIED'):coordinator.require_health(refresh=True)
    assert calls==[True]


@pytest.mark.parametrize('kind,callback',[('scorecard',None),('echo',lambda **_:None)])
def test_review_health_callback_is_required_and_confined(coordinator,monkeypatch,kind,callback):
    from uuid import uuid4
    from compertum.foundation import fixture_spec
    from compertum.runtime import jobs
    def forbidden():pytest.fail('invalid review callback reached native creation')
    monkeypatch.setattr(jobs,'JobAPI',forbidden)
    task=fixture_spec(coordinator.store.root,str(uuid4()))
    with pytest.raises(RuntimeRefused,match='REVIEW_INPUT_DENIED'):
        jobs.launch_bounded(coordinator.store.lease,task,['fixture',kind,'unused'],before_execute=callback)
