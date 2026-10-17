"""Real Windows stores; invented records and simulated reserve qualification."""
import json,sqlite3
import pytest
from compertum.data.encoding import canonical
from compertum.fake_attempt_guard import append_record,verify_attempt_guard
from compertum.runtime.errors import RuntimeRefused
from test_native_attempt_records import records,attempt,AT
from test_paper_intent_journal import paper,native

@pytest.fixture
def journal(paper,monkeypatch):
 from compertum.native_write_journal import _NativeWriteJournal
 monkeypatch.setattr('compertum.native_write_journal.execution_durable',lambda *args:None)
 project,lease,store,old,protected=paper
 return project,lease,store,_NativeWriteJournal(store,old.reserve)

def consume(fixture,p=None,d=None):
 _,lease,store,journal=fixture
 if p is None:p,d=records(lease)
 with store.conn:
  store.conn.execute('BEGIN IMMEDIATE')
  result=journal.consume(p,d,now=AT)
 return p,d,result

def test_consumption_precedes_any_effect_and_never_repeats(journal):
 project,lease,store,j=journal;p,d,first=consume(journal)
 assert first['first_consumption'] and first['record']['status']=='NATIVE_CONSUMED'
 assert first['transport_authorized'] is first['financial_accepted'] is False
 _,_,again=consume(journal,p,d)
 assert not again['first_consumption']
 assert verify_attempt_guard(project)['records']==[attempt(p,d)]
 assert store.conn.execute('SELECT count(*) FROM fake_intents').fetchone()==(1,)

def test_consumption_requires_its_callers_explicit_transaction(journal):
 _,lease,store,j=journal;p,d=records(lease)
 with pytest.raises(RuntimeRefused):j.consume(p,d,now=AT)
 assert not store.conn.in_transaction

def test_guard_only_crash_restores_unknown_and_never_another_send(journal):
 from compertum.native_write_journal import _NativeWriteJournal
 project,lease,store,j=journal;p,d=records(lease)
 with store.conn:assert append_record(store,attempt(p,d))['first']
 restored=_NativeWriteJournal(store,j.reserve)
 assert restored.read('fixture',p['intent_id'])['status']=='NATIVE_UNKNOWN'
 with store.conn:
  store.conn.execute('BEGIN IMMEDIATE')
  assert not restored.consume(p,d,now=AT)['first_consumption']
 assert verify_attempt_guard(project)['sequence']==1

def test_older_database_cannot_erase_consumption(journal,tmp_path):
 from compertum.native_write_journal import _NativeWriteJournal
 project,lease,store,j=journal;older=sqlite3.connect(tmp_path/'older.sqlite')
 try:
  store.conn.backup(older);p,d,_=consume(journal);older.backup(store.conn)
  restored=_NativeWriteJournal(store,j.reserve)
  assert restored.read('fixture',p['intent_id'])['status']=='NATIVE_UNKNOWN'
  with store.conn:
   store.conn.execute('BEGIN IMMEDIATE')
   assert not restored.consume(p,d,now=AT)['first_consumption']
  assert verify_attempt_guard(project)['records']==[attempt(p,d)]
 finally:older.close()

def test_ignored_insert_keeps_external_consumption(journal):
 from compertum.native_write_journal import _NativeWriteJournal
 project,lease,store,j=journal;p,d=records(lease)
 with store.conn:store.conn.execute("CREATE TRIGGER ignore_native_insert BEFORE INSERT ON fake_intents BEGIN SELECT RAISE(IGNORE); END")
 with pytest.raises(RuntimeRefused):consume(journal,p,d)
 assert verify_attempt_guard(project)['records']==[attempt(p,d)]
 assert store.conn.execute('SELECT count(*) FROM fake_intents').fetchone()==(0,)
 # Remove this test's injected fault. Preserve its original attempt.
 with store.conn:store.conn.execute('DROP TRIGGER ignore_native_insert')
 assert _NativeWriteJournal(store,j.reserve).read('fixture',p['intent_id'])['status']=='NATIVE_UNKNOWN'

def test_rolled_back_consumption_keeps_external_guard(journal):
 from compertum.native_write_journal import _NativeWriteJournal
 project,lease,store,j=journal;p,d=records(lease)
 store.conn.execute('BEGIN IMMEDIATE')
 assert j.consume(p,d,now=AT)['first_consumption'];store.conn.rollback()
 assert verify_attempt_guard(project)['records']==[attempt(p,d)]
 assert _NativeWriteJournal(store,j.reserve).read('fixture',p['intent_id'])['status']=='NATIVE_UNKNOWN'

def test_unknown_effect_blocks_an_unrelated_new_attempt(journal):
 project,lease,store,j=journal;consume(journal)
 with pytest.raises(RuntimeRefused):consume(journal)
 assert verify_attempt_guard(project)['sequence']==1

def test_native_recovery_keeps_fake_readers_disjoint(journal):
 from compertum.fake_execution_journal import FakeIntentJournal
 project,lease,store,j=journal;fake=FakeIntentJournal(store);before=fake.status()
 p,d,_=consume(journal)
 assert fake.status()==before
 with pytest.raises(RuntimeRefused,match='INTENT_SCOPE_MISMATCH'):fake.read('fixture',p['intent_id'])

@pytest.mark.parametrize('fault',['body','decision','client','state'])
def test_changed_retained_rows_refuse(journal,fault):
 _,lease,store,j=journal;p,d,_=consume(journal)
 with store.conn:
  if fault=='body':store.conn.execute("UPDATE fake_intents SET body='{}'")
  elif fault=='decision':store.conn.execute("UPDATE fake_intents SET decision='{}'")
  elif fault=='client':store.conn.execute("UPDATE fake_intents SET client_id='cmp-changed'")
  else:store.conn.execute("UPDATE fake_intents SET state='PAPER_CONSUMED'")
 with pytest.raises(RuntimeRefused):j.read('fixture',p['intent_id'])
