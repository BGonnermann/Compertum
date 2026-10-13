"""Real SQLite snapshot rollback with separately preserved fake attempts."""
import json,sqlite3
from compertum.fake_execution_journal import FakeIntentJournal
from compertum.deterministic_broker import DeterministicBroker
from compertum.runtime.errors import RuntimeRefused
from test_fake_execution_journal import native,checked_records,arguments
from test_execution_risk import NOW
import pytest


def test_older_sqlite_snapshot_cannot_regrant_a_simulated_submission(native,tmp_path):
 from compertum.fake_attempt_guard import verify_attempt_guard
 project,lease,store,j=native;i,d=checked_records(lease);j.record_checked(i,d)
 snapshot=sqlite3.connect(tmp_path/'older.sqlite');store.conn.backup(snapshot)
 broker=DeterministicBroker(tmp_path/'independent-broker')
 try:
  assert j.begin_attempt(*arguments(i),now=NOW)['simulate_once'];broker.submit(i)
  snapshot.backup(store.conn)
  recovered=FakeIntentJournal(store)
  assert recovered.read(*arguments(i))['status']=='UNKNOWN'
  assert not recovered.begin_attempt(*arguments(i),now=NOW)['simulate_once']
  assert verify_attempt_guard(project)['sequence']==1
  assert len(broker.snapshot()['orders'])==1
 finally:snapshot.close();broker.close()


@pytest.mark.parametrize('expired',[False,True])
def test_preserved_attempt_before_database_commit_never_grants_again(native,expired):
 from compertum.fake_attempt_guard import record_attempt,verify_attempt_guard
 project,lease,store,j=native;i,d=checked_records(lease);j.record_checked(i,d)
 assert record_attempt(store,i,d,now=NOW)['first']
 result=j.begin_attempt(*arguments(i),now=i.to_payload()['expires_at'] if expired else NOW)
 assert not result['simulate_once'] and result['record']['status']=='UNKNOWN'
 assert verify_attempt_guard(project)['sequence']==1


@pytest.mark.parametrize('damage',['missing_head','extra_event','changed_record'])
def test_uncertain_attempt_files_block_new_effects_and_preserve_rows(native,damage):
 from compertum.fake_attempt_guard import verify_attempt_guard
 project,lease,store,j=native;i,d=checked_records(lease);j.record_checked(i,d);j.begin_attempt(*arguments(i),now=NOW)
 path=project.root_path/'state/fake-execution-attempts'
 if damage=='missing_head':(path/'head.json').rename(path/'preserved-head.json')
 elif damage=='extra_event':(path/'00000002.json').write_text('{}')
 else:
  event=path/'00000001.json';raw=json.loads(event.read_text());raw['record']['intent']['quantity']+=1;event.write_text(json.dumps(raw))
 assert verify_attempt_guard(project)['status']=='EXECUTION_COMPROMISED'
 other,decision=checked_records(lease);j.record_checked(other,decision)
 with pytest.raises(RuntimeRefused,match='EXECUTION_COMPROMISED'):j.begin_attempt(*arguments(other),now=NOW)
 assert j.read(*arguments(i))['status']=='SUBMITTING'


def test_missing_entire_guard_cannot_be_reinitialized_from_older_snapshot(native,tmp_path):
 project,lease,store,j=native;i,d=checked_records(lease);j.record_checked(i,d)
 snapshot=sqlite3.connect(tmp_path/'older.sqlite');store.conn.backup(snapshot)
 try:
  j.begin_attempt(*arguments(i),now=NOW);snapshot.backup(store.conn)
  path=project.root_path/'state/fake-execution-attempts';path.rename(project.root_path/'preserved-fake-attempt-evidence')
  recovered=FakeIntentJournal(store)
  with pytest.raises(RuntimeRefused,match='EXECUTION_COMPROMISED'):recovered.begin_attempt(*arguments(i),now=NOW)
  assert not path.exists()
 finally:snapshot.close()


def test_database_attempt_without_matching_preserved_evidence_blocks(native):
 project,lease,store,j=native;i,d=checked_records(lease);j.record_checked(i,d)
 with store.conn:store.conn.execute("UPDATE fake_intents SET state='ACKNOWLEDGED'")
 other,decision=checked_records(lease);j.record_checked(other,decision)
 with pytest.raises(RuntimeRefused,match='EXECUTION_COMPROMISED'):j.begin_attempt(*arguments(other),now=NOW)


def test_snapshot_before_first_journal_cannot_reset_lost_attempt_guard(tmp_path):
 from compertum.runtime.identity import resolve_project
 from compertum.runtime.owners import acquire_owner,release_owner
 from compertum.persistence import open_store
 project=resolve_project(tmp_path);lease=acquire_owner(project,'execution');store=open_store(lease,'execution');snapshot=sqlite3.connect(tmp_path/'pre-journal.sqlite')
 try:
  store.conn.backup(snapshot);j=FakeIntentJournal(store);i,d=checked_records(lease);j.record_checked(i,d)
  assert j.begin_attempt(*arguments(i),now=NOW)['simulate_once']
  snapshot.backup(store.conn)
  (tmp_path/'state/fake-execution-attempts').rename(tmp_path/'preserved-attempts')
  recovered=FakeIntentJournal(store);recovered.record_checked(i,d)
  with pytest.raises(RuntimeRefused,match='EXECUTION_COMPROMISED'):recovered.begin_attempt(*arguments(i),now=NOW)
  assert not (tmp_path/'state/fake-execution-attempts').exists()
 finally:snapshot.close();release_owner(lease)


def test_unexpected_guard_entry_stops_directory_consumption(native,monkeypatch):
 import os
 from pathlib import Path
 from contextlib import contextmanager
 from types import SimpleNamespace
 from compertum.fake_attempt_guard import verify_attempt_guard
 project,_,_,_=native;original=os.scandir
 def rows():
  yield SimpleNamespace(name='unexpected')
  raise AssertionError('enumeration continued past invalid evidence')
 @contextmanager
 def entries(path):
  if Path(path).name=='fake-execution-attempts':yield rows()
  else:
   with original(path) as iterator:yield iterator
 monkeypatch.setattr(os,'scandir',entries)
 assert verify_attempt_guard(project)['status']=='EXECUTION_COMPROMISED'
