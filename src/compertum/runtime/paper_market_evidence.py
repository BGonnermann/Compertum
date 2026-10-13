"""Purpose-bound encrypted historical operational data; no renewed authority."""
from contextlib import contextmanager,ExitStack
from dataclasses import dataclass
import hashlib,json,re
from compertum.data.encoding import canonical
from compertum.domain import ContractError
from compertum.paper_contracts import identifier,strict_json
from compertum.paper_market_inputs import OperationalMarketPlan,OperationalMarketRequest,MarketObservation,qualify_market_inputs,_body,_ns,_day,_sha,_token
from compertum.paper_action_inputs import prepare_action_query,CurrentActionPage,qualify_action_inputs
from compertum.persistence import checked_path
from compertum.storage import owner_of_grant
from .errors import RuntimeRefused
from .owners import _MUTEX,_owner_scope,require_live_owner
from .paper_credentials import _alias,_crypt_bounded,_wipe,open_paper_credentials
from .paper_credential_slot import _coordinator_records
from .paper_market_collection import _PrivateCollectionSnapshot,_scan_generated

_MAGIC=b'CPOMKT01';_SNAPSHOT_MAX=2*1024**2;_PLAIN_MAX=_SNAPSHOT_MAX+16384;_CIPHER_MAX=3*1024**2;_FACTORY=object()
_ORIGIN='https://data.alpaca.markets'

def _need(value,code='MARKET_EVIDENCE_INVALID'):
    if not value:raise RuntimeRefused(code)

def _context(project,alias,task,collection):
    _need(type(project) is str and re.fullmatch('[0-9a-f]{64}',project) is not None)
    _alias(alias);identifier(task);identifier(collection)
    return b'\0'.join((_MAGIC,b'OPERATIONAL_ONLY',_ORIGIN.encode(),project.encode(),alias.encode(),task.encode(),collection.encode()))

def _crypt_evidence(buffer,entropy,*,decrypt):
    return _crypt_bounded(buffer,entropy,decrypt=decrypt,input_max=_CIPHER_MAX if decrypt else _PLAIN_MAX,
                          output_max=_PLAIN_MAX if decrypt else _CIPHER_MAX,error_prefix='MARKET_EVIDENCE')

def _path(task,collection):
    identifier(task);identifier(collection);return f'artifacts/runs/{task}/market-collection-{collection}.bin'

@dataclass(frozen=True,slots=True,repr=False,init=False)
class _ProtectedMarketEvidence:
    project_id:str
    account_alias:str
    task_id:str
    collection_id:str
    ciphertext:bytes
    _binding_sha256:str
    def __init__(self,project,alias,task,collection,ciphertext,*,_factory=None):
        _need(_factory is _FACTORY);_context(project,alias,task,collection)
        _need(type(ciphertext) is bytes and 0<len(ciphertext)<=_CIPHER_MAX)
        for k,v in zip(self.__slots__,(project,alias,task,collection,ciphertext)):object.__setattr__(self,k,v)
        object.__setattr__(self,'_binding_sha256',self._binding())
    def _binding(self):
        _need(type(self.ciphertext) is bytes and 0<len(self.ciphertext)<=_CIPHER_MAX)
        return _sha(_context(self.project_id,self.account_alias,self.task_id,self.collection_id)+hashlib.sha256(self.ciphertext).digest())
    def _verify(self):_need(self._binding()==self._binding_sha256)
    def __repr__(self):return '<ProtectedOperationalEvidence redacted>'
    def __reduce_ex__(self,protocol):raise RuntimeRefused('MARKET_EVIDENCE_SERIALIZATION_FORBIDDEN')

def _pack(frames,entropy):
    _need(type(frames) is list and len(frames)==2)
    plain=bytearray(_MAGIC+hashlib.sha256(entropy).digest()+bytes(32)+bytes(4))
    try:
        for frame,maximum in zip(frames,(8192,_SNAPSHOT_MAX)):
            _need(type(frame) is bytes and 0<len(frame)<=maximum)
            _need(len(plain)+4+len(frame)<=_PLAIN_MAX);plain.extend(len(frame).to_bytes(4,'big'));plain.extend(frame)
        h=hashlib.sha256(entropy);h.update(memoryview(plain)[72:]);plain[40:72]=h.digest();return plain
    except BaseException:_wipe(plain);raise

def _frames(plain,entropy,*,cipher_size=None):
    _need(type(plain) is bytearray and 84<=len(plain)<=_PLAIN_MAX)
    _need(plain[:8]==_MAGIC and plain[8:40]==hashlib.sha256(entropy).digest())
    h=hashlib.sha256(entropy);h.update(memoryview(plain)[72:]);_need(plain[40:72]==h.digest())
    if cipher_size is not None:_need(int.from_bytes(plain[72:76],'big')==cipher_size)
    at=76;frames=[]
    for maximum in (8192,_SNAPSHOT_MAX):
        _need(at+4<=len(plain));size=int.from_bytes(plain[at:at+4],'big');at+=4
        _need(0<size<=maximum and at+size<=len(plain));frames.append(bytes(memoryview(plain)[at:at+size]));at+=size
    _need(at==len(plain));return frames

def _snapshot(raw):
    _need(type(raw) is bytes and 0<len(raw)<=_SNAPSHOT_MAX)
    # Only the producer's canonical representation is accepted, including key uniqueness.
    v=json.loads(raw);_need(canonical(v)==raw);pending=[(v,0)];count=0
    while pending:
        item,level=pending.pop();count+=1;_need(level<=40 and count<=100000)
        if type(item) is dict:pending.extend((x,level+1) for x in item.values())
        elif type(item) is list:pending.extend((x,level+1) for x in item)
    return v

def _cursor(raw,mode,symbol):
    b=_body(raw);_need('next_page_token' in b)
    if mode=='HISTORY':
        groups=b.get('bars');_need(type(groups) is dict and set(groups)<={symbol})
        rows=groups.get(symbol,[]);_need(type(rows) is list and len(rows)<=100)
    else:
        groups=b.get('corporate_actions');_need(type(groups) is dict and all(type(x) is list for x in groups.values()))
        _need(sum(map(len,groups.values()))<=100)
    return _token(b['next_page_token'])

def _validate(frames,project,alias,task,collection):
    _context(project,alias,task,collection);_need(type(frames) is list and len(frames)==2)
    meta=strict_json(frames[0]);v=_snapshot(frames[1])
    _need(type(meta) is dict and set(meta)=={'version','record_type','purpose','project_id','account_alias','task_id','collection_id','execution_generation','credential_sha256','snapshot_sha256'})
    _need(type(meta['version']) is int and meta['version']==1 and meta['record_type']=='PrivateMarketEvidence' and meta['purpose']=='OPERATIONAL_ONLY')
    _need((meta['project_id'],meta['account_alias'],meta['task_id'],meta['collection_id'])==(project,alias,task,collection))
    _need(type(meta['execution_generation']) is int and meta['execution_generation']>0 and meta['snapshot_sha256']==_sha(frames[1]))
    _need(type(meta['credential_sha256']) is str and re.fullmatch('[0-9a-f]{64}',meta['credential_sha256']) is not None)
    _need(type(v) is dict and set(v)=={'version','record_type','purpose','collection_id','mode','plan','started_at','validated_at','state','reason','attempts','records','aggregate','aggregate_error','complete_by_cutoff','native_provenance','clock_basis','research_eligible','financial_accepted','transport_authorized'})
    _need(type(v['version']) is int and v['version']==1 and v['record_type']=='PrivateOperationalCollection' and v['purpose']=='OPERATIONAL_ONLY' and v['collection_id']==collection)
    _need(all(v[k] is False for k in ('research_eligible','financial_accepted','transport_authorized')))
    _need(v['mode'] in ('HISTORY','CURRENT_ACTIONS') and v['clock_basis'] in ('LOCAL_CLOCK','SYNTHETIC_FIXTURE'))
    plan=OperationalMarketPlan(canonical(v['plan']));p=plan.to_payload();_need((p['project_id'],p['account_alias'])==(project,alias))
    start=_ns(v['started_at']);cutoff=_ns(p['history_cutoff_at']);last=start;last_valid=v['started_at']
    _need(_day(v['started_at'])==p['session_date'] and _ns(p['created_at'])<=start<cutoff)
    rows=v['records'];_need(type(rows) is list and len(rows)<=8);n=len(rows)
    _need(type(v['attempts']) is int and n<=v['attempts']<=min(8,n+1))
    _need(len(canonical(dict(plan=p,records=rows)))<=1048576)
    ids=set();tokens=set();cursor=None;observations=[];provenances=set();valid_pages=[]
    for i,r in enumerate(rows):
        _need(type(r) is dict and set(r)=={'request','body_utf8','diagnostic','validated_at','dispatched_at'})
        request=r['request'];d=r['diagnostic'];_need(type(request) is dict and type(d) is dict and type(r['body_utf8']) is str)
        raw=r['body_utf8'].encode('utf-8');request_raw=canonical(request);_need(len(request_raw)<=65536)
        rid=request['request_id'];identifier(rid);_need(rid not in ids);ids.add(rid)
        at=request.get('created_at',request.get('requested_at'));received=d['received_at'];sent=r['dispatched_at']
        _need(last<=_ns(at)<=_ns(sent)<cutoff and _ns(sent)<=_ns(received))
        _need(_day(sent)==p['session_date'] and request['parameters'].get('page_token')==cursor)
        if v['mode']=='HISTORY':
            req=OperationalMarketRequest(plan,request_raw);_need(request['operation']=='HISTORY');o=MarketObservation(req,raw,d['status'],received)
        else:
            o=CurrentActionPage(prepare_action_query(plan),rid,cursor,at,received,d['status'],raw);_need(canonical(o.request_payload())==request_raw)
        observations.append(o)
        provenance=d['transport_provenance'];_need(provenance in ('DATA_TLS','LOOPBACK_FIXTURE'));provenances.add(provenance)
        expected=dict(version=1,record_type='PrivateMarketReply',scope='PREPARATION_ONLY',request_sha256=_sha(request_raw),plan_sha256=plan.sha256,request_id=rid,
            operation=v['mode'],status=d['status'],received_at=received,age_ns=_ns(received)-_ns(at),raw_bytes=len(raw),raw_sha256=_sha(raw),transport_provenance=provenance,
            credential_dispatch_binding='PINNED_ENVELOPE' if provenance=='DATA_TLS' else 'NOT_SENT_FIXTURE',outcome='HTTP_RESPONSE_OBSERVED' if d['status']==200 else 'HTTP_REFUSED',
            semantic_qualification='NOT_PERFORMED',timestamps='DECLARED',transport_authorized=False,financial_accepted=False,research_eligible=False,entitlement='UNVERIFIED',coverage='UNVERIFIED')
        _need(canonical(d)==canonical(expected))
        validated=r['validated_at']
        if validated is None:_need(i==n-1 and v['state']=='INCOMPLETE' and v['reason']=='REPLY_REFUSED');last=_ns(received)
        else:
            _need(_day(validated)==p['session_date'] and _ns(received)<=_ns(validated));last=_ns(validated);last_valid=validated
        page_valid=False;next_cursor=None
        if d['status']==200:
            try:
                next_cursor=_cursor(raw,v['mode'],p['symbol']);_need(next_cursor is None or next_cursor not in tokens);page_valid=True
            except (ContractError,RuntimeRefused):pass
        valid_pages.append(page_valid)
        if i<n-1:
            _need(page_valid and next_cursor is not None and validated is not None and _ns(validated)<=cutoff)
            tokens.add(next_cursor);cursor=next_cursor
    _need(v['validated_at']==last_valid)
    provenance=next(iter(provenances)) if len(provenances)==1 else 'UNVERIFIED';_need(v['native_provenance']==provenance)
    if n:_need(len(provenances)==1 and (provenance=='LOOPBACK_FIXTURE')==(v['clock_basis']=='SYNTHETIC_FIXTURE'))
    if v['aggregate'] is not None:
        _need(n>0 and v['aggregate_error'] is None)
        result=qualify_market_inputs(plan,tuple(observations),as_of=rows[-1]['diagnostic']['received_at']) if v['mode']=='HISTORY' else qualify_action_inputs(prepare_action_query(plan),tuple(observations),as_of=rows[-1]['diagnostic']['received_at'])
        _need(result.content==canonical(v['aggregate']))
    else:_need(v['aggregate_error']==('AGGREGATE_UNVERIFIED' if n else None))
    if v['state']=='PAGINATION_COMPLETE':
        _need(n>0 and v['reason'] is None and v['attempts']==n and all(valid_pages) and next_cursor is None and all(r['validated_at'] is not None for r in rows))
        _need(_ns(last_valid)<=cutoff and v['complete_by_cutoff'] is True and v['aggregate'] is not None)
    else:
        _need(v['state']=='INCOMPLETE' and v['complete_by_cutoff'] is False)
        _need(v['reason'] in ('DISPATCH_FAILED','TOTAL_DEADLINE','INFORMATION_CUTOFF','HTTP_REFUSED','PAGE_INVALID','PAGE_LIMIT','REPLY_REFUSED','CANCELLED'))
        if v['reason']=='HTTP_REFUSED':_need(n>0 and rows[-1]['diagnostic']['status']!=200)
        elif v['reason']=='PAGE_INVALID':_need(n>0 and (not valid_pages[-1] or v['aggregate'] is None))
        elif v['reason']=='PAGE_LIMIT':_need(n==8 and all(valid_pages) and next_cursor is not None)
        elif v['reason']=='INFORMATION_CUTOFF':_need(n>0 and _ns(last_valid)>cutoff)
        if n==0:_need(v['reason'] in ('CANCELLED','DISPATCH_FAILED','TOTAL_DEADLINE','REPLY_REFUSED'))
    return dict(metadata=meta,collection=v,use='HISTORICAL_ONLY',purpose='OPERATIONAL_ONLY',freshness='NOT_RESTORED',
                provenance='HISTORICAL_PRODUCER_ASSERTION',transport_authorized=False,financial_accepted=False,research_eligible=False)

def protect_market_evidence(lease,snapshot,*,task_id):
    plain=bytearray();encrypted=bytearray()
    try:
        with _owner_scope(lease) as state:
            require_live_owner(lease,'execution');_need(type(snapshot) is _PrivateCollectionSnapshot and snapshot._collection._lease is lease)
            c=snapshot._collection;content=snapshot.content;_need(c.private_snapshot() is snapshot)
            alias=c._protected.account_alias;cid=c._collection_id;entropy=_context(state.project.project_id,alias,task_id,cid)
            meta=dict(version=1,record_type='PrivateMarketEvidence',purpose='OPERATIONAL_ONLY',project_id=state.project.project_id,account_alias=alias,
                      task_id=task_id,collection_id=cid,execution_generation=lease.generation,credential_sha256=c._credential_sha,snapshot_sha256=_sha(content))
            frames=[canonical(meta),content];_validate(frames,state.project.project_id,alias,task_id,cid)
            with open_paper_credentials(lease,c._protected) as opened:
                values=tuple(opened.headers().values());_scan_generated(dict(metadata=meta,path=_path(task_id,cid)),values);_scan_generated(json.loads(content),values)
            plain=_pack(frames,entropy);encrypted=_crypt_evidence(plain,entropy,decrypt=False)
            size=len(encrypted);_wipe(encrypted);plain[72:76]=size.to_bytes(4,'big')
            h=hashlib.sha256(entropy);h.update(memoryview(plain)[72:]);plain[40:72]=h.digest()
            encrypted=_crypt_evidence(plain,entropy,decrypt=False);_need(len(encrypted)==size)
            return _ProtectedMarketEvidence(state.project.project_id,alias,task_id,cid,bytes(encrypted),_factory=_FACTORY)
    except (ContractError,ValueError,TypeError,KeyError,UnicodeError,RecursionError,AttributeError,OSError):raise RuntimeRefused('MARKET_EVIDENCE_INVALID') from None
    finally:_wipe(plain);_wipe(encrypted)


def _manifest(value,task,collection):
    _need(type(value) is dict and set(value)=={'artifact_id','path','size_bytes','sha256','task_id'})
    identifier(value['artifact_id']);_need(value['task_id']==task and value['path']==_path(task,collection))
    _need(type(value['size_bytes']) is int and 0<value['size_bytes']<=_CIPHER_MAX)
    _need(type(value['sha256']) is str and re.fullmatch('[0-9a-f]{64}',value['sha256']) is not None)


@contextmanager
def _pinned(guard,path):
    with ExitStack() as pins:
        current=guard.project.root_path
        for part in path.parent.relative_to(current).parts:
            current=current/part;pins.enter_context(guard.api.open_directory(current))
        _need(next(path.parent.glob(path.name+'.partial-*'),None) is None)
        yield


def publish_market_evidence(manager,grant,protected):
    writer=None
    try:
        with manager.store._live() as guard:
            _need(type(protected) is _ProtectedMarketEvidence and owner_of_grant(grant) is manager)
            project,alias,task,cid,ciphertext=protected.project_id,protected.account_alias,protected.task_id,protected.collection_id,protected.ciphertext
            _need(type(ciphertext) is bytes and 0<len(ciphertext)<=_CIPHER_MAX)
            _need(_sha(_context(project,alias,task,cid)+hashlib.sha256(ciphertext).digest())==protected._binding_sha256)
            _need(project==manager.lease.project_id and grant.task_id==task and grant.category=='records' and grant.maximum==len(ciphertext))
            _context(project,alias,task,cid)
            _need(0<len(ciphertext)<=_CIPHER_MAX)
            relative=_path(grant.task_id,cid);path=checked_path(manager.root,manager.root/relative)
            row=manager.store.conn.execute('SELECT status,path,manifest FROM reservations WHERE id=?',(grant.grant_id,)).fetchone();_need(row is not None)
            if path.parent.exists():
                with _pinned(guard,path):
                    if path.exists():
                        _need(row[:2]==('PUBLISHED',relative));manifest=strict_json(row[2].encode());_manifest(manifest,grant.task_id,cid)
                        raw=guard.api.read_regular(path,maximum=_CIPHER_MAX)
                        _need(raw==ciphertext and len(raw)==manifest['size_bytes'] and hashlib.sha256(raw).hexdigest()==manifest['sha256']);return manifest
            _need(row[0]=='RESERVED');writer=manager.open_artifact(grant,relative)
            writer.write(ciphertext);manifest=writer.publish();_manifest(manifest,grant.task_id,cid)
            with _pinned(guard,path):_need(guard.api.read_regular(path,maximum=_CIPHER_MAX)==ciphertext)
            return manifest
    except (ContractError,ValueError,TypeError,KeyError,UnicodeError,RecursionError,OSError):raise RuntimeRefused('MARKET_EVIDENCE_INVALID') from None
    finally:
        if writer is not None:writer.close()


class _OpenedMarketEvidence:
    __slots__=('_lease','_buffer','_context','_identity','_closed','_state')
    def __init__(self,lease,buffer,entropy,identity,state):self._lease=lease;self._buffer=buffer;self._context=entropy;self._identity=identity;self._closed=False;self._state=state
    def __repr__(self):return '<HistoricalOperationalEvidence private data redacted>'
    def __reduce_ex__(self,protocol):raise RuntimeRefused('MARKET_EVIDENCE_SERIALIZATION_FORBIDDEN')
    def snapshot(self):
        with _owner_scope(self._lease):
            require_live_owner(self._lease,'execution');_need(not self._closed)
            return _validate(_frames(self._buffer,self._context),*self._identity)
    def close(self):
        with _MUTEX:
            self._closed=True;_wipe(self._buffer)
            if self in self._state.resources:self._state.resources.remove(self)


@contextmanager
def open_market_evidence(lease,account_alias,collection_id,manifest):
    private=None;state=None;plain=bytearray()
    try:
        try:
            with _owner_scope(lease) as state:
                require_live_owner(lease,'execution');_need(type(manifest) is dict)
                _need(not any(type(r) is _OpenedMarketEvidence and not r._closed for r in state.resources),'MARKET_EVIDENCE_CAPACITY')
                task=manifest.get('task_id');entropy=_context(state.project.project_id,account_alias,task,collection_id);_manifest(manifest,task,collection_id)
                # Only the exact durable publication can supply historical provenance.
                manifest=strict_json(canonical(manifest))
                with _coordinator_records(state) as conn:
                    rows=conn.execute('SELECT task,category,status,written,manifest FROM reservations WHERE path=? LIMIT 2',(manifest['path'],)).fetchall()
                    _need(rows==[(task,'records','PUBLISHED',manifest['size_bytes'],canonical(manifest).decode())])
                path=checked_path(state.project.root_path,state.project.root_path/manifest['path'])
                with _pinned(state,path):raw=state.api.read_regular(path,maximum=_CIPHER_MAX)
                _need(len(raw)==manifest['size_bytes'] and hashlib.sha256(raw).hexdigest()==manifest['sha256'])
                plain=_crypt_evidence(bytearray(raw),entropy,decrypt=True);identity=(state.project.project_id,account_alias,task,collection_id)
                _validate(_frames(plain,entropy,cipher_size=len(raw)),*identity)
                private=_OpenedMarketEvidence(lease,plain,entropy,identity,state);state.resources.append(private)
        except (ContractError,ValueError,TypeError,KeyError,UnicodeError,RecursionError,OSError):raise RuntimeRefused('MARKET_EVIDENCE_INVALID') from None
        yield private
    finally:
        with _MUTEX:
            if private is not None:
                private.close()
                if private in state.resources:state.resources.remove(private)
            else:_wipe(plain)
