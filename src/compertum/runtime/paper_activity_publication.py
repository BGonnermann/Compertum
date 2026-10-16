"""Opaque coordinator publication. Acknowledgement retries cannot issue GETs."""
import base64,re
from uuid import uuid5,NAMESPACE_URL
from compertum.data.encoding import canonical
from compertum.paper_activity_records import sha
from compertum.paper_contracts import identifier,strict_json
from .errors import RuntimeRefused
from .owner_channel import _remote_scope
from .owner_rpc import call_owner
from .paper_activity_evidence import _ProtectedActivityEvidence,_FACTORY,_MAX,_manifest,_evidence,publish_activity_evidence

_PREFIX='paper_activity_route:'


def _need(value,code='PAPER_ACTIVITY_PUBLICATION_INVALID'):
    if not value:raise RuntimeRefused(code)


class PaperActivityPublication:
    def __init__(self,manager,remote):
        self.manager=manager;self.remote=remote;self.db=manager.store.conn;self.entries={}
        with manager.store._live(),_remote_scope(remote):
            _need(not self.db.in_transaction)
            r=remote.descriptor.registration;_need(r.identity.role=='execution' and r.project_id==manager.lease.project_id)
            for aid in self._keys():
                route=self._read(aid)
                if route['state']=='ACK_PENDING' and route['ack_attempts']==2:
                    route.update(state='ACK_UNCONFIRMED',reason='ACK_UNCONFIRMED');self._save(route)
                self.entries[aid]=self._entry(route,'ACK' if route['manifest'] is not None and route['state']!='PUBLISHED' and route['ack_attempts']<2 else 'DONE' if route['state'] in {'PUBLISHED','FAILED','ACK_UNCONFIRMED'} else 'WAIT')
    def _keys(self):
        rows=self.db.execute('SELECT key FROM state WHERE substr(key,1,?)=? LIMIT 33',(len(_PREFIX),_PREFIX)).fetchall()
        _need(len(rows)<=32);return [row[0][len(_PREFIX):] for row in rows]
    def _validate(self,v):
        _need(type(v) is dict and set(v)=={'activity_id','packet_id','task_id','reservation_id','subject','account_alias','state','reason','manifest','evidence','ack_attempts'})
        for k in ('activity_id','packet_id','task_id','reservation_id'):identifier(v[k])
        _need(v['task_id']==str(uuid5(NAMESPACE_URL,self.manager.lease.project_id+'/paper-activity/'+v['activity_id'])))
        _need(type(v['subject']) is str and re.fullmatch('[0-9a-f]{64}',v['subject']) is not None)
        _need(v['state'] in {'WAITING','TRANSFERRING','ACK_PENDING','ACK_UNCONFIRMED','PUBLISHED','FAILED'})
        _need(type(v['ack_attempts']) is int and 0<=v['ack_attempts']<=2)
        _need(v['reason'] is None or type(v['reason']) is str and re.fullmatch('[A-Z][A-Z0-9_]{0,95}',v['reason']) is not None)
        if v['evidence'] is not None:_evidence(v['evidence'])
        _need(v['account_alias'] is None or type(v['account_alias']) is str and re.fullmatch('[A-Za-z0-9][A-Za-z0-9_-]{0,63}',v['account_alias']) is not None)
        if v['manifest'] is not None:
            _manifest(v['manifest'],v['task_id'],v['activity_id'])
            _need(v['evidence']==dict(size_bytes=v['manifest']['size_bytes'],sha256=v['manifest']['sha256']))
        if v['state'] in {'ACK_PENDING','ACK_UNCONFIRMED','PUBLISHED'}:_need(v['manifest'] is not None)
        _need(len(canonical(v))<=8192);return v
    def _read(self,aid):
        identifier(aid);row=self.db.execute('SELECT CASE WHEN length(CAST(value AS BLOB))<=8192 THEN value END FROM state WHERE key=?',(_PREFIX+aid,)).fetchone()
        _need(row is not None and row[0] is not None);v=self._validate(strict_json(row[0].encode()));_need(v['activity_id']==aid);return v
    def _save(self,v,new=False):
        _need(not self.db.in_transaction)
        self._validate(v);key=_PREFIX+v['activity_id'];raw=canonical(v).decode()
        with self.db:
            if new:c=self.db.execute('INSERT INTO state VALUES(?,?)',(key,raw))
            else:
                before=self._read(v['activity_id'])
                _need(all(v[k]==before[k] for k in ('activity_id','packet_id','task_id','reservation_id','subject')))
                _need(before['manifest'] is None or before['manifest']==v['manifest'])
                _need(before['evidence'] is None or before['evidence']==v['evidence'])
                _need(before['ack_attempts']<=v['ack_attempts'])
                _need(before['account_alias'] is None or before['account_alias']==v['account_alias'])
                c=self.db.execute('UPDATE state SET value=? WHERE key=? AND value=?',(raw,key,canonical(before).decode()))
            _need(c.rowcount==1 and self._read(v['activity_id'])==v,'PAPER_ACTIVITY_ROUTE_WRITE_UNVERIFIED')
    def _entry(self,r,phase='PREPARED',grant=None):return dict(route=r,phase=phase,grant=grant,buffer=bytearray(),protected=None,child=None)
    def _call(self,r,command):
        with _remote_scope(self.remote):
            value=call_owner(self.remote,'paper_activity',dict(subject_key=r['subject'],command=command))
            _need(type(value) is dict and all(value.get(k)==r[k] for k in ('activity_id','packet_id','task_id','reservation_id')))
            _need(r['account_alias'] is None or value['account_alias']==r['account_alias']);return value
    def handle(self,subject,c):
        # Local command refusals do not change the authenticated transport.
        # Each owner exchange still verifies the peer and its returned binding.
        with self.manager.store._live():
            _need(not self.db.in_transaction)
            _need(type(c) is dict);op=c.get('operation');aid=c.get('activity_id');identifier(aid)
            fields={'prepare':{'packet_id'},'authorize':{'plan_sha256'},'start':{'plan_sha256'},'status':set(),'cancel':set()}
            _need(op in fields and set(c)=={'operation','activity_id'}|fields[op])
            if op=='prepare' and aid not in self._keys():
                _need(len(self._keys())<32)
                task=str(uuid5(NAMESPACE_URL,self.manager.lease.project_id+'/paper-activity/'+aid))
                grant=self.manager.reserve_bytes(task,'records',_MAX)
                r=dict(activity_id=aid,packet_id=c['packet_id'],task_id=task,reservation_id=grant.grant_id,subject=subject,
                    account_alias=None,state='WAITING',reason=None,manifest=None,evidence=None,ack_attempts=0)
                self._save(r,new=True);e=self._entry(r,grant=grant);self.entries[aid]=e
            else:r=self._read(aid);_need(r['subject']==subject);e=self.entries.get(aid)
            if op=='prepare':
                _need(r['packet_id']==c['packet_id'])
                command=dict(c,task_id=r['task_id'],reservation_id=r['reservation_id'])
            else:command=c
            if op in {'authorize','start'}:
                _need(e is not None and e['phase']=='PREPARED' or op=='start' and e is not None and (e['phase']=='WAIT' or r['manifest'] is not None))
            value=self._call(r,command)
            if r['account_alias'] is None:r['account_alias']=value['account_alias'];self._save(r)
            if op in {'start','cancel'} and e is not None and e['phase']=='PREPARED':e['phase']='WAIT'
            return dict(value,publication={k:r[k] for k in ('state','reason','manifest')})
    def tick(self):
        with self.manager.store._live(),_remote_scope(self.remote):
            active=[e for e in self.entries.values() if e['phase'] not in {'PREPARED','DONE','FAILED'}]
            if not active:return
            e=active[0];r=e['route']
            try:
                if e['phase']=='WAIT':
                    s=self._call(r,dict(operation='status',activity_id=r['activity_id']))
                    if s['evidence'] is None:
                        if s['state'] in {'INTERRUPTED','ABORTED','CANCELED'}:raise RuntimeRefused('PAPER_ACTIVITY_NO_EVIDENCE')
                        return
                    evidence=s['evidence'];_need(type(evidence) is dict and set(evidence)=={'size_bytes','sha256'})
                    _need(type(evidence['size_bytes']) is int and 0<evidence['size_bytes']<=_MAX and re.fullmatch('[0-9a-f]{64}',evidence['sha256']) is not None)
                    r.update(evidence=evidence,state='TRANSFERRING');self._save(r);e['phase']='COLLECT'
                elif e['phase']=='COLLECT':
                    offset=len(e['buffer']);expected=dict(project_id=self.manager.lease.project_id,account_alias=r['account_alias'],task_id=r['task_id'],activity_id=r['activity_id'],
                        sha256=r['evidence']['sha256'],total_bytes=r['evidence']['size_bytes'],offset=offset)
                    reply=call_owner(self.remote,'paper_activity_transfer',dict(operation='chunk',activity_id=r['activity_id'],offset=offset,sha256=expected['sha256']))
                    _need(type(reply) is dict and set(reply)==set(expected)|{'data'} and all(type(reply[k]) is type(v) and reply[k]==v for k,v in expected.items()))
                    _need(type(reply['data']) is str and len(reply['data'])<=43692)
                    chunk=base64.b64decode(reply['data'],validate=True);_need(len(chunk)==min(32768,expected['total_bytes']-offset));e['buffer'].extend(chunk)
                    if len(e['buffer'])==expected['total_bytes']:
                        _need(sha(e['buffer'])==expected['sha256'])
                        e['protected']=_ProtectedActivityEvidence(expected['project_id'],r['account_alias'],r['task_id'],r['activity_id'],bytes(e['buffer']),_factory=_FACTORY)
                        e['buffer'].clear();e['phase']='PUBLISH'
                elif e['phase']=='PUBLISH':
                    if e['child'] is None:e['child']=self.manager.split_grant(e['grant'],len(e['protected'].ciphertext))
                    m=publish_activity_evidence(self.manager,e['child'],e['protected']);r.update(manifest=m,state='ACK_PENDING');self._save(r);e['phase']='ACK'
                elif e['phase']=='ACK':
                    _need(r['ack_attempts']<2);r['ack_attempts']+=1;self._save(r)
                    value=call_owner(self.remote,'paper_activity_transfer',dict(operation='ack',activity_id=r['activity_id'],manifest=r['manifest']))
                    _need(value.get('state')=='PUBLISHED' and value.get('manifest')==r['manifest'] and value.get('evidence')==r['evidence'])
                    r['state']='PUBLISHED';r['reason']=None;self._save(r);e.update(phase='DONE',protected=None)
            except (RuntimeRefused,OSError,ValueError,TypeError,KeyError) as error:
                r['reason']='ACK_UNCONFIRMED' if e['phase']=='ACK' else 'PUBLICATION_FAILED'
                r['state']='ACK_UNCONFIRMED' if e['phase']=='ACK' else 'FAILED';e['phase']='FAILED'
                self._save(r)
