"""Real owner journals with simulated final worker identities; no native admission."""
from copy import deepcopy
from datetime import datetime,timedelta
from uuid import UUID,uuid4,uuid5
import hashlib,json
import pytest
from test_final_transaction import ready,owned,pair_inputs,environment,begin
from test_final_attempts import context,start,close,SID
from compertum.data.encoding import canonical
from compertum.data.errors import DataError
from compertum.evaluation_seals import verify_seal_journal
from compertum.final_transaction import remaining_events
from compertum.runtime.errors import RuntimeRefused

def starting(seals,sid,number=1):
 row=verify_seal_journal(seals.project)['seals'][sid];plan=row['final']['plan'];r=seals._record(sid,'START_FINAL_BATCH')
 a=start(context())['attempt'];p=row['freeze']['ticket'];eid=plan['evaluation_id'];prior=row.get('final_attempts',[])
 charged=prior[-1]['close']['charged_ms'] if prior else 0
 began=datetime.fromisoformat(r['created_at'])
 if prior:began=max(began,datetime.fromisoformat(prior[-1]['close']['created_at']))
 r['created_at']=began.isoformat()
 a.update(number=number,attempt_id=str(uuid5(UUID(eid),f'synthetic-final-attempt-{number}')),evaluation_id=eid,checkpoint_id=plan['checkpoint_id'],plan_sha256=row['final']['plan_sha256'],output_path=f'artifacts/runs/{eid}/final/attempt-{number:02}.final',charged_before_ms=charged,started_at=began.isoformat(),deadline_at=(began+timedelta(milliseconds=120000-charged)).isoformat())
 from compertum.consumption import verify_consumption_guard
 a['consumption_sha256']=hashlib.sha256(canonical(verify_consumption_guard(seals.project)['consumed'][sid])).hexdigest()
 n=a['native_execution'];n.update(task_id=eid,code_sha256=plan['runtime']['package_sha256'],lock_sha256=plan['runtime']['lock_sha256'])
 n['process']['pid']+=number;n['process']['creation_filetime']+=number
 n['clean_environment'].update(pair_sha256=p['pair_sha256'],manifest_sha256=p['pair']['source']['manifest_sha256'],run_id=p['pair']['source']['run_id'])
 return dict(r,attempt=a)
def closing(seals,sid,outcome='INTERRUPTED'):
 row=verify_seal_journal(seals.project)['seals'][sid];a=row['final_attempts'][-1]['start']['attempt'];r=close({SID:row},outcome)
 r.update(seals._record(sid,r['operation']));r['created_at']=(datetime.fromisoformat(a['started_at'])+timedelta(seconds=1)).isoformat();r['charged_ms']=a['charged_before_ms']+1000
 if r['publication']:r['publication']['artifact']['task_id']=a['evaluation_id']
 return r
def append(seals,r):
 with seals.store._live() as scope:seals._append(seals._evidence(),r,scope)

def test_two_attempts_replay_with_exact_reserved_headroom(ready,monkeypatch):
 from compertum import evaluation_seals as mod
 seals,p,_=ready;sid=p['source']['seal_id'];monkeypatch.setattr(mod,'MAX_EVENTS',12);first=begin(seals,p)
 assert remaining_events(verify_seal_journal(seals.project)['seals'][sid])==4
 append(seals,starting(seals,sid));assert remaining_events(verify_seal_journal(seals.project)['seals'][sid])==3
 append(seals,closing(seals,sid));assert remaining_events(verify_seal_journal(seals.project)['seals'][sid])==2
 append(seals,starting(seals,sid,2));assert remaining_events(verify_seal_journal(seals.project)['seals'][sid])==1
 append(seals,closing(seals,sid,'COMPLETED'))
 journal=verify_seal_journal(seals.project);assert journal['status']=='VERIFIED' and journal['sequence']==10 and remaining_events(journal['seals'][sid])==0
 receipt=seals.handle(dict(operation='inspect_final',seal_id=sid))
 assert receipt['status']=='COMPLETED' and receipt['price_reads'] is None and receipt['result']['publication'] is not None
 assert receipt['evaluation_id']==first['evaluation_id']
 from test_evaluation_seals import invalidate
 invalidate(seals,sid,'OPERATOR_INVALIDATED');invalidate(seals,p['wheel']['seal_id'],'OPERATOR_INVALIDATED')
 assert verify_seal_journal(seals.project)['sequence']==12

@pytest.mark.parametrize('outcome',['REJECTED','COMPLETED'])
def test_restored_sqlite_keeps_terminal_journal_and_attempts(ready,outcome):
 seals,p,_=ready;sid=p['source']['seal_id'];begin(seals,p);append(seals,starting(seals,sid));append(seals,closing(seals,sid,outcome))
 before=seals.handle(dict(operation='inspect_final',seal_id=sid))
 with seals.store.conn:seals.store.conn.execute('DELETE FROM evaluation_seal_events WHERE sequence>6')
 seals.store.close()
 from compertum.persistence import open_store
 from compertum.evaluation_seals import EvaluationSeals
 restored=EvaluationSeals(open_store(seals.store.lease,'evaluation'));restored.test_storage=seals.test_storage
 assert restored.handle(dict(operation='inspect_final',seal_id=sid))==before and before['status']==outcome
 with pytest.raises(DataError):append(restored,starting(restored,sid,2))
 assert verify_seal_journal(restored.project)['sequence']==8

def test_invalid_proposed_attempt_is_rejected_before_any_write(ready):
 seals,p,_=ready;sid=p['source']['seal_id'];begin(seals,p);before=verify_seal_journal(seals.project)
 r=starting(seals,sid);r['attempt']['checkpoint_id']=str(uuid4())
 with pytest.raises(DataError):append(seals,r)
 assert verify_seal_journal(seals.project)==before
 assert not (seals.project.root_path/'state/evaluation-seals/00000007.json').exists()

def test_interrupted_receipt_does_not_report_zero_reads_or_completion(ready):
 seals,p,_=ready;sid=p['source']['seal_id'];begin(seals,p);append(seals,starting(seals,sid))
 r=seals.handle(dict(operation='inspect_final',seal_id=sid));assert r['status']=='BATCH_RUNNING' and r['price_reads'] is None and r['result'] is None
 append(seals,closing(seals,sid));r=seals.handle(dict(operation='inspect_final',seal_id=sid))
 assert r['status']=='BATCH_INTERRUPTED' and r['price_reads'] is None and r['attempt_count']==1 and r['charged_ms']==1000
