"""Synthetic daily market for engine cycles and the Validator adapter that scores Engineer signals on it.

The market is closed and deterministic: one asset, one return per session, from a seed. A planted pattern is optional.
TRAIN and VALIDATION are session ranges of the same market. There is no vault in stage E3.
The adapter scores with the existing `simulation.metrics.metrics`. It defines no new threshold. The connection to the
real walk-forward Validator and the deflated Sharpe ratio is stage E4 work.
"""
import csv
from decimal import Decimal
import io
import random
from compertum.data.errors import DataError
from compertum.runtime.errors import RuntimeRefused
from compertum.simulation.metrics import metrics
from .deflation import moments

MIN_SESSIONS,MAX_SESSIONS=40,4096
SIGNALS_BYTES=1024*1024
# Planted patterns: the next return leans with the sign of the last `window` returns (momentum) or against it (reversal).
# Reversal added 25 October 2026 for varied GEPA markets (owner decision); momentum and unplanted markets are unchanged byte for byte.
PLANTED_KINDS=('momentum','reversal')
COST=Decimal('0.0005')  # fixed cost for each position change, as a fraction of NAV


def synthetic_market(seed,sessions,*,planted=None):
    """Return rows {session, close, return}. planted: None or {'kind': 'momentum' or 'reversal', 'window': k, 'strength': b}."""
    if type(seed) is not int or type(sessions) is not int or not MIN_SESSIONS<=sessions<=MAX_SESSIONS: raise RuntimeRefused('ENGINE_MARKET_DENIED')
    if planted is not None and (not isinstance(planted,dict) or planted.keys()!={'kind','window','strength'} or planted['kind'] not in PLANTED_KINDS
                                or type(planted['window']) is not int or not 1<=planted['window']<=20
                                or type(planted['strength']) not in (int,float) or not 0<=planted['strength']<=0.05):
        raise RuntimeRefused('ENGINE_MARKET_DENIED')
    generator=random.Random(seed);close=100.0;returns=[];rows=[]
    for index in range(sessions):
        noise=generator.gauss(0.0002,0.01)
        if planted is not None and index>=planted['window']:
            recent=sum(returns[-planted['window']:])
            lean=planted['strength']*(1 if recent>0 else -1 if recent<0 else 0)
            noise+=lean if planted['kind']=='momentum' else -lean
        value=max(-0.5,min(0.5,noise));returns.append(value);close=close*(1+value)
        rows.append({'session':index,'close':f'{close:.6f}','return':f'{value:.8f}'})
    return rows


def market_csv(rows):
    out=io.StringIO();writer=csv.DictWriter(out,fieldnames=['session','close','return'],lineterminator='\n')
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


def score_signals(text,validation_rows,*,cost=COST):
    """Score positions against buy and hold on the validation sessions. The position chosen at session t earns the return of t+1."""
    positions=parse_signals(text,validation_rows)
    returns=[Decimal(row['return']) for row in validation_rows]
    navs=[Decimal(1)];benchmark=[Decimal(1)];previous=0
    for index in range(1,len(returns)):
        held=positions[index-1];change=abs(held-previous);previous=held
        navs.append(navs[-1]*(1+held*returns[index]-cost*change));benchmark.append(benchmark[-1]*(1+returns[index]))
    if any(nav<=0 for nav in navs): raise RuntimeRefused('ENGINE_SIGNALS_INVALID')
    try: scored=metrics(navs,benchmark);baseline=metrics(benchmark,benchmark)
    except DataError as error: raise RuntimeRefused(error.reason) from None
    # metrics() reports numbers as decimal strings and an undefined Sharpe ratio as None. Compare as decimals, record as given.
    excess=_decimal(scored['annual_mean_excess']);sharpe=_decimal(scored['sharpe']);baseline_sharpe=_decimal(baseline['sharpe'])
    beats=(scored['sharpe_status']=='DEFINED' and excess is not None and excess>0
           and (baseline['sharpe_status']!='DEFINED' or (sharpe is not None and baseline_sharpe is not None and sharpe>baseline_sharpe)))
    return {'sessions':len(returns),'positions_held':sum(positions),'position_changes':sum(abs(a-b) for a,b in zip(positions,[0]+positions[:-1])),
            'final_nav':str(navs[-1].quantize(Decimal('0.00000001'))),'benchmark_final_nav':str(benchmark[-1].quantize(Decimal('0.00000001'))),
            'annual_mean_excess':scored['annual_mean_excess'],'sharpe':scored['sharpe'],'sharpe_status':scored['sharpe_status'],'max_drawdown':scored['max_drawdown'],
            'benchmark_sharpe':baseline['sharpe'],'benchmark_sharpe_status':baseline['sharpe_status'],'beats_baseline':bool(beats),
            'cost_per_change':str(cost),'rule':'beats_baseline: Sharpe defined, annual mean excess > 0, Sharpe above the benchmark Sharpe',
            'deflation_inputs':moments(scored['returns'])}


def _decimal(value):
    return Decimal(value) if isinstance(value,str) else None
