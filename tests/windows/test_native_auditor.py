from uuid import uuid4
import hashlib,json
import pytest
from test_native_seals import state
from test_native_development_seals import setup
from test_campaign_job import finish_unit
from compertum.data.encoding import canonical
from compertum.data.errors import DataError
from compertum.runtime.job_identity import validate_execution_identity


def test_native_author_identity_is_committed_before_resume_and_matches_exit(state,monkeypatch):
    controller,run,sid,remote,_=setup(state)
    import compertum.runtime.jobs as jobs
    factory=jobs.JobAPI;observed=[]
    def create_api():
        api=factory();resume=api.ResumeThread
        def invoke(handle):
            attempt=controller.runs._load(run)['attempts'][-1]
            identity=attempt['native_execution'];validate_execution_identity(identity)
            assert identity['role']=='experiment_runner' and identity['task_id']==run
            assert controller.runs._load(run)['last_transition']=='NATIVE_EXECUTION_BOUND'
            observed.append(identity);return resume(handle)
        api.ResumeThread=invoke;return api
    monkeypatch.setattr(jobs,'JobAPI',create_api)
    try:
        controller.step(run);receipt=controller.active[2].wait()
        changed=json.loads(json.dumps(receipt));changed['execution_identity']['task_sha256']='0'*64
        with pytest.raises(DataError,match='CAMPAIGN_EXECUTION_UNVERIFIED'):controller._receipt(run,changed)
        controller.tick();result=controller.runs.summary(run)
        assert receipt['exit_code']==0 and receipt['execution_identity']==observed[0]
        assert observed[0]['process']['pid']==receipt['pid']
        assert observed[0]['process']['creation_filetime']>0
        assert result['attempts'][-1]['native_execution']==observed[0]
        from compertum.audit_campaign import reconstruct_history
        history=[dict(seq=s,body=b,sha256=h) for s,b,h in controller.store.conn.execute('SELECT seq,body,sha256 FROM baseline_history WHERE run_id=? ORDER BY seq',(run,))]
        controls=[dict(request_id=r,action=a,receipt=c) for r,a,c in controller.store.conn.execute('SELECT request_id,action,receipt FROM baseline_controls WHERE run_id=?',(run,))]
        restored,report=reconstruct_history(canonical(controller.runs._load(run)),history,controls)
        assert report['transition_counts']['NATIVE_EXECUTION_BOUND']==1
    finally:controller.pause()


def test_native_independent_momentum_and_ridge_audits_bind_saved_source(state,monkeypatch):
    from compertum.auditor import AuditorController
    from compertum.runtime.job_identity import same_process
    controller,run,sid,remote,_=setup(state,True)
    import ctypes as c
    import compertum.runtime.jobs as jobs
    from compertum.runtime._windows import DWORD
    create=jobs.create_suspended;readonly=[]
    def inspect(api,argv,env,cwd,inherited=()):
        if argv[3]=='compertum.runtime.audit_worker':
            for handle in inherited[1:]:
                written=DWORD();buffer=c.create_string_buffer(b'X')
                assert not api.WriteFile(handle,buffer,1,c.byref(written),None) and c.get_last_error()==5 and written.value==0
            readonly.append(len(inherited)-1)
        return create(api,argv,env,cwd,inherited)
    monkeypatch.setattr(jobs,'create_suspended',inspect)
    try:
        for _ in range(5):result,receipt=finish_unit(controller,run);assert receipt['exit_code']==0
        controller.control(run,str(uuid4()),'stop')
        auditor=AuditorController(controller.coordinator,controller.storage)
        for unit in (0,4):
            task=str(uuid4());registered=auditor.runs.register(task,run,unit)
            assert registered['state']=='READY'
            auditor.step(task);job=auditor.active[2];assert job.api.limits(job.job).basic.active_limit==1
            receipt=job.wait();assert receipt['exit_code']==0
            auditor.tick();result=auditor.runs.status(task)
            assert result['state']=='COMPLETED' and result['financial_accepted'] is False
            attempt=result['attempts'][-1]
            assert attempt['job_receipt']['execution_identity']==attempt['native_execution']
            assert attempt['native_execution']['role']=='experiment_auditor'
            assert not same_process(result['request']['author_execution'],attempt['native_execution'])
            raw=(controller.storage.root/result['artifact']['path']).read_bytes();body=json.loads(raw)
            assert body['worker_pid']==receipt['pid'] and body['audit']['status']=='VERIFIED_PASS'
            assert body['audit_sha256']==result['audit_sha256']
            assert auditor.runs.register(task,run,unit)==result
            assert auditor.step(task)==result and auditor.active is None
        assert controller.runs.summary(run)['state']=='STOPPED' and readonly==[2,3]
    finally:controller.pause()


def test_callback_cannot_rewrite_kernel_identity_before_resume(state,monkeypatch):
    controller,run,sid,remote,_=setup(state)
    import compertum.research as module
    launch=module.launch_bounded
    def altered(*args,**kwargs):
        commit=kwargs['before_resume']
        def changed(identity):
            identity['process']['creation_filetime']+=1
            commit(identity)
        kwargs['before_resume']=changed
        return launch(*args,**kwargs)
    monkeypatch.setattr(module,'launch_bounded',altered)
    try:
        with pytest.raises(DataError,match='CAMPAIGN_EXECUTION_UNVERIFIED'):controller.step(run)
        assert controller.active is None and controller.runs.summary(run)['completed_units']==0
    finally:controller.pause()


def test_native_bound_completed_attempt_requires_exit_receipt(state):
    from compertum.simulation.campaign_runs import validate_state
    from compertum.audit_campaign import _state
    controller,run,sid,remote,_=setup(state)
    try:
        result,receipt=finish_unit(controller,run);s=controller.runs._load(run)
        del s['attempts'][-1]['job_receipt']
        for validator in (validate_state,_state):
            with pytest.raises(DataError):validator(s)
    finally:controller.pause()


@pytest.mark.parametrize('boundary',['before_prepare','before_resume','before_accept'])
def test_native_auditor_rechecks_current_seal_at_every_boundary(state,monkeypatch,boundary):
    from compertum.auditor import AuditorController
    from test_native_development_seals import invalidate
    from compertum.runtime.errors import RuntimeRefused
    controller,run,sid,remote,_=setup(state);finish_unit(controller,run);controller.control(run,str(uuid4()),'stop')
    auditor=AuditorController(controller.coordinator,controller.storage);task=str(uuid4());auditor.runs.register(task,run,0)
    import compertum.runtime.jobs as jobs
    factory=jobs.JobAPI;resumes=[]
    def new_api():
        api=factory();resume=api.ResumeThread
        def invoke(handle):resumes.append(True);return resume(handle)
        api.ResumeThread=invoke;return api
    monkeypatch.setattr(jobs,'JobAPI',new_api)
    try:
        if boundary=='before_prepare':invalidate(state,remote,sid)
        if boundary=='before_resume':
            begin=auditor.runs.begin
            def changed(*args,**kwargs):
                result=begin(*args,**kwargs);invalidate(state,remote,sid);return result
            monkeypatch.setattr(auditor.runs,'begin',changed)
        if boundary=='before_accept':
            auditor.step(task);assert auditor.active[2].wait()['exit_code']==0
            invalidate(state,remote,sid);auditor.tick();assert resumes==[True]
            assert auditor.runs.status(task)['state']=='BLOCKED'
        else:
            with pytest.raises((DataError,RuntimeRefused),match='SEAL_INVALIDATED'):auditor.step(task)
            assert resumes==[] and auditor.runs.status(task)['state']==('READY' if boundary=='before_prepare' else 'BLOCKED')
        assert auditor.runs.status(task)['artifact'] is None
    finally:auditor.pause();controller.pause()


def test_native_audit_pause_retains_orphan_and_retries_once(state):
    from compertum.auditor import AuditorController
    controller,run,sid,remote,_=setup(state);finish_unit(controller,run);controller.control(run,str(uuid4()),'stop')
    auditor=AuditorController(controller.coordinator,controller.storage);task=str(uuid4());auditor.runs.register(task,run,0)
    try:
        auditor.step(task);first=auditor.active[1].path;auditor.pause()
        assert first.exists() and auditor.runs.status(task)['state']=='INTERRUPTED'
        auditor.runs.resume(task);auditor.step(task);assert auditor.active[2].wait()['exit_code']==0;auditor.tick()
        result=auditor.runs.status(task);assert result['state']=='COMPLETED' and len(result['attempts'])==2
        assert result['attempts'][0]['status']=='INTERRUPTED' and first.exists()
        with pytest.raises(DataError):auditor.runs.resume(task)
    finally:auditor.pause();controller.pause()


def test_completed_native_audit_revalidates_its_committed_output(state):
    from compertum.auditor import AuditorController
    controller,run,sid,remote,_=setup(state);finish_unit(controller,run);controller.control(run,str(uuid4()),'stop')
    auditor=AuditorController(controller.coordinator,controller.storage);task=str(uuid4());auditor.runs.register(task,run,0)
    try:
        auditor.step(task);assert auditor.active[2].wait()['exit_code']==0;auditor.tick();result=auditor.runs.status(task)
        assert result['state']=='COMPLETED'
        path=controller.storage.root/result['artifact']['path'];raw=path.read_bytes();path.write_bytes(raw[:-1]+b' ')
        failures=[]
        for operation in (lambda:auditor.step(task),lambda:auditor.runs.register(task,run,0)):
            try:operation()
            except DataError:failures.append(True)
        assert len(failures)==2
    finally:auditor.pause();controller.pause()


@pytest.mark.parametrize('failure',['receipt','adopt'])
def test_pause_bookkeeping_failure_leaves_durable_nonrunning_outcome(state,monkeypatch,failure):
    from compertum.auditor import AuditorController
    import compertum.auditor as module
    controller,run,sid,remote,_=setup(state);finish_unit(controller,run);controller.control(run,str(uuid4()),'stop')
    auditor=AuditorController(controller.coordinator,controller.storage);task=str(uuid4());auditor.runs.register(task,run,0)
    def refused(*args,**kwargs):raise DataError('INJECTED_PAUSE_FAILURE')
    try:
        auditor.step(task)
        if failure=='receipt':monkeypatch.setattr(auditor.runs,'record_exit',refused)
        else:monkeypatch.setattr(module,'adopt_fixture_bytes',refused)
        with pytest.raises(DataError,match='INJECTED_PAUSE_FAILURE'):auditor.pause()
        assert auditor.active is None and auditor.runs.status(task)['state']=='BLOCKED'
        assert AuditorController(controller.coordinator,controller.storage).runs.status(task)['state']=='BLOCKED'
    finally:auditor.pause();controller.pause()


@pytest.mark.parametrize('case',['task','source','pid','audit_digest','boolean_unit','financial_integer'])
def test_native_audit_output_cannot_be_relabelled_or_copied(state,case):
    from compertum.auditor import AuditorController
    controller,run,sid,remote,_=setup(state);finish_unit(controller,run);controller.control(run,str(uuid4()),'stop')
    auditor=AuditorController(controller.coordinator,controller.storage)
    try:
        task=str(uuid4());auditor.runs.register(task,run,0);auditor.step(task)
        writer=auditor.active[1];assert auditor.active[2].wait()['exit_code']==0
        v=json.loads(writer.path.read_bytes())
        if case=='task':v['task_id']=str(uuid4())
        elif case=='source':v['input_sha256']='0'*64
        elif case=='pid':v['worker_pid']+=4
        elif case=='audit_digest':v['audit_sha256']='0'*64
        elif case=='boolean_unit':v['unit']=False
        else:v['financial_accepted']=0
        # Fault injection after genuine worker exit, before the coordinator publishes.
        writer.stream.seek(0);writer.stream.truncate();writer.stream.write(canonical(v));writer.stream.flush()
        auditor.tick();assert auditor.runs.status(task)['state']=='BLOCKED'
    finally:auditor.pause();controller.pause()


def test_native_audit_request_identity_does_not_reset_attempt_budget(state):
    from compertum.auditor import AuditorController
    controller,run,sid,remote,_=setup(state);finish_unit(controller,run);controller.control(run,str(uuid4()),'stop')
    auditor=AuditorController(controller.coordinator,controller.storage);task=str(uuid4());auditor.runs.register(task,run,0)
    try:
        for attempt in (1,2):
            auditor.step(task);auditor.pause()
            if attempt==1:auditor.runs.resume(task)
        result=auditor.runs.status(task);assert result['state']=='FAILED' and len(result['attempts'])==2
        assert auditor.runs.register(task,run,0)==result
        with pytest.raises(DataError,match='AUDITOR_REQUEST_CONFLICT'):auditor.runs.register(str(uuid4()),run,0)
        assert auditor.runs.status(task)==result
        # Simulate an older ledger containing duplicate requests; retain both records.
        duplicate=json.loads(json.dumps(result));duplicate.update(task_id=str(uuid4()),state='READY',attempts=[])
        db=controller.store.conn
        import sqlite3
        with pytest.raises(sqlite3.IntegrityError,match='AUDITOR_REQUEST_CONFLICT'):
            with db:db.execute('INSERT INTO audit_runs VALUES(?,?)',(duplicate['task_id'],canonical(duplicate).decode()))
        with db:
            db.execute('DROP TRIGGER audit_request_insert');db.execute('DROP TRIGGER audit_request_update')
            db.execute('INSERT INTO audit_runs VALUES(?,?)',(duplicate['task_id'],canonical(duplicate).decode()))
        before=[tuple(db.execute('SELECT * FROM '+table+' ORDER BY task_id').fetchall()) for table in ('audit_runs','audit_history')]
        for operation in (lambda:auditor.runs.status(task),lambda:AuditorController(controller.coordinator,controller.storage)):
            with pytest.raises(DataError,match='AUDITOR_REQUEST_CONFLICT'):operation()
        after=[tuple(db.execute('SELECT * FROM '+table+' ORDER BY task_id').fetchall()) for table in ('audit_runs','audit_history')]
        assert before==after
    finally:auditor.pause();controller.pause()
