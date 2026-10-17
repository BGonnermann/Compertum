"""Native files and SQLite with invented proofs, clocks, and reserve qualification."""
from types import SimpleNamespace
import pytest
from compertum.fake_attempt_guard import verify_attempt_guard
from compertum.runtime.errors import RuntimeRefused
from compertum.runtime.owners import acquire_owner,release_owner
from compertum.runtime.paper_final_proof import _final_proof
from compertum.runtime.execution_health import MutualHealth
from test_native_write_journal import journal,paper,native,records,AT

@pytest.fixture
def call(journal,monkeypatch):
 from compertum.runtime import execution_health
 project,lease,store,j=journal;w=acquire_owner(project,'watchdog');clock=SimpleNamespace(mono=100.,utc=1000.)
 monkeypatch.setattr(execution_health,'time',SimpleNamespace(monotonic=lambda:clock.mono,time=lambda:clock.utc))
 e=MutualHealth(lease,lambda reason:None,required=True);watch=MutualHealth(w,lambda reason:None,required=False);e.receive(watch.receipt())
 owner=SimpleNamespace(store=store,reserve=j.reserve,db=store.conn,lease=lease,health=e,_closed=False)
 events=[];valid=[True]
 def check():
  assert not store.conn.in_transaction;events.append('read')
 def finish():
  assert not store.conn.in_transaction
  assert verify_attempt_guard(project)['sequence']==1
  assert store.conn.execute("SELECT state FROM fake_intents").fetchone()==('NATIVE_CONSUMED',)
  events.append('finish')
 proofs=tuple(_final_proof(owner,check,finish,lambda reason:events.append('invalidated'),{'fixture':i}) for i in range(2))
 def identity():
  if not valid[0]:raise RuntimeRefused('TEST_IDENTITY_CHANGED')
 for proof in proofs:proof._final_identity=identity
 p,d=records(lease)
 try:yield SimpleNamespace(owner=owner,journal=j,p=p,d=d,proofs=proofs,events=events,clock=clock,valid=valid,project=project)
 finally:release_owner(w)

def prepared(f):
 from compertum.runtime.paper_fixture_send_commit import _ConsumeCall
 return _ConsumeCall(f.owner,f.journal,f.p,f.d,f.proofs)

def test_durable_consumption_precedes_final_checks_and_is_single_use(call):
 value=prepared(call);value.commit(now=AT);value.identity()
 assert call.events==['read','read','finish','finish']
 assert all(proof._used for proof in call.proofs)
 with pytest.raises(RuntimeRefused):value.commit(now=AT)
 value.close()
 assert all(proof._content==b'' and proof._check is None for proof in call.proofs)
 with pytest.raises(RuntimeRefused):value.identity()

def test_caller_transaction_stays_open_and_proofs_remain_unused(call):
 call.owner.db.execute("INSERT INTO state VALUES('caller-pending','true')")
 with pytest.raises(RuntimeRefused):prepared(call)
 assert call.owner.db.in_transaction and not any(proof._used for proof in call.proofs)
 call.owner.db.rollback()

@pytest.mark.parametrize('fault',['identity','health','callback','owner'])
def test_change_after_durable_consumption_cannot_permit_send(call,monkeypatch,fault):
 from compertum.runtime import paper_fixture_send_commit as module
 value=prepared(call);original=module._health_finish
 def after(*args):
  original(*args)
  if fault=='identity':call.valid[0]=False
  elif fault=='health':call.owner.health.reason='TEST_CHANGED'
  elif fault=='callback':call.proofs[0]._final_identity=lambda:None
  else:call.owner._closed=True
 monkeypatch.setattr(module,'_health_finish',after)
 with pytest.raises(RuntimeRefused):value.commit(now=AT)
 assert verify_attempt_guard(call.project)['sequence']==1 and not call.owner.db.in_transaction
 assert call.owner.db.execute('SELECT state FROM fake_intents').fetchone()==('NATIVE_CONSUMED',)
 value.close()

def test_late_identity_change_is_checked_until_native_send_returns(call):
 value=prepared(call);value.commit(now=AT);call.valid[0]=False
 with pytest.raises(RuntimeRefused):value.identity()
 value.close();assert verify_attempt_guard(call.project)['sequence']==1
