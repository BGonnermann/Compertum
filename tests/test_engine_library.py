"""The strategy library (owner, 1 November 2026): causal pre-coded families, knobs chosen on TRAIN only, every setting counted as a trial before
any VALIDATION score, and the real gate with option C. Fixture prices are generated inside the test only; research runs use real data."""
from datetime import date,timedelta
import json
import random
import pytest
from test_ai_manual import bridge  # noqa: F401  (fixture)
from compertum.ai.engine import library
from compertum.ai.engine.ledger import EngineLedger
from compertum.runtime.errors import RuntimeRefused


def rows(count,seed,start=date(2016,1,4),drift=0.0003):
    rng=random.Random(seed);out=[];day=start;close=100.0;previous=None
    while len(out)<count:
        if day.weekday()<5:
            change=drift+rng.gauss(0,0.01);close*=1+change
            ret=0.0 if previous is None else close/previous-1
            out.append({'session':day.isoformat(),'close':f'{close:.6f}','return':repr(ret)});previous=close
        day+=timedelta(days=1)
    return out


def market(symbol,seed,count=700,train=420):
    data=rows(count,seed);return {'symbol':symbol,'label':f'fixture {symbol}','train_rows':data[:train],'validation_rows':data[train:]}


def test_grid_size():
    assert len(library.FAMILIES)==10 and library.SETTINGS==67
    for name,(rule,grid) in library.FAMILIES.items():
        assert grid and len({json.dumps(k,sort_keys=True) for k in grid})==len(grid),name


def test_causal_families():
    """Changing prices after session k never changes a position at or before k (calendar rules read only the next session's date)."""
    base=rows(600,7);changed=[dict(r) for r in base]
    for r in changed[400:]: r['close']=f"{float(r['close'])*1.5:.6f}"
    a=library.series(base,[]);b=library.series(changed,[])
    for name,(rule,grid) in library.FAMILIES.items():
        for knobs in grid:
            pa=rule(a,**knobs);pb=rule(b,**knobs)
            assert len(pa)==600 and set(pa)<={0,1},(name,knobs)
            assert pa[:400]==pb[:400],(name,knobs)


def test_calendar_rules():
    data=rows(60,3);s=library.series(data,[])
    monday=library.week_day(s,weekday=0)
    assert all(p==(1 if date.fromisoformat(data[t+1]['session']).weekday()==0 else 0) for t,p in enumerate(monday[:-1])) and monday[-1]==0
    tom=library.month_turn(s,last=1,first=1)
    for t in range(len(data)-1):
        today=date.fromisoformat(data[t]['session']);nxt=date.fromisoformat(data[t+1]['session'])
        if today.month!=nxt.month: assert tom[t]==1 and (t==0 or tom[t-1]==1),data[t+1]['session']
        elif t+2<len(data) and date.fromisoformat(data[t+2]['session']).month==nxt.month and t>0 and date.fromisoformat(data[t-1]['session']).month==today.month:
            assert tom[t]==0,data[t+1]['session']


def test_train_knobs():
    m=market('AAA',11);other=dict(m);other['validation_rows']=[dict(r,close=f"{float(r['close'])*0.7:.6f}") for r in m['validation_rows']]
    assert library.choose(m)==library.choose(other)


def test_sweep_gate(bridge,monkeypatch):
    b,_=bridge;ledger=EngineLedger(b.store);ledger.record_external_trials('earlier',100,{})
    markets=[market('AAA',1),market('BBB',2)];order=[]
    real_record=ledger.record_external_trials;real_validate=library.validate
    monkeypatch.setattr(ledger,'record_external_trials',lambda *a,**k:(order.append('trials'),real_record(*a,**k))[1])
    monkeypatch.setattr(library,'validate',lambda *a,**k:(order.append('validate'),real_validate(*a,**k))[1])
    report=library.sweep(markets,ledger,run_id='library-20261101-00000001',note='fixture')
    assert order[0]=='trials' and order.count('trials')==1 and order.count('validate')>=20
    assert report['trials_recorded']==2*67 and report['total_trials']==100+134==ledger.total_trials()
    assert len(report['rows'])==20 and {r['family'] for r in report['rows']}==set(library.FAMILIES)
    for r in report['rows']:
        if r['gate']=='UNDEFINED': continue
        assert r['gate']==('PASS' if r['validation']['beats_baseline'] and r['deflated_sharpe'] is not None and float(r['deflated_sharpe'])>=0.95 else 'FAIL')
    summary=report['summary'];assert summary['candidates']==20 and summary['scored']+sum(r['gate']=='UNDEFINED' for r in report['rows'])==20
    with pytest.raises(RuntimeRefused,match='^ENGINE_TRIAL_DUPLICATE$'): library.sweep(markets,ledger,run_id='library-20261101-00000001',note='again')
    with pytest.raises(RuntimeRefused,match='^ENGINE_MARKET_DENIED$'): library.sweep([market('AAA',1),market('AAA',2)],ledger,run_id='library-20261101-00000002',note='x')


def test_planted_trend(bridge):
    """A strong drift regime switch that a moving-average rule can follow should beat buy-and-hold; the gate decides the rest."""
    b,_=bridge;ledger=EngineLedger(b.store)
    data=rows(900,5,drift=0.0)
    close=100.0;out=[];previous=None;rng=random.Random(9)
    for i,r in enumerate(data):
        drift=0.004 if (i//60)%2==0 else -0.004
        close*=1+drift+rng.gauss(0,0.006);ret=0.0 if previous is None else close/previous-1;previous=close
        out.append({'session':r['session'],'close':f'{close:.6f}','return':repr(ret)})
    trend={'symbol':'TRD','label':'fixture trend','train_rows':out[:540],'validation_rows':out[540:]}
    report=library.sweep([trend],ledger,run_id='library-20261101-00000003',note='fixture')
    best=[r for r in report['rows'] if r['family'] in ('momentum','above_ma','ma_cross','breakout')]
    assert any(r['validation']['beats_baseline'] for r in best)


def test_command_refusals(tmp_path,capsys):
    assert library.main(['--project',str(tmp_path),'sweep','--note','x'])==2 and json.loads(capsys.readouterr().out)=={'refused':'ENGINE_RUN_LIMITS_DENIED'}
    assert library.main(['--project',str(tmp_path),'sweep','--all','--note',' '])==2


def test_skipped_market(tmp_path,monkeypatch):
    def fake(root,path):
        if 'BAD' in path: raise RuntimeRefused('ENGINE_MARKET_COVERAGE_INCOMPLETE')
        m=market('GOOD',1);return {'label':'fixture','train_csv':'session,close,return'+chr(10)+''.join(f"{r['session']},{r['close']},{r['return']}"+chr(10) for r in m['train_rows']),
                                   'validation_rows':m['validation_rows']},[]
    import compertum.ai.engine.real_market as real_market
    monkeypatch.setattr(real_market,'open_market',fake)
    out,skipped=library.load_markets(tmp_path,['data/history/GOOD/manifest.json','data/history/BAD/manifest.json'])
    assert [m['symbol'] for m in out]==['GOOD'] and skipped==[{'symbol':'BAD','code':'ENGINE_MARKET_COVERAGE_INCOMPLETE'}] and len(out[0]['train_rows'])==420


def test_all_manifests(tmp_path,monkeypatch,capsys):
    for symbol in ('AAA','BRK.B'):
        (tmp_path/'data'/'history'/symbol).mkdir(parents=True);(tmp_path/'data'/'history'/symbol/'manifest.json').write_text('{}',encoding='utf-8')
    seen=[]
    def fake(root,manifests): seen.extend(manifests);raise RuntimeRefused('ENGINE_MARKET_DENIED')
    monkeypatch.setattr(library,'load_markets',fake)
    assert library.main(['--project',str(tmp_path),'sweep','--all','--note','x'])==2
    assert seen==['data/history/AAA/manifest.json','data/history/BRK.B/manifest.json'] and json.loads(capsys.readouterr().out)=={'refused':'ENGINE_MARKET_DENIED'}


def test_library_queue(bridge,monkeypatch):
    from compertum.ai.engine.vault import CandidateQueue,quarter_end
    b,_=bridge;ledger=EngineLedger(b.store);queue=CandidateQueue(ledger)
    data=rows(1000,5,drift=0.0);close=100.0;out=[];previous=None;rng=random.Random(9)
    for i,r in enumerate(data):
        close*=1+(0.004 if (i//60)%2==0 else -0.004)+rng.gauss(0,0.006);ret=0.0 if previous is None else close/previous-1;previous=close
        out.append({'session':r['session'],'close':f'{close:.6f}','return':repr(ret)})
    trend={'symbol':'TRD','label':'fixture trend','train_rows':out[:540],'validation_rows':out[540:900]};vault=out[900:]
    report=library.sweep([trend],ledger,run_id='library-20261102-00000004',note='fixture')
    beat=[r for r in report['rows'] if r['validation'].get('beats_baseline')];assert beat
    assert all(r['causal'] and r['recomputed'] and r['queue']['event']=='ELIGIBLE' for r in beat)
    assert all('queue' not in r for r in report['rows'] if not r['validation'].get('beats_baseline'))
    assert queue.eligible()==[r['queue']['candidate_id'] for r in beat]
    def peek(s,**knobs): return [1 if i+1<len(s['closes']) and s['closes'][i+1]>s['closes'][i] else 0 for i in range(len(s['closes']))]
    monkeypatch.setitem(library.FAMILIES,'peek',(peek,[{}]))
    assert library.causal(trend,'peek',{}) is False and library.causal(trend,beat[0]['family'],beat[0]['knobs']) is True
    route=ledger.queue_events(beat[0]['queue']['candidate_id'])[0]['route']
    assert route['kind']=='library' and route['symbol']=='TRD' and route['family']==beat[0]['family'] and route['knobs']==beat[0]['knobs']
    quarter=beat[0]['queue']['quarter'];chosen=queue.close_quarter(quarter,day=quarter_end(quarter));assert 1<=len(chosen)<=3
    cid=chosen[0];look=queue.open_batch([cid],'Owner OK: library vault fixture');reads=[]
    def load(): reads.append(1);return vault
    changed={**trend,'validation_rows':trend['validation_rows'][:-1]}
    for bad in ((changed,load),({**trend,'symbol':'OTHER'},load),(trend,vault)):
        with pytest.raises(RuntimeRefused,match='^ENGINE_VAULT_DENIED$'): library.vault_score(queue,look['look_id'],cid,*bad)
    assert reads==[] and queue.state(cid)[0]=='LOOK_COUNTED'
    result=library.vault_score(queue,look['look_id'],cid,trend,load)
    assert result['status']=='SCORED' and result['result']['sessions']==len(vault) and result['confirmation']['trials']==1 and reads==[1]
    with pytest.raises(RuntimeRefused,match='^ENGINE_VAULT_REPEAT$'): library.vault_score(queue,look['look_id'],cid,trend,load)
    assert reads==[1] and queue.vault_of(cid)=='history-v1'
    french={**trend,'symbol':'TRF','vault':'french-v1'};again=library.sweep([french],ledger,run_id='library-20261102-00000005',note='fixture')
    ids=[r['queue']['candidate_id'] for r in again['rows'] if (r.get('queue') or {}).get('event')=='ELIGIBLE'];assert ids and all(queue.vault_of(i)=='french-v1' for i in ids)
    peeked=next(r for r in again['rows'] if r['family']=='peek');assert peeked['causal'] is False and peeked['queue']['event']=='NOT_ADMITTED'
