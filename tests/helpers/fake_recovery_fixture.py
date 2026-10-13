"""Real native process boundaries; fake broker and simulated reserve receipt only."""
from pathlib import Path
import json,sys,os,sqlite3,shutil
from uuid import uuid4
sys.path.insert(0,str(Path(__file__).parents[1]))
from compertum.runtime.identity import resolve_project
from compertum.runtime.owners import acquire_owner,release_owner
from compertum.persistence import open_store
from compertum.recovery import restore_recovery_set,recover_interrupted_restore
from compertum.consumption import verify_consumption_guard
from compertum.fake_execution_journal import FakeIntentJournal
from compertum.deterministic_broker import DeterministicBroker
from compertum.runtime.errors import RuntimeRefused
from test_fake_execution_journal import checked_records,arguments
from test_execution_risk import NOW
root=Path(sys.argv[1]);action=sys.argv[2];project=resolve_project(root)
if action in ('prepare','prepare_opening'):
 from test_recovery_snapshot_closure import prepared
 from test_fake_recovery import save_checkpoint
 leases={r:acquire_owner(project,r) for r in ('coordinator','evaluation','execution','watchdog','recovery')}
 try:
  if action=='prepare_opening':
   from compertum.fake_economic_opening import provision_opening
   opening_store=open_store(leases['execution'],'execution');FakeIntentJournal(opening_store)
   opening_broker=DeterministicBroker(root/'state/fake-broker')
   try:provision_opening(opening_store,opening_broker,cash='10000',positions={})
   finally:opening_broker.close()
  seals,sid,a,before=prepared((project,leases),barrier_leases={r:leases[r] for r in ('watchdog','recovery')});store=open_store(leases['execution'],'execution');j=FakeIntentJournal(store)
  shutil.copytree(root/'state/fake-execution-attempts',root/'saved-empty-guard')
  with sqlite3.connect(root/'saved-empty.sqlite') as saved:store.conn.backup(saved)
  i,d=checked_records(leases['execution']);j.record_checked(i,d);assert j.begin_attempt(*arguments(i),now=NOW)['simulate_once']
  broker=DeterministicBroker(root/'independent-broker');broker.submit(i);broker.close()
  latest=save_checkpoint((project,leases),seals.test_storage,{r:leases[r] for r in ('watchdog','recovery')})
  (root/'fixture-intent.json').write_text(json.dumps(i.to_payload()),encoding='utf-8')
  answer={'manifest':before['manifest_path'],'latest':latest['manifest_path']}
 finally:
  for lease in leases.values():release_owner(lease)
elif action in ('restore','crash_restore','partial_restore','mutate_restore','mutate_opening_restore'):
 if action=='mutate_opening_restore':
  from compertum import recovery
  original_hash=recovery._hash;execution_hashes=0
  def mutate_hash(path):
   global execution_hashes
   digest=original_hash(path)
   if path.name=='execution.sqlite' and path.parent.parent.name=='generations':
    execution_hashes+=1
    if execution_hashes==2:(root/'state/fake-economic-opening.json').rename(root/'retained-opening.json')
   return digest
  recovery._hash=mutate_hash
 if action=='mutate_restore':
  from compertum.runtime._windows import WindowsAPI
  original=WindowsAPI.publish_metadata
  def mutate(api,path,raw):
   original(api,path,raw)
   if path.name=='restore-operation.json' and json.loads(raw)['status']=='STAGING_EXECUTION':
    (root/'state/fake-execution-attempts').rename(root/'retained-newer-guard')
    shutil.copytree(root/'saved-empty-guard',root/'state/fake-execution-attempts')
  WindowsAPI.publish_metadata=mutate
 if action=='partial_restore':
  original_open=Path.open
  class Partial:
   def __init__(self,stream):self.stream=stream
   def __enter__(self):return self
   def __exit__(self,*args):self.stream.close()
   def write(self,raw):
    self.stream.write(raw[:256]);self.stream.flush();os.fsync(self.stream.fileno());os._exit(17)
  def partial_open(path,mode='r',*args,**kwargs):
   stream=original_open(path,mode,*args,**kwargs)
   return Partial(stream) if path.name=='execution.sqlite' and mode=='xb' and path.parent.parent.name=='generations' else stream
  Path.open=partial_open
 if action=='crash_restore':
  from compertum.runtime._windows import WindowsAPI
  original=WindowsAPI.publish_metadata
  def crash(api,path,raw):
   original(api,path,raw)
   if path.name=='active-generation.json':os._exit(17)
  WindowsAPI.publish_metadata=crash
 try:answer=restore_recovery_set(sys.argv[3],verify_consumption_guard(project),root/'state/generations'/str(uuid4()),project=project)
 except RuntimeRefused as error:
  if action not in ('mutate_restore','mutate_opening_restore'):raise
  answer={'refused':error.code}
elif action=='recover':answer=recover_interrupted_restore(project)
elif action in ('rollback','rollback_guard'):
 (root/'state/fake-execution-attempts').rename(root/'retained-newer-guard')
 shutil.copytree(root/'saved-empty-guard',root/'state/fake-execution-attempts')
 if action=='rollback':
  with sqlite3.connect(root/'saved-empty.sqlite') as old,sqlite3.connect(root/'state/execution.sqlite') as current:old.backup(current)
 answer={'status':'FIXTURE_ROLLED_BACK'}
elif action=='repair_guard':
 (root/'state/fake-execution-attempts').rename(root/'retained-rolled-back-guard')
 (root/'retained-newer-guard').rename(root/'state/fake-execution-attempts');answer={'status':'FIXTURE_GUARD_REPAIRED'}
elif action=='probe':
 lease=acquire_owner(project,'execution')
 try:
  store=open_store(lease,'execution');j=FakeIntentJournal(store);i=json.loads((root/'fixture-intent.json').read_bytes())
  broker=DeterministicBroker(root/'independent-broker');answer={'acceptances':len(broker.snapshot()['orders']),'armed':store.get_state('armed'),'plan':store.get_state('approved_plan')};broker.close()
  if store.get_state('fake_attempt_conflict'):
   other,d=checked_records(lease);j.record_checked(other,d)
   try:j.begin_attempt(*arguments(other),now=NOW)
   except RuntimeRefused as e:answer['refused']=e.code
   else:raise AssertionError('compromised restore granted attempt')
  else:
   row=j.read(i['account_alias'],i['intent_id']);answer['state']=row['status'];answer['new_attempt']=j.begin_attempt(i['account_alias'],i['intent_id'],now=NOW)['simulate_once']
 finally:release_owner(lease)
else:raise ValueError('unknown fixture action')
print(json.dumps(answer))
