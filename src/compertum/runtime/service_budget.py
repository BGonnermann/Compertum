"""Execution-owned cooperative admission; no request or retry authority."""
from collections import deque
import hashlib,json,time
from compertum.data.encoding import canonical
from .errors import RuntimeRefused
from .owners import _MUTEX,_owner_scope,require_live_owner

_WINDOW=60*10**9
_FACTORY=object()


def _need(value,code='HTTP_QUEUE_INVALID'):
    if not value:raise RuntimeRefused(code)

class _Ticket:
    __slots__=()
    def __repr__(self):return '<ServiceTicket redacted>'
    def __reduce_ex__(self,p):raise RuntimeRefused('HTTP_QUEUE_SERIALIZATION_FORBIDDEN')

class _Permit:
    __slots__=()
    def __repr__(self):return '<DispatchPermit redacted>'
    def __reduce_ex__(self,p):raise RuntimeRefused('HTTP_QUEUE_SERIALIZATION_FORBIDDEN')


class _ServiceQueue:
    def __init__(self,lease,guard,*,_factory,clock=None):
        _need(_factory is _FACTORY)
        self._lease=lease;self._guard=guard;self._fixture=clock is not None;self._clock=clock or time.monotonic_ns
        self._anchor=self._clock() if self._fixture else guard.acquired_monotonic_ns
        _need(type(self._anchor) is int and 0<=self._anchor<2**63-_WINDOW,'HTTP_QUEUE_CLOCK_INVALID')
        self._last=self._anchor;self._closed=False;self._poison=False;self._seq=0
        self._used={'DATA':deque(),'PAPER':deque()};self._entries={};self._producers={};self._claimed=None;self._binding=None;self._native=None;self._seal()
    def __repr__(self):return '<OwnedServiceQueue redacted>'
    def __reduce_ex__(self,p):raise RuntimeRefused('HTTP_QUEUE_SERIALIZATION_FORBIDDEN')
    def _digest(self):
        return hashlib.sha256(repr((id(self._lease),id(self._guard),id(self._clock),self._fixture,self._anchor,self._last,self._closed,self._poison,self._seq,
            tuple((k,tuple(v)) for k,v in self._used.items()),tuple((id(t),e) for t,e in self._entries.items()),
            tuple((i,id(p),id(t)) for i,(p,t) in self._producers.items()),None if self._claimed is None else tuple(map(id,self._claimed)),self._binding,self._native)).encode()).hexdigest()
    def _seal(self):self._hash=self._digest()
    def _verify(self):
        require_live_owner(self._lease,'execution')
        _need(not self._closed,'HTTP_QUEUE_CLOSED');_need(not self._poison,'HTTP_QUEUE_CLOCK_INVALID')
        _need(self._guard._service_queue_initialized and self._guard._service_queue is self and self in self._guard.resources and self._hash==self._digest(),'HTTP_QUEUE_CONTEXT_CHANGED')
    def _now(self):
        self._verify();value=self._clock()
        if type(value) is not int or not self._last<=value<2**63-_WINDOW:
            self._poison=True;self._seal();raise RuntimeRefused('HTTP_QUEUE_CLOCK_INVALID')
        self._last=value
        for rows in self._used.values():
            while rows and rows[0]<=value-_WINDOW:rows.popleft()
        self._seal();return value
    def _enqueue(self,service,priority,kind,deadline,producer=None):
        self._now();_need(service in ('PAPER','DATA') and type(priority) is int and 0<=priority<=3 and type(deadline) is int and time.monotonic_ns()<deadline<2**63)
        _need(len(self._entries)<16,'HTTP_QUEUE_CAPACITY');_need(self._seq<2**63-1,'HTTP_QUEUE_CAPACITY')
        ticket=_Ticket();self._seq+=1;self._entries[ticket]=(service,priority,kind,deadline,self._seq)
        if producer is not None:self._producers[id(producer)]=(producer,ticket)
        self._seal();return ticket
    def _claim(self,ticket):
        now=self._now();_need(type(ticket) is _Ticket and ticket in self._entries,'HTTP_TICKET_INVALID')
        if time.monotonic_ns()>=self._entries[ticket][3]:
            self.cancel(ticket);raise RuntimeRefused('HTTP_TICKET_EXPIRED')
        from ._winhttp_get import _PENDING
        if self._claimed is not None or len(_PENDING)>=4 or any(x._lease is self._lease for x in _PENDING.values()) or now<self._anchor+_WINDOW:return None
        eligible=[(entry[1],entry[4],t) for t,entry in self._entries.items() if len(self._used[entry[0]])<100 and time.monotonic_ns()<entry[3]]
        if not eligible or min(eligible,key=lambda x:x[:2])[2] is not ticket:return None
        permit=_Permit();self._claimed=(ticket,permit);self._seal();return permit
    def _validate_permit(self,permit,service,kind):
        self._now();_need(type(permit) is _Permit and self._claimed is not None and self._claimed[1] is permit,'HTTP_PERMIT_INVALID')
        ticket=self._claimed[0];_need(ticket in self._entries,'HTTP_PERMIT_INVALID');entry=self._entries[ticket]
        _need(entry[0]==service and entry[2]==kind,'HTTP_PERMIT_WRONG_REQUEST')
        _need(time.monotonic_ns()<entry[3],'HTTP_TICKET_EXPIRED');return ticket,entry
    def _commit(self,permit,service,kind):
        ticket,entry=self._validate_permit(permit,service,kind);now=self._now()
        _need(now>=self._anchor+_WINDOW and len(self._used[service])<100,'HTTP_ADMISSION_WAITING')
        self._used[service].append(now);self._drop(ticket);self._seal()
    def _drop(self,ticket):
        self._entries.pop(ticket,None)
        self._producers={i:pair for i,pair in self._producers.items() if pair[1] is not ticket}
        if self._claimed is not None and self._claimed[0] is ticket:self._claimed=None;self._binding=None;self._native=None
    def cancel(self,ticket):
        with _MUTEX:
            if self._closed:return
            _need(self._hash==self._digest(),'HTTP_QUEUE_CONTEXT_CHANGED');self._drop(ticket);self._seal()
    def status(self):
        with _owner_scope(self._lease):
            now=self._now();return dict(ready=now>=self._anchor+_WINDOW,wait_ns=max(0,self._anchor+_WINDOW-now),data_used=len(self._used['DATA']),paper_used=len(self._used['PAPER']),queued=len(self._entries),fixture_only=self._fixture)
    def close(self):
        with _MUTEX:
            self._closed=True;self._entries.clear();self._producers.clear();self._claimed=None;self._binding=None;self._native=None;self._seal()


def queue_for(lease):
    with _owner_scope(lease) as guard:
        require_live_owner(lease,'execution');q=guard._service_queue
        if q is None:
            _need(not guard._service_queue_initialized and not any(type(r) is _ServiceQueue for r in guard.resources),'HTTP_QUEUE_ALREADY_INITIALIZED')
            q=_ServiceQueue(lease,guard,_factory=_FACTORY);guard._service_queue=q;guard._service_queue_initialized=True;guard.resources.append(q)
        _need(type(q) is _ServiceQueue);q._verify();return q


def _install_loopback_queue(lease,clock):
    with _owner_scope(lease) as guard:
        require_live_owner(lease,'execution');_need(guard._service_queue is None and not guard._service_queue_initialized and not any(type(r) is _ServiceQueue for r in guard.resources) and callable(clock),'HTTP_QUEUE_ALREADY_INITIALIZED')
        q=_ServiceQueue(lease,guard,_factory=_FACTORY,clock=clock);guard._service_queue=q;guard._service_queue_initialized=True;guard.resources.append(q);return q


def _profile(native):
    from ._winhttp_get import _OwnedGet
    from ._winhttp_data import _OwnedDataGet
    from ._winhttp_asset import _OwnedAssetGet
    from ._winhttp_order import _OwnedOrderHTTP
    from ._winhttp_activity import _OwnedActivityGet
    from .paper_fixture_orders import _FixtureOrderHTTP
    if type(native) is _FixtureOrderHTTP:return 'PAPER',native._method
    if type(native) is _OwnedActivityGet:return 'PAPER','ACTIVITY'
    if type(native) is _OwnedGet:return 'PAPER','READ'
    if type(native) is _OwnedAssetGet:return 'PAPER','ASSET'
    if type(native) is _OwnedDataGet:
        p=json.loads(native._request_bytes);return 'DATA',p.get('operation','CURRENT_ACTIONS')
    if type(native) is _OwnedOrderHTTP:return 'PAPER','READ' if native._method=='GET' else native._method
    raise RuntimeRefused('HTTP_QUEUE_ADAPTER_INVALID')


def _prepared_binding(producer):
    from .paper_activity_owner import _ActivityProducer
    from .paper_market_collection import _MarketCollection
    from .paper_market_fresh import _MarketFresh
    from .paper_market_qualification import _PreparedMarketExchange
    from .paper_read_owner import PaperReadOwner
    from .paper_fixture_orders import _FixtureOrderProducer
    if type(producer) is _FixtureOrderProducer:
        from .paper_order_qualification import _PreparedOrderExchange
        producer._check();_need(producer._state=='PENDING' and type(producer._pending) is _PreparedOrderExchange)
        x=producer._pending;request=x;raw=x.content;p=x._verify(producer._lease,producer._protected)
        from ._winhttp_order import _wire
        method,target,body=_wire(p['operation'],p['parameters'],p['body'])
        return (id(producer),id(x),id(request),hashlib.sha256(raw).hexdigest(),'_FixtureOrderHTTP',target,
            method,hashlib.sha256(body).hexdigest(),('127.0.0.1',producer._port,False),
            hashlib.sha256(canonical({'X-Compertum-Test':producer._header})).hexdigest())
    if type(producer) is _ActivityProducer:
        producer._check(full=False);_need(producer._state=='PENDING')
        x=producer;request=producer._request;request.__post_init__();raw=request.content
        target=request.to_payload()['target'];adapter='_OwnedActivityGet'
    elif type(producer) in (_MarketCollection,_MarketFresh):
        producer._context();x=producer._pending
        _need(producer._state=='PENDING' and type(x) is _PreparedMarketExchange,'HTTP_PERMIT_WRONG_REQUEST')
        wire,target=x._verify(producer._lease,producer._protected)
        adapter='_OwnedAssetGet' if wire.get('operation')=='ASSET' else '_OwnedDataGet'
        request=x._request;raw=x._content
    elif type(producer) is PaperReadOwner:
        _need(not producer._closed and producer in producer._guard.resources,'HTTP_PERMIT_WRONG_REQUEST')
        x=producer._packet
        _need(x is not None and not x._closed and x._state=='PENDING','HTTP_PERMIT_WRONG_REQUEST')
        x._context();x.remaining_seconds();request=x._pending
        request.__post_init__();raw=request.content;target=request.to_payload()['target'];adapter='_OwnedGet'
    else:raise RuntimeRefused('HTTP_QUEUE_PRODUCER_INVALID')
    return (id(producer),id(x),id(request),hashlib.sha256(raw).hexdigest(),adapter,target)


def bind_producer_permit(producer,permit):
    lease=getattr(producer,'_lease',None) or getattr(producer,'lease',None)
    with _owner_scope(lease):
        q=queue_for(lease);pair=q._producers.get(id(producer))
        _need(pair is not None and pair[0] is producer and q._claimed==(pair[1],permit),'HTTP_PERMIT_INVALID')
        _need(q._binding is None and q._native is None,'HTTP_PERMIT_WRONG_REQUEST')
        q._binding=_prepared_binding(producer);q._seal()


def _native_wire(native):
    raw=getattr(native,'_request_bytes',b'');request=getattr(native,'_source_request',None)
    return (id(native),type(native).__name__,native._origin,native._wire_path,native._method,
            id(request),hashlib.sha256(raw).hexdigest(),native._wire_body_sha256,getattr(native,'_wire_header_sha256',None))


def _validate_binding(q,native,permit,service,kind):
    ticket,entry=q._validate_permit(permit,service,kind)
    producers=[p for p,t in q._producers.values() if t is ticket]
    if producers:
        _need(len(producers)==1 and q._binding==_prepared_binding(producers[0]),'HTTP_PERMIT_WRONG_REQUEST')
        _,_,rid,sha,adapter,target=q._binding[:6]
        method='GET'
        if adapter=='_FixtureOrderHTTP':
            method,body_sha,origin,header_sha=q._binding[6:]
            _need(native._wire_body_sha256==body_sha and native._origin==origin
                and native._wire_header_sha256==header_sha,'HTTP_PERMIT_WRONG_REQUEST')
        _need(type(native).__name__==adapter and id(getattr(native,'_source_request',None))==rid
              and hashlib.sha256(getattr(native,'_request_bytes',b'')).hexdigest()==sha
              and native._wire_path==target and native._method==method,'HTTP_PERMIT_WRONG_REQUEST')
    else:
        _need(entry[1]==3 and q._binding is None,'HTTP_PERMIT_WRONG_REQUEST')
    _need(q._native==_native_wire(native),'HTTP_PERMIT_WRONG_REQUEST')


def native_permit(native,provided=None):
    """Before any native handle; direct calls make one lowest-priority claim."""
    q=queue_for(native._lease)
    _need(not q._fixture or native._origin[0]=='127.0.0.1' and native._origin[2] is False,'HTTP_FIXTURE_QUEUE_TLS_FORBIDDEN')
    service,kind=_profile(native);direct=provided is None
    if direct:
        ticket=q._enqueue(service,3,kind,int(native._deadline*10**9))
        try:
            provided=q._claim(ticket)
            _need(provided is not None,'HTTP_ADMISSION_WAITING')
        except BaseException:q.cancel(ticket);raise
    q._validate_permit(provided,service,kind)
    _need(q._native is None,'HTTP_PERMIT_WRONG_REQUEST')
    # Only this adapter instance may use the claim. Failed setup cancels it.
    q._native=_native_wire(native);q._seal()
    try:_validate_binding(q,native,provided,service,kind)
    except BaseException:
        q._native=None;q._seal()
        if direct:q.cancel(ticket)
        raise
    return q,provided,service,kind,native


def commit_native(admission):
    q,permit,service,kind,native=admission
    _validate_binding(q,native,permit,service,kind);q._commit(permit,service,kind)


def cancel_native(admission):
    if admission is None:return
    q,permit,_,_,_=admission
    with _MUTEX:
        if q._claimed is not None and q._claimed[1] is permit:q.cancel(q._claimed[0])


def _producer_permit_locked(producer):
    """Trust registered producer type, never caller-provided service/priority."""
    from .paper_market_collection import _MarketCollection
    from .paper_market_fresh import _MarketFresh
    from .paper_read_owner import PaperReadOwner
    from .paper_activity_owner import _ActivityProducer
    from .paper_fixture_orders import _FixtureOrderProducer
    if type(producer) is _FixtureOrderProducer:
        producer._check();lease=producer._lease;_need(producer._state=='READY')
        profile=('PAPER',0,'DELETE' if getattr(producer,'_purpose',None)=='CANCEL' else 'POST');deadline=producer._deadline_ns
    elif type(producer) is _ActivityProducer:
        producer._check(full=False);lease=producer._lease;_need(producer._state=='READY')
        profile=('PAPER',0,'ACTIVITY');deadline=producer._deadline_ns
    elif type(producer) is _MarketCollection:
        producer._context();lease=producer._lease;_need(producer._state=='READY')
        profile=('DATA',2,'HISTORY' if producer._mode=='HISTORY' else 'CURRENT_ACTIONS');deadline=int((producer._real_started+80)*10**9)
    elif type(producer) is _MarketFresh:
        producer._context();lease=producer._lease;_need(producer._state=='READY')
        profile=('PAPER',1,'ASSET') if producer._attempts==0 else ('DATA',1,'QUOTE');deadline=int((producer._real_started+20)*10**9)
    elif type(producer) is PaperReadOwner:
        lease=producer.lease;_need(not producer._closed and producer._packet is not None and producer._packet._state=='READY')
        with _owner_scope(lease) as guard:_need(producer in guard.resources)
        profile=('PAPER',0,'READ');deadline=producer._packet._started_real_ns+30*10**9
    else:raise RuntimeRefused('HTTP_QUEUE_PRODUCER_INVALID')
    q=queue_for(lease);entry=q._producers.get(id(producer))
    if entry is None:ticket=q._enqueue(*profile,deadline,producer)
    else:
        _need(entry[0] is producer);ticket=entry[1]
        _need(q._entries[ticket][:3]==profile and q._entries[ticket][3]==deadline,'HTTP_QUEUE_PRODUCER_CHANGED')
    return q._claim(ticket)


def cancel_producer(producer):
    lease=getattr(producer,'_lease',None) or getattr(producer,'lease',None)
    from .owners import _LEASES
    with _MUTEX:
        guard=_LEASES.get(lease);q=None if guard is None else guard._service_queue
        if type(q) is _ServiceQueue:
            entry=q._producers.get(id(producer))
            if entry is not None and entry[0] is producer:q.cancel(entry[1])


def producer_permit(producer):
    lease=getattr(producer,'_lease',None) or getattr(producer,'lease',None)
    with _owner_scope(lease):return _producer_permit_locked(producer)
