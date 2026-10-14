"""Purpose-separated encrypted owner lineage; reopening grants no authority."""
from contextlib import contextmanager,ExitStack
from dataclasses import dataclass
import hashlib,json,re
from compertum.data.encoding import canonical
from compertum.domain import ContractError
from compertum.paper_contracts import identifier,strict_json
from compertum.paper_market_inputs import _sha
from compertum.persistence import checked_path
from compertum.storage import owner_of_grant
from .errors import RuntimeRefused
from .owners import _MUTEX,_owner_scope,require_live_owner
from .paper_credentials import _alias,_crypt_bounded,_wipe,open_paper_credentials
from .paper_credential_slot import _coordinator_records
from .paper_market_collection import _scan_generated
from .paper_market_evidence import _pinned,open_market_evidence,_OpenedMarketEvidence,_manifest as history_manifest
from .paper_market_lineage_owner import _OwnerMarketLineage,validate_owner_lineage,_MAX as _CONTENT_MAX

_MAGIC=b'CPMLIN01';_PLAIN_MAX=_CONTENT_MAX+16384;_CIPHER_MAX=3*1024**2;_FACTORY=object()
_INVALID=(ContractError,ValueError,TypeError,KeyError,AttributeError,UnicodeError,RecursionError,OverflowError,OSError)


def _need(value):
    if not value:raise RuntimeRefused('MARKET_LINEAGE_EVIDENCE_INVALID')


def _context(project,alias,task,capture):
    _need(type(project) is str and re.fullmatch('[0-9a-f]{64}',project) is not None)
    _alias(alias);identifier(task);identifier(capture)
    return b'\0'.join((_MAGIC,b'OPERATIONAL_ONLY',project.encode(),alias.encode(),task.encode(),capture.encode()))


def _path(task,capture):
    identifier(task);identifier(capture);return f'artifacts/runs/{task}/market-lineage-{capture}.bin'


def _crypt(buffer,entropy,*,decrypt):
    return _crypt_bounded(buffer,entropy,decrypt=decrypt,input_max=_CIPHER_MAX if decrypt else _PLAIN_MAX,
                          output_max=_PLAIN_MAX if decrypt else _CIPHER_MAX,error_prefix='MARKET_LINEAGE_EVIDENCE')


def _pack(frames,entropy):
    _need(type(frames) is list and len(frames)==2)
    plain=bytearray(_MAGIC+hashlib.sha256(entropy).digest()+bytes(36))
    try:
        for frame,maximum in zip(frames,(8192,_CONTENT_MAX)):
            _need(type(frame) is bytes and 0<len(frame)<=maximum)
            _need(len(plain)+4+len(frame)<=_PLAIN_MAX);plain.extend(len(frame).to_bytes(4,'big'));plain.extend(frame)
        _digest(plain,entropy);return plain
    except BaseException:_wipe(plain);raise


def _digest(plain,entropy):
    h=hashlib.sha256(entropy);h.update(memoryview(plain)[72:]);plain[40:72]=h.digest()


def _frames(plain,entropy,*,cipher_size):
    _need(type(plain) is bytearray and 84<=len(plain)<=_PLAIN_MAX)
    _need(plain[:8]==_MAGIC and plain[8:40]==hashlib.sha256(entropy).digest())
    h=hashlib.sha256(entropy);h.update(memoryview(plain)[72:]);_need(plain[40:72]==h.digest())
    _need(int.from_bytes(plain[72:76],'big')==cipher_size)
    at=76;frames=[]
    for maximum in (8192,_CONTENT_MAX):
        _need(at+4<=len(plain));size=int.from_bytes(plain[at:at+4],'big');at+=4
        _need(0<size<=maximum and at+size<=len(plain));frames.append(bytes(memoryview(plain)[at:at+size]));at+=size
    _need(at==len(plain));return frames


def _originals(owner,content):
    _need(type(content) is bytes and 0<len(content)<=_CONTENT_MAX and not owner.db.in_transaction)
    v=json.loads(content);_need(canonical(v)==content);inner=v['lineage'];proofs=v['consumption'];records=[]
    for mode in ('fresh','history'):
        grant=inner[mode+'_grant'];record=owner.records.read(grant['job_id'])
        _need(canonical(record['grant'])==canonical(grant) and record['grant_sha256']==inner[mode+'_grant_sha256'])
        _need(record['consumed'] and canonical(owner.consumptions.read(grant['job_id']))==canonical(proofs[mode]));records.append(record)
    fresh,prior=records;g=fresh['grant'];h=prior['grant']
    _need(g['project_id']==owner.lease.project_id and g['mode']=='FRESH' and h['mode']=='HISTORY')
    _need(fresh['state'] in {'COMPLETE','INTERRUPTED','CANCELED'} and fresh['summary'] is not None and fresh['summary']['state']=='PAIR_COMPLETE')
    _need(prior['state']=='PUBLISHED' and prior['manifest']==inner['history']['manifest']==g['history']['manifest'])
    _need(owner._history(g['subject_key'],g['account_alias'],g['plan']['symbol'],g['history'],g['credential_sha256'])==prior)
    return v,records


def _metadata(owner,content,task,capture):
    value,records=_originals(owner,content);g=records[0]['grant']
    return dict(version=1,record_type='PrivateMarketLineageEvidence',purpose='OPERATIONAL_ONLY',project_id=g['project_id'],account_alias=g['account_alias'],
                task_id=task,capture_id=capture,fresh_job_id=g['job_id'],fresh_grant_sha256=records[0]['grant_sha256'],
                execution_instance=g['owner_instance'],execution_generation=g['owner_generation'],lineage_sha256=_sha(content)),value,records


def _manifest(value,task,capture):
    _need(type(value) is dict and set(value)=={'artifact_id','path','size_bytes','sha256','task_id'})
    identifier(value['artifact_id']);_need(value['task_id']==task and value['path']==_path(task,capture))
    _need(type(value['size_bytes']) is int and 0<value['size_bytes']<=_CIPHER_MAX)
    _need(type(value['sha256']) is str and re.fullmatch('[0-9a-f]{64}',value['sha256']) is not None)


def _published(state,manifest):
    with _coordinator_records(state) as db:
        rows=db.execute('SELECT task,category,status,written,manifest FROM reservations WHERE path=? LIMIT 2',(manifest['path'],)).fetchall()
        _need(rows==[(manifest['task_id'],'records','PUBLISHED',manifest['size_bytes'],canonical(manifest).decode())])
    path=checked_path(state.project.root_path,state.project.root_path/manifest['path'])
    with _pinned(state,path):raw=state.api.read_regular(path,maximum=_CIPHER_MAX)
    _need(len(raw)==manifest['size_bytes'] and _sha(raw)==manifest['sha256']);return raw


def _history(owner,state,record,opened):
    g=record['grant'];manifest=record['manifest'];history_manifest(manifest,g['task_id'],g['job_id']);_published(state,manifest)
    _need(type(opened) is _OpenedMarketEvidence and opened._lease is owner.lease and opened._state is state)
    _need(not opened._closed and opened in state.resources and opened.publication()==manifest)
    return opened.snapshot()


@dataclass(frozen=True,slots=True,repr=False,init=False)
class _ProtectedMarketLineage:
    project_id:str
    account_alias:str
    task_id:str
    capture_id:str
    ciphertext:bytes
    _binding_sha256:str
    def __init__(self,project,alias,task,capture,ciphertext,*,_factory=None):
        _need(_factory is _FACTORY);_context(project,alias,task,capture)
        _need(type(ciphertext) is bytes and 0<len(ciphertext)<=_CIPHER_MAX)
        for k,v in zip(self.__slots__,(project,alias,task,capture,ciphertext)):object.__setattr__(self,k,v)
        object.__setattr__(self,'_binding_sha256',self._binding())
    def _binding(self):
        _need(type(self.ciphertext) is bytes and 0<len(self.ciphertext)<=_CIPHER_MAX)
        return _sha(_context(self.project_id,self.account_alias,self.task_id,self.capture_id)+hashlib.sha256(self.ciphertext).digest())
    def _verify(self):_need(self._binding()==self._binding_sha256)
    def __repr__(self):return '<ProtectedMarketLineage redacted>'
    def __reduce_ex__(self,protocol):raise RuntimeRefused('MARKET_LINEAGE_SERIALIZATION_FORBIDDEN')


def protect_market_lineage(owner,lineage,*,task_id,capture_id):
    plain=bytearray();encrypted=bytearray()
    try:
        with _owner_scope(owner.lease) as state:
            require_live_owner(owner.lease,'execution');_need(type(lineage) is _OwnerMarketLineage)
            content=lineage.content;meta,value,records=_metadata(owner,content,task_id,capture_id);fresh,prior=records;g=fresh['grant']
            entropy=_context(state.project.project_id,g['account_alias'],task_id,capture_id)
            _need(g['owner_instance']==owner.lease.identity.process_instance_id and g['owner_generation']==owner.lease.generation)
            _need(fresh['state']=='COMPLETE' and owner._fresh_job==g['job_id'] and owner._producer is not None)
            owner._fresh_current(fresh);owner._producer._context();history=_history(owner,state,prior,owner._opened)
            validate_owner_lineage(content,history=history)
            with open_paper_credentials(owner.lease,owner._producer._protected) as opened:
                _scan_generated(dict(metadata=meta,lineage=value,path=_path(task_id,capture_id)),tuple(opened.headers().values()))
            plain=_pack([canonical(meta),content],entropy);encrypted=_crypt(plain,entropy,decrypt=False)
            size=len(encrypted);_wipe(encrypted);plain[72:76]=size.to_bytes(4,'big');_digest(plain,entropy)
            encrypted=_crypt(plain,entropy,decrypt=False);_need(len(encrypted)==size)
            owner._fresh_current(fresh);owner._producer._context()
            _need(_originals(owner,content)[1]==records and _history(owner,state,prior,owner._opened)==history)
            return _ProtectedMarketLineage(state.project.project_id,g['account_alias'],task_id,capture_id,bytes(encrypted),_factory=_FACTORY)
    except _INVALID:raise RuntimeRefused('MARKET_LINEAGE_EVIDENCE_INVALID') from None
    finally:_wipe(plain);_wipe(encrypted)


def publish_market_lineage(manager,grant,protected):
    writer=None
    try:
        with manager.store._live() as guard:
            _need(type(protected) is _ProtectedMarketLineage and owner_of_grant(grant) is manager);protected._verify()
            task=protected.task_id;capture=protected.capture_id;raw=protected.ciphertext
            _need(protected.project_id==manager.lease.project_id and grant.task_id==task and grant.category=='records' and grant.maximum==len(raw))
            relative=_path(task,capture);path=checked_path(manager.root,manager.root/relative)
            row=manager.store.conn.execute('SELECT status,path,manifest FROM reservations WHERE id=?',(grant.grant_id,)).fetchone();_need(row is not None)
            if path.parent.exists():
                with _pinned(guard,path):
                    if path.exists():
                        _need(row[:2]==('PUBLISHED',relative));manifest=strict_json(row[2].encode());_manifest(manifest,task,capture)
                        _need(guard.api.read_regular(path,maximum=_CIPHER_MAX)==raw and manifest['size_bytes']==len(raw) and manifest['sha256']==_sha(raw));return manifest
            _need(row[0]=='RESERVED');writer=manager.open_artifact(grant,relative);writer.write(raw);manifest=writer.publish();_manifest(manifest,task,capture)
            with _pinned(guard,path):_need(guard.api.read_regular(path,maximum=_CIPHER_MAX)==raw)
            return manifest
    except _INVALID:raise RuntimeRefused('MARKET_LINEAGE_EVIDENCE_INVALID') from None
    finally:
        if writer is not None:writer.close()


class _OpenedMarketLineage:
    __slots__=('_owner','_buffer','_entropy','_manifest','_manifest_sha','_capture','_history','_state','_closed')
    def __init__(self,owner,buffer,entropy,manifest,capture,history,state):
        self._owner=owner;self._buffer=buffer;self._entropy=entropy;self._manifest=manifest;self._capture=capture;self._history=history;self._state=state;self._closed=False
        self._manifest_sha=_sha(canonical(manifest))
    def __repr__(self):return '<HistoricalMarketLineage private data redacted>'
    def __reduce_ex__(self,protocol):raise RuntimeRefused('MARKET_LINEAGE_SERIALIZATION_FORBIDDEN')
    def snapshot(self):
        try:
            with _owner_scope(self._owner.lease) as state:
                require_live_owner(self._owner.lease,'execution');_need(state is self._state and not self._closed and self in state.resources)
                _need(_sha(canonical(self._manifest))==self._manifest_sha)
                _manifest(self._manifest,self._manifest['task_id'],self._capture);_published(state,self._manifest)
                frames=_frames(self._buffer,self._entropy,cipher_size=self._manifest['size_bytes']);meta=strict_json(frames[0])
                expected,value,records=_metadata(self._owner,frames[1],self._manifest['task_id'],self._capture)
                _need(canonical(meta)==frames[0]==canonical(expected))
                _need(self._entropy==_context(state.project.project_id,meta['account_alias'],meta['task_id'],meta['capture_id']))
                history=_history(self._owner,state,records[1],self._history);result=validate_owner_lineage(frames[1],history=history)
                _need(_originals(self._owner,frames[1])[1]==records and _history(self._owner,state,records[1],self._history)==history)
                return dict(result,metadata=meta,lineage=value)
        except _INVALID:raise RuntimeRefused('MARKET_LINEAGE_EVIDENCE_INVALID') from None
    def close(self):
        with _MUTEX:
            self._closed=True;_wipe(self._buffer)
            if self in self._state.resources:self._state.resources.remove(self)


@contextmanager
def open_market_lineage(owner,*,account_alias,capture_id,manifest):
    plain=bytearray();private=None
    with ExitStack() as stack:
        try:
            try:
                with _owner_scope(owner.lease) as state:
                    require_live_owner(owner.lease,'execution')
                    _need(not any(type(r) is _OpenedMarketLineage and not r._closed for r in state.resources))
                    _need(type(manifest) is dict);task=manifest.get('task_id');entropy=_context(state.project.project_id,account_alias,task,capture_id)
                    _manifest(manifest,task,capture_id);manifest=strict_json(canonical(manifest));raw=_published(state,manifest)
                    plain=_crypt(bytearray(raw),entropy,decrypt=True);frames=_frames(plain,entropy,cipher_size=len(raw))
                    _,records=_originals(owner,frames[1]);prior=records[1]
                    held=owner._opened
                    if held is None:held=stack.enter_context(open_market_evidence(owner.lease,account_alias,prior['grant']['job_id'],prior['manifest']))
                    _history(owner,state,prior,held)
                    private=_OpenedMarketLineage(owner,plain,entropy,manifest,capture_id,held,state);state.resources.append(private);private.snapshot()
            except _INVALID:raise RuntimeRefused('MARKET_LINEAGE_EVIDENCE_INVALID') from None
            yield private
        finally:
            if private is not None:private.close()
            else:_wipe(plain)
