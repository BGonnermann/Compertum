"""Native owner-backed saved runs; no worker service or external data."""
from uuid import uuid4
import hashlib,json
import pytest

from test_persistence import owned
from test_storage import manager
from helpers.simulation_fixture import fixture,SECTORS
from compertum.data.errors import DataError
from compertum.runtime.errors import RuntimeRefused
from compertum.runtime.owners import release_owner
from compertum.simulation import replay
from compertum.simulation.runs import SavedRuns


def setup_run(owned,maximum=32*1024*1024):
    storage=manager(owned);runs=SavedRuns(storage);run=str(uuid4())
    chunks,start,end,_=fixture(scored=3)
    created=runs.create(run,chunks,SECTORS,start,end,maximum_bytes=maximum)
    return storage,runs,run,(chunks,start,end),created


def control(runs,run,action):return runs.control(run,str(uuid4()),action)


def test_saved_run_pause_resume_and_exact_six_results(owned):
    storage,runs,run,args,created=setup_run(owned)
    assert created['state']=='PAUSED' and created['completed_units']==0
    with pytest.raises(DataError,match='RUN_NOT_READY'):runs.step(run)
    control(runs,run,'resume');first=runs.step(run)
    assert first['completed_units']==1
    control(runs,run,'pause');assert runs.status(run)['state']=='PAUSED'
    control(runs,run,'resume')
    for _ in range(5):runs.step(run)
    result=runs.status(run);assert result['state']=='COMPLETED' and result['completed_units']==6
    chunks,start,end=args
    for row in result['results']:
        expected=replay(chunks,SECTORS,start,end,row['horizon'],cost_bps=row['cost_bps'])
        assert (storage.root/row['artifact']['path']).read_bytes()==expected.content
    assert len(result['attempts'])==6
    assert runs.step(run)==result


def test_idempotent_create_controls_and_terminal_stop(owned):
    storage,runs,run,(chunks,start,end),created=setup_run(owned)
    assert runs.create(run,chunks,SECTORS,start,end,maximum_bytes=32*1024*1024)==created
    request=str(uuid4());a=runs.control(run,request,'resume')
    assert runs.control(run,request,'resume')==a
    with pytest.raises(DataError,match='CONTROL_CONFLICT'):runs.control(run,request,'pause')
    runs.step(run);stopped=control(runs,run,'stop')
    assert stopped['state']=='STOPPED' and runs.status(run)['completed_units']==1
    with pytest.raises(DataError,match='RUN_TERMINAL'):control(runs,run,'resume')
    with pytest.raises(DataError,match='RUN_NOT_READY'):runs.step(run)
    with pytest.raises(DataError,match='RUN_CONFLICT'):runs.create(run,chunks,SECTORS,start,end,maximum_bytes=64*1024*1024)


def test_corruption_and_changed_code_refuse_resume_but_allow_stop(owned,monkeypatch):
    storage,runs,run,args,created=setup_run(owned)
    path=storage.root/created['input_artifact']['path'];path.write_bytes(b'broken')
    with pytest.raises(DataError,match='RUN_ARTIFACT_CORRUPT'):control(runs,run,'resume')
    assert control(runs,run,'stop')['state']=='STOPPED'


def test_completed_result_corruption_is_not_success(owned):
    storage,runs,run,args,created=setup_run(owned)
    control(runs,run,'resume');done=runs.step(run)
    (storage.root/done['results'][0]['artifact']['path']).write_bytes(b'broken')
    with pytest.raises(DataError,match='RUN_ARTIFACT_CORRUPT'):runs.step(run)


def test_interrupted_publish_retry_preserves_orphan(owned,monkeypatch):
    storage,runs,run,args,created=setup_run(owned)
    control(runs,run,'resume');open_artifact=storage.open_artifact
    def interrupted(*args):
        writer=open_artifact(*args);publish=writer.publish
        def crash():
            publish();raise OSError('synthetic failure after durable publication')
        monkeypatch.setattr(writer,'publish',crash);return writer
    monkeypatch.setattr(storage,'open_artifact',interrupted)
    with pytest.raises(DataError,match='RUN_INTERRUPTED'):runs.step(run)
    state=runs.status(run)
    assert state['state']=='INTERRUPTED' and state['completed_units']==0
    orphan=next((storage.root/f'artifacts/runs/{run}/baseline').glob('unit-*.json'));old=orphan.read_bytes()
    monkeypatch.setattr(storage,'open_artifact',open_artifact)
    control(runs,run,'resume');new=runs.step(run)
    assert new['completed_units']==1 and len(new['attempts'])==2
    assert orphan.read_bytes()==old and new['results'][0]['artifact']['path']!=orphan.relative_to(storage.root).as_posix()


def test_released_owner_and_insufficient_budget_refused(owned):
    storage,runs,run,args,created=setup_run(owned)
    chunks,start,end=args
    with pytest.raises(DataError,match='RUN_BUDGET'):runs.create(str(uuid4()),chunks,SECTORS,start,end,maximum_bytes=1)
    release_owner(owned[1]['coordinator'])
    with pytest.raises(RuntimeRefused):runs.status(run)


def test_changed_runtime_identity_requires_new_run(owned,monkeypatch):
    import compertum.simulation.runs as module
    storage,runs,run,args,created=setup_run(owned);identity=module.runtime_identity()
    identity['package_sha256']='f'*64;monkeypatch.setattr(module,'runtime_identity',lambda:identity)
    with pytest.raises(DataError,match='RUN_IDENTITY_CHANGED'):control(runs,run,'resume')
    assert control(runs,run,'stop')['state']=='STOPPED'


def test_attempts_bounded_and_exception_text_never_persisted(owned,monkeypatch):
    import compertum.simulation.runs as module
    storage,runs,run,args,created=setup_run(owned)
    def failure(*args,**kwargs):raise OSError('synthetic-sensitive-message-must-not-be-saved')
    monkeypatch.setattr(module,'replay',failure)
    for _ in range(2):
        control(runs,run,'resume')
        with pytest.raises(DataError,match='RUN_INTERRUPTED'):runs.step(run)
    control(runs,run,'resume')
    with pytest.raises(DataError,match='RUN_ATTEMPT_BOUND'):runs.step(run)
    state=runs.status(run);assert len(state['attempts'])==2
    assert 'synthetic-sensitive' not in json.dumps(state)


@pytest.mark.parametrize('error',[DataError('MISSING_REFERENCE'),ValueError('synthetic-sensitive-message')])
def test_deterministic_failure_is_terminal(owned,monkeypatch,error):
    import compertum.simulation.runs as module
    storage,runs,run,args,created=setup_run(owned)
    def failure(*args,**kwargs):raise error
    monkeypatch.setattr(module,'replay',failure)
    control(runs,run,'resume')
    with pytest.raises(DataError,match='RUN_FAILED'):runs.step(run)
    state=runs.status(run)
    assert state['state']=='FAILED' and len(state['attempts'])==1 and state['completed_units']==0
    assert state['attempts'][0]['status']=='FAILED'
    assert 'synthetic-sensitive' not in json.dumps(state)
    with pytest.raises(DataError,match='RUN_TERMINAL'):control(runs,run,'resume')


def test_aggregate_budget_counts_saved_inputs(owned):
    storage,runs,run,(chunks,start,end),created=setup_run(owned)
    small=str(uuid4());maximum=created['input_artifact']['size_bytes']+32
    runs.create(small,chunks,SECTORS,start,end,maximum_bytes=maximum)
    control(runs,small,'resume')
    with pytest.raises(DataError,match='RUN_FAILED'):runs.step(small)
    state=runs.status(small)
    assert state['attempts'][-1]['reason']=='RUN_BUDGET' and state['completed_units']==0
    assert sum(r['written'] for r in storage.reservations() if r['task']==small)<=maximum


def test_oversized_input_corruption_checked_before_read(owned,monkeypatch):
    from pathlib import Path
    storage,runs,run,args,created=setup_run(owned)
    path=storage.root/created['input_artifact']['path'];size=created['input_artifact']['size_bytes']
    with path.open('ab') as f:f.write(b'corrupt')
    original=Path.open
    class Reader:
        def __init__(self,stream):self.stream=stream
        def __enter__(self):return self
        def __exit__(self,*args):self.stream.close()
        def fileno(self):return self.stream.fileno()
        def read(self,*args):pytest.fail('oversized corrupted file was read')
    def guarded(p,*args,**kwargs):
        stream=original(p,*args,**kwargs)
        return Reader(stream) if p==path and args==('rb',) else stream
    monkeypatch.setattr(Path,'open',guarded)
    with pytest.raises(DataError,match='RUN_ARTIFACT_CORRUPT'):control(runs,run,'resume')


def test_restart_does_not_bless_corrupt_checkpoint(owned):
    storage,runs,run,args,created=setup_run(owned)
    state=json.loads(storage.store.conn.execute('SELECT body FROM baseline_runs WHERE run_id=?',(run,)).fetchone()[0])
    state.update(state='RUNNING',active_owner='different-owner')
    with storage.store.conn:storage.store.conn.execute('UPDATE baseline_runs SET body=? WHERE run_id=?',(json.dumps(state),run))
    before=storage.store.conn.execute('SELECT body FROM baseline_runs WHERE run_id=?',(run,)).fetchone()[0]
    with pytest.raises(DataError,match='RUN_STATE_CORRUPT'):SavedRuns(storage)
    assert storage.store.conn.execute('SELECT body FROM baseline_runs WHERE run_id=?',(run,)).fetchone()[0]==before


def test_abandoned_reservations_keep_full_budget_charge(owned):
    storage,runs,run,(chunks,start,end),created=setup_run(owned)
    size=len(replay(chunks,SECTORS,start,end,1).content)
    small=str(uuid4());maximum=created['input_artifact']['size_bytes']+size+512
    runs.create(small,chunks,SECTORS,start,end,maximum_bytes=maximum)
    grant=storage.reserve_bytes(small,'records',1024)
    writer=storage.open_artifact(grant,f'artifacts/runs/{small}/baseline/abandoned.bin')
    writer.write(b'x');writer.close()
    control(runs,small,'resume')
    with pytest.raises(DataError,match='RUN_FAILED'):runs.step(small)
    assert runs.status(small)['attempts'][-1]['reason']=='RUN_BUDGET'
