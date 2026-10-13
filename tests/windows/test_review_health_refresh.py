"""Review launch health uses real watchdog replies and bounded native workers."""
import time
from types import SimpleNamespace
from uuid import uuid4

import pytest
from test_native_seals import state
from test_native_campaign_review import finished_source
from test_native_development_seals import invalidate
from compertum.campaign_review import CampaignReviewController
from compertum.coordinator import Coordinator
from compertum.data.errors import DataError
from compertum.runtime.errors import RuntimeRefused
from compertum.runtime.managed import launch_owner
from compertum.runtime.owner_rpc import call_owner


@pytest.fixture
def review_health(state):
    source,run,seal,evaluation=finished_source(state)
    watchdog,remote=launch_owner(state[1],'watchdog',expect_execution=False)
    state[3].append(watchdog)
    cache={};samples=[]
    def refresh():
        cache['health']=call_owner(remote,'status',{})
        samples.append(cache['health']['observed_monotonic'])
    refresh()
    coordinator=Coordinator(state[2].store,health=lambda:dict(cache['health']))
    coordinator.refresh_health=refresh
    with coordinator.store.conn:coordinator._state('research_state','RUNNING')
    review=CampaignReviewController(coordinator,state[2]);task=str(uuid4())
    review.runs.register(task,run,'scorecard');refresh()
    try:yield review,task,coordinator,refresh,samples,watchdog,seal,evaluation
    finally:review.pause();source.pause()


def capture_children(monkeypatch):
    import compertum.runtime.jobs as jobs
    factory=jobs.JobAPI;create=jobs.create_suspended;handles=[];resumes=[]
    def api_factory():
        api=factory();resume=api.ResumeThread
        def observe(handle):resumes.append(True);return resume(handle)
        api.ResumeThread=observe;return api
    def capture(api,*args,**kwargs):
        info=create(api,*args,**kwargs);handles.append(api.open_process(info.pid));return info
    monkeypatch.setattr(jobs,'JobAPI',api_factory);monkeypatch.setattr(jobs,'create_suspended',capture)
    return handles,resumes


def close_observations(handles):
    try:assert all(h.api.WaitForSingleObject(h.get(),3000)==0 for h in handles)
    finally:
        for h in handles:h.close()


def test_healthy_review_refreshes_after_slow_preparation(review_health,monkeypatch):
    review,task,coordinator,refresh,samples,*_=review_health
    bind=review.runs.bind_task
    def delayed(*args,**kwargs):
        result=bind(*args,**kwargs);time.sleep(5.2);return result
    monkeypatch.setattr(review.runs,'bind_task',delayed)
    before=len(samples);review.step(task)
    assert len(samples)>=before+2
    assert review.active[2].wait()['exit_code']==0
    refresh();review.tick();assert review.runs.completed(task)['state']=='COMPLETED'


def test_slow_final_validation_cannot_resume_with_expired_health(review_health,monkeypatch):
    review,task,*_=review_health
    verify=type(review.runs).verify_launch;delays=[]
    def delayed(runs,*args,**kwargs):
        result=verify(runs,*args,**kwargs)
        if kwargs.get('execution_identity') is not None:
            delays.append(True);time.sleep(5.2)
        return result
    monkeypatch.setattr(type(review.runs),'verify_launch',delayed)
    handles,resumes=capture_children(monkeypatch)
    try:
        with pytest.raises(RuntimeRefused,match='HEALTH_UNVERIFIED'):review.step(task)
        assert delays==[True] and not resumes and review.active is None
        assert review.runs.status(task)['state']=='BLOCKED'
        with pytest.raises(DataError):review.runs.resume(task)
    finally:review.pause();close_observations(handles)


@pytest.mark.parametrize('fault',['watchdog_exit','seal_revoked','deadline'])
def test_final_refresh_preserves_launch_boundaries(state,review_health,monkeypatch,fault):
    review,task,coordinator,refresh,samples,watchdog,seal,evaluation=review_health
    import compertum.runtime.jobs as jobs
    offset=[0.0];calls=[0]
    if fault=='deadline':
        monkeypatch.setattr(jobs,'time',SimpleNamespace(monotonic=lambda:time.monotonic()+offset[0],sleep=time.sleep))
    def changed():
        calls[0]+=1
        if calls[0]==2:
            if fault=='watchdog_exit':watchdog.close()
            elif fault=='seal_revoked':invalidate(state,evaluation,seal)
            else:offset[0]=121.0
        refresh()
    coordinator.refresh_health=changed
    handles,resumes=capture_children(monkeypatch)
    try:
        with pytest.raises((RuntimeRefused,DataError)):review.step(task)
        assert calls[0]==2 and not resumes and review.active is None
        assert review.runs.status(task)['state']=='BLOCKED'
    finally:review.pause();close_observations(handles)
