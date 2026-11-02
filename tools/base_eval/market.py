"""Synthetic daily markets for the base-model comparison (docs/BASE_MODEL_EVAL.md).

Each market is a CSV with date, close and x. In the signal market the next day's return depends on today's x:
r[t+1] = DRIFT + BETA * x[t] + noise. In the noise market x is drawn the same way and has no effect.
"""
from datetime import date,timedelta
import math
import random

DAYS=3000
DRIFT=0.0002
VOL=0.01
BETA=0.0009
MARKETS={'m1':(20261102,True),'m2':(20261103,False)}


def make_market(seed,signal):
    rng=random.Random(seed)
    day=date(2012,1,2);close=100.0;rows=['date,close,x']
    x=[rng.gauss(0,1) for _ in range(DAYS)]
    for t in range(DAYS):
        if t:
            ret=DRIFT+(BETA*x[t-1] if signal else 0.0)+rng.gauss(0,VOL)
            close*=math.exp(ret)
        rows.append(f'{day.isoformat()},{close:.4f},{x[t]:.4f}')
        day+=timedelta(days=3 if day.weekday()==4 else 1)
    return '\n'.join(rows)+'\n'


def market_csv(name):
    seed,signal=MARKETS[name]
    return make_market(seed,signal)


def lag_stats(text,start,end):
    rows=[line.split(',') for line in text.strip().split('\n')[1:]]
    close=[float(r[1]) for r in rows];x=[float(r[2]) for r in rows]
    pairs=[(x[t-1],math.log(close[t]/close[t-1])) for t in range(max(start,1),end)]
    n=len(pairs);mx=sum(p[0] for p in pairs)/n;my=sum(p[1] for p in pairs)/n
    sxy=sum((a-mx)*(b-my) for a,b in pairs);sxx=sum((a-mx)**2 for a,_ in pairs);syy=sum((b-my)**2 for _,b in pairs)
    corr=sxy/math.sqrt(sxx*syy)
    return {'n':n,'corr':corr,'t':corr*math.sqrt((n-2)/(1-corr*corr))}
