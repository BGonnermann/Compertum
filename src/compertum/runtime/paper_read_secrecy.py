"""Execution-owned response privacy gate. No request, file write or authority."""
from dataclasses import dataclass
import base64
import hashlib
import json
from zoneinfo import ZoneInfo
from compertum.data.encoding import canonical
from compertum.domain import ContractError
from compertum.paper_contracts import strict_json,identifier,timestamp,utc
from compertum.paper_read_preparation import PreparedReadRequest
from compertum.paper_responses import _account,_clock,_calendar
from .errors import RuntimeRefused
from .owners import _owner_scope,require_live_owner
from .paper_credentials import ProtectedPaperCredentials,open_paper_credentials


_PARSED_READ_FACTORY=object()


@dataclass(frozen=True,slots=True,repr=False,init=False)
class _PrivateParsedRead:
    content:bytes
    raw:bytes
    private_account_id:str
    request:PreparedReadRequest
    def __init__(self,content,raw,private_account_id,*,request=None,_factory=None):
        if _factory is not _PARSED_READ_FACTORY:raise RuntimeRefused('PAPER_READ_UNQUALIFIED_RESULT')
        object.__setattr__(self,'content',content)
        object.__setattr__(self,'raw',raw)
        object.__setattr__(self,'private_account_id',private_account_id)
        object.__setattr__(self,'request',request)
    def to_payload(self):return json.loads(self.content)
    def __repr__(self):return '<ParsedPaperRead private data redacted>'
    def __reduce_ex__(self,protocol):raise RuntimeRefused('PAPER_READ_PRIVATE_SERIALIZATION_FORBIDDEN')


def _reject_reflections(raw,values):
    tokens=[]
    for value in values:
        tokens.extend((value,base64.b64encode(value.encode()).decode(),base64.urlsafe_b64encode(value.encode()).decode().rstrip('=')))
    tokens.extend(('APCA-API-KEY-ID','APCA-API-SECRET-KEY'))
    if any(token.encode() in raw for token in tokens):raise RuntimeRefused('PAPER_READ_SECRET_REFLECTION')
    parsed=strict_json(raw)
    pending=[parsed]
    while pending:
        item=pending.pop()
        if type(item) is str:
            if any(token in item for token in tokens):raise RuntimeRefused('PAPER_READ_SECRET_REFLECTION')
        elif type(item) is dict:
            pending.extend(item.keys());pending.extend(item.values())
        elif type(item) is list:pending.extend(item)
    return parsed


def _parse_read_reply(request,raw,received_at,body):
    """Shared bounded historical parser; does not grant transport or check secrets."""
    request.__post_init__();p=request.to_payload();plan=request.plan.to_payload()
    if type(raw) is not bytes or not 0<len(raw)<=65536:raise ContractError('INVALID_READ')
    received=timestamp(received_at);dispatched=timestamp(p['created_at']);started=timestamp(p['packet_started_at'])
    if received.astimezone(ZoneInfo('America/New_York')).date().isoformat()!=plan['session_date']:raise ContractError('INVALID_READ')
    if not 0<=(received-dispatched).total_seconds()<=p['timeout_ms']/1000 or not 0<=(received-started).total_seconds()<30:raise ContractError('INVALID_READ')
    account_id=request.expected_account_id;operation=p['operation']
    if operation=='ACCOUNT':
        if type(body) is not dict:raise ContractError('INVALID_READ')
        actual=identifier(body.get('id'))
        if account_id is not None and actual!=account_id:raise ContractError('INVALID_READ')
        account_id=actual;observation=_account(body,{'account_id':actual});observation.pop('id')
    elif operation=='CLOCK':observation=_clock(body)
    elif operation=='CALENDAR':observation=_calendar(body,p)
    else:
        from compertum.paper_portfolio import parse_portfolio_rows
        observation=parse_portfolio_rows(body,p)
    content=canonical(dict(version=1,record_type='ParsedPaperRead',scope='PREPARATION_ONLY',
        request_sha256=request.sha256,request_id=p['request_id'],account_alias=p['account_alias'],operation=operation,
        account_identity='DISCOVERED_UNCONFIRMED' if request.expected_account_id is None else 'ID_MATCHES_PRIVATE_REQUEST_CONTEXT',
        native_transport_verified=False,financial_accepted=False,actual_flat=None,ownership='UNVERIFIED',
        received_at=utc(received_at),raw_bytes=len(raw),raw_sha256=hashlib.sha256(raw).hexdigest(),observation=observation))
    if account_id.encode() in content:raise RuntimeRefused('PAPER_READ_PRIVATE_ID_REFLECTION')
    if len(content)>65536:raise ContractError('INVALID_READ')
    return _PrivateParsedRead(content,raw,account_id,request=request,_factory=_PARSED_READ_FACTORY)


def qualify_read_reply(lease,protected,request,raw,*,received_at):
    with _owner_scope(lease) as state:
        require_live_owner(lease,'execution')
        if type(protected) is not ProtectedPaperCredentials or type(request) is not PreparedReadRequest:raise RuntimeRefused('PAPER_READ_CONTEXT_MISMATCH')
        try:
            request.__post_init__();plan=request.plan.to_payload()
            if (plan['project_id']!=state.project.project_id or protected.project_id!=state.project.project_id
                    or protected.account_alias!=plan['account_alias']
                    or request.credential_sha256!=hashlib.sha256(protected.ciphertext).hexdigest()):raise RuntimeRefused('PAPER_READ_CONTEXT_MISMATCH')
            if type(raw) is not bytes or not 0<len(raw)<=65536:raise ContractError('INVALID_READ')
            with open_paper_credentials(lease,protected) as opened:
                values=tuple(opened.headers().values());body=_reject_reflections(raw,values)
                parsed=_parse_read_reply(request,raw,received_at,body)
                _reject_reflections(parsed.content,values)
                return parsed
        except (ContractError,ValueError,TypeError,KeyError,UnicodeError,RecursionError):raise RuntimeRefused('PAPER_READ_RESPONSE_INVALID') from None
