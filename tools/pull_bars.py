"""Pull years of Alpaca daily bars into engine history evidence. Owner-started, read-only, $0.

    python tools/pull_bars.py --symbols SPY,QQQ [--start 2016] [--end 2023] [--feed sip] [--adjustment split]
                              [--asof YYYY-MM-DD] [--refetch-empty] [--credentials PATH] [--out data/history] [--dry-run]

For each symbol and each calendar year the tool sends one bars request (1Day, 100 rows per page), follows every page, and retains the
exchange exactly as compertum.data.alpaca reads it: an alpaca-bars-v1 envelope per symbol and year at data/history/SYMBOL/YEAR.json,
then a history manifest at data/history/SYMBOL/manifest.json. An existing envelope is never replaced, so a second run fills gaps only.
Every envelope is reread with the evidence reader before it is written, and every manifest is loaded through the engine's own loader.
The credential file is the owner's Desktop/v20/.env (entries alpaca_key and alpaca_secret, authorized 9 October 2026). The values go
into the request headers and are never printed, logged or written. Years end before 2024, the vault period, as the evidence reader
requires. The data folder is outside Git. See docs/ENGINE_PLAN.md, "History markets".

Alpaca reads a symbol as of the asof date and returns that company's whole history under the symbol. Without --asof each year uses
its own last day, so a company renamed later (FB to META in 2022) has empty years before the rename. With --asof DATE each year uses
the later of DATE and the year's last day. --refetch-empty moves an envelope without bars to SYMBOL/superseded/ and fetches it again.
tools/update_indices.py also passes until=DATE for a stock that left the S&P 500: its last envelope ends on that day.
"""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import sys
import time
import httpx
from compertum.data.alpaca import HOST,read_bar_evidence
from compertum.data.errors import DataError
from compertum.runtime.errors import RuntimeRefused

ROOT=Path(__file__).resolve().parents[1]
DEFAULT_CREDENTIALS=Path.home()/'Desktop'/'v20'/'.env'
KEY_NAMES=('alpaca_key','alpaca_secret')
PAGE_LIMIT=100
MAX_PAGES=40
PAUSE_SECONDS=0.35
RETRY_SECONDS=15
RETRIES=4
FIRST_YEAR=2000
LAST_YEAR=2023


def credentials(path):
    try: lines=Path(path).read_text(encoding='utf-8').splitlines()
    except OSError: raise RuntimeRefused('CREDENTIAL_FILE_UNAVAILABLE') from None
    found={}
    for line in lines:
        if '=' not in line or line.lstrip().startswith('#'): continue
        name,value=line.split('=',1);name=name.strip();value=value.strip().strip('"').strip("'")
        if name in KEY_NAMES and value: found[name]=value
    if set(found)!=set(KEY_NAMES): raise RuntimeRefused('CREDENTIAL_ENTRIES_MISSING')
    return {'APCA-API-KEY-ID':found['alpaca_key'],'APCA-API-SECRET-KEY':found['alpaca_secret']}


def stamp(): return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00','Z')


def year_params(symbol,year,feed,adjustment,asof=None,until=None):
    last=until if until and until[:4]==str(year) else f'{year}-12-31'
    return {'symbols':symbol,'start':f'{year}-01-01T00:00:00Z','end':f'{last}T23:59:59Z','timeframe':'1Day','adjustment':adjustment,
            'feed':feed,'asof':max(last,asof or ''),'sort':'asc','currency':'USD','limit':PAGE_LIMIT}


def bar_count(raw):
    return sum(len(v) for page in json.loads(raw)['pages'] for v in (json.loads(page['body_utf8']).get('bars') or {}).values())


def fetch_year(client,symbol,year,feed,adjustment,asof=None,until=None):
    params=year_params(symbol,year,feed,adjustment,asof,until);request_id=f'{symbol}-{year}-1Day-{adjustment}';pages=[];token=None
    while True:
        sent=dict(params)
        if token is not None: sent['page_token']=token
        for attempt in range(RETRIES+1):
            started=stamp();time.sleep(PAUSE_SECONDS)
            try: reply=client.get('/v2/stocks/bars',params=sent)
            except httpx.HTTPError as error: raise RuntimeRefused('PROVIDER_TRANSPORT_'+type(error).__name__.upper()) from None
            received=stamp()
            if reply.status_code==200: break
            if reply.status_code==429 and attempt<RETRIES: time.sleep(RETRY_SECONDS*(attempt+1));continue
            raise RuntimeRefused(f'PROVIDER_STATUS_{reply.status_code}')
        body=reply.text
        pages.append({'request_id':request_id,'page':len(pages),'params':sent,'status':200,'started_utc':started,'received_utc':received,
                      'body_utf8':body,'body_sha256':hashlib.sha256(body.encode('utf-8')).hexdigest()})
        try: token=json.loads(body).get('next_page_token')
        except ValueError: raise RuntimeRefused('PROVIDER_RESPONSE_INVALID') from None
        if token is None: break
        if len(pages)>=MAX_PAGES: raise RuntimeRefused('PROVIDER_PAGE_BOUND')
    envelope={'schema_version':'alpaca-bars-v1','host':HOST,'requests':[{'id':request_id,'path':'/v2/stocks/bars','params':params}],'pages':pages}
    raw=json.dumps(envelope,separators=(',',':')).encode('utf-8')
    try: evidence=read_bar_evidence(raw,universe=None)
    except DataError as error: raise RuntimeRefused('PROVIDER_EVIDENCE_'+error.code) from None
    return raw,evidence


def pull_symbol(client,symbol,years,feed,adjustment,out,dry_run,asof=None,refetch_empty=False,until=None):
    folder=out/symbol;folder.mkdir(parents=True,exist_ok=True);record={'symbol':symbol,'years':{},'requests':0}
    for year in years:
        path=folder/f'{year}.json'
        if path.exists() and refetch_empty and bar_count(path.read_bytes())==0:
            if dry_run: record['years'][year]='would refetch';continue
            aside=folder/'superseded'/f'{year}.json';aside.parent.mkdir(exist_ok=True)
            if aside.exists(): raise RuntimeRefused('SUPERSEDED_EXISTS')
            path.replace(aside)
        if path.exists(): record['years'][year]='kept';continue
        if dry_run: record['years'][year]='would fetch';continue
        raw,evidence=fetch_year(client,symbol,year,feed,adjustment,asof,until)
        path.write_bytes(raw);record['requests']+=len(json.loads(raw)['pages'])
        record['years'][year]={'rows':len(evidence.rows),'missing':len(evidence.missing),'bytes':len(raw)}
    chunks=[]
    for year in years:
        path=folder/f'{year}.json'
        if not path.exists(): continue
        relative=path.relative_to(ROOT).as_posix()
        chunks.append({'path':relative,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
    if chunks and not dry_run:
        manifest={'schema_version':'1','kind':'history','symbol':symbol,'feed':feed,'adjustment':adjustment,'chunks':chunks}
        (folder/'manifest.json').write_text(json.dumps(manifest,indent=1),encoding='utf-8')
        from compertum.ai.engine.real_market import load_market_manifest
        try:
            market,_=load_market_manifest(ROOT,(folder/'manifest.json').relative_to(ROOT).as_posix())
            record['market']={'label':market['label'],'sessions_available':market['provenance']['sessions_available'],
                              'start':market['provenance']['market_start'],'end':market['provenance']['market_end'],'manifest':(folder/'manifest.json').relative_to(ROOT).as_posix()}
        except RuntimeRefused as error: record['market']={'refused':error.code}
    return record


def main(argv=None):
    parser=argparse.ArgumentParser(description='Pull Alpaca daily bars into engine history evidence (owner-started, read-only).')
    parser.add_argument('--symbols',required=True);parser.add_argument('--start',type=int,default=2016);parser.add_argument('--end',type=int,default=LAST_YEAR)
    parser.add_argument('--feed',choices=('sip','iex'),default='sip');parser.add_argument('--adjustment',choices=('split','raw'),default='split')
    parser.add_argument('--credentials',type=Path,default=DEFAULT_CREDENTIALS);parser.add_argument('--out',type=Path,default=ROOT/'data'/'history')
    parser.add_argument('--host',default=HOST);parser.add_argument('--dry-run',action='store_true')
    parser.add_argument('--asof',default=None);parser.add_argument('--refetch-empty',action='store_true')
    args=parser.parse_args(argv)
    symbols=[s.strip().upper() for s in args.symbols.split(',') if s.strip()]
    if not symbols or not FIRST_YEAR<=args.start<=args.end<=LAST_YEAR: print(json.dumps({'refused':'ARGUMENTS'}));return 2
    if args.asof is not None:
        try: args.asof=datetime.strptime(args.asof,'%Y-%m-%d').date().isoformat()
        except ValueError: print(json.dumps({'refused':'ARGUMENTS'}));return 2
    years=list(range(args.start,args.end+1));out=args.out if args.out.is_absolute() else ROOT/args.out
    if not out.resolve().is_relative_to(ROOT): print(json.dumps({'refused':'OUT_OUTSIDE_PROJECT'}));return 2
    try: headers={} if args.dry_run else credentials(args.credentials)
    except RuntimeRefused as error: print(json.dumps({'refused':error.code}));return 2
    records=[];started=time.time()
    with httpx.Client(base_url=args.host,headers=headers,timeout=60,trust_env=False) as client:
        for symbol in symbols:
            try: records.append(pull_symbol(client,symbol,years,args.feed,args.adjustment,out,args.dry_run,args.asof,args.refetch_empty))
            except RuntimeRefused as error: records.append({'symbol':symbol,'refused':error.code})
    summary={'at':stamp(),'feed':args.feed,'adjustment':args.adjustment,'years':[args.start,args.end],'asof':args.asof,'elapsed_seconds':round(time.time()-started,1),
             'requests':sum(r.get('requests',0) for r in records),'symbols':records}
    if not args.dry_run:
        out.mkdir(parents=True,exist_ok=True);(out/f'pull-{datetime.now():%Y%m%d-%H%M%S}.json').write_text(json.dumps(summary,indent=1),encoding='utf-8')
    print(json.dumps(summary,indent=1))
    return 0 if all('refused' not in r for r in records) else 1


if __name__=='__main__': sys.exit(main())
