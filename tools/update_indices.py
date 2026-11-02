"""Index membership for the Russell 3000, the S&P 500 and the Nasdaq-100. Owner-run each week, $0, no scheduled task.

    python tools/update_indices.py                    weekly: ingest the inbox, then pull history for names without it
    python tools/update_indices.py ingest [--as-of YYYY-MM-DD]
    python tools/update_indices.py sp500-history --source CSV [--check FOLDER]
    python tools/update_indices.py pull [--dry-run] [--limit N] [--retry]
    python tools/update_indices.py status

Route 1 (owner, 1 November 2026): each week the owner saves the fund holdings files into data/indices/inbox/: IWV (iShares Russell
3000 ETF), IVV (iShares Core S&P 500 ETF) and QQQ (Invesco QQQ Trust, which holds the Nasdaq-100). Ingest reads each file, keeps the
equity tickers, writes a dated snapshot, records the names added and removed since the previous snapshot, and moves the file to the
index's raw/ folder. A file is never deleted.

Route 3 (owner, 1 November 2026): sp500-history imports the point-in-time S&P 500 membership from the GitHub dataset fja05680/sp500.
With --check it compares every month with month-end IVV holdings from riazarbi/sp500-scraper and writes the result next to it.

Pull fetches 2016-2023 daily bars through tools/pull_bars.py for every snapshot name and every S&P 500 member since 2016 that has no
history. A current name uses its snapshot date as the Alpaca asof date, so a renamed company keeps its earlier years. A past member
uses the session before the day it left the index as the asof date and the last day requested: Alpaca maps a ticker asked for on
or after a delisting to a stub. Its bars stop on its last day with trades, so a later reuse of its ticker cannot replace it.
Failed names wait 28 days before the next try; --retry tries them again now. PERIODS splits a ticker that two companies used, each
company in its own folder: DOW (Dow Chemical to 31 August 2017 in DOW-2017, Dow Inc from 2 April 2019), FTI (FMC Technologies to
13 January 2017 in FTI-2017, TechnipFMC from 17 January 2017 to 12 February 2021) and IR (Ingersoll-Rand plc to 28 February 2020 in IR-2020, then
Ingersoll Rand Inc, formerly Gardner Denver, with its history from 12 May 2017). In a period, until and since are membership dates,
last is the last trading day and data_since the first day pulled. The table is written to sp500/periods.json for the engine.
ALIASES names the ticker a past member traded under when the dataset lists its later ticker (CCEP traded as CCE, WYND as WYN).
ASOF gives a later asof date where Alpaca's mapping at the exit returns a stub (LVLT). Alpaca's daily bars start in 2016, so six
members that left the index before March 2016 (BRCM, CNX, FOSL, GMCR, PCL, PCP) stay below the loader's 50-session minimum.
Each pull writes data/indices/pull-progress.json after every name; the harness command /data shows it.
Everything is written under data/indices, which is outside Git. See docs/ENGINE_PLAN.md, "Index membership".
"""
import argparse
import bisect
import csv
from datetime import date,datetime,timedelta,timezone
import hashlib
import io
import json
from pathlib import Path
import re
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
INDICES=ROOT/'data'/'indices'
HISTORY=ROOT/'data'/'history'
SYMBOL=re.compile(r'[A-Z]{1,5}(?:\.[A-Z])?')
FUNDS={'russell3000':{'fund':'IWV','names':('ishares russell 3000',),'bounds':(2300,3200)},
       'sp500':{'fund':'IVV','names':('ishares core s&p 500',),'bounds':(480,520)},
       'nasdaq100':{'fund':'QQQ','names':('invesco qqq','qqq trust'),'bounds':(95,110)}}
CLASS_SHARES={'BRKB':'BRK.B','BRKA':'BRK.A','BFB':'BF.B','BFA':'BF.A','LENB':'LEN.B','HEIA':'HEI.A','MOGA':'MOG.A','MOGB':'MOG.B',
              'GEFB':'GEF.B','CWENA':'CWEN.A','UHALB':'UHAL.B','CRDA':'CRD.A','CRDB':'CRD.B','BIOB':'BIO.B','HVTA':'HVT.A',
              'MKCV':'MKC.V','GTNA':'GTN.A','LGFA':'LGF.A','LGFB':'LGF.B','JWA':'JW.A','AKOB':'AKO.B','WSOB':'WSO.B','TAPA':'TAP.A'}
HISTORY_START='2016-01-01';HISTORY_END='2023-12-31';FIRST_YEAR=2016;LAST_YEAR=2023;RETRY_DAYS=28
PERIODS={'DOW':[{'key':'DOW-2017','until':'2017-09-01','last':'2017-08-31'},{'key':'DOW','since':'2019-04-02'}],
         'FTI':[{'key':'FTI-2017','until':'2017-01-17','last':'2017-01-13'},{'key':'FTI','since':'2017-01-17','until':'2021-02-12'}],
         'IR':[{'key':'IR-2020','until':'2020-03-03','last':'2020-02-28'},{'key':'IR','since':'2020-03-03','data_since':'2017-05-12'}]}
ALIASES={'CCEP':'CCE','WYND':'WYN'}
ASOF={'LVLT':'2017-12-31'}


def session_before(day):
    from compertum.data.calendar import session_times
    current=date.fromisoformat(day)-timedelta(days=1)
    for _ in range(10):
        try: session_times(current.isoformat());return current.isoformat()
        except Exception: current-=timedelta(days=1)
    raise ValueError('CALENDAR')


def stamp(): return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00','Z')


def normalize(ticker):
    t=ticker.strip().upper().replace(' ','.').replace('/','.').replace('-','.')
    return CLASS_SHARES.get(t,t)


def _date(text):
    text=text.strip().strip('"').strip()
    for form in ('%b %d, %Y','%m/%d/%Y','%Y-%m-%d','%d-%b-%Y','%B %d, %Y','%Y%m%d'):
        try: return datetime.strptime(text,form).date().isoformat()
        except ValueError: pass
    return None


def detect(name,text):
    head=text[:3000].lower()
    for index,spec in FUNDS.items():
        if any(n in head for n in spec['names']): return index
    stem=Path(name).name.upper()
    for index,spec in FUNDS.items():
        if stem.startswith(spec['fund']): return index
    return None


def parse_holdings(text):
    lines=text.splitlines();as_of=None;header=None
    for i,line in enumerate(lines[:60]):
        cells=next(csv.reader([line]),[])
        low=[c.strip().lower() for c in cells]
        if as_of is None and low and ('as of' in low[0] or low[0] in ('date','as of date')) and len(cells)>1: as_of=_date(cells[1])
        if any(c in ('ticker','holding ticker','symbol') for c in low): header=i;break
    if header is None: raise ValueError('HOLDINGS_HEADER_MISSING')
    reader=csv.DictReader(io.StringIO('\n'.join(lines[header:])))
    fields={f.strip().lower():f for f in reader.fieldnames or []}
    tick=next(fields[k] for k in ('ticker','holding ticker','symbol') if k in fields)
    klass=next((fields[k] for k in ('asset class','assetclass','security type') if k in fields),None)
    when=next((fields[k] for k in ('date','as of date','as of') if k in fields),None)
    tickers=set();skipped=[]
    for row in reader:
        raw=(row.get(tick) or '').strip()
        if not raw or raw.startswith(('The content','©','Holdings subject')): continue
        if klass and (row.get(klass) or '').strip().lower() not in ('equity','common stock','stock'): continue
        if when and as_of is None: as_of=_date(row.get(when) or '')
        symbol=normalize(raw)
        if SYMBOL.fullmatch(symbol): tickers.add(symbol)
        else: skipped.append(raw)
    return as_of,sorted(tickers),sorted(set(skipped))


def snapshots(index):
    folder=INDICES/index/'snapshots'
    return sorted(folder.glob('*.json')) if folder.exists() else []


def latest(index):
    found=snapshots(index)
    return json.loads(found[-1].read_text(encoding='utf-8')) if found else None


def ingest(as_of_override=None):
    inbox=INDICES/'inbox';inbox.mkdir(parents=True,exist_ok=True);out=[]
    for path in sorted(p for p in inbox.iterdir() if p.is_file()):
        raw=path.read_bytes();sha=hashlib.sha256(raw).hexdigest();text=raw.decode('utf-8-sig',errors='replace')
        index=detect(path.name,text)
        if index is None: out.append({'file':path.name,'refused':'FUND_UNKNOWN'});continue
        try: as_of,tickers,skipped=parse_holdings(text)
        except ValueError as error: out.append({'file':path.name,'index':index,'refused':str(error)});continue
        as_of=as_of_override or as_of
        if as_of is None: out.append({'file':path.name,'index':index,'refused':'AS_OF_MISSING'});continue
        low,high=FUNDS[index]['bounds']
        if not low<=len(tickers)<=high: out.append({'file':path.name,'index':index,'refused':'COUNT_OUT_OF_BOUNDS','count':len(tickers)});continue
        target=INDICES/index/'snapshots'/f'{as_of}.json'
        if target.exists():
            old=json.loads(target.read_text(encoding='utf-8'))
            if old['source_sha256']!=sha: out.append({'file':path.name,'index':index,'refused':'SNAPSHOT_DATE_TAKEN','as_of':as_of});continue
            kept=INDICES/index/'raw'/f'{as_of}-duplicate-{sha[:8]}-{path.name}';kept.parent.mkdir(parents=True,exist_ok=True)
            if not kept.exists(): path.replace(kept)
            out.append({'file':path.name,'index':index,'as_of':as_of,'duplicate':True});continue
        before=[s for s in snapshots(index) if s.stem<as_of];previous=json.loads(before[-1].read_text(encoding='utf-8')) if before else None
        kept=INDICES/index/'raw'/f'{as_of}-{sha[:8]}-{path.name}';kept.parent.mkdir(parents=True,exist_ok=True)
        snapshot={'schema_version':'1','index':index,'fund':FUNDS[index]['fund'],'as_of':as_of,'ingested_utc':stamp(),
                  'source_file':kept.relative_to(ROOT).as_posix(),'source_sha256':sha,'count':len(tickers),'tickers':tickers,'skipped':skipped}
        target.parent.mkdir(parents=True,exist_ok=True);target.write_text(json.dumps(snapshot,indent=1),encoding='utf-8');path.replace(kept)
        record={'file':path.name,'index':index,'as_of':as_of,'count':len(tickers),'skipped':len(skipped)}
        if previous:
            change={'index':index,'as_of':as_of,'previous_as_of':previous['as_of'],
                    'added':sorted(set(tickers)-set(previous['tickers'])),'removed':sorted(set(previous['tickers'])-set(tickers))}
            with (INDICES/index/'changes.jsonl').open('a',encoding='utf-8') as stream: stream.write(json.dumps(change)+'\n')
            record.update(added=change['added'],removed=change['removed'],previous_as_of=previous['as_of'])
        if index=='sp500': record['history_check']=history_check(as_of,tickers)
        out.append(record)
    return out


def load_history():
    path=INDICES/'sp500'/'history.json'
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else None


def members_on(history,day):
    i=bisect.bisect_right(history['dates'],day)-1
    return set(history['members'][i]) if i>=0 else set()


def history_check(as_of,tickers):
    history=load_history()
    if history is None: return None
    m=members_on(history,as_of)
    return {'history_date':history['dates'][bisect.bisect_right(history['dates'],as_of)-1],'only_holdings':sorted(set(tickers)-m),'only_history':sorted(m-set(tickers))}


def import_history(source,check=None):
    raw=Path(source).read_bytes();rows=list(csv.reader(io.StringIO(raw.decode('utf-8-sig'))))
    if not rows or [c.strip().lower() for c in rows[0]]!=['date','tickers']: raise ValueError('HISTORY_HEADER')
    dates=[];members=[]
    for day,names in rows[1:]:
        day=_date(day)
        if day is None or (dates and day<=dates[-1]): raise ValueError('HISTORY_DATES')
        tickers=sorted({normalize(t) for t in names.split(',') if t.strip()})
        if not 480<=len(tickers)<=520: raise ValueError('HISTORY_COUNT')
        dates.append(day);members.append(tickers)
    value={'schema_version':'1','index':'sp500','source':Path(source).resolve().relative_to(ROOT).as_posix(),'source_sha256':hashlib.sha256(raw).hexdigest(),
           'imported_utc':stamp(),'first':dates[0],'last':dates[-1],'dates':dates,'members':members}
    target=INDICES/'sp500'/'history.json';target.parent.mkdir(parents=True,exist_ok=True)
    report={'rows':len(dates),'first':dates[0],'last':dates[-1],'members_since_2016':len(since(value,HISTORY_START))}
    if check: report['check']=cross_check(value,Path(check))
    value['check']=report.get('check');target.write_text(json.dumps(value),encoding='utf-8')
    return report


def since(history,start,end=HISTORY_END):
    last={};dates=history['dates']
    i=max(0,bisect.bisect_right(dates,start)-1)
    for k in range(i,len(dates)):
        if dates[k]>end: break
        for t in history['members'][k]: last[t]=k
    return {t:(dates[k+1] if k+1<len(dates) and dates[k+1]<=end else None) for t,k in last.items()}


def cross_check(history,folder):
    months=[];renames={}
    for path in sorted(folder.glob('*.csv')):
        day=_date(path.stem)
        if day is None: continue
        with path.open(encoding='utf-8') as stream: held={normalize(r['symbol']) for r in csv.DictReader(stream) if r.get('asset_class')=='Equity'}
        held={t for t in held if SYMBOL.fullmatch(t)};m=members_on(history,day)
        months.append({'date':day,'history':len(m),'holdings':len(held),'only_holdings':sorted(held-m),'only_history':sorted(m-held)})
    exact=sum(1 for x in months if not x['only_holdings'] and not x['only_history'])
    later=[x for x in months if x['date']>='2019-01-01']
    return {'source':folder.resolve().relative_to(ROOT).as_posix(),'months':len(months),'exact':exact,
            'mean_differences':round(sum(len(x['only_holdings'])+len(x['only_history']) for x in months)/max(1,len(months)),2),
            'mean_differences_since_2019':round(sum(len(x['only_holdings'])+len(x['only_history']) for x in later)/max(1,len(later)),2),
            'by_month':months}


def wanted():
    out={}
    for index in FUNDS:
        snap=latest(index)
        if snap:
            for t in snap['tickers']: out.setdefault(t,{'symbol':t,'asof':snap['as_of'],'until':None,'since':None,'why':[]})['why'].append(index)
    history=load_history();present=set(out)
    if history:
        names=since(history,HISTORY_START);present|=set(names)
        for t,left in names.items():
            if t in PERIODS: continue
            entry=out.setdefault(t,{'symbol':ALIASES.get(t,t),'asof':None,'until':None,'since':None,'why':[]});entry['why'].append('sp500-history')
            if entry['asof'] is None:
                last=session_before(left) if left else None
                entry.update(asof=max(last or HISTORY_END,ASOF.get(t,'')),until=last,left=left)
    for t,periods in PERIODS.items():
        if t not in present: continue
        for p in periods:
            if (p.get('until') or '9999')<=HISTORY_START or (p.get('since') or '')>HISTORY_END: continue
            listed=p['key'] in out;entry=out.setdefault(p['key'],{'symbol':t,'why':[]});last=p.get('last') or (session_before(p['until']) if p.get('until') else None)
            if listed: entry['since']=p.get('data_since') or p.get('since')
            else: entry.update(asof=last or HISTORY_END,until=last,since=p.get('data_since') or p.get('since'),left=p.get('until'))
            entry['why'].append('period')
    return out


def write_periods():
    target=INDICES/'sp500'/'periods.json';target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps({'schema_version':'1','periods':PERIODS},indent=1),encoding='utf-8')


def span(entry):
    first=FIRST_YEAR
    if entry.get('since'): first=max(first,int(entry['since'][:4]))
    last=int(entry['until'][:4]) if entry['until'] else LAST_YEAR
    return list(range(first,last+1))


def progress(state,path=None):
    path=path or INDICES/'pull-progress.json';state['updated_utc']=stamp()
    text=json.dumps({k:v for k,v in state.items() if not k.startswith('_')},indent=1)
    for attempt in range(5):
        try:
            path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_suffix('.tmp')
            tmp.write_text(text,encoding='utf-8');tmp.replace(path);return True
        except OSError: time.sleep(0.05*(attempt+1))
    return False


def pull(dry_run=False,limit=None,client=None,credentials=None,retry_now=False,job='History pull'):
    sys.path.insert(0,str(ROOT/'tools'));import pull_bars
    status_path=INDICES/'pull-status.json';status=json.loads(status_path.read_text(encoding='utf-8')) if status_path.exists() else {}
    today=date.today().isoformat();retry=(date.today()-timedelta(days=RETRY_DAYS)).isoformat()
    todo=[];have=0;waiting=0
    if not dry_run and load_history(): write_periods()
    for t,entry in sorted(wanted().items()):
        if (HISTORY/t/'manifest.json').exists() and status.get(t,{}).get('ok',True): have+=1;continue
        if not retry_now and status.get(t,{}).get('tried','')>retry: waiting+=1;continue
        todo.append((t,entry))
    if limit is not None: todo=todo[:limit]
    report={'at':stamp(),'have':have,'waiting':waiting,'todo':len(todo),'dry_run':dry_run,'symbols':[]}
    if dry_run or not todo:
        report['symbols']=[{'symbol':t,'request':e['symbol'],'asof':e['asof'],'until':e['until'],'since':e.get('since'),'years':span(e),'why':e['why']} for t,e in todo];return report
    import httpx
    started=time.time()
    headers=credentials if credentials is not None else pull_bars.credentials(pull_bars.DEFAULT_CREDENTIALS)
    own=client is None
    state={'schema':'pull-progress-v1','job':job,'started_utc':stamp(),'total':len(todo),'done':0,'loaded':0,'failed':0,'current':None,
           'rate_per_min':None,'eta_minutes':None,'finished':False,'recent':[],'pending':[t for t,_ in todo],'_started':time.time()}
    progress(state)
    if own: client=httpx.Client(base_url=pull_bars.HOST,headers=headers,timeout=60,trust_env=False)
    try:
        for t,entry in todo:
            years_wanted=span(entry);state['pending']=state['pending'][1:]
            state['current']={'symbol':t,'years':f'{years_wanted[0]}-{years_wanted[-1]}'};progress(state)
            try: record=pull_bars.pull_symbol(client,entry['symbol'],years_wanted,'sip','split',HISTORY,False,entry['asof'],True,until=entry['until'],since=entry.get('since'),folder=t)
            except Exception as error: record={'symbol':entry['symbol'],'refused':getattr(error,'code',type(error).__name__)}
            record.update(key=t,asof=entry['asof'],until=entry['until'],since=entry.get('since'),why=entry['why']);report['symbols'].append(record)
            ok='market' in record and 'refused' not in record['market']
            code=record.get('refused') or (record.get('market') or {}).get('refused')
            status[t]={'tried':today,'ok':ok,'code':code}
            status_path.parent.mkdir(parents=True,exist_ok=True);status_path.write_text(json.dumps(status,indent=1,sort_keys=True),encoding='utf-8')
            state['done']+=1;state['loaded' if ok else 'failed']+=1
            state['recent']=(state['recent']+[{'symbol':t,'status':'loaded' if ok else 'failed',**({} if ok else {'code':code})}])[-8:]
            minutes=max((time.time()-state['_started'])/60,1e-6);state['rate_per_min']=round(state['done']/minutes,2)
            state['eta_minutes']=round((state['total']-state['done'])/state['rate_per_min'],1) if state['rate_per_min'] else None;progress(state)
    finally:
        state['current']=None;state['finished']=True;progress(state)
        if own: client.close()
    report['elapsed_seconds']=round(time.time()-started,1);report['loaded']=sum(1 for r in report['symbols'] if status[r['key']]['ok'])
    report['failed']=sorted(r['key'] for r in report['symbols'] if not status[r['key']]['ok'])
    log=INDICES/'pulls'/f'pull-{datetime.now():%Y%m%d-%H%M%S}.json';log.parent.mkdir(parents=True,exist_ok=True);log.write_text(json.dumps(report,indent=1),encoding='utf-8')
    report['log']=log.relative_to(ROOT).as_posix();report['symbols']=len(report['symbols'])
    return report


def status_report():
    out={}
    for index in FUNDS:
        found=snapshots(index);snap=latest(index)
        out[index]={'snapshots':len(found),'latest':snap and snap['as_of'],'count':snap and snap['count'],
                    'with_history':snap and sum(1 for t in snap['tickers'] if (HISTORY/t/'manifest.json').exists())}
    history=load_history()
    if history:
        names=since(history,HISTORY_START)
        out['sp500-history']={'first':history['first'],'last':history['last'],'members_since_2016':len(names),
                              'with_history':sum(1 for t in names if (HISTORY/t/'manifest.json').exists())}
    out['inbox']=sorted(p.name for p in (INDICES/'inbox').iterdir()) if (INDICES/'inbox').exists() else []
    return out


def main(argv=None):
    parser=argparse.ArgumentParser(description='Index membership: weekly holdings ingest, S&P 500 history, history pulls.')
    sub=parser.add_subparsers(dest='command')
    a=sub.add_parser('ingest');a.add_argument('--as-of')
    b=sub.add_parser('sp500-history');b.add_argument('--source',required=True);b.add_argument('--check')
    c=sub.add_parser('pull');c.add_argument('--dry-run',action='store_true');c.add_argument('--limit',type=int);c.add_argument('--retry',action='store_true')
    sub.add_parser('status');w=sub.add_parser('weekly');w.add_argument('--no-pull',action='store_true')
    args=parser.parse_args(argv);command=args.command or 'weekly'
    try:
        if command=='ingest':
            as_of=_date(args.as_of) if args.as_of else None
            if args.as_of and as_of is None: print(json.dumps({'refused':'ARGUMENTS'}));return 2
            result={'ingested':ingest(as_of)}
        elif command=='sp500-history': result=import_history(args.source,args.check)
        elif command=='pull': result=pull(args.dry_run,args.limit,retry_now=args.retry)
        elif command=='status': result=status_report()
        else:
            result={'ingested':ingest()}
            if not getattr(args,'no_pull',False): result['pull']=pull()
            result['status']=status_report()
    except ValueError as error: print(json.dumps({'refused':str(error)}));return 2
    if command=='sp500-history' and result.get('check'): result['check']={k:v for k,v in result['check'].items() if k!='by_month'}
    print(json.dumps(result,indent=1))
    refused=[x for x in result.get('ingested',[]) if 'refused' in x] if isinstance(result,dict) else []
    return 1 if refused else 0


if __name__=='__main__': sys.exit(main())
