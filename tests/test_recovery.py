import json,subprocess,sys,sqlite3
import pytest
from compertum.domain import ContractError,file_hash,atomic_json
from compertum.runtime.identity import resolve_project
from compertum.runtime.owners import acquire_owner
from compertum.recovery import validate_recovery_set,restore_recovery_set,restore_admission,abort_incomplete_restore

SETUP='''
import sys,json
from pathlib import Path
from compertum.runtime.identity import resolve_project
from compertum.runtime.owners import acquire_owner
from compertum.persistence import open_store
from compertum.consumption import create_guard,consume_once
from compertum.recovery import collect_recovery_set
from compertum.storage import StorageManager
from compertum.domain import file_hash
p=resolve_project(Path(sys.argv[1]));ls=[acquire_owner(p,r) for r in ('coordinator','evaluation','execution')];ss=[open_store(l,l.role) for l in ls]
create_guard(ls[1]);ss[1].db.execute("INSERT INTO seals VALUES('synthetic-SEAL_A','UNUSED',NULL)");ss[1].db.execute("INSERT INTO seals VALUES('synthetic-SEAL_OTHER','UNUSED',NULL)")
artifact=p.root_path/'artifacts/fixture.json';artifact.parent.mkdir();artifact.write_text('{"answer":14}')
ss[0].commit_event({'event_id':'artifact','kind':'ARTIFACT_REGISTERED','payload':{'path':'artifacts/fixture.json','sha256':file_hash(artifact)}})
event={'event_id':'ack','kind':'TASK_STATUS','payload':{'status':'DONE'}}
ss[0].commit_event(event);ss[1].accept_message(event);ss[0].acknowledge('ack')
ss[0].commit_event({'event_id':'pending','kind':'TASK_STATUS','payload':{'status':'WAITING'}})
ss[2].commit_event({'event_id':'side','kind':'BROKER_SIDE_EFFECT','payload':{'synthetic':True}})
ss[0].set('arms',True);ss[0].set('approved_plans',{'synthetic':True})
manager=StorageManager(ss[0]);a=collect_recovery_set(p,ss,manager)
consume_once(ls[1],'synthetic-SEAL_A','EVAL_A',{'fixture':True});b=collect_recovery_set(p,ss,manager)
(p.root_path/'indexes.json').write_text(json.dumps({'a':a['recovery_id'],'b':b['recovery_id']}))
for s in ss:s.close()
for l in ls:l.close()
'''

@pytest.fixture
def recovery_root(tmp_path):
    result=subprocess.run([sys.executable,'-B','-c',SETUP,str(tmp_path)],capture_output=True,text=True,timeout=50)
    assert result.returncode==0,result.stderr
    p=resolve_project(tmp_path);ids=json.loads((tmp_path/'indexes.json').read_text())
    return p,tmp_path/'backups'/ids['a']/'manifest.json'

def test_old_backup_sticky_consumption_and_missing_guard(recovery_root):
    p,path=recovery_root
    with acquire_owner(p,'recovery') as lease:
        receipt=restore_recovery_set(lease,path)
        db=sqlite3.connect(p.root_path/receipt['path']/'evaluation.sqlite')
        assert db.execute("SELECT status,evaluation_id FROM seals WHERE seal_id='synthetic-SEAL_A'").fetchone()==('CONSUMED','EVAL_A');db.close()
        assert receipt['restored_unconsumed_seals']=='EVALUATION_COMPROMISED'
        (p.root_path/'state/evaluation-consumption/head.json').rename(p.root_path/'state/evaluation-consumption/head.missing')
        second=restore_recovery_set(lease,path)
        db=sqlite3.connect(p.root_path/second['path']/'evaluation.sqlite')
        assert db.execute("SELECT status FROM seals WHERE seal_id='synthetic-SEAL_A'").fetchone()[0]=='CONSUMED'
        assert db.execute("SELECT status FROM seals WHERE seal_id='synthetic-SEAL_OTHER'").fetchone()[0]=='EVALUATION_COMPROMISED';db.close()
        assert restore_admission(p.root_path)

def test_valid_old_guard_cannot_unconsume_surviving_evidence(recovery_root):
    p,path=recovery_root;directory=p.root_path/'state/evaluation-consumption'
    for event in directory.glob('event-*.json'):event.rename(event.with_suffix('.retained'))
    atomic_json(directory/'head.json',{'project_id':p.project_id,'sequence':0,'sha256':'0'*64})
    with acquire_owner(p,'recovery') as lease:r=restore_recovery_set(lease,path)
    assert r['consumption']=='EVALUATION_COMPROMISED'
    check='''
import sys
from pathlib import Path
from compertum.runtime.identity import resolve_project
from compertum.runtime.owners import acquire_owner
from compertum.persistence import open_store
from compertum.consumption import consume_once
from compertum.domain import ContractError
p=resolve_project(Path(sys.argv[1]))
with acquire_owner(p,'evaluation') as l:
 s=open_store(l,'evaluation');assert s.db.execute("SELECT status FROM seals WHERE seal_id='synthetic-SEAL_A'").fetchone()[0]=='CONSUMED';s.close()
 try:consume_once(l,'synthetic-SEAL_A','NEW_EVAL',{'fixture':True})
 except ContractError:pass
 else:raise AssertionError('restored evaluation reopened')
'''
    out=subprocess.run([sys.executable,'-B','-c',check,str(p.root_path)],capture_output=True,text=True,timeout=10);assert out.returncode==0,out.stderr

def test_corrupt_closure_and_interrupted_restore(recovery_root):
    p,path=recovery_root;m=validate_recovery_set(p,path)
    with acquire_owner(p,'recovery') as lease:
        with pytest.raises(ContractError,match='INTERRUPTION'):restore_recovery_set(lease,path,fail_after=0)
        assert not restore_admission(p.root_path)
        assert abort_incomplete_restore(lease)['state']=='ABORTED' and restore_admission(p.root_path)
        ref=m['artifacts'][0];(p.root_path/ref['path']).write_text('corrupt')
        with pytest.raises(ContractError,match='HASH'):validate_recovery_set(p,path)

def test_restore_invalidates_arms_and_retains_nonreplayable(recovery_root):
    p,path=recovery_root;m=validate_recovery_set(p,path)
    assert {x['event_id'] for x in m['pending_messages']}=={'artifact','pending','side'}
    with acquire_owner(p,'recovery') as lease:r=restore_recovery_set(lease,path)
    db=sqlite3.connect(p.root_path/r['path']/'research.sqlite')
    assert json.loads(db.execute("SELECT value FROM kv WHERE key='arms'").fetchone()[0]) is False
    assert json.loads(db.execute("SELECT value FROM kv WHERE key='approved_plans'").fetchone()[0]) is None
    db.close();assert r['side_effect_replay'] is False

def test_missing_or_corrupt_active_database_cannot_reset_history(recovery_root):
    p,path=recovery_root
    with acquire_owner(p,'recovery') as lease:r=restore_recovery_set(lease,path)
    database=p.root_path/r['path']/'evaluation.sqlite';database.rename(database.with_suffix('.retained'))
    script='''
import sys
from pathlib import Path
from compertum.runtime.identity import resolve_project
from compertum.runtime.owners import acquire_owner
from compertum.persistence import open_store
from compertum.domain import ContractError
with acquire_owner(resolve_project(Path(sys.argv[1])),'evaluation') as l:
 try:open_store(l,'evaluation')
 except ContractError:pass
 else:raise AssertionError('empty restored history created')
'''
    for contents in [None,b'not a sqlite database']:
        if contents is not None:database.write_bytes(contents)
        outcome=subprocess.run([sys.executable,'-B','-c',script,str(p.root_path)],capture_output=True,text=True,timeout=10);assert outcome.returncode==0,outcome.stderr
        if contents is None:assert not database.exists()

def test_scaled_restore_budget_exhaustion_before_any_staging(recovery_root,monkeypatch):
    from compertum.storage import CAPS,sample_storage
    p,path=recovery_root
    with acquire_owner(p,'recovery') as lease:
        actual=sample_storage(p.root_path)['used']['records'];monkeypatch.setitem(CAPS,'records',actual+100)
        with pytest.raises(ContractError,match='RESTORE_STORAGE_LIMIT'):restore_recovery_set(lease,path)
        assert not (p.root_path/'state/restores').exists() and not (p.root_path/'state/restore-operation.json').exists()
