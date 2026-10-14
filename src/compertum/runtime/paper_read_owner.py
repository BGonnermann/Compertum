"""Execution-owned read grants and cooperative dispatch; no order capability.

Only the native authenticated coordinator route may call handle. Account reads
still need the human operator's exact plan authorization. No caller transport,
credentials, wall clock, health assertion or account UUID is accepted.
"""
from datetime import datetime,timedelta,timezone
import base64,hashlib,json,re,time
from uuid import uuid4
from zoneinfo import ZoneInfo
from compertum.data.encoding import canonical
from compertum.domain import ContractError
from compertum.events import uuid
from compertum.paper_contracts import timestamp,strict_json
from compertum.paper_read_preparation import PreparedReadPlan,prepare_read_plan
from compertum.persistence import StateStore
from compertum.storage import JournalReserve
from .errors import RuntimeRefused
from .service_budget import producer_permit,cancel_producer,bind_producer_permit
from .owners import _MUTEX,_owner_scope,require_live_owner
from .execution_health import MutualHealth,execution_durable
from .paper_credential_slot import load_paper_slot,_coordinator_records
from .paper_credentials import open_paper_credentials
from .paper_read_secrecy import _reject_reflections
from .paper_read_packet import _ReadPacket
from .paper_read_evidence import protect_read_evidence,open_read_evidence
from ._winhttp_get import _OwnedGet

_CIPHER_MAX=3*1024**2
_IMMUTABLE=('packet_id','task_id','account_alias','reservation_id','project_id','owner_instance','owner_generation','subject_key','credential_sha256','plan','plan_sha256','prepared_mono')
_MUTABLE=('state','consumed','requests','responses','reason','evidence','packet_status')
_STATES={'PREPARED','GRANTED','RUNNING','EVIDENCE_READY','ABORTED','CANCELED','INTERRUPTED','PUBLISHED'}


def _start_get(lease,request,protected,timeout,*,_permit=None):
    with open_paper_credentials(lease,protected) as opened:
        return _OwnedGet(lease,host='paper-api.alpaca.markets',port=443,secure=True,
                         path=request.to_payload()['target'],headers=opened.headers(),timeout=timeout,_permit=_permit,_read_request=request)


def _now():return datetime.fromtimestamp(time.time(),timezone.utc).isoformat()
def _hash(value):return hashlib.sha256(canonical(value)).hexdigest()
def _binding(value):return _hash({k:value[k] for k in _IMMUTABLE})
def _need(value,code='READ_STATE_CORRUPT'):
    if not value:raise RuntimeRefused(code)


class PaperReadOwner:
    def __init__(self,store,reserve,health):
        if type(store) is not StateStore or type(reserve) is not JournalReserve or type(health) is not MutualHealth:raise RuntimeRefused('WRONG_OWNER_ROLE')
        require_live_owner(store.lease,'execution')
        if reserve.lease is not store.lease or health.lease is not store.lease:raise RuntimeRefused('OWNER_UNVERIFIED')
        self.store=store;self.reserve=reserve;self.health=health;self.lease=store.lease;self.db=store.conn
        self._preflight=None;self._read_provenance=[];self._account_proposal=None
        self._market=None
        self._active=None;self._packet=None;self._get=None;self._cipher=None;self._closed=False;self._transfer_offset=0;self._last_offset=None
        with _owner_scope(self.lease) as guard,store._live(),self.db:
            if any(type(r) is PaperReadOwner and not r._closed for r in guard.resources):raise RuntimeRefused('READ_OWNER_CAPACITY')
            present=self.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='paper_read_packets'").fetchone() is not None
            version=self.db.execute("SELECT value FROM state WHERE key='paper_read_owner_version'").fetchone()
            _need(present==(version is not None) and (version is None or version==('1',)))
            if not present:
                self.db.execute('CREATE TABLE paper_read_packets(packet_id TEXT PRIMARY KEY,binding TEXT NOT NULL,body TEXT NOT NULL)')
                changed=self.db.execute("INSERT INTO state VALUES('paper_read_owner_version','1')")
                _need(changed.rowcount==1,'READ_WRITE_UNVERIFIED')
            rows=self.db.execute('SELECT packet_id FROM paper_read_packets LIMIT 33').fetchall();_need(len(rows)<=32)
            for (packet_id,) in rows:
                value=self._read(packet_id)
                if value['state'] in {'PREPARED','GRANTED','RUNNING','EVIDENCE_READY'}:
                    value.update(state='INTERRUPTED',reason='OWNER_RESTARTED');self._write(value)
            guard.resources.append(self);self._guard=guard
        try:
            with _owner_scope(self.lease),store._live():
                if self.db.execute("SELECT 1 FROM state WHERE key='paper_market_owner_version' OR substr(key,1,17)='paper_market_job:' LIMIT 1").fetchone():
                    self._market_helper()
        except BaseException:self.close();raise

    def __repr__(self):return '<PaperReadOwner private state redacted>'
    def __reduce_ex__(self,protocol):raise RuntimeRefused('PAPER_READ_PRIVATE_SERIALIZATION_FORBIDDEN')

    def _read(self,packet_id):
        row=self.db.execute('SELECT binding,CASE WHEN length(body)<=32768 THEN body ELSE NULL END FROM paper_read_packets WHERE packet_id=?',(packet_id,)).fetchone()
        if row is None:raise RuntimeRefused('READ_PACKET_UNKNOWN')
        try:
            value=strict_json(row[1].encode())
            _need(type(value) is dict and set(value)==set(_IMMUTABLE+_MUTABLE))
            _need(_binding(value)==row[0] and value['packet_id']==packet_id)
            plan=PreparedReadPlan(canonical(value['plan']))
            _need(plan.sha256==value['plan_sha256'] and value['project_id']==self.lease.project_id and value['plan']['project_id']==value['project_id'] and value['plan']['account_alias']==value['account_alias'])
            for k in ('packet_id','task_id','reservation_id','owner_instance'):uuid(value[k])
            for k in ('subject_key','credential_sha256'):_need(type(value[k]) is str and re.fullmatch('[0-9a-f]{64}',value[k]) is not None)
            _need(type(value['owner_generation']) is int and value['owner_generation']>0)
            _need(type(value['prepared_mono']) in (int,float) and 0<=value['prepared_mono']<1e15)
            _need(value['state'] in _STATES and type(value['consumed']) is bool)
            _need(type(value['requests']) is list and len(value['requests'])<=13 and type(value['responses']) is int and 0<=value['responses']<=len(value['requests']))
            _need(value['reason'] is None or type(value['reason']) is str and re.fullmatch('[A-Z0-9_]{1,80}',value['reason']) is not None)
            ids=set()
            for r in value['requests']:
                _need(type(r) is dict and set(r)=={'request_id','request_sha256','http_status'})
                uuid(r['request_id']);_need(r['request_id'] not in ids);ids.add(r['request_id'])
                _need(type(r['request_sha256']) is str and re.fullmatch('[0-9a-f]{64}',r['request_sha256']) is not None)
                _need(r['http_status'] is None or type(r['http_status']) is int and 100<=r['http_status']<=599)
            _need(value['state'] not in {'PREPARED','GRANTED'} or not value['consumed'])
            _need(value['state'] not in {'RUNNING','EVIDENCE_READY','PUBLISHED'} or value['consumed'])
            _need(not value['requests'] or value['consumed'])
            if value['evidence'] is not None:
                e=value['evidence'];_need(type(e) is dict and set(e)=={'size_bytes','sha256'})
                _need(type(e['size_bytes']) is int and 0<e['size_bytes']<=_CIPHER_MAX and type(e['sha256']) is str and re.fullmatch('[0-9a-f]{64}',e['sha256']) is not None)
            return value
        except (ValueError,TypeError,AttributeError,KeyError,ContractError):raise RuntimeRefused('READ_STATE_CORRUPT') from None

    def _write(self,value,*,new=False):
        raw=canonical(value).decode();_need(len(raw.encode())<=32768,'READ_STATE_BOUND')
        if new:changed=self.db.execute('INSERT INTO paper_read_packets VALUES(?,?,?)',(value['packet_id'],_binding(value),raw))
        else:changed=self.db.execute('UPDATE paper_read_packets SET body=? WHERE packet_id=? AND binding=?',(raw,value['packet_id'],_binding(value)))
        _need(changed.rowcount==1 and self._read(value['packet_id'])==value,'READ_WRITE_UNVERIFIED')

    def _ready(self):
        _need(self.health.status()['verified'] is True,'EXECUTION_HEALTH_UNVERIFIED');execution_durable(self.store,self.reserve)

    def _reservation(self,value):
        with _owner_scope(self.lease) as guard,_coordinator_records(guard) as db:
            rows=db.execute('SELECT task,category,maximum,written,status,path FROM reservations WHERE id=? LIMIT 2',(value['reservation_id'],)).fetchall()
            _need(rows==[(value['task_id'],'records',_CIPHER_MAX,0,'RESERVED',None)],'READ_STORAGE_UNVERIFIED')

    def _live_grant(self,value):
        _need(value['owner_instance']==self.lease.identity.process_instance_id and value['owner_generation']==self.lease.generation,'READ_OWNER_CHANGED')
        p=value['plan'];elapsed=time.monotonic()-value['prepared_mono'];now=timestamp(_now())
        _need(0<=elapsed<60 and timestamp(p['created_at'])<=now<timestamp(p['start_expires_at']),'READ_GRANT_EXPIRED')
        _need(abs((now-timestamp(p['created_at'])).total_seconds()-elapsed)<=5,'READ_GRANT_EXPIRED')
        self._ready();self._reservation(value)
        protected=load_paper_slot(self.lease,value['account_alias'])
        _need(hashlib.sha256(protected.ciphertext).hexdigest()==value['credential_sha256'],'READ_CREDENTIAL_CHANGED')
        return protected

    def _public(self,value):
        return dict(version=1,record_type='NativePaperReadReceipt',scope='ACCOUNT_READ_ONLY',packet_id=value['packet_id'],task_id=value['task_id'],
            account_alias=value['account_alias'],plan_sha256=value['plan_sha256'],plan=value['plan'],state=value['state'],consumed=value['consumed'],
            reason=value['reason'],attempts=len(value['requests']),responses=value['responses'],requests=value['requests'],evidence=value['evidence'],financial_accepted=False)

    def handle(self,packet):
        with _owner_scope(self.lease),self.store._live():
            _need(not self._closed,'READ_OWNER_CLOSED')
            _need(type(packet) is dict and set(packet)=={'subject_key','command'},'CONTROL_PAYLOAD_DENIED')
            subject=packet['subject_key'];command=packet['command']
            _need(type(subject) is str and re.fullmatch('[0-9a-f]{64}',subject) is not None,'CONTROL_PAYLOAD_DENIED')
            _need(type(command) is dict and type(command.get('operation')) is str,'CONTROL_PAYLOAD_DENIED')
            op=command['operation'];keys={'prepare':{'operation','packet_id','task_id','account_alias','reservation_id'},'authorize':{'operation','packet_id','plan_sha256'},'start':{'operation','packet_id','plan_sha256'},'status':{'operation','packet_id'},'cancel':{'operation','packet_id'},'account_propose':{'operation','packet_id','manifest'},'account_confirm':{'operation','packet_id','manifest','proposal_sha256','acknowledgement'},'account_status':{'operation','packet_id','manifest'}}
            _need(op in keys and set(command)==keys[op],'CONTROL_PAYLOAD_DENIED');uuid(command['packet_id'])
            _need(not self.db.in_transaction,'READ_TRANSACTION_OPEN')
            if op=='prepare':return self._prepare(subject,command)
            value=self._read(command['packet_id']);_need(value['subject_key']==subject,'READ_OPERATOR_CHANGED')
            if op in {'account_propose','account_confirm','account_status'}:
                from .paper_account_binding import handle_binding
                return handle_binding(self,subject,value,command)
            if op in {'authorize','start'}:_need(value['plan_sha256']==command['plan_sha256'],'READ_PLAN_CHANGED')
            if op=='status':return self._public(value)
            if op=='cancel':
                if self._active==value['packet_id']:self._stop('CANCELED','OPERATOR_CANCELED')
                elif value['state'] in {'PREPARED','GRANTED'}:
                    with self.db:value.update(state='CANCELED',reason='OPERATOR_CANCELED');self._write(value)
                return self._public(self._read(value['packet_id']))
            if value['consumed']:return self._public(value)
            _need(value['state'] in {'PREPARED','GRANTED'},'READ_GRANT_REQUIRED')
            protected=self._live_grant(value)
            if op=='authorize':
                with self.db:value['state']='GRANTED';self._write(value)
            else:
                _need(value['state']=='GRANTED','READ_GRANT_REQUIRED');_need(self._active is None and self._cipher is None,'READ_OWNER_CAPACITY')
                with self.db:value.update(state='RUNNING',consumed=True);self._write(value)
                # Durable commit precedes every possible native request.
                self._clear_preflight();self._read_provenance=[]
                self._active=value['packet_id']
                try:self._packet=_ReadPacket(self.lease,PreparedReadPlan(canonical(value['plan'])),protected,started_at=_now())
                except RuntimeRefused as error:self._stop('ABORTED',error.code)
            return self._public(self._read(value['packet_id']))

    def _prepare(self,subject,command):
        packet_id=command['packet_id']
        if self.db.execute('SELECT 1 FROM paper_read_packets WHERE packet_id=?',(packet_id,)).fetchone():
            value=self._read(packet_id)
            _need(all(value[k]==command[k] for k in ('task_id','account_alias','reservation_id')) and value['subject_key']==subject,'READ_PACKET_CONFLICT')
            return self._public(value)
        _need(self._active is None and self._cipher is None,'READ_OWNER_CAPACITY');self._ready()
        for k in ('task_id','reservation_id'):uuid(command[k])
        protected=load_paper_slot(self.lease,command['account_alias']);at=datetime.fromtimestamp(time.time(),timezone.utc)
        plan=prepare_read_plan(project_id=self.lease.project_id,account_alias=command['account_alias'],created_at=at.isoformat(),start_expires_at=(at+timedelta(seconds=60)).isoformat(),session_date=at.astimezone(ZoneInfo('America/New_York')).date().isoformat())
        value=dict(packet_id=packet_id,task_id=command['task_id'],account_alias=command['account_alias'],reservation_id=command['reservation_id'],project_id=self.lease.project_id,
            owner_instance=self.lease.identity.process_instance_id,owner_generation=self.lease.generation,subject_key=subject,credential_sha256=hashlib.sha256(protected.ciphertext).hexdigest(),
            plan=plan.to_payload(),plan_sha256=plan.sha256,prepared_mono=time.monotonic(),state='PREPARED',consumed=False,requests=[],responses=0,reason=None,evidence=None,packet_status=None)
        with open_paper_credentials(self.lease,protected) as opened:_reject_reflections(canonical(value),tuple(opened.headers().values()))
        self._reservation(value)
        with self.db:
            _need(self.db.execute('SELECT count(*) FROM paper_read_packets').fetchone()[0]<32,'READ_HISTORY_BOUND')
            _need(self.db.execute('SELECT 1 FROM paper_read_packets WHERE json_extract(body,\'$.task_id\')=? OR json_extract(body,\'$.reservation_id\')=?',(value['task_id'],value['reservation_id'])).fetchone() is None,'READ_STORAGE_REUSED')
            self._write(value,new=True)
        self._clear_preflight()
        return self._public(value)

    def _clear_preflight(self):
        if self._account_proposal is not None:self._account_proposal.close();self._account_proposal=None
        if self._preflight is not None:self._preflight.close();self._preflight=None

    def preflight(self,packet_id):
        # Private in-process reader; no operator RPC operation accepts this.
        _need(self._preflight is not None,'PAPER_PREFLIGHT_UNAVAILABLE')
        _need(self._preflight.diagnostic()['packet_id']==packet_id,'PAPER_PREFLIGHT_UNAVAILABLE')
        return self._preflight

    def opening_history(self,account_alias):
        from .paper_opening import opening_history
        return opening_history(self,account_alias)

    def opening(self,packet_id,manifest):
        from .paper_opening import current_opening
        return current_opening(self,packet_id,manifest)

    def _dispose_get(self):
        if self._get is not None:
            self._get.close();_need(self._get.native_closed,'HTTP_CLEANUP_UNVERIFIED');self._get=None

    def _finish(self,value):
        if self._packet is not None:
            status=self._packet.status();value['responses']=status['responses'];value['packet_status']={k:status[k] for k in ('state','reason','orders_coverage','positions','orders','order_pages')}
            value['packet_status'].update(deficiency_count=len(status['deficiencies']),status_sha256=_hash(status))
            if status['responses'] and self._cipher is None:
                self._cipher=protect_read_evidence(self.lease,self._packet,task_id=value['task_id'],packet_id=value['packet_id'])
            if self._cipher is not None:
                value['evidence']=dict(size_bytes=len(self._cipher.ciphertext),sha256=hashlib.sha256(self._cipher.ciphertext).hexdigest())
        if self._packet is not None and value['state']=='EVIDENCE_READY' and self._packet.status()['state']=='PREPARATION_COMPLETE':
            from .paper_preflight import capture_preflight
            self._clear_preflight();self._preflight=capture_preflight(self,value)
        with self.db:self._write(value)
        if self._packet is not None:self._packet.close();self._packet=None
        self._active=None

    def _stop(self,state,reason):
        cancel_producer(self)
        if self._active is None:return
        value=self._read(self._active);value.update(state=state,reason=reason)
        try:self._dispose_get()
        except RuntimeRefused:
            value.update(state='ABORTED',reason='HTTP_CLEANUP_UNVERIFIED')
            with self.db:self._write(value)
            raise
        if self._packet is not None:
            # Preserve qualified prefix until sealing; never accept a pending body.
            if self._packet.status()['state'] in {'READY','PENDING'}:self._packet.finish_failed()
        self._finish(value)

    def _market_helper(self):
        if self._market is None:
            from .paper_market_owner import _MarketOwner
            self._market=_MarketOwner(self)
        return self._market

    def market_handle(self,packet):
        with _owner_scope(self.lease),self.store._live():
            _need(not self._closed,'READ_OWNER_CLOSED')
            return self._market_helper().handle(packet)

    def market_transfer(self,payload):
        with _owner_scope(self.lease),self.store._live():
            _need(not self._closed,'READ_OWNER_CLOSED')
            return self._market_helper().transfer(payload)

    def tick(self):
        with _owner_scope(self.lease),self.store._live():
            if self._closed:return
            self._tick_account()
            if self._market is not None:self._market.tick()

    def _tick_account(self):
        with _owner_scope(self.lease),self.store._live():
            if self._closed or self._active is None:return
            value=self._read(self._active)
            try:
                self._ready();self._packet.remaining_seconds()
                if self._get is None:
                    permit=producer_permit(self)
                    if permit is None:return
                    request=self._packet.issue(now=_now(),request_id=str(uuid4()))
                    bind_producer_permit(self,permit)
                    value['requests'].append(dict(request_id=request.to_payload()['request_id'],request_sha256=request.sha256,http_status=None))
                    with self.db:self._write(value)
                    self._get=_start_get(self.lease,request,self._packet._protected,min(request.to_payload()['timeout_ms']/1000,self._packet.remaining_seconds()),_permit=permit)
                else:
                    result=self._get.poll()
                    if result is None:return
                    value['requests'][-1]['http_status']=result.status_code
                    with self.db:self._write(value)
                    transport=self._get;request=self._packet._pending
                    self._dispose_get()
                    self._packet.accept(result.body,received_at=_now())
                    from .paper_preflight import native_read_provenance
                    self._read_provenance.append(native_read_provenance(transport,result,self.lease,request))
                    status=self._packet.status();value['responses']=status['responses']
                    if status['state'] not in {'READY','PENDING'}:
                        value.update(state='EVIDENCE_READY',reason=status['reason']);self._finish(value)
                    else:
                        with self.db:self._write(value)
            except RuntimeRefused as error:
                if self._get is not None and self._get.status_code is not None:
                    value=self._read(self._active);value['requests'][-1]['http_status']=self._get.status_code
                    with self.db:self._write(value)
                self._stop('ABORTED',error.code)

    def transfer(self,payload):
        """Private native coordinator RPC only; never a public control command."""
        with _owner_scope(self.lease),self.store._live():
            _need(not self._closed,'READ_OWNER_CLOSED')
            _need(type(payload) is dict and type(payload.get('operation')) is str,'READ_TRANSFER_INVALID')
            op=payload['operation'];keys={'chunk':{'operation','packet_id','offset','sha256'},'ack':{'operation','packet_id','manifest'}}
            _need(op in keys and set(payload)==keys[op],'READ_TRANSFER_INVALID');uuid(payload['packet_id'])
            value=self._read(payload['packet_id']);e=value['evidence'];_need(e is not None,'READ_EVIDENCE_UNAVAILABLE')
            if op=='ack':
                manifest=payload['manifest']
                _need(type(manifest) is dict and manifest.get('task_id')==value['task_id'] and manifest.get('sha256')==e['sha256'] and manifest.get('size_bytes')==e['size_bytes'],'READ_PUBLICATION_UNVERIFIED')
                # Validates exact PUBLISHED ledger, path, bytes and DPAPI context.
                with open_read_evidence(self.lease,value['account_alias'],value['packet_id'],manifest):pass
                if value['state']!='PUBLISHED':
                    _need(self._cipher is not None and self._cipher.packet_id==value['packet_id'],'READ_EVIDENCE_UNAVAILABLE')
                    with self.db:value['state']='PUBLISHED';self._write(value)
                    self._cipher=None;self._transfer_offset=0;self._last_offset=None
                return self._public(value)
            _need(self._cipher is not None and self._cipher.packet_id==value['packet_id'] and payload['sha256']==e['sha256'],'READ_EVIDENCE_UNAVAILABLE')
            offset=payload['offset']
            _need(type(offset) is int and 0<=offset<e['size_bytes'] and (offset==self._transfer_offset or offset==self._last_offset),'READ_TRANSFER_ORDER')
            data=self._cipher.ciphertext[offset:offset+32768]
            if offset==self._transfer_offset:self._last_offset=offset;self._transfer_offset+=len(data)
            return dict(project_id=value['project_id'],account_alias=value['account_alias'],task_id=value['task_id'],packet_id=value['packet_id'],
                        sha256=e['sha256'],total_bytes=e['size_bytes'],offset=offset,data=base64.b64encode(data).decode())

    def require_checkpoint(self):
        if self._market is not None:self._market.require_checkpoint()
        _need(self._active is None and self._get is None and self._cipher is None,'READ_CHECKPOINT_BUSY')

    def close(self):
        with _MUTEX:
            cancel_producer(self)
            if self._closed:return
            if self._market is not None:self._market.close()
            self._closed=True;self._clear_preflight();self._read_provenance=[]
            try:self._dispose_get()
            finally:
                if self._packet is not None:self._packet.close();self._packet=None
                self._cipher=None;self._active=None
                if not self._guard.closed and self in self._guard.resources:self._guard.resources.remove(self)
