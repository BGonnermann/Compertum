"""Owned current local accounting. This never creates submission authority."""
import hashlib,json
from compertum.attempt_records import is_native
from compertum.data.encoding import canonical
from compertum.fake_attempt_guard import require_attempt_guard
from compertum.fixture_order_journal import decode_order_journal
from compertum.paper_contracts import utc
from .errors import RuntimeRefused
from .owners import _MUTEX,_owner_scope
from .fixture_source_binding import _reserved_source_file,ORDER_SOURCE_PATH,source_file
from .paper_fixture_economics import fixture_economic_context,_account_original
from .paper_fixture_orders import _FixtureOrders
from .paper_fixture_send_commit import _ProofWriteCall
from .paper_presence import _PresenceOwner
from .paper_preflight import _measure
from .paper_fixture_risk import _INVALID

def _need(value,code='FIXTURE_RECONCILIATION_UNVERIFIED'):
 if not value:raise RuntimeRefused(code)

def _idle(lease):
 from ._winhttp_get import _PENDING
 _need(not any(native._lease is lease for native in _PENDING.values()),'FIXTURE_NATIVE_TRANSPORT_PENDING')

class _ObserveCall(_ProofWriteCall):
 """Its exact type is excluded by the native HTTP send gate."""
 def __init__(self,owner,component,proofs,raw,heads,source_check):
  super().__init__(owner,component.journal,proofs)
  self.raw=raw;self.heads=heads;self._source_pin=canonical([raw.hex(),heads]);self.result=None
  self._source_check=self._check_pin=source_check
 def _same(self,used):
  super()._same(used)
  _need(canonical([self.raw.hex(),self.heads])==self._source_pin)
  _need(self._source_check is self._check_pin);_idle(self.lease)
 def _before_write(self):self._source_check();_idle(self.lease)
 def _write(self,now):
  self.result=self.journal._observe_source(self.raw,economic_heads=self.heads,now=now)
  self._source_check();_idle(self.lease)
 def close(self):
  super().close();self.raw=b'';self.heads=();self._source_pin=b'';self._source_check=self._check_pin=None

def reconcile_fixture_orders(owner,*,subject,packet_id,activity_id,presence_id):
 with _MUTEX:
  economic=None;call=None
  try:
   _need(not owner.db.in_transaction,'NATIVE_WRITE_TRANSACTION_OPEN')
   component=getattr(owner,'_fixture_orders',None)
   _need(type(component) is _FixtureOrders and component.owner is owner);component._same()
   _idle(owner.lease)
   active=component.active
   if active is not None:
    _need(active._state=='COMPLETE' and active._native is active._native_pin
     and active._native.native_closed and not active._native._cleanup_failed,'FIXTURE_ORDER_ACTIVE')
    active.close()
   with _owner_scope(owner.lease),owner.store._live():
    context=owner._account_context
    _need(context is not None and context._packet==packet_id and context._subject==subject and not context._closed)
    alias=owner._read(packet_id)['account_alias']
    raw,file_id=_reserved_source_file(owner.lease,ORDER_SOURCE_PATH)
    economic_source,economic_id=source_file(owner.lease)
    heads=(economic_source['genesis_sha256'],*(event['sha256'] for event in economic_source['ledger']['events']))
    decoded=decode_order_journal(raw,economic_heads=heads)
    _need(decoded['origin']['project_id']==owner.lease.project_id and decoded['origin']['account_alias']==alias)
    _,embedded,_,_,_=_account_original(owner,alias,packet_id)
    _need(embedded['order_source']['journal_sha256']==hashlib.sha256(raw).hexdigest())
    economic=fixture_economic_context(owner,subject=subject,packet_id=packet_id,activity_id=activity_id)
    presence=owner._presence;_need(type(presence) is _PresenceOwner and presence.parent is owner and not presence._closed)
    proofs=(economic._prepare_proof(),presence._prepare_proof(subject=subject,presence_id=presence_id))
    p=json.loads(proofs[1]._content);instance=presence.instance
    _need(p['packet_id']==packet_id and p['account_alias']==alias and p['subject_key']==subject)
    def identity():
     component._same()
     _need(owner._account_context is context and not context._closed and not economic._closed)
     _need(owner._presence is presence and presence.parent is owner and presence.db is owner.db and not presence._closed)
     _need(presence.instance==instance==p['component_id'] and presence._reason is None)
     _need(presence._issued.get(presence_id)==hashlib.sha256(canonical(p)).hexdigest() and presence_id not in presence._revoked)
     _need(p['owner_instance']==owner.lease.identity.process_instance_id and p['owner_generation']==owner.lease.generation)
    check=proofs[0]._check;pure=proofs[0]._final_identity
    def original():
     check();identity()
    def source_check():
     _idle(owner.lease)
     _need(_reserved_source_file(owner.lease,ORDER_SOURCE_PATH)==(raw,file_id))
     current,current_id=source_file(owner.lease)
     _need(current_id==economic_id and canonical(current)==canonical(economic_source))
    def final_identity():
     if pure is not None:pure()
     identity()
    proofs[0]._check=original;proofs[0]._final_identity=final_identity
    require_attempt_guard(owner.store);source_check()
   call=_ObserveCall(owner,component,proofs,raw,heads,source_check)
   call.commit(now=utc(_measure()[0].isoformat()));call.identity();result=call.result
   return dict(scope='CONTROLLED_LOCAL_RECONCILIATION',observed_native_count=result['observed_native_count'],
    unresolved_count=result['unresolved_count'],source_journal_sha256=decoded['journal_sha256'],
    fixture_flat=not decoded['inventory']['positions'] and not any(row['status'] not in {'filled','canceled','expired','rejected'} for row in decoded['inventory']['orders']),
    transport_authorized=False,financial_accepted=False,actual_flat=None,automatic_send=False)
  except _INVALID:raise RuntimeRefused('FIXTURE_RECONCILIATION_UNVERIFIED') from None
  finally:
   if call is not None:call.close()
   if economic is not None:economic.close()
