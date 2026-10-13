"""Execution recovery evidence with real owners; no reserve-capacity acceptance."""
import json,sqlite3
from copy import deepcopy
from pathlib import Path
from uuid import uuid4
import pytest
from test_fake_execution_journal import native,checked_records,arguments
from test_recovery_snapshot_closure import prepared,owned
from test_execution_risk import NOW
from compertum.data.encoding import canonical
from compertum.fake_attempt_guard import verify_attempt_guard
from compertum.runtime.errors import RuntimeRefused


def test_new_manifest_pins_execution_attempt_boundary(owned):
 from compertum.recovery import validate_recovery_set
 seals,sid,a,result=prepared(owned);project=owned[0];m=result['manifest']
 assert m['fake_attempt_guard']=={k:verify_attempt_guard(project)[k] for k in ('sequence','sha256')}
 for fault in ('omitted','changed'):
  changed=deepcopy(m)
  if fault=='omitted':del changed['fake_attempt_guard']
  else:changed['fake_attempt_guard']['sha256']='f'*64
  path=project.root_path/(fault+'.json');path.write_bytes(canonical(changed))
  assert validate_recovery_set(path,project_root=project.root_path)['status']=='RECOVERY_INVALID'


def test_active_newer_attempt_detects_rolled_back_guard(native):
 from compertum.fake_recovery import preserved_attempt_evidence
 project,lease,store,j=native;old=verify_attempt_guard(project);i,d=checked_records(lease);j.record_checked(i,d);j.begin_attempt(*arguments(i),now=NOW)
 assert preserved_attempt_evidence(project,verify_attempt_guard(project))
 assert not preserved_attempt_evidence(project,old)


def test_prior_generation_evidence_and_compromise_are_preserved(native,tmp_path):
 from compertum.fake_recovery import preserved_attempt_evidence
 project,lease,store,j=native;old=verify_attempt_guard(project);empty=sqlite3.connect(':memory:');store.conn.backup(empty)
 i,d=checked_records(lease);j.record_checked(i,d);j.begin_attempt(*arguments(i),now=NOW)
 target=tmp_path/'state/generations'/str(uuid4())/'execution.sqlite';target.parent.mkdir(parents=True)
 with sqlite3.connect(target) as saved:store.conn.backup(saved)
 empty.backup(store.conn);empty.close()
 assert not preserved_attempt_evidence(project,old)
 with sqlite3.connect(target) as saved:saved.execute("INSERT INTO state VALUES('fake_attempt_conflict','true')")
 assert not preserved_attempt_evidence(project,verify_attempt_guard(project))


@pytest.mark.parametrize('fault',['head','body','decision','overflow'])
def test_snapshot_reader_rejects_conflicting_or_oversized_evidence(native,fault):
 from compertum.fake_recovery import snapshot_attempts,matches_snapshot
 project,lease,store,j=native;i,d=checked_records(lease);j.record_checked(i,d);j.begin_attempt(*arguments(i),now=NOW);e=verify_attempt_guard(project)
 with store.conn:
  if fault=='head':store.conn.execute("UPDATE state SET value=? WHERE key='fake_attempt_guard_head'",(json.dumps(dict(sequence=1,sha256='f'*64)),))
  elif fault=='body':store.conn.execute("UPDATE fake_intents SET body=?",('x'*65537,))
  elif fault=='decision':store.conn.execute("UPDATE fake_intents SET decision='{}'")
  else:store.conn.execute("UPDATE state SET value=? WHERE key='fake_attempt_guard_head'",('x'*1025,))
 try:assert not matches_snapshot(snapshot_attempts(store.conn,project.project_id),e)
 except RuntimeRefused as error:assert error.code=='EXECUTION_COMPROMISED'


def test_legacy_absence_is_not_reinterpreted_as_empty_head(native):
 from compertum.fake_recovery import snapshot_attempts,matches_snapshot
 project,lease,store,j=native
 with store.conn:store.conn.execute("DELETE FROM state WHERE key='fake_attempt_guard_head'")
 value=snapshot_attempts(store.conn,project.project_id)
 assert value['head'] is None and matches_snapshot(value,verify_attempt_guard(project))
 i,d=checked_records(lease);j.record_checked(i,d)
 with store.conn:store.conn.execute("UPDATE fake_intents SET state='SUBMITTING'")
 assert not matches_snapshot(snapshot_attempts(store.conn,project.project_id),verify_attempt_guard(project))


@pytest.fixture
def barrier(owned):
 from compertum.runtime.owners import acquire_owner,release_owner
 extra={r:acquire_owner(owned[0],r) for r in ('watchdog','recovery')}
 try:yield extra
 finally:
  for lease in extra.values():release_owner(lease)


def save_checkpoint(owned,storage,barrier_leases):
 # Capacity measurement is simulated; native owner/SQLite/recovery paths are real.
 from types import SimpleNamespace
 from compertum.persistence import open_store
 from compertum.recovery import collect_recovery_set
 project,leases=owned
 reserve=SimpleNamespace(lease=leases['execution'],receipt=lambda:dict(capacity_bytes=1024**3,unused_bytes=1024**3,allocated_bytes=1024**3))
 return collect_recovery_set(project,[open_store(leases[r],r) for r in ('coordinator','evaluation','execution')],storage.reserve_bytes(str(uuid4()),'backups',4*1024**2),recovery_lease=barrier_leases['recovery'],watchdog_lease=barrier_leases['watchdog'],reserve=reserve)


def test_retained_backup_detects_joint_active_database_and_guard_rollback(owned,barrier):
 from compertum.fake_recovery import preserved_attempt_evidence
 from compertum.fake_execution_journal import FakeIntentJournal
 from compertum.persistence import open_store
 seals,sid,a,before=prepared(owned,barrier_leases=barrier);project,leases=owned;store=open_store(leases['execution'],'execution');j=FakeIntentJournal(store)
 old=verify_attempt_guard(project);database=sqlite3.connect(':memory:');store.conn.backup(database)
 i,d=checked_records(leases['execution']);j.record_checked(i,d);j.begin_attempt(*arguments(i),now=NOW)
 latest=save_checkpoint(owned,seals.test_storage,barrier)
 assert latest['manifest']['fake_attempt_guard']['sequence']==1
 database.backup(store.conn);database.close()
 assert not preserved_attempt_evidence(project,old)
 assert preserved_attempt_evidence(project,verify_attempt_guard(project))


def test_row_count_bound_refuses_before_payload_validation(native,monkeypatch):
 import compertum.fake_recovery as module
 project,lease,store,j=native;i,d=checked_records(lease);j.record_checked(i,d)
 with store.conn:
  for n in range(257):store.conn.execute("INSERT INTO fake_intents SELECT account,?, ?,body,decision,state,order_id,filled,notional,conflict FROM fake_intents LIMIT 1",(str(n),str(n)))
 def forbidden(value):raise AssertionError('payload read after row limit')
 monkeypatch.setattr(module,'ExecutionIntent',forbidden)
 with pytest.raises(RuntimeRefused,match='EXECUTION_COMPROMISED'):module.snapshot_attempts(store.conn,project.project_id)


def invoke(root,action,manifest=None,expected_exit=0):
 import os,sys,subprocess
 env={k:v for k,v in os.environ.items() if k.upper() in {'SYSTEMROOT','WINDIR','PYTHONPATH','PYTHONDONTWRITEBYTECODE','TEMP','TMP'}}
 args=[sys.executable,'-B',str(Path(__file__).parent/'helpers/fake_recovery_fixture.py'),str(root),action]
 if manifest is not None:args.append(str(manifest))
 result=subprocess.run(args,env=env,capture_output=True,text=True,timeout=30)
 assert result.returncode==expected_exit,result.stderr
 assert result.stderr=='',result.stderr
 return json.loads(result.stdout) if result.stdout else None


def test_actual_restore_keeps_one_acceptance_and_disarms(tmp_path):
 setup=invoke(tmp_path,'prepare');result=invoke(tmp_path,'restore',setup['manifest'])
 assert result['execution_state']=='VERIFIED' and result['admission']=='HALTED' and result['seal_state']=='CONSUMED'
 probe=invoke(tmp_path,'probe')
 assert probe['state']=='UNKNOWN' and probe['acceptances']==1 and probe['new_attempt'] is False
 assert probe['armed'] is False and probe['plan'] is None


def test_joint_rollback_and_repeated_restore_remain_compromised(tmp_path):
 setup=invoke(tmp_path,'prepare');invoke(tmp_path,'rollback')
 first=invoke(tmp_path,'restore',setup['manifest']);assert first['execution_state']=='EXECUTION_COMPROMISED'
 invoke(tmp_path,'repair_guard')
 second=invoke(tmp_path,'restore',setup['manifest']);assert second['execution_state']=='EXECUTION_COMPROMISED'
 assert invoke(tmp_path,'probe')['refused']=='EXECUTION_COMPROMISED'


@pytest.mark.parametrize('damage',[False,True])
def test_ready_crash_requires_exact_preserved_attempt_head(tmp_path,damage):
 setup=invoke(tmp_path,'prepare');invoke(tmp_path,'crash_restore',setup['manifest'],expected_exit=17)
 if damage:invoke(tmp_path,'rollback_guard')
 result=invoke(tmp_path,'recover')
 assert result['status']==('ABORTED' if damage else 'PUBLISHED')


@pytest.mark.parametrize('directory_exists',[False,True])
def test_missing_pointed_execution_store_is_compromised(native,directory_exists):
 from compertum.fake_recovery import preserved_attempt_evidence
 project,lease,store,j=native;generation=str(uuid4());path=project.root_path/'state/generations'/generation
 if directory_exists:path.mkdir(parents=True)
 (project.root_path/'state/active-generation.json').write_bytes(canonical(dict(schema_version=1,project_id=project.project_id,generation=generation,operation_id=str(uuid4()))))
 assert not preserved_attempt_evidence(project,verify_attempt_guard(project))


def test_prior_intent_integrity_conflict_cannot_be_erased(native):
 from compertum.fake_recovery import snapshot_attempts,matches_snapshot
 project,lease,store,j=native;i,d=checked_records(lease);j.record_checked(i,d);j.begin_attempt(*arguments(i),now=NOW)
 with store.conn:store.conn.execute('UPDATE fake_intents SET conflict=1')
 assert not matches_snapshot(snapshot_attempts(store.conn,project.project_id),verify_attempt_guard(project))


@pytest.mark.parametrize('terminal',['ABORTED','PUBLISHED'])
def test_only_proven_aborted_partial_copy_is_excluded(native,terminal):
 from compertum.fake_recovery import preserved_attempt_evidence
 project,lease,store,j=native;generation=str(uuid4());operation=str(uuid4());path=project.root_path/'state/generations'/generation/'execution.sqlite';path.parent.mkdir(parents=True);path.write_bytes(b'incomplete snapshot')
 common=dict(operation_id=operation,generation=generation,prior_active=None)
 records=[dict(common,status='PREPARING'),dict(common,status=terminal)]
 (project.root_path/'state'/('restore-'+operation+'.jsonl')).write_bytes(b''.join(canonical(r)+b'\n' for r in records))
 assert preserved_attempt_evidence(project,verify_attempt_guard(project)) is (terminal=='ABORTED')


def test_partial_execution_copy_is_retained_but_retry_can_restore(tmp_path):
 setup=invoke(tmp_path,'prepare');invoke(tmp_path,'partial_restore',setup['manifest'],expected_exit=17)
 phase=json.loads((tmp_path/'state/restore-operation.json').read_bytes());partial=tmp_path/'state/generations'/phase['generation']/'execution.sqlite'
 assert partial.stat().st_size==256
 assert invoke(tmp_path,'recover')['status']=='ABORTED'
 result=invoke(tmp_path,'restore',setup['manifest']);assert result['execution_state']=='VERIFIED'
 assert partial.stat().st_size==256
 again=invoke(tmp_path,'restore',setup['manifest']);assert again['execution_state']=='VERIFIED'
 assert invoke(tmp_path,'probe')['new_attempt'] is False


def test_restored_guard_head_can_be_checkpointed_without_losing_attempts(tmp_path):
 setup=invoke(tmp_path,'prepare');result=invoke(tmp_path,'restore',setup['manifest'])
 with sqlite3.connect(tmp_path/'state/generations'/result['generation']/'execution.sqlite') as db:
  head=json.loads(db.execute("SELECT value FROM state WHERE key='fake_attempt_guard_head'").fetchone()[0])
 assert head=={k:verify_attempt_guard(__import__('compertum.runtime.identity',fromlist=['resolve_project']).resolve_project(tmp_path))[k] for k in ('sequence','sha256')}
 assert head['sequence']==1 and invoke(tmp_path,'probe')['new_attempt'] is False


@pytest.mark.parametrize('proof',['published','prior_active'])
def test_other_publication_evidence_prevents_aborted_exclusion(native,proof):
 from compertum.fake_recovery import preserved_attempt_evidence
 project,lease,store,j=native;generation=str(uuid4());operation=str(uuid4());path=project.root_path/'state/generations'/generation/'execution.sqlite';path.parent.mkdir(parents=True)
 with sqlite3.connect(path) as saved:
  store.conn.backup(saved);saved.execute("INSERT INTO state VALUES('fake_attempt_conflict','true')")
 common=dict(operation_id=operation,generation=generation,prior_active=None)
 (project.root_path/'state'/('restore-'+operation+'.jsonl')).write_bytes(b''.join(canonical(dict(common,status=status))+b'\n' for status in ('PREPARING','ABORTED')))
 other=str(uuid4());prior=None;other_generation=generation
 if proof=='prior_active':
  other_generation=str(uuid4());prior=dict(schema_version=1,project_id=project.project_id,generation=generation,operation_id=operation)
 common=dict(operation_id=other,generation=other_generation,prior_active=prior)
 (project.root_path/'state'/('restore-'+other+'.jsonl')).write_bytes(b''.join(canonical(dict(common,status=status))+b'\n' for status in ('PREPARING','PUBLISHED')))
 assert not preserved_attempt_evidence(project,verify_attempt_guard(project))


def test_guard_change_during_staging_refuses_pointer_publication(tmp_path):
 setup=invoke(tmp_path,'prepare');result=invoke(tmp_path,'mutate_restore',setup['manifest'])
 assert result['refused']=='RESTORE_JOURNAL_CHANGED'
 assert not (tmp_path/'state/active-generation.json').exists()
 assert invoke(tmp_path,'recover')['status']=='ABORTED'


def test_legacy_ready_record_without_attempt_boundary_cannot_complete(tmp_path):
 setup=invoke(tmp_path,'prepare');invoke(tmp_path,'crash_restore',setup['manifest'],expected_exit=17)
 path=tmp_path/'state/restore-operation.json';record=json.loads(path.read_bytes());del record['fake_attempt_guard'];path.write_bytes(canonical(record))
 assert invoke(tmp_path,'recover')['status']=='ABORTED'
