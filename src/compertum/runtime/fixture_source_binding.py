"""Private native identity for controlled loopback sources. No broker permission."""
import ctypes as c
from dataclasses import asdict
from datetime import datetime,timezone
import hashlib,json,os,socket
from compertum.data.encoding import canonical
from compertum.fixture_source_journal import decode_source_journal
from compertum.fixture_order_origin import decode_order_origin
from compertum.paper_contracts import strict_json
from compertum.persistence import checked_path,open_store
from .errors import RuntimeRefused
from .owners import _MUTEX,_owner_scope,_metadata,require_live_owner
from .paper_credential_slot import _coordinator_records

D=c.c_uint32
class _Row4(c.Structure):
    _fields_=[(n,D) for n in ('state','address','port','remote','remote_port','pid')]
class _Row6(c.Structure):
    _fields_=[('address',c.c_ubyte*16),('scope',D),('port',D),('remote',c.c_ubyte*16),('remote_scope',D),('remote_port',D),('state',D),('pid',D)]
class _Table4(c.Structure):_fields_=[('count',D),('rows',_Row4*1)]
class _Table6(c.Structure):_fields_=[('count',D),('rows',_Row6*1)]
SOURCE_PATH='state/fixture-economic-source.jsonl'
ORDER_SOURCE_PATH='state/fixture-order-source.jsonl'
_FACTORY=object()

def _need(ok):
    if not ok:raise RuntimeRefused('FIXTURE_NATIVE_SOURCE_UNVERIFIED')
def _sha(raw):return hashlib.sha256(raw).hexdigest()

def _rows(raw,row_type,table_type):
    _need(type(raw) is bytes and 4<=len(raw)<=1024**2)
    count=D.from_buffer_copy(raw[:4]).value;offset=table_type.rows.offset;size=c.sizeof(row_type)
    _need(count<=16384 and offset+count*size<=len(raw))
    return [row_type.from_buffer_copy(raw[offset+i*size:offset+(i+1)*size]) for i in range(count)]

def listener_pid(ipv4,ipv6,port):
    _need(type(port) is int and 1<=port<=65535)
    rows=[r for r in _rows(ipv4,_Row4,_Table4) if r.state==2 and socket.ntohs(r.port&65535)==port]
    other=[r for r in _rows(ipv6,_Row6,_Table6) if r.state==2 and socket.ntohs(r.port&65535)==port]
    _need(len(rows)==1 and not other and rows[0].pid>0)
    _need(rows[0].address==int.from_bytes(socket.inet_aton('127.0.0.1'),'little'))
    return rows[0].pid

def _table(family):
    _need(os.name=='nt');fn=c.WinDLL('iphlpapi',use_last_error=True).GetExtendedTcpTable
    fn.restype=D;fn.argtypes=[c.c_void_p,c.POINTER(D),c.c_int,D,c.c_int,D]
    size=D();code=fn(None,c.byref(size),False,family,3,0)
    _need(code in (0,122))
    for _ in range(3):
        _need(4<=size.value<=1024**2);buffer=c.create_string_buffer(size.value)
        code=fn(buffer,c.byref(size),False,family,3,0)
        if code==0:
            _need(size.value<=len(buffer));return buffer.raw[:size.value]
        _need(code==122)
    raise RuntimeRefused('FIXTURE_NATIVE_SOURCE_UNVERIFIED')

def native_source_peer(lease,port):
    from .ipc import RoleEndpoint,PeerRegistration
    from ._pipes import verify_peer
    with _owner_scope(lease) as guard:
        require_live_owner(lease,'execution')
        endpoints=[x for x in guard.resources if isinstance(x,RoleEndpoint) and not x.closed and x._owner_channel is not None]
        _need(len(endpoints)==1);endpoint=endpoints[0];channel=endpoint._owner_channel
        with endpoint._lock:
            _need(not channel.closed and channel.endpoint is endpoint)
            raw=guard.api.read_regular(guard.project.root_path/'state/locks/supervisor.json')
            generation,identity=_metadata(raw,guard.project,'supervisor')
            registration=PeerRegistration(identity,guard.project.logon_sid,guard.project.project_id,generation,'worker')
            with channel.api.peer(channel.handle,server_side=False) as peer:
                verify_peer(registration,peer)
                _need(channel.api.parent_pid(os.getpid())==peer.pid)
                _need(listener_pid(_table(2),_table(23),port)==peer.pid)
            return dict(project_id=guard.project.project_id,generation=generation,identity=asdict(identity),logon_sid=registration.logon_sid)

def _reserved_source_file(lease,relative):
    with _owner_scope(lease) as guard:
        path=checked_path(guard.project.root_path,guard.project.root_path/relative)
        with _coordinator_records(guard) as db:
            _need(db.execute('SELECT maximum,status,category FROM reservations WHERE path=? LIMIT 2',(relative,)).fetchall()==[(128*1024,'RUNTIME','records')])
        with guard.api.open_directory(path.parent),guard.api.open_file(path,0x80000000,3) as handle:
            info=guard.api.file_info(handle);_need(not info.attributes&0x410 and info.links==1)
            identity=list(guard.api.file_identity(handle));raw=guard.api.read_regular(path,maximum=128*1024)
            _need(list(guard.api.file_identity(handle))==identity)
        return raw,identity

def source_file(lease):
    with _owner_scope(lease) as guard:
        raw,identity=_reserved_source_file(lease,SOURCE_PATH);value=decode_source_journal(raw)
        _need(value['ledger']['project_id']==guard.project.project_id)
        return value,identity

def order_source_file(lease):
    with _owner_scope(lease) as guard:
        raw,identity=_reserved_source_file(lease,ORDER_SOURCE_PATH);value=decode_order_origin(raw)
        _need(value['origin']['project_id']==guard.project.project_id)
        return value,identity

class _SourceStart:
    def __init__(self,lease,request,port,*,_factory=None):
        _need(_factory is _FACTORY)
        self.lease=lease;self.request=request.content;self.port=port;self.closed=False
        self.peer=native_source_peer(lease,port);source,self.file_identity=source_file(lease)
        self.producer=source['producer_id'];self.genesis=source['genesis_sha256']
        self.orders,self.order_file_identity=order_source_file(lease)
        _need(self.orders['origin']['economic_producer_id']==self.producer and self.orders['origin']['economic_genesis_sha256']==self.genesis)
        _need(all(self.orders['origin'][k]==source['ledger'][k] for k in ('account_alias','asset_id','symbol')))
        _need(self.orders['origin']['initial_cash']==source['ledger']['opening_cash'])
        from ._pipes import NativePipeAPI
        self.api=NativePipeAPI();self.context=self.api.open_process(self.peer['identity']['pid']);self.pin=self.context.__enter__()
        try:
            _need(self.api.creation_time(self.pin)==self.peer['identity']['creation_filetime'] and self.api.WaitForSingleObject(self.pin.get(),0)==258)
            with _owner_scope(lease) as guard:guard.resources.append(self)
        except BaseException:self.context.__exit__(None,None,None);raise
    def __repr__(self):return '<PrivateFixtureSourceStart redacted>'
    def __reduce_ex__(self,protocol):raise RuntimeRefused('FIXTURE_SOURCE_SERIALIZATION_FORBIDDEN')
    def close(self):
        with _MUTEX:
            if self.closed:return
            self.closed=True;self.context.__exit__(None,None,None)
            try:
                with _owner_scope(self.lease) as guard:
                    if self in guard.resources:guard.resources.remove(self)
            except RuntimeRefused:pass

def _close_source_start(transport):
    start=getattr(transport,'_fixture_source_start',None)
    if type(start) is _SourceStart:start.close()

def start_fixture_get(lease,request,port,timeout,*,_permit=None):
    from ._winhttp_get import _OwnedGet
    with _owner_scope(lease):
        request.__post_init__();p=request.to_payload()
        guard=_SourceStart(lease,request,port,_factory=_FACTORY) if p['operation']=='ACCOUNT' else None
        try:
            transport=_OwnedGet(lease,host='127.0.0.1',port=port,secure=False,path=p['target'],
                headers={'X-Compertum-Test':'synthetic'},timeout=timeout,_permit=_permit,_read_request=request)
            if guard is not None:transport._fixture_source_start=guard
            return transport
        except BaseException:
            if guard is not None:guard.close()
            raise

def finish_if_present(transport,result,lease,request):
    start=getattr(transport,'_fixture_source_start',None)
    if start is None:return None
    from ._winhttp_get import _OwnedGet,_HTTPResult
    try:
        with _owner_scope(lease) as guard:
            _need(type(start) is _SourceStart and start in guard.resources and not start.closed)
            _need(type(transport) is _OwnedGet and type(result) is _HTTPResult)
            _need(start.lease is lease and transport._lease is lease and start.request==request.content==transport._request_bytes)
            _need(transport._result is result and transport.native_closed and result.status_code==200)
            _need(transport._origin==('127.0.0.1',start.port,False) and transport._method=='GET' and transport._wire_path==request.to_payload()['target'])
            _need(start.api.WaitForSingleObject(start.pin.get(),0)==258 and native_source_peer(lease,start.port)==start.peer)
            source,identity=source_file(lease);payload=strict_json(result.body);embedded=payload['compertum_fixture_source']
            orders,order_identity=order_source_file(lease)
            _need(order_identity==start.order_file_identity and canonical(orders)==canonical(start.orders))
            _need(type(payload['id']) is str and _sha(payload['id'].encode())==orders['origin']['account_identity_sha256'])
            _need(identity==start.file_identity and source['producer_id']==start.producer and source['genesis_sha256']==start.genesis)
            _need(set(embedded)=={'version','producer_id','genesis_sha256','ledger','served_by','order_source'} and type(embedded['version']) is int and embedded['version']==1)
            _need(canonical(embedded['order_source'])==canonical({k:orders[k] for k in ('producer_id','genesis_sha256','journal_sha256')}))
            _need(canonical(embedded['served_by'])==canonical(start.peer) and embedded['producer_id']==start.producer and embedded['genesis_sha256']==start.genesis)
            _need(canonical(embedded['ledger'])==canonical(source['ledger']) and embedded['ledger']['covered_until'] is not None)
            value=dict(version=1,scope='CONTROLLED_NATIVE_SOURCE',project_id=guard.project.project_id,
                request_sha256=request.sha256,raw_sha256=_sha(result.body),source_sha256=_sha(canonical(embedded)),
                source_file_identity=identity,producer_id=start.producer,genesis_sha256=start.genesis,
                order_source_file_identity=order_identity,order_source=embedded['order_source'],
                peer=start.peer,port=start.port,captured_at=datetime.now(timezone.utc).isoformat().replace('+00:00','Z'))
            store=open_store(lease,'execution');db=store.conn;_need(not db.in_transaction)
            with store._live(),db:
                db.execute('CREATE TABLE IF NOT EXISTS fixture_source_witnesses(request_sha256 TEXT PRIMARY KEY,body TEXT NOT NULL)')
                db.execute("CREATE TRIGGER IF NOT EXISTS fixture_witness_no_update BEFORE UPDATE ON fixture_source_witnesses BEGIN SELECT RAISE(ABORT,'immutable source witness'); END")
                db.execute("CREATE TRIGGER IF NOT EXISTS fixture_witness_no_delete BEFORE DELETE ON fixture_source_witnesses BEGIN SELECT RAISE(ABORT,'immutable source witness'); END")
                previous=db.execute('SELECT body FROM fixture_source_witnesses WHERE request_sha256=?',(request.sha256,)).fetchone()
                encoded=canonical(value).decode()
                if previous is None:
                    _need(db.execute('SELECT count(*) FROM fixture_source_witnesses').fetchone()[0]<256)
                    db.execute('INSERT INTO fixture_source_witnesses VALUES(?,?)',(request.sha256,encoded))
                else:_need(previous==(encoded,))
            return value
    except (ValueError,TypeError,KeyError,AttributeError,OSError):raise RuntimeRefused('FIXTURE_NATIVE_SOURCE_UNVERIFIED') from None
    finally:
        if type(start) is _SourceStart:start.close()
