"""French library markets (owner, 2 November 2026): daily portfolio returns turned into close series, the protected period cut, no gap
filled, fixed calendar tiers, the french49 universe, and a vault of their own. Fixture files are written by the test in the library's format."""
from decimal import Decimal
import hashlib
import io
import json
import zipfile
import pytest
from test_ai_manual import bridge  # noqa: F401  (fixture)
from compertum.ai.engine import french_market as fm
from compertum.ai.engine import history_market
from compertum.ai.engine import library_multi as lm
from compertum.ai.engine.ledger import EngineLedger
from compertum.ai.engine.market import MAX_SESSIONS,synthetic_market
from compertum.ai.engine.real_market import open_market
from compertum.ai.engine.vault import VAULT_BUDGET,CandidateQueue,quarter_end,quarter_of
from compertum.runtime.errors import RuntimeRefused

NL=chr(10)
DAYS=sorted([f'{y}{m:02d}{d:02d}' for y in (1950,1951) for m in range(1,13) for d in (3,10,17,24)]+['19510101','19510701','20231228','20231229','20240102','20250630'])


def industries_csv(names,rows,equal_rows=None):
    head=['This file was created using the 202609 CRSP database.','','Missing data are indicated by -99.99 or -999.','','',
          '  Average Value Weighted Returns -- Daily',','+','.join(names)]
    body=[f"{d},"+','.join(f'{v:7.2f}' for v in values) for d,values in rows]
    tail=['','','  Average Equal Weighted Returns -- Daily',','+','.join(names)]+[f"{d},"+','.join(f'{v:7.2f}' for v in values) for d,values in (equal_rows or rows)]
    return NL.join(head+body+tail+['','Copyright 2026 Eugene F. Fama and Kenneth R. French'])+NL


def factors_csv(rows):
    return NL.join(['This file was created by using the 202609 CRSP database.','',',Mkt-RF,SMB,HML,RF']+
                   [f'{d},{a:8.2f},{0:8.2f},{0:8.2f},{b:8.2f}' for d,a,b in rows]+['','Copyright 2026 Eugene F. Fama and Kenneth R. French'])+NL


def zipped(path,name,text):
    buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,'w') as z: z.writestr(name,text)
    path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(buffer.getvalue());return hashlib.sha256(buffer.getvalue()).hexdigest()


def manifest(root,key,file,sha,table='Average Value Weighted Returns -- Daily'):
    folder=root/'data'/'french'/key;folder.mkdir(parents=True,exist_ok=True)
    body={'schema_version':'1','kind':'french','series':key,'table':table,'file':{'path':file,'sha256':sha}}
    (folder/'manifest.json').write_text(json.dumps(body),encoding='utf-8');return f'data/french/{key}/manifest.json'


@pytest.fixture
def library(tmp_path,monkeypatch):
    monkeypatch.setattr(fm,'MIN_SESSIONS',5);monkeypatch.setattr(fm,'VALIDATION_START','1951-01-01');monkeypatch.setattr(fm,'VAULT_START','1951-07-01')
    names=[f'I{i:02d}' for i in range(12)]+['Late','Bad']
    rows=[(d,[(0.1*((i+k)%5)-0.2) for i in range(12)]+[-99.99 if k<10 or k==20 else 0.5,-99.99 if d=='19510310' else 0.3]) for k,d in enumerate(DAYS)]
    equal=[(d,[v+1.0 if v>-99 else v for v in values]) for d,values in rows]
    sha=zipped(tmp_path/'data'/'french'/'raw'/'ind.zip','49_Industry_Portfolios_Daily.csv',industries_csv(names,rows,equal))
    fsha=zipped(tmp_path/'data'/'french'/'raw'/'ff.zip','F-F_Research_Data_Factors_daily.csv',factors_csv([(d,1.0,0.01) for d in DAYS]))
    paths={n:manifest(tmp_path,n,'data/french/raw/ind.zip',sha) for n in names}
    paths['Mkt']=manifest(tmp_path,'Mkt','data/french/raw/ff.zip',fsha,table=None)
    return tmp_path,paths,rows


def test_french_closes(library):
    root,paths,rows=library
    history=fm.load_french(root,paths['I01'])
    assert history['returns']['1950-01-03']=='-0.001'  # the value-weighted table, not the equal-weighted one
    assert history['closes'][0]==('1950-01-03',format((Decimal(100)*(1+Decimal('-0.10')/100)).quantize(fm.PLACES),'f'))
    assert history['closes'][-1][0]=='2023-12-29' and all(d<'2024-01-01' for d,_ in history['closes']) and history['vault']=='french-v1'
    late=fm.load_french(root,paths['Late']);assert late['closes'][0][0]==f'{DAYS[21][:4]}-{DAYS[21][4:6]}-{DAYS[21][6:]}'  # the day after its last gap
    market=fm.load_french(root,paths['Mkt']);assert market['closes'][0][1]==format(Decimal('101.0100000000'),'f')  # Mkt-RF 1.00 plus RF 0.01


def test_french_tiers(library):
    root,paths,_=library
    market,vault=open_market(root,paths['I02'])
    train=market['train_csv'].strip().split(NL)[1:]
    assert all(r.split(',')[0]<'1951-01-01' for r in train) and market['validation_rows'][0]['session']>='1951-01-01'
    assert all(r['session']<'1951-07-01' for r in market['validation_rows']) and vault[0]['session']>='1951-07-01' and vault[-1]['session']=='2023-12-29'
    assert market['vault']=='french-v1' and market['provenance']['provider']=='french' and market['provenance']['tiers']['cutoff']=='2024-01-01'
    with pytest.raises(RuntimeRefused,match='^ENGINE_MARKET_DENIED$'): fm.build_french(root,paths['I02'],sessions=100)
    assert MAX_SESSIONS==32768 and len(synthetic_market(3,20000))==20000 and history_market.HISTORY_SESSIONS==4096
    assert market['validation_rows'][0]['session']=='1951-01-01' and vault[0]['session']=='1951-07-01'
    k=DAYS.index('19510101');assert market['validation_rows'][0]['return']==format(Decimal('%.2f'%(0.1*((2+k)%5)-0.2))/100,'f')
    with pytest.raises(RuntimeRefused,match='^ENGINE_MARKET_INPUT_INVALID$'): fm.load_french(root,paths['Bad'])


def test_french_refusals(library):
    root,paths,_=library
    (root/'data'/'french'/'raw'/'ind.zip').write_bytes(b'changed')
    with pytest.raises(RuntimeRefused,match='^ENGINE_MARKET_EVIDENCE_CHANGED$'): fm.load_french(root,paths['I01'])
    for change,code in (({'series':'Nope'},'ENGINE_MARKET_MANIFEST_INVALID'),({'kind':'history'},'ENGINE_MARKET_MANIFEST_INVALID'),({'table':'No table'},'ENGINE_MARKET_MANIFEST_INVALID')):
        path=root/paths['Mkt'];body=json.loads(path.read_text(encoding='utf-8'));path.write_text(json.dumps({**body,**change}),encoding='utf-8')
        with pytest.raises(RuntimeRefused,match=f'^{code}$'): fm.load_french(root,paths['Mkt'])
        path.write_text(json.dumps(body),encoding='utf-8')
    with pytest.raises(RuntimeRefused,match='^ENGINE_MARKET_INPUT_INVALID$'): fm.read_table('x'+NL+',A'+NL+'1950010,1.0'+NL,None)


def test_french_universe(library):
    root,paths,_=library
    p=lm.french_panel(root,sorted(paths.values()))
    assert p['skipped']==[{'symbol':'Bad','code':'ENGINE_MARKET_INPUT_INVALID'}]
    assert 'Mkt' not in p['closes'] and len(p['closes'])==13 and all(d<'1951-07-01' for d in p['dates']) and p['dates'][p['train']]>='1951-01-01'
    assert lm.universes(p)=={'french49':sorted(p['closes'])} and p['membership']['industries']==13
    late=p['closes']['Late'];join=next(t for t,v in enumerate(late) if v is not None)
    assert 'Late' not in p['eligible'][join-1] and 'Late' in p['eligible'][join] and p['dates'][join]==f'{DAYS[21][:4]}-{DAYS[21][4:6]}-{DAYS[21][6:]}'


def test_french_vault(bridge):
    b,_=bridge;ledger=EngineLedger(b.store);queue=CandidateQueue(ledger);ledger.record_external_trials('earlier',10,{})
    inputs={'observations':603,'skewness':'0.0','kurtosis':'3.0','sharpe_status':'DEFINED'}
    from compertum.ai.engine.deflation import deflated_sharpe,trial_variance
    def record(sr): i={**inputs,'sharpe_per_period':sr};return deflated_sharpe(i,10,trial_variance([],i)['trial_variance'])
    french,alpaca=f'cycle-0001-aaaaaaaa:h1',f'cycle-0001-bbbbbbbb:h1'
    queue.admit(french,{'beats_baseline':True},record('0.05'),tests_passed=True,auditor_passed=True,vault='french-v1')
    queue.admit(alpaca,{'beats_baseline':True},record('0.04'),tests_passed=True,auditor_passed=True)
    with pytest.raises(RuntimeRefused,match='^ENGINE_QUEUE_DENIED$'): queue.admit('cycle-0001-cccccccc:h1',{'beats_baseline':True},record('0.05'),tests_passed=True,auditor_passed=True,vault='other')
    name=quarter_of(ledger.queue_events(french)[0]['recorded_at']);queue.close_quarter(name,day=quarter_end(name))
    assert queue.vault_of(french)=='french-v1' and queue.vault_of(alpaca)=='history-v1' and set(queue.queued())=={french,alpaca}
    for ids,vault in (([french],'history-v1'),([alpaca],'french-v1'),([french,alpaca],'french-v1'),([french],'other')):
        with pytest.raises(RuntimeRefused,match='^ENGINE_VAULT_DENIED$'): queue.open_batch(ids,'Owner OK: mixed or wrong vault',vault=vault)
    look=queue.open_batch([french],'Owner OK: French vault',vault='french-v1');other=queue.open_batch([alpaca],'Owner OK: Alpaca vault')
    assert look['vault']=='french-v1' and other['vault']=='history-v1' and queue.vault_trials(look['look_id'])==1 and queue.vault_trials(other['look_id'])==1 and VAULT_BUDGET==12


def test_vault_separation(bridge,monkeypatch):
    import inspect
    from datetime import date
    from compertum.ai.engine import gepa_run,run
    from compertum.ai.engine import vault as vault_module
    from compertum.ai.engine.cycle import Engine
    from compertum.ai.engine.deflation import deflated_sharpe,trial_variance
    b,_=bridge;ledger=EngineLedger(b.store);queue=CandidateQueue(ledger);ledger.record_external_trials('earlier',10,{})
    def record(sr):
        i={'observations':603,'skewness':'0.0','kurtosis':'3.0','sharpe_status':'DEFINED','sharpe_per_period':sr}
        return deflated_sharpe(i,10,trial_variance([],i)['trial_variance'])
    monkeypatch.setattr(vault_module,'today',lambda:date(2026,11,2))
    french=[f'cycle-0002-{i:08x}:h1' for i in range(4)];alpaca=[f'cycle-0003-{i:08x}:h1' for i in range(4)]
    for i,cid in enumerate(french): queue.admit(cid,{'beats_baseline':True},record(f'0.0{i+5}'),tests_passed=True,auditor_passed=True,vault='french-v1')
    for i,cid in enumerate(alpaca): queue.admit(cid,{'beats_baseline':True},record(f'0.0{i+1}'),tests_passed=True,auditor_passed=True)
    chosen=queue.close_quarter('2026-Q4',day=quarter_end('2026-Q4'))
    assert len(chosen)==6 and set(french[1:])<=set(chosen) and set(alpaca[1:])<=set(chosen)  # three a vault
    ledger.record_look('look-french-full','b'*64,{'candidate_ids':[f'f{i}' for i in range(VAULT_BUDGET)],'owner_note':'fixture','vault':'french-v1'})
    with pytest.raises(RuntimeRefused,match='^ENGINE_VAULT_BUDGET$'): queue.open_batch([french[1]],'Owner OK: French over budget',vault='french-v1')
    first=queue.open_batch([alpaca[1]],'Owner OK: Alpaca still open');second=queue.open_batch(alpaca[2:],'Owner OK: Alpaca again')
    assert queue.vault_trials(first['look_id'])==1 and queue.vault_trials(second['look_id'])==3 and queue.vault_trials('look-french-full')==VAULT_BUDGET
    reads=[]
    with pytest.raises(RuntimeRefused,match='^ENGINE_VAULT_DENIED$'):
        queue.evaluate_in_vault(first['look_id'],alpaca[1],'session,position'+NL,lambda:reads.append(1),vault='french-v1')
    assert reads==[] and queue.state(alpaca[1])[0]=='LOOK_COUNTED'
    with pytest.raises(RuntimeRefused,match='^ENGINE_MARKET_DENIED$'):
        Engine(client=None,ledger=None,lease=None,project_root=None,sandbox_root=None,verification={},train_csv='',validation_csv='',
               validation_rows=[],memory_floor_bytes=0,vault='other')
    assert "vault=market.get('vault','history-v1')" in inspect.getsource(gepa_run) and "vault=item.get('vault','history-v1')" in inspect.getsource(run)


@pytest.fixture
def drift(tmp_path,monkeypatch):
    import random
    from datetime import date,timedelta
    days=[];day=date(1950,1,2)
    while len(days)<900:
        if day.weekday()<5: days.append(day.strftime('%Y%m%d'))
        day+=timedelta(days=1)
    days+=['20231229','20240102']
    monkeypatch.setattr(fm,'MIN_SESSIONS',5);monkeypatch.setattr(fm,'VALIDATION_START',f'{days[540][:4]}-{days[540][4:6]}-{days[540][6:]}')
    monkeypatch.setattr(fm,'VAULT_START',f'{days[780][:4]}-{days[780][4:6]}-{days[780][6:]}')
    rng=random.Random(7);names=[f'D{i:02d}' for i in range(20)]
    rows=[(d,[round(rng.gauss(0.3 if i<2 else 0.0,1.0),2) for i in range(20)]) for d in days]
    sha=zipped(tmp_path/'data'/'french'/'raw'/'drift.zip','49_Industry_Portfolios_Daily.csv',industries_csv(names,rows))
    paths=[manifest(tmp_path,n,'data/french/raw/drift.zip',sha) for n in names]
    return tmp_path,paths


def test_multi_route(bridge,drift,monkeypatch):
    from compertum.ai.engine import vault as vault_module
    from datetime import date
    root,paths=drift;b,_=bridge;ledger=EngineLedger(b.store);queue=CandidateQueue(ledger)
    monkeypatch.setattr(vault_module,'today',lambda:date(2026,11,2))
    p=lm.french_panel(root,paths);assert p['vault']=='french-v1' and p['dates'][-1]<fm.VAULT_START
    report=lm.sweep(p,ledger,run_id='library-multi-20261102-00000001',note='fixture')
    beat=[r for r in report['rows'] if r['validation'].get('beats_baseline')];assert any(r['family']=='xs_momentum' for r in beat)
    assert all(r['recomputed'] and r['causal'] and r['queue']['event']=='ELIGIBLE' for r in beat)
    assert all(queue.vault_of(r['queue']['candidate_id'])=='french-v1' for r in beat) and len(queue.eligible())==len(beat)
    def peek(u,t):
        if t+1>=u['n']: return {}
        return {max(u['eligible'][t],key=lambda s:u['returns'][s][t+1] or 0.0):1.0}
    monkeypatch.setitem(lm.FAMILIES,'peek',(peek,[{'hold':1}]))
    assert lm.causal(p,sorted(p['closes']),'peek',{'hold':1}) is False and lm.causal(p,sorted(p['closes']),beat[0]['family'],beat[0]['knobs']) is True
    queue.close_quarter('2026-Q4',day=quarter_end('2026-Q4'));chosen=queue.queued();assert 1<=len(chosen)<=3
    cid=chosen[0];look=queue.open_batch([cid],'Owner OK: French vault fixture',vault='french-v1')
    with pytest.raises(RuntimeRefused,match='^ENGINE_VAULT_DENIED$'): lm.vault_score(queue,look['look_id'],cid,root,paths[:-1])  # other files: refused before any read
    assert queue.state(cid)[0]=='LOOK_COUNTED'
    event=lm.vault_score(queue,look['look_id'],cid,root,paths)
    assert event['status']=='SCORED' and event['result']['sessions']==len(lm.french_panel(root,paths,with_vault=True)['dates'])-len(p['dates'])
    assert event['confirmation']['vault']=='french-v1' and event['confirmation']['trials']==1 and event['confirmation']['status'] in ('PASS','FAIL')
    with pytest.raises(RuntimeRefused,match='^ENGINE_VAULT_REPEAT$'): lm.vault_score(queue,look['look_id'],cid,root,paths)


def test_multi_admit(bridge,drift,monkeypatch):
    root,paths=drift;b,_=bridge;ledger=EngineLedger(b.store);queue=CandidateQueue(ledger)
    p=lm.french_panel(root,paths)
    monkeypatch.setattr(lm,'ROUTES',frozenset())
    report=lm.sweep(p,ledger,run_id='library-multi-20261102-00000002',note='fixture');trials=ledger.total_trials()
    assert all(r['queue']['event']=='NOT_ADMITTED' for r in report['rows'] if r.get('queue')) and queue.eligible()==[]
    monkeypatch.setattr(lm,'ROUTES',frozenset({'french49'}))
    stored=json.loads(json.dumps(report));tampered=json.loads(json.dumps(report))
    row=next(r for r in tampered['rows'] if r['validation'].get('beats_baseline'));row['validation']['sharpe']='9.9'
    with pytest.raises(RuntimeRefused,match='^ENGINE_QUEUE_DENIED$'): lm.admit_report(tampered,p,ledger)
    rows=lm.admit_report(stored,p,ledger);admitted=[r['queue'] for r in rows if r.get('queue')]
    assert admitted and all(a['event']=='ELIGIBLE' for a in admitted) and ledger.total_trials()==trials  # no trial is recorded twice
    with pytest.raises(RuntimeRefused,match='^ENGINE_QUEUE_DENIED$'): lm.admit_report(stored,p,ledger)  # already ELIGIBLE
    from compertum.ai.engine.control import queue_state
    state=queue_state(b.store);assert state['vaults']['french-v1']['eligible']==[a['candidate_id'] for a in admitted] and state['vaults']['history-v1']['budget_used']==0
