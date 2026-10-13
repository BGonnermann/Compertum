"""Committed dispatch with real owners and simulated campaign/native evidence."""
from copy import deepcopy
from datetime import datetime,timezone
from uuid import uuid4
import json
import pytest
from test_final_transaction import owned,pair_inputs,environment,begin
from test_shortlist_freeze_journal import frozen_setup,freeze_now
from test_final_attempt_journal import starting
from compertum.data.encoding import canonical
from compertum.data.errors import DataError
from compertum.runtime.errors import RuntimeRefused
from compertum.evaluation_seals import verify_seal_journal
from compertum.review_evidence import sha
from compertum.final_dispatch import FinalRuns,read_dispatch

@pytest.fixture
def dispatch(owned,pair_inputs,monkeypatch):
 from compertum.final_transaction import recipe_sha256
 import test_shortlist_freeze_journal as setup
 original=setup.build_protocol;source=b'fixture input: native environment admission is simulated'
 monkeypatch.setattr(setup,'build_protocol',lambda **kw:original(**{**kw,'development_sha256':sha(source)}))
 pair_inputs[0]['holdout_manifest_sha256']=recipe_sha256()
 seals,p,ticket=frozen_setup.__wrapped__(owned,pair_inputs,monkeypatch);freeze_now(seals,p,ticket);begin(seals,p)
 from compertum import foundation
 from compertum.domain import TaskSpec
 real=foundation.fixture_spec
 def spec(root,task):
  payload=real(root,task).to_payload();payload.update(code_sha256=p['runtime']['package_sha256'],lock_sha256=p['runtime']['lock_sha256'])
  return TaskSpec(payload,project_root=root)
 monkeypatch.setattr(foundation,'fixture_spec',spec)
 storage=seals.test_storage;run=p['source']['run_id']
 grant=storage.reserve_bytes(run,'records',len(source));writer=storage.open_artifact(grant,f'artifacts/runs/{run}/baseline/inputs.json');writer.write(source);a=writer.publish();writer.close()
 with storage.store.conn:
  storage.store.conn.execute('CREATE TABLE baseline_runs(run_id TEXT PRIMARY KEY,body TEXT NOT NULL)')
  storage.store.conn.execute('INSERT INTO baseline_runs VALUES(?,?)',(run,canonical(dict(run_id=run,input_kind='synthetic-campaign',state='COMPLETED',request_sha256=a['sha256'],input_artifact=a)).decode()))
 runs=FinalRuns(storage);sid=p['source']['seal_id'];d,task,out=runs.prepare(sid,now=datetime.now(timezone.utc))
 try:yield runs,seals,p,d,task,out
 finally:out.close()

def native(seals,sid,d):
 n=starting(seals,sid)['attempt']['native_execution'];n['task_sha256']=d['attempt']['task_sha256'];return n

def test_owner_start_reads_committed_dispatch_and_saved_readback(dispatch):
 runs,seals,p,d,task,out=dispatch;sid=p['source']['seal_id'];n=native(seals,sid,d)
 assert runs.verify_launch(d,task.to_payload(),out.grant.grant_id)['attempt']['native_execution'] is None
 result=runs.begin(d,n,evaluation=seals)
 assert result['status']=='BATCH_RUNNING'
 saved=runs.verify_launch(d,task.to_payload(),out.grant.grant_id,execution_identity=n)
 assert saved['attempt']['native_execution']==n
 assert verify_seal_journal(seals.project)['seals'][sid]['final_attempts'][0]['start']['attempt']==saved['attempt']
 assert runs.begin(d,n,evaluation=seals)==result

@pytest.mark.parametrize('fault',['no_callback','wrong_native','request_hash','task_bytes','source_bytes','reservation','wrong_plan','lost_consumption'])
def test_changed_or_uncommitted_inputs_never_allow_resume(dispatch,fault):
 runs,seals,p,d,task,out=dispatch;sid=p['source']['seal_id'];n=native(seals,sid,d)
 if fault=='no_callback':
  with pytest.raises((DataError,RuntimeRefused)):runs.verify_launch(d,task.to_payload(),out.grant.grant_id,execution_identity=n)
  assert not verify_seal_journal(seals.project)['seals'][sid].get('final_attempts');return
 if fault=='wrong_native':n['task_sha256']='f'*64
 elif fault=='request_hash':
  v=deepcopy(d);v['request_artifact']['sha256']='f'*64
  with runs.store.conn:runs.store.conn.execute('UPDATE final_dispatches SET body=?,sha256=?',(canonical(v).decode(),sha(canonical(v))))
 elif fault in ('task_bytes','source_bytes'):
  a=d['task_artifact'] if fault=='task_bytes' else json.loads((runs.storage.root/d['request_artifact']['path']).read_bytes())['source_artifact']
  (runs.storage.root/a['path']).write_bytes(b'changed')
 elif fault=='reservation':
  with runs.store.conn:runs.store.conn.execute("UPDATE reservations SET status='ABANDONED' WHERE id=?",(out.grant.grant_id,))
 elif fault=='wrong_plan':
  v=deepcopy(d);v['attempt']['plan_sha256']='f'*64
  with runs.store.conn:runs.store.conn.execute('UPDATE final_dispatches SET body=?,sha256=?',(canonical(v).decode(),sha(canonical(v))))
 else:
  with seals.store.conn:seals.store.conn.execute('DELETE FROM consumption')
 with pytest.raises((DataError,RuntimeRefused)):runs.begin(d,n,evaluation=seals)
 assert not verify_seal_journal(seals.project)['seals'][sid].get('final_attempts')

def test_returned_success_without_saved_owner_start_is_not_authority(dispatch,monkeypatch):
 from compertum import development_seals
 runs,seals,p,d,task,out=dispatch;n=native(seals,p['source']['seal_id'],d)
 monkeypatch.setattr(development_seals,'_caller',lambda *a:lambda payload:dict(status='BATCH_RUNNING'))
 with pytest.raises((DataError,RuntimeRefused)):runs.begin(d,n,evaluation=seals)
 assert not verify_seal_journal(seals.project)['seals'][p['source']['seal_id']].get('final_attempts')

def test_rpc_does_not_accept_caller_native_or_plan(dispatch):
 runs,seals,p,d,task,out=dispatch
 with pytest.raises(RuntimeRefused):seals.handle(dict(operation='start_final',seal_id=p['source']['seal_id'],attempt_id=d['attempt']['attempt_id'],dispatch_sha256=sha(canonical(d)),native_execution=native(seals,p['source']['seal_id'],d)))

@pytest.mark.parametrize('fault',['pid_float','task_float','prepared_float','manifest_padding'])
def test_strict_json_bindings_and_bounded_manifest_projection(dispatch,fault):
 runs,seals,p,d,task,out=dispatch;sid=p['source']['seal_id'];n=native(seals,sid,d);runs.begin(d,n,evaluation=seals)
 if fault=='manifest_padding':
  with runs.store.conn:runs.store.conn.execute('UPDATE reservations SET manifest=? WHERE path=?',(' '*8192+canonical(d['request_artifact']).decode(),d['request_artifact']['path']))
  with pytest.raises((DataError,RuntimeRefused)):runs.verify_launch(d,task.to_payload(),out.grant.grant_id,execution_identity=n)
 elif fault=='task_float':
  payload=task.to_payload();payload['budget']['cpu_threads']=4.0
  with pytest.raises((DataError,RuntimeRefused)):runs.verify_launch(d,payload,out.grant.grant_id,execution_identity=n)
 elif fault=='prepared_float':
  d=deepcopy(d);d['attempt']['number']=1.0
  with pytest.raises((DataError,RuntimeRefused)):runs.begin(d,n,evaluation=seals)
 else:
  n=deepcopy(n);n['process']['pid']=float(n['process']['pid'])
  with pytest.raises((DataError,RuntimeRefused)):runs.verify_launch(d,task.to_payload(),out.grant.grant_id,execution_identity=n)
  with pytest.raises((DataError,RuntimeRefused)):runs.begin(d,n,evaluation=seals)
 assert len(verify_seal_journal(seals.project)['seals'][sid]['final_attempts'])==1
