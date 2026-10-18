"""Controlled local orders only. Actual broker and financial gates remain closed."""
from copy import deepcopy
import hashlib,json,time
from uuid import uuid4
from compertum.data.encoding import canonical
from compertum.native_attempt_records import native_client_id,validate_pair,sha
from compertum.native_write_journal import _NativeWriteJournal,_logical_snapshot,_expected_event
from compertum.fake_attempt_guard import require_attempt_guard
from compertum.fake_execution_journal import FakeIntentJournal
from compertum.paper_contracts import utc
from .errors import RuntimeRefused
from .owners import _MUTEX,_owner_scope
from ._winhttp_order import _OwnedOrderHTTP,_wire
from ._winhttp_get import _utc_now,_HTTPResult
from .paper_order_qualification import prepare_order_exchange,qualify_order_reply,_PreparedOrderExchange,_PrivateOrderReply
from .paper_fixture_risk import fixture_risk_context,_INVALID
from .paper_fixture_economics import _account_original
from .paper_credential_slot import load_paper_slot
from .fixture_source_binding import native_source_peer,source_file,order_source_file
from .paper_fixture_send_commit import _ConsumeCall
from .service_budget import producer_permit,bind_producer_permit,cancel_producer

def _need(value,code='FIXTURE_ORDER_CONTEXT_CHANGED'):
 if not value:raise RuntimeRefused(code)

def _digest(raw):return hashlib.sha256(raw).hexdigest()

class _FixtureOrderHTTP(_OwnedOrderHTTP):
 def __init__(self,producer,*,_permit):
  from .paper_fixture_closing import _ParentConsumeCall
  _need(type(producer) is _FixtureOrderProducer and _permit is not None)
  producer._check();_need(producer._state=='PENDING' and type(producer._call) in (_ConsumeCall,_ParentConsumeCall))
  _need(producer._call._source_check is producer._source_check_pin and producer._source_check_pin is not None)
  _need(canonical([producer._call.p,producer._call.d])==canonical([producer._p,producer._d]))
  _need((producer._child is None and type(producer._call) is _ConsumeCall)
   or (producer._child is not None and type(producer._call) is _ParentConsumeCall and producer._call.child is producer._child))
  _need(type(producer._port) is int and 1<=producer._port<=65535,'FIXTURE_ORDER_ENDPOINT_REQUIRED')
  self._producer=producer;self._send_call=producer._call;self._armed=False
  self._source_request=producer._pending;self._request_bytes=producer._pending.content
  self._wire_header_sha256=_digest(canonical({'X-Compertum-Test':producer._header}))
  request=producer._pending._verify(producer._lease,producer._protected)
  try:
   remaining=10-(time.monotonic()-producer._prepared_at);_need(0<remaining<=10,'HTTP_DEADLINE_EXCEEDED')
   super().__init__(producer._lease,operation=request['operation'],parameters=request['parameters'],body=request['body'],
    headers={'X-Compertum-Test':producer._header},timeout=remaining,_test_port=producer._port,_permit=_permit,
    _deadline_at=producer._prepared_at+10)
  finally:
   self._armed=False;self._send_call.close();self._send_call=None;self._producer=None
 def _native_initialized(self):
  _need(self._producer._native is None);self._producer._native=self;self._producer._native_pin=self
 def _before_send(self):self._producer._before_native_send()
 def _send_committed(self):
  self._send_call.commit(now=self._producer._now());self._armed=True
 def _check_deadline(self):
  super()._check_deadline()
  if self._armed:self._send_call.identity();self._producer._pure()

class _FixtureOrders:
 def __init__(self,owner):
  from .paper_read_owner import PaperReadOwner
  _need(type(owner) is PaperReadOwner and not owner._closed and not owner.db.in_transaction)
  self.owner=owner;self.journal=_NativeWriteJournal(owner.store,owner.reserve);self.active=None;self.closed=False;self.parents={}
  self._owners=(owner.store,owner.reserve,owner.health,owner.lease,owner.db)
 def __repr__(self):return '<ControlledLocalOrderComponent private values redacted>'
 def __reduce_ex__(self,protocol):raise RuntimeRefused('FIXTURE_ORDER_SERIALIZATION_FORBIDDEN')
 def _same(self):
  owner=self.owner
  _need(not self.closed and not owner._closed and getattr(owner,'_fixture_orders',None) is self
   and self in owner._guard.resources and owner in owner._guard.resources)
  _need(all(a is b for a,b in zip(self._owners,(owner.store,owner.reserve,owner.health,owner.lease,owner.db))))
 def prepare(self,*,subject,intent_id,activity_id):
  with _MUTEX:
   self._same();_need(self.active is None,'FIXTURE_ORDER_ACTIVE')
   value=_FixtureOrderProducer(self,subject,intent_id,activity_id);self.active=value;return value
 def close(self):
  with _MUTEX:
   if self.closed:return
   if self.active is not None:self.active.close()
   for parent in self.parents.values():parent.close()
   self.closed=True
 def _retain(self,producer,reply):
  self._same();_need(type(reply) is _PrivateOrderReply and reply.request is producer._pending)
  reply.request._verify(producer._lease,producer._protected);p=producer._p;value=reply.to_payload()
  _need(value['request_sha256']==p['request_sha256'] and value['raw_sha256']==_digest(reply.raw))
  event=dict(at=value['received_at'],qualified_reply=value);key=(p['account_alias'],p['intent_id'])
  with self.journal._transaction():
   before=_logical_snapshot(self.owner.db);require_attempt_guard(self.owner.store)
   row=self.journal._row(*key);_need(row['intent']==p and row['binding']==producer._d)
   found=self.owner.db.execute("SELECT body FROM fake_intent_events WHERE account=? AND intent_id=? AND kind='NATIVE_REPLY_QUALIFIED' LIMIT 2",key).fetchall()
   _need(not found,'FIXTURE_ORDER_REPLY_ALREADY_RETAINED')
   FakeIntentJournal._event(self.journal,*key,'NATIVE_REPLY_QUALIFIED',event)
   expected=deepcopy(before);_expected_event(expected,key,'NATIVE_REPLY_QUALIFIED',event)
   _need(canonical(_logical_snapshot(self.owner.db))==canonical(expected),'NATIVE_WRITE_UNEXPECTED_MUTATION')

class _FixtureOrderProducer:
 def __init__(self,component,subject,intent_id,activity_id,*,_child=None):
  component._same();self._component=component;self._owner=component.owner;self._lease=self._owner.lease
  self._subject=subject;self._intent_id=intent_id;self._activity_id=activity_id
  self._child=_child
  if _child is None:
   root=self._owner._intents._read(intent_id)
   _need(root['purpose'] in {'FIXTURE_BUY','FIXTURE_RESTING_BUY','CANCEL'},'FIXTURE_CLOSE_PARENT_REQUIRED')
  else:
   from .paper_fixture_closing import _CloseRiskContext
   _need(type(_child) is _CloseRiskContext and _child.parent.component is component and not _child._closed)
   root=_child._projection;_need(root['purpose']=='CLOSE_LONG' and root['intent_id']==intent_id)
  _need(root['subject_key']==subject)
  self._purpose=root['purpose'];self._intent_pin=sha(root)
  self._closed=False;self._state='READY';self._deadline_ns=time.monotonic_ns()+90*10**9
  self._pending=self._native=self._native_pin=self._call=self._protected=self._risk=None;self._result=None
  self._port=self._header=self._prepared_at=None;self._wire_pin=None;self._source_check_pin=None
 def __repr__(self):return '<ControlledLocalOrderProducer private values redacted>'
 def __reduce_ex__(self,protocol):raise RuntimeRefused('FIXTURE_ORDER_SERIALIZATION_FORBIDDEN')
 def _pure(self):
  self._component._same();_need(self._component.active is self and not self._closed and self._owner is self._component.owner)
  _need(self._lease is self._owner.lease and self._state in {'READY','PENDING'})
  if self._wire_pin is not None:
   request,content,port,header,prepared,records,protected,call,source_check=self._wire_pin
   _need(self._pending is request and request.content==content and self._port==port and self._header==header
    and self._prepared_at==prepared and self._protected is protected and canonical([self._p,self._d])==records
    and self._call is call and self._source_check_pin is source_check)
   _need(self._native is self._native_pin)
  if self._child is not None:self._child.parent._pure()
 def _check(self):
  self._pure();_need(not self._owner.db.in_transaction,'NATIVE_WRITE_TRANSACTION_OPEN')
  _need(time.monotonic_ns()<self._deadline_ns,'FIXTURE_ORDER_QUEUE_EXPIRED')
  if self._pending is not None:self._pending._verify(self._lease,self._protected)
 def _now(self):return utc(self._owner._intents._age(self._root)[0].isoformat())
 def _source(self):
  economic,economic_id=source_file(self._lease);orders,order_id=order_source_file(self._lease)
  peer=native_source_peer(self._lease,self._port)
  return canonical(dict(economic=economic,economic_id=economic_id,orders=orders,order_id=order_id,peer=peer))
 def _before_native_send(self):
  self._check();_need(self._source()==self._source_pin,'FIXTURE_ORDER_SOURCE_CHANGED')
 def _prepare(self):
  owner=self._owner
  root=owner._intents._read(self._intent_id) if self._child is None else self._child._projection
  _need(root['subject_key']==self._subject)
  _need(sha(root)==self._intent_pin and root['purpose']==self._purpose)
  _need(root['purpose']!='CLOSE_LONG' or self._child is not None,'FIXTURE_CLOSE_PARENT_REQUIRED')
  self._root=root;self._protected=load_paper_slot(self._lease,root['account_alias'])
  self._risk=fixture_risk_context(owner,subject=self._subject,intent_id=self._intent_id,activity_id=self._activity_id) if self._child is None else self._child
  _,source,witness,_,_=_account_original(owner,root['account_alias'],root['packet_id'])
  self._port=witness['port'];_need(native_source_peer(self._lease,self._port)==witness['peer'])
  economic,_=source_file(self._lease);orders,_=order_source_file(self._lease)
  _need(source['order_source']['journal_sha256']==orders['journal_sha256'])
  client=native_client_id(self._lease.project_id,root['account_alias'],root['intent_id'])
  calculation=json.loads(self._risk._calculation);request=calculation['request'];body=request['body']
  if body is not None:body=dict(body,client_order_id=client)
  self._prepared_at=time.monotonic();at=self._now()
  self._pending=prepare_order_exchange(self._lease,self._protected,account_id=owner._preflight._account_id,
   request_id=str(uuid4()),intent_id=root['intent_id'],operation=request['operation'],created_at=at,parameters=request['parameters'],body=body)
  self._p=dict(version=1,record_type='NativePaperWrite',scope='NATIVE_PAPER_WRITE',project_id=self._lease.project_id,
   account_alias=root['account_alias'],intent_id=root['intent_id'],generation=self._lease.generation,
   owner_instance=self._lease.identity.process_instance_id,created_at=at,expires_at=utc(root['expires_at']),purpose=root['purpose'],
   client_order_id=client,evidence_sha256=json.loads(self._risk._evidence),request=self._pending.to_payload(),request_sha256=self._pending.sha256)
  self._d=dict(version=1,record_type='NativePaperWriteBinding',scope='RETAINED_EVIDENCE_ONLY',intent_sha256=sha(self._p),transport_authorized=False,financial_accepted=False)
  validate_pair(self._p,self._d)
  self._header='synthetic_'+client+'_'+economic['ledger']['ledger_head_sha256']+'_'+orders['journal_sha256']
  self._source_pin=self._source()
  def source_check():
   self._pure();_need(self._source()==self._source_pin,'FIXTURE_ORDER_SOURCE_CHANGED')
  self._source_check_pin=source_check
  if self._child is None:self._call=_ConsumeCall(owner,self._component.journal,self._p,self._d,self._risk._prepare_proofs(),_source_check=source_check)
  else:
   from .paper_fixture_closing import _ParentConsumeCall
   self._call=_ParentConsumeCall(self,self._p,self._d,self._risk._prepare_proofs())
  self._wire_pin=(self._pending,self._pending.content,self._port,self._header,self._prepared_at,canonical([self._p,self._d]),self._protected,self._call,source_check)
 def dispatch(self):
  with _MUTEX:
   self._check();_need(self._state=='READY','FIXTURE_ORDER_ALREADY_STARTED')
   permit=producer_permit(self)
   if permit is None:return 'WAITING'
   try:
    self._prepare();self._state='PENDING';bind_producer_permit(self,permit)
    self._native=_FixtureOrderHTTP(self,_permit=permit);return 'PENDING'
   except (RuntimeRefused,*_INVALID):self.close();raise
   finally:
    if self._risk is not None:self._risk.close()
 def poll(self):
  with _MUTEX:
   if self._result is not None:return self._result
   self._check();_need(self._state=='PENDING' and self._native is not None)
   try:
    raw=self._native.poll()
    if raw is None:return None
    self._verify_reply(raw)
    reply=qualify_order_reply(self._lease,self._protected,self._pending,raw.body,status=raw.status_code,received_at=_utc_now().isoformat())
    self._component._retain(self,reply);self._state='COMPLETE'
    self._result=dict(scope='CONTROLLED_LOCAL_DISPATCH',intent_id=self._intent_id,reply_status=reply.to_payload()['outcome'],
     effect_status='UNRECONCILED',transport_authorized=False,financial_accepted=False,retry_authorized=False)
    return self._result
   except (RuntimeRefused,*_INVALID):self.close();raise
 def _verify_reply(self,result):
  native=self._native
  _need(type(native) is _FixtureOrderHTTP and native is self._native_pin and type(result) is _HTTPResult
   and native._result is result and native.native_closed is True and native._closed is True
   and native._cleanup_failed is False,'FIXTURE_ORDER_NATIVE_REPLY_UNVERIFIED')
  _need(native._source_request is self._pending and native._request_bytes==self._pending.content
   and native._lease is self._lease and native._origin==('127.0.0.1',self._port,False),'FIXTURE_ORDER_NATIVE_REPLY_UNVERIFIED')
  request=self._pending._verify(self._lease,self._protected);method,target,body=_wire(request['operation'],request['parameters'],request['body'])
  _need(native._method==method and native._wire_path==target and native._wire_body_sha256==_digest(body)
   and native._wire_header_sha256==_digest(canonical({'X-Compertum-Test':self._header})),'FIXTURE_ORDER_NATIVE_REPLY_UNVERIFIED')
 def close(self):
  with _MUTEX:
   cancel_producer(self)
   try:
    if self._native is not None:self._native.close()
   finally:
    if self._call is not None:self._call.close()
    if self._risk is not None:self._risk.close()
    self._closed=True
    if self._component.active is self:self._component.active=None

def install_fixture_orders(owner):
 with _MUTEX,_owner_scope(owner.lease),owner.store._live():
  _need(getattr(owner,'_fixture_orders',None) is None,'FIXTURE_ORDER_COMPONENT_ALREADY_INSTALLED')
  component=_FixtureOrders(owner);owner._fixture_orders=component;owner._guard.resources.append(component);return component
