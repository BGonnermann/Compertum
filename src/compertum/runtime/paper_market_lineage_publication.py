"""Coordinator reservations, opaque lineage publication and ACK-only recovery."""
import base64,hashlib
from compertum.data.encoding import canonical
from compertum.events import uuid
from compertum.paper_contracts import strict_json
from compertum.persistence import checked_path
from compertum.storage import owner_of_grant
from .errors import RuntimeRefused
from .paper_market_lineage_records import task_id,validate_manifest,_hash
from .paper_market_lineage_routes import LineageRoutes,PURPOSE
from .paper_market_lineage_evidence import _ProtectedMarketLineage,_FACTORY,publish_market_lineage
from .paper_market_evidence import _pinned

_MAX=3*1024**2


def _need(value,code='MARKET_LINEAGE_PUBLICATION_INVALID'):
    if not value:raise RuntimeRefused(code)


class LineagePublication:
    def __init__(self,parent):
        self.parent=parent;self.manager=parent.manager;self.db=parent.db
        self.routes=LineageRoutes(self.db,self.manager.lease.project_id)
        self.entries={v['capture_id']:self._entry(v,phase='RECOVER') for v in self.routes.all()}

    def _entry(self,route,*,phase='REQUEST',grant=None):
        return dict(route=route,phase=phase,grant=grant,buffer=bytearray(),protected=None,child=None)

    def _call(self,action,payload):
        from .paper_market_publication import call_owner
        return call_owner(self.parent.remote,action,payload)

    def _check(self,r,result):
        _need(type(result) is dict and all(type(result.get(k)) is type(r[k]) and result[k]==r[k]
              for k in ('project_id','capture_id','job_id','task_id','account_alias','grant_sha256')))
        _need(result.get('use')=='HISTORICAL_ONLY' and result.get('freshness')=='NOT_RESTORED'
              and all(result.get(k) is False for k in ('financial_accepted','transport_authorized','research_eligible')))
        _need(len(canonical(result))<65536,'MARKET_SUMMARY_LIMIT');return result

    def _status(self,r):
        return self._check(r,self._call('paper_market_read',dict(subject_key=r['subject_key'],command=dict(operation='lineage_status',capture_id=r['capture_id']))))

    def _request(self,r,e):
        _need(e['phase']=='REQUEST' and e['grant'] is not None and owner_of_grant(e['grant']) is self.manager)
        _need(r['state']=='WAITING' and self.routes.read(r['capture_id'])==r)
        registration=self.parent.remote.descriptor.registration
        _need(registration.identity.process_instance_id==r['owner_instance'] and registration.generation==r['owner_generation'],'MARKET_OWNER_CHANGED')
        private={k:r[k] for k in ('capture_id','job_id','grant_sha256','task_id','reservation_id')}
        result=self._check(r,self._call('paper_market_read',dict(subject_key=r['subject_key'],command=dict(operation='publish_lineage',**private))))
        e['phase']='WAIT';return result

    def handle(self,subject,c):
        _need(_hash(subject),'CONTROL_PAYLOAD_DENIED')
        op=c['operation'];keys={'publish_lineage':{'operation','capture_id','job_id','grant_sha256'},'lineage_status':{'operation','capture_id'}}
        _need(op in keys and set(c)==keys[op],'CONTROL_PAYLOAD_DENIED');uuid(c['capture_id'])
        _need(not self.db.in_transaction,'MARKET_TRANSACTION_OPEN');known={v['capture_id'] for v in self.routes.all()}
        if c['capture_id'] in known:
            r=self.routes.read(c['capture_id']);_need(r['subject_key']==subject,'MARKET_OPERATOR_CHANGED')
            if op=='publish_lineage':_need(all(c[k]==r[k] for k in ('job_id','grant_sha256')),'MARKET_LINEAGE_CONFLICT')
            entry=self.entries.get(r['capture_id'])
            result=self._request(r,entry) if op=='publish_lineage' and entry is not None and entry['phase']=='REQUEST' else self._status(r)
        else:
            _need(op=='publish_lineage','MARKET_LINEAGE_UNKNOWN');uuid(c['job_id']);_need(_hash(c['grant_sha256']))
            _need(not any(e['phase'] not in {'DONE','FAILED'} or e['protected'] is not None or e['buffer'] for e in self.entries.values()),'MARKET_LINEAGE_CAPACITY')
            f=self.parent._route(c['job_id']);_need(f['subject_key']==subject,'MARKET_OPERATOR_CHANGED')
            _need(f['mode']=='FRESH' and f['grant_sha256']==c['grant_sha256'],'MARKET_LINEAGE_CONFLICT')
            status=self.parent._call(f,dict(operation='status',job_id=f['job_id']));_need(status['state']=='COMPLETE','MARKET_FRESH_UNAVAILABLE')
            history=self.parent._history(subject,dict(history_job_id=f['history_job_id'],account_alias=f['account_alias'],symbol=f['symbol']))
            task=task_id(f['project_id'],c['capture_id'])
            _need(self.db.execute('SELECT 1 FROM reservations WHERE task=?',(task,)).fetchone() is None,'MARKET_STORAGE_REUSED')
            _need(len(known)<32,'MARKET_LINEAGE_HISTORY_BOUND')
            registration=self.parent.remote.descriptor.registration
            grant=self.manager.reserve_bytes(task,'records',_MAX)
            r=dict(version=1,purpose=PURPOSE,capture_id=c['capture_id'],task_id=task,reservation_id=grant.grant_id,
                   project_id=f['project_id'],subject_key=subject,account_alias=f['account_alias'],job_id=f['job_id'],grant_sha256=f['grant_sha256'],
                   history=history,owner_instance=registration.identity.process_instance_id,owner_generation=registration.generation,
                   state='WAITING',reason=None,lineage_sha256=None,evidence=None,manifest=None)
            with self.db:self.routes.write(r,new=True)
            self.entries[r['capture_id']]=self._entry(r,grant=grant)
            result=self._request(r,self.entries[r['capture_id']])
        route=self.routes.read(r['capture_id'])
        return dict(result,publication={k:route[k] for k in ('state','reason','manifest')})

    def _ledger_manifest(self,r):
        task=r['task_id'];path=f'artifacts/runs/{task}/market-lineage-{r["capture_id"]}.bin';evidence=r['evidence']
        _need(evidence is not None,'MARKET_LINEAGE_PUBLICATION_UNVERIFIED')
        rows=self.db.execute('SELECT task,category,maximum,written,status,path,CASE WHEN length(manifest)<=4096 THEN manifest END FROM reservations WHERE path=? LIMIT 2',(path,)).fetchall()
        _need(len(rows)==1,'MARKET_LINEAGE_PUBLICATION_UNVERIFIED');row=rows[0]
        try:m=strict_json(row[6].encode());validate_manifest(m,task,r['capture_id'])
        except (TypeError,ValueError,AttributeError):raise RuntimeRefused('MARKET_LINEAGE_PUBLICATION_UNVERIFIED') from None
        _need(row==(task,'records',m['size_bytes'],m['size_bytes'],'PUBLISHED',path,canonical(m).decode()))
        _need(all(m[k]==evidence[k] for k in ('size_bytes','sha256')) and (r['manifest'] is None or r['manifest']==m))
        parent=self.db.execute('SELECT task,category,maximum,written,status,path,manifest FROM reservations WHERE id=?',(r['reservation_id'],)).fetchone()
        _need(parent==(task,'records',_MAX,m['size_bytes'],'SPLIT',None,None))
        with self.manager.store._live() as guard:
            file=checked_path(self.manager.root,self.manager.root/path)
            with _pinned(guard,file):raw=guard.api.read_regular(file,maximum=_MAX)
            _need(len(raw)==m['size_bytes'] and hashlib.sha256(raw).hexdigest()==m['sha256'])
        return m

    def tick(self):
        ready=[e for e in self.entries.values() if e['phase'] not in {'REQUEST','DONE','FAILED'}]
        if not ready:return
        e=ready[0];r=e['route'];cid=r['capture_id']
        try:
            _need(self.routes.read(cid)==r,'MARKET_LINEAGE_ROUTE_WRITE_UNVERIFIED')
            if e['phase']=='RECOVER':
                manifest=self._ledger_manifest(r)
                if r['state']!='PUBLISHED':
                    r.update(state='TRANSFERRING',reason=None,manifest=manifest)
                    with self.db:self.routes.write(r)
                e['phase']='ACK'
            elif e['phase']=='WAIT':
                s=self._status(r)
                if s.get('state')=='CAPTURING':return
                _need(s.get('state')=='READY','MARKET_LINEAGE_UNAVAILABLE')
                r.update(state='TRANSFERRING',lineage_sha256=s['lineage_sha256'],evidence=s['evidence'])
                with self.db:self.routes.write(r)
                e['phase']='COLLECT'
            elif e['phase']=='COLLECT':
                expected={k:r[k] for k in ('project_id','capture_id','job_id','task_id','account_alias','grant_sha256')}
                expected.update(sha256=r['evidence']['sha256'],total_bytes=r['evidence']['size_bytes'],offset=len(e['buffer']))
                reply=self._call('paper_market_transfer',dict(operation='lineage_chunk',capture_id=cid,offset=expected['offset'],sha256=expected['sha256']))
                _need(type(reply) is dict and set(reply)==set(expected)|{'data'} and all(type(reply[k]) is type(v) and reply[k]==v for k,v in expected.items()))
                _need(type(reply['data']) is str and len(reply['data'])<=43692)
                try:chunk=base64.b64decode(reply['data'],validate=True)
                except ValueError:raise RuntimeRefused('MARKET_LINEAGE_PUBLICATION_INVALID') from None
                _need(len(chunk)==min(32768,expected['total_bytes']-expected['offset']));e['buffer'].extend(chunk)
                if len(e['buffer'])==expected['total_bytes']:
                    _need(hashlib.sha256(e['buffer']).hexdigest()==expected['sha256'])
                    e['protected']=_ProtectedMarketLineage(r['project_id'],r['account_alias'],r['task_id'],cid,bytes(e['buffer']),_factory=_FACTORY)
                    e['buffer'].clear();e['phase']='PUBLISH'
            elif e['phase']=='PUBLISH':
                if e['child'] is None:e['child']=self.manager.split_grant(e['grant'],len(e['protected'].ciphertext))
                r['manifest']=publish_market_lineage(self.manager,e['child'],e['protected'])
                with self.db:self.routes.write(r)
                e['phase']='ACK'
            elif e['phase']=='ACK':
                manifest=self._ledger_manifest(r);_need(self.routes.read(cid)['manifest']==manifest,'MARKET_LINEAGE_ROUTE_WRITE_UNVERIFIED')
                reply=self._check(r,self._call('paper_market_transfer',dict(operation='lineage_ack',capture_id=cid,manifest=manifest)))
                _need(reply.get('state')=='PUBLISHED' and reply.get('manifest')==manifest and reply.get('evidence')==r['evidence'] and reply.get('lineage_sha256')==r['lineage_sha256'])
                r.update(state='PUBLISHED',reason=None)
                with self.db:self.routes.write(r)
                e.update(phase='DONE',protected=None);e['buffer'].clear()
        except (RuntimeRefused,OSError) as error:
            e['phase']='FAILED'
            # Retain ciphertext after failed publication/ACK. Recovery uses only
            # the committed ledger; it never reconstructs a grant or capture.
            if r['state'] not in {'FAILED','PUBLISHED'}:
                r.update(state='FAILED',reason=error.code if isinstance(error,RuntimeRefused) else 'MARKET_LINEAGE_PUBLICATION_IO_FAILED')
                with self.db:self.routes.write(r)
