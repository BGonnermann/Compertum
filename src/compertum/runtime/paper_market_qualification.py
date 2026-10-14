"""Private execution-owned market exchange; no grants, publication or packet driver."""
from dataclasses import dataclass
import json,time
from compertum.data.encoding import canonical
from compertum.domain import ContractError
from compertum.paper_market_inputs import MarketObservation,OperationalMarketRequest,_ns,_sha
from compertum.paper_action_inputs import CurrentActionPage
from .errors import RuntimeRefused
from .owners import _MUTEX,_owner_scope,require_live_owner
from .paper_credentials import ProtectedPaperCredentials,open_paper_credentials
from .paper_read_secrecy import _reject_reflections
from ._winhttp_data import _OwnedDataGet,_wire as _data_wire
from ._winhttp_asset import _OwnedAssetGet,_wire as _asset_wire

_FACTORY=object()
_INVALID=(ContractError,ValueError,TypeError,KeyError,UnicodeError,RecursionError,AttributeError)


def _need(value,code='PAPER_MARKET_CONTEXT_MISMATCH'):
    if not value:raise RuntimeRefused(code)


def _wire(request,request_id,requested_at,page_token):
    if type(request) is OperationalMarketRequest:
        request.__post_init__()
        if request.to_payload()['operation']=='ASSET':
            _need(request_id is requested_at is page_token is None)
            return _asset_wire(request)
    return _data_wire(request,request_id,requested_at,page_token)


def _binding(content,plan,credential,generation,instance):
    return _sha(canonical(dict(request=_sha(content),plan=_sha(plan),credential=credential,generation=generation,instance=instance)))


@dataclass(frozen=True,slots=True,repr=False,init=False,eq=False)
class _PreparedMarketExchange:
    _lease:object
    _state:object
    _protected:ProtectedPaperCredentials
    _request:object
    _action:tuple
    _content:bytes
    _plan_bytes:bytes
    _credential_sha256:str
    _owner_generation:int
    _owner_instance:str
    _binding_sha256:str
    _closed:bool
    _started:bool
    _transport:object
    _dispatch_origin:object
    _reply:object
    _dispatch_commit_ns:object
    _commit_deadline_ns:object
    _native_sha256:str

    def __init__(self,*,_factory=None,**fields):
        _need(_factory is _FACTORY,'PAPER_MARKET_UNQUALIFIED_CONTEXT')
        for k,v in fields.items():object.__setattr__(self,k,v)
    def __repr__(self):return '<PreparedMarketExchange private context redacted>'
    def __reduce_ex__(self,protocol):raise RuntimeRefused('PAPER_MARKET_SERIALIZATION_FORBIDDEN')

    def _verify(self,lease,protected):
        try:
            require_live_owner(lease,'execution')
            _need(lease is self._lease and protected is self._protected and type(protected) is ProtectedPaperCredentials)
            _need(not self._closed and self in self._state.resources)
            protected.__post_init__()
            plan,content,target=_wire(self._request,*self._action)
            p=plan.to_payload()
            _need(content==self._content and plan.content==self._plan_bytes and len(content)<=65536 and len(plan.content)<=65536)
            _need(p['project_id']==lease.project_id==protected.project_id and p['account_alias']==protected.account_alias)
            _need(_sha(protected.ciphertext)==self._credential_sha256 and lease.generation==self._owner_generation and lease.identity.process_instance_id==self._owner_instance)
            _need(self._binding_sha256==_binding(content,plan.content,self._credential_sha256,self._owner_generation,self._owner_instance))
            _need(self._native_signature()==self._native_sha256)
            return json.loads(content),target
        except _INVALID:raise RuntimeRefused('PAPER_MARKET_CONTEXT_MISMATCH') from None

    @property
    def content(self):
        with _owner_scope(self._lease):
            self._verify(self._lease,self._protected)
            return self._content

    def _native_signature(self):
        _need(self._dispatch_commit_ns is None or type(self._dispatch_commit_ns) is int and 0<=self._dispatch_commit_ns<=2**63-1)
        return _sha(canonical(dict(binding=self._binding_sha256,transport=None if self._transport is None else id(self._transport),
                                  origin=self._dispatch_origin,committed_ns=self._dispatch_commit_ns,commit_deadline_ns=self._commit_deadline_ns)))

    def _seal_native(self):object.__setattr__(self,'_native_sha256',self._native_signature())

    def _observe_native(self,transport,stage):
        request,target=self._verify(self._lease,self._protected)
        _need(self._started and type(transport) is _OwnedDataGet and transport._lease is self._lease)
        _need(transport._request_bytes==self._content and transport._request_sha256==_sha(self._content)
              and transport._plan_sha256==_sha(self._plan_bytes) and transport._method=='GET' and transport._wire_path==target
              and transport._origin==transport._data_origin==self._dispatch_origin)
        if stage=='INITIALIZED':
            _need(self._transport is None and self._dispatch_commit_ns is None)
            object.__setattr__(self,'_transport',transport)
        else:
            _need(stage=='COMMITTED' and self._transport is transport and self._dispatch_commit_ns is None)
            # Conservative evidence: SendRequest may begin immediately after this.
            transport._check_deadline()
            observed=time.monotonic_ns()
            _need(self._commit_deadline_ns is None or observed<self._commit_deadline_ns,'HTTP_DEADLINE_EXCEEDED')
            object.__setattr__(self,'_dispatch_commit_ns',observed)
        self._seal_native()

    def _native_evidence(self):
        # Closure revokes reply access but must not erase dispatch/cleanup facts.
        with _owner_scope(self._lease):
            require_live_owner(self._lease,'execution')
            _need(self._native_signature()==self._native_sha256)
            _need(self._owner_generation==self._lease.generation and self._owner_instance==self._lease.identity.process_instance_id)
            _need(self._binding_sha256==_binding(self._content,self._plan_bytes,self._credential_sha256,self._owner_generation,self._owner_instance))
            t=self._transport
            if t is not None:
                asset=json.loads(self._content).get('operation')=='ASSET'
                _need(type(t) is (_OwnedAssetGet if asset else _OwnedDataGet) and t._lease is self._lease and t._request_bytes==self._content)
                _need(t._origin==self._dispatch_origin and type(t.native_closed) is bool)
            return dict(dispatch_committed_ns=self._dispatch_commit_ns,native_closed=t is None or t.native_closed,
                        observed_status=None if t is None else t.status_code)
    def _observation(self,raw,status,received_at):
        if type(self._request) is OperationalMarketRequest:return MarketObservation(self._request,raw,status,received_at)
        rid,at,token=self._action
        return CurrentActionPage(self._request,rid,token,at,received_at,status,raw)

    def close(self):
        # Revocation is independent of lease validity. Immutable caller copies cannot be erased.
        with _MUTEX:
            object.__setattr__(self,'_closed',True)
            reply=self._reply
            if reply is not None:
                object.__setattr__(reply,'_raw',b'');object.__setattr__(reply,'_content',b'')
                object.__setattr__(self,'_reply',None)
            transport=self._transport
            if transport is not None:
                try:transport.close()
                finally:transport._result=None
            if not self._state.closed and self in self._state.resources:self._state.resources.remove(self)


@dataclass(frozen=True,slots=True,repr=False,init=False,eq=False)
class _PrivateMarketReply:
    _exchange:_PreparedMarketExchange
    _raw:bytes
    _content:bytes
    _raw_sha256:str
    _content_sha256:str

    def __init__(self,*,_factory=None,**fields):
        _need(_factory is _FACTORY,'PAPER_MARKET_UNQUALIFIED_REPLY')
        for k,v in fields.items():object.__setattr__(self,k,v)
    def __repr__(self):return '<PrivateMarketReply original response redacted>'
    def __reduce_ex__(self,protocol):raise RuntimeRefused('PAPER_MARKET_SERIALIZATION_FORBIDDEN')
    def _verify(self):
        x=self._exchange;x._verify(x._lease,x._protected)
        _need(x._reply is self and type(self._raw) is bytes and type(self._content) is bytes
              and _sha(self._raw)==self._raw_sha256 and _sha(self._content)==self._content_sha256)
    @property
    def raw(self):
        with _owner_scope(self._exchange._lease):self._verify();return self._raw
    @property
    def content(self):
        with _owner_scope(self._exchange._lease):self._verify();return self._content
    def to_payload(self):return json.loads(self.content)
    def observation(self):
        with _owner_scope(self._exchange._lease):
            self._verify();p=json.loads(self._content)
            return self._exchange._observation(self._raw,p['status'],p['received_at'])


def prepare_market_exchange(lease,protected,request,*,action_request_id=None,action_requested_at=None,action_page_token=None):
    with _owner_scope(lease) as state:
        require_live_owner(lease,'execution')
        try:
            _need(type(protected) is ProtectedPaperCredentials);protected.__post_init__()
            action=(action_request_id,action_requested_at,action_page_token)
            plan,content,_=_wire(request,*action);p=plan.to_payload()
            _need(p['project_id']==state.project.project_id==protected.project_id and p['account_alias']==protected.account_alias)
            _need(len(content)<=65536 and len(plan.content)<=65536)
            _need(sum(type(r) is _PreparedMarketExchange for r in state.resources)<4,'PAPER_MARKET_CONTEXT_LIMIT')
            with open_paper_credentials(lease,protected) as opened:
                values=tuple(opened.headers().values());_reject_reflections(plan.content,values);_reject_reflections(content,values)
            credential=_sha(protected.ciphertext);generation=lease.generation;instance=lease.identity.process_instance_id
            x=_PreparedMarketExchange(_factory=_FACTORY,_lease=lease,_state=state,_protected=protected,_request=request,_action=action,
                _content=content,_plan_bytes=plan.content,_credential_sha256=credential,_owner_generation=generation,_owner_instance=instance,
                _binding_sha256=_binding(content,plan.content,credential,generation,instance),_closed=False,_started=False,_transport=None,_dispatch_origin=None,_reply=None,_dispatch_commit_ns=None,_commit_deadline_ns=None)
            x._seal_native();state.resources.append(x);return x
        except _INVALID:raise RuntimeRefused('PAPER_MARKET_REQUEST_INVALID') from None


def start_market_exchange(exchange,*,timeout=10,_test_port=None,_deadline_at=None,_pre_send=None,_permit=None,_commit_deadline_ns=None):
    _need(type(exchange) is _PreparedMarketExchange)
    with _owner_scope(exchange._lease):
        try:
            wire,_=exchange._verify(exchange._lease,exchange._protected)
            _need(not exchange._started and exchange._reply is None,'PAPER_MARKET_ALREADY_USED')
            _need(_commit_deadline_ns is None or type(_commit_deadline_ns) is int and 0<=_commit_deadline_ns<=2**63-1)
            object.__setattr__(exchange,'_commit_deadline_ns',_commit_deadline_ns);exchange._seal_native()
            object.__setattr__(exchange,'_started',True)
            _need(_test_port is None or type(_test_port) is int and 1<=_test_port<=65535)
            asset=wire.get('operation')=='ASSET'
            origin=(('paper-api.alpaca.markets' if asset else 'data.alpaca.markets'),443,True) if _test_port is None else ('127.0.0.1',_test_port,False)
            object.__setattr__(exchange,'_dispatch_origin',origin);exchange._seal_native()
            with open_paper_credentials(exchange._lease,exchange._protected) as opened:
                headers=opened.headers() if _test_port is None else {'X-Compertum-Test':'synthetic'}
                rid,at,token=exchange._action
                options=dict(request=exchange._request,headers=headers,timeout=timeout,_test_port=_test_port,_deadline_at=_deadline_at,_pre_send=_pre_send,_permit=_permit)
                if asset:transport=_OwnedAssetGet(exchange._lease,**options)
                else:transport=_OwnedDataGet(exchange._lease,**options,action_request_id=rid,action_requested_at=at,action_page_token=token,_native_observer=exchange._observe_native)
            if asset:object.__setattr__(exchange,'_transport',transport);exchange._seal_native()
            else:_need(exchange._transport is transport)
            return transport
        except BaseException:
            exchange.close();raise


def _provenance(exchange,result,raw,status,target):
    t=exchange._transport
    if t is None:
        _need(result is None and not exchange._started)
        return 'UNVERIFIED','UNVERIFIED'
    asset=json.loads(exchange._content).get('operation')=='ASSET'
    _need(type(t) is (_OwnedAssetGet if asset else _OwnedDataGet) and t._lease is exchange._lease and t.native_closed
          and t._result is result and result is not None and result.body==raw and result.status_code==status and t.retry_after==result.retry_after)
    _need(t._request_bytes==exchange._content and t._request_sha256==_sha(exchange._content)
          and t._plan_sha256==_sha(exchange._plan_bytes) and t._method=='GET' and t._wire_path==target==(t._asset_target if asset else t._data_target)
          and t._origin==(t._asset_origin if asset else t._data_origin)==exchange._dispatch_origin)
    if asset and t._origin==('paper-api.alpaca.markets',443,True):return 'PAPER_TLS','PINNED_ENVELOPE'
    if not asset and t._origin==('data.alpaca.markets',443,True):return 'DATA_TLS','PINNED_ENVELOPE'
    _need(t._origin[0]=='127.0.0.1' and t._origin[2] is False)
    return 'LOOPBACK_FIXTURE','NOT_SENT_FIXTURE'


def qualify_market_reply(lease,protected,exchange,raw,*,status,received_at,result=None):
    _need(type(exchange) is _PreparedMarketExchange)
    with _owner_scope(lease):
        try:
            request,target=exchange._verify(lease,protected)
            _need(exchange._reply is None,'PAPER_MARKET_ALREADY_USED')
            _need(type(raw) is bytes and 0<len(raw)<=65536,'PAPER_MARKET_RESPONSE_INVALID')
            with open_paper_credentials(lease,protected) as opened:
                values=tuple(opened.headers().values());_reject_reflections(raw,values)
                # The secrecy parser's ordinary float values never enter market calculations.
                exchange._observation(raw,status,received_at)
                provenance,binding=_provenance(exchange,result,raw,status,target)
                started=request.get('created_at',request.get('requested_at'))
                content=canonical(dict(version=1,record_type='PrivateMarketReply',scope='PREPARATION_ONLY',
                    request_sha256=_sha(exchange._content),plan_sha256=_sha(exchange._plan_bytes),request_id=request['request_id'],
                    operation=request.get('operation','CURRENT_ACTIONS'),status=status,received_at=received_at,age_ns=_ns(received_at)-_ns(started),
                    raw_bytes=len(raw),raw_sha256=_sha(raw),transport_provenance=provenance,credential_dispatch_binding=binding,
                    outcome='HTTP_RESPONSE_OBSERVED' if status==200 else 'HTTP_REFUSED',semantic_qualification='NOT_PERFORMED',timestamps='DECLARED',
                    transport_authorized=False,financial_accepted=False,research_eligible=False,entitlement='UNVERIFIED',coverage='UNVERIFIED'))
                _need(len(content)<=8192,'PAPER_MARKET_RESPONSE_INVALID');_reject_reflections(content,values)
                reply=_PrivateMarketReply(_factory=_FACTORY,_exchange=exchange,_raw=raw,_content=content,_raw_sha256=_sha(raw),_content_sha256=_sha(content))
                object.__setattr__(exchange,'_reply',reply);return reply
        except BaseException as error:
            if getattr(exchange,'_lease',None) is lease:exchange.close()
            if isinstance(error,_INVALID):raise RuntimeRefused('PAPER_MARKET_RESPONSE_INVALID') from None
            raise
