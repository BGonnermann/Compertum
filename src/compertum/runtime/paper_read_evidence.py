"""Bounded encrypted historical read artifacts; no transport, grant or freshness."""
from contextlib import contextmanager,ExitStack
from dataclasses import dataclass
import hashlib,json,re
from compertum.data.encoding import canonical
from compertum.domain import ContractError
from compertum.paper_contracts import PAPER_ORIGIN,identifier,strict_json
from compertum.paper_read_preparation import PreparedReadPlan,PreparedReadRequest
from compertum.persistence import checked_path
from compertum.storage import owner_of_grant
from .errors import RuntimeRefused
from .owners import _MUTEX,_owner_scope,require_live_owner
from .paper_credentials import _alias,_crypt_bounded,_wipe,open_paper_credentials
from .paper_read_packet import _ReadPacket,_local_time
from .paper_credential_slot import _coordinator_records
from .paper_read_secrecy import _parse_read_reply,_reject_reflections,qualify_read_reply

_MAGIC=b'CPREAD01';_PLAIN_MAX=2*1024**2;_CIPHER_MAX=3*1024**2;_FACTORY=object()


def _need(value):
    if not value:raise RuntimeRefused('PAPER_EVIDENCE_INVALID')


def _context(project,alias,task,packet):
    _need(type(project) is str and re.fullmatch('[0-9a-f]{64}',project) is not None)
    _alias(alias);identifier(task);identifier(packet)
    return _MAGIC+b'\0'+project.encode()+b'\0'+PAPER_ORIGIN.encode()+b'\0'+alias.encode()+b'\0'+task.encode()+b'\0'+packet.encode()


def _crypt_evidence(buffer,entropy,*,decrypt):
    return _crypt_bounded(buffer,entropy,decrypt=decrypt,input_max=_CIPHER_MAX if decrypt else _PLAIN_MAX,
                          output_max=_PLAIN_MAX if decrypt else _CIPHER_MAX,error_prefix='PAPER_EVIDENCE')


def _path(task,packet):
    identifier(task);identifier(packet);return f'artifacts/runs/{task}/paper-read-{packet}.bin'


@dataclass(frozen=True,slots=True,repr=False,init=False)
class _ProtectedReadEvidence:
    project_id:str
    account_alias:str
    task_id:str
    packet_id:str
    ciphertext:bytes
    def __init__(self,project,alias,task,packet,ciphertext,*,_factory=None):
        _need(_factory is _FACTORY);_context(project,alias,task,packet)
        _need(type(ciphertext) is bytes and 0<len(ciphertext)<=_CIPHER_MAX)
        for k,v in zip(self.__slots__,(project,alias,task,packet,ciphertext)):object.__setattr__(self,k,v)
    def __repr__(self):return '<ProtectedPaperReadEvidence redacted>'
    def __reduce_ex__(self,protocol):raise RuntimeRefused('PAPER_READ_PRIVATE_SERIALIZATION_FORBIDDEN')


def _pack(frames,entropy):
    _need(5<=len(frames)<=41 and (len(frames)-2)%3==0)
    plain=bytearray(_MAGIC+hashlib.sha256(entropy).digest()+bytes(32)+len(frames).to_bytes(2,'big')+bytes(4))
    try:
        for i,frame in enumerate(frames):
            maximum=65536 if i==0 else 8192 if i==1 or (i-2)%3==0 else 65536
            _need(type(frame) is bytes and 0<len(frame)<=maximum)
            _need(len(plain)+4+len(frame)<=_PLAIN_MAX);plain.extend(len(frame).to_bytes(4,'big'));plain.extend(frame)
        h=hashlib.sha256(entropy);h.update(memoryview(plain)[72:]);plain[40:72]=h.digest();return plain
    except BaseException:_wipe(plain);raise


def _frames(plain,entropy,*,cipher_size=None):
    _need(type(plain) is bytearray and 78<=len(plain)<=_PLAIN_MAX)
    _need(plain[:8]==_MAGIC and plain[8:40]==hashlib.sha256(entropy).digest())
    h=hashlib.sha256(entropy);h.update(memoryview(plain)[72:]);_need(plain[40:72]==h.digest())
    if cipher_size is not None:_need(int.from_bytes(plain[74:78],'big')==cipher_size)
    count=int.from_bytes(plain[72:74],'big');_need(5<=count<=41 and (count-2)%3==0);at=78;frames=[]
    for i in range(count):
        _need(at+4<=len(plain));size=int.from_bytes(plain[at:at+4],'big');at+=4
        maximum=65536 if i==0 else 8192 if i==1 or (i-2)%3==0 else 65536
        _need(0<size<=maximum and at+size<=len(plain));frames.append(bytes(memoryview(plain)[at:at+size]));at+=size
    _need(at==len(plain));return frames


def _validate(frames,project,alias,task,packet):
    meta=strict_json(frames[0]);plan=PreparedReadPlan(frames[1]);p=plan.to_payload();count=(len(frames)-2)//3
    _need(type(meta) is dict and set(meta)=={'version','record_type','purpose','project_id','account_alias','task_id','packet_id','execution_generation','credential_sha256','plan_sha256','started_at','record_count','contexts','status'})
    _need(meta['version']==1 and type(meta['version']) is int and meta['record_type']=='PrivatePaperReadEvidence' and meta['purpose']=='HISTORICAL_ONLY')
    _need((meta['project_id'],meta['account_alias'],meta['task_id'],meta['packet_id'])==(project,alias,task,packet))
    _need(p['project_id']==project and p['account_alias']==alias and meta['plan_sha256']==plan.sha256)
    _need(type(meta['execution_generation']) is int and meta['execution_generation']>0 and meta['record_count']==count and type(meta['record_count']) is int)
    _need(type(meta['contexts']) is list and len(meta['contexts'])==count)
    records=[];ids=set();account=None;last=_local_time(meta['started_at']);ops=[];refs=[];order_pages=[];positions=0
    for i in range(count):
        context=meta['contexts'][i];_need(type(context) is dict and set(context)=={'expected_account_id','private_account_id'})
        request_raw,raw,parsed_raw=frames[2+3*i:5+3*i]
        request=PreparedReadRequest(plan,request_raw,context['expected_account_id'],meta['credential_sha256']);r=request.to_payload();parsed=strict_json(parsed_raw)
        _need(r['packet_started_at']==meta['started_at'] and _local_time(r['created_at'])>=last and r['request_id'] not in ids)
        ids.add(r['request_id']);_need(type(parsed) is dict and type(parsed.get('received_at')) is str)
        restored=_parse_read_reply(request,raw,parsed['received_at'],strict_json(raw));_need(restored.content==parsed_raw and restored.private_account_id==context['private_account_id'])
        if i==0:account=restored.private_account_id;_need(context['expected_account_id'] is None)
        else:_need(context['expected_account_id']==account and restored.private_account_id==account)
        last=_local_time(parsed['received_at']);op=r['operation'];ops.append(op)
        if i<4:_need(op==('ACCOUNT','CLOCK','CALENDAR','POSITIONS')[i])
        elif op=='CLOCK':_need(i==count-1 and order_pages and len(order_pages[-1])<25)
        else:
            _need(op=='ORDERS' and len(order_pages)<8 and (not order_pages or len(order_pages[-1])==25))
            cursor=order_pages[-1][-1]['id'] if order_pages else None;_need(r['parameters'].get('after_order_id')==cursor)
            order_pages.append(parsed['observation']['rows'])
        if op=='POSITIONS':positions=len(parsed['observation']['rows'])
        refs.append(dict(request_id=r['request_id'],request_sha256=request.sha256,raw_sha256=parsed['raw_sha256']))
        records.append(dict(request=r,raw=raw,parsed=parsed))
    status=meta['status'];_need(type(status) is dict and set(status)=={'version','record_type','scope','state','reason','account_alias','plan_sha256','attempts','responses','order_pages','positions','orders','orders_coverage','deficiencies','references','native_transport_verified','financial_accepted','actual_flat','account_identity'})
    _need(status['version']==1 and type(status['version']) is int and status['record_type']=='PaperReadPacketStatus' and status['scope']=='PREPARATION_ONLY')
    _need(status['account_alias']==alias and status['plan_sha256']==plan.sha256 and status['references']==refs)
    _need(status['native_transport_verified'] is False and status['financial_accepted'] is False and status['actual_flat'] is None and status['account_identity']=='DISCOVERED_UNCONFIRMED')
    _need(all(type(status[k]) is int for k in ('attempts','responses','order_pages','positions','orders')))
    _need(status['responses']==count and status['order_pages']==len(order_pages) and status['positions']==positions and status['orders']==sum(map(len,order_pages)))
    _need(type(status['deficiencies']) is list and all(type(x) is str and len(x)<=128 for x in status['deficiencies']))
    _need(status['orders_coverage'] in ('INCOMPLETE','OBSERVED_SHORT_TERMINAL_PAGE'))
    state=status['state'];reason=status['reason'];_need(state in ('PREPARATION_COMPLETE','INCOMPLETE','ABORTED'))
    _need(count<=status['attempts']<=min(13,count+(state=='ABORTED')))
    if state=='PREPARATION_COMPLETE':_need(count>=6 and ops[-1]=='CLOCK' and reason is None and status['orders_coverage']=='OBSERVED_SHORT_TERMINAL_PAGE')
    elif state=='INCOMPLETE':
        _need((reason=='INITIAL_CLOCK_INVALID' and count==2) or (reason=='FINAL_CLOCK_INVALID' and count>=6 and ops[-1]=='CLOCK') or (reason in ('ORDER_COVERAGE_INVALID','ORDER_PAGE_LIMIT') and count>=5 and ops[-1]=='ORDERS'))
        if reason=='ORDER_PAGE_LIMIT':_need(len(order_pages)==8 and len(order_pages[-1])==25)
    else:_need(reason in ('PRIVATE_CONTEXT_CHANGED','PACKET_DEADLINE','DISPATCH_CONTEXT_INVALID','READ_ATTEMPT_FAILED','REPLY_INVALID'))
    return dict(metadata=meta,plan=p,records=records)


def protect_read_evidence(lease,packet,*,task_id,packet_id):
    plain=bytearray();encrypted=bytearray()
    try:
        with _owner_scope(lease) as state:
            require_live_owner(lease,'execution')
            _need(type(packet) is _ReadPacket and packet._lease is lease and not packet._closed)
            packet._context();status=packet.status();_need(status['state'] in ('PREPARATION_COMPLETE','INCOMPLETE','ABORTED'))
            records=packet.private_evidence();_need(1<=len(records)<=13)
            alias=packet._alias;entropy=_context(state.project.project_id,alias,task_id,packet_id)
            meta=dict(version=1,record_type='PrivatePaperReadEvidence',purpose='HISTORICAL_ONLY',project_id=state.project.project_id,account_alias=alias,
                task_id=task_id,packet_id=packet_id,execution_generation=lease.generation,credential_sha256=packet._credential_sha,plan_sha256=packet._plan_sha,
                started_at=packet._started_at,record_count=len(records),contexts=[dict(expected_account_id=r.request.expected_account_id,private_account_id=r.private_account_id) for r in records],status=status)
            frames=[canonical(meta),packet._plan.content]
            with open_paper_credentials(lease,packet._protected) as opened:
                values=tuple(opened.headers().values())
                _reject_reflections(canonical(dict(metadata=meta,path=_path(task_id,packet_id))),values)
                _reject_reflections(packet._plan.content,values)
                for r in records:
                    _reject_reflections(r.request.content,values)
                    verified=qualify_read_reply(lease,packet._protected,r.request,r.raw,received_at=r.to_payload()['received_at'])
                    _need(verified.content==r.content and verified.private_account_id==r.private_account_id)
                    frames.extend((r.request.content,r.raw,r.content))
            _validate(frames,state.project.project_id,alias,task_id,packet_id)
            plain=_pack(frames,entropy);encrypted=_crypt_evidence(plain,entropy,decrypt=False)
            # DPAPI accepts trailing ciphertext. Bind the complete native length
            # inside authenticated plaintext; a fixed-size second seal verifies it.
            size=len(encrypted);_wipe(encrypted);plain[74:78]=size.to_bytes(4,'big')
            h=hashlib.sha256(entropy);h.update(memoryview(plain)[72:]);plain[40:72]=h.digest()
            encrypted=_crypt_evidence(plain,entropy,decrypt=False);_need(len(encrypted)==size)
            return _ProtectedReadEvidence(state.project.project_id,alias,task_id,packet_id,bytes(encrypted),_factory=_FACTORY)
    except (ContractError,ValueError,TypeError,KeyError,UnicodeError,RecursionError,OSError):raise RuntimeRefused('PAPER_EVIDENCE_INVALID') from None
    finally:_wipe(plain);_wipe(encrypted)


def _manifest(value,task,packet):
    _need(type(value) is dict and set(value)=={'artifact_id','path','size_bytes','sha256','task_id'})
    identifier(value['artifact_id']);_need(value['task_id']==task and value['path']==_path(task,packet))
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


def publish_read_evidence(manager,grant,protected):
    writer=None
    try:
        with manager.store._live() as guard:
            _need(type(protected) is _ProtectedReadEvidence and owner_of_grant(grant) is manager)
            _need(protected.project_id==manager.lease.project_id and grant.task_id==protected.task_id and grant.category=='records' and grant.maximum==len(protected.ciphertext))
            _context(protected.project_id,protected.account_alias,protected.task_id,protected.packet_id)
            _need(0<len(protected.ciphertext)<=_CIPHER_MAX)
            relative=_path(grant.task_id,protected.packet_id);path=checked_path(manager.root,manager.root/relative)
            row=manager.store.conn.execute('SELECT status,path,manifest FROM reservations WHERE id=?',(grant.grant_id,)).fetchone();_need(row is not None)
            if path.parent.exists():
                with _pinned(guard,path):
                    if path.exists():
                        _need(row[:2]==('PUBLISHED',relative));manifest=strict_json(row[2].encode());_manifest(manifest,grant.task_id,protected.packet_id)
                        raw=guard.api.read_regular(path,maximum=_CIPHER_MAX)
                        _need(raw==protected.ciphertext and len(raw)==manifest['size_bytes'] and hashlib.sha256(raw).hexdigest()==manifest['sha256']);return manifest
            _need(row[0]=='RESERVED');writer=manager.open_artifact(grant,relative)
            writer.write(protected.ciphertext);manifest=writer.publish();_manifest(manifest,grant.task_id,protected.packet_id)
            with _pinned(guard,path):_need(guard.api.read_regular(path,maximum=_CIPHER_MAX)==protected.ciphertext)
            return manifest
    except (ContractError,ValueError,TypeError,KeyError,UnicodeError,RecursionError,OSError):raise RuntimeRefused('PAPER_EVIDENCE_INVALID') from None
    finally:
        if writer is not None:writer.close()


class _OpenedReadEvidence:
    __slots__=('_lease','_buffer','_context','_identity','_closed')
    def __init__(self,lease,buffer,entropy,identity):self._lease=lease;self._buffer=buffer;self._context=entropy;self._identity=identity;self._closed=False
    def __repr__(self):return '<HistoricalPaperReadEvidence private data redacted>'
    def __reduce_ex__(self,protocol):raise RuntimeRefused('PAPER_READ_PRIVATE_SERIALIZATION_FORBIDDEN')
    def snapshot(self):
        with _owner_scope(self._lease):
            require_live_owner(self._lease,'execution');_need(not self._closed)
            return _validate(_frames(self._buffer,self._context),*self._identity)
    def close(self):
        with _MUTEX:self._closed=True;_wipe(self._buffer)


@contextmanager
def open_read_evidence(lease,account_alias,packet_id,manifest):
    private=None;state=None;plain=bytearray()
    try:
        try:
            with _owner_scope(lease) as state:
                require_live_owner(lease,'execution');_need(type(manifest) is dict)
                task=manifest.get('task_id');entropy=_context(state.project.project_id,account_alias,task,packet_id);_manifest(manifest,task,packet_id)
                # Only the exact durable publication can supply historical provenance.
                manifest=strict_json(canonical(manifest))
                with _coordinator_records(state) as conn:
                    rows=conn.execute('SELECT task,category,status,written,manifest FROM reservations WHERE path=? LIMIT 2',(manifest['path'],)).fetchall()
                    _need(rows==[(task,'records','PUBLISHED',manifest['size_bytes'],canonical(manifest).decode())])
                path=checked_path(state.project.root_path,state.project.root_path/manifest['path'])
                with _pinned(state,path):raw=state.api.read_regular(path,maximum=_CIPHER_MAX)
                _need(len(raw)==manifest['size_bytes'] and hashlib.sha256(raw).hexdigest()==manifest['sha256'])
                plain=_crypt_evidence(bytearray(raw),entropy,decrypt=True);identity=(state.project.project_id,account_alias,task,packet_id)
                _validate(_frames(plain,entropy,cipher_size=len(raw)),*identity)
                private=_OpenedReadEvidence(lease,plain,entropy,identity);state.resources.append(private)
        except (ContractError,ValueError,TypeError,KeyError,UnicodeError,RecursionError,OSError):raise RuntimeRefused('PAPER_EVIDENCE_INVALID') from None
        yield private
    finally:
        with _MUTEX:
            if private is not None:
                private.close()
                if private in state.resources:state.resources.remove(private)
            else:_wipe(plain)
