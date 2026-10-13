"""Saved snapshot contracts with simulated native identities; no native acceptance."""
from copy import deepcopy
from contextlib import contextmanager
import json,sqlite3
from types import SimpleNamespace
from uuid import uuid4
import pytest
from test_final_audit_runs import owner,saved,environment,prepare,bound,receipt,report
from compertum.data.encoding import canonical
from compertum.data.errors import DataError
from compertum.runtime.errors import RuntimeRefused
from compertum.review_evidence import sha
from compertum import final_audit_recovery as m

REFUSED=(DataError,RuntimeRefused)


def finish(o,mode='COMPLETED'):
 p,t,w,n=bound(o);o.runs.record_exit(o.task,receipt(n,0 if mode=='COMPLETED' else 125))
 if mode=='COMPLETED':w.write(report(o,p,n));o.runs.accept(o.task,w.publish())
 else:o.runs.interrupt(o.task,'OPERATOR_PAUSE');w.close()
 return p,t,w,n


def lineage(o):
 return dict(artifacts=[{k:a[k] for k in ('artifact_id','path','size_bytes','sha256')}|{'parent_artifact_ids':[]} for (raw,) in o.db.execute("SELECT manifest FROM reservations WHERE status='PUBLISHED'") for a in [json.loads(raw)]])


def clone(db):
 db.commit();result=sqlite3.connect(':memory:');db.backup(result);return result


def copy_current(o,db=None):
 from compertum.persistence import STORE_NAMES
 db=o.db if db is None else db
 pid=o.saved.row['final']['plan']['project_id'];root=o.storage.root
 db.execute('CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY,value TEXT)')
 db.executemany('INSERT OR REPLACE INTO metadata VALUES(?,?)',[('schema_version','1'),('project_id',pid),('role','coordinator')]);db.commit()
 path=root/'state'/STORE_NAMES['coordinator'];path.parent.mkdir(parents=True,exist_ok=True)
 with sqlite3.connect(path) as out:db.backup(out)
 return SimpleNamespace(project_id=pid,root_path=root)


@pytest.mark.parametrize('state',['READY','INTERRUPTED','COMPLETED'])
def test_snapshot_and_artifact_roundtrip(owner,state):
 o=owner
 if state!='READY':finish(o,state)
 before=m.closed(m.snapshot(o.db));c=clone(o.db)
 try:assert m.closed(m.snapshot(c))==before;m.verify_artifacts(c,lineage(o),o.storage.root)
 finally:c.close()
 assert before[o.task]['state']['state']==state


@pytest.mark.parametrize('fault',['missing_table','orphan_history','missing_history','key','body','history_hash','row_limit'])
def test_malformed_snapshot_is_refused(owner,fault):
 o=owner
 if fault=='missing_table':o.db.execute('DROP TABLE final_audit_history')
 elif fault=='orphan_history':o.db.execute('UPDATE final_audit_history SET task_id=?',(str(uuid4()),))
 elif fault=='missing_history':o.db.execute('DELETE FROM final_audit_history')
 elif fault=='key':o.db.execute("UPDATE final_audit_runs SET audit_key=?",('0'*64,))
 elif fault=='body':o.db.execute("UPDATE final_audit_runs SET body=?",(' '*24577,))
 elif fault=='history_hash':o.db.execute("UPDATE final_audit_history SET sha256=?",('0'*64,))
 else:
  row=o.db.execute('SELECT * FROM final_audit_history').fetchone()
  o.db.executemany('INSERT INTO final_audit_history VALUES(?,?,?,?,?)',[(row[0],n,*row[2:]) for n in range(2,34)])
 with pytest.raises(REFUSED):m.snapshot(o.db)


@pytest.mark.parametrize('bound_child',[False,True])
def test_unknown_exit_blocks_checkpoint_snapshot(owner,bound_child):
 (bound if bound_child else prepare)(owner)
 with pytest.raises(RuntimeRefused,match='FINAL_AUDIT_RECOVERY_UNVERIFIED'):m.closed(m.snapshot(owner.db))


@pytest.mark.parametrize('fault',['request','task','manifest','output','original_frame','request_bytes','output_bytes','output_cap','original_cap','original_exit','original_closure','original_dispatch'])
def test_missing_or_changed_publication_is_refused(owner,fault):
 o=owner;p,t,w,n=finish(o);s=o.runs.status(o.task)
 by_name=dict(request=p['request_artifact'],task=s['attempts'][0]['task_artifact'],manifest=s['manifest'],output=s['artifact'],original_frame=o.saved.frame)
 if fault in by_name:o.db.execute('UPDATE reservations SET status=? WHERE path=?',('ABANDONED',by_name[fault]['path']))
 elif fault in ('request_bytes','output_bytes'):
  a=by_name['request' if fault=='request_bytes' else 'output'];path=o.storage.root/a['path'];raw=path.read_bytes();path.write_bytes(raw[:-1]+b'!')
 elif fault in ('output_cap','original_cap'):
  a=by_name['output' if fault=='output_cap' else 'original_frame'];o.db.execute('UPDATE reservations SET maximum=maximum+1 WHERE path=?',(a['path'],))
 else:o.db.execute('DELETE FROM '+{'original_exit':'final_exits','original_closure':'final_closures','original_dispatch':'final_dispatches'}[fault])
 with pytest.raises(REFUSED):m.verify_artifacts(o.db,lineage(o),o.storage.root)


def test_backup_blobs_close_all_audit_artifacts(owner):
 o=owner;finish(o);items=lineage(o);supplied={}
 for a in items['artifacts']:
  path='backups/test/blobs/'+a['artifact_id']+'.bin';dest=o.storage.root/path;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes((o.storage.root/a['path']).read_bytes());supplied[a['artifact_id']]=dict(a,path=path)
 m.verify_artifacts(o.db,items,o.storage.root,supplied)
 s=o.runs.status(o.task);(o.storage.root/s['artifact']['path']).write_bytes(b'original changed')
 m.verify_artifacts(o.db,items,o.storage.root,supplied)
 supplied.pop(s['attempts'][0]['request_artifact']['artifact_id'])
 with pytest.raises(RuntimeRefused):m.verify_artifacts(o.db,items,o.storage.root,supplied)


def test_bound_auditor_cannot_be_original_process_after_restore(owner):
 o=owner;finish(o,'INTERRUPTED');author=o.saved.dispatch['attempt']['native_execution']['process'];previous=None
 rows=o.db.execute('SELECT seq,body FROM final_audit_history ORDER BY seq').fetchall()
 for seq,raw in rows:
  v=json.loads(raw)
  for a in v['attempts']:
   n=a['native_execution']
   if n is not None:
    n['process'].update(pid=author['pid'],creation_filetime=author['creation_filetime'])
    if a['job_receipt'] is not None:a['job_receipt'].update(pid=author['pid'],execution_identity=deepcopy(n))
  body=canonical(v);pin=sha(body);o.db.execute('UPDATE final_audit_history SET body=?,sha256=?,previous_sha256=? WHERE seq=?',(body.decode(),pin,previous,seq));previous=pin
 o.db.execute('UPDATE final_audit_runs SET body=?',(body.decode(),))
 assert m.closed(m.snapshot(o.db))[o.task]['state']['state']=='INTERRUPTED'
 with pytest.raises(DataError):o.runs.current(o.runs.status(o.task))
 with pytest.raises(RuntimeRefused,match='FINAL_AUDIT_RECOVERY_UNVERIFIED'):m.verify_artifacts(o.db,lineage(o),o.storage.root)


@pytest.mark.parametrize('candidate_stage',['absent','registered','one_attempt','current'])
def test_restore_cannot_roll_back_retained_attempts(owner,candidate_stage):
 o=owner
 if candidate_stage=='absent':candidate=sqlite3.connect(':memory:')
 elif candidate_stage=='registered':candidate=clone(o.db)
 finish(o,'INTERRUPTED')
 if candidate_stage=='one_attempt':candidate=clone(o.db)
 o.runs.resume(o.task);finish(o)
 if candidate_stage=='current':candidate=clone(o.db)
 project=copy_current(o)
 try:
  if candidate_stage=='current':m.require_preserved(project,candidate)
  else:
   with pytest.raises(RuntimeRefused,match='FINAL_AUDIT_RECOVERY_UNVERIFIED'):m.require_preserved(project,candidate)
 finally:candidate.close()


def test_closed_audit_tables_join_generic_lineage(owner):
 from compertum.recovery_lineage import extend_lineage
 o=owner;finish(o);o.db.execute('DELETE FROM baseline_runs')
 e=sqlite3.connect(':memory:');e.execute('CREATE TABLE consumption(seal_id,evaluation_id,body)')
 try:result=extend_lineage(o.db,e,o.saved.row['final']['plan']['project_id'],'0'*64,dict(artifacts=[],task_states=[],run_states=[],checkpoints=[]))
 finally:e.close()
 assert result['task_states']==[dict(task_id=o.task,state='COMPLETED',checkpoint_id=None)]
 assert {a['artifact_id'] for a in result['artifacts']}=={a['artifact_id'] for a in lineage(o)['artifacts']}
 m.verify_artifacts(o.db,result,o.storage.root)


@pytest.mark.parametrize('older',[True,False])
def test_interrupted_restore_does_not_publish_rolled_back_audit(owner,monkeypatch,older):
 from compertum import recovery as r,evaluation_seals,fake_attempt_guard,fake_recovery,fake_economic_opening
 from compertum.persistence import STORE_NAMES
 o=owner;candidate=clone(o.db) if older else None;finish(o,'INTERRUPTED');project=copy_current(o)
 if candidate is None:candidate=clone(o.db)
 # Snapshot metadata is authenticated by require_preserved for the retained current store.
 generation=str(uuid4());operation=str(uuid4());target=project.root_path/'state/generations'/generation;target.mkdir(parents=True)
 for role,name in STORE_NAMES.items():
  with sqlite3.connect(target/name) as out:
   if role=='coordinator':candidate.backup(out)
   else:out.execute('CREATE TABLE test(value)')
 candidate.close();pointer=dict(schema_version=1,project_id=project.project_id,generation=generation,operation_id=operation)
 state=project.root_path/'state';(state/'active-generation.json').write_bytes(canonical(pointer))
 attempts=dict(status='VERIFIED',sequence=0,sha256='a'*64);opening=dict(status='VERIFIED')
 record=dict(operation_id=operation,status='READY',generation=generation,prior_active=None,staged_sha256={name:r._hash(target/name) for name in STORE_NAMES.values()},guard_sha256='b'*64,seal_sha256='c'*64,fake_attempt_guard={k:attempts[k] for k in ('sequence','sha256')},fake_economic_opening=opening)
 (state/'restore-operation.json').write_bytes(canonical(record))
 @contextmanager
 def scope(lease):yield SimpleNamespace(api=SimpleNamespace(publish_metadata=lambda path,raw:path.write_bytes(raw)))
 monkeypatch.setattr(r,'acquire_owner',lambda *a:object());monkeypatch.setattr(r,'release_owner',lambda *a:None);monkeypatch.setattr(r,'_owner_scope',scope)
 monkeypatch.setattr(r,'verify_consumption_guard',lambda *a:dict(status='VERIFIED',sha256='b'*64))
 monkeypatch.setattr(evaluation_seals,'verify_seal_journal',lambda *a:dict(status='VERIFIED',sha256='c'*64))
 monkeypatch.setattr(fake_attempt_guard,'verify_attempt_guard',lambda *a:attempts)
 monkeypatch.setattr(fake_recovery,'preserved_attempt_evidence',lambda *a:True)
 monkeypatch.setattr(fake_economic_opening,'verify_opening',lambda *a:opening)
 result=r.recover_interrupted_restore(project)
 assert result['status']==('ABORTED' if older else 'PUBLISHED')
 assert (state/'active-generation.json').exists() is (not older)
 if older:assert json.loads((state/f'aborted-pointer-{operation}.json').read_bytes())==pointer
