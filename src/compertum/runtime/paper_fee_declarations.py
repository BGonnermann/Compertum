"""Retained declared fee inputs. Original bytes do not prove billing or applicability."""
from dataclasses import dataclass
from contextlib import ExitStack
import base64,hashlib,json,re,sqlite3

from compertum.data.encoding import canonical
from compertum.domain import ContractError
from compertum.paper_contracts import identifier,strict_json
from compertum.paper_fees import FeeSource,FeeSchedule
from compertum.persistence import checked_path
from compertum.storage import owner_of_grant
from .errors import RuntimeRefused
from .owners import _owner_scope,require_live_owner
from .paper_credential_slot import _coordinator_records
from .paper_market_evidence import _pinned

_MAX=12*1024**2
_FACTORY=object()
_INVALID=(ContractError,ValueError,TypeError,KeyError,AttributeError,UnicodeError,
          RecursionError,OverflowError,OSError,sqlite3.Error)


def _need(value):
    if not value:
        raise RuntimeRefused('FEE_DECLARATION_INVALID')


def _sha(raw):return hashlib.sha256(raw).hexdigest()


def _path(task,identity):
    identifier(task);identifier(identity)
    return f'artifacts/runs/{task}/declared-fees-{identity}.json'


def _base64(value,maximum):
    _need(type(value) is str and len(value)<=4*((maximum+2)//3))
    raw=base64.b64decode(value,validate=True)
    _need(len(raw)<=maximum and base64.b64encode(raw).decode()==value)
    return raw


def _decode(raw,project,task,identity):
    _need(type(raw) is bytes and 0<len(raw)<=_MAX)
    value=json.loads(raw);_need(canonical(value)==raw)
    pending=[(value,0)];count=0
    while pending:
        item,depth=pending.pop();count+=1;_need(depth<=40 and count<=100000)
        if type(item) is dict:pending.extend((x,depth+1) for x in item.values())
        elif type(item) is list:pending.extend((x,depth+1) for x in item)
    _need(type(value) is dict and set(value)=={'version','purpose','project_id','task_id','declaration_id','sources','schedules'})
    _need(type(project) is str and re.fullmatch('[0-9a-f]{64}',project) is not None)
    identifier(task);identifier(identity)
    _need(type(value['version']) is int and value['version']==1 and value['purpose']=='DECLARED_FEE_INPUTS')
    _need((value['project_id'],value['task_id'],value['declaration_id'])==(project,task,identity))
    _need(type(value['sources']) is list and len(value['sources'])<=32)
    sources={};total=0
    for row in value['sources']:
        _need(type(row) is dict and set(row)=={'sha256','metadata','raw_base64'})
        metadata=row['metadata'];_need(type(metadata) is dict)
        source=FeeSource(_base64(row['raw_base64'],2*1024**2),metadata['url'],metadata['media_type'],metadata['retrieved_at'])
        _need(metadata==source.to_payload() and row['sha256']==source.sha256 and source.sha256 not in sources)
        sources[source.sha256]=source;total+=len(source.raw);_need(total<=8*1024**2)
    _need(type(value['schedules']) is list and len(value['schedules'])<=8)
    schedules=[];hashes=set();identities=set();used=set()
    for row in value['schedules']:
        _need(type(row) is dict and set(row)=={'sha256','content_base64','source_sha256'})
        refs=row['source_sha256']
        _need(type(refs) is list and 1<=len(refs)<=4 and all(type(x) is str for x in refs))
        _need(refs==sorted(set(refs)) and all(ref in sources for ref in refs))
        schedule=FeeSchedule(tuple(sources[ref] for ref in refs),_base64(row['content_base64'],65536))
        schedule_id=schedule.to_payload()['schedule_id']
        _need(row['sha256']==schedule.sha256 and schedule.sha256 not in hashes and schedule_id not in identities)
        hashes.add(schedule.sha256);identities.add(schedule_id);used.update(refs);schedules.append(schedule)
    _need(used==set(sources))
    return value,tuple(schedules)


def _manifest(value,task,identity):
    _need(type(value) is dict and set(value)=={'artifact_id','path','size_bytes','sha256','task_id'})
    identifier(value['artifact_id']);identifier(task)
    _need(value['task_id']==task and value['path']==_path(task,identity))
    _need(type(value['size_bytes']) is int and 0<value['size_bytes']<=_MAX)
    _need(type(value['sha256']) is str and re.fullmatch('[0-9a-f]{64}',value['sha256']) is not None)


@dataclass(frozen=True,slots=True,repr=False,init=False)
class _FeeDeclaration:
    project_id:str
    task_id:str
    declaration_id:str
    content:bytes
    _binding:str

    def __init__(self,project,task,identity,content,*,_factory=None):
        _need(_factory is _FACTORY)
        for key,value in zip(self.__slots__,(project,task,identity,content,_sha(content))):
            object.__setattr__(self,key,value)

    def __repr__(self):return '<DeclaredFeeInputs private sources redacted>'
    def __reduce_ex__(self,protocol):raise RuntimeRefused('FEE_DECLARATION_SERIALIZATION_FORBIDDEN')


def prepare_fee_declaration(*,project_id,task_id,declaration_id,schedules):
    try:
        _need(type(schedules) is tuple and len(schedules)<=8)
        sources={};prepared=[]
        for schedule in schedules:
            _need(type(schedule) is FeeSchedule);schedule.__post_init__()
            for source in schedule.sources:sources[source.sha256]=source
            prepared.append(dict(sha256=schedule.sha256,content_base64=base64.b64encode(schedule.content).decode(),
                source_sha256=sorted(source.sha256 for source in schedule.sources)))
        _need(sum(len(source.raw) for source in sources.values())<=8*1024**2)
        payload=dict(version=1,purpose='DECLARED_FEE_INPUTS',project_id=project_id,task_id=task_id,
            declaration_id=declaration_id,sources=[dict(sha256=key,metadata=source.to_payload(),
            raw_base64=base64.b64encode(source.raw).decode()) for key,source in sorted(sources.items())],
            schedules=sorted(prepared,key=lambda row:row['sha256']))
        raw=canonical(payload);_decode(raw,project_id,task_id,declaration_id)
        return _FeeDeclaration(project_id,task_id,declaration_id,raw,_factory=_FACTORY)
    except _INVALID:
        raise RuntimeRefused('FEE_DECLARATION_INVALID') from None


def publish_fee_declaration(manager,grant,declaration):
    writer=None
    try:
        _need(not manager.store.conn.in_transaction)
        with manager.store._live() as guard:
            _need(type(declaration) is _FeeDeclaration and owner_of_grant(grant) is manager)
            d=declaration;_need(d.project_id==manager.lease.project_id and d._binding==_sha(d.content))
            _decode(d.content,d.project_id,d.task_id,d.declaration_id)
            _need(grant.task_id==d.task_id and grant.category=='records' and grant.maximum==len(d.content))
            relative=_path(d.task_id,d.declaration_id);path=checked_path(manager.root,manager.root/relative)
            row=manager.store.conn.execute('SELECT status,path,manifest FROM reservations WHERE id=?',(grant.grant_id,)).fetchone()
            _need(row is not None)
            if row[0]=='PUBLISHED':
                _need(row[1]==relative);manifest=strict_json(row[2].encode());_manifest(manifest,d.task_id,d.declaration_id)
                with _pinned(guard,path):raw=guard.api.read_regular(path,maximum=_MAX)
                _need(raw==d.content and len(raw)==manifest['size_bytes'] and _sha(raw)==manifest['sha256'])
                return manifest
            _need(row[0]=='RESERVED' and not path.exists())
            writer=manager.open_artifact(grant,relative)
            for start in range(0,len(d.content),65536):writer.write(d.content[start:start+65536])
            manifest=writer.publish();_manifest(manifest,d.task_id,d.declaration_id)
            with _pinned(guard,path):_need(guard.api.read_regular(path,maximum=_MAX)==d.content)
            return manifest
    except _INVALID:
        raise RuntimeRefused('FEE_DECLARATION_INVALID') from None
    finally:
        if writer is not None:writer.close()


def _published(guard,identity,manifest):
    task=manifest.get('task_id');_manifest(manifest,task,identity)
    with _coordinator_records(guard) as db:
        rows=db.execute('SELECT task,category,status,written,manifest FROM reservations WHERE path=? LIMIT 2',(manifest['path'],)).fetchall()
        _need(rows==[(task,'records','PUBLISHED',manifest['size_bytes'],canonical(manifest).decode())])
    path=checked_path(guard.project.root_path,guard.project.root_path/manifest['path'])
    with _pinned(guard,path):raw=guard.api.read_regular(path,maximum=_MAX)
    _need(len(raw)==manifest['size_bytes'] and _sha(raw)==manifest['sha256'])
    return raw


def _raw_original(lease,manifest,expected):
    """Capture fixed native checks. Run no declaration or source callbacks here."""
    task=manifest['task_id'];relative=manifest['path']
    expected_row=(task,'records','PUBLISHED',manifest['size_bytes'],canonical(manifest).decode())
    def checked(identity=None):
        with _owner_scope(lease) as guard,ExitStack() as pins:
            require_live_owner(lease,'execution')
            path=guard.project.root_path/relative;current=guard.project.root_path
            for part in path.parent.relative_to(current).parts:
                current=current/part;pins.enter_context(guard.api.open_directory(current))
            _need(next(path.parent.glob(path.name+'.partial-*'),None) is None)
            handle=pins.enter_context(guard.api.open_file(path,0x80000000,1))
            current_identity=guard.api.file_identity(handle)
            _need(identity is None or current_identity==identity)
            with _coordinator_records(guard) as db:
                rows=db.execute('SELECT task,category,status,written,manifest FROM reservations WHERE path=? LIMIT 2',(relative,)).fetchall()
                _need(rows==[expected_row])
            _need(guard.api.read_regular(path,maximum=_MAX)==expected)
            return current_identity
    identity=checked()
    def original():
        try:checked(identity)
        except _INVALID:raise RuntimeRefused('FEE_DECLARATION_INVALID') from None
    return original


def _capture_fee_declaration(lease,declaration_id,manifest):
    try:
        m=strict_json(canonical(manifest));identifier(declaration_id)
        with _owner_scope(lease) as guard:
            require_live_owner(lease,'execution');raw=_published(guard,declaration_id,m)
            value,schedules=_decode(raw,lease.project_id,m['task_id'],declaration_id)
        final=_raw_original(lease,m,raw)
        manifest_bytes=canonical(m)
        def original():
            try:
                with _owner_scope(lease) as current:
                    require_live_owner(lease,'execution')
                    _need(_published(current,declaration_id,json.loads(manifest_bytes))==raw)
            except _INVALID:
                raise RuntimeRefused('FEE_DECLARATION_INVALID') from None
        return value,schedules,original,final
    except _INVALID:
        raise RuntimeRefused('FEE_DECLARATION_INVALID') from None


def read_fee_declaration(lease,declaration_id,manifest):
    value,schedules,callback_check,final=_capture_fee_declaration(lease,declaration_id,manifest)
    def original():
        callback_check();final()
    return value,schedules,original
