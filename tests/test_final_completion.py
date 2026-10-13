"""Durable completion tests use simulated worker receipts, never native admission."""
import json
from copy import deepcopy
import pytest
from test_final_dispatch import dispatch,owned,pair_inputs,environment,native
from compertum.data.encoding import canonical
from compertum.data.errors import DataError
from compertum.runtime.errors import RuntimeRefused
from compertum.final_completion import record_exit,propose_close,close_through_owner
from compertum.review_frame import pack_review,result_binding
from compertum.runtime.startup_record import expected_proof
from compertum.runtime.campaign_environment import observed_from_native
from compertum.review_evidence import sha
from compertum.evaluation_seals import verify_seal_journal

def start(dispatch,monkeypatch):
 import compertum.final_completion as module
 runs,seals,p,d,task,out=dispatch;n=native(seals,p['source']['seal_id'],d);runs.begin(d,n,evaluation=seals)
 monkeypatch.setattr(module,'require_exited',lambda n:None)
 receipt=dict(pid=n['process']['pid'],exit_code=0,timed_out=False,active_processes=0,assigned_before_resume=True,affinity=15,memory_limit=4*1024**3,peak_job_memory=1024**2,observed_child_pids=[],observed_children_exited=True,execution_identity=n)
 return n,receipt

def publication(dispatch,n):
 runs,seals,p,d,task,out=dispatch;req=json.loads((runs.storage.root/d['request_artifact']['path']).read_bytes());body=b'opaque fixture payload; worker mathematics not exercised'
 frame=pack_review(body,result_binding('final',task.to_payload()['task_id'],p['source']['run_id'],d['request_artifact']['sha256'],p['runtime'],n['process']['pid'],startup=expected_proof(n),environment=observed_from_native(n)))
 out.write(frame);artifact=out.publish()
 return dict(artifact=artifact,payload_sha256=sha(body),payload_bytes=len(body))

def test_completed_reference_is_streamed_checked_and_owner_terminal(dispatch,monkeypatch):
 runs,seals,p,d,task,out=dispatch;n,r=start(dispatch,monkeypatch);record_exit(runs,d,r);pub=publication(dispatch,n)
 ticket=propose_close(runs,d,'COMPLETED',publication=pub);done=close_through_owner(runs,d,ticket,evaluation=seals)
 assert done['status']=='COMPLETED' and done['result']['publication']==pub and done['charged_ms']>0
 assert close_through_owner(runs,d,ticket,evaluation=seals)==done
 with pytest.raises((DataError,RuntimeRefused)):runs.prepare(p['source']['seal_id'],now=__import__('datetime').datetime.now(__import__('datetime').timezone.utc))

@pytest.mark.parametrize('mode,code,status',[('INTERRUPTED',125,'BATCH_INTERRUPTED'),('STOPPED',125,'STOPPED'),('INTERRUPTED',4,'REJECTED'),('INTERRUPTED',6,'REJECTED')])
def test_integrity_rejection_cannot_become_resumable_pause(dispatch,monkeypatch,mode,code,status):
 runs,seals,p,d,task,out=dispatch;n,r=start(dispatch,monkeypatch);r['exit_code']=code;record_exit(runs,d,r)
 ticket=propose_close(runs,d,mode);done=close_through_owner(runs,d,ticket,evaluation=seals)
 assert done['status']==status
 assert verify_seal_journal(seals.project)['seals'][p['source']['seal_id']]['final_attempts'][-1]['close']['job_receipt']==r

@pytest.mark.parametrize('fault',['missing_exit','live_process','changed_frame','wrong_payload','changed_exit','children','wrong_attempt'])
def test_incomplete_exit_or_publication_never_completes(dispatch,monkeypatch,fault):
 import compertum.final_completion as module
 runs,seals,p,d,task,out=dispatch;n,r=start(dispatch,monkeypatch)
 if fault=='children':
  r['observed_child_pids']=[99]
  with pytest.raises((DataError,RuntimeRefused)):record_exit(runs,d,r)
  return
 if fault!='missing_exit':record_exit(runs,d,r)
 pub=publication(dispatch,n)
 if fault=='changed_frame':(runs.storage.root/pub['artifact']['path']).write_bytes(b'changed')
 elif fault=='wrong_payload':pub['payload_sha256']='f'*64
 elif fault=='changed_exit':
  r['exit_code']=4
  with pytest.raises((DataError,RuntimeRefused)):record_exit(runs,d,r)
  return
 elif fault=='wrong_attempt':d=deepcopy(d);d['attempt']['attempt_id']=str(__import__('uuid').uuid4())
 elif fault=='live_process':
  def live(n):raise RuntimeRefused('FINAL_PROCESS_STILL_LIVE')
  monkeypatch.setattr(module,'require_exited',live)
 with pytest.raises((DataError,RuntimeRefused)):
  ticket=propose_close(runs,d,'COMPLETED',publication=pub);close_through_owner(runs,d,ticket,evaluation=seals)
 assert verify_seal_journal(seals.project)['seals'][p['source']['seal_id']].get('final_complete') is None

@pytest.mark.parametrize('fault',['output','source'])
def test_terminal_reuse_rechecks_retained_bytes(dispatch,monkeypatch,fault):
 runs,seals,p,d,task,out=dispatch;n,r=start(dispatch,monkeypatch);record_exit(runs,d,r);pub=publication(dispatch,n)
 ticket=propose_close(runs,d,'COMPLETED',publication=pub);done=close_through_owner(runs,d,ticket,evaluation=seals)
 target=pub['artifact'] if fault=='output' else json.loads((runs.storage.root/d['request_artifact']['path']).read_bytes())['source_artifact']
 (runs.storage.root/target['path']).write_bytes(b'changed after completion')
 with pytest.raises((DataError,RuntimeRefused)):close_through_owner(runs,d,ticket,evaluation=seals)
 assert verify_seal_journal(seals.project)['seals'][p['source']['seal_id']]['final_complete']['result']==done['result']

def test_missing_output_is_acknowledged_refusal_and_owner_remains_usable(dispatch,monkeypatch):
 runs,seals,p,d,task,out=dispatch;n,r=start(dispatch,monkeypatch);record_exit(runs,d,r);pub=publication(dispatch,n)
 ticket=propose_close(runs,d,'COMPLETED',publication=pub)
 path=runs.storage.root/pub['artifact']['path'];path.rename(path.with_name('preserved-missing-output.final'))
 with pytest.raises(RuntimeRefused):close_through_owner(runs,d,ticket,evaluation=seals)
 assert seals.handle(dict(operation='inspect_final',seal_id=p['source']['seal_id']))['status']=='BATCH_RUNNING'
 assert verify_seal_journal(seals.project)['seals'][p['source']['seal_id']].get('final_complete') is None
