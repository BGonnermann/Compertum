"""Private single-use final checks; never a retained authorization or grant."""
import json,math,sqlite3
from compertum.data.encoding import canonical
from compertum.domain import ContractError
from .errors import RuntimeRefused
from .owners import _MUTEX,_owner_scope
from . import execution_health

_FACTORY=object()
_INVALID=(ContractError,ValueError,TypeError,KeyError,AttributeError,OverflowError,RecursionError,UnicodeError,sqlite3.Error)


def _need(value,code='EXECUTION_HEALTH_UNVERIFIED'):
    if not value:raise RuntimeRefused(code)


def _health_state(health):
    return (health.last_mono,health.last_utc,health.clock_offset,health.observed,health.observed_utc,health.peer_sequence)


def _health_live(owner,proofs):
    health=owner.health
    _need(type(health) is execution_health.MutualHealth and health.lease is owner.lease)
    _need(health.required is True and health.peer_role=='watchdog' and health.peer is not None and health.reason is None)
    _need(all(p._health is health and p._peer==canonical(health.peer) for p in proofs))
    # Native metadata/process reads only. tick/status/halt may commit shared
    # state and must not run at this final boundary.
    health._peer_live(*health.peer)
    return health,_health_state(health)


def _health_finish(owner,health,state):
    _need(owner.health is health and health.lease is owner.lease and health.reason is None and _health_state(health)==state)
    mono=execution_health.time.monotonic();utc=execution_health.time.time()
    _need(all(type(v) in (int,float) and math.isfinite(v) for v in (mono,utc,*state[:5])))
    dm=mono-health.last_mono;du=utc-health.last_utc
    _need(dm>=0 and du>=0,'CLOCK_REVERSED')
    _need(dm<=15 and du<=15,'ELAPSED_CLOCK_GAP')
    _need(abs((utc-mono)-health.clock_offset)<=5,'CLOCK_MISMATCH')
    _need(0<=mono-health.observed<=15 and 0<=utc-health.observed_utc<=15,'PEER_HEARTBEAT_STALE')


class _FinalProof:
    __slots__=('_owner','_db','_lease','_health','_peer','_check','_finish','_invalidate','_final_identity','_content','_used')
    def __init__(self,owner,check,finish,invalidate,value,*,_factory=None):
        if _factory is not _FACTORY:raise RuntimeRefused('PAPER_FINAL_PROOF_UNQUALIFIED')
        self._owner=owner;self._db=owner.db;self._check=check;self._finish=finish;self._invalidate=invalidate
        self._lease=owner.lease;self._health=owner.health;self._peer=canonical(owner.health.peer)
        self._final_identity=None;self._content=canonical(value);self._used=False
    def __repr__(self):return '<PrivatePaperFinalProof redacted>'
    def __reduce_ex__(self,protocol):raise RuntimeRefused('PAPER_FINAL_PROOF_SERIALIZATION_FORBIDDEN')
    def _verify(self):return _verify_proofs(self)[0]


def _verify_proofs(*proofs):
    """Finish every durable read before checking any final original clock."""
    with _MUTEX:
        if not 1<=len(proofs)<=2 or any(type(p) is not _FinalProof for p in proofs):
            raise RuntimeRefused('PAPER_FINAL_PROOF_UNQUALIFIED')
        if len({id(p) for p in proofs})!=len(proofs):raise RuntimeRefused('PAPER_FINAL_PROOF_DUPLICATE')
        if any(p._used for p in proofs):raise RuntimeRefused('PAPER_FINAL_PROOF_CONSUMED')
        owner=proofs[0]._owner
        if any(p._owner is not owner for p in proofs):raise RuntimeRefused('PAPER_FINAL_PROOF_OWNER_MISMATCH')
        consumed=False;failed=None
        try:
            # Revocation uses captured connections, even after owner closure or
            # replacement. A pending caller transaction leaves proofs unused.
            if any(p._db.in_transaction for p in proofs):
                raise RuntimeRefused('PAPER_FINAL_PROOF_TRANSACTION_OPEN')
            for p in proofs:p._used=True
            consumed=True
            if any(p._lease is not owner.lease for p in proofs):raise RuntimeRefused('PAPER_FINAL_PROOF_OWNER_MISMATCH')
            with _owner_scope(owner.lease),owner.store._live():
                if owner._closed:raise RuntimeRefused('PAPER_FINAL_PROOF_OWNER_CLOSED')
                if any(p._db is not owner.db for p in proofs):raise RuntimeRefused('PAPER_FINAL_PROOF_DATABASE_CHANGED')
                for p in proofs:
                    failed=p;p._check()
                failed=None
                if any(p._db.in_transaction for p in proofs):raise RuntimeRefused('PAPER_FINAL_PROOF_TRANSACTION_OPEN')
                health,state=_health_live(owner,proofs)
            # Owner/store scope exits perform native identity reads too. Finish
            # them as common checks before measuring the last clocks. _MUTEX
            # still prevents owner/resource replacement throughout this phase.
            for p in proofs:
                failed=p;p._finish()
            failed=None;_health_finish(owner,health,state)
            # These optional checks compare captured objects only. They must
            # not read files or clocks after the final original clock checks.
            for p in proofs:
                failed=p
                if p._final_identity is not None:p._final_identity()
            failed=None
            values=[]
            for p in proofs:
                failed=p;values.append(json.loads(p._content))
            return tuple(values)
        except RuntimeRefused as error:
            if consumed:
                for p in ((failed,) if failed is not None else proofs):p._invalidate(error.code)
            raise
        except _INVALID:
            consumed=True
            for p in proofs:p._used=True
            for p in ((failed,) if failed is not None else proofs):p._invalidate('PAPER_FINAL_PROOF_INVALID')
            raise RuntimeRefused('PAPER_FINAL_PROOF_INVALID') from None
        finally:
            if consumed:
                for p in proofs:
                    p._check=None;p._finish=None;p._invalidate=None;p._final_identity=None;p._owner=None;p._db=None
                    p._lease=None;p._health=None;p._peer=None;p._content=b''


def _final_proof(owner,check,finish,invalidate,value):
    return _FinalProof(owner,check,finish,invalidate,value,_factory=_FACTORY)
