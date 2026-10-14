"""Execution-owned capture queue and bounded opaque transfer; no data dispatch."""
import base64,hashlib
from compertum.data.encoding import canonical
from compertum.events import uuid
from compertum.paper_contracts import strict_json
from .errors import RuntimeRefused
from .owners import _owner_scope
from .paper_credential_slot import _coordinator_records,load_paper_slot
from .paper_credentials import open_paper_credentials
from .paper_market_collection import _scan_generated
from .paper_market_grants import MarketGrant
from .paper_market_lineage_records import LineageCaptureRecords,initial_capture,IMMUTABLE,_hash
from .paper_market_lineage_routes import validate_route,VERSION as ROUTE_VERSION,PREFIX as ROUTE_PREFIX
from .paper_market_lineage_evidence import protect_market_lineage,open_market_lineage


def _need(value,code='MARKET_LINEAGE_TRANSFER_INVALID'):
    if not value:raise RuntimeRefused(code)


class LineageTransfer:
    def __init__(self,owner):
        self.owner=owner;self.db=owner.db;self.records=LineageCaptureRecords(owner.records)
        self.records.interrupt_unfinished();self._pending=None;self._cipher=None;self._offset=0;self._previous=None

    def require_clear(self,code='MARKET_LINEAGE_CAPACITY'):
        _need(self._pending is None and self._cipher is None,code)

    def _route(self,v,manifest=None):
        with _owner_scope(self.owner.lease) as guard,_coordinator_records(guard) as db:
            _need(db.execute('SELECT value FROM state WHERE key=?',(ROUTE_VERSION,)).fetchone()==('1',),'MARKET_LINEAGE_STORAGE_UNVERIFIED')
            row=db.execute('SELECT CASE WHEN length(value)<=16384 THEN value END FROM state WHERE key=?',(ROUTE_PREFIX+v['capture_id'],)).fetchone()
            try:r=validate_route(strict_json(row[0].encode()),v['project_id'])
            except (TypeError,ValueError,AttributeError):raise RuntimeRefused('MARKET_LINEAGE_STORAGE_UNVERIFIED') from None
            _need(all(r[k]==v[k] for k in IMMUTABLE-{'purpose'}),'MARKET_LINEAGE_STORAGE_UNVERIFIED')
            parent=db.execute('SELECT task,category,maximum,written,status,path,manifest FROM reservations WHERE id=?',(v['reservation_id'],)).fetchone()
            if manifest is None:
                _need(r['state']=='WAITING' and r['evidence'] is None and r['manifest'] is None,'MARKET_LINEAGE_STORAGE_UNVERIFIED')
                expected=(v['task_id'],'records',3*1024**2,0,'RESERVED',None,None)
            else:
                _need(r['manifest']==manifest and r['evidence']==v['evidence'] and r['lineage_sha256']==v['lineage_sha256'],'MARKET_LINEAGE_STORAGE_UNVERIFIED')
                expected=(v['task_id'],'records',3*1024**2,manifest['size_bytes'],'SPLIT',None,None)
                rows=db.execute('SELECT task,category,maximum,written,status,manifest FROM reservations WHERE path=? LIMIT 2',(manifest['path'],)).fetchall()
                _need(rows==[(v['task_id'],'records',manifest['size_bytes'],manifest['size_bytes'],'PUBLISHED',canonical(manifest).decode())],'MARKET_LINEAGE_STORAGE_UNVERIFIED')
            _need(parent==expected,'MARKET_LINEAGE_STORAGE_UNVERIFIED')

    def _public(self,v):
        result={k:v[k] for k in ('capture_id','task_id','project_id','account_alias','job_id','grant_sha256','state','reason','lineage_sha256','evidence','manifest')}
        result.update(version=1,record_type='NativePaperMarketLineageReceipt',use='HISTORICAL_ONLY',freshness='NOT_RESTORED',
                      financial_accepted=False,transport_authorized=False,research_eligible=False)
        _need(len(canonical(result))<65536,'MARKET_SUMMARY_LIMIT')
        protected=load_paper_slot(self.owner.lease,v['account_alias'])
        with open_paper_credentials(self.owner.lease,protected) as opened:_scan_generated(result,tuple(opened.headers().values()))
        return result

    def handle(self,subject,c):
        op=c['operation'];keys={'publish_lineage':{'operation','capture_id','job_id','grant_sha256','task_id','reservation_id'},
                              'lineage_status':{'operation','capture_id'}}
        _need(op in keys and set(c)==keys[op],'CONTROL_PAYLOAD_DENIED');uuid(c['capture_id'])
        _need(not self.db.in_transaction,'MARKET_TRANSACTION_OPEN')
        known={v['capture_id'] for v in self.records.all()}
        if c['capture_id'] in known:
            v=self.records.read(c['capture_id']);_need(v['subject_key']==subject,'MARKET_OPERATOR_CHANGED')
            if op=='publish_lineage':_need(all(c[k]==v[k] for k in ('job_id','grant_sha256','task_id','reservation_id')),'MARKET_LINEAGE_CONFLICT')
            return self._public(v)
        _need(op=='publish_lineage','MARKET_LINEAGE_UNKNOWN');uuid(c['job_id']);uuid(c['task_id']);uuid(c['reservation_id']);_need(_hash(c['grant_sha256']))
        self.require_clear();o=self.owner
        _need(o._active is None and o._cipher is None and not o._cleanup_failed,'MARKET_OWNER_CAPACITY')
        fresh=o.records.read(c['job_id']);g=fresh['grant']
        _need(g['subject_key']==subject and fresh['grant_sha256']==c['grant_sha256'],'MARKET_LINEAGE_CONFLICT')
        _need(fresh['state']=='COMPLETE' and o._fresh_job==c['job_id'] and o._fresh_view is not None,'MARKET_FRESH_UNAVAILABLE')
        _need(g['owner_instance']==o.lease.identity.process_instance_id and g['owner_generation']==o.lease.generation,'MARKET_OWNER_CHANGED')
        o._fresh_current(fresh);v=initial_capture(MarketGrant(canonical(g)),capture_id=c['capture_id'],reservation_id=c['reservation_id'])
        _need(v['task_id']==c['task_id']);self._route(v)
        with self.db:self.records.write(v,new=True)
        _need(not self.db.in_transaction and self.records.read(v['capture_id'])==v,'MARKET_LINEAGE_WRITE_UNVERIFIED')
        self._pending=v['capture_id'];return self._public(v)

    def tick(self):
        if self._pending is None:return
        v=self.records.read(self._pending);_need(v['state']=='CAPTURING')
        try:
            self._route(v)
            try:
                lineage=self.owner._capture_lineage(subject=v['subject_key'],job_id=v['job_id'],grant_sha256=v['grant_sha256'])
                self._cipher=protect_market_lineage(self.owner,lineage,task_id=v['task_id'],capture_id=v['capture_id'])
            except RuntimeRefused as error:
                self.owner._invalidate_fresh(v['job_id'],error.code)
                raise
            v.update(state='READY',lineage_sha256=hashlib.sha256(lineage.content).hexdigest(),
                     evidence=dict(size_bytes=len(self._cipher.ciphertext),sha256=hashlib.sha256(self._cipher.ciphertext).hexdigest()))
            with self.db:self.records.write(v)
            _need(not self.db.in_transaction and self.records.read(v['capture_id'])==v,'MARKET_LINEAGE_WRITE_UNVERIFIED')
            self._pending=None
        except (RuntimeRefused,OSError) as error:
            v.update(state='FAILED',reason=error.code if isinstance(error,RuntimeRefused) else 'MARKET_LINEAGE_CAPTURE_IO_FAILED')
            with self.db:self.records.write(v)
            self._pending=None

    def transfer(self,payload):
        op=payload['operation'];keys={'lineage_chunk':{'operation','capture_id','offset','sha256'},'lineage_ack':{'operation','capture_id','manifest'}}
        _need(op in keys and set(payload)==keys[op]);uuid(payload['capture_id'])
        _need(not self.db.in_transaction,'MARKET_TRANSACTION_OPEN')
        v=self.records.read(payload['capture_id']);e=v['evidence'];_need(e is not None,'MARKET_LINEAGE_UNAVAILABLE')
        if op=='lineage_ack':
            manifest=payload['manifest'];_need(type(manifest) is dict and all(manifest.get(k)==e[k] for k in ('size_bytes','sha256')))
            self._route(v,manifest)
            with open_market_lineage(self.owner,account_alias=v['account_alias'],capture_id=v['capture_id'],manifest=manifest) as opened:
                s=opened.snapshot();meta=s['metadata']
                expected=dict(project_id=v['project_id'],account_alias=v['account_alias'],task_id=v['task_id'],capture_id=v['capture_id'],
                              fresh_job_id=v['job_id'],fresh_grant_sha256=v['grant_sha256'],execution_instance=v['owner_instance'],
                              execution_generation=v['owner_generation'],lineage_sha256=v['lineage_sha256'])
                _need(all(meta[k]==value for k,value in expected.items()))
            if v['state']!='PUBLISHED':
                v.update(state='PUBLISHED',reason=None,manifest=manifest)
                with self.db:self.records.write(v)
                _need(not self.db.in_transaction and self.records.read(v['capture_id'])==v,'MARKET_LINEAGE_WRITE_UNVERIFIED')
            else:_need(v['manifest']==manifest)
            if self._cipher is not None and self._cipher.capture_id==v['capture_id']:
                self._cipher=None;self._offset=0;self._previous=None
            return self._public(v)
        cipher=self._cipher;_need(v['state']=='READY' and cipher is not None and cipher.capture_id==v['capture_id'],'MARKET_LINEAGE_UNAVAILABLE')
        cipher._verify();_need((cipher.project_id,cipher.account_alias,cipher.task_id)==(v['project_id'],v['account_alias'],v['task_id']))
        _need(payload['sha256']==e['sha256']==hashlib.sha256(cipher.ciphertext).hexdigest() and len(cipher.ciphertext)==e['size_bytes'])
        at=payload['offset'];_need(type(at) is int and 0<=at<e['size_bytes'] and at in (self._offset,self._previous),'MARKET_TRANSFER_ORDER')
        data=cipher.ciphertext[at:at+32768]
        if at==self._offset:self._previous=at;self._offset+=len(data)
        result={k:v[k] for k in ('project_id','capture_id','job_id','task_id','account_alias','grant_sha256')}
        return dict(result,sha256=e['sha256'],total_bytes=e['size_bytes'],offset=at,data=base64.b64encode(data).decode())

    def close(self):
        self.records.interrupt_unfinished();self._pending=None;self._cipher=None;self._offset=0;self._previous=None
