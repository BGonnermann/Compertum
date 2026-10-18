"""Accepted finite local closing. Restart never recreates a submission grant."""
from copy import deepcopy
from datetime import timedelta
import hashlib,json
from compertum.data.encoding import canonical
from compertum.fake_attempt_guard import require_attempt_guard
from compertum.fixture_closing import next_close_child,settle_close_child
from compertum.native_attempt_records import native_client_id,sha
from compertum.native_write_journal import _logical_snapshot,_replace
from compertum.paper_contracts import number,timestamp
from compertum.paper_portfolio import TERMINAL
from .errors import RuntimeRefused
from .owners import _MUTEX,_owner_scope
from .paper_fixture_send_commit import _ProofWriteCall,_ConsumeCall
from .paper_fixture_risk import fixture_risk_context,_join,_INVALID
from .paper_fixture_economics import fixture_economic_context
from . import paper_fixture_economics as economic_module
from .paper_reconciliation_context import _capture_originals
from .paper_presence import _PresenceOwner
from .paper_preflight import _measure
from .paper_final_proof import _verify_proofs
from .paper_credential_slot import load_paper_slot

_FACTORY=object()
def _need(value,code='FIXTURE_CLOSING_CONTEXT_CHANGED'):
 if not value:raise RuntimeRefused(code)

class _ParentWriteCall(_ProofWriteCall):
 def __init__(self,parent,proofs,target,source_check,*,complete=False):
  super().__init__(parent.owner,parent.component.journal,proofs)
  self.parent=parent;self.target=canonical(target);self._target_pin=self.target;self.complete=complete
  _need(callable(source_check));self._source_check=self._source_check_pin=source_check
 def _same(self,used):
  super()._same(used);self.parent._pure();_need(self.target==self._target_pin and self._source_check is self._source_check_pin)
 def _before_write(self):
  self.parent._records();self.parent._age(accounting=self.complete);self._source_check()
 def _write(self,now):self.parent._put(json.loads(self.target));self._source_check()
 def close(self):
  super().close();self._source_check=self._source_check_pin=None;self.parent=None;self.target=self._target_pin=b''

class _ParentConsumeCall(_ConsumeCall):
 def __init__(self,producer,p,d,proofs):
  child=producer._child;_need(type(child) is _CloseRiskContext and child._producer is producer)
  super().__init__(producer._owner,producer._component.journal,p,d,proofs,_source_check=producer._source_check_pin)
  self.child=child;self._child_pin=child;self._parent=child.parent;self._target=child._target
  self._child_identity=child._identity
 def _same(self,used):
  super()._same(used);child=self.child
  _need(child is self._child_pin and child.parent is self._parent and child._identity is self._child_identity)
  _need(child._target==self._target);self._child_identity();child._pure()
 def _before_write(self):
  super()._before_write();self.child.parent._records();self.child.parent._age()
 def _write(self,now):
  child=self.child;_need(not child._committed)
  self._child_identity();self._parent._put(json.loads(self._target));child._committed=True
  super()._write(now)
 def close(self):
  super().close();self.child=self._child_pin=self._parent=self._child_identity=None;self._target=b''

class _ClosingParent:
 def __init__(self,component,root,confirmation,*,_factory=None):
  _need(_factory is _FACTORY)
  self.component=component;self.owner=component.owner;self._root=json.loads(canonical(root));self._confirmation=json.loads(canonical(confirmation))
  self._root_pin=canonical([root,confirmation]);self._intents=self.owner._intents;self._instance=self._intents.instance
  self._issued=self._intents._issued.get(root['intent_id']);_need(self._issued is not None)
  self._resources=(self.owner.store,self.owner.reserve,self.owner.health,self.owner.lease,self.owner.db)
  self._key='fixture_closing_parent:'+root['intent_id'];self._state=None;self.closed=False
 def __repr__(self):return '<PrivateFiniteFixtureClosing original values redacted>'
 def __reduce_ex__(self,protocol):raise RuntimeRefused('FIXTURE_CLOSING_SERIALIZATION_FORBIDDEN')
 def _pure(self):
  self.component._same();owner=self.owner;intents=self._intents;root=self._root
  _need(not self.closed and self.component.parents.get(root['intent_id']) is self)
  _need(owner._intents is intents and not intents._closed and intents.parent is owner and intents.db is owner.db)
  _need(intents.instance==self._instance and intents._reason is None)
  _need(all(a is b for a,b in zip(self._resources,(owner.store,owner.reserve,owner.health,owner.lease,owner.db))))
  _need(root['owner_generation']==owner.lease.generation and root['owner_instance']==owner.lease.identity.process_instance_id)
  _need(canonical([root,self._confirmation])==self._root_pin and intents._issued.get(root['intent_id']) is self._issued)
  _need(self._issued[0]==sha(root) and intents._confirmed.get(root['intent_id'])==sha(self._confirmation))
  # Acceptance replaces only the start window. Explicit revocation, changed
  # evidence, service gaps and every other recorded failure still refuse.
  _need(intents._revoked.get(root['intent_id']) in (None,'PAPER_INTENT_EXPIRED'),'PAPER_INTENT_INVALIDATED')
 def _records(self):
  try:
   self._pure();owner=self.owner;root=self._root
   _need(self._intents._read(root['intent_id'])==root and self._intents._confirmation(root)==self._confirmation)
   _need(self._intents._reason_for(root['intent_id']) in (None,'PAPER_INTENT_EXPIRED'),'PAPER_INTENT_INVALIDATED')
   protected=load_paper_slot(owner.lease,root['account_alias'])
   _need(hashlib.sha256(protected.ciphertext).hexdigest()==root['credential_sha256'])
   row=owner.db.execute('SELECT CASE WHEN length(CAST(value AS BLOB))<=16384 THEN value END FROM state WHERE key=?',(self._key,)).fetchone()
   _need(row==(self._state.decode(),) if self._state is not None else row is None,'FIXTURE_CLOSING_STATE_CHANGED')
  except (RuntimeRefused,*_INVALID):
   self.closed=True;raise RuntimeRefused('FIXTURE_CLOSING_STATE_CHANGED') from None
 def _age(self,*,accounting=False):
  self._pure();now,mono=self._intents._clock();root=self._root
  du=(now-timestamp(root['created_at'])).total_seconds();dm=mono-root['created_mono']
  _need(du>=0 and dm>=0 and abs(du-dm)<=5,'PAPER_INTENT_CLOCK_CHANGED')
  if not accounting:
   limit=(timestamp(root['operation_deadline'])-timestamp(root['created_at'])).total_seconds()
   _need(du<limit and dm<limit,'FIXTURE_CLOSING_DEADLINE')
  return now,mono
 def _put(self,value):
  db=self.owner.db;_need(db.in_transaction,'NATIVE_WRITE_TRANSACTION_REQUIRED');self._records()
  before=_logical_snapshot(db);guard=require_attempt_guard(self.owner.store);raw=canonical(value)
  _need(len(raw)<=16384)
  if self._state is None:changed=db.execute('INSERT INTO state VALUES(?,?)',(self._key,raw.decode()))
  else:changed=db.execute('UPDATE state SET value=? WHERE key=? AND value=?',(raw.decode(),self._key,self._state.decode()))
  _need(changed.rowcount==1,'FIXTURE_CLOSING_WRITE_UNVERIFIED')
  expected=deepcopy(before);_replace(expected['rows']['state'],self._key,[self._key,raw.decode()])
  _need(canonical(_logical_snapshot(db))==canonical(expected),'NATIVE_WRITE_UNEXPECTED_MUTATION')
  _need(canonical(require_attempt_guard(self.owner.store))==canonical(guard),'EXECUTION_COMPROMISED')
  self._state=raw
 def _progress(self,originals):
  self._records();_need(self._state is not None);state=json.loads(self._state);_need(state['status']=='ACTIVE')
  root=self._root;index=state['index'];completed=state['completed_quantity']
  child=next_close_child(root_id=root['intent_id'],terms=root['terms'],index=index,completed_quantity=completed,active=None)
  if state['active'] is not None:
   _need(child is not None and state['active']==dict(intent_id=child['intent_id'],quantity=child['quantity']))
   row=self.component.journal._row(root['account_alias'],child['intent_id']);p=row['intent'];body=p['request']['body']
   _need(p['purpose']=='CLOSE_LONG' and body['side']=='sell' and body['qty']==str(child['quantity']))
   _need(p['evidence_sha256']['intent']==sha(root) and p['evidence_sha256']['confirmation']==sha(self._confirmation))
   matches=[order for order in originals['orders'] if order['client_order_id']==p['client_order_id']]
   _need(len(matches)==1 and matches[0]['id']==row['order_id'] and matches[0]['status']=='filled'
    and number(matches[0]['filled_qty'])==child['quantity'],'FIXTURE_CLOSING_CHILD_UNRESOLVED')
   progress=settle_close_child(child,state=row['status'],filled_quantity=row['filled_quantity'])
   index=progress['index'];completed=progress['completed_quantity']
   child=next_close_child(root_id=root['intent_id'],terms=root['terms'],index=index,completed_quantity=completed,active=None)
  return state,index,completed,child
 def _presence(self,subject,packet_id,presence_id):
  owner=self.owner;root=self._root;presence=owner._presence
  _need(subject==root['subject_key'] and type(presence) is _PresenceOwner and presence.parent is owner)
  proof=presence._prepare_proof(subject=subject,presence_id=presence_id);p=json.loads(proof._content)
  _need(p['packet_id']==packet_id and all(p[k]==root[k] for k in ('subject_key','account_alias','credential_sha256','identity_sha256','owner_instance','owner_generation')))
  return proof,p,presence
 def prepare_child(self,*,subject,packet_id,fresh_job_id,capture_id,activity_id,presence_id):
  from .paper_fixture_orders import _FixtureOrderProducer
  with _MUTEX:
   self._records();self._age();_need(self.component.active is None,'FIXTURE_ORDER_ACTIVE')
   child=_CloseRiskContext(self,subject,packet_id,fresh_job_id,capture_id,activity_id,presence_id,_factory=_FACTORY)
   try:
    _need(self.component.active is None,'FIXTURE_ORDER_ACTIVE')
    producer=_FixtureOrderProducer(self.component,subject,child._projection['intent_id'],activity_id,_child=child)
    child._producer=producer;self.component.active=producer;return producer
   except BaseException:child.close();raise
 def finish(self,*,subject,packet_id,activity_id,presence_id):
  with _MUTEX:
   economic=None;call=None
   try:
    self._records();_need(self.component.active is None,'FIXTURE_ORDER_ACTIVE')
    economic=fixture_economic_context(self.owner,subject=subject,packet_id=packet_id,activity_id=activity_id)
    proof,p,presence=self._presence(subject,packet_id,presence_id)
    _,_,originals,_,_,_,_=_capture_originals(self.owner,economic._context,economic._portfolio,activity_id,allow_unsupported=True)
    state,index,completed,child=self._progress(originals)
    _need(child is None and not originals['positions'] and all(row['status'] in TERMINAL for row in originals['orders']))
    proofs=(economic._prepare_proof(),proof);check=proofs[0]._check;finish=proofs[0]._finish;pure=proofs[0]._final_identity
    def original():check();self._records()
    def last():finish();self._age(accounting=True)
    def identity():
     if pure is not None:pure()
     self._pure();_presence_identity(self.owner,presence,p)
    proofs[0]._check=original;proofs[0]._finish=last;proofs[0]._final_identity=identity
    target=dict(state,index=index,completed_quantity=completed,active=None,status='COMPLETE')
    call=_ParentWriteCall(self,proofs,target,_economic_source_check(economic),complete=True);call.commit(now=_measure()[0].isoformat());call.identity()
    result=dict(scope='CONTROLLED_LOCAL_CLOSING',status='COMPLETE',fixture_flat=True,completed_children=index,
     transport_authorized=False,financial_accepted=False,actual_flat=None,automatic_send=False)
    self.closed=True;return result
   finally:
    if call is not None:call.close()
    if economic is not None:economic.close()
 def close(self):
  self.closed=True;active=self.component.active
  if active is not None and active._child is not None and active._child.parent is self:active.close()

def _economic_source_check(economic):
 owner=economic._owner
 _,base,originals,_,_,_,_=_capture_originals(owner,economic._context,economic._portfolio,economic._activity_id,allow_unsupported=True)
 _,binding,check=economic_module._source_snapshot(owner,economic._context,base,originals)
 _need(economic._binding==sha(dict(base,source=binding,calculation_sha256=sha(json.loads(economic._calculation)))))
 return check

def _presence_identity(owner,presence,p):
 _need(owner._presence is presence and presence.parent is owner and presence.db is owner.db and not presence._closed)
 _need(presence.instance==p['component_id'] and presence._reason is None and p['presence_id'] not in presence._revoked)
 _need(presence._issued.get(p['presence_id'])==sha(p))

class _CloseRiskContext:
 def __init__(self,parent,subject,packet_id,fresh_job_id,capture_id,activity_id,presence_id,*,_factory=None):
  _need(_factory is _FACTORY);self.parent=parent;self._owner=parent.owner;self._producer=None;self._closed=False;self._committed=False
  owner=self._owner;self._subject=subject;self._activity=activity_id;self._presence_id=presence_id
  self._context=owner.input_context(subject=subject,packet_id=packet_id,fresh_job_id=fresh_job_id,capture_id=capture_id)
  self._identities=self._context._identities;self._context_binding=self._context._binding
  self._economic=fixture_economic_context(owner,subject=subject,packet_id=packet_id,activity_id=activity_id)
  self._before=parent._state
  try:
   proof,p,presence=parent._presence(subject,packet_id,presence_id)
   # This is a child calculation projection. No native confirmation is made.
   now,mono=parent._age();expires=min(now+timedelta(seconds=60),timestamp(parent._root['operation_deadline']),timestamp(p['expires_at']))
   self._projection=dict(parent._root,packet_id=packet_id,fresh_job_id=fresh_job_id,capture_id=capture_id,
    presence_id=presence_id,presence_sha256=sha(p),context_sha256=self._context_binding,
    created_at=now.isoformat(),created_mono=mono,expires_at=expires.isoformat())
   self._presence=presence;self._presence_value=p
   # Consume this initial presence proof normally; later captures create fresh proofs.
   _verify_proofs(proof)
   proofs,pin,calculation,evidence,target=self._capture()
   self._binding=pin;self._calculation=calculation;self._evidence=canonical(evidence);self._target=canonical(target)
   self._projection_pin=canonical(self._projection)
   context=self._context;economic=self._economic;before=self._before;projection=self._projection_pin
   evidence_raw=self._evidence;target_raw=self._target;presence_value=canonical(p)
   def identity():
    _need(self.parent is parent and self._owner is owner and self._context is context and self._economic is economic)
    _need(self._presence is presence and canonical(self._presence_value)==presence_value)
    _need(self._before==before and self._binding==pin and self._calculation==calculation)
    _need(self._evidence==evidence_raw and self._target==target_raw)
    _need(canonical(self._projection)==projection and self._projection_pin==projection)
    _need(parent._state==(target_raw if self._committed else before))
   self._identity=identity;_verify_proofs(*proofs)
  except BaseException:self.close();raise
 def __repr__(self):return '<PrivateAcceptedCloseChild original values redacted>'
 def __reduce_ex__(self,protocol):raise RuntimeRefused('FIXTURE_CLOSING_SERIALIZATION_FORBIDDEN')
 def _pure(self):
  if hasattr(self,'_identity'):self._identity()
  parent=self.parent;owner=self._owner;parent._pure();_need(not self._closed and not self._economic._closed)
  _need(parent.owner is owner and owner._input_context is self._context and not self._context._closed)
  _need(self._context._owner is owner and self._context._binding==self._context_binding and self._context._identities is self._identities)
  _need(self._context._generation==owner.lease.generation and self._context._instance==owner.lease.identity.process_instance_id)
  preflight,proposal,market,producer,view,held,combined=self._identities
  _need(owner._preflight is preflight and not preflight._closed and owner._account_proposal is proposal and owner._market is market)
  _need(proposal is not None and not proposal._closed and proposal._context is preflight)
  _need(market.parent is owner and market.lease is owner.lease and market._producer is producer and market._fresh_view is view
   and market._opened is held and market._combined is combined)
  _need(not producer._closed and not held._closed and not combined._closed and producer in producer._owner_state.resources
   and held in held._state.resources and combined in combined._state.resources)
  _need(view._pair is producer and producer._view is view and combined._fresh is view and combined._history is held)
  _presence_identity(owner,self._presence,self._presence_value)
  if hasattr(self,'_projection_pin'):_need(canonical(self._projection)==self._projection_pin)
  if hasattr(self,'_target'):_need(parent._state==(self._target if self._committed else self._before))
  if self._producer is not None:_need(parent.component.active is self._producer and self._producer._child is self)
 def _capture(self):
  from .paper_fixture_risk import _arithmetic
  parent=self.parent;owner=self._owner;parent._records();parent._age()
  _need(parent._state==self._before and not self._committed)
  input_proof=self._context._prepare_proof();economic_proof=self._economic._prepare_proof()
  presence,p,current=parent._presence(self._subject,self._context._packet,self._presence_id)
  _need(current is self._presence and p==self._presence_value)
  _,base,originals,metadata,original,_,_=_capture_originals(owner,self._economic._context,self._economic._portfolio,self._activity,allow_unsupported=True)
  source,source_binding,source_check=economic_module._source_snapshot(owner,self._economic._context,base,originals)
  calculation=json.loads(self._economic._calculation)
  _need(self._economic._binding==sha(dict(base,source=source_binding,calculation_sha256=sha(calculation))))
  _need(metadata['provenance']=='LOOPBACK_FIXTURE' and calculation['cash_matches'])
  state,index,completed,child=parent._progress(originals);_need(child is not None,'FIXTURE_CLOSING_ALREADY_COMPLETE')
  self._projection.update(intent_id=child['intent_id'],terms=child['terms'])
  private,risk=_arithmetic(owner,self._projection,source,calculation,p)
  _need(risk['request']['body']['side']=='sell' and risk['request']['body']['qty']==str(child['quantity']))
  evidence=dict(intent=sha(parent._root),confirmation=sha(parent._confirmation),presence=sha(p),opening=base['opening']['sha256'],
   ownership=sha(originals),economics=sha(calculation),risk=sha(risk),inputs=self._context_binding)
  target=dict(state,index=index,completed_quantity=completed,active=dict(intent_id=child['intent_id'],quantity=child['quantity']))
  pin=sha(dict(evidence=evidence,economic=self._economic._binding,parent=self._before.decode(),projection=self._projection,target=target))
  def checked():self._pure();parent._records();original();source_check()
  def finished():self._pure();parent._age();parent._intents._age(self._projection)
  joined=_join(input_proof,economic_proof,dict(scope='CONTROLLED_LOCAL_CLOSE_CHILD',financial_accepted=False,transport_authorized=False),checked,finished,self._pure)
  return (joined,presence),pin,private,evidence,target
 def _prepare_proofs(self):
  self._pure();proofs,pin,calculation,evidence,target=self._capture()
  _need(pin==self._binding and calculation==self._calculation and canonical(evidence)==self._evidence and canonical(target)==self._target)
  return proofs
 def close(self):
  self._closed=True
  if hasattr(self,'_economic'):self._economic.close()

def accept_fixture_close(owner,*,subject,intent_id,activity_id):
 from .paper_fixture_orders import _FixtureOrders
 from .paper_native_intents import _NativeIntents
 with _MUTEX:
  risk=None;call=None;parent=None
  try:
   component=getattr(owner,'_fixture_orders',None);_need(type(component) is _FixtureOrders and component.owner is owner);component._same()
   _need(type(owner._intents) is _NativeIntents and owner._intents.parent is owner and not owner._intents._closed)
   _need(intent_id not in component.parents,'FIXTURE_CLOSING_ALREADY_ACCEPTED')
   _need(component.active is None and len(component.parents)<16 and not any(not p.closed for p in component.parents.values()),'FIXTURE_CLOSING_ACTIVE')
   root=owner._intents._read(intent_id);confirmation=owner._intents._confirmation(root)
   _need(root['purpose']=='CLOSE_LONG' and root['subject_key']==subject and confirmation is not None)
   owner._intents._records_current(root,confirmation);owner._intents._age(root)
   risk=fixture_risk_context(owner,subject=subject,intent_id=intent_id,activity_id=activity_id)
   child=next_close_child(root_id=intent_id,terms=root['terms'],index=0,completed_quantity=0,active=None)
   _need(json.loads(risk._calculation)['request']['body']['qty']==str(child['quantity']))
   parent=_ClosingParent(component,root,confirmation,_factory=_FACTORY);component.parents[intent_id]=parent
   now,mono=owner._intents._age(root)
   state=dict(version=1,scope='CONTROLLED_LOCAL_CLOSING_PARENT',root_id=intent_id,intent_sha256=sha(root),confirmation_sha256=sha(confirmation),
    generation=owner.lease.generation,owner_instance=owner.lease.identity.process_instance_id,component_id=owner._intents.instance,
    accepted_at=now.isoformat(),accepted_mono=mono,operation_deadline=root['operation_deadline'],terms=root['terms'],
    status='ACTIVE',index=0,completed_quantity=0,active=None)
   call=_ParentWriteCall(parent,risk._prepare_proofs(),state,_economic_source_check(risk._economic));call.commit(now=now.isoformat());call.identity();return parent
  except BaseException:
   if parent is not None:parent.close()
   raise
  finally:
   if call is not None:call.close()
   if risk is not None:risk.close()
