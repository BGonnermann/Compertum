"""Candidate queue and sealed vault batches (section 19, "Vault and candidate queue"). Stage E4; two stages since 2 November 2026.

Owner, 2 November 2026: "build it as written" (docs/TRIAL_SPENDING_PLAN.md, "Option 1: exact rules").
- Stage 1, screen: a candidate becomes ELIGIBLE when it beats the baseline on VALIDATION and its tests and the Auditor pass. Its
  deflated Sharpe ratio with the global trial count is recorded and ranks it; it is not a minimum. A denial is a ledger event too.
- Quota: after a calendar quarter ends, close_quarter queues at most QUOTA of that quarter's eligible candidates, highest DSR first;
  the rest become NOT_SELECTED. A quarter can only be closed after it ends, so no batch can open on a quarter that is still filling.
- Stage 2, confirmation: the vault opens in batches, only with the owner's note. Each batch is one look with its own seal, counted
  before any vault data is read. At most VAULT_BUDGET candidates are ever evaluated in one vault. A candidate passes when it beats the
  baseline in the vault and its vault DSR is at least the fixed minimum, with N the number of candidates counted in this vault's looks
  up to and including its own, and the null variance of its own estimate (option C).
- No candidate is evaluated in the vault more than once. A second attempt is ENGINE_VAULT_REPEAT. A failed vault test is final.
QUEUED events written before 2 November 2026 passed the old rule (DSR at the minimum); they stay QUEUED. A QUEUED event without an
earlier ELIGIBLE event is accepted only with a time before LEGACY_BEFORE.
At the close each candidate's DSR is recomputed with the trial count at the close, so early and late candidates are ranked on the same N.
A candidate with an undefined DSR is never selected.
The Engineer never sees vault rows. Only this module's evaluate_in_vault reads them, through the Validator adapter.
"""
from datetime import date,datetime,timezone
from decimal import Decimal,InvalidOperation
import hashlib
import re
from uuid import uuid4
from compertum.events import canonical
from compertum.runtime.errors import RuntimeRefused
from .deflation import DSR_MIN,deflated_sharpe,trial_variance
from .market import score_signals

MAX_BATCH=16
NOTE_LIMIT=1024
QUOTA=3
VAULT_BUDGET=12
VAULT_ID='history-v1'
LEGACY_BEFORE='2026-11-02'
INPUTS=('observations','sharpe_per_period','skewness','kurtosis')
QUARTER=re.compile(r'([0-9]{4})-Q([1-4])')
STATES=(None,'ELIGIBLE','NOT_SELECTED','QUEUED','LOOK_COUNTED','VAULT_EVALUATED')


def quarter_of(stamp):
    """The calendar quarter of an ISO date or time, as YYYY-Qn."""
    day=date.fromisoformat(str(stamp)[:10]);return f'{day.year}-Q{(day.month-1)//3+1}'


def quarter_end(name):
    """The first day after the quarter."""
    match=QUARTER.fullmatch(name) if isinstance(name,str) else None
    if match is None: raise RuntimeRefused('ENGINE_QUEUE_DENIED')
    year,number=int(match.group(1)),int(match.group(2))
    return date(year+1,1,1) if number==4 else date(year,3*number+1,1)


def today(): return datetime.now(timezone.utc).date()


def rank_value(deflation,trials):
    """The candidate's DSR recomputed with the trial count at the close and its own null variance; None when it is not defined."""
    if not isinstance(deflation,dict) or any(deflation.get(k) is None for k in INPUTS): return None
    inputs={k:deflation[k] for k in INPUTS}|{'sharpe_status':'DEFINED'}
    try: record=deflated_sharpe(inputs,trials,trial_variance([],inputs)['trial_variance'])
    except (RuntimeRefused,TypeError,ValueError,InvalidOperation): return None
    return None if record['deflated_sharpe'] is None else Decimal(record['deflated_sharpe'])


def fold(events):
    """(state, look_id or None, ELIGIBLE event or None) of one candidate's events, in order."""
    state=None;look=None;eligible=None
    for event in events:
        kind=event.get('event')
        if kind=='ELIGIBLE' and state is None: state='ELIGIBLE';eligible=event
        elif kind=='QUEUED' and (state=='ELIGIBLE' or (state is None and str(event.get('recorded_at',''))<LEGACY_BEFORE)): state='QUEUED'
        elif kind=='NOT_SELECTED' and state=='ELIGIBLE': state='NOT_SELECTED'
        elif kind=='LOOK_COUNTED' and state=='QUEUED' and isinstance(event.get('look_id'),str): state='LOOK_COUNTED';look=event['look_id']
        elif kind=='VAULT_EVALUATED' and state=='LOOK_COUNTED': state='VAULT_EVALUATED'
        elif kind!='DENIED': raise RuntimeRefused('ENGINE_QUEUE_CORRUPT')
    return state,look,eligible


class CandidateQueue:
    def __init__(self,ledger): self.ledger=ledger

    def _fold(self,candidate_id):
        return fold(self.ledger.queue_events(candidate_id))

    def state(self,candidate_id):
        """Fold the candidate's events. DENIED changes nothing. Returns (state, look_id or None)."""
        state,look,_=self._fold(candidate_id);return state,look

    @staticmethod
    def _consistent(deflation):
        """The record's status matches its own value and the fixed minimum. A FAIL rounded to exactly the minimum is honest."""
        try:
            status=deflation.get('status');value=deflation.get('deflated_sharpe')
            if deflation.get('minimum')!=str(DSR_MIN): return False
            if status=='UNDEFINED': return value is None
            return (status=='PASS' and Decimal(value)>=DSR_MIN) or (status=='FAIL' and Decimal(value)<=DSR_MIN)
        except (InvalidOperation,TypeError,ValueError): return False

    def admit(self,candidate_id,score,deflation,*,tests_passed,auditor_passed,route=None):
        """Stage 1: make one candidate ELIGIBLE, or record why not and refuse. The score and deflation records come from the Validator."""
        if not isinstance(candidate_id,str) or not 1<=len(candidate_id)<=128 or not isinstance(score,dict) or not isinstance(deflation,dict): raise RuntimeRefused('ENGINE_QUEUE_DENIED')
        reasons=[]
        if score.get('beats_baseline') is not True: reasons.append('does not beat the baseline on VALIDATION')
        if not self._consistent(deflation): reasons.append('deflation record inconsistent')
        if tests_passed is not True: reasons.append('tests not passed')
        if auditor_passed is not True: reasons.append('Auditor not passed')
        state,_=self.state(candidate_id)
        if state is not None: reasons.append(f'already {state}')
        record={'score_sha256':hashlib.sha256(canonical(score)).hexdigest(),'deflation':deflation,'tests_passed':tests_passed is True,'auditor_passed':auditor_passed is True}
        if reasons:
            self.ledger.record_queue_event(candidate_id,'DENIED',{**record,'reasons':reasons});raise RuntimeRefused('ENGINE_QUEUE_DENIED')
        if route is not None and not isinstance(route,dict): raise RuntimeRefused('ENGINE_QUEUE_DENIED')
        return self.ledger.record_queue_event(candidate_id,'ELIGIBLE',{**record,'quarter':quarter_of(today()),'route':route or {'kind':'engine'}})

    def eligible(self,quarter=None):
        """Candidate ids still ELIGIBLE, in event order, optionally for one quarter."""
        out=[]
        for cid in self._candidates():
            state,_,event=self._fold(cid)
            if state=='ELIGIBLE' and (quarter is None or event.get('quarter')==quarter): out.append(cid)
        return out

    def close_quarter(self,quarter,day=None):
        """After the quarter ends, queue its best eligible candidates by DSR (at most QUOTA queued in the quarter, counting earlier closes)
        and mark the rest NOT_SELECTED, in one locked transaction. Returns the queued ids."""
        end=quarter_end(quarter);day=day or today()
        if not isinstance(day,date) or day<end: raise RuntimeRefused('ENGINE_QUEUE_DENIED')
        trials=max(self.ledger.total_trials(),1)

        def decide(events):
            by={}
            for event in events: by.setdefault(event['candidate_id'],[]).append(event)
            done=sum(1 for rows in by.values() for e in rows if e.get('event')=='QUEUED' and e.get('quarter')==quarter)
            ranked=[]
            for order,(cid,rows) in enumerate(by.items()):
                state,_,eligible=fold(rows)
                if state!='ELIGIBLE' or eligible.get('quarter')!=quarter: continue
                value=rank_value(eligible.get('deflation'),trials)
                ranked.append((value is None,-(value if value is not None else Decimal(0)),order,cid,value))
            ranked.sort();room=max(QUOTA-done,0)
            chosen=[r[3] for r in ranked if r[4] is not None][:room]
            return [(cid,'QUEUED' if cid in chosen else 'NOT_SELECTED',{'quarter':quarter,'rank':rank,'quota':QUOTA,'trials_at_close':trials,
                     'rank_dsr':None if value is None else str(value)}) for rank,(*_,cid,value) in enumerate(ranked,1)]
        return [row['candidate_id'] for row in self.ledger.close_queue(decide) if row['event']=='QUEUED']

    def _candidates(self):
        order=[];seen=set()
        for event in self.ledger.queue_events():
            cid=event['candidate_id']
            if cid not in seen: seen.add(cid);order.append(cid)
        return order

    def queued(self):
        return [cid for cid in self._candidates() if self.state(cid)[0]=='QUEUED']

    def _vault_looks(self):
        return [look for look in self.ledger.looks() if look.get('vault',VAULT_ID)==VAULT_ID]

    def open_batch(self,candidate_ids,owner_note):
        """Seal one batch and count the look. Every candidate must be QUEUED and the vault budget must hold. The owner's note is the OK."""
        if not isinstance(owner_note,str) or not 1<=len(owner_note)<=NOTE_LIMIT: raise RuntimeRefused('ENGINE_VAULT_DENIED')
        if not isinstance(candidate_ids,(list,tuple)) or not 1<=len(candidate_ids)<=MAX_BATCH or len(set(candidate_ids))!=len(candidate_ids): raise RuntimeRefused('ENGINE_VAULT_DENIED')
        for cid in candidate_ids:
            if self.state(cid)[0]!='QUEUED': raise RuntimeRefused('ENGINE_VAULT_DENIED')
        if sum(len(look['candidate_ids']) for look in self._vault_looks())+len(candidate_ids)>VAULT_BUDGET: raise RuntimeRefused('ENGINE_VAULT_BUDGET')
        look_id=f'look-{uuid4().hex}'
        body={'look_id':look_id,'candidate_ids':list(candidate_ids),'owner_note':owner_note,'count_before_open':len(self.ledger.looks())+1,'vault':VAULT_ID}
        seal=hashlib.sha256(canonical(body)).hexdigest()
        # One transaction: the look row and every LOOK_COUNTED event, or nothing.
        return self.ledger.record_look(look_id,seal,{**body,'seal_sha256':seal},counted=[(cid,{'look_id':look_id,'seal_sha256':seal}) for cid in candidate_ids])

    def vault_trials(self,look_id):
        """N for stage 2: the candidates counted in this vault's looks up to and including this look."""
        total=0
        for look in self._vault_looks():
            total+=len(look['candidate_ids'])
            if look['look_id']==look_id: return total
        raise RuntimeRefused('ENGINE_LOOK_UNKNOWN')

    def evaluate_in_vault(self,look_id,candidate_id,signals_text,read_vault):
        """Score one candidate on the vault rows, once, inside its sealed look, and decide stage 2.

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
        trials=self.vault_trials(look_id)
        try:
            produced=read_vault()
            if signals_text is None: signals_text,rows=produced
            else: rows=produced
            result=score_signals(signals_text,rows)
            inputs=result['deflation_inputs'];variance=trial_variance([],inputs)
            deflation=deflated_sharpe(inputs,trials,variance['trial_variance'])
        except RuntimeRefused as error:
            self.ledger.record_queue_event(candidate_id,'VAULT_EVALUATED',{'look_id':look_id,'status':'INVALID','code':error.code});raise
        except BaseException as error:
            # Any failure after the checks consumes the candidate's one look. A second call must never read the vault again.
            self.ledger.record_queue_event(candidate_id,'VAULT_EVALUATED',{'look_id':look_id,'status':'INVALID','code':'FAILED_UNEXPECTED','error':type(error).__name__[:64]});raise
        confirmation={'vault':look.get('vault',VAULT_ID),'trials':trials,'deflation':deflation,'trial_variance':variance,'beats_baseline':result['beats_baseline'],
                      'status':'PASS' if result['beats_baseline'] is True and deflation['status']=='PASS' else 'FAIL'}
        return self.ledger.record_queue_event(candidate_id,'VAULT_EVALUATED',{'look_id':look_id,'status':'SCORED','result':result,'confirmation':confirmation})
