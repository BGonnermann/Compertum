"""Private live observation diagnostic; never an order grant or risk approval."""
from dataclasses import dataclass
from datetime import datetime,timedelta,timezone
import hashlib,json,math,sqlite3
from zoneinfo import ZoneInfo
from compertum.data.calendar import session_times
from compertum.data.errors import DataError
from compertum.data.encoding import canonical
from compertum.domain import ContractError
from compertum.persistence import StateStore
from compertum.storage import JournalReserve
from compertum.paper_contracts import identifier
from compertum.fake_attempt_guard import require_attempt_guard
from compertum.attempt_records import is_paper,is_native,is_fake
from .errors import RuntimeRefused
from .owners import _MUTEX,_owner_scope,require_live_owner
from .execution_health import MutualHealth
from .paper_credential_slot import load_paper_slot
from .paper_credentials import open_paper_credentials
from .paper_read_packet import _ReadPacket,_local_time
from .paper_read_secrecy import qualify_read_reply,_reject_reflections
from ._winhttp_get import _OwnedGet,_HTTPResult

_FACTORY=object()
_MISSING=('ACCOUNT_CONFIRMATION_UNVERIFIED','OWNERSHIP_UNVERIFIED','ECONOMIC_RECONCILIATION_UNVERIFIED',
 'SUPERVISION_UNVERIFIED','QUOTE_EVIDENCE_UNVERIFIED','FEED_ENTITLEMENT_UNVERIFIED','ELIGIBILITY_UNVERIFIED',
 'LIQUIDITY_UNVERIFIED','ACTION_EVIDENCE_UNVERIFIED','FEE_EVIDENCE_UNVERIFIED','EXACT_PLAN_GRANT_REQUIRED')


def _need(value,reason='PAPER_PREFLIGHT_CONTEXT_CHANGED'):
    if not value:raise RuntimeRefused(reason)


def _sha(raw):return hashlib.sha256(raw).hexdigest()


def _measure():
    from . import paper_read_owner
    utc,mono=paper_read_owner.time.time(),paper_read_owner.time.monotonic()
    _need(all(type(v) in (int,float) and math.isfinite(v) and v>=0 for v in (utc,mono)))
    return datetime.fromtimestamp(utc,timezone.utc),mono


def _live(owner):
    from .paper_read_owner import PaperReadOwner
    _need(type(owner) is PaperReadOwner and not owner._closed,'PAPER_PREFLIGHT_UNAVAILABLE')
    _need(type(owner.store) is StateStore and owner.store.lease is owner.lease)
    _need(type(owner.reserve) is JournalReserve and owner.reserve.lease is owner.lease,'JOURNAL_UNRESERVED')
    _need(type(owner.health) is MutualHealth and owner.health.lease is owner.lease)
    require_live_owner(owner.lease,'execution');owner._ready()


def native_read_provenance(transport,result,lease,request):
    """Called by the owner with its completed native handle, never an RPC flag."""
    p=request.to_payload();origin='UNVERIFIED_TRANSPORT'
    if (type(transport) is _OwnedGet and type(result) is _HTTPResult and transport._lease is lease
        and transport._result is result and transport.native_closed and transport._method=='GET'
        and transport._wire_path==p['target'] and result.status_code==200):
        if transport._origin==('paper-api.alpaca.markets',443,True):origin='PAPER_TLS'
        elif transport._origin[0]=='127.0.0.1' and transport._origin[2] is False:origin='LOOPBACK_FIXTURE'
    from .fixture_source_binding import finish_if_present
    finish_if_present(transport,result,lease,request)
    return dict(request_sha256=request.sha256,raw_sha256=_sha(result.body),origin=origin)


def _history(store):
    if store.conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='fake_intents'").fetchone() is None:
        return dict(status='UNAVAILABLE',paper_preparations=None,fake_attempts=None)
    try:
        count=store.conn.execute('SELECT count(*),coalesce(max(length(CAST(body AS BLOB))),0),coalesce(max(length(CAST(decision AS BLOB))),0) FROM fake_intents').fetchone()
        _need(count[0]<=256 and max(count[1:])<=65536,'EXECUTION_COMPROMISED')
        evidence=require_attempt_guard(store)
        paper=sum(is_paper(r['intent']) for r in evidence['records'])
        native=sum(is_native(r['intent']) for r in evidence['records'])
        result=dict(status='PRESERVED_PREPARATION_AND_FAKE_HISTORY',paper_preparations=paper,
                    fake_attempts=sum(is_fake(r['intent']) for r in evidence['records']))
        if native:result.update(status='PRESERVED_DISJOINT_EXECUTION_HISTORY',native_attempts=native)
        return result
    except (RuntimeRefused,sqlite3.Error):return dict(status='COMPROMISED',paper_preparations=None,fake_attempts=None)


def _calendar(records,day):
    by_operation={}
    for r in records:by_operation.setdefault(r['operation'],[]).append(r)
    rows=by_operation['CALENDAR'][0]['observation'];clocks=by_operation.get('CLOCK',[])
    reasons=[]
    if not clocks:reasons.append('CLOCK_MISSING')
    try:
        times=session_times(day);successor=session_times(times.next_date)
    except DataError:
        times=None;successor=None
        # Closed days do not excuse unchecked source clocks. Bound the search;
        # an unavailable pinned calendar must still refuse clock agreement.
        for offset in range(1,15):
            try:successor=session_times((datetime.fromisoformat(day)+timedelta(days=offset)).date().isoformat());break
            except DataError:continue
        reasons.extend(('NO_PINNED_CALENDAR_SESSION','MARKET_NOT_OPEN'))
    ny=ZoneInfo('America/New_York')
    expected=[] if times is None else [dict(date=day,open=times.open.astimezone(ny).strftime('%H:%M'),close=times.close.astimezone(ny).strftime('%H:%M'))]
    agreement='NO_PINNED_SESSION' if times is None else 'MATCHES_PINNED_CALENDAR' if rows==expected else 'DISAGREES'
    if rows!=expected:reasons.append('CALENDAR_DISAGREEMENT')
    for r in clocks:
        c=r['observation'];at=_local_time(c['timestamp']);received=_local_time(r['received_at'])
        if not 0<=(received-at).total_seconds()<=5:reasons.append('CLOCK_DISAGREEMENT')
        if at.astimezone(ny).date().isoformat()!=day:reasons.append('CLOCK_SESSION_DISAGREEMENT')
        if c['is_open']!=(times is not None and times.open<=at<times.close):reasons.append('CLOCK_SESSION_DISAGREEMENT')
        if not c['is_open']:reasons.append('MARKET_NOT_OPEN')
        if successor is None:
            reasons.append('CLOCK_CALENDAR_UNAVAILABLE');continue
        if times is None:
            if _local_time(c['next_open'])!=successor.open:reasons.append('CLOCK_OPEN_DISAGREEMENT')
            if _local_time(c['next_close'])!=successor.close:reasons.append('CLOCK_CLOSE_DISAGREEMENT')
            continue
        next_open=times.open if at<times.open else successor.open
        next_close=times.close if at<times.close else successor.close
        if _local_time(c['next_open'])!=next_open:reasons.append('CLOCK_OPEN_DISAGREEMENT')
        if _local_time(c['next_close'])!=next_close:reasons.append('CLOCK_CLOSE_DISAGREEMENT')
    return agreement,reasons


@dataclass(frozen=True,slots=True,repr=False,init=False)
class _PaperPreflight:
    content:bytes
    _owner:object
    _account_id:str
    _credential_sha:str
    _generation:int
    _instance:str
    _content_sha:str
    _private_sha:str
    _records:tuple
    _captured_utc:object
    _captured_mono:float
    _closed:bool

    def __init__(self,*,_factory=None,**fields):
        _need(_factory is _FACTORY,'PAPER_PREFLIGHT_UNQUALIFIED')
        for key,value in fields.items():object.__setattr__(self,key,value)
    def __repr__(self):return '<PrivatePaperPreflight redacted>'
    def __reduce_ex__(self,protocol):raise RuntimeRefused('PAPER_PREFLIGHT_PRIVATE_SERIALIZATION_FORBIDDEN')

    def close(self):
        with _MUTEX:
            object.__setattr__(self,'_closed',True);object.__setattr__(self,'_account_id',None)
            object.__setattr__(self,'_records',());object.__setattr__(self,'_owner',None)

    def diagnostic(self):
        owner=self._owner;_need(not self._closed and owner is not None,'PAPER_PREFLIGHT_UNAVAILABLE')
        with _owner_scope(owner.lease),owner.store._live():
            _need(not self._closed and self._owner is owner,'PAPER_PREFLIGHT_UNAVAILABLE')
            _live(owner);_need(owner._preflight is self)
            _need(self._generation==owner.lease.generation and self._instance==owner.lease.identity.process_instance_id)
            _need(type(self.content) is bytes and _sha(self.content)==self._content_sha)
            p=json.loads(self.content)
            _need(self._private_sha==_sha(canonical(dict(account=self._account_id,content=self._content_sha,credentials=self._credential_sha,instance=self._instance,generation=self._generation))))
            value=owner._read(p['packet_id'])
            _need(value['state'] in {'EVIDENCE_READY','PUBLISHED'} and value['evidence'] is not None and value['evidence']['sha256']==p['encrypted_evidence_sha256'])
            protected=load_paper_slot(owner.lease,p['account_alias']);_need(_sha(protected.ciphertext)==self._credential_sha)
            now,mono=_measure();du=(now-self._captured_utc).total_seconds();dm=mono-self._captured_mono
            _need(0<=du<=30 and 0<=dm<=30,'PAPER_PREFLIGHT_STALE')
            _need(abs(du-dm)<=5,'PAPER_PREFLIGHT_CLOCK_CHANGED')
            _need(len(self._records)==len(p['references']))
            for (raw_request,raw_record),reference in zip(self._records,p['references']):
                _need(_sha(raw_request)==reference['request_sha256'] and _sha(raw_record)==reference['parsed_sha256'])
                request=json.loads(raw_request);record=json.loads(raw_record)
                _need(0<=(now-_local_time(request['created_at'])).total_seconds()<=30 and _local_time(record['received_at'])<=now,'PAPER_PREFLIGHT_STALE')
            reasons=list(p['deficiencies']);history=_history(owner.store)
            if history['status']=='COMPROMISED':reasons.append('LOCAL_HISTORY_COMPROMISED')
            p.update(checked_at=now.isoformat(),local_history=history,deficiencies=sorted(set(reasons)))
            raw=canonical(p);_need(len(raw)<=16384)
            with open_paper_credentials(owner.lease,protected) as opened:_reject_reflections(raw,tuple(opened.headers().values()))
            _need(self._account_id.encode() not in raw,'PAPER_READ_PRIVATE_ID_REFLECTION')
            return p


def capture_preflight(owner,value):
    """Internal completion hook. No historical evidence or supplied risk flags."""
    _live(owner)
    with _owner_scope(owner.lease),owner.store._live():
        packet=owner._packet
        _need(type(packet) is _ReadPacket and packet._lease is owner.lease and not packet._closed)
        _need(type(value) is dict and value.get('packet_id')==owner._active)
        status=packet.status();_need(status['state']=='PREPARATION_COMPLETE','PAPER_PREFLIGHT_INCOMPLETE')
        saved=owner._read(value['packet_id'])
        _need(saved['state']=='RUNNING' and saved['consumed'] and saved['owner_generation']==owner.lease.generation and saved['owner_instance']==owner.lease.identity.process_instance_id)
        _need(all(saved[k]==value[k] for k in ('packet_id','account_alias','plan_sha256','credential_sha256','project_id')))
        _need(value['evidence'] is not None and owner._cipher is not None and _sha(owner._cipher.ciphertext)==value['evidence']['sha256'])
        protected=load_paper_slot(owner.lease,value['account_alias']);credential=_sha(protected.ciphertext)
        _need(credential==value['credential_sha256']==packet._credential_sha)
        records=packet.private_evidence();_need(6<=len(records)<=13 and len(owner._read_provenance)==len(records))
        parsed=[];retained=[];references=[];origins=[]
        for record,proof in zip(records,owner._read_provenance):
            r=record.to_payload();verified=qualify_read_reply(owner.lease,protected,record.request,record.raw,received_at=r['received_at'])
            _need(verified.content==record.content and verified.private_account_id==packet._account_id)
            _need(proof['request_sha256']==record.request.sha256 and proof['raw_sha256']==r['raw_sha256'])
            _need(proof['origin'] in {'PAPER_TLS','LOOPBACK_FIXTURE','UNVERIFIED_TRANSPORT'})
            parsed.append(r);retained.append((record.request.content,record.content));origins.append(proof['origin'])
            references.append(dict(request_sha256=record.request.sha256,parsed_sha256=_sha(record.content),raw_sha256=r['raw_sha256'],received_at=r['received_at']))
        _need(sum(len(a)+len(b) for a,b in retained)<=1024**2)
        identifier(packet._account_id);now,mono=_measure()
        agreement,reasons=_calendar(parsed,packet._plan.to_payload()['session_date'])
        if status['deficiencies']:reasons.append('READ_PACKET_DEFICIENCIES_PRESENT')
        reasons.extend(_MISSING)
        origin=origins[0] if len(set(origins))==1 else 'MIXED_UNVERIFIED'
        if origin!='PAPER_TLS':reasons.append('NATIVE_PAPER_TRANSPORT_UNVERIFIED')
        if status['positions']:reasons.append('POSITION_OWNERSHIP_UNVERIFIED')
        if status['orders']:reasons.append('ORDER_OWNERSHIP_UNVERIFIED')
        payload=dict(version=1,record_type='PaperPreflightDiagnostic',scope='PREPARATION_ONLY',project_id=owner.lease.project_id,
            account_alias=value['account_alias'],packet_id=value['packet_id'],plan_sha256=value['plan_sha256'],encrypted_evidence_sha256=value['evidence']['sha256'],
            created_at=now.isoformat(),generation=owner.lease.generation,owner_instance=owner.lease.identity.process_instance_id,
            credential_sha256=credential,transport_provenance=origin,calendar_agreement=agreement,response_count=len(records),
            positions=status['positions'],orders=status['orders'],order_coverage=status['orders_coverage'],references=references,
            packet_deficiency_count=len(status['deficiencies']),packet_deficiencies_sha256=_sha(canonical(status['deficiencies'])),
            preflight_status='BLOCKED',deficiencies=sorted(set(reasons)),transport_authorized=False,financial_accepted=False,actual_flat=None)
        content=canonical(payload);_need(len(content)<=16384)
        with open_paper_credentials(owner.lease,protected) as opened:_reject_reflections(content,tuple(opened.headers().values()))
        _need(packet._account_id.encode() not in content,'PAPER_READ_PRIVATE_ID_REFLECTION')
        digest=_sha(content);private=_sha(canonical(dict(account=packet._account_id,content=digest,credentials=credential,instance=owner.lease.identity.process_instance_id,generation=owner.lease.generation)))
        return _PaperPreflight(_factory=_FACTORY,content=content,_owner=owner,_account_id=packet._account_id,_credential_sha=credential,
            _generation=owner.lease.generation,_instance=owner.lease.identity.process_instance_id,_content_sha=digest,_private_sha=private,
            _records=tuple(retained),_captured_utc=now,_captured_mono=mono,_closed=False)
