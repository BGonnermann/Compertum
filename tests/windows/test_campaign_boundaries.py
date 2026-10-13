"""Native campaign failure boundaries; injected failures are labeled explicitly."""
import ctypes as c
import time
from types import SimpleNamespace
import pytest
from test_persistence import owned
from test_saved_campaigns import setup,control
from test_campaign_job import controller_for,finish_unit
from compertum.data.errors import DataError
from compertum.modeling.campaign import UNITS
from compertum.runtime.errors import RuntimeRefused
from compertum.runtime._windows import DWORD


@pytest.mark.parametrize('case',['reject','changed','after_commit','deadline','resume','cleanup','no_commit'])
def test_pre_resume_failures_bind_only_the_prepared_attempt(owned,monkeypatch,case):
    import compertum.runtime.jobs as jobs
    storage,runs,run,_=setup(owned);controller=controller_for(storage);control(controller.runs,run,'resume')
    original=controller.runs.begin_campaign;processes=[];resume_calls=[];native_create=jobs.create_suspended
    real_clock=time.monotonic;offset=[0]
    if case=='deadline':monkeypatch.setattr(jobs,'time',SimpleNamespace(monotonic=lambda:real_clock()+offset[0],sleep=time.sleep))
    def capture(api,*args,**kwargs):
        result=native_create(api,*args,**kwargs);processes.append(api.open_process(result.pid));return result
    monkeypatch.setattr(jobs,'create_suspended',capture)
    native_api=jobs.JobAPI
    def api_factory():
        api=native_api();resume=api.ResumeThread;set_flag=api.set_inheritable;failed=[False]
        def flag(handle,value):
            if case=='cleanup' and not value and not failed[0]:
                failed[0]=True;raise RuntimeRefused('INJECTED_FLAG_RESET_FAILURE')
            return set_flag(handle,value)
        api.set_inheritable=flag
        def invoke(handle):
            resume_calls.append(True)
            return 0 if case=='resume' else resume(handle)
        api.ResumeThread=invoke;return api
    monkeypatch.setattr(jobs,'JobAPI',api_factory)
    def admission(run_id,prepared,**kwargs):
        if case=='reject':raise DataError('ADMISSION_TEST_REJECTED')
        if case=='no_commit':return None
        if case=='changed':return original(run_id,{**prepared,'unit':prepared['unit']+1},**kwargs)
        result=original(run_id,prepared,**kwargs)
        if case=='after_commit':raise RuntimeRefused('AFTER_COMMIT_TEST_FAILURE')
        if case=='deadline':offset[0]=121
        return result
    monkeypatch.setattr(controller.runs,'begin_campaign',admission)
    try:
        with pytest.raises((DataError,RuntimeRefused)):controller.step(run)
        state=controller.runs.summary(run)
        assert controller.active is None and len(processes)==1
        assert all(h.api.WaitForSingleObject(h.get(),3000)==0 for h in processes)
        if case in ('reject','changed','cleanup','no_commit'):assert state['state']=='READY' and state['attempts']==[]
        else:
            assert state['state']=='BLOCKED' and len(state['attempts'])==1
            assert state['attempts'][0]['reason']=='LAUNCH_FAILED'
            assert state['attempts'][0]['unit']==0 and state['attempts'][0]['attempt']==1
        assert len(resume_calls)==(1 if case=='resume' else 0)
        assert any(r['status']=='ABANDONED' and (storage.root/r['path']).is_file() and r['maximum']==16*1024**2 for r in storage.reservations())
        # Failure before resume conservatively retains the entire CPU reservation.
        assert storage.store.conn.execute('SELECT charged,status FROM job_budget').fetchall()==[(126,'RESERVED')]
    finally:
        for h in processes:
            if h.api.WaitForSingleObject(h.get(),0)!=0:
                # Contain the intentionally exposed regression before leaving a failed test.
                h.api.TerminateProcess(h.get(),125);h.api.WaitForSingleObject(h.get(),3000)
            h.close()


@pytest.mark.parametrize('case',['alias','invalid','swapped'])
def test_worker_native_handle_refusal_blocks_without_publishing(owned,monkeypatch,case):
    import compertum.runtime.jobs as jobs
    storage,runs,run,_=setup(owned);controller=controller_for(storage);control(controller.runs,run,'resume')
    create=jobs.create_suspended
    def corrupt(api,argv,env,cwd,inherited=()):
        argv=list(argv)
        if case=='alias':argv[4]=argv[5]
        elif case=='invalid':argv[4]='2147483646'
        else:argv[4],argv[5]=argv[5],argv[4]
        return create(api,argv,env,cwd,inherited)
    monkeypatch.setattr(jobs,'create_suspended',corrupt)
    try:
        state,receipt=finish_unit(controller,run)
        assert receipt['exit_code']==6 and state['state']=='BLOCKED' and state['resolved_units']==0
        assert state['attempts'][0]['reason']=='UNIT_INTEGRITY_FAILURE'
        assert not list((storage.root/f'artifacts/runs/{run}/baseline').glob('unit-*.campaign'))
        with pytest.raises(DataError,match='RUN_BLOCKED'):control(controller.runs,run,'resume')
        control(controller.runs,run,'pause')
        with pytest.raises(DataError,match='RUN_BLOCKED'):control(controller.runs,run,'resume')
    finally:controller.pause()


def test_injected_transient_exit_receipts_allow_two_attempts_only(owned,monkeypatch):
    storage,runs,run,_=setup(owned);controller=controller_for(storage);control(controller.runs,run,'resume')
    try:
        for number in (1,2):
            controller.step(run);job=controller.active[2];receipt=job.wait();assert receipt['exit_code']==0
            monkeypatch.setattr(job,'wait',lambda:{**receipt,'exit_code':5})
            controller.tick();state=controller.runs.summary(run)
            assert len(state['attempts'])==number and state['resolved_units']==(1 if number==2 else 0)
            if number==1:
                assert state['state']=='INTERRUPTED';control(controller.runs,run,'resume')
        assert state['outcomes'][UNITS[0].key]['reason']=='TRANSIENT_ATTEMPTS_EXHAUSTED'
    finally:controller.pause()


@pytest.mark.parametrize('case',['timely','timeout','exit_race'])
def test_campaign_late_poll_keeps_native_timeout_evidence(owned,monkeypatch,case):
    storage,runs,run,_=setup(owned);controller=controller_for(storage);control(controller.runs,run,'resume')
    controller.step(run);job=controller.active[2]
    try:
        if case=='timeout':job.deadline=time.monotonic()-.01
        receipt=job.wait()
        if case=='exit_race':monkeypatch.setattr(job,'wait',lambda:{**receipt,'timed_out':True})
        job.deadline=time.monotonic()-.01;controller.tick();state=controller.runs.summary(run)
        assert state['resolved_units']==1 and state['state']=='READY'
        if case=='timely':assert state['completed_units']==1
        else:
            assert state['failed_units']==1 and state['attempts'][0]['reason']=='JOB_TIMEOUT'
            assert state['attempts'][0]['job_receipt']['timed_out']
    finally:controller.pause()


def test_campaign_preparation_time_is_charged(owned,monkeypatch):
    from datetime import datetime,timedelta
    import compertum.research as module
    storage,runs,run,_=setup(owned);controller=controller_for(storage);control(controller.runs,run,'resume')
    class Earlier(datetime):
        @classmethod
        def now(cls,tz=None):return datetime.now(tz)-timedelta(seconds=3)
    monkeypatch.setattr(module,'datetime',Earlier)
    started=time.monotonic();controller.step(run);job=controller.active[2]
    try:
        assert job.started<=started-2.9 and job.deadline<=started+117.1
        receipt=job.wait();controller.tick();assert receipt['exit_code']==0
        charged,status=storage.store.conn.execute('SELECT charged,status FROM job_budget').fetchone()
        assert status=='FINISHED' and charged>=3
    finally:controller.pause()

def test_same_committed_attempt_cannot_launch_a_second_process(owned,monkeypatch):
    import compertum.research as module
    storage,runs,run,_=setup(owned);controller=controller_for(storage);control(controller.runs,run,'resume')
    launch=module.launch_bounded;captured={};second=None
    def capture(*args,**kwargs):
        captured.update(args=args,kwargs=kwargs);return launch(*args,**kwargs)
    monkeypatch.setattr(module,'launch_bounded',capture)
    try:
        controller.step(run);first=controller.active[2];assert first.wait()['exit_code']==0
        # The first process exited, but its output has not yet been accepted.
        with pytest.raises((DataError,RuntimeRefused),match='CAMPAIGN_ADMISSION_UNCOMMITTED'):
            second=launch(*captured['args'],**{**captured['kwargs'],'before_resume':lambda identity:None})
        assert len(controller.runs.summary(run)['attempts'])==1
        controller.tick();assert controller.runs.summary(run)['completed_units']==1
    finally:
        if second:second.close()
        controller.pause()
