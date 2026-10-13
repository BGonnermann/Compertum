"""Native owner/pinning and audit checks without worker admission."""
from uuid import uuid4
import pytest
from test_persistence import owned
from test_saved_campaigns import setup,control
from test_campaign_job import controller_for
from compertum.audit_campaign import reconstruct_history
from compertum.data.encoding import canonical
from compertum.data.errors import DataError
from compertum.simulation.campaign_verification import _Verification


def audit(controller,run):
    state=controller.runs._load(run);db=controller.store.conn
    history=[dict(seq=n,body=b,sha256=h) for n,b,h in db.execute('SELECT seq,body,sha256 FROM baseline_history WHERE run_id=? ORDER BY seq',(run,))]
    controls=[dict(request_id=r,action=a,receipt=c) for r,a,c in db.execute('SELECT request_id,action,receipt FROM baseline_controls WHERE run_id=?',(run,))]
    restored,report=reconstruct_history(canonical(state),history,controls)
    assert restored==state
    return report


@pytest.mark.parametrize('end',['finish','cancel','refuse'])
def test_pending_resume_preserves_history_contract(owned,monkeypatch,end):
    storage,runs,run,_=setup(owned);controller=controller_for(storage);controller.cooperative=True
    request=str(uuid4());reply=controller.control(run,request,'resume')
    assert reply['state']=='PAUSED' and reply['pending_operation']['operation']=='resume'
    assert controller.control(run,request,'resume')==reply
    assert audit(controller,run)['controls']==0
    if end=='cancel':controller.control(run,str(uuid4()),'pause')
    elif end=='refuse':
        def denied():raise DataError('RUN_IDENTITY_CHANGED')
        monkeypatch.setattr(controller.pending.proof,'_constraints',denied)
        controller.tick()
    else:
        for _ in range(5):controller.tick()
    assert controller.pending is None and controller.active is None
    report=audit(controller,run)
    assert report['controls']==(0 if end=='refuse' else 1)
    assert controller.runs.summary(run)['attempts']==[]
    if end=='refuse':assert controller.last_operation_error['reason']=='RUN_IDENTITY_CHANGED'
    elif end=='finish':assert controller.control(run,request,'resume')['state']=='READY'


def test_pending_proof_blocks_file_write_and_rename_then_releases(owned):
    storage,runs,run,created=setup(owned);proof=_Verification(runs,run)
    path=storage.root/created['input_artifact']['path'];raw=path.read_bytes()
    try:
        assert proof.advance() is False
        with pytest.raises(OSError):
            with path.open('r+b'):pass
        with pytest.raises(OSError):path.rename(path.with_suffix('.renamed'))
    finally:proof.close()
    with path.open('r+b') as handle:assert handle.read()==raw
    assert proof.state is None and proof.records==[] and proof.runs is None and proof.handles==[]


def test_proof_refuses_artifact_changed_before_its_phase(owned):
    storage,runs,run,_=setup(owned);control(runs,run,'resume');runs.step(run)
    proof=_Verification(runs,run)
    try:
        assert not proof.advance()
        outcome=next(iter(runs._load(run)['outcomes'].values()));path=storage.root/outcome['artifact']['path']
        raw=path.read_bytes();path.write_bytes(raw[:-1]+bytes([raw[-1]^1]))
        with pytest.raises(DataError,match='RUN_ARTIFACT_CORRUPT'):proof.advance()
    finally:proof.close()


def test_proof_refuses_current_history_change(owned):
    storage,runs,run,_=setup(owned);proof=_Verification(runs,run)
    try:
        assert not proof.advance();control(runs,run,'stop')
        with pytest.raises(DataError,match='CAMPAIGN_ADMISSION_CHANGED'):proof.advance()
    finally:proof.close()


def test_repeated_closed_proofs_do_not_retain_campaign_snapshots(owned):
    storage,runs,run,_=setup(owned);control(runs,run,'resume')
    for _ in range(3):runs.step(run)
    retained=[]
    for _ in range(12):
        proof=_Verification(runs,run)
        while not proof.advance():pass
        assert proof.check(runs,runs._load(run))
        proof.close();retained.append(proof)
    assert all(p.closed and p.state is None and p.runs is None and not p.records and p.bundle is None and p.previous is None and not p.handles for p in retained)
    assert runs.summary(run)['completed_units']==3


def test_owner_restart_discards_uncommitted_pending_resume(tmp_path):
    import json,os,subprocess,sys
    from pathlib import Path
    from compertum.runtime.identity import resolve_project
    from compertum.runtime.owners import acquire_owner,release_owner
    from test_storage import manager
    env={k:v for k,v in os.environ.items() if k.upper() in {'SYSTEMROOT','WINDIR','PATH','PYTHONPATH','TEMP','TMP','OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'}}
    env.update(PYTHONDONTWRITEBYTECODE='1',PYTHONNOUSERSITE='1')
    child=subprocess.run([sys.executable,'-B',str(Path(__file__).resolve().parents[1]/'helpers/pending_campaign_owner.py'),str(tmp_path)],env=env,capture_output=True,text=True,timeout=20)
    assert child.returncode==0,child.stderr
    result=json.loads(child.stdout);assert result['pid']!=os.getpid() and result['proof_closed']
    project=resolve_project(tmp_path);lease=acquire_owner(project,'coordinator');run=result['run_id']
    try:
        fresh=controller_for(manager((project,{'coordinator':lease})));fresh.cooperative=True
        assert fresh.pending is None and fresh.active is None and fresh.runs.summary(run)['state']=='PAUSED'
        assert fresh.runs.summary(run)['attempts']==[] and audit(fresh,run)['controls']==0
        fresh.tick();assert fresh.runs.summary(run)['attempts']==[]
    finally:release_owner(lease)
