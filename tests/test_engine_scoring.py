"""Honest scoring (owner, 2 November 2026: "yes approve all four"): the cash rate, Sharpe ratios above it, the deflated Sharpe ratio of active
returns, costs by era, drift turnover, and the one-session lag check. Fixture prices are generated inside the test only."""
from datetime import date,timedelta
from decimal import Decimal
import math
import random
import pytest
from french_rates import rates_file
from compertum.ai.engine import french_market as fm
from compertum.ai.engine import library_multi as lm
from compertum.ai.engine.market import COST,ERA_COSTS,cost_at,market_csv,score_signals,synthetic_market
from compertum.runtime.errors import RuntimeRefused


def weekdays(start,count):
    out=[];day=start
    while len(out)<count:
        if day.weekday()<5: out.append(day.isoformat())
        day+=timedelta(days=1)
    return out


def rows_for(days,seed=3,drift=0.0004,rate='0.0002'):
    rng=random.Random(seed);close=Decimal(100);out=[]
    for d in days:
        r=Decimal(repr(round(drift+rng.gauss(0,0.01),6)));close=close*(1+r)
        out.append({'session':d,'close':format(close,'f'),'return':format(r,'f'),'rate':rate})
    return out


def text(rows,positions):
    return 'session,position\n'+''.join(f"{r['session']},{p}\n" for r,p in zip(rows,positions))


def test_rates_file(tmp_path):
    days=weekdays(date(1960,1,4),70);rates_file(tmp_path,days,rf=0.42)
    rates=fm.rates_for(tmp_path,days);january=[r for d,r in zip(days,rates) if d<'1960-02-01']
    assert len(set(january))==1 and math.isclose((1+float(january[0]))**len(january)-1,0.0042,rel_tol=1e-9)
    with pytest.raises(RuntimeRefused,match='^ENGINE_MARKET_COVERAGE_INCOMPLETE$'): fm.rates_for(tmp_path,['1961-01-03'])  # no monthly rate
    rates_file(tmp_path,days+['2024-01-02'],months=['196001','196002','196003','196004','202401'])
    with pytest.raises(RuntimeRefused,match='^ENGINE_MARKET_COVERAGE_INCOMPLETE$'): fm.rates_for(tmp_path,['2024-01-02'])  # protected period
    raw=tmp_path/'data'/'french'/'raw'/'ffm.zip';raw.write_bytes(raw.read_bytes()+b'x')
    with pytest.raises(RuntimeRefused,match='^ENGINE_MARKET_EVIDENCE_CHANGED$'): fm.rates_for(tmp_path,days)


def test_cash_rate():
    rows=rows_for(weekdays(date(2016,1,4),200));flat=score_signals(text(rows,[0]*200),rows)
    assert Decimal(flat['final_nav'])==(Decimal('1.0002')**199).quantize(Decimal('0.00000001')) and flat['cash_rate']=='session rate'
    held=score_signals(text(rows,[1]*200),rows);none=[{k:v for k,v in r.items() if k!='rate'} for r in rows]
    assert Decimal(held['sharpe'])<Decimal(score_signals(text(none,[1]*200),none)['sharpe'])  # Sharpe above the rate
    assert 'rate' not in market_csv(rows)


def test_active_deflation():
    rows=rows_for(weekdays(date(2016,1,4),300))
    same=score_signals(text(rows,[1]*299+[0]),rows)
    assert same['deflation_inputs']['observations']==299 and Decimal(same['deflation_inputs']['sharpe_per_period'])<0  # one entry cost, no edge
    up=[1 if i+1<300 and Decimal(rows[i+1]['return'])>0 else 0 for i in range(300)]
    s=score_signals(text(rows,up),rows);active=[]
    for i in range(1,300):
        r=Decimal(rows[i]['return']);step=up[i-1]*r+(1-up[i-1])*Decimal('0.0002')-COST*abs(up[i-1]-(up[i-2] if i>1 else 0));active.append(step-r)
    mean=sum(active)/len(active);std=(sum((a-mean)**2 for a in active)/(len(active)-1)).sqrt()
    assert math.isclose(float(s['deflation_inputs']['sharpe_per_period']),float(mean/std),rel_tol=1e-6)


def test_era_costs():
    assert [cost_at(d) for d in ('1960-06-01','1980-06-01','1995-06-01','2005-06-01','2016-06-01')]==[c for _,c in ERA_COSTS]+[COST]
    assert cost_at(5)==cost_at('5')==COST
    old=rows_for(weekdays(date(1960,1,4),100),rate='0');new=[dict(r,session=d) for r,d in zip(old,weekdays(date(2016,1,4),100))]
    flip=[i%2 for i in range(100)];a=score_signals(text(old,flip),old);b=score_signals(text(new,flip),new)
    assert Decimal(a['final_nav'])<Decimal(b['final_nav']) and a['cost_per_change'].startswith('by era')
    assert score_signals(text(new,flip),new,cost=Decimal('0.01'))['final_nav']==a['final_nav']


def test_lag_check():
    rows=rows_for(weekdays(date(2016,1,4),300),rate='0')
    up=[1 if i+1<300 and Decimal(rows[i+1]['return'])>0 else 0 for i in range(300)]
    s=score_signals(text(rows,up),rows);assert s['lag_check']['beats'] is False and s['beats_baseline'] is False  # tomorrow's sign, one day late
    trend=score_signals(text(rows,[1]*300),rows);assert trend['lag_check'] is not None
    generated=synthetic_market(5,120);g=score_signals(text(generated,[1]*120),generated);assert g['lag_check'] is None and g['cash_rate']=='0'


def test_drift_turnover():
    days=weekdays(date(2016,1,4),80);rng=random.Random(9)
    closes={s:[] for s in ('A','B')}
    for t in range(80):
        for s,drift in (('A',0.01),('B',-0.01)): closes[s].append((closes[s][-1] if t else 100.0)*(1+drift+rng.gauss(0,0.001)))
    p={'dates':days,'train':40,'closes':closes,'rates':['0.0001']*80};u=lm.prepare(p,['A','B'])
    once={'A':0.5,'B':0.5};held=lm.score(u,[once]*80,0,80);daily=lm.score(u,[{'A':0.5,'B':0.5} for _ in range(80)],0,80)
    assert Decimal(held['turnover_per_year'])<Decimal(daily['turnover_per_year']) and Decimal(daily['turnover_per_year'])>Decimal('5')
    cash=lm.score(u,[{'A':0.5}]*80,0,80);assert cash['cash_rate']=='session rate'
    *_,turnover=lm.run_navs(u,[{'A':0.5}]*80,0,80,0.0)
    assert turnover==0.5  # bought once; the cash half and the stock half drift without trading
    assert held['lag_check'] is not None and lm.score(u,[once]*80,0,80,lag=False)['lag_check'] is None
