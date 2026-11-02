"""tools/update_indices.py: holdings files become dated snapshots with adds and removes, the S&P 500 history gives point-in-time
members, and the pull asks only for names without history, with the right asof and exit day. Fixture files are written by the test."""
from itertools import product
import json
from pathlib import Path
import string
import sys
import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import update_indices as ui  # noqa: E402

NL=chr(10)
NAMES=[''.join(p) for p in product(string.ascii_uppercase,repeat=3)]


@pytest.fixture
def project(tmp_path,monkeypatch):
    monkeypatch.setattr(ui,'ROOT',tmp_path);monkeypatch.setattr(ui,'INDICES',tmp_path/'data'/'indices');monkeypatch.setattr(ui,'HISTORY',tmp_path/'data'/'history')
    (tmp_path/'data'/'indices'/'inbox').mkdir(parents=True);return tmp_path


def ishares(fund,as_of,tickers):
    head=[fund,'Fund Holdings as of,"'+as_of+'"','Inception Date,"May 15, 2000"','Shares Outstanding,"1,000,000.00"','Stock,"-"','Bond,"-"','Cash,"-"','Other,"-"',' ',
          'Ticker,Name,Sector,Asset Class,Market Value,Weight (%),Notional Value,Quantity,Price,Location,Exchange,Currency,FX Rate,Market Currency,Accrual Date']
    rows=[f'"{t}","NAME {t}","Information Technology","Equity","1,000.00","0.10","1,000.00","10.00","100.00","United States","NASDAQ","USD","1.00","USD","-"' for t in tickers]
    rows+=['"USD","USD CASH","Cash and/or Derivatives","Cash","10.00","0.01","10.00","10.00","100.00","United States","-","USD","1.00","USD","-"',
           '"ESZ6","S&P500 EMINI DEC 26","Cash and/or Derivatives","Futures","0.00","0.00","1.00","1.00","1.00","United States","CME","USD","1.00","USD","-"']
    return NL.join(head+rows+[' ','"The content contained herein is owned or licensed by BlackRock"'])+NL


def test_parse_holdings():
    as_of,tickers,skipped=ui.parse_holdings(ishares('iShares Core S&P 500 ETF','Oct 30, 2026',['AAPL','BRKB','BFB','P5N994']))
    assert as_of=='2026-10-30' and tickers==['AAPL','BF.B','BRK.B'] and skipped==['P5N994']
    assert ui.detect('IVV_holdings.csv',ishares('iShares Core S&P 500 ETF','Oct 30, 2026',[]))=='sp500'
    assert ui.detect('IWV_holdings.csv','x')=='russell3000' and ui.detect('other.csv','x') is None
    qqq='Fund Ticker,Security Identifier,Holding Ticker,Shares/Par Value,MarketValue,Weight,Name,Class of Shares,Sector,Date'+NL+NL.join(
        f'QQQ,000,{t} ,10,100,1.0,NAME,Common Stock,Tech,10/30/2026' for t in ['MSFT','GOOGL'])
    assert ui.parse_holdings(qqq)==('2026-10-30',['GOOGL','MSFT'],[]) and ui.detect('holdings.csv','Invesco QQQ Trust'+NL)=='nasdaq100'


def test_ingest_snapshots(project):
    inbox=project/'data'/'indices'/'inbox';first=NAMES[:500];second=NAMES[2:502];raw=project/'data'/'indices'/'sp500'/'raw'
    (inbox/'IVV_holdings.csv').write_text(ishares('iShares Core S&P 500 ETF','Oct 23, 2026',first),encoding='utf-8')
    out=ui.ingest();assert out[0]['as_of']=='2026-10-23' and out[0]['count']==500 and 'added' not in out[0] and not list(inbox.iterdir())
    (inbox/'IVV_holdings.csv').write_text(ishares('iShares Core S&P 500 ETF','Oct 30, 2026',second),encoding='utf-8')
    out=ui.ingest();assert out[0]['added']==NAMES[500:502] and out[0]['removed']==NAMES[:2] and out[0]['previous_as_of']=='2026-10-23'
    changes=[json.loads(x) for x in (project/'data'/'indices'/'sp500'/'changes.jsonl').read_text(encoding='utf-8').splitlines()]
    assert len(changes)==1 and changes[0]['added']==NAMES[500:502]
    assert len(list(raw.iterdir()))==2 and ui.latest('sp500')['tickers']==sorted(second)
    (inbox/'IVV_holdings.csv').write_text(ishares('iShares Core S&P 500 ETF','Oct 30, 2026',second),encoding='utf-8')
    assert ui.ingest()[0]['duplicate'] is True and len(list(raw.iterdir()))==3
    (inbox/'IVV_holdings.csv').write_text(ishares('iShares Core S&P 500 ETF','Oct 30, 2026',NAMES[3:503]),encoding='utf-8')
    assert ui.ingest()[0]['refused']=='SNAPSHOT_DATE_TAKEN' and (inbox/'IVV_holdings.csv').exists()
    (inbox/'IVV_holdings.csv').unlink();(inbox/'IVV_small.csv').write_text(ishares('iShares Core S&P 500 ETF','Nov 6, 2026',NAMES[:50]),encoding='utf-8')
    assert ui.ingest()[0]=={'file':'IVV_small.csv','index':'sp500','refused':'COUNT_OUT_OF_BOUNDS','count':50}
    assert ui.main(['ingest'])==1


def history_csv(path,rows):
    path.write_text('date,tickers'+NL+NL.join(f'{d},"'+','.join(t)+'"' for d,t in rows)+NL,encoding='utf-8')


def test_history_members(project):
    base=NAMES[:500];rows=[('2015-06-01',base),('2017-03-15',base[1:]+['NEWA']),('2024-02-01',base[1:]+['NEWB'])]
    source=project/'sp.csv';history_csv(source,rows)
    report=ui.import_history(source);assert report['rows']==3 and report['members_since_2016']==501
    h=ui.load_history()
    assert ui.members_on(h,'2016-01-04')==set(base) and 'NEWA' in ui.members_on(h,'2017-03-15') and ui.members_on(h,'2015-01-01')==set()
    left=ui.since(h,ui.HISTORY_START);assert left[base[0]]=='2017-03-15' and left['NEWA'] is None and 'NEWB' not in left
    history_csv(source,rows[::-1])
    with pytest.raises(ValueError,match='HISTORY_DATES'): ui.import_history(source)


def test_pull_plan(project,monkeypatch):
    base=NAMES[:500];source=project/'sp.csv';history_csv(source,[('2015-06-01',base),('2017-03-15',base[1:]+['NEWA'])]);ui.import_history(source)
    for t in base[2:]: (project/'data'/'history'/t).mkdir(parents=True);(project/'data'/'history'/t/'manifest.json').write_text('{}',encoding='utf-8')
    plan=ui.pull(dry_run=True);assert plan['have']==498 and plan['todo']==3
    got={s['symbol']:(s['asof'],s['until']) for s in plan['symbols']}
    assert got=={base[0]:('2017-03-14','2017-03-14'),base[1]:('2023-12-31',None),'NEWA':('2023-12-31',None)}
    calls=[]
    import pull_bars
    def fake(client,symbol,years,feed,adjustment,out,dry_run,asof=None,refetch_empty=False,until=None,since=None,folder=None):
        calls.append((symbol,years[-1],asof,until))
        return {'symbol':symbol,'years':{},'requests':0,'market':{'refused':'ENGINE_MARKET_COVERAGE_INCOMPLETE'} if symbol=='NEWA' else {'label':'x'}}
    monkeypatch.setattr(pull_bars,'pull_symbol',fake)
    report=ui.pull(client=object(),credentials={})
    assert report['loaded']==2 and report['failed']==['NEWA'] and (base[0],2017,'2017-03-14','2017-03-14') in calls
    assert ui.pull(dry_run=True)['waiting']==3 and ui.pull(dry_run=True,retry_now=True)['todo']==3
    shown=json.loads((project/'data'/'indices'/'pull-progress.json').read_text(encoding='utf-8'))
    assert shown['schema']=='pull-progress-v1' and shown['finished'] is True and shown['done']==3 and shown['loaded']==2 and shown['failed']==1
    assert shown['recent'][-1]=={'symbol':'NEWA','status':'failed','code':'ENGINE_MARKET_COVERAGE_INCOMPLETE'} and shown['pending']==[]
    assert pull_bars.year_params('X',2017,'sip','split','2017-03-15','2017-03-15')['end']=='2017-03-15T23:59:59Z'


def test_ticker_periods(project):
    base=NAMES[:498]+['DOW','CCEP'];source=project/'sp.csv'
    history_csv(source,[('2015-06-01',base),('2016-02-01',NAMES[:498]+['DOW','QQA']),('2017-09-01',NAMES[:498]+['QQA','QQB']),('2019-04-02',NAMES[:498]+['DOW','QQA'])])
    ui.import_history(source);w=ui.wanted()
    assert w['DOW-2017']['symbol']=='DOW' and w['DOW-2017']['until']=='2017-08-31' and w['DOW-2017']['left']=='2017-09-01'
    assert w['DOW']['since']=='2019-04-02' and w['DOW']['until'] is None and w['CCEP']['until']=='2016-01-29' and w['CCEP']['asof']=='2016-01-29'
    assert w['CCEP']['symbol']=='CCE' and ui.span(w['CCEP'])==[2016] and ui.span(w['DOW'])==list(range(2019,2024)) and ui.span(w['DOW-2017'])==[2016,2017]
    ui.pull(dry_run=True)
    import importlib
    lm=importlib.import_module('compertum.ai.engine.library_multi');ui.write_periods()
    periods=json.loads((project/'data'/'indices'/'sp500'/'periods.json').read_text(encoding='utf-8'))['periods']
    assert lm.resolve_member('DOW','2017-08-31',periods)=='DOW-2017' and lm.resolve_member('DOW','2018-06-01',periods) is None
    assert lm.resolve_member('DOW','2019-04-02',periods)=='DOW' and lm.resolve_member('AAPL','2018-06-01',periods)=='AAPL'


def test_busy_progress(project,monkeypatch):
    def busy(self,target): raise PermissionError('in use')
    monkeypatch.setattr(Path,'replace',busy);monkeypatch.setattr(ui.time,'sleep',lambda s:None)
    assert ui.progress({'schema':'pull-progress-v1','_started':0.0}) is False


def test_snapshot_dates(project):
    snap=project/'data'/'indices'/'russell3000'/'snapshots';snap.mkdir(parents=True)
    (snap/'2026-10-30.json').write_text(json.dumps({'as_of':'2026-10-30','tickers':['FTI'],'count':1}),encoding='utf-8')
    base=NAMES[:499]+['FTI'];source=project/'sp.csv'
    history_csv(source,[('2015-06-01',base),('2021-02-12',NAMES[:499]+['QQA'])]);ui.import_history(source)
    w=ui.wanted()
    assert w['FTI']['until'] is None and w['FTI']['asof']=='2026-10-30' and w['FTI']['since']=='2017-01-17' and w['FTI-2017']['until']=='2017-01-13'
