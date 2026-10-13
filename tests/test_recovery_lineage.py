"""Small snapshot contracts; no native campaign or large recovery reserve."""
import sqlite3,json,hashlib
from uuid import uuid4
from copy import deepcopy
import pytest
from compertum.data.encoding import canonical
from compertum.recovery_lineage import extend_lineage,snapshot_seals,verify_boundary
from compertum.runtime.errors import RuntimeRefused


def setup():
 c=sqlite3.connect(':memory:');e=sqlite3.connect(':memory:')
 c.execute('CREATE TABLE reservations(task,path,manifest,category,status,id)');c.execute('CREATE TABLE baseline_runs(run_id,body)');e.execute('CREATE TABLE consumption(seal_id,evaluation_id,body)')
 c.execute('CREATE TABLE baseline_history(run_id,seq,body,sha256)')
 task=str(uuid4());a=dict(artifact_id=str(uuid4()),task_id=task,path=f'artifacts/runs/{task}/baseline/inputs.json',size_bytes=12,sha256='a'*64)
 c.execute('INSERT INTO reservations VALUES(?,?,?,?,?,?)',(task,a['path'],canonical(a).decode(),'records','PUBLISHED',str(uuid4())))
 raw=canonical(dict(run_id=task,state='COMPLETED',input_artifact=a)).decode()
 c.execute('INSERT INTO baseline_runs VALUES(?,?)',(task,raw));c.execute('INSERT INTO baseline_history VALUES(?,?,?,?)',(task,1,raw,hashlib.sha256(raw.encode()).hexdigest()))
 return c,e,a


def collect(c,e):return extend_lineage(c,e,'a'*64,'b'*64,dict(task_states=[],run_states=[],checkpoints=[],artifacts=[]))


def test_published_campaign_and_orphan_output_retained():
 c,e,a=setup();orphan={**a,'artifact_id':str(uuid4()),'path':a['path']+'.retained'}
 c.execute('INSERT INTO reservations VALUES(?,?,?,?,?,?)',(a['task_id'],orphan['path'],canonical(orphan).decode(),'records','PUBLISHED',str(uuid4())))
 result=collect(c,e)
 assert {r['artifact_id'] for r in result['artifacts']}=={a['artifact_id'],orphan['artifact_id']}
 assert result['task_states']==[dict(task_id=a['task_id'],state='COMPLETED',checkpoint_id=None)]


@pytest.mark.parametrize('fault',['missing','different_hash','oversized_manifest','oversized_state','boolean_size','duplicate_path'])
def test_incomplete_or_unbounded_ledger_is_refused(fault):
 c,e,a=setup()
 if fault=='missing':c.execute('DELETE FROM reservations')
 elif fault=='different_hash':a['sha256']='f'*64;c.execute('UPDATE reservations SET manifest=?',(canonical(a).decode(),))
 elif fault=='oversized_manifest':c.execute('UPDATE reservations SET manifest=?',(' '*5000,))
 elif fault=='oversized_state':c.execute('UPDATE baseline_runs SET body=?',(' '*600000,))
 elif fault=='boolean_size':a['size_bytes']=True;c.execute('UPDATE reservations SET manifest=?',(canonical(a).decode(),))
 else:c.execute('INSERT INTO reservations SELECT task,path,manifest,category,status,? FROM reservations',(str(uuid4()),))
 with pytest.raises(RuntimeRefused):collect(c,e)


def test_empty_snapshot_boundary_is_exact():
 c,e,a=setup();m=dict(seal_journal=dict(sequence=0,sha256='0'*64),consumption_order=[],consumption_guard=dict(sequence=0,sha256='0'*64,head_event_id=None))
 assert verify_boundary(e,'a'*64,m)[0]['sequence']==0
 m['seal_journal']['sha256']='f'*64
 with pytest.raises(RuntimeRefused):verify_boundary(e,'a'*64,m)


def test_seal_checkpoint_cannot_reference_another_task():
 from test_contracts import complete_recovery
 from compertum.domain import _recovery_rules,ContractError
 p=complete_recovery();p['consumption_guard']=dict(sequence=1,sha256='a'*64,head_event_id=str(uuid4()));p['seals']=[dict(seal_id=str(uuid4()),evaluation_id=str(uuid4()),consumption_state='CONSUMED',checkpoint_id=p['checkpoints'][0]['checkpoint_id'])]
 with pytest.raises(ContractError):_recovery_rules(p)


def test_partial_artifact_cannot_hide_a_missing_dependency():
 c,e,a=setup();a.pop('sha256');c.execute('DELETE FROM reservations');c.execute('UPDATE baseline_runs SET body=?',(canonical(dict(run_id=a['task_id'],state='COMPLETED',input_artifact=a)).decode(),))
 with pytest.raises(RuntimeRefused):collect(c,e)


@pytest.mark.parametrize('fault',[None,'missing','native_changed','hash_changed','wrong_seal','malformed'])
def test_newer_start_requires_original_dispatch_in_restored_snapshot(fault):
 from test_final_attempts import context,start,apply,SID
 from compertum.recovery_lineage import validate_dispatch_links
 s=context();apply(s,start(s));a=s[SID]['final_attempts'][0]['start']['attempt'];db=sqlite3.connect(':memory:');db.execute('CREATE TABLE final_dispatches(seal_id,attempt_id,body,sha256)')
 d=dict(schema='synthetic-final-dispatch-v1',seal_id=SID,attempt=deepcopy(a),request_artifact=dict(artifact_id=str(uuid4()),task_id=a['evaluation_id'],path=f"artifacts/runs/{a['evaluation_id']}/input/request.json",size_bytes=12,sha256='a'*64),task_artifact=dict(artifact_id=str(uuid4()),task_id=a['evaluation_id'],path=f"artifacts/runs/{a['evaluation_id']}/input/task.json",size_bytes=12,sha256=a['task_sha256']))
 if fault=='native_changed':d['attempt']['native_execution']['process']['pid']+=1
 elif fault=='wrong_seal':d['seal_id']=str(uuid4())
 elif fault=='malformed':d.pop('request_artifact')
 raw=canonical(d);pin=hashlib.sha256(raw).hexdigest()
 if fault=='hash_changed':pin='f'*64
 if fault!='missing':db.execute('INSERT INTO final_dispatches VALUES(?,?,?,?)',(SID,a['attempt_id'],raw.decode(),pin))
 if fault:
  with pytest.raises(RuntimeRefused):validate_dispatch_links(db,SID,s[SID])
 else:validate_dispatch_links(db,SID,s[SID])


def test_request_file_cannot_hide_an_unlisted_dependency(tmp_path):
 from compertum.recovery_lineage import verify_file_dependencies
 c,e,a=setup();task=a['task_id'];hidden={**a,'artifact_id':str(uuid4()),'path':a['path']+'.missing'}
 raw=canonical(dict(records=[dict(kind='frame',index=0,artifact=hidden)]))+b'\n'
 path=f'artifacts/runs/{task}/review/input/request.review';target=tmp_path/path;target.parent.mkdir(parents=True);target.write_bytes(raw)
 request=dict(artifact_id=str(uuid4()),task_id=task,path=path,size_bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
 c.execute('INSERT INTO reservations VALUES(?,?,?,?,?,?)',(task,path,canonical(request).decode(),'records','PUBLISHED',str(uuid4())))
 with pytest.raises(RuntimeRefused):verify_file_dependencies(c,collect(c,e),tmp_path)
