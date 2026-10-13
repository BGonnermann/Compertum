"""Actual worker rejection remains terminal through coordinator fault paths."""
from uuid import uuid4
import pytest
from test_native_seals import state
from test_native_development_seals import setup
from test_campaign_job import finish_unit
from test_native_campaign_review import finished_source
from compertum.data.errors import DataError


@pytest.mark.parametrize('kind,boundary',[('scorecard','adopt'),('audit','pause'),('audit','adopt')])
def test_native_rejection_survives_pause_and_bookkeeping_failure(state,monkeypatch,kind,boundary):
    if kind=='scorecard':
        from compertum.campaign_review import CampaignReviewController as Controller
        import compertum.campaign_review as module
        controller,run,seal,remote=finished_source(state)
    else:
        from compertum.auditor import AuditorController as Controller
        import compertum.auditor as module
        controller,run,seal,remote,_=setup(state);finish_unit(controller,run);controller.control(run,str(uuid4()),'stop')
    review=Controller(controller.coordinator,controller.storage);task=str(uuid4());review.runs.register(task,run,kind if kind=='scorecard' else 0)
    import compertum.runtime.jobs as jobs
    create=jobs.create_suspended
    def changed(api,argv,*args,**kwargs):
        target=argv[3]=='compertum.runtime.audit_worker' if kind=='audit' else argv[3]=='compertum.runtime.campaign_worker' and argv[4]=='scorecard'
        if target:
            argv=list(argv);argv[7 if kind=='audit' else 8]='0'*64
        return create(api,argv,*args,**kwargs)
    monkeypatch.setattr(jobs,'create_suspended',changed)
    try:
        review.step(task);assert review.active[2].wait()['exit_code']==6
        if boundary=='adopt':
            def unavailable(*args):raise OSError('INJECTED_ADOPTION_FAILURE')
            monkeypatch.setattr(module,'adopt_fixture_bytes',unavailable)
            try:review.tick()
            except DataError:pass
        else:review.pause()
        result=review.runs.status(task)
        assert result['state']=='BLOCKED' and review.active is None
        assert result['attempts'][-1]['job_receipt']['exit_code']==6
        with pytest.raises(DataError):review.runs.resume(task)
    finally:review.pause();controller.pause()


@pytest.mark.parametrize('kind',['review','audit'])
def test_native_owner_death_after_recorded_rejection_stays_terminal(tmp_path,kind):
    import json,os,shutil,subprocess
    from pathlib import Path
    from fixture_processes import python_process
    shutil.copyfile(Path(__file__).parents[2]/'config/default.toml',tmp_path/'config.toml');run,task=str(uuid4()),str(uuid4())
    def child(action,expected=0):
        p=python_process(['-B',str(Path(__file__).parents[1]/('helpers/'+kind+'_native_child.py')),str(tmp_path),run,task,action],env={k:v for k,v in os.environ.items() if k.upper() in {'SYSTEMROOT','WINDIR','PYTHONPATH','PYTHONDONTWRITEBYTECODE','PYTHONNOUSERSITE','OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'}},stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        out,err=p.communicate(timeout=60);assert p.returncode==expected,(out,err)
        return json.loads(out)['result'] if expected==0 else None
    child('create');child('crash_after_rejection',80);result=child('status')
    assert result['state']=='BLOCKED' and len(result['attempts'])==1
    assert result['attempts'][-1]['job_receipt']['exit_code']==6 and result['artifact'] is None


@pytest.mark.parametrize('case',['erase_attempts','reset_terminal'])
def test_unit_audit_rehashed_history_cannot_reset_attempts(state,case):
    import hashlib,json
    from compertum.auditor import AuditorController
    from compertum.data.encoding import canonical
    controller,run,seal,remote,_=setup(state);finish_unit(controller,run);controller.control(run,str(uuid4()),'stop')
    audit=AuditorController(controller.coordinator,controller.storage);task=str(uuid4());audit.runs.register(task,run,0)
    try:
        audit.step(task);audit.pause();audit.runs.resume(task);audit.step(task);audit.pause()
        result=audit.runs.status(task);assert result['state']=='FAILED'
        result.update(state='READY',last_transition='RESUMED')
        if case=='erase_attempts':result['attempts']=[]
        raw=canonical(result);db=audit.runs.store.conn
        with db:
            db.execute('UPDATE audit_runs SET body=? WHERE task_id=?',(raw.decode(),task))
            db.execute('UPDATE audit_history SET body=?,sha256=? WHERE task_id=? AND seq=(SELECT max(seq) FROM audit_history WHERE task_id=?)',(raw.decode(),hashlib.sha256(raw).hexdigest(),task,task))
        with pytest.raises(DataError):audit.runs.status(task)
    finally:audit.pause();controller.pause()
