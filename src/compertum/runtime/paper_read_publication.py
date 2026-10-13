"""Coordinator routing and bounded opaque publication from its native owner.

The coordinator never receives plaintext credentials or account observations.
Each tick performs at most one private RPC or one local publication operation.
"""
import base64,hashlib,re
from uuid import uuid5,NAMESPACE_URL
from compertum.data.encoding import canonical
from compertum.events import uuid
from compertum.paper_contracts import strict_json
from .errors import RuntimeRefused
from .owner_channel import _remote_scope
from .owner_rpc import call_owner
from .paper_read_evidence import _ProtectedReadEvidence,_FACTORY,publish_read_evidence

_CIPHER_MAX=3*1024**2

def _need(value,code='READ_PUBLICATION_INVALID'):
    if not value:raise RuntimeRefused(code)

class PaperReadPublication:
    def __init__(self,manager,remote):
        self.manager=manager;self.remote=remote;self.db=manager.store.conn;self.entries={};self._cursor=0
        with manager.store._live(),_remote_scope(remote),self.db:
            r=remote.descriptor.registration
            _need(r.identity.role=='execution' and r.project_id==manager.lease.project_id)
            self.db.execute('CREATE TABLE IF NOT EXISTS paper_read_routes(packet_id TEXT PRIMARY KEY,body TEXT NOT NULL)')
            rows=self.db.execute('SELECT packet_id FROM paper_read_routes LIMIT 33').fetchall();_need(len(rows)<=32)
            for (packet_id,) in rows:
                route=self._route(packet_id)
                if route['publication']['state'] in {'WAITING','TRANSFERRING'}:
                    route['publication'].update(state='FAILED',reason='READ_COORDINATOR_RESTARTED');self._save(route)

    def _route(self,packet_id):
        row=self.db.execute('SELECT CASE WHEN length(body)<=8192 THEN body END FROM paper_read_routes WHERE packet_id=?',(packet_id,)).fetchone()
        if row is None:raise RuntimeRefused('READ_PACKET_UNKNOWN')
        try:
            v=strict_json(row[0].encode())
            _need(type(v) is dict and set(v)=={'packet_id','task_id','account_alias','subject_key','reservation_id','publication'})
            _need(v['packet_id']==packet_id)
            for k in ('packet_id','task_id','reservation_id'):uuid(v[k])
            _need(type(v['subject_key']) is str and re.fullmatch('[0-9a-f]{64}',v['subject_key']) is not None)
            _need(type(v['account_alias']) is str and re.fullmatch('[A-Za-z0-9][A-Za-z0-9_-]{0,63}',v['account_alias']) is not None)
            _need(type(v['publication']) is dict and set(v['publication'])=={'state','reason','manifest'})
            _need(v['publication']['state'] in {'WAITING','TRANSFERRING','PUBLISHED','FAILED','NO_EVIDENCE'})
            return v
        except (ValueError,TypeError,AttributeError,KeyError):raise RuntimeRefused('READ_PUBLICATION_INVALID') from None

    def _save(self,route,*,new=False):
        raw=canonical(route).decode();_need(len(raw.encode())<=8192)
        if new:c=self.db.execute('INSERT INTO paper_read_routes VALUES(?,?)',(route['packet_id'],raw))
        else:c=self.db.execute('UPDATE paper_read_routes SET body=? WHERE packet_id=?',(raw,route['packet_id']))
        _need(c.rowcount==1 and self._route(route['packet_id'])==route,'READ_PUBLICATION_WRITE_UNVERIFIED')

    def _call(self,route,command):return call_owner(self.remote,'paper_read',dict(subject_key=route['subject_key'],command=command))

    def handle(self,subject,command):
        with self.manager.store._live():
            _need(type(subject) is str and re.fullmatch('[0-9a-f]{64}',subject) is not None,'CONTROL_PAYLOAD_DENIED')
            _need(type(command) is dict and type(command.get('operation')) is str,'CONTROL_PAYLOAD_DENIED')
            op=command['operation'];keys={'prepare':{'operation','packet_id','account_alias'},'authorize':{'operation','packet_id','plan_sha256'},'start':{'operation','packet_id','plan_sha256'},'status':{'operation','packet_id'},'cancel':{'operation','packet_id'},'account_propose':{'operation','packet_id'},'account_confirm':{'operation','packet_id','proposal_sha256','acknowledgement'},'account_status':{'operation','packet_id'}}
            _need(op in keys and set(command)==keys[op],'CONTROL_PAYLOAD_DENIED');uuid(command['packet_id']);pid=command['packet_id']
            if op=='prepare':
                if self.db.execute('SELECT 1 FROM paper_read_routes WHERE packet_id=?',(pid,)).fetchone():route=self._route(pid)
                else:
                    _need(type(command['account_alias']) is str and re.fullmatch('[A-Za-z0-9][A-Za-z0-9_-]{0,63}',command['account_alias']) is not None,'CONTROL_PAYLOAD_DENIED')
                    _need(self.db.execute('SELECT count(*) FROM paper_read_routes').fetchone()[0]<32,'READ_HISTORY_BOUND')
                    task=str(uuid5(NAMESPACE_URL,self.manager.lease.project_id+'/paper-read/'+pid))
                    # The bounded parent reservation is retained even on failure.
                    grant=self.manager.reserve_bytes(task,'records',_CIPHER_MAX)
                    route=dict(packet_id=pid,task_id=task,account_alias=command['account_alias'],subject_key=subject,reservation_id=grant.grant_id,
                        publication=dict(state='WAITING',reason=None,manifest=None))
                    with self.db:self._save(route,new=True)
                    self.entries[pid]=dict(route=route,grant=grant,phase='PREPARED',buffer=bytearray(),evidence=None,protected=None,child=None)
                _need(route['account_alias']==command['account_alias'] and route['subject_key']==subject,'READ_PACKET_CONFLICT')
                result=self._call(route,dict(command,task_id=route['task_id'],reservation_id=route['reservation_id']))
            else:
                route=self._route(pid);_need(route['subject_key']==subject,'READ_OPERATOR_CHANGED')
                if op in {'authorize','start'}:_need(pid in self.entries,'READ_COORDINATOR_RESTARTED')
                if op=='start' and self.entries[pid]['phase']=='PREPARED':self.entries[pid]['phase']='WAIT'
                if op in {'account_propose','account_confirm','account_status'}:
                    _need(route['publication']['state']=='PUBLISHED' and route['publication']['manifest'] is not None,'PAPER_ACCOUNT_PUBLISHED_EVIDENCE_REQUIRED')
                    command=dict(command,manifest=route['publication']['manifest'])
                result=self._call(route,command)
            return dict(result,publication=self._route(pid)['publication'])

    def tick(self):
        with self.manager.store._live():
            ready=[k for k,v in self.entries.items() if v['phase'] not in {'PREPARED','DONE','FAILED'}]
            if not ready:return
            pid=ready[self._cursor%len(ready)];self._cursor+=1;e=self.entries[pid];route=e['route']
            try:
                if e['phase']=='WAIT':
                    status=self._call(route,dict(operation='status',packet_id=pid))
                    _need(status.get('packet_id')==pid and status.get('task_id')==route['task_id'] and status.get('account_alias')==route['account_alias'])
                    evidence=status.get('evidence')
                    if evidence is None:
                        if status.get('state') in {'ABORTED','CANCELED','INTERRUPTED'}:
                            e['phase']='DONE';route['publication'].update(state='NO_EVIDENCE',reason=status.get('reason'))
                            with self.db:self._save(route)
                        return
                    _need(type(evidence) is dict and set(evidence)=={'size_bytes','sha256'} and type(evidence['size_bytes']) is int and 0<evidence['size_bytes']<=_CIPHER_MAX)
                    _need(type(evidence['sha256']) is str and re.fullmatch('[0-9a-f]{64}',evidence['sha256']) is not None)
                    e['evidence']=evidence;e['phase']='COLLECT';route['publication']['state']='TRANSFERRING'
                    with self.db:self._save(route)
                elif e['phase']=='COLLECT':
                    expected=dict(project_id=self.manager.lease.project_id,account_alias=route['account_alias'],task_id=route['task_id'],packet_id=pid,
                        sha256=e['evidence']['sha256'],total_bytes=e['evidence']['size_bytes'],offset=len(e['buffer']))
                    # Both peer identity and frame sequence are native-verified.
                    with _remote_scope(self.remote):
                        reply=call_owner(self.remote,'paper_read_transfer',dict(operation='chunk',packet_id=pid,offset=expected['offset'],sha256=expected['sha256']))
                        _need(type(reply) is dict and set(reply)==set(expected)|{'data'})
                        _need(all(type(reply[k]) is type(v) and reply[k]==v for k,v in expected.items()))
                        _need(type(reply['data']) is str and len(reply['data'])<=43692)
                        try:chunk=base64.b64decode(reply['data'],validate=True)
                        except ValueError:raise RuntimeRefused('READ_PUBLICATION_INVALID') from None
                        _need(len(chunk)==min(32768,expected['total_bytes']-expected['offset']))
                        e['buffer'].extend(chunk)
                        if len(e['buffer'])==expected['total_bytes']:
                            _need(hashlib.sha256(e['buffer']).hexdigest()==expected['sha256'])
                            e['protected']=_ProtectedReadEvidence(expected['project_id'],expected['account_alias'],expected['task_id'],pid,bytes(e['buffer']),_factory=_FACTORY)
                            e['buffer'].clear();e['phase']='PUBLISH'
                elif e['phase']=='PUBLISH':
                    if e['child'] is None:e['child']=self.manager.split_grant(e['grant'],len(e['protected'].ciphertext))
                    manifest=publish_read_evidence(self.manager,e['child'],e['protected'])
                    route['publication'].update(manifest=manifest);e['phase']='ACK'
                    with self.db:self._save(route)
                elif e['phase']=='ACK':
                    reply=call_owner(self.remote,'paper_read_transfer',dict(operation='ack',packet_id=pid,manifest=route['publication']['manifest']))
                    _need(reply.get('packet_id')==pid and reply.get('state')=='PUBLISHED' and reply.get('evidence')==e['evidence'])
                    route['publication']['state']='PUBLISHED'
                    with self.db:self._save(route)
                    e.update(phase='DONE',protected=None);e['buffer'].clear()
            except (RuntimeRefused,OSError) as error:
                e.update(phase='FAILED',protected=None);e['buffer'].clear()
                route['publication'].update(state='FAILED',reason=error.code if isinstance(error,RuntimeRefused) else 'READ_PUBLICATION_IO_FAILED')
                with self.db:self._save(route)
