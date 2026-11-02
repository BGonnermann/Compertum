"""Synthetic daily market for engine cycles and the Validator adapter that scores Engineer signals on it.

The market is closed and deterministic: one asset, one return per session, from a seed. A planted pattern is optional.
TRAIN and VALIDATION are session ranges of the same market. There is no vault in stage E3.
The adapter scores with the existing `simulation.metrics.metrics`. It defines no new threshold. The connection to the
real walk-forward Validator and the deflated Sharpe ratio is stage E4 work.

Honest scoring (owner, 2 November 2026: "yes approve all four"; docs/IMPROVEMENT_RESEARCH.md items 1 to 3):
- A row may carry 'rate', the daily risk-free return of that session. Cash earns it; rows without it earn 0 (generated markets).
- Sharpe ratios are of returns above the rate. The deflated Sharpe ratio tests active returns (strategy minus benchmark), not the raw return.
- A row whose session is a date pays the cost of its era (ERA_COSTS); other rows pay COST.
- On dated (real) sessions, beats_baseline also needs the same positions executed one session later to beat the benchmark (the lag check).
  The check targets stale closing prices of real portfolios. A generated market has no stale prices; its planted pattern is one session long.
"""
import csv
from decimal import Decimal
import io
import random
from compertum.data.errors import DataError
from compertum.runtime.errors import RuntimeRefused
from compertum.simulation.metrics import metrics
from .deflation import moments

MIN_SESSIONS,MAX_SESSIONS=40,32768
SIGNALS_BYTES=1024*1024
# Planted patterns: the next return leans with the sign of the last `window` returns (momentum) or against it (reversal).
# Reversal added 25 October 2026 for varied GEPA markets (owner decision); momentum and unplanted markets are unchanged byte for byte.
PLANTED_KINDS=('momentum','reversal')
COST=Decimal('0.0005')  # fixed cost for each position change, as a fraction of NAV
ERA_COSTS=(('1975-05-01',Decimal('0.0100')),('1991-01-01',Decimal('0.0050')),('2001-04-09',Decimal('0.0025')),('2010-01-01',Decimal('0.0010')))


def synthetic_market(seed,sessions,*,planted=None,regimes=None):
    """Return rows {session, close, return}, with one optional planted pattern or explicit regimes."""
    if type(seed) is not int or type(sessions) is not int or not MIN_SESSIONS<=sessions<=MAX_SESSIONS: raise RuntimeRefused('ENGINE_MARKET_DENIED')
    if planted is not None and (not isinstance(planted,dict) or planted.keys()!={'kind','window','strength'} or planted['kind'] not in PLANTED_KINDS
                                or type(planted['window']) is not int or not 1<=planted['window']<=20
                                or type(planted['strength']) not in (int,float) or not 0<=planted['strength']<=0.05):
        raise RuntimeRefused('ENGINE_MARKET_DENIED')
    if planted is not None and regimes is not None: raise RuntimeRefused('ENGINE_MARKET_DENIED')
    if regimes is not None:
        if not isinstance(regimes,list) or not 1<=len(regimes)<=16: raise RuntimeRefused('ENGINE_MARKET_DENIED')
        previous=-1
        for regime in regimes:
            if (not isinstance(regime,dict) or regime.keys()!={'start','kind','window','strength','drift','noise'} or type(regime['start']) is not int
                    or regime['start']<=previous or (previous==-1 and regime['start']!=0) or regime['kind'] not in PLANTED_KINDS+(None,)
                    or type(regime['window']) is not int or type(regime['strength']) not in (int,float)
                    or type(regime['drift']) not in (int,float) or type(regime['noise']) not in (int,float)
                    or not -0.05<=regime['drift']<=0.05 or not 0<regime['noise']<=0.1):
                raise RuntimeRefused('ENGINE_MARKET_DENIED')
            if regime['kind'] is None:
                if regime['window']!=0 or regime['strength']!=0: raise RuntimeRefused('ENGINE_MARKET_DENIED')
            elif not 1<=regime['window']<=20 or not 0<=regime['strength']<=0.05: raise RuntimeRefused('ENGINE_MARKET_DENIED')
            previous=regime['start']
        if regimes[-1]['start']>=sessions: raise RuntimeRefused('ENGINE_MARKET_DENIED')
    generator=random.Random(seed);close=100.0;returns=[];rows=[]
    for index in range(sessions):
        if regimes is None:
            noise=generator.gauss(0.0002,0.01);pattern=planted;start=0
        else:
            pattern=regime_at(regimes,index);start=pattern['start'];noise=generator.gauss(pattern['drift'],pattern['noise'])
        if pattern is not None and pattern['kind'] is not None and index>=start+pattern['window']:
            recent=sum(returns[-pattern['window']:])
            lean=pattern['strength']*(1 if recent>0 else -1 if recent<0 else 0)
            noise+=lean if pattern['kind']=='momentum' else -lean
        value=max(-0.5,min(0.5,noise));returns.append(value);close=close*(1+value)
        rows.append({'session':index,'close':f'{close:.6f}','return':f'{value:.8f}'})
    return rows


def regime_at(regimes,index):
    current=None
    for regime in regimes:
        if regime['start']>index: break
        current=regime
    return current


def market_csv(rows):
    out=io.StringIO();writer=csv.DictWriter(out,fieldnames=['session','close','return'],lineterminator='\n',extrasaction='ignore')
    writer.writeheader()
    for row in rows: writer.writerow(row)
    return out.getvalue()


def split_market(rows,train_fraction=0.7):
    cut=int(len(rows)*train_fraction)
    if cut<10 or len(rows)-cut<10: raise RuntimeRefused('ENGINE_MARKET_DENIED')
    return rows[:cut],rows[cut:]


def split_market_tiers(rows,train_fraction=0.5,validation_fraction=0.3):
    """TRAIN, VALIDATION and VAULT as consecutive session ranges. The vault is the last range; the Engineer never receives it."""
    if not 0<train_fraction<1 or not 0<validation_fraction<1 or train_fraction+validation_fraction>=1: raise RuntimeRefused('ENGINE_MARKET_DENIED')
    first=int(len(rows)*train_fraction);second=first+int(len(rows)*validation_fraction)
    train,validation,vault=rows[:first],rows[first:second],rows[second:]
    if min(len(train),len(validation),len(vault))<10: raise RuntimeRefused('ENGINE_MARKET_DENIED')
    return train,validation,vault


def parse_signals(text,validation_rows):
    """Admit a signals.csv with exactly one position in {0, 1} for every validation session, in order."""
    if not isinstance(text,str) or len(text.encode('utf-8'))>SIGNALS_BYTES: raise RuntimeRefused('ENGINE_SIGNALS_INVALID')
    try: reader=list(csv.reader(io.StringIO(text)))
    except csv.Error: raise RuntimeRefused('ENGINE_SIGNALS_INVALID') from None
    if not reader or reader[0]!=['session','position']: raise RuntimeRefused('ENGINE_SIGNALS_INVALID')
    body=[row for row in reader[1:] if row!=[]]
    expected=[str(row['session']) for row in validation_rows]
    if len(body)!=len(expected) or any(len(row)!=2 for row in body): raise RuntimeRefused('ENGINE_SIGNALS_INVALID')
    positions=[]
    for row,session in zip(body,expected):
        if row[0]!=session or row[1] not in ('0','1'): raise RuntimeRefused('ENGINE_SIGNALS_INVALID')
        positions.append(int(row[1]))
    return positions


def dated(session):
    return isinstance(session,str) and len(session)==10 and session[4]=='-' and session[7]=='-'


def cost_at(session):
    """The one-way cost of a change at this session: by era for a dated session, COST otherwise."""
    if not dated(session): return COST
    for until,cost in ERA_COSTS:
        if session<until: return cost
    return COST


def nav_paths(positions,returns,rates,costs):
    """NAV, benchmark, both above the rate, and active returns. The position chosen at t earns the return of t+1; cash earns the rate."""
    one=Decimal(1);navs=[one];benchmark=[one];above=[one];bench_above=[one];active=[];previous=0
    for index in range(1,len(returns)):
        held=positions[index-1];change=abs(held-previous);previous=held;r=returns[index];rf=rates[index]
        step=held*r+(1-held)*rf-costs[index-1]*change
        navs.append(navs[-1]*(1+step));benchmark.append(benchmark[-1]*(1+r));above.append(above[-1]*(1+step-rf));bench_above.append(bench_above[-1]*(1+r-rf))
        active.append(step-r)
    if any(nav<=0 for nav in navs+above+bench_above): raise RuntimeRefused('ENGINE_SIGNALS_INVALID')
    return navs,benchmark,above,bench_above,active


def verdict(scored,sharpe,baseline):
    """Sharpe defined, annual mean excess over the benchmark above 0, and Sharpe above the benchmark Sharpe (both above the rate)."""
    excess=_decimal(scored['annual_mean_excess']);own=_decimal(sharpe['sharpe']);base=_decimal(baseline['sharpe'])
    return bool(sharpe['sharpe_status']=='DEFINED' and excess is not None and excess>0
                and (baseline['sharpe_status']!='DEFINED' or (own is not None and base is not None and own>base)))


def score_signals(text,validation_rows,*,cost=None):
    """Score positions against buy and hold on the validation sessions. The position chosen at session t earns the return of t+1.
    cost None charges each session's era cost (cost_at); a Decimal charges that cost on every session."""
    positions=parse_signals(text,validation_rows)
    returns=[Decimal(row['return']) for row in validation_rows];rates=[Decimal(row.get('rate','0')) for row in validation_rows]
    costs=[cost_at(row['session']) if cost is None else cost for row in validation_rows]
    def measure(held):
        navs,benchmark,above,bench_above,active=nav_paths(held,returns,rates,costs)
        try: return navs,benchmark,metrics(navs,benchmark),metrics(above,bench_above),metrics(bench_above,bench_above),active
        except DataError as error: raise RuntimeRefused(error.reason) from None
    navs,benchmark,scored,sharpe,baseline,active=measure(positions)
    # metrics() reports numbers as decimal strings and an undefined Sharpe ratio as None. Compare as decimals, record as given.
    beats=verdict(scored,sharpe,baseline);lag_check=None
    if all(dated(row['session']) for row in validation_rows):
        _,_,lag_scored,lag_sharpe,_,_=measure([0]+positions[:-1]);lagged=verdict(lag_scored,lag_sharpe,baseline);beats=beats and lagged
        lag_check={'sharpe':lag_sharpe['sharpe'],'annual_mean_excess':lag_scored['annual_mean_excess'],'beats':lagged}
    return {'sessions':len(returns),'positions_held':sum(positions),'position_changes':sum(abs(a-b) for a,b in zip(positions,[0]+positions[:-1])),
            'final_nav':str(navs[-1].quantize(Decimal('0.00000001'))),'benchmark_final_nav':str(benchmark[-1].quantize(Decimal('0.00000001'))),
            'annual_mean_excess':scored['annual_mean_excess'],'sharpe':sharpe['sharpe'],'sharpe_status':sharpe['sharpe_status'],'max_drawdown':scored['max_drawdown'],
            'benchmark_sharpe':baseline['sharpe'],'benchmark_sharpe_status':baseline['sharpe_status'],'beats_baseline':beats,
            'lag_check':lag_check,
            'cost_per_change':str(cost) if cost is not None else 'by era: '+', '.join(f'{c} before {d}' for d,c in ERA_COSTS)+f', then {COST}',
            'cash_rate':'session rate' if any(rates) else '0',
            'rule':'beats_baseline: Sharpe above the rate defined, annual mean excess > 0, Sharpe above the benchmark Sharpe; '
                   'on dated sessions the same holds with every position one session later. Deflation tests active returns (strategy minus benchmark).',
            'deflation_inputs':moments([format(a,'f') for a in active])}


def _decimal(value):
    return Decimal(value) if isinstance(value,str) else None
