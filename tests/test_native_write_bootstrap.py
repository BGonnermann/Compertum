"""First native journal use in a real fresh store with no fake execution tables."""
import pytest
from compertum.fake_attempt_guard import verify_attempt_guard
from test_native_write_journal import paper,native,records,consume

def test_fresh_store_can_record_native_consumption_without_fake_startup(paper,monkeypatch):
 from compertum.native_write_journal import _NativeWriteJournal
 project,lease,store,prior,_=paper
 monkeypatch.setattr('compertum.native_write_journal.execution_durable',lambda *args:None)
 # Only this fresh test's empty tables are removed. No retained attempt exists.
 assert verify_attempt_guard(project)['records']==[]
 with store.conn:
  names=[row[0] for row in store.conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'fake_%'")]
  for name in names:store.conn.execute('DROP TABLE "'+name.replace('"','""')+'"')
 j=_NativeWriteJournal(store,prior.reserve)
 from types import SimpleNamespace
 from compertum.runtime.paper_account_binding import _history
 owner=SimpleNamespace(store=store,db=store.conn)
 assert _history(owner)['status']=='VERIFIED_HISTORY'
 p,d,first=consume((project,lease,store,j))
 assert first['first_consumption'] and j.read('fixture',p['intent_id'])['status']=='NATIVE_CONSUMED'
 assert verify_attempt_guard(project)['sequence']==1
 assert _history(owner)['status']=='VERIFIED_HISTORY'
