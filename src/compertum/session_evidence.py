"""Bounded immutable session inventory checks; payload semantics stay unverified.

No producer authenticity, supervision, reconciliation or recovery qualification is
inferred from a caller label or hash. This module cannot accept an actual day.
"""
import hashlib
from importlib.metadata import version
import re
from zoneinfo import ZoneInfo
from .data.calendar import session_times,utc_time
from .data.errors import DataError
from .data.encoding import canonical
from .domain import ContractError
from .paper_contracts import strict_json,identifier

MAX_ARTIFACTS=128
MAX_BYTES=65536
KINDS=frozenset({'INPUTS','SUPERVISION','ORDERS','LEDGER','INCIDENTS','CLOSING','RECOVERY','AI_OFF'})
OPTIONAL=frozenset({'RECOVERY','AI_OFF'})
PROVENANCE=frozenset({'ACTUAL_PAPER_CLAIM','PAPER_PREPARATION','DETERMINISTIC_FAKE','PAPER_WIRE_FIXTURE','ACCELERATED_CLOCK','BACKTEST','HISTORICAL_REPLAY'})
_IDENTITY=('project_id','session_id','account_alias')
_UNVERIFIED=('NATIVE_PRODUCER_AUTHENTICITY_UNVERIFIED','NATIVE_SESSION_SEMANTICS_UNVERIFIED',
 'MINIMUM_OPERATING_INTERVAL_UNSPECIFIED','EXERCISE_WINDOW_POLICY_UNSPECIFIED','ACTUAL_M5_ACCEPTANCE_UNVERIFIED')


def _need(condition,code='SESSION_EVIDENCE_INVALID'):
    if not condition:raise ContractError(code)


def _hash(raw):return hashlib.sha256(raw).hexdigest()


def _sha(value):
    _need(type(value) is str and re.fullmatch('[0-9a-f]{64}',value) is not None)


def _object(raw):
    value=strict_json(raw)
    _need(type(value) is dict and canonical(value)==raw)
    return value


def _reference(value):
    _need(type(value) is dict and set(value)=={'artifact_id','sha256','size_bytes'})
    identifier(value['artifact_id']);_sha(value['sha256'])
    _need(type(value['size_bytes']) is int and 0<value['size_bytes']<=MAX_BYTES)
    return value


def _time(value):
    try:
        parsed=utc_time(value)
        _need(2000<=parsed.year<=2100,'SESSION_TIME_INVALID')
        return parsed
    except DataError:raise ContractError('SESSION_TIME_INVALID') from None


def _manifest(raw,as_of):
    m=_object(raw)
    keys={'version','record_type','scope','provenance','project_id','account_alias','private_context_sha256','session_id','session_date','calendar','started_at','ended_at','code_sha256','lock_sha256','config_sha256','previous_session','roots'}
    _need(set(m)==keys and type(m['version']) is int and m['version']==1)
    _need(m['record_type']=='SessionEvidenceManifest' and m['scope']=='OFFLINE_SESSION_EVIDENCE')
    _need(type(m['provenance']) is str and m['provenance'] in PROVENANCE)
    for key in ('project_id','private_context_sha256','code_sha256','lock_sha256','config_sha256'):_sha(m[key])
    identifier(m['session_id'])
    _need(type(m['account_alias']) is str and re.fullmatch('[a-zA-Z0-9_-]{1,64}',m['account_alias']) is not None)
    _need(m['calendar']==dict(name='XNYS',package='exchange_calendars',version=version('exchange-calendars')),'SESSION_CALENDAR_UNVERIFIED')
    try:times=session_times(m['session_date'])
    except DataError:raise ContractError('SESSION_CALENDAR_INVALID') from None
    started,ended,now=(_time(v) for v in (m['started_at'],m['ended_at'],as_of))
    ny=ZoneInfo('America/New_York')
    _need(started<ended<=now and times.close<=now and started<times.close and ended>=times.open,'SESSION_NOT_COMPLETED')
    _need(started.astimezone(ny).date().isoformat()==m['session_date']==ended.astimezone(ny).date().isoformat(),'SESSION_INTERVAL_INVALID')
    if m['previous_session'] is not None:
        _reference(m['previous_session']);_need(m['previous_session']['artifact_id']!=m['session_id'])
    _need(type(m['roots']) is dict and set(m['roots'])==KINDS)
    return m,times


def _session(content,artifacts,as_of):
    m,times=_manifest(content,as_of)
    _need(type(artifacts) is tuple and 1<=len(artifacts)<=MAX_ARTIFACTS)
    _need(all(type(raw) is bytes and 0<len(raw)<=MAX_BYTES for raw in artifacts))
    # Immutable bytes are bounded before parsing; no paths or external reads.
    rows={}
    for raw in artifacts:
        a=_object(raw)
        _need(set(a)=={'version','record_type','artifact_id','session_id','project_id','account_alias','kind','page','records','references'})
        _need(type(a['version']) is int and a['version']==1 and a['record_type']=='SessionEvidenceArtifact')
        aid=identifier(a['artifact_id']);_need(aid not in rows and aid!=m['session_id'])
        _need(all(a[k]==m[k] for k in _IDENTITY),'SESSION_ARTIFACT_IDENTITY')
        _need(type(a['kind']) is str and a['kind'] in KINDS and type(a['page']) is int and 1<=a['page']<=MAX_ARTIFACTS)
        _need(type(a['records']) is list and len(a['records'])<=512 and all(type(r) is dict for r in a['records']))
        _need(type(a['references']) is list and len(a['references'])<=MAX_ARTIFACTS)
        for ref in a['references']:_reference(ref)
        _need(len({r['artifact_id'] for r in a['references']})==len(a['references']))
        rows[aid]=(a,raw)
    if m['previous_session'] is not None:_need(m['previous_session']['artifact_id'] not in rows,'SESSION_PREDECESSOR_COLLISION')
    seen=set();streams={};missing=[]
    def visit(ref,kind,pages,depth):
        _reference(ref);_need(depth<=16,'SESSION_GRAPH_DEPTH')
        aid=ref['artifact_id'];_need(aid in rows and aid not in seen,'SESSION_ARTIFACT_CLOSURE')
        a,raw=rows[aid]
        _need(len(raw)==ref['size_bytes'] and _hash(raw)==ref['sha256'],'SESSION_ARTIFACT_DIGEST')
        _need(a['kind']==kind,'SESSION_ARTIFACT_KIND')
        seen.add(aid);pages.append(a)
        for child in a['references']:visit(child,kind,pages,depth+1)
    for kind in sorted(KINDS):
        root=m['roots'][kind]
        if root is None:
            _need(kind in OPTIONAL);missing.append(kind+'_EVIDENCE_ABSENT');continue
        _need(type(root) is dict and set(root)=={'reference','page_count','record_count'})
        _need(type(root['page_count']) is int and 1<=root['page_count']<=MAX_ARTIFACTS)
        _need(type(root['record_count']) is int and 0<=root['record_count']<=MAX_ARTIFACTS*512)
        pages=[];visit(root['reference'],kind,pages,1)
        _need(pages[0]['page']==1 and [p['page'] for p in pages]==list(range(1,len(pages)+1)),'SESSION_PAGE_SEQUENCE')
        count=sum(len(p['records']) for p in pages)
        _need(root['page_count']==len(pages) and root['record_count']==count,'SESSION_DECLARED_COUNT')
        _need(len(pages)==1 or all(p['records'] for p in pages),'SESSION_EMPTY_PAGE')
        streams[kind]=dict(page_count=len(pages),record_count=count)
    _need(seen==set(rows),'SESSION_UNREFERENCED_ARTIFACT')
    report=dict(record_type='SessionEvidenceDiagnostic',structural_status='VERIFIED_PASS',qualification_status='UNVERIFIED',
        semantic_status='UNVERIFIED',actual_sessions_verified=0,financial_accepted=False,milestone_accepted=False,transport_authorized=False,
        as_of=_time(as_of).isoformat(),session_id=m['session_id'],session_date=m['session_date'],manifest_sha256=_hash(content),provenance=m['provenance'],
        exchange_open=times.open.isoformat(),exchange_close=times.close.isoformat(),artifact_count=len(rows),artifact_bytes=sum(len(r) for r in artifacts),
        streams=streams,unverified_reasons=list(_UNVERIFIED)+missing)
    return m,report,frozenset(rows)


def check_session(content,artifacts,*,as_of):
    """Check inventory and calendar only; payload meaning and actual time unverified."""
    return _session(content,artifacts,as_of)[1]


def check_window(packets,*,as_of):
    """Exactly ten consecutive completed calendar dates, never ten accepted days."""
    _need(type(packets) is tuple and len(packets)==10,'SESSION_WINDOW_COUNT')
    previous=None;first=None;ids=set();reports=[]
    for packet in packets:
        _need(type(packet) is tuple and len(packet)==2)
        m,report,artifact_ids=_session(packet[0],packet[1],as_of)
        current=artifact_ids|{m['session_id']}
        _need(not current&ids,'SESSION_WINDOW_IDENTITY_COLLISION');ids.update(current)
        if first is None:first=m
        else:
            _need(all(m[k]==first[k] for k in ('project_id','account_alias','private_context_sha256','calendar')),'SESSION_WINDOW_IDENTITY')
            pm,praw=previous
            _need(session_times(pm['session_date']).next_date==m['session_date'],'SESSION_WINDOW_GAP')
            _need(m['previous_session']==dict(artifact_id=pm['session_id'],sha256=_hash(praw),size_bytes=len(praw)),'SESSION_PREDECESSOR_MISMATCH')
            _need(_time(pm['ended_at'])<_time(m['started_at']),'SESSION_INTERVAL_OVERLAP')
        previous=(m,packet[0]);reports.append(report)
    if first['previous_session'] is not None:
        _need(first['previous_session']['artifact_id'] not in ids,'SESSION_PREDECESSOR_COLLISION')
    return dict(as_of=_time(as_of).isoformat(),record_type='SessionWindowDiagnostic',structural_status='VERIFIED_PASS',structurally_valid_sessions=10,
        actual_sessions_verified=0,qualification_status='UNVERIFIED',semantic_status='UNVERIFIED',milestone_accepted=False,
        financial_accepted=False,transport_authorized=False,prospective_strategy_sessions_verified=0,
        session_dates=[r['session_date'] for r in reports],manifests_sha256=[r['manifest_sha256'] for r in reports],
        unverified_reasons=sorted(set(reason for r in reports for reason in r['unverified_reasons'])))
