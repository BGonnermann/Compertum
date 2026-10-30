"""Engine history markets: years of one symbol's split-adjusted daily closes from retained Alpaca evidence, development only.

A history manifest (schemas/engine_market_history.v1.json) names one symbol, the feed, the adjustment and the evidence chunks. Each chunk
is an alpaca-bars-v1 envelope that tools/pull_bars.py retained. The loader rechecks every chunk byte for byte, keeps that symbol's daily
bars of the named adjustment, and refuses a gap in the exchange calendar between the first and the last bar. The evidence reader keeps
every date before 2024, the vault period. The market is at most the last MAX_SESSIONS sessions.
"""
from decimal import Decimal
import hashlib
import json
from pathlib import Path
from compertum.data.alpaca import read_bar_evidence
from compertum.data.calendar import NY,session_times,utc_time
from compertum.data.errors import DataError
from compertum.data.provider_snapshot import MAX_CHUNKS,MAX_TOTAL
from compertum.data.snapshot_text import MAX_INPUT
from compertum.domain import ContractError,validate_record
from compertum.runtime.errors import RuntimeRefused
from .market import MAX_SESSIONS,market_csv,split_market_tiers

MIN_HISTORY_SESSIONS=50
from .real_market import MANIFEST_BYTES,_json,_read


def load_history_manifest(project_root,manifest_path):
    root=Path(project_root).absolute()
    value=_json(_read(root,manifest_path,MANIFEST_BYTES),'ENGINE_MARKET_MANIFEST_INVALID')
    try: return validate_record('engine_market_history.v1',value,project_root=root)
    except ContractError as error: raise RuntimeRefused(error.reason) from None


def load_history(project_root,manifest_path):
    root=Path(project_root).absolute();manifest=load_history_manifest(root,manifest_path);symbol=manifest['symbol']
    if len(manifest['chunks'])>MAX_CHUNKS: raise RuntimeRefused('ENGINE_MARKET_INPUT_BOUND')
    closes={};hashes=[];total=0
    for item in manifest['chunks']:
        raw=_read(root,item['path'],MAX_INPUT);total+=len(raw)
        if total>MAX_TOTAL: raise RuntimeRefused('ENGINE_MARKET_INPUT_BOUND')
        if hashlib.sha256(raw).hexdigest()!=item['sha256']: raise RuntimeRefused('ENGINE_MARKET_EVIDENCE_CHANGED')
        try: chunk=read_bar_evidence(raw,universe=None)
        except DataError as error: raise RuntimeRefused(error.code) from None
        if chunk.feed!=manifest['feed']: raise RuntimeRefused('ENGINE_MARKET_MANIFEST_INVALID')
        for request in json.loads(raw)['requests']:
            params=request['params']
            if params['symbols']!=symbol or params['timeframe']!='1Day' or params['adjustment']!=manifest['adjustment']:
                raise RuntimeRefused('ENGINE_MARKET_MANIFEST_INVALID')
        hashes.append(chunk.sha256)
        for bar in chunk.rows:
            day=utc_time(bar.timestamp).astimezone(NY).date().isoformat()
            if day in closes: raise RuntimeRefused('ENGINE_MARKET_MANIFEST_INVALID')
            closes[day]=bar.close
    if len(closes)<MIN_HISTORY_SESSIONS+1: raise RuntimeRefused('ENGINE_MARKET_COVERAGE_INCOMPLETE')
    days=sorted(closes);expected=days[0]
    for day in days:
        if day!=expected: raise RuntimeRefused('ENGINE_MARKET_COVERAGE_INCOMPLETE')
        try: expected=session_times(day).next_date
        except DataError as error: raise RuntimeRefused(error.code) from None
    return {'symbol':symbol,'feed':manifest['feed'],'adjustment':manifest['adjustment'],'chunks_sha256':hashes,'closes':[(day,closes[day]) for day in days]}


def history_market(history,sessions=None):
    closes=history['closes'];available=min(len(closes)-1,MAX_SESSIONS)
    if sessions is None: sessions=available
    if type(sessions) is not int or sessions<MIN_HISTORY_SESSIONS: raise RuntimeRefused('ENGINE_MARKET_DENIED')
    if sessions>available: raise RuntimeRefused('ENGINE_MARKET_COVERAGE_INCOMPLETE')
    closes=closes[-(sessions+1):];rows=[]
    for (_,before),(day,close) in zip(closes,closes[1:]):
        before=Decimal(before);close=Decimal(close)
        if before<=0 or close<=0: raise RuntimeRefused('ENGINE_MARKET_DENIED')
        rows.append({'session':day,'close':format(close,'f'),'return':format(close/before-Decimal(1),'f')})
    train,validation,vault=split_market_tiers(rows)
    provenance={'provider':'alpaca','feed':history['feed'],'symbol':history['symbol'],'adjustment':history['adjustment'],'chunks_sha256':history['chunks_sha256'],
                'financial_accepted':False,'sessions_available':available,'market_start':rows[0]['session'],'market_end':rows[-1]['session']}
    label=f"history alpaca/{history['feed']} {history['symbol']}, {rows[0]['session']} to {rows[-1]['session']}, {sessions} sessions, development only"
    return {'train_csv':market_csv(train),'validation_csv':market_csv(validation),'validation_rows':validation,'label':label,'provenance':provenance,'vault_sessions':len(vault)},vault


def load_history_market(project_root,manifest_path,*,sessions=None):
    return history_market(load_history(project_root,manifest_path),sessions)
