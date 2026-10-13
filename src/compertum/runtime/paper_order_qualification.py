"""Execution-private order shapes and replies. No transport or write authority."""
from dataclasses import dataclass
import hashlib
import json
from compertum.data.encoding import canonical
from compertum.domain import ContractError
from compertum.paper_contracts import identifier,utc
from compertum.paper_responses import _order
from .errors import RuntimeRefused
from .owners import _owner_scope,require_live_owner
from .paper_credentials import ProtectedPaperCredentials,open_paper_credentials
from .paper_read_packet import _local_time
from .paper_read_secrecy import _reject_reflections
from ._winhttp_order import _wire

_FACTORY=object()


def _sha(value):return hashlib.sha256(value).hexdigest()


def _need(value,code='PAPER_ORDER_CONTEXT_MISMATCH'):
    if not value:raise RuntimeRefused(code)


def _private_id(raw,parsed,account_id):
    pending=[parsed]
    if account_id.encode() in raw:raise RuntimeRefused('PAPER_ORDER_PRIVATE_ID_REFLECTION')
    while pending:
        item=pending.pop()
        if type(item) is str:
            if account_id in item:raise RuntimeRefused('PAPER_ORDER_PRIVATE_ID_REFLECTION')
        elif type(item) is dict:pending.extend(item.keys());pending.extend(item.values())
        elif type(item) is list:pending.extend(item)


@dataclass(frozen=True,slots=True,repr=False,init=False)
class _PreparedOrderExchange:
    content:bytes
    private_account_id:str
    _lease:object
    _protected:ProtectedPaperCredentials
    _credential_sha256:str
    _request_sha256:str
    _owner_generation:int
    _owner_instance:str
    _private_binding:str

    def __init__(self,*,_factory=None,**fields):
        _need(_factory is _FACTORY,'PAPER_ORDER_UNQUALIFIED_REQUEST')
        for key,value in fields.items():object.__setattr__(self,key,value)

    def __repr__(self):return '<PreparedOrderExchange private context redacted>'
    def __reduce_ex__(self,protocol):raise RuntimeRefused('PAPER_ORDER_PRIVATE_SERIALIZATION_FORBIDDEN')
    def to_payload(self):return json.loads(self.content)
    @property
    def sha256(self):
        _need(type(self.content) is bytes and _sha(self.content)==self._request_sha256)
        return self._request_sha256

    def _verify_context(self,lease,protected):
        require_live_owner(lease,'execution')
        _need(lease is self._lease and type(protected) is ProtectedPaperCredentials)
        protected.__post_init__()
        self.sha256
        p=self.to_payload()
        _need(p['project_id']==lease.project_id==protected.project_id and p['account_alias']==protected.account_alias
              and self._credential_sha256==_sha(protected.ciphertext)
              and self._owner_generation==lease.generation and self._owner_instance==lease.identity.process_instance_id)
        _need(self._private_binding==_sha(canonical(dict(account_id=self.private_account_id,request_sha256=self._request_sha256,
                    credential_sha256=self._credential_sha256,generation=self._owner_generation,instance=self._owner_instance))))
        return p

    def _verify(self,lease,protected):
        try:return self._verify_context(lease,protected)
        except (ContractError,ValueError,TypeError,KeyError,UnicodeError,AttributeError):
            raise RuntimeRefused('PAPER_ORDER_CONTEXT_MISMATCH') from None

    def _validate_retention(self,raw):
        with _owner_scope(self._lease):
            self._verify(self._lease,self._protected)
            _need(type(raw) is bytes and len(raw)<=65536,'PAPER_ORDER_RESPONSE_INVALID')
            with open_paper_credentials(self._lease,self._protected) as opened:
                parsed=_reject_reflections(raw,tuple(opened.headers().values()))
                _private_id(raw,parsed,self.private_account_id)

    def wire(self):
        with _owner_scope(self._lease):
            p=self._verify(self._lease,self._protected)
            return _wire(p['operation'],p['parameters'],p['body'])


@dataclass(frozen=True,slots=True,repr=False,init=False)
class _PrivateOrderReply:
    content:bytes
    raw:bytes
    request:_PreparedOrderExchange
    def __init__(self,*,_factory=None,**fields):
        _need(_factory is _FACTORY,'PAPER_ORDER_UNQUALIFIED_RESULT')
        for key,value in fields.items():object.__setattr__(self,key,value)
    def __repr__(self):return '<QualifiedPaperOrderReply private context redacted>'
    def __reduce_ex__(self,protocol):raise RuntimeRefused('PAPER_ORDER_PRIVATE_SERIALIZATION_FORBIDDEN')
    def to_payload(self):return json.loads(self.content)


def prepare_order_exchange(lease,protected,*,account_id,request_id,intent_id,operation,created_at,parameters=None,body=None):
    with _owner_scope(lease) as state:
        require_live_owner(lease,'execution')
        _need(type(protected) is ProtectedPaperCredentials and protected.project_id==state.project.project_id)
        protected.__post_init__()
        try:
            identifier(account_id);identifier(request_id);identifier(intent_id);_local_time(created_at)
            method,target,wire=_wire(operation,parameters,body)
            value=dict(version=1,record_type='PreparedPaperOrderExchange',scope='PREPARATION_ONLY',
                       project_id=state.project.project_id,account_alias=protected.account_alias,request_id=request_id,intent_id=intent_id,
                       created_at=utc(created_at),operation=operation,method=method,target=target,
                       parameters={} if parameters is None else parameters.copy(),body=json.loads(wire) if wire else None,
                       transport_authorized=False,financial_accepted=False,approval_status='NOT_GRANTED')
            content=canonical(value);_need(len(content)<=8192,'PAPER_ORDER_REQUEST_INVALID')
            with open_paper_credentials(lease,protected) as opened:
                values=tuple(opened.headers().values())
                _reject_reflections(content,values)
                _reject_reflections(canonical(dict(private_account_id=account_id)),values)
            _private_id(content,value,account_id)
            credential_sha=_sha(protected.ciphertext);request_sha=_sha(content)
            private_binding=_sha(canonical(dict(account_id=account_id,request_sha256=request_sha,credential_sha256=credential_sha,
                                                generation=lease.generation,instance=lease.identity.process_instance_id)))
            return _PreparedOrderExchange(_factory=_FACTORY,content=content,private_account_id=account_id,_lease=lease,_protected=protected,
                                          _credential_sha256=credential_sha,_request_sha256=request_sha,_private_binding=private_binding,
                                          _owner_generation=lease.generation,_owner_instance=lease.identity.process_instance_id)
        except (ContractError,ValueError,TypeError,KeyError,UnicodeError,RecursionError):
            raise RuntimeRefused('PAPER_ORDER_REQUEST_INVALID') from None


def qualify_order_reply(lease,protected,request,raw,*,status,received_at):
    with _owner_scope(lease):
        require_live_owner(lease,'execution')
        _need(type(request) is _PreparedOrderExchange)
        try:
            p=request._verify(lease,protected)
            _need(type(raw) is bytes and len(raw)<=65536,'PAPER_ORDER_RESPONSE_INVALID')
            _need(status is None or type(status) is int and (status in (200,204) or 400<=status<=599),'PAPER_ORDER_RESPONSE_INVALID')
            elapsed=_local_time(received_at)-_local_time(p['created_at'])
            age_us=(elapsed.days*86400+elapsed.seconds)*1000000+elapsed.microseconds
            _need(0<=age_us<=10000000,'PAPER_ORDER_RESPONSE_INVALID')
            with open_paper_credentials(lease,protected) as opened:
                values=tuple(opened.headers().values());body=_reject_reflections(raw,values) if raw else None
                _private_id(raw,body,request.private_account_id)
                outcome='UNCONFIRMED';observation=None
                if status in (200,204):
                    if p['operation']=='CANCEL_ORDER':
                        _need(status==204 and raw==b'','PAPER_ORDER_RESPONSE_INVALID')
                        outcome='CANCEL_REQUEST_ACCEPTED_UNCONFIRMED'
                    else:
                        _need(status==200,'PAPER_ORDER_RESPONSE_INVALID');observation=_order(body,p);outcome='ORDER_REPLY_QUALIFIED'
                value=dict(version=1,record_type='QualifiedPaperOrderReply',scope='PREPARATION_ONLY',
                           request_sha256=request.sha256,request_id=p['request_id'],intent_id=p['intent_id'],account_alias=p['account_alias'],
                           operation=p['operation'],received_at=utc(received_at),age_since_request_creation_us=age_us,status=status,
                           raw_bytes=len(raw),raw_sha256=_sha(raw),outcome=outcome,observation=observation,
                           account_binding='PRIVATE_REQUEST_CONTEXT_ONLY',transport_authorized=False,financial_accepted=False,
                           retry_authorized=False,actual_flat=None)
                content=canonical(value);_need(len(content)<=65536,'PAPER_ORDER_RESPONSE_INVALID')
                _reject_reflections(content,values);_private_id(content,value,request.private_account_id)
                return _PrivateOrderReply(_factory=_FACTORY,content=content,raw=raw,request=request)
        except (ContractError,ValueError,TypeError,KeyError,UnicodeError,RecursionError,AttributeError):
            raise RuntimeRefused('PAPER_ORDER_RESPONSE_INVALID') from None
