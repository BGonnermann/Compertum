"""Candidate queue and sealed vault batches (section 19, "Vault and candidate queue"). Stage E4. Deterministic code.

- A candidate enters the queue only after it beats the baseline on VALIDATION, passes the deflation gate, the tests and the
  Auditor. Every admission decision, including a denial, is a ledger event.
- Queued candidates wait. There is no allowance. The vault opens in batches, only with the owner's note.
- Each batch is one look with its own seal. The ledger counts the look before any vault data is read.
- No candidate is evaluated in the vault more than once. A second attempt is ENGINE_VAULT_REPEAT.
The Engineer never sees vault rows. Only this module's evaluate_in_vault reads them, through the Validator adapter.
"""
from decimal import Decimal,InvalidOperation
import hashlib
from uuid import uuid4
from compertum.events import canonical
from compertum.runtime.errors import RuntimeRefused
from .deflation import DSR_MIN
from .market import score_signals

MAX_BATCH=16
NOTE_LIMIT=1024
STATES=(None,'QUEUED','LOOK_COUNTED','VAULT_EVALUATED')


class CandidateQueue:
    def __init__(self,ledger): self.ledger=ledger

    def state(self,candidate_id):
        """Fold the candidate's events. DENIED changes nothing. Returns (state, look_id or None)."""
        state=None;look=None
        for event in self.ledger.queue_events(candidate_id):
            kind=event.get('event')
            if kind=='QUEUED' and state is None: state='QUEUED'
            elif kind=='LOOK_COUNTED' and state=='QUEUED' and isinstance(event.get('look_id'),str): state='LOOK_COUNTED';look=event['look_id']
            elif kind=='VAULT_EVALUATED' and state=='LOOK_COUNTED': state='VAULT_EVALUATED'
            elif kind!='DENIED': raise RuntimeRefused('ENGINE_QUEUE_CORRUPT')
        return state,look

    @staticmethod
    def _deflation_passes(deflation):
        """The record must say PASS and its own numbers must agree: the fixed minimum, and a DSR at or above it."""
        if deflation.get('status')!='PASS' or deflation.get('minimum')!=str(DSR_MIN): return False
        try: return Decimal(deflation.get('deflated_sharpe'))>=DSR_MIN
        except (InvalidOperation,TypeError,ValueError): return False

    def admit(self,candidate_id,score,deflation,*,tests_passed,auditor_passed):
        """Queue one candidate, or record why not and refuse. The score and deflation records come from the Validator."""
        if not isinstance(candidate_id,str) or not 1<=len(candidate_id)<=128 or not isinstance(score,dict) or not isinstance(deflation,dict): raise RuntimeRefused('ENGINE_QUEUE_DENIED')
        reasons=[]
        if score.get('beats_baseline') is not True: reasons.append('does not beat the baseline on VALIDATION')
        if not self._deflation_passes(deflation): reasons.append(f'deflation gate {deflation.get("status")}' if deflation.get('status')!='PASS' else 'deflation record inconsistent')
        if tests_passed is not True: reasons.append('tests not passed')
        if auditor_passed is not True: reasons.append('Auditor not passed')
        state,_=self.state(candidate_id)
        if state is not None: reasons.append(f'already {state}')
        record={'score_sha256':hashlib.sha256(canonical(score)).hexdigest(),'deflation':deflation,'tests_passed':tests_passed is True,'auditor_passed':auditor_passed is True}
        if reasons:
            self.ledger.record_queue_event(candidate_id,'DENIED',{**record,'reasons':reasons});raise RuntimeRefused('ENGINE_QUEUE_DENIED')
        return self.ledger.record_queue_event(candidate_id,'QUEUED',record)

    def queued(self):
        order=[];seen=set()
        for event in self.ledger.queue_events():
            cid=event['candidate_id']
            if cid in seen: continue
            seen.add(cid)
            if self.state(cid)[0]=='QUEUED': order.append(cid)
        return order

    def open_batch(self,candidate_ids,owner_note):
        """Seal one batch and count the look. Every candidate must be QUEUED. The owner's note is the OK; it is recorded."""
        if not isinstance(owner_note,str) or not 1<=len(owner_note)<=NOTE_LIMIT: raise RuntimeRefused('ENGINE_VAULT_DENIED')
        if not isinstance(candidate_ids,(list,tuple)) or not 1<=len(candidate_ids)<=MAX_BATCH or len(set(candidate_ids))!=len(candidate_ids): raise RuntimeRefused('ENGINE_VAULT_DENIED')
        for cid in candidate_ids:
            if self.state(cid)[0]!='QUEUED': raise RuntimeRefused('ENGINE_VAULT_DENIED')
        look_id=f'look-{uuid4().hex}';body={'look_id':look_id,'candidate_ids':list(candidate_ids),'owner_note':owner_note,'count_before_open':len(self.ledger.looks())+1}
        seal=hashlib.sha256(canonical(body)).hexdigest()
        # One transaction: the look row and every LOOK_COUNTED event, or nothing.
        return self.ledger.record_look(look_id,seal,{**body,'seal_sha256':seal},counted=[(cid,{'look_id':look_id,'seal_sha256':seal}) for cid in candidate_ids])

    def evaluate_in_vault(self,look_id,candidate_id,signals_text,read_vault):
        """Score one candidate on the vault rows, once, inside its sealed look.

        read_vault is a callable with no arguments. It is called only after the look and the candidate's state pass, so a
        repeat or a denied attempt never reads the vault. It returns the vault rows; when signals_text is None it returns
        (signals_text, vault_rows), for the Validator that produces the signals by a trusted re-run on the vault (E6).
        """
        if not callable(read_vault): raise RuntimeRefused('ENGINE_VAULT_DENIED')
        look=self.ledger.look(look_id)
        if candidate_id not in look['candidate_ids']: raise RuntimeRefused('ENGINE_VAULT_DENIED')
        state,counted=self.state(candidate_id)
        if state=='VAULT_EVALUATED': raise RuntimeRefused('ENGINE_VAULT_REPEAT')
        if state!='LOOK_COUNTED' or counted!=look_id: raise RuntimeRefused('ENGINE_VAULT_DENIED')
        try:
            produced=read_vault()
            if signals_text is None: signals_text,rows=produced
            else: rows=produced
            result=score_signals(signals_text,rows)
        except RuntimeRefused as error:
            self.ledger.record_queue_event(candidate_id,'VAULT_EVALUATED',{'look_id':look_id,'status':'INVALID','code':error.code});raise
        except BaseException as error:
            # Any failure after the checks consumes the candidate's one look. A second call must never read the vault again.
            self.ledger.record_queue_event(candidate_id,'VAULT_EVALUATED',{'look_id':look_id,'status':'INVALID','code':'FAILED_UNEXPECTED','error':type(error).__name__[:64]});raise
        return self.ledger.record_queue_event(candidate_id,'VAULT_EVALUATED',{'look_id':look_id,'status':'SCORED','result':result})
