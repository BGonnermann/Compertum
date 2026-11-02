"""Engine markets from the Kenneth French Data Library: daily portfolio returns from 1926, survivorship-free, development only.

Owner, 2 November 2026: "go ahead with all three" (accept the library's terms for private research, raise the session cap, add the 49 daily
industry portfolios as a universe with its own vault). Source: https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html,
"Copyright Eugene F. Fama and Kenneth R. French"; files are built from CRSP and kept outside Git, unchanged, with their SHA-256.

A french manifest names one retained zip file, its SHA-256, a table and a series. The loader rechecks the file byte for byte, reads the
table, turns percent returns into a close series that starts at 100, and keeps only dates before CUTOFF: 2024 and 2025 are the product's
protected final period. A series starts the day after its last missing value (-99.99 or -999) before VALIDATION_START, so no gap is filled
and no later row decides the start; a missing value from VALIDATION_START on refuses the series. The series "Mkt" is
Mkt-RF plus RF from the factors file: the total return of all NYSE, AMEX and NASDAQ stocks. Portfolio returns include dividends.
Every French series uses the same calendar tiers, so no year is VALIDATION in one series and vault in another: TRAIN before VALIDATION_START,
VALIDATION before VAULT_START, and the vault up to CUTOFF. The dates are the 50/30/20 split of the Mkt series (25,648 sessions).
"""
from datetime import date
from decimal import Decimal
import hashlib
import io
from pathlib import Path
import zipfile
from compertum.runtime.errors import RuntimeRefused
from .real_market import MANIFEST_BYTES,_json,_read

CUTOFF='2024-01-01'
VALIDATION_START='1973-02-26'
VAULT_START='2003-08-14'
VAULT='french-v1'
FILE_BYTES=64*1024*1024
TEXT_BYTES=128*1024*1024
MISSING=(Decimal('-99.99'),Decimal('-999'))
START=Decimal(100)
PLACES=Decimal('1e-10')
MIN_SESSIONS=50


def read_table(text,table):
    """(columns, rows) of one table: the block under the title line `table`, or the first block when table is None."""
    lines=text.splitlines();start=0
    if table is not None:
        try: start=next(i for i,line in enumerate(lines) if line.strip()==table)+1
        except StopIteration: raise RuntimeRefused('ENGINE_MARKET_MANIFEST_INVALID') from None
    try: header=next(i for i in range(start,len(lines)) if lines[i].startswith(','))
    except StopIteration: raise RuntimeRefused('ENGINE_MARKET_INPUT_INVALID') from None
    columns=[c.strip() for c in lines[header].split(',')[1:]];rows=[]
    for line in lines[header+1:]:
        if not line.strip(): break
        cells=[c.strip() for c in line.split(',')]
        if len(cells)!=len(columns)+1 or len(cells[0])!=8 or not cells[0].isdigit(): raise RuntimeRefused('ENGINE_MARKET_INPUT_INVALID')
        try: rows.append((date(int(cells[0][:4]),int(cells[0][4:6]),int(cells[0][6:])).isoformat(),[Decimal(c) for c in cells[1:]]))
        except (ValueError,ArithmeticError): raise RuntimeRefused('ENGINE_MARKET_INPUT_INVALID') from None
    if not rows or any(a[0]>=b[0] for a,b in zip(rows,rows[1:])): raise RuntimeRefused('ENGINE_MARKET_INPUT_INVALID')
    return columns,rows


def open_file(root,item):
    """The retained zip, checked against the manifest's SHA-256, and the text of its one member."""
    if not isinstance(item,dict) or not isinstance(item.get('path'),str) or not isinstance(item.get('sha256'),str): raise RuntimeRefused('ENGINE_MARKET_MANIFEST_INVALID')
    raw=_read(root,item['path'],FILE_BYTES)
    if hashlib.sha256(raw).hexdigest()!=item['sha256']: raise RuntimeRefused('ENGINE_MARKET_EVIDENCE_CHANGED')
    try:
        archive=zipfile.ZipFile(io.BytesIO(raw));members=archive.infolist()
        if len(members)!=1 or members[0].file_size>TEXT_BYTES: raise RuntimeRefused('ENGINE_MARKET_INPUT_INVALID')
        return archive.read(members[0]).decode('latin-1')
    except (zipfile.BadZipFile,OSError): raise RuntimeRefused('ENGINE_MARKET_INPUT_INVALID') from None


def series_returns(columns,rows,series):
    """(date, percent return) pairs of one series; "Mkt" is Mkt-RF plus RF."""
    parts=['Mkt-RF','RF'] if series=='Mkt' else [series]
    if any(p not in columns for p in parts): raise RuntimeRefused('ENGINE_MARKET_MANIFEST_INVALID')
    index=[columns.index(p) for p in parts];out=[]
    for day,values in rows:
        picked=[values[i] for i in index]
        out.append((day,None if any(v in MISSING for v in picked) else sum(picked,Decimal(0))))
    return out


def load_french(project_root,manifest_path):
    root=Path(project_root).absolute()
    manifest=_json(_read(root,manifest_path,MANIFEST_BYTES),'ENGINE_MARKET_MANIFEST_INVALID')
    if (not isinstance(manifest,dict) or manifest.get('kind')!='french' or manifest.get('schema_version')!='1' or not isinstance(manifest.get('series'),str)
            or not isinstance(manifest.get('table'),(str,type(None)))): raise RuntimeRefused('ENGINE_MARKET_MANIFEST_INVALID')
    columns,rows=read_table(open_file(root,manifest.get('file')),manifest['table'])
    values=[(day,r) for day,r in series_returns(columns,rows,manifest['series']) if day<CUTOFF]
    if any(r is None and day>=VALIDATION_START for day,r in values): raise RuntimeRefused('ENGINE_MARKET_INPUT_INVALID')
    last_missing=max((i for i,(_,r) in enumerate(values) if r is None),default=-1);values=values[last_missing+1:]
    if len(values)<MIN_SESSIONS+1: raise RuntimeRefused('ENGINE_MARKET_COVERAGE_INCOMPLETE')
    closes=[];close=START
    for day,r in values:
        close=(close*(1+r/100)).quantize(PLACES)
        if close<=0: raise RuntimeRefused('ENGINE_MARKET_DENIED')
        closes.append((day,format(close,'f')))
    returns={day:format(r/100,'f') for day,r in values}
    return {'symbol':manifest['series'],'provider':'french','feed':Path(manifest['file']['path']).name,'adjustment':'total return',
            'chunks_sha256':[manifest['file']['sha256']],'table':manifest['table'],'closes':closes,'returns':returns,'vault':VAULT}


def build_french(project_root,manifest_path,*,sessions=None):
    from .market import market_csv
    history=load_french(project_root,manifest_path)
    if sessions is not None: raise RuntimeRefused('ENGINE_MARKET_DENIED')
    closes=history['closes'];rows=[]
    for day,close in closes[1:]: rows.append({'session':day,'close':close,'return':history['returns'][day]})
    train=[r for r in rows if r['session']<VALIDATION_START];validation=[r for r in rows if VALIDATION_START<=r['session']<VAULT_START]
    vault=[r for r in rows if r['session']>=VAULT_START]
    if min(len(train),len(validation),len(vault))<10: raise RuntimeRefused('ENGINE_MARKET_COVERAGE_INCOMPLETE')
    provenance={'provider':'french','feed':history['feed'],'symbol':history['symbol'],'table':history['table'],'adjustment':history['adjustment'],
                'chunks_sha256':history['chunks_sha256'],'financial_accepted':False,'sessions_available':len(rows),'market_start':rows[0]['session'],
                'market_end':rows[-1]['session'],'tiers':{'validation_start':VALIDATION_START,'vault_start':VAULT_START,'cutoff':CUTOFF}}
    label=f"history french/{history['feed']} {history['symbol']}, {rows[0]['session']} to {rows[-1]['session']}, {len(rows)} sessions, development only"
    return {'train_csv':market_csv(train),'validation_csv':market_csv(validation),'validation_rows':validation,'label':label,'provenance':provenance,
            'vault_sessions':len(vault),'vault':VAULT},vault
