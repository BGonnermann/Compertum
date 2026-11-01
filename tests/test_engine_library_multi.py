"""The multi-stock library (owner, 1 November 2026): a common calendar, causal portfolio rules, the equal-weight benchmark, knobs chosen on TRAIN,
every setting counted before any VALIDATION score, and the real gate. Fixture prices are generated inside the test only; research runs use real data."""
from datetime import date,timedelta
import math
import random
import pytest
from test_ai_manual import bridge  # noqa: F401  (fixture)
from compertum.ai.engine import library_multi as lm
from compertum.ai.engine.ledger import EngineLedger
from compertum.runtime.errors import RuntimeRefused


def calendar(count,start=date(2016,1,4)):
    out=[];day=start
    while len(out)<count:
        if day.weekday()<5: out.append(day.isoformat())
        day+=timedelta(days=1)
    return out


def symbol_rows(days,seed,drift=0.0):
    rng=random.Random(seed);close=100.0;out=[]
    for d in days:
        close*=1+drift+rng.gauss(0,0.01);out.append({'session':d,'close':f'{close:.6f}','return':'0'})
    return out


def markets(count=12,sessions=500,train=300,drifts=None):
    days=calendar(sessions);out={}
    for i in range(count):
        rows=symbol_rows(days,i,(drifts or {}).get(i,0.0));out[f'S{i:02d}']=(rows[:train],rows[train:])
    return out


def test_the_grid_has_six_families_and_75_settings():
    assert len(lm.FAMILIES)==6 and lm.SETTINGS==75


def test_the_panel_keeps_only_symbols_on_the_common_calendar():
    m=markets(12);short=m['S03'];m['S03']=(short[0],short[1][:-1])
    p=lm.panel(m)
    assert p['dropped']==['S03'] and len(p['closes'])==11 and p['train']==300 and len(p['dates'])==500


def test_every_setting_is_causal_and_long_only():
    m=markets(12,sessions=420,train=250);p=lm.panel(m)
    changed={s:(t,[dict(r,close=f"{float(r['close'])*(1.4 if i>=300 else 1):.6f}") for i,r in enumerate(t+v)][len(t):]) for s,(t,v) in m.items()}
    q=lm.panel(changed);a=lm.prepare(p,sorted(p['closes']));b=lm.prepare(q,sorted(q['closes']))
    for name,(_,grid) in lm.FAMILIES.items():
        for knobs in grid:
            wa=lm.weights(a,name,knobs);wb=lm.weights(b,name,knobs)
            assert wa[:300]==wb[:300],(name,knobs)
            assert all(all(v>0 for v in w.values()) and sum(w.values())<=1+1e-9 for w in wa),(name,knobs)


def test_the_score_charges_turnover_and_uses_the_equal_weight_benchmark():
    m=markets(10,sessions=60,train=30);p=lm.panel(m);u=lm.prepare(p,sorted(p['closes']))
    targets=[{'S00':1.0}]*u['n'];s=lm.score(u,targets,0,u['n'])
    daily=[u['returns']['S00'][t+1]-(0.0005 if t==0 else 0.0) for t in range(u['n']-1)]
    mean=sum(daily)/len(daily);std=math.sqrt(sum((x-mean)**2 for x in daily)/(len(daily)-1))
    assert math.isclose(float(s['deflation_inputs']['sharpe_per_period']),mean/std,rel_tol=1e-6)
    assert s['sessions']==60 and s['sessions_invested']==59 and s['benchmark_sharpe'] is not None
    flat=lm.score(u,[{}]*u['n'],0,u['n']);assert flat['sharpe_status']=='UNDEFINED' and flat['beats_baseline'] is False


def test_the_sweep_counts_every_setting_before_validation_and_uses_the_real_gate(bridge,monkeypatch):
    b,_=bridge;ledger=EngineLedger(b.store);ledger.record_external_trials('earlier',50,{})
    p=lm.panel(markets(12,sessions=500,train=300));order=[]
    real_record=ledger.record_external_trials;real_safe=lm._safe
    monkeypatch.setattr(ledger,'record_external_trials',lambda *a,**k:(order.append('trials'),real_record(*a,**k))[1])
    calls=[]
    def safe(u,targets,start,end):
        calls.append(start);return real_safe(u,targets,start,end)
    monkeypatch.setattr(lm,'_safe',safe)
    report=lm.sweep(p,ledger,run_id='library-multi-20261101-00000001',note='fixture')
    assert report['universes']=={'stocks':12} and report['trials_recorded']==75 and report['total_trials']==125==ledger.total_trials()
    assert all(c==0 for c in calls[:75]) and all(c==300 for c in calls[75:]) and len(calls)==81
    for r in report['rows']:
        if r['gate']=='UNDEFINED': continue
        assert r['gate']==('PASS' if r['validation']['beats_baseline'] and float(r['deflated_sharpe'])>=0.95 else 'FAIL')
    with pytest.raises(RuntimeRefused,match='^ENGINE_MARKET_DENIED$'): lm.sweep(lm.panel(markets(5)),ledger,run_id='library-multi-20261101-00000002',note='x')


def test_a_planted_cross_sectional_drift_is_found_by_momentum(bridge):
    b,_=bridge;ledger=EngineLedger(b.store)
    p=lm.panel(markets(20,sessions=900,train=540,drifts={0:0.003,1:0.003}))
    report=lm.sweep(p,ledger,run_id='library-multi-20261101-00000003',note='fixture')
    row=next(r for r in report['rows'] if r['family']=='xs_momentum')
    assert row['validation']['beats_baseline'] is True


def test_the_command_refuses_without_history_or_note(tmp_path):
    assert lm.main(['--project',str(tmp_path),'sweep','--note','x'])==2
