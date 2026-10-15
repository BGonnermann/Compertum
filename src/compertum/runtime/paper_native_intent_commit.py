"""Call-local transaction adapter for original, single-use private proofs."""
from types import SimpleNamespace
from .errors import RuntimeRefused
from .owners import _MUTEX,_owner_scope
from .paper_final_proof import _verify_proofs,_health_live,_health_finish,_INVALID


def finish_operation(owner,proofs,durable,finish,write=None):
    """Do no committing callbacks after INSERT; discard every retained closure."""
    with _MUTEX:
        db=owner.db;lease=owner.lease;tails=[];owned=False;invalidators=()
        if db.in_transaction:raise RuntimeRefused('PAPER_INTENT_TRANSACTION_OPEN')
        try:
            for proof in proofs:
                tails.append(SimpleNamespace(_check=proof._check,_finish=proof._finish,_invalidate=proof._invalidate,
                    _health=proof._health,_peer=proof._peer))
            # Consume normally; the retained callbacks exist only for this call.
            _verify_proofs(*proofs)
            invalidators=tuple(t._invalidate for t in tails)
            if write is not None:
                db.execute('BEGIN IMMEDIATE');owned=True;write()
            with _owner_scope(lease),owner.store._live():
                if owner._closed or owner.db is not db or owner.lease is not lease:
                    raise RuntimeRefused('PAPER_INTENT_OWNER_REPLACED')
                invalidators=();durable()
                for tail in tails:
                    invalidators=(tail._invalidate,);tail._check()
                invalidators=tuple(t._invalidate for t in tails)
                health,state=_health_live(owner,tails)
            for tail in tails:
                invalidators=(tail._invalidate,);tail._finish()
            invalidators=();finish()
            invalidators=tuple(t._invalidate for t in tails);_health_finish(owner,health,state)
            if owned:db.commit();owned=False
        except (RuntimeRefused,*_INVALID) as error:
            if owned:
                db.rollback();owned=False
            code=error.code if isinstance(error,RuntimeRefused) else 'PAPER_INTENT_STATE_CORRUPT'
            for invalidate in invalidators:invalidate(code)
            raise RuntimeRefused(code) from None
        finally:
            if owned:db.rollback()
            invalidators=()
            for tail in tails:tail.__dict__.clear()
            tails.clear()
