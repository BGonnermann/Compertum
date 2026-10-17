"""Call-local native consumption. No retained proof can grant a second send."""
import json
from compertum.data.encoding import canonical
from compertum.native_attempt_records import validate_pair
from compertum.native_write_journal import _NativeWriteJournal
from .errors import RuntimeRefused
from .owners import _MUTEX,_owner_scope
from .paper_final_proof import _FinalProof,_health_live,_health_finish,_health_state,_INVALID

def _need(value,code='FIXTURE_SEND_CONTEXT_CHANGED'):
 if not value:raise RuntimeRefused(code)

class _ConsumeCall:
 """Used only within one trusted native transport constructor."""
 def __init__(self,owner,journal,p,d,proofs):
  _need(type(journal) is _NativeWriteJournal and journal.store is owner.store and journal.db is owner.db)
  _need(not owner.db.in_transaction,'NATIVE_WRITE_TRANSACTION_OPEN')
  _need(type(proofs) is tuple and len(proofs)==2 and len({id(p) for p in proofs})==2)
  _need(all(type(proof) is _FinalProof and not proof._used and proof._owner is owner
   and proof._db is owner.db and proof._lease is owner.lease for proof in proofs),'PAPER_FINAL_PROOF_UNQUALIFIED')
  p,d,_=validate_pair(json.loads(canonical(p)),json.loads(canonical(d)))
  self.owner=owner;self.journal=journal;self.db=owner.db;self.lease=owner.lease;self.store=owner.store
  self.health=owner.health;self.reserve=owner.reserve;self.proofs=proofs;self.p=p;self.d=d
  self._original_proofs=proofs;self._records=canonical([p,d]);self.state='READY';self._health_snapshot=None
  self._pins=tuple((proof._check,proof._finish,proof._invalidate,proof._final_identity,proof._content,proof._health,proof._peer) for proof in proofs)
  self._peer=canonical(self.health.peer)
  _need(all(callable(pin[0]) and callable(pin[1]) and callable(pin[2]) for pin in self._pins))
 def __repr__(self):return '<CallLocalFixtureConsumption private values redacted>'
 def __reduce_ex__(self,protocol):raise RuntimeRefused('FIXTURE_SEND_SERIALIZATION_FORBIDDEN')
 def _same(self,used):
  owner=self.owner
  _need(self.state!='CLOSED' and not owner._closed and owner.db is self.db and owner.lease is self.lease
   and owner.store is self.store and owner.reserve is self.reserve and owner.health is self.health)
  _need(self.journal.store is self.store and self.journal.db is self.db and self.journal.reserve is self.reserve)
  _need(self.proofs is self._original_proofs and canonical([self.p,self.d])==self._records)
  for proof,pin in zip(self.proofs,self._pins):
   _need(proof._owner is owner and proof._db is self.db and proof._lease is self.lease and proof._health is self.health
    and proof._used is used and proof._peer==pin[6] and proof._content==pin[4])
   _need(all(a is b for a,b in zip((proof._check,proof._finish,proof._invalidate,proof._final_identity),pin[:4])))
 def identity(self):
  with _MUTEX:
   _need(self.state=='COMMITTED');self._same(True)
   _need(not self.db.in_transaction,'NATIVE_WRITE_TRANSACTION_OPEN')
   _need(self.health.required is True and self.health.peer_role=='watchdog' and self.health.lease is self.lease
    and canonical(self.health.peer)==self._peer)
   _need(self.health.reason is None and _health_state(self.health)==self._health_snapshot)
   for pin in self._pins:
    if pin[3] is not None:pin[3]()
   self._same(True)
   _need(not self.db.in_transaction,'NATIVE_WRITE_TRANSACTION_OPEN')
   _need(self.health.reason is None and self.health.required is True and self.health.peer_role=='watchdog'
    and self.health.lease is self.lease and canonical(self.health.peer)==self._peer
    and _health_state(self.health)==self._health_snapshot)
 def commit(self,*,now):
  with _MUTEX:
   _need(self.state=='READY','NATIVE_WRITE_ALREADY_CONSUMED');self._same(False)
   _need(not self.db.in_transaction,'NATIVE_WRITE_TRANSACTION_OPEN')
   owned=False
   try:
    for proof in self.proofs:proof._used=True
    self.state='CHECKING'
    with _owner_scope(self.lease),self.store._live():
     for pin in self._pins:pin[0]()
     self._same(True);_need(not self.db.in_transaction,'NATIVE_WRITE_TRANSACTION_OPEN')
     health,state=_health_live(self.owner,self.proofs)
     self.db.execute('BEGIN IMMEDIATE');owned=True
     result=self.journal.consume(self.p,self.d,now=now)
     _need(result['first_consumption'],'NATIVE_WRITE_ALREADY_CONSUMED')
     self.db.commit();owned=False
    # Expected consumption changes were audited inside the journal. Old history
    # callbacks must not run after that write. Only original clocks and captured
    # identities remain, through the final native deadline check.
    for pin in self._pins:pin[1]()
    _health_finish(self.owner,health,state)
    self._health_snapshot=state;self.state='COMMITTED';self.identity()
   except (RuntimeRefused,*_INVALID) as error:
    if owned:self.db.rollback();owned=False
    code=error.code if isinstance(error,RuntimeRefused) else 'FIXTURE_SEND_INVALID'
    try:
     for pin in self._pins:pin[2](code)
    finally:self.close()
    raise RuntimeRefused(code) from None
   finally:
    if owned:self.db.rollback()
 def close(self):
  with _MUTEX:
   if self.state=='CLOSED':return
   for proof in self.proofs:
    proof._used=True;proof._check=proof._finish=proof._invalidate=proof._final_identity=None
    proof._owner=proof._db=proof._lease=proof._health=proof._peer=None;proof._content=b''
   self.state='CLOSED';self._pins=();self.proofs=();self._original_proofs=();self._records=b''
   self.owner=self.journal=self.db=self.lease=self.store=self.health=self.reserve=None;self.p=self.d=None
