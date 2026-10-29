"""The ten outcome levels of a candidate (owner decision, 25 October 2026) and the Director's lessons table built from them.

Code sets every level from the Validator's and the Auditor's records; no model judges it. The Director's lessons table (ledger.py)
uses these rules. GEPA's score (gepa_run.py) uses them with a fixed trial count and a cap on markets with no pattern.
No engine library is imported here: the product environment uses this module.
"""
from decimal import Decimal,InvalidOperation
import re

# Level 3 (failed the Auditor: lookahead or not reproducible) sits below every honest strategy, so no prompt is rewarded for cheating.
LEVELS={1:'Nothing was built: the pick failed or every memo was rejected.',
        2:'A program was built but produced no valid signals: it crashed, never ran, or wrote a bad file.',
        3:'It failed the Auditor: not reproducible, or it used future data.',
        4:'Valid signals, but degenerate: the same position on every session.',
        5:'A real strategy, clearly worse than buy-and-hold.',
        6:'A real strategy, close to buy-and-hold but not better.',
        7:'It beat buy-and-hold, but the deflated Sharpe is below 0.50: most likely luck.',
        8:'It beat buy-and-hold, deflated Sharpe 0.50 to 0.79.',
        9:'It beat buy-and-hold, deflated Sharpe 0.80 to 0.94: close to the gate.',
        10:'It passed the deflation gate and the Auditor and was queued.'}
CLEARLY_WORSE=Decimal('0.25')  # a Sharpe below buy-and-hold by more than this is level 5; within it, level 6
NO_SIGNAL_STATUSES=frozenset({'NO_SIGNALS','INVALID_SIGNALS','BUILD_FAILED'})
AUDIT_STATUSES=frozenset({'REJECTED_AUDIT','FROZEN'})
# Outcomes of a hypothesis that never became a candidate. They are not levels: nothing was tested.
NOT_BUILT_REJECTED='Not built: the Director rejected the memo.'
NOT_BUILT_OTHER='Not built: a step failed or the cycle stopped before a candidate existed.'
MAX_LESSONS=40
IDEA_CHARS=120


def _decimal(value):
    try: return Decimal(value) if isinstance(value,str) else None
    except InvalidOperation: return None


def norm_title(title): return re.sub(r'[^a-z0-9]+',' ',str(title).lower()).strip()


def degenerate(score):
    """The same traded position on every session. score_signals pays the position at session t with the return of t+1, so the last session's
    position never trades: always long or always flat except on the last session is still degenerate. In position counts that is
    held N-1 with 2 changes (long, then flat on the last session) or held 1 with 1 change (flat, then long on the last session)."""
    held=score.get('positions_held');sessions=score.get('sessions');changes=score.get('position_changes')
    return held in (0,sessions) or (held==sessions-1 and changes==2) or (held==1 and changes==1)


def audited(candidate): return (candidate.get('audit') or {}).get('label')=='VERIFIED_PASS'


def candidate_level(candidate,score):
    """The level, 1 to 10, of one candidate: its status, then the Validator's score record for it (None when it has none)."""
    status=candidate.get('status')
    if status=='QUEUED': return 10
    if status in AUDIT_STATUSES: return 3
    if status in NO_SIGNAL_STATUSES or not isinstance(score,dict): return 2
    if degenerate(score): return 4
    if not score.get('beats_baseline'):
        sharpe=_decimal(score.get('sharpe'));benchmark=_decimal(score.get('benchmark_sharpe'))
        return 5 if sharpe is None or benchmark is None or sharpe<benchmark-CLEARLY_WORSE else 6
    # Levels 7 to 9 need an Auditor pass (review, 25 October 2026): graded by its deflated Sharpe alone, a strategy that read future data would
    # rise toward 9 with more lookahead. The Auditor checks every candidate that beats buy-and-hold (owner decision the same day).
    if not audited(candidate): return 6
    deflated=_decimal((candidate.get('deflation') or {}).get('deflated_sharpe'))
    if deflated is None or deflated<Decimal('0.50'): return 7
    return 8 if deflated<Decimal('0.80') else 9  # 0.95 and above with no queue entry means the audit did not finish: still 9


def cycle_level(result):
    """The best candidate's level, or 1 when the cycle built nothing."""
    scores=result.get('scores') or {}
    levels=[candidate_level(c,scores.get(c.get('hypothesis_id'))) for c in result.get('candidates') or []]
    return max(levels) if levels else 1


def lessons(cycle_ends,market_sha256):
    """The Director's lessons table: one row per distinct idea tried on this market, oldest first, at most MAX_LESSONS rows.

    Built by code from the cycles' END records; no model writes a row. A row holds the idea's title, how often it was tried, the last
    cycle that tried it, and its best outcome as a sentence without the level number. It holds no Sharpe, return or deflated value: the Director
    learns what failed and why, not which numbers to chase. Cycles on another market, or recorded before cycles carried a market
    fingerprint (25 October 2026), are left out: an idea that failed on one market says nothing about another.
    Ideas match by normalized title, so a reworded idea is a new row.
    A cycle that stopped (stop_code set) contributes only the candidates that reached a status and the Director's own rejects: its other ideas were never tested.
    A reject that the cycle code wrote after a failed step (source 'code') is a fault, not the Director's verdict."""
    rows={}
    for cycle in cycle_ends:
        if not isinstance(cycle,dict) or cycle.get('market_sha256')!=market_sha256: continue
        scores=cycle.get('scores');decisions=cycle.get('decisions');candidates=cycle.get('candidates');hypotheses=cycle.get('hypotheses')
        scores=scores if isinstance(scores,dict) else {};decisions=decisions if isinstance(decisions,dict) else {}
        stopped=cycle.get('stop_code') is not None
        built={c.get('hypothesis_id'):candidate_level(c,scores.get(c.get('hypothesis_id'))) for c in (candidates if isinstance(candidates,list) else [])
               if isinstance(c,dict) and (c.get('status') or not stopped)}
        for hypothesis in hypotheses if isinstance(hypotheses,list) else []:
            if not isinstance(hypothesis,dict) or not hypothesis.get('title'): continue
            hid=hypothesis.get('id');level=built.get(hid);decision=decisions.get(hid)
            rejected=isinstance(decision,dict) and decision.get('decision')=='reject' and decision.get('source')!='code'
            if level is None and not rejected and stopped: continue
            if level is None: outcome=NOT_BUILT_REJECTED if rejected else NOT_BUILT_OTHER
            else: outcome=LEVELS[level]
            key=norm_title(hypothesis['title']);row=rows.pop(key,None)  # pop and reinsert: the dict stays in order of last use
            if row is None: row={'idea':str(hypothesis['title'])[:IDEA_CHARS],'tries':0,'best_level':None,'best_outcome':outcome}
            row['tries']+=1;row['last_cycle']=cycle.get('cycle_index')
            if level is not None and (row['best_level'] is None or level>row['best_level']): row['best_level']=level;row['best_outcome']=outcome
            rows[key]=row
    return [{k:v for k,v in row.items() if k!='best_level'} for row in list(rows.values())[-MAX_LESSONS:]]
