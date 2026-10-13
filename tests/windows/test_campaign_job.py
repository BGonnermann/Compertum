"""Dedicated campaign Jobs: inherited dependencies, admission, limits and controls."""
import hashlib,json,time
from types import SimpleNamespace
from uuid import uuid4
import pytest
from test_persistence import owned
from test_saved_campaigns import setup,control
from compertum.data.errors import DataError
from compertum.research import ResearchController
from compertum.runtime.errors import RuntimeRefused
from compertum.modeling.campaign import UNITS


def controller_for(storage):
    return ResearchController(SimpleNamespace(status=lambda:{'research_state':'RUNNING'},require_health=lambda **_:None),storage)


def finish_unit(controller,run):
    controller.step(run);job=controller.active[2];receipt=job.wait();controller.tick()
    assert receipt['assigned_before_resume'] and receipt['active_processes']==0 and receipt['observed_children_exited']
    assert receipt['memory_limit']==4*1024**3 and receipt['affinity'].bit_count()<=4
    return controller.runs.summary(run),receipt


def test_native_campaign_fit_dependency_and_exact_evaluation(owned,monkeypatch):
    storage,runs,run,created=setup(owned,True);controller=controller_for(storage);control(controller.runs,run,'resume')
    import ctypes as c
    import compertum.runtime.jobs as jobs
    from compertum.runtime._windows import DWORD
    create=jobs.create_suspended;read_only=[]
    def inspect_handles(api,argv,env,cwd,inherited=()):
        if len(inherited)==3:
            written=DWORD();buffer=c.create_string_buffer(b'X')
            assert not api.WriteFile(inherited[2],buffer,1,c.byref(written),None)
            assert c.get_last_error()==5 and written.value==0
            read_only.append(True)
        return create(api,argv,env,cwd,inherited)
    monkeypatch.setattr(jobs,'create_suspended',inspect_handles)
    try:
        for _ in range(5):
            state,receipt=finish_unit(controller,run);assert receipt['exit_code']==0 and not receipt['timed_out']
        assert state['completed_units']==5 and state['resolved_units']==5 and read_only==[True]
        fit=state['outcomes'][UNITS[3].key];evaluation=state['outcomes'][UNITS[4].key]
        assert evaluation['dependency_sha256']==fit['payload_sha256']
        from compertum.runtime.campaign_worker import compute
        import compertum.modeling.checkpoints as module
        def forbidden(*a,**k):raise AssertionError('evaluation worker cannot refit')
        monkeypatch.setattr(module,'fit_ridge',forbidden)
        raw=(storage.root/created['input_artifact']['path']).read_bytes()
        dependency=(storage.root/fit['artifact']['path']).read_bytes()
        expected=compute(raw,created['request_sha256'],4,dependency_raw=dependency,dependency_digest=fit['artifact']['sha256'],dependency_payload_sha256=fit['payload_sha256'])
        from compertum.simulation.campaign_record import pack_result
        from compertum.runtime.startup_record import expected_proof
        bound=expected_proof(state['attempts'][-1]['native_execution'])
        expected=pack_result(expected.split(b'\n',1)[1],created['request_sha256'],4,fit['payload_sha256'],startup=bound)
        assert (storage.root/evaluation['artifact']['path']).read_bytes()==expected
        for wrong in ('frame','payload','missing'):
            kwargs=dict(dependency_raw=dependency,dependency_digest=fit['artifact']['sha256'],dependency_payload_sha256=fit['payload_sha256'])
            if wrong=='frame':kwargs['dependency_digest']='0'*64
            elif wrong=='payload':kwargs['dependency_payload_sha256']='0'*64
            else:kwargs={}
            with pytest.raises(DataError):compute(raw,created['request_sha256'],4,**kwargs)
    finally:controller.pause()


def test_native_deterministic_fit_failure_skips_only_its_evaluation(owned):
    storage,runs,run,created=setup(owned);controller=controller_for(storage);control(controller.runs,run,'resume')
    try:
        for _ in range(4):state,receipt=finish_unit(controller,run)
        assert receipt['exit_code']==4
        assert state['state']=='READY' and state['resolved_units']==5 and state['failed_units']==1 and state['skipped_units']==1
        assert state['outcomes'][UNITS[3].key]['status']=='FAILED' and state['outcomes'][UNITS[4].key]['status']=='SKIPPED'
    finally:controller.pause()


def test_prior_daily_usage_does_not_block_native_campaign(owned):
    from datetime import datetime
    storage,runs,run,created=setup(owned);controller=controller_for(storage);control(controller.runs,run,'resume')
    day=datetime.now().astimezone().date().isoformat();historical=str(uuid4())
    with storage.store.conn:
        storage.store.conn.execute('CREATE TABLE IF NOT EXISTS job_budget(id TEXT PRIMARY KEY,day TEXT NOT NULL,charged INTEGER NOT NULL,status TEXT NOT NULL)')
        storage.store.conn.execute('INSERT INTO job_budget VALUES(?,?,?,?)',(historical,day,7200,'FINISHED'))
    try:
        state,receipt=finish_unit(controller,run)
        assert receipt['exit_code']==0 and not receipt['timed_out']
        assert state['state']=='READY' and len(state['attempts'])==1 and state['resolved_units']==1
        assert controller.active is None
        assert storage.store.conn.execute('SELECT charged,status FROM job_budget WHERE id=?',(historical,)).fetchone()==(7200,'FINISHED')
        rows=storage.store.conn.execute('SELECT charged,status FROM job_budget WHERE id!=?',(historical,)).fetchall()
        assert len(rows)==1 and rows[0][0]>0 and rows[0][1]=='FINISHED'
    finally:controller.pause()


def test_health_admission_and_startup_never_dispatch_implicitly(owned):
    storage,runs,run,created=setup(owned);control(runs,run,'resume');controller=controller_for(storage)
    assert controller.runs.summary(run)['state']=='PAUSED' and controller.active is None
    control(controller.runs,run,'resume')
    def refused():raise RuntimeRefused('HEALTH_NOT_READY')
    controller.coordinator.require_health=refused
    with pytest.raises(RuntimeRefused,match='HEALTH_NOT_READY'):controller.step(run)
    assert controller.runs.summary(run)['attempts']==[] and controller.active is None


def test_native_campaign_pause_and_terminal_stop_preserve_attempt(owned):
    storage,runs,run,created=setup(owned);controller=controller_for(storage);control(controller.runs,run,'resume')
    controller.step(run);job=controller.active[2];controller.pause()
    state=controller.runs.summary(run)
    assert controller.active is None and state['state']=='INTERRUPTED' and len(state['attempts'])==1
    assert job.closed and job.receipt['observed_children_exited']
    assert state['attempts'][0]['job_receipt']['active_processes']==0
    stopped=controller.control(run,str(uuid4()),'stop');assert stopped['state']=='STOPPED'
    with pytest.raises(DataError,match='RUN_TERMINAL'):controller.control(run,str(uuid4()),'resume')

