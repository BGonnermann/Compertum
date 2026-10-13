"""Inject native boundary failures into the real launcher; Win32 is simulated."""
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
import pytest
from test_final_audit_runs import owner,saved,environment,prepare,native
from compertum.runtime import jobs,audit_job_lifetime as life
from compertum.runtime import bootstrap,ipc,job_identity
from compertum import storage as storage_module
from compertum.domain import TaskSpec
from compertum.runtime.errors import RuntimeRefused


@pytest.fixture
def launch_fixture(owner,monkeypatch):
    o=owner;o.storage.root=Path('\\\\?\\'+str(o.storage.root));p,t,w=prepare(o);w.manager=o.storage
    lease=o.storage.lease;lease.project_id='test-audit-project';lease.identity.role='coordinator'
    guard=SimpleNamespace(project=SimpleNamespace(root_path=o.storage.root),resources=[])
    @contextmanager
    def scope(*a):yield guard
    monkeypatch.setattr(jobs,'_owner_scope',scope);monkeypatch.setattr(jobs,'require_live_owner',lambda *a:None)
    monkeypatch.setattr(jobs,'open_store',lambda *a:o.storage.store);monkeypatch.setattr(jobs,'available_physical_memory',lambda:16*1024**3)
    monkeypatch.setattr(storage_module,'BoundedWriter',type(w))
    events=[];state=SimpleNamespace(fail=None,alive=False,assigned=False,resumed=False,limits=None)
    def fault(label):
        events.append(label)
        if state.fail==label:raise RuntimeRefused('SIMULATED_'+label)
    class API:
        def checked(self,value,name):
            if not value:raise RuntimeRefused(name)
            return value
        def _handle(self,value,name):return life.OwnedHandle(self,value)
        def CreateJobObjectW(self,*a):fault('job');return 10
        def GetProcessAffinityMask(self,h,available,system):available._obj.value=15;system._obj.value=15;return True
        def SetInformationJobObject(self,h,kind,value,size):state.limits=value._obj;return True
        def limits(self,h):return state.limits
        def set_inheritable(self,h,value):
            if not value and state.alive:fault('inherit_cleanup')
        def assign(self,j,p):fault('assign');state.assigned=True
        def active(self,j):return int(state.alive and state.assigned)
        def WaitForSingleObject(self,h,ms):return 258 if state.alive else 0
        def TerminateProcess(self,h,code):fault('terminate');state.alive=False;return True
        def TerminateJobObject(self,h,code):state.alive=False;return True
        def ResumeThread(self,h):fault('resume');state.resumed=True;return 1
        def CloseHandle(self,h):events.append('close-'+str(h));return True
    api=API();monkeypatch.setattr(jobs,'JobAPI',lambda:api)
    class Startup:
        raw='{}'
        def __init__(self,*a,**kw):self.closed=False
        def apply(self,env):fault('startup_apply')
        def observe(self,p):fault('startup_observe');return {'fixture':'startup'}
        def before_resume(self,p):fault('startup_recheck');return {'fixture':'startup'}
        def close(self):self.closed=True;events.append('startup_close')
    monkeypatch.setattr(jobs,'StartupBinding',Startup)
    def create(api,argv,env,cwd,inherited=(),*,on_created=None):
        fault('create');state.alive=True
        info=SimpleNamespace(process=11,thread=12,pid=321)
        assert jobs._ACTIVE[lease.project_id] is guard.resources[-1]
        assert on_created is not None;on_created(info)
        assert guard.resources[-1].process.value==11
        fault('after_create');return info
    monkeypatch.setattr(jobs,'create_suspended',create)
    monkeypatch.setattr(bootstrap,'_observation',lambda *a:(fault('observation') or SimpleNamespace()))
    monkeypatch.setattr(ipc,'_remember_worker',lambda *a:None)
    def identity(*a,**kw):fault('identity');return native(o,t)
    monkeypatch.setattr(job_identity,'capture_execution_identity',identity)
    monkeypatch.setattr(jobs.JobHandle,'start_monitor',lambda self:fault('monitor'))
    def before(identity):
        assert o.runs.status(o.task)['state']=='RUNNING';assert not state.resumed;fault('before_resume')
    def launch():return jobs.launch_bounded(lease,TaskSpec(t,project_root=o.storage.root),['fixture','final_audit',str(w.destination)],writer=w,final_audit_request=p,before_resume=before)
    result=SimpleNamespace(o=o,prepared=p,writer=w,lease=lease,events=events,state=state,launch=launch)
    yield result
    job=jobs._ACTIVE.get(lease.project_id)
    if job is not None:
        state.fail=None;job.close()
    jobs._ACTIVE.pop(lease.project_id,None)


@pytest.mark.parametrize('phase,created,bound',[
    ('job',False,False),('startup_apply',False,False),('create',False,False),
    ('after_create',True,False),('inherit_cleanup',True,False),('assign',True,False),
    ('observation',True,False),('startup_observe',True,False),('identity',True,False),
    ('monitor',True,True),('before_resume',True,True),('startup_recheck',True,True),('resume',True,True),
])
def test_failed_launch_retains_exact_job_until_verified_cleanup(launch_fixture,phase,created,bound):
    f=launch_fixture;f.state.fail=phase
    with pytest.raises(life.AuditLaunchFailed) as caught:f.launch()
    launch=caught.value.launch;job=launch.job
    assert caught.value.__cause__.code=='SIMULATED_'+phase
    assert (f.o.runs.status(f.o.task)['attempts'][0]['native_execution'] is not None)==bound
    if job is None:
        assert phase=='job' and life.no_child_disposition(launch)['child_created'] is False
    else:
        assert job.audit_lifetime.child_created==created and not job.closed and not f.writer.closed
        assert jobs._ACTIVE[f.lease.project_id] is job
        f.state.fail=None;job.close();assert job.closed and not f.state.alive and f.lease.project_id not in jobs._ACTIVE
        if not bound:assert life.closed_unbound(job)['child_created']==created
        else:
            with pytest.raises(RuntimeRefused):life.closed_unbound(job)


def test_success_binds_before_resume_and_keeps_slot_until_cleanup(launch_fixture):
    f=launch_fixture;j=f.launch();assert f.state.resumed and j.audit_lifetime.durably_bound and j.audit_lifetime.resume_attempted
    assert not j.audit_lifetime.thread.closed and not j.audit_lifetime.startup.closed
    assert f.events.index('identity')<f.events.index('before_resume')<f.events.index('resume')
    j._finish_budget();assert jobs._ACTIVE[f.lease.project_id] is j
    j.close();assert f.lease.project_id not in jobs._ACTIVE and not f.writer.closed


def test_failed_termination_retains_all_cleanup_authority(launch_fixture):
    f=launch_fixture;j=f.launch();f.state.fail='terminate'
    with pytest.raises(RuntimeRefused):j.close()
    assert not j.closed and f.state.alive and jobs._ACTIVE[f.lease.project_id] is j and not f.writer.closed
    assert not any(e.startswith('close-') for e in f.events)


def test_no_child_proof_is_unavailable_after_any_job_ownership(launch_fixture):
    f=launch_fixture;j=f.launch()
    with pytest.raises(RuntimeRefused):life.no_child_disposition(life.AuditLaunch(f.prepared,f.writer,j))
