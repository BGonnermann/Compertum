"""Kenneth French Data Library files for the engine: fetch the two daily zips and write one manifest per series. Owner-started, $0.

    python tools/french_data.py fetch        # download into data/french/raw/ (an existing file is never replaced) and record the retrieval
    python tools/french_data.py manifests    # data/french/SERIES/manifest.json for the 49 value-weighted industries and Mkt

Owner, 2 November 2026: "go ahead with all three". The files keep the library's copyright ("Copyright Eugene F. Fama and Kenneth R. French");
they stay outside Git and are used for private research only. See src/compertum/ai/engine/french_market.py and docs/ENGINE_PLAN.md.
"""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import sys
import httpx

ROOT=Path(__file__).resolve().parents[1]
FOLDER=ROOT/'data'/'french'
BASE='https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/'
INDUSTRIES='49_Industry_Portfolios_daily_CSV.zip'
FACTORS='F-F_Research_Data_Factors_daily_CSV.zip'
TABLE='Average Value Weighted Returns -- Daily'


def stamp(): return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00','Z')


def fetch(folder=FOLDER,client=None):
    raw=folder/'raw';raw.mkdir(parents=True,exist_ok=True);record_path=raw/'retrieval.json'
    record=json.loads(record_path.read_text(encoding='utf-8')) if record_path.exists() else {}
    own=client is None;client=client or httpx.Client(timeout=120,trust_env=False,follow_redirects=False)
    try:
        for name in (INDUSTRIES,FACTORS):
            path=raw/name
            if not path.exists():
                reply=client.get(BASE+name)
                if reply.status_code!=200: raise SystemExit(json.dumps({'refused':f'HTTP_{reply.status_code}','file':name}))
                path.write_bytes(reply.content)
            data=path.read_bytes()
            record.setdefault(name,{'url':BASE+name,'retrieved_utc':stamp()})
            record[name].update(sha256=hashlib.sha256(data).hexdigest(),bytes=len(data))
    finally:
        if own: client.close()
    record_path.write_text(json.dumps(record,indent=1,sort_keys=True),encoding='utf-8');return record


def manifests(folder=FOLDER,root=ROOT):
    from compertum.ai.engine.french_market import open_file,read_table
    raw=folder/'raw';written=[]
    for name,table,series in ((INDUSTRIES,TABLE,None),(FACTORS,None,['Mkt'])):
        item={'path':(raw/name).relative_to(root).as_posix(),'sha256':hashlib.sha256((raw/name).read_bytes()).hexdigest()}
        columns,_=read_table(open_file(root,item),table)
        for key in series or columns:
            target=folder/key;target.mkdir(parents=True,exist_ok=True)
            body={'schema_version':'1','kind':'french','series':key,'table':table,'file':item,
                  'source':'Kenneth French Data Library, Copyright Eugene F. Fama and Kenneth R. French'}
            (target/'manifest.json').write_text(json.dumps(body,indent=1),encoding='utf-8');written.append(key)
    return written


def main(argv=None):
    parser=argparse.ArgumentParser(description='Kenneth French Data Library files for the engine.')
    parser.add_argument('command',choices=('fetch','manifests'))
    args=parser.parse_args(argv)
    result=fetch() if args.command=='fetch' else {'manifests':manifests()}
    print(json.dumps(result,indent=1,sort_keys=True));return 0


if __name__=='__main__': sys.exit(main())
