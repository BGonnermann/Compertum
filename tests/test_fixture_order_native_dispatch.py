"""Real WinHTTP and stores, with explicit simulated producer authority and peer checks."""
import hashlib,time
from uuid import uuid4
from types import SimpleNamespace
import pytest
from compertum.data.encoding import canonical
from compertum.runtime.errors import RuntimeRefused
from compertum.runtime.paper_credentials import seal_paper_credentials
from compertum.runtime.paper_order_qualification import prepare_order_exchange
from compertum.runtime.service_budget import _install_loopback_queue,producer_permit,bind_producer_permit
from test_native_send_commit import call,journal,paper,native,records,AT,prepared
from test_paper_read_preparation import KEY,SECRET
from test_paper_responses import ACCOUNT
from test_winhttp_order import service
from test_winhttp_get import finish

@pytest.fixture
def producer(call,monkeypatch):
 from compertum.runtime.paper_fixture_orders import _FixtureOrderProducer
 clock=SimpleNamespace(ns=0);q=_install_loopback_queue(call.owner.lease,lambda:clock.ns)
 p=object.__new__(_FixtureOrderProducer);p._lease=call.owner.lease;p._closed=False;p._state='READY';p._deadline_ns=time.monotonic_ns()+90*10**9
 p._pending=None;p._native=None;p._call=None;p._port=None;p._header=None;p._prepared_at=None
 p._protected=seal_paper_credentials(p._lease,'fixture',bytearray(KEY.encode()),bytearray(SECRET.encode()))
 monkeypatch.setattr(_FixtureOrderProducer,'_check',lambda self:None)
 monkeypatch.setattr(_FixtureOrderProducer,'_pure',lambda self:None)
 monkeypatch.setattr(_FixtureOrderProducer,'_before_native_send',lambda self:None)
 p._now=lambda:AT
 return call,p,q,clock

def pending(f,port):
 call,p,q,clock=f;clock.ns=60*10**9
 permit=producer_permit(p);assert permit is not None
 r=call.p['request'];p._pending=prepare_order_exchange(p._lease,p._protected,account_id=ACCOUNT,
  request_id=r['request_id'],intent_id=r['intent_id'],operation=r['operation'],created_at=AT,parameters=r['parameters'],body=r['body'])
 assert p._pending.to_payload()==r
 p._prepared_at=time.monotonic();p._port=port;p._header='synthetic_'+call.p['client_order_id']+'_'+'a'*64+'_'+'b'*64
 p._state='PENDING';p._call=prepared(call);bind_producer_permit(p,permit)
 return permit

def test_native_send_observes_committed_guard_and_database(producer,monkeypatch):
 from compertum.runtime.paper_fixture_orders import _FixtureOrderHTTP
 from compertum.runtime import _winhttp_get as backend
 from compertum.fake_attempt_guard import verify_attempt_guard
 call,p,q,clock=producer;original=backend._API;sent=[]
 def api():
  value=original();send=value.SendRequest
  def checked(*args):
   assert verify_attempt_guard(call.project)['sequence']==1
   assert call.owner.db.execute('SELECT state FROM fake_intents').fetchone()==('NATIVE_CONSUMED',)
   assert p._call.state=='COMMITTED';sent.append(True);return send(*args)
  value.SendRequest=checked;return value
 monkeypatch.setattr(backend,'_API',api)
 with service() as (port,_,seen):
  permit=pending(producer,port);op=_FixtureOrderHTTP(p,_permit=permit);finish(op)
  assert sent==[True] and len(seen)==1 and seen[0]['headers']['X-Compertum-Test']==p._header
  assert op._send_call is None and p._call.state=='CLOSED'
  assert all(proof._check is None for proof in call.proofs)
  assert q.status()['paper_used']==1 and not q.status()['queued']

def test_queue_wait_does_not_create_an_exchange_or_consume(producer):
 call,p,q,clock=producer
 assert producer_permit(p) is None and p._pending is None and q.status()['queued']==1
 from compertum.fake_attempt_guard import verify_attempt_guard
 assert verify_attempt_guard(call.project)['sequence']==0

@pytest.mark.parametrize('fault',['port','method','header','body','direct'])
def test_wrong_prepared_wire_never_reaches_send(producer,monkeypatch,fault):
 from compertum.runtime.paper_fixture_orders import _FixtureOrderHTTP
 from compertum.fake_attempt_guard import verify_attempt_guard
 call,p,q,clock=producer
 with service() as (port,_,seen):
  permit=pending(producer,port)
  if fault=='port':p._port=None
  elif fault=='header':p._header+='changed'
  elif fault=='method':object.__setattr__(p._pending,'content',canonical(dict(p._pending.to_payload(),method='DELETE')))
  elif fault=='body':object.__setattr__(p._pending,'content',canonical(dict(p._pending.to_payload(),body=dict(call.p['request']['body'],qty='2'))))
  with pytest.raises(RuntimeRefused):_FixtureOrderHTTP(p,_permit=None if fault=='direct' else permit)
  assert seen==[] and verify_attempt_guard(call.project)['sequence']==0
  p._call.close()

def test_last_native_deadline_check_catches_a_post_commit_identity_change(producer,monkeypatch):
 from compertum.runtime.paper_fixture_orders import _FixtureOrderHTTP
 from compertum.runtime import _winhttp_get as backend
 from compertum.runtime.paper_fixture_send_commit import _ConsumeCall
 from compertum.fake_attempt_guard import verify_attempt_guard
 call,p,q,clock=producer;original=_ConsumeCall.commit
 def changed(self,**args):original(self,**args);call.valid[0]=False
 monkeypatch.setattr(_ConsumeCall,'commit',changed)
 with service() as (port,_,seen):
  permit=pending(producer,port)
  with pytest.raises(RuntimeRefused):_FixtureOrderHTTP(p,_permit=permit)
  assert seen==[] and verify_attempt_guard(call.project)['sequence']==1
  assert p._call.state=='CLOSED'
