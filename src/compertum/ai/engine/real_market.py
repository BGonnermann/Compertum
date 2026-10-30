"""Verified Alpaca provider evidence as development-only engine markets."""
from decimal import Decimal
import hashlib
import json
from pathlib import Path
from compertum.data.alpaca import SYMBOLS,read_bar_evidence
from compertum.data.errors import DataError
from compertum.data.provider_snapshot import MAX_CHUNKS,MAX_TOTAL,ProviderSnapshot,build_provider_snapshot,verify_provider_snapshot
from compertum.data.snapshot_text import MAX_INPUT
from compertum.domain import ContractError,resolve_project_path,validate_record
from compertum.runtime.errors import RuntimeRefused
from .market import MAX_SESSIONS,MIN_SESSIONS,market_csv,split_market_tiers

MANIFEST_BYTES=65536


def _read(root,relative,limit):
    try: path=resolve_project_path(relative,Path(root).absolute())
    except ContractError as error: raise RuntimeRefused(error.reason) from None
    try:
        with path.open('rb') as stream: raw=stream.read(limit+1)
    except OSError: raise RuntimeRefused('ENGINE_MARKET_INPUT_UNAVAILABLE') from None
    if not raw or len(raw)>limit: raise RuntimeRefused('ENGINE_MARKET_INPUT_BOUND')
    return raw


def _pairs(items):
    out={}
    for key,value in items:
        if key in out: raise RuntimeRefused('ENGINE_MARKET_MANIFEST_INVALID')
        out[key]=value
    return out


def _json(raw,code):
    try: return json.loads(raw.decode('utf-8'),object_pairs_hook=_pairs,parse_constant=lambda _:(_ for _ in ()).throw(RuntimeRefused(code)))
    except RuntimeRefused: raise
    except (UnicodeError,ValueError,RecursionError): raise RuntimeRefused(code) from None


def load_manifest(project_root,manifest_path):
    root=Path(project_root).absolute()
    raw=_read(root,manifest_path,MANIFEST_BYTES);value=_json(raw,'ENGINE_MARKET_MANIFEST_INVALID')
    try: return validate_record('engine_market_manifest.v1',value,project_root=root)
    except ContractError as error: raise RuntimeRefused(error.reason) from None


def load_snapshot(project_root,manifest_path):
    root=Path(project_root).absolute();manifest=load_manifest(root,manifest_path)
    snapshot_raw=_read(root,manifest['snapshot']['path'],MAX_TOTAL)
    if hashlib.sha256(snapshot_raw).hexdigest()!=manifest['snapshot']['sha256']: raise RuntimeRefused('ENGINE_MARKET_SNAPSHOT_CHANGED')
    saved=_json(snapshot_raw,'ENGINE_MARKET_SNAPSHOT_INVALID')
    chunks=[];total=0
    if len(manifest['evidence'])>MAX_CHUNKS: raise RuntimeRefused('ENGINE_MARKET_INPUT_BOUND')
    for item in manifest['evidence']:
        raw=_read(root,item['path'],MAX_INPUT);total+=len(raw)
        if total>MAX_TOTAL: raise RuntimeRefused('ENGINE_MARKET_INPUT_BOUND')
        if hashlib.sha256(raw).hexdigest()!=item['sha256']: raise RuntimeRefused('ENGINE_MARKET_EVIDENCE_CHANGED')
        try: chunks.append(read_bar_evidence(raw))
        except DataError as error: raise RuntimeRefused(error.code) from None
    try:
        snapshot=build_provider_snapshot(tuple(chunks),start=saved['start'],end=saved['end'],feed=saved['feed'])
    except (DataError,KeyError,TypeError) as error:
        if isinstance(error,DataError): raise RuntimeRefused(error.code) from None
        raise RuntimeRefused('ENGINE_MARKET_SNAPSHOT_INVALID') from None
    if saved!=json.loads(snapshot.content): raise RuntimeRefused('ENGINE_MARKET_SNAPSHOT_CHANGED')
    if snapshot.sha256!=manifest['snapshot']['sha256']: raise RuntimeRefused('ENGINE_MARKET_SNAPSHOT_CHANGED')
    if saved.get('coverage',{}).get('complete') is not True: raise RuntimeRefused('ENGINE_MARKET_COVERAGE_INCOMPLETE')
    return snapshot,manifest['symbol']


def provider_market(snapshot,symbol,*,sessions=500):
    if type(sessions) is not int or not MIN_SESSIONS<=sessions<=MAX_SESSIONS: raise RuntimeRefused('ENGINE_MARKET_DENIED')
    if not isinstance(symbol,str) or symbol not in SYMBOLS: raise RuntimeRefused('ENGINE_MARKET_DENIED')
    try: snapshot=verify_provider_snapshot(snapshot)
    except DataError as error: raise RuntimeRefused(error.code) from None
    value=json.loads(snapshot.content)
    if symbol not in value['symbols'] or value['coverage']['complete'] is not True: raise RuntimeRefused('ENGINE_MARKET_COVERAGE_INCOMPLETE')
    bars=sorted((r for r in value['rows'] if r['symbol']==symbol and r['reference']=='daily' and r['adjustment']=='split'),
                key=lambda r:r['session_date'])
    if len(bars)<sessions+1: raise RuntimeRefused('ENGINE_MARKET_COVERAGE_INCOMPLETE')
    bars=bars[-(sessions+1):];rows=[]
    for previous,current in zip(bars,bars[1:]):
        before=Decimal(previous['close']);close=Decimal(current['close'])
        if before<=0 or close<=0: raise RuntimeRefused('ENGINE_MARKET_DENIED')
        rows.append({'session':current['session_date'],'close':current['close'],'return':format(close/before-Decimal(1),'f')})
    train,validation,vault=split_market_tiers(rows)
    provenance={'provider':value['provider'],'feed':value['feed'],'symbol':symbol,'adjustment':'split','snapshot_sha256':snapshot.sha256,
                'availability_basis':value['availability_basis'],'financial_accepted':False,'pending':value['pending'],
                'snapshot_start':value['start'],'snapshot_end':value['end'],'market_start':rows[0]['session'],'market_end':rows[-1]['session']}
    label=f"provider {value['provider']}/{value['feed']} {symbol}, snapshot {snapshot.sha256}, {sessions} sessions, development only"
    return {'train_csv':market_csv(train),'validation_csv':market_csv(validation),'validation_rows':validation,'label':label,'provenance':provenance,'vault_sessions':len(vault)},vault


def load_market_manifest(project_root,manifest_path,*,sessions=None):
    """A history manifest (kind "history") gives every retained session up to MAX_SESSIONS unless sessions is given; a provider
    snapshot manifest keeps its 500-session default."""
    root=Path(project_root).absolute()
    value=_json(_read(root,manifest_path,MANIFEST_BYTES),'ENGINE_MARKET_MANIFEST_INVALID')
    if isinstance(value,dict) and value.get('kind')=='history':
        from .history_market import load_history_market
        return load_history_market(root,manifest_path,sessions=sessions)
    snapshot,symbol=load_snapshot(root,manifest_path)
    return provider_market(snapshot,symbol,sessions=500 if sessions is None else sessions)
