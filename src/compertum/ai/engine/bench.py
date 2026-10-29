"""The fixed test bench and the holdout (25 October 2026). The owner measures one set of role prompts on fixed markets, before and after a change.

Rules (owner agreement, 25 October 2026):
- Two separate seed sets. The bench is reused freely. The holdout is used rarely: every use is counted in the ledger before its first
  cycle, and the set is retired after HOLDOUT_USES uses.
- Bench and holdout cycles start with no history: no recent cycles and no lessons table. Their results never enter the lessons table,
  the Director's recent-cycle list, or GEPA's feedback (ledger.EVALUATION_PURPOSES). So a check cannot teach the prompts the answers.
- The bench measure does not drift with the global trial count. The cycle still applies the real gate with the global count (the judge is
  unchanged); the report adds a bench-local deflated Sharpe with the fixed count BENCH_TRIALS and the null variance only.
- Each patterned market has a reference rule that trades the planted pattern exactly. A pattern counts as found when an audited
  candidate beats buy-and-hold and reaches at least FOUND_CAPTURE of the reference's Sharpe advantage over buy-and-hold.
  The bench-local gate is not the test here: with 150 validation sessions, the exact planted rule passes it on only 2 of the 6
  patterned markets (25 October 2026). A harness cannot be asked to pass where perfect knowledge fails.
- Two markets have no pattern. An audited strategy that passes the bench-local gate there is a false discovery. One false discovery
  says that the harness is broken, however good the other markets look.

This module imports no engine library, so the product environment can build the markets and the report.
"""
from collections import Counter
from decimal import Decimal
from functools import lru_cache
import hashlib
from compertum.runtime.errors import RuntimeRefused
from .deflation import deflated_sharpe,trial_variance
from .levels import AUDIT_STATUSES,audited,candidate_level
from .market import market_csv,regime_at,score_signals,split_market_tiers,synthetic_market

SESSIONS=500
STRENGTH=0.004
CYCLES_PER_MARKET=4  # 5 markets x 4 cycles = 20 cycles, about 85 minutes with Flint
MAX_CYCLES_PER_MARKET=10
MAX_HYPOTHESES=3
BENCH_TRIALS=5*CYCLES_PER_MARKET*MAX_HYPOTHESES  # the most candidates a default bench run can produce. Never the global count.
# Seeds 100 to 199 and 900 to 999 belong to bench and holdout sets, present and future. Practice and GEPA runs may not use them (review, 25 October 2026).
RESERVED_SEEDS=(range(100,200),range(900,1000))
EVALUATION_STATUSES=frozenset({'QUEUED','EVALUATION_GATE_PASS'})  # passed the real gate and the Auditor
FOUND_CAPTURE=Decimal('0.5')  # half of the reference rule's Sharpe advantage over buy-and-hold
HOLDOUT_USES=5  # the holdout set retires after this many counted uses; only the owner changes it
# (kind, window, seed). kind None is a market with no pattern. Seeds are assigned in order, not chosen by result.
SETS={
    'bench-1':(('momentum',5,101),('momentum',10,102),('reversal',3,103),(None,0,104),(None,0,105)),
    'bench-2':(('regimes',5,106),('regimes',3,107),('regimes',5,108),('regimes',0,109),(None,0,110)),
    'bench-3':(('momentum',5,111),('momentum',5,112),('reversal',3,113),('reversal',3,114),
               ('momentum',5,115),('momentum',5,116),('reversal',3,117),('reversal',3,118),('regimes',5,119),('regimes',3,120),
               (None,0,121),(None,0,122),(None,0,123),('regimes',0,124),('regimes',0,125),('regimes',0,126)),
    'holdout-1':(('momentum',5,901),('momentum',10,902),('reversal',3,903),(None,0,904),(None,0,905)),
}


def regime(start,kind,window,*,drift=0.0002,noise=0.01):
    return {'start':start,'kind':kind,'window':window,'strength':STRENGTH if kind is not None else 0,'drift':drift,'noise':noise}


REGIME_SETS={
    106:[regime(0,'momentum',5,noise=0.006),regime(250,'momentum',5,noise=0.02)],
    107:[regime(0,'reversal',3,drift=0.002),regime(250,'reversal',3,drift=-0.002)],
    108:[regime(0,'momentum',5),regime(250,'reversal',3)],
    109:[regime(0,None,0,noise=0.005),regime(150,None,0,noise=0.025),regime(350,None,0,drift=-0.001,noise=0.008)],
    119:[regime(0,'momentum',5),regime(250,'reversal',3)],
    120:[regime(0,'reversal',3,noise=0.006),regime(250,'reversal',3,noise=0.02)],
    124:[regime(0,None,0,noise=0.005),regime(200,None,0,noise=0.02)],
    125:[regime(0,None,0,noise=0.02),regime(300,None,0,noise=0.006)],
    126:[regime(0,None,0,drift=0.001)],
}
WEAK_STRENGTH=STRENGTH/2
STRENGTHS={115:WEAK_STRENGTH,116:WEAK_STRENGTH,117:WEAK_STRENGTH,118:WEAK_STRENGTH}
BENCH_SET='bench-1'
HOLDOUT_SET='holdout-1'


def reserved_seed(seed): return any(seed in r for r in RESERVED_SEEDS)


def trials_for(cycles_per_market,markets=5):
    """The fixed trial count of one bench run: the most candidates it can produce. Runs with different cycles per market are not comparable."""
    return markets*cycles_per_market*MAX_HYPOTHESES


def fingerprint(train_csv,validation_csv):
    return hashlib.sha256(train_csv.encode('utf-8')+b'\0'+validation_csv.encode('utf-8')).hexdigest()


@lru_cache(maxsize=None)
def set_fingerprints(name):
    return frozenset(fingerprint(m['train_csv'],m['validation_csv']) for m in set_markets(name))


def reserved_fingerprints():
    return frozenset().union(*(set_fingerprints(name) for name in SETS))


def set_markets(name):
    """The markets of one set, in a fixed order. Each market carries its set, kind and window for the report."""
    if name not in SETS: raise RuntimeRefused('ENGINE_MARKET_DENIED')
    out=[]
    for kind,window,seed in SETS[name]:
        regimes=REGIME_SETS.get(seed) if kind=='regimes' else None
        if kind=='regimes' and regimes is None: raise RuntimeRefused('ENGINE_MARKET_DENIED')
        strength=None if kind in (None,'regimes') else STRENGTHS.get(seed,STRENGTH)
        planted=None if strength is None else {'kind':kind,'window':window,'strength':strength}
        train,validation,vault=split_market_tiers(synthetic_market(seed,SESSIONS,planted=planted,regimes=regimes))
        market_kind=kind
        if regimes is not None:
            market_kind='regimes' if any(r['kind'] is not None for r in regimes) else None
            if market_kind is not None: pattern='changing regimes'
            elif len({r['noise'] for r in regimes})>1: pattern='changing noise, no pattern'
            else: pattern=f"steady drift {regimes[0]['drift']}, no pattern"
        else: pattern='no pattern' if kind is None else f'{kind} window {window}, strength {strength}'
        out.append({'train_csv':market_csv(train),'validation_csv':market_csv(validation),'validation_rows':validation,
                    'label':f'{name}: seed {seed}, {SESSIONS} sessions, {pattern}','set':name,'kind':market_kind,'window':window,'seed':seed,
                    'strength':strength,'regimes':regimes,'train_rows':train,'vault_sessions':len(vault)})  # the vault rows stay here, unused
    return out


def reference_positions(train,validation,kind,window,regimes=None):
    """The planted rule, traded exactly. The generator leans the return of session t+1 on the sign of the last `window` returns up to t,
    so the position at t is 1 when the lean is up. A market with no pattern has buy-and-hold as its reference."""
    if kind is None: return [1 for _ in validation]
    if kind=='regimes':
        if regimes is None: raise RuntimeRefused('ENGINE_MARKET_DENIED')
        history=[];out=[]
        for row in train+validation:
            index=int(row['session']);regime=regime_at(regimes,index);history.append(float(row['return']))
            if regime['kind'] is None: out.append(1);continue
            if index+1<regime['start']+regime['window']: out.append(0);continue
            recent=sum(history[-regime['window']:]);out.append(1 if (recent>0 if regime['kind']=='momentum' else recent<0) else 0)
        return out[len(train):]
    if kind not in ('momentum','reversal') or type(window) is not int or window<1: raise RuntimeRefused('ENGINE_MARKET_DENIED')
    history=[float(r['return']) for r in train];out=[]
    for row in validation:
        history.append(float(row['return']));recent=sum(history[-window:])
        out.append(1 if (recent>0 if kind=='momentum' else recent<0) else 0)
    return out


def signals_text(validation,positions):
    return 'session,position\n'+''.join(f"{row['session']},{int(p)}\n" for row,p in zip(validation,positions))


def reference_score(market):
    return score_signals(signals_text(market['validation_rows'],reference_positions(market['train_rows'],market['validation_rows'],market['kind'],market['window'],market.get('regimes'))),
                         market['validation_rows'])


def bench_deflation(score,trials=BENCH_TRIALS):
    """The deflated Sharpe with the fixed bench trial count and the candidate's own null variance: the same value for the same signals in every run."""
    inputs=score['deflation_inputs']
    return deflated_sharpe(inputs,trials,trial_variance([],inputs)['trial_variance'])


def _decimal(value):
    return Decimal(value) if isinstance(value,str) else None


def capture_ratio(score,reference):
    """How much of the reference rule's Sharpe advantage over buy-and-hold the candidate reached, unrounded. 1 is as good as knowing the pattern."""
    own=_decimal(score.get('sharpe'));base=_decimal(score.get('benchmark_sharpe'));ref=_decimal(reference.get('sharpe'))
    if own is None or base is None or ref is None or ref<=base: return None
    return (own-base)/(ref-base)


def capture(score,reference):
    """The capture rounded to 0.001 for the report. The found rule uses capture_ratio, so 0.4995 is never found (review, 26 October 2026)."""
    ratio=capture_ratio(score,reference)
    return None if ratio is None else format(ratio.quantize(Decimal('0.001')),'f')


def bench_level(candidate,score,trials=BENCH_TRIALS):
    """The ten levels with the bench-local deflation in place of the global one, so a level never moves with the global trial count.
    Level 10 here means an audited candidate that passed the bench-local gate; the real queue is not involved."""
    if candidate.get('status') in AUDIT_STATUSES or not isinstance(score,dict) or not score.get('beats_baseline'): return candidate_level(candidate,score)
    local=bench_deflation(score,trials)
    level=candidate_level({**candidate,'status':'BENCH_SCORED','deflation':local},score)
    return 10 if level>=7 and audited(candidate) and local['status']=='PASS' else level


def bench_cycle_level(cycle,trials=BENCH_TRIALS):
    scores=cycle.get('scores') or {}
    levels=[bench_level(c,scores.get(c.get('hypothesis_id')),trials) for c in cycle.get('candidates') or [] if isinstance(c,dict)]
    return max(levels) if levels else 1


def report(cycles,markets,cycles_per_market=CYCLES_PER_MARKET):
    """The bench report from a run's cycle results. cycles: dicts with 'market' (label), 'status', 'stop_code', 'candidates', 'scores'.
    Counts and levels only come from the cycles' own records; no number depends on the ledger's global trial count."""
    by_label={m['label']:m for m in markets};rows=[];trials=trials_for(cycles_per_market,len(markets))
    for market in markets:
        mine=[c for c in cycles if c.get('market')==market['label']]
        reference=reference_score(market);patterned=market['kind'] is not None
        row={'market':market['label'],'pattern':patterned,'cycles':len(mine),'cycles_stopped':sum(1 for c in mine if c.get('stop_code') is not None),
             'levels':[bench_cycle_level(c,trials) for c in mine],'candidates':0,'scored':0,'beat_buy_and_hold':0,'audit_passed':0,'bench_gate_passed':0,
             'best_capture':None,'reference':{'sharpe':reference['sharpe'],'benchmark_sharpe':reference['benchmark_sharpe'],'beats_baseline':reference['beats_baseline'],
                                              'bench_deflated_sharpe':bench_deflation(reference,trials)['deflated_sharpe']},
             'statuses':{}}
        if patterned: row['found']=0
        statuses=Counter();captures=[]
        for cycle in mine:
            scores=cycle.get('scores') or {}
            for candidate in cycle.get('candidates') or []:
                if not isinstance(candidate,dict): continue
                row['candidates']+=1;statuses[str(candidate.get('status'))]+=1
                score=scores.get(candidate.get('hypothesis_id'))
                if not isinstance(score,dict): continue
                row['scored']+=1
                if not score.get('beats_baseline'): continue
                row['beat_buy_and_hold']+=1
                if (candidate.get('audit') or {}).get('label')!='VERIFIED_PASS': continue
                row['audit_passed']+=1
                # A pass of the real gate counts too: on a young ledger with few trials the real gate can be looser than the bench gate.
                if bench_deflation(score,trials)['status']=='PASS' or candidate.get('status') in EVALUATION_STATUSES: row['bench_gate_passed']+=1
                if patterned:
                    share=capture(score,reference)
                    if share is not None:
                        captures.append(share)
                        if capture_ratio(score,reference)>=FOUND_CAPTURE: row['found']+=1
        row['statuses']=dict(sorted(statuses.items()))
        known=[Decimal(c) for c in captures if c is not None]
        row['best_capture']=format(max(known),'f') if known else None
        if not patterned: row['false_discoveries']=row['bench_gate_passed']
        rows.append(row)
    unknown=sorted({c.get('market') for c in cycles}-set(by_label))
    patterned=[r for r in rows if r['pattern']];empty=[r for r in rows if not r['pattern']]
    levels=[level for r in rows for level in r['levels']]
    return {'markets':rows,'unknown_markets':unknown,'bench_trials':trials,'cycles_per_market':cycles_per_market,'candidates_total':sum(r['candidates'] for r in rows),
            'patterns_found':sum(1 for r in patterned if r['found']>0),'patterned_markets':len(patterned),'found_capture':str(FOUND_CAPTURE),
            'false_discoveries':sum(r['false_discoveries'] for r in empty),'empty_markets':len(empty),
            'mean_level':format((Decimal(sum(levels))/len(levels)).quantize(Decimal('0.01')),'f') if levels else None,
            'verdict':('BROKEN: a strategy passed on a market with no pattern' if any(r['false_discoveries'] for r in empty) else
                       'INCOMPLETE: a market has no finished cycle' if any(r['cycles']==0 for r in rows) else 'MEASURED'),
            'rule':'capture: (candidate Sharpe - buy-and-hold Sharpe) / (reference Sharpe - buy-and-hold Sharpe), for audited candidates that beat buy-and-hold. '
                   'pattern found: capture >= found_capture. false discovery: on a market with no pattern, an audited candidate that passed the bench-local gate '
                   '(deflated Sharpe >= 0.95 with the fixed bench trial count) or the real gate. Levels use the bench-local gate. Compare runs only at the same cycles_per_market.'}
