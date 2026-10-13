"""Saved campaign owner checks; native worker integration has separate tests."""
from uuid import uuid4
from pathlib import Path
import hashlib,json
import pytest
from test_persistence import owned
from test_storage import manager
from helpers.saved_campaign_fixture import campaign_folds
from compertum.simulation.runs import SavedRuns,runtime_identity
from compertum.modeling.campaign import UNITS
from compertum.data.errors import DataError


def setup(owned,full=False,maximum=128*1024**2):
    storage=manager(owned);runs=SavedRuns(storage);run=str(uuid4())
    created=runs.create_campaign(run,campaign_folds(full),maximum_bytes=maximum)
    return storage,runs,run,created

def control(runs,run,action):return runs.control(run,str(uuid4()),action)


def test_campaign_registration_controls_and_terminal_stop(owned):
    storage,runs,run,created=setup(owned)
    assert created['state']=='PAUSED' and created['total_units']==63 and created['resolved_units']==0
    assert runs.create_campaign(run,campaign_folds())==created
    with pytest.raises(DataError,match='RUN_NOT_READY'):runs.step(run)
    request=str(uuid4());receipt=runs.control(run,request,'resume');assert runs.control(run,request,'resume')==receipt
    runs.step(run);control(runs,run,'pause');assert runs.status(run)['completed_units']==1
    control(runs,run,'stop')
    with pytest.raises(DataError,match='RUN_TERMINAL'):control(runs,run,'resume')


def test_all_independent_units_finish_with_explicit_failed_dependencies(owned):
    storage,runs,run,created=setup(owned);control(runs,run,'resume')
    for _ in range(63):
        result=runs.step(run)
        if result['state']=='COMPLETED':break
    assert result['state']=='COMPLETED' and result['resolved_units']==63
    assert (result['completed_units'],result['failed_units'],result['skipped_units'])==(9,27,27)
    assert len(result['attempts'])==36 and result['financial_acceptance']=='UNVERIFIED'
    score=json.loads(runs.campaign_scorecard(run).content)
    assert score['counts']=={'completed':9,'failed':27,'pending':0} and score['shortlist']==[]
    assert runs.step(run)==result


def test_committed_fit_reused_without_refit_and_duplicate_acceptance_refused(owned,monkeypatch):
    storage,runs,run,created=setup(owned,True);control(runs,run,'resume')
    for _ in range(4):result=runs.step(run)
    fit=result['outcomes'][UNITS[3].key]
    assert fit['status']=='COMPLETED' and fit['payload_sha256']!=fit['artifact']['sha256']
    import compertum.modeling.checkpoints as module
    def forbidden(*a,**k):raise AssertionError('committed fit must never execute again')
    monkeypatch.setattr(module,'fit_ridge',forbidden)
    control(runs,run,'pause');control(runs,run,'resume');result=runs.step(run)
    evaluated=result['outcomes'][UNITS[4].key]
    assert evaluated['status']=='COMPLETED' and evaluated['dependency_sha256']==fit['payload_sha256']
    assert result['completed_units']==5
    with pytest.raises(DataError,match='RUN_NOT_RUNNING'):runs.accept(run,evaluated['artifact'])
    assert runs.status(run)['completed_units']==5


def test_orphan_output_is_not_a_committed_checkpoint(owned,monkeypatch):
    storage,runs,run,created=setup(owned);control(runs,run,'resume');original=storage.open_artifact
    def interrupted(*args):
        writer=original(*args);publish=writer.publish
        def crash():publish();raise OSError('sensitive text must not be persisted')
        monkeypatch.setattr(writer,'publish',crash);return writer
    monkeypatch.setattr(storage,'open_artifact',interrupted)
    with pytest.raises(DataError,match='RUN_INTERRUPTED'):runs.step(run)
    state=runs.status(run);assert state['resolved_units']==0
    path=next((storage.root/f'artifacts/runs/{run}/baseline').glob('unit-*.campaign'));old=path.read_bytes()
    monkeypatch.setattr(storage,'open_artifact',original);control(runs,run,'resume');result=runs.step(run)
    assert result['completed_units']==1 and len(result['attempts'])==2 and path.read_bytes()==old
    assert 'sensitive' not in json.dumps(result)


def test_two_transient_attempts_exhaust_only_affected_unit(owned,monkeypatch):
    import compertum.modeling.campaign as module
    storage,runs,run,created=setup(owned)
    def failure(*a,**k):raise OSError('sensitive diagnostic')
    monkeypatch.setattr(module,'compute_campaign_unit',failure)
    control(runs,run,'resume')
    with pytest.raises(DataError,match='RUN_INTERRUPTED'):runs.step(run)
    control(runs,run,'resume');result=runs.step(run)
    assert result['failed_units']==1 and result['state']=='READY' and len(result['attempts'])==2
    assert result['outcomes'][UNITS[0].key]['reason']=='TRANSIENT_ATTEMPTS_EXHAUSTED'


@pytest.mark.parametrize('case',['input','result','identity'])
def test_integrity_failure_blocks_before_new_attempt(owned,monkeypatch,case):
    import compertum.simulation.runs as module
    storage,runs,run,created=setup(owned);control(runs,run,'resume');result=runs.step(run)
    if case=='identity':
        identity=runtime_identity();identity['package_sha256']='0'*64;monkeypatch.setattr(module,'runtime_identity',lambda:identity)
    else:
        artifact=created['input_artifact'] if case=='input' else result['results'][0]['artifact']
        (storage.root/artifact['path']).write_bytes(b'corrupt')
    with pytest.raises(DataError):runs.step(run)
    summary=runs.summary(run);assert len(summary['attempts'])==1 and summary['completed_units']==1
    control(runs,run,'stop')


def test_output_reservation_budget_gate_does_not_consume_attempt(owned):
    storage,runs,run,created=setup(owned);small=str(uuid4());maximum=created['input_artifact']['size_bytes']+1024
    v=runs.create_campaign(small,campaign_folds(),maximum_bytes=maximum);control(runs,small,'resume')
    with pytest.raises(DataError,match='RUN_BUDGET'):runs.step(small)
    assert runs.summary(small)['attempts']==[] and runs.summary(small)['resolved_units']==0


def test_prepared_admission_cannot_switch_unit_or_dependency(owned):
    storage,runs,run,created=setup(owned);control(runs,run,'resume')
    prepared=runs.prepare_campaign(run);changed=dict(prepared,unit=3)
    with pytest.raises(DataError):runs.begin_campaign(run,changed)
    assert runs.summary(run)['attempts']==[]


def test_prepared_output_reservation_must_match_exact_attempt(owned):
    storage,runs,run,created=setup(owned);control(runs,run,'resume');prepared=runs.prepare_campaign(run)
    grant=storage.reserve_bytes(run,'records',16*1024**2);writer=storage.open_artifact(grant,prepared['output_path'])
    try:
        with pytest.raises(DataError):runs.begin_campaign(run,prepared,reservation_id=str(uuid4()))
        assert runs.summary(run)['attempts']==[]
        runs.begin_campaign(run,prepared,reservation_id=grant.grant_id)
        state=runs.summary(run);assert state['attempts'][0]['reservation_id']==grant.grant_id
        assert state['attempts'][0]['output_path']==prepared['output_path']
    finally:writer.close()


def test_history_reconstruction_detects_older_changed_entry(owned):
    from compertum.simulation.campaign_runs import history
    storage,runs,run,created=setup(owned)
    assert history(runs,run)==runs._load(run)
    with storage.store.conn:storage.store.conn.execute("UPDATE baseline_history SET body='{}' WHERE run_id=? AND seq=1",(run,))
    with pytest.raises(DataError,match='RUN_HISTORY_CORRUPT'):history(runs,run)


def test_integrity_failure_blocks_even_when_terminal_flag_is_set(owned):
    from compertum.simulation.campaign_runs import interrupt
    storage,runs,run,created=setup(owned);control(runs,run,'resume');runs.begin_campaign(run,runs.prepare_campaign(run))
    result=interrupt(runs,run,'UNIT_INTEGRITY_FAILURE',terminal=True)
    assert result['state']=='BLOCKED' and result['resolved_units']==0


def test_maximum_attempt_receipts_and_compact_controls_stay_bounded(owned):
    from dataclasses import asdict
    from compertum.data.encoding import canonical
    from compertum.simulation.campaign_runs import validate_receipt,validate_state,history
    storage,runs,run,created=setup(owned);state=runs._load(run)
    receipt=dict(pid=2**32-1,exit_code=5,timed_out=False,active_processes=0,assigned_before_resume=True,affinity=15,memory_limit=4*1024**3,peak_job_memory=4*1024**3,observed_child_pids=list(range(2**32-65,2**32-1)),observed_children_exited=True)
    validate_receipt(receipt)
    receipt['exit_code']=0
    for i,u in enumerate(UNITS):
        dependency=f'{u.fit_unit+1:064x}' if u.fit_unit is not None else None
        for n in (1,2):state['attempts'].append(dict(unit=i,identity=asdict(u),attempt=n,status='INTERRUPTED' if n==1 else 'COMPLETED',input_sha256=state['request_sha256'],dependency_sha256=dependency,output_path=f'artifacts/runs/{run}/baseline/unit-{i:02}-attempt-{n}.campaign',reservation_id=None,job_receipt=receipt))
        artifact=dict(artifact_id=str(uuid4()),path=state['attempts'][-1]['output_path'],task_id=run,size_bytes=100,sha256='f'*64)
        state['outcomes'][u.key]=dict(unit=i,identity=asdict(u),status='COMPLETED',artifact=artifact,payload_sha256=f'{i+1:064x}',dependency_sha256=dependency)
    state['state']='COMPLETED';validate_state(state)
    assert len(canonical(state))<512*1024 and len(state['attempts'])==126
    with storage.store.conn:runs._save(state,'BOUNDED_STATE_FIXTURE')
    assert history(runs,run)==runs._load(run)
    too_many=json.loads(canonical(state));too_many['attempts'].append(too_many['attempts'][-1])
    with pytest.raises(DataError):validate_state(too_many)
    with pytest.raises(DataError):validate_receipt(dict(receipt,unbounded_text='x'*2048))
    other=str(uuid4());runs.create_campaign(other,campaign_folds())
    for _ in range(128):control(runs,other,'pause')
    with pytest.raises(DataError,match='CONTROL_BOUND'):control(runs,other,'pause')
    size=storage.store.conn.execute('SELECT sum(length(receipt)) FROM baseline_controls WHERE run_id=?',(other,)).fetchone()[0]
    assert size<256*1024


@pytest.mark.parametrize('case',['status','path','input','failure'])
def test_outcome_and_dispatch_identity_must_agree(owned,case):
    from compertum.simulation.campaign_runs import validate_state
    storage,runs,run,created=setup(owned);control(runs,run,'resume');runs.step(run)
    state=runs._load(run);record=state['outcomes'][UNITS[0].key]
    if case=='status':state['attempts'][-1]['status']='FAILED'
    elif case=='path':record['artifact']['path']=record['artifact']['path'].replace('attempt-1','attempt-2')
    elif case=='input':state['attempts'][-1]['input_sha256']='0'*64
    else:record.update(status='FAILED',reason='WORKER_FAILED')
    with pytest.raises(DataError,match='RUN_STATE_CORRUPT'):validate_state(state)


@pytest.mark.parametrize('pause',[False,True])
def test_integrity_block_cannot_be_resumed_or_hidden_by_pause(owned,pause):
    from compertum.simulation.campaign_runs import interrupt
    storage,runs,run,created=setup(owned);control(runs,run,'resume');runs.begin_campaign(run,runs.prepare_campaign(run))
    interrupt(runs,run,'UNIT_INTEGRITY_FAILURE')
    if pause:control(runs,run,'pause')
    with pytest.raises(DataError,match='RUN_BLOCKED'):control(runs,run,'resume')
    assert runs.summary(run)['attempts'][-1]['reason']=='UNIT_INTEGRITY_FAILURE'


@pytest.mark.parametrize('reason',['LAUNCH_FAILED','HEALTH_HALT'])
def test_explicit_resource_resume_retains_attempt_and_allows_bounded_retry(owned,reason):
    storage,runs,run,created=setup(owned);control(runs,run,'resume');runs.begin_campaign(run,runs.prepare_campaign(run))
    runs.interrupt(run,reason)
    assert control(runs,run,'resume')['state']=='READY'
    prepared=runs.prepare_campaign(run);assert prepared['attempt']==2 and prepared['unit']==0
    runs.begin_campaign(run,prepared)
    assert len(runs.summary(run)['attempts'])==2
