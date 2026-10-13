"""Real managed evaluation RPC, bounded Jobs and current revocation evidence."""
from uuid import uuid4
import pytest
from test_native_seals import state,start
from test_campaign_job import controller_for,finish_unit
from helpers.saved_campaign_fixture import campaign_folds
from compertum.development_seals import create_campaign
from compertum.simulation.runs import SavedRuns
from compertum.evaluation_seals import reserve_seal_append,verify_seal_journal
from compertum.runtime.owner_rpc import call_owner
from compertum.data.errors import DataError
from compertum.runtime.errors import RuntimeRefused


def setup(state,full=False):
    job,remote=start(state);runs=SavedRuns(state[2]);run,sid=str(uuid4()),str(uuid4())
    created=create_campaign(runs,run,campaign_folds(full),seal_id=sid,evaluation=remote,
        data_manifest_sha256='a'*64,holdout_manifest_sha256='b'*64)
    controller=controller_for(state[2]);controller.runs.control(run,str(uuid4()),'resume')
    return controller,run,sid,remote,created


def invalidate(state,remote,sid):
    reserve_seal_append(state[2]);call_owner(remote,'synthetic_protocol',{'operation':'invalidate','seal_id':sid,'reason':'POLICY_CHANGED'})


def test_native_admitted_campaign_uses_saved_fit_and_survives_owner_restart(state):
    controller,run,sid,remote,created=setup(state,True)
    try:
        for _ in range(5):
            result,receipt=finish_unit(controller,run);assert receipt['exit_code']==0
        assert result['completed_units']==5 and result['protocol_status']=='SEALED_SYNTHETIC_DEVELOPMENT'
        first=call_owner(remote,'synthetic_protocol',{'operation':'inspect','seal_id':sid})
        remote.close();state[3][0].close();job,other=start(state)
        assert call_owner(other,'synthetic_protocol',{'operation':'inspect','seal_id':sid})==first
        assert controller.runs.status(run)['completed_units']==5
        assert verify_seal_journal(state[0])['sequence']==2
    finally:controller.pause()


@pytest.mark.parametrize('boundary',['before_prepare','before_resume','before_accept'])
def test_native_revocation_blocks_current_execution_boundary(state,monkeypatch,boundary):
    controller,run,sid,remote,_=setup(state)
    import compertum.runtime.jobs as jobs
    factory=jobs.JobAPI;resumes=[];processes=[];create=jobs.create_suspended
    def capture(api,*args,**kwargs):
        result=create(api,*args,**kwargs);processes.append(api.open_process(result.pid));return result
    def api_factory():
        api=factory();resume=api.ResumeThread
        def invoke(handle):resumes.append(True);return resume(handle)
        api.ResumeThread=invoke;return api
    monkeypatch.setattr(jobs,'JobAPI',api_factory);monkeypatch.setattr(jobs,'create_suspended',capture)
    try:
        if boundary=='before_prepare':invalidate(state,remote,sid)
        elif boundary=='before_resume':
            begin=controller.runs.begin_campaign
            def changed(*args,**kwargs):
                result=begin(*args,**kwargs);invalidate(state,remote,sid);return result
            monkeypatch.setattr(controller.runs,'begin_campaign',changed)
        if boundary=='before_accept':
            controller.step(run);assert controller.active[2].wait()['exit_code']==0
            invalidate(state,remote,sid);controller.tick()
            result=controller.runs.summary(run)
            assert result['state']=='BLOCKED' and result['completed_units']==0
            assert resumes==[True]
        else:
            with pytest.raises((DataError,RuntimeRefused),match='SEAL_INVALIDATED'):controller.step(run)
            result=controller.runs.summary(run)
            assert result['completed_units']==0 and not resumes
            assert result['state']==('READY' if boundary=='before_prepare' else 'BLOCKED')
        assert all(h.api.WaitForSingleObject(h.get(),3000)==0 for h in processes)
    finally:
        controller.pause()
        for h in processes:h.close()


def test_remote_checkpoint_barrier_leaves_retriable_ticket(state):
    job,remote=start(state);runs=SavedRuns(state[2]);run,sid,barrier=str(uuid4()),str(uuid4()),str(uuid4())
    call_owner(remote,'checkpoint',{'operation':'snapshot','barrier_id':barrier,'destination':'backups/admission-fixture.sqlite','maximum_bytes':1024**2})
    args=dict(seal_id=sid,evaluation=remote,data_manifest_sha256='a'*64,holdout_manifest_sha256='b'*64)
    with pytest.raises(DataError,match='SEAL_ADMISSION_UNVERIFIED'):create_campaign(runs,run,campaign_folds(),**args)
    assert verify_seal_journal(state[0])['sequence']==0
    call_owner(remote,'checkpoint',{'operation':'end','barrier_id':barrier})
    assert create_campaign(runs,run,campaign_folds(),**args)['state']=='PAUSED'
    assert verify_seal_journal(state[0])['sequence']==2
