"""Purpose-bound encrypted activity history. Reopening never restores freshness."""
from contextlib import contextmanager
from dataclasses import dataclass
import json,re,math
from compertum.data.encoding import canonical
from compertum.paper_activity_records import PreparedActivityRequest,ParsedActivityPage,activity_traversal,sha
from compertum.paper_contracts import identifier,strict_json,timestamp,utc
from compertum.persistence import checked_path
from compertum.storage import owner_of_grant
from .errors import RuntimeRefused
from .owners import _MUTEX,_owner_scope,require_live_owner
from .paper_credentials import _alias,_crypt_bounded,_wipe,open_paper_credentials
from .paper_credential_slot import _coordinator_records,load_paper_slot
from .paper_market_evidence import _pinned
from .paper_market_collection import _scan_generated

_MAX=3*1024**2;_PLAIN=2*1024**2;_FACTORY=object()


def _need(value):
    if not value:raise RuntimeRefused('PAPER_ACTIVITY_EVIDENCE_INVALID')


def _decode(raw):
    _need(type(raw) is bytes and 0<len(raw)<=_PLAIN)
    value=json.loads(raw);_need(canonical(value)==raw)
    pending=[(value,0)];count=0
    while pending:
        item,depth=pending.pop();count+=1;_need(depth<=40 and count<=100000)
        if type(item) is dict:pending.extend((x,depth+1) for x in item.values())
        elif type(item) is list:pending.extend((x,depth+1) for x in item)
    return value


def _context(project,alias,task,aid):
    _need(type(project) is str and re.fullmatch('[0-9a-f]{64}',project) is not None)
    _alias(alias);identifier(task);identifier(aid)
    return b'\0'.join((b'CPACT001',b'HISTORICAL_ACTIVITY_ONLY',b'https://paper-api.alpaca.markets',project.encode(),alias.encode(),task.encode(),aid.encode()))


def _hash(v):return type(v) is str and re.fullmatch('[0-9a-f]{64}',v) is not None


def _evidence(v):
    _need(type(v) is dict and set(v)=={'size_bytes','sha256'} and type(v['size_bytes']) is int and 0<v['size_bytes']<=_MAX and _hash(v['sha256']))


def validate_binding(v,project,alias,aid):
    _need(type(v) is dict and set(v)=={'seed','activity_id','account','port','generation','instance','started_ns','deadline_ns','start_mono'})
    _need(v['activity_id']==aid and _hash(v['account']));identifier(aid);identifier(v['instance'])
    _need(type(v['generation']) is int and v['generation']>0)
    _need(v['port'] is None or type(v['port']) is int and 1<=v['port']<=65535)
    _need(type(v['started_ns']) is int and 0<=v['started_ns']<2**63 and type(v['deadline_ns']) is int and v['deadline_ns']-v['started_ns']==20*10**9)
    _need(type(v['start_mono']) in (int,float) and math.isfinite(v['start_mono']) and v['start_mono']>=0)
    s=v['seed'];_need(type(s) is dict and set(s)=={'project_id','account_alias','opening_sha256','account_context_sha256','history_sha256','credential_sha256','after','until','started_at'})
    _need(s['project_id']==project and s['account_alias']==alias)
    for k in ('project_id','opening_sha256','account_context_sha256','history_sha256','credential_sha256'):_need(_hash(s[k]))
    _need(timestamp(s['after'])<timestamp(s['until'])==timestamp(s['started_at']))
    _need(all(utc(s[k])==s[k] for k in ('after','until','started_at')))


def validate_summary(v):
    base={'status','traversal_complete','pages','rows','raw_bytes','deficiencies','native_transport_verified','financial_accepted','transport_authorized','actual_flat','attempts','native_closed','reason'}
    extra={'version','record_type','scope','unsupported_activities'}
    _need(type(v) is dict and set(v) in (base,base|extra))
    _need(v['status']=='BLOCKED' and v['native_transport_verified'] is v['financial_accepted'] is v['transport_authorized'] is False and v['actual_flat'] is None)
    _need(type(v['traversal_complete']) is bool and type(v['native_closed']) is bool)
    for k,maximum in (('pages',8),('rows',200),('raw_bytes',512*1024),('attempts',8)):_need(type(v[k]) is int and 0<=v[k]<=maximum)
    _need(v['pages']<=v['attempts'] and type(v['deficiencies']) is list and len(v['deficiencies'])<=16)
    _need(all(type(x) is str and re.fullmatch('[A-Z][A-Z0-9_]{0,95}',x) is not None for x in v['deficiencies']))
    _need({'OWNERSHIP_UNVERIFIED','ECONOMIC_COVERAGE_UNVERIFIED'}<=set(v['deficiencies']))
    _need(v['reason'] is None or type(v['reason']) is str and re.fullmatch('[A-Z][A-Z0-9_]{0,95}',v['reason']) is not None)


def _path(task,aid):
    identifier(task);identifier(aid);return f'artifacts/runs/{task}/paper-activity-{aid}.bin'


def _validate(value,project,alias,task,aid):
    _context(project,alias,task,aid)
    _need(type(value) is dict and set(value)=={'version','purpose','project_id','account_alias','task_id','activity_id','collection','freshness','financial_accepted','transport_authorized'})
    _need(type(value['version']) is int and value['version']==1 and value['purpose']=='HISTORICAL_ACTIVITY_ONLY')
    _need((value['project_id'],value['account_alias'],value['task_id'],value['activity_id'])==(project,alias,task,aid))
    _need(value['freshness']=='NOT_RESTORED' and value['financial_accepted'] is value['transport_authorized'] is False)
    v=value['collection'];_need(type(v) is dict and set(v)=={'version','purpose','activity_id','bindings','binding','plan_sha256','account_identity_sha256','expected_account_id','execution_generation','execution_instance','attempts','provenance','state','reason','summary','pages'})
    _need(v['activity_id']==aid and v['purpose']=='HISTORICAL_ACTIVITY_ONLY' and type(v['version']) is int and v['version']==1)
    _need(v['provenance'] in {'PAPER_TLS','LOOPBACK_FIXTURE','NO_RESPONSE'} and v['state'] in {'COMPLETE','INCOMPLETE','CANCELED'})
    validate_binding(v['binding'],project,alias,aid)
    _need(v['bindings']==v['binding']['seed'] and sha(canonical(v['binding']))==v['plan_sha256'])
    _need(v['execution_generation']==v['binding']['generation'] and v['execution_instance']==v['binding']['instance'])
    _need(v['account_identity_sha256']==v['binding']['account'])
    _need(v['provenance']=='NO_RESPONSE' or v['provenance']==('PAPER_TLS' if v['binding']['port'] is None else 'LOOPBACK_FIXTURE'))
    identifier(v['execution_instance']);_need(type(v['execution_generation']) is int and v['execution_generation']>0)
    _need(sha(v['expected_account_id'].encode())==v['account_identity_sha256'])
    _need(type(v['attempts']) is list and len(v['attempts'])<=8 and type(v['pages']) is list and len(v['pages'])<=len(v['attempts']))
    requests={};ids=set()
    for a in v['attempts']:
        _need(type(a) is dict and set(a)=={'request','request_sha256','pre_send_ns','committed_ns','native_closed','status'})
        request=PreparedActivityRequest(canonical(a['request']),v['expected_account_id']);r=request.to_payload()
        _need(request.sha256==a['request_sha256'] and request.sha256 not in requests and r['request_id'] not in ids)
        _need(all(r[k]==item for k,item in v['bindings'].items()))
        _need(r['project_id']==project and r['account_alias']==alias)
        for k in ('pre_send_ns','committed_ns'):_need(a[k] is None or type(a[k]) is int and 0<=a[k]<2**63)
        _need(a['committed_ns'] is None or a['pre_send_ns'] is not None and a['pre_send_ns']<=a['committed_ns'])
        _need(type(a['native_closed']) is bool and (a['status'] is None or type(a['status']) is int and 200<=a['status']<=599))
        requests[request.sha256]=(request,a);ids.add(r['request_id'])
    pages=[]
    for i,row in enumerate(v['pages']):
        _need(type(row) is dict and set(row)=={'request','raw_utf8','parsed'})
        request=PreparedActivityRequest(canonical(row['request']),v['expected_account_id'])
        _need(i<len(v['attempts']) and v['attempts'][i]['request_sha256']==request.sha256)
        _,attempt=requests[request.sha256];_need(attempt['status']==200 and attempt['native_closed'] and attempt['committed_ns'] is not None)
        page=ParsedActivityPage(request,row['raw_utf8'].encode(),canonical(row['parsed']),row['parsed']['received_at']);pages.append(page)
    summary=v['summary'];validate_summary(summary)
    _need(summary['attempts']==len(v['attempts']) and summary['pages']==len(pages) and summary['reason']==v['reason'])
    _need(summary['native_transport_verified'] is False and summary['actual_flat'] is None)
    if pages:
        expected=activity_traversal(tuple(pages));_need(all(summary[k]==item for k,item in expected.items()))
    else:_need(not summary['traversal_complete'] and v['provenance']=='NO_RESPONSE')
    if v['state']=='COMPLETE':_need(pages and summary['traversal_complete'] and summary['native_closed'])
    return value


@dataclass(frozen=True,slots=True,repr=False,init=False)
class _ProtectedActivityEvidence:
    project_id:str
    account_alias:str
    task_id:str
    activity_id:str
    ciphertext:bytes
    _binding:str
    def __init__(self,project,alias,task,aid,cipher,*,_factory=None):
        _need(_factory is _FACTORY and type(cipher) is bytes and 0<len(cipher)<=_MAX)
        for key,item in zip(self.__slots__,(project,alias,task,aid,cipher,sha(_context(project,alias,task,aid)+cipher))):object.__setattr__(self,key,item)
    def __repr__(self):return '<ProtectedActivityEvidence redacted>'
    def __reduce_ex__(self,p):raise RuntimeRefused('PAPER_ACTIVITY_SERIALIZATION_FORBIDDEN')


def protect_activity_evidence(lease,alias,task,aid,producer):
    from .paper_activity_owner import _ActivityProducer
    plain=bytearray();encrypted=bytearray()
    try:
        with _owner_scope(lease) as guard:
            require_live_owner(lease,'execution');_need(type(producer) is _ActivityProducer and producer._lease is lease and producer._id==aid)
            value=dict(version=1,purpose='HISTORICAL_ACTIVITY_ONLY',project_id=lease.project_id,account_alias=alias,task_id=task,
                activity_id=aid,collection=producer.snapshot(),freshness='NOT_RESTORED',financial_accepted=False,transport_authorized=False)
            _validate(value,lease.project_id,alias,task,aid)
            with open_paper_credentials(lease,producer._protected) as opened:_scan_generated(value,tuple(opened.headers().values()))
            _need(value['collection']==producer.snapshot());entropy=_context(lease.project_id,alias,task,aid)
            plain=bytearray(canonical(value));_need(len(plain)<=_PLAIN)
            encrypted=_crypt_bounded(plain,entropy,decrypt=False,input_max=_PLAIN,output_max=_MAX,error_prefix='PAPER_ACTIVITY_EVIDENCE')
            return _ProtectedActivityEvidence(lease.project_id,alias,task,aid,bytes(encrypted),_factory=_FACTORY)
    finally:_wipe(plain);_wipe(encrypted)


def _manifest(m,task,aid):
    _need(type(m) is dict and set(m)=={'artifact_id','path','size_bytes','sha256','task_id'})
    identifier(m['artifact_id']);_need(m['task_id']==task and m['path']==_path(task,aid))
    _need(type(m['size_bytes']) is int and 0<m['size_bytes']<=_MAX and type(m['sha256']) is str and re.fullmatch('[0-9a-f]{64}',m['sha256']) is not None)


def publish_activity_evidence(manager,grant,protected):
    writer=None
    try:
        with manager.store._live() as guard:
            _need(type(protected) is _ProtectedActivityEvidence and owner_of_grant(grant) is manager)
            p=protected;_need(p._binding==sha(_context(p.project_id,p.account_alias,p.task_id,p.activity_id)+p.ciphertext))
            _need(p.project_id==manager.lease.project_id and grant.task_id==p.task_id and grant.category=='records' and grant.maximum==len(p.ciphertext))
            relative=_path(p.task_id,p.activity_id);path=checked_path(manager.root,manager.root/relative)
            row=manager.store.conn.execute('SELECT status,path,manifest FROM reservations WHERE id=?',(grant.grant_id,)).fetchone();_need(row is not None)
            if path.parent.exists():
                with _pinned(guard,path):
                    if path.exists():
                        _need(row[:2]==('PUBLISHED',relative));m=strict_json(row[2].encode());_manifest(m,p.task_id,p.activity_id)
                        _need(guard.api.read_regular(path,maximum=_MAX)==p.ciphertext and m['sha256']==sha(p.ciphertext) and m['size_bytes']==len(p.ciphertext));return m
            _need(row[0]=='RESERVED');writer=manager.open_artifact(grant,relative);writer.write(p.ciphertext);m=writer.publish()
            _manifest(m,p.task_id,p.activity_id)
            with _pinned(guard,path):_need(guard.api.read_regular(path,maximum=_MAX)==p.ciphertext)
            return m
    finally:
        if writer is not None:writer.close()


def verify_activity_publication(lease,alias,aid,task,manifest,evidence):
    with open_activity_evidence(lease,alias,aid,manifest) as opened:
        _need(manifest['task_id']==task and evidence==dict(size_bytes=manifest['size_bytes'],sha256=manifest['sha256']))
        return opened.snapshot()


class _OpenedActivity:
    def __init__(self,lease,plain,identity):self._lease=lease;self._plain=plain;self._identity=identity;self._closed=False
    def __repr__(self):return '<HistoricalActivityEvidence redacted>'
    def __reduce_ex__(self,p):raise RuntimeRefused('PAPER_ACTIVITY_SERIALIZATION_FORBIDDEN')
    def snapshot(self):
        with _owner_scope(self._lease):
            require_live_owner(self._lease,'execution');_need(not self._closed)
            return _validate(_decode(bytes(self._plain)),*self._identity)
    def close(self):self._closed=True;_wipe(self._plain)


@contextmanager
def open_activity_evidence(lease,alias,aid,manifest):
    plain=bytearray();opened=None
    try:
        with _owner_scope(lease) as guard:
            require_live_owner(lease,'execution');m=strict_json(canonical(manifest));task=m.get('task_id');_manifest(m,task,aid)
            with _coordinator_records(guard) as db:
                rows=db.execute('SELECT task,category,status,written,manifest FROM reservations WHERE path=? LIMIT 2',(m['path'],)).fetchall()
                _need(rows==[(task,'records','PUBLISHED',m['size_bytes'],canonical(m).decode())])
            path=checked_path(guard.project.root_path,guard.project.root_path/m['path'])
            with _pinned(guard,path):raw=guard.api.read_regular(path,maximum=_MAX)
            _need(sha(raw)==m['sha256'] and len(raw)==m['size_bytes'])
            entropy=_context(lease.project_id,alias,task,aid)
            plain=_crypt_bounded(bytearray(raw),entropy,decrypt=True,input_max=_MAX,output_max=_PLAIN,error_prefix='PAPER_ACTIVITY_EVIDENCE')
            _validate(_decode(bytes(plain)),lease.project_id,alias,task,aid)
            opened=_OpenedActivity(lease,plain,(lease.project_id,alias,task,aid));guard.resources.append(opened)
        yield opened
    finally:
        with _MUTEX:
            if opened is not None:
                opened.close()
                if opened in guard.resources:guard.resources.remove(opened)
            else:_wipe(plain)
