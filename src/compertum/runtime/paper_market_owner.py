"""Private cooperative market lifecycle hosted by PaperReadOwner."""
from datetime import datetime,timezone
import hashlib,re,time
from zoneinfo import ZoneInfo
from compertum.data.encoding import canonical
from compertum.domain import ContractError
from compertum.events import uuid
from compertum.paper_contracts import timestamp
from compertum.paper_market_inputs import OperationalMarketPlan,prepare_market_plan
from .errors import RuntimeRefused
from .owners import _owner_scope
from .paper_credential_slot import load_paper_slot,_coordinator_records
from .paper_credentials import open_paper_credentials
from .paper_read_secrecy import _reject_reflections
from .paper_market_grants import build_grant,initial_record
from .paper_market_records import MarketRecords
from .paper_market_collection import _MarketCollection
from .paper_market_evidence import protect_market_evidence


def _need(value,code):
 if not value:raise RuntimeRefused(code)


def _now():return datetime.fromtimestamp(time.time(),timezone.utc).isoformat()


class _MarketOwner:
 def __init__(self,parent):
  self.parent=parent;self.lease=parent.lease;self.db=parent.db
  self.records=MarketRecords(self.db,self.lease.project_id);self.records.interrupt_unfinished()
  self._active=None;self._producer=None;self._cipher=None;self._cleanup_failed=False

 def __repr__(self):return '<PrivateMarketOwner>'
 def __reduce_ex__(self,protocol):raise RuntimeRefused('PAPER_MARKET_PRIVATE_SERIALIZATION_FORBIDDEN')

 def _reservation(self,g):
  with _owner_scope(self.lease) as guard,_coordinator_records(guard) as db:
   rows=db.execute('SELECT task,category,maximum,written,status,path FROM reservations WHERE id=? LIMIT 2',(g['reservation_id'],)).fetchall()
   _need(rows==[(g['task_id'],'records',3*1024**2,0,'RESERVED',None)],'MARKET_STORAGE_UNVERIFIED')

 def _live_grant(self,v):
  g=v['grant'];_need(g['owner_instance']==self.lease.identity.process_instance_id and g['owner_generation']==self.lease.generation,'MARKET_OWNER_CHANGED')
  now=timestamp(_now());created=timestamp(g['created_at']);elapsed=time.monotonic()-g['prepared_mono']
  _need(0<=elapsed<60 and created<=now<timestamp(g['start_expires_at']) and abs((now-created).total_seconds()-elapsed)<=5,'MARKET_GRANT_EXPIRED')
  _need(now<timestamp(g['plan']['history_cutoff_at']),'MARKET_COLLECTION_CUTOFF')
  self.parent._ready();self._reservation(g)
  protected=load_paper_slot(self.lease,g['account_alias'])
  _need(hashlib.sha256(protected.ciphertext).hexdigest()==g['credential_sha256'],'MARKET_CREDENTIAL_CHANGED')
  return protected

 def _public(self,v):
  g=v['grant']
  return dict(version=1,record_type='NativePaperMarketReceipt',scope='OPERATIONAL_MARKET_READ_ONLY',
              job_id=g['job_id'],task_id=g['task_id'],account_alias=g['account_alias'],mode=g['mode'],
              symbol=g['plan']['symbol'],grant_sha256=v['grant_sha256'],plan_sha256=g['plan_sha256'],plan=g['plan'],
              state=v['state'],consumed=v['consumed'],reason=v['reason'],summary=v['summary'],evidence=v['evidence'],
              manifest=v['manifest'],financial_accepted=False,research_eligible=False)

 def _capacity(self):
  _need(self._active is None and self._producer is None and self._cipher is None and not self._cleanup_failed,'MARKET_OWNER_CAPACITY')

 def handle(self,packet):
  _need(type(packet) is dict and set(packet)=={'subject_key','command'},'CONTROL_PAYLOAD_DENIED')
  subject=packet['subject_key'];c=packet['command']
  _need(type(subject) is str and re.fullmatch('[0-9a-f]{64}',subject) is not None,'CONTROL_PAYLOAD_DENIED')
  _need(type(c) is dict and type(c.get('operation')) is str,'CONTROL_PAYLOAD_DENIED')
  op=c['operation'];keys={'prepare':{'operation','job_id','task_id','account_alias','reservation_id','mode','symbol','history'},
   'authorize':{'operation','job_id','grant_sha256'},'start':{'operation','job_id','grant_sha256'},
   'status':{'operation','job_id'},'cancel':{'operation','job_id'}}
  _need(op in keys and set(c)==keys[op],'CONTROL_PAYLOAD_DENIED');uuid(c['job_id'])
  _need(not self.db.in_transaction,'MARKET_TRANSACTION_OPEN')
  if op=='prepare':return self._prepare(subject,c)
  v=self.records.read(c['job_id']);_need(v['grant']['subject_key']==subject,'MARKET_OPERATOR_CHANGED')
  if op=='status':return self._public(v)
  if op=='cancel':
   if self._active==c['job_id']:self._stop('CANCELED','OPERATOR_CANCELED')
   elif v['state'] in {'PREPARED','GRANTED'}:
    with self.db:v.update(state='CANCELED',reason='OPERATOR_CANCELED');self.records.write(v)
   return self._public(self.records.read(c['job_id']))
  _need(c['grant_sha256']==v['grant_sha256'],'MARKET_GRANT_CHANGED')
  if v['consumed']:return self._public(v)
  _need(v['state'] in {'PREPARED','GRANTED'},'MARKET_GRANT_REQUIRED')
  protected=self._live_grant(v)
  if op=='authorize':
   with self.db:v['state']='GRANTED';self.records.write(v)
  else:
   _need(v['state']=='GRANTED','MARKET_GRANT_REQUIRED');self._capacity()
   with self.db:v.update(state='RUNNING',consumed=True);self.records.write(v)
   _need(not self.db.in_transaction and self.records.read(c['job_id'])==v,'MARKET_WRITE_UNVERIFIED')
   self._active=c['job_id'];g=v['grant']
   try:self._producer=_MarketCollection(self.lease,OperationalMarketPlan(canonical(g['plan'])),protected,collection_id=g['job_id'],mode=g['mode'])
   except RuntimeRefused as error:self._stop('ABORTED',error.code)
  return self._public(self.records.read(c['job_id']))

 def _prepare(self,subject,c):
  from .paper_market_records import PREFIX
  if self.db.execute('SELECT 1 FROM state WHERE key=?',(PREFIX+c['job_id'],)).fetchone():
   v=self.records.read(c['job_id']);g=v['grant']
   _need(g['subject_key']==subject and all(g[k]==c[k] for k in ('task_id','account_alias','reservation_id','mode','history')) and g['plan']['symbol']==c['symbol'],'MARKET_JOB_CONFLICT')
   return self._public(v)
  self._capacity();self.parent._ready()
  _need(type(c['mode']) is str and c['mode'] in {'HISTORY','CURRENT_ACTIONS'} and c['history'] is None,'MARKET_HISTORY_REQUIRED')
  uuid(c['task_id']);uuid(c['reservation_id'])
  protected=load_paper_slot(self.lease,c['account_alias']);at=_now()
  try:
   plan=prepare_market_plan(project_id=self.lease.project_id,account_alias=c['account_alias'],symbol=c['symbol'],
       session_date=timestamp(at).astimezone(ZoneInfo('America/New_York')).date().isoformat(),created_at=at)
  except ContractError:raise RuntimeRefused('MARKET_PLAN_INVALID') from None
  grant=build_grant(job_id=c['job_id'],task_id=c['task_id'],reservation_id=c['reservation_id'],project_id=self.lease.project_id,
      owner_instance=self.lease.identity.process_instance_id,owner_generation=self.lease.generation,subject_key=subject,
      credential_sha256=hashlib.sha256(protected.ciphertext).hexdigest(),mode=c['mode'],plan=plan,history=None,created_at=at,prepared_mono=time.monotonic())
  v=initial_record(grant);self._reservation(v['grant'])
  with open_paper_credentials(self.lease,protected) as opened:_reject_reflections(canonical(v),tuple(opened.headers().values()))
  with self.db:self.records.write(v,new=True)
  return self._public(v)

 def _summary(self):
  s=self._producer.status()
  return dict(state=s['state'],reason=s['reason'],attempts=s['attempts'],responses=s['pages'])

 def _dispose_producer(self):
  if self._producer is not None:
   try:
    self._producer.close()
    _need(self._producer._pending is None and self._producer._cleanup_pending is None,'HTTP_CLEANUP_UNVERIFIED')
   except BaseException:self._cleanup_failed=True;raise
   self._producer=None;self._cleanup_failed=False

 def _finish(self,v):
  if self._producer is not None:
   v['summary']=self._summary()
   if self._cipher is None:self._cipher=protect_market_evidence(self.lease,self._producer.private_snapshot(),task_id=v['grant']['task_id'])
   v['evidence']=dict(size_bytes=len(self._cipher.ciphertext),sha256=hashlib.sha256(self._cipher.ciphertext).hexdigest())
  with self.db:self.records.write(v)
  self._dispose_producer();self._active=None

 def _stop(self,state,reason):
  if self._active is None:return
  v=self.records.read(self._active);v.update(state=state,reason=reason);error=None
  if self._producer is not None and not self._cleanup_failed:
   if self._producer.status()['state'] in {'READY','PENDING','WAITING'}:
    try:self._producer.cancel()
    except RuntimeRefused as caught:error=caught;v['reason']=caught.code
  # A failed native cancellation can still leave a valid terminal snapshot.
  # Seal it before retrying disposal; retain the producer if cleanup is uncertain.
  self._finish(v)
  if error is not None:raise error

 def tick(self):
  if self._active is None or self._cleanup_failed:return
  v=self.records.read(self._active)
  try:
   self.parent._ready();state=self._producer.status()['state']
   if state in {'READY','WAITING'}:self._producer.dispatch()
   elif state=='PENDING':self._producer.poll()
   v['summary']=self._summary()
   if v['summary']['state'] in {'PAGINATION_COMPLETE','INCOMPLETE'}:
    v.update(state='EVIDENCE_READY',reason=v['summary']['reason']);self._finish(v)
   else:
    with self.db:self.records.write(v)
  except RuntimeRefused as error:
   if self._cleanup_failed:raise
   self._stop('ABORTED',error.code)

 def require_checkpoint(self):
  _need(self._active is None and self._producer is None and self._cipher is None and not self._cleanup_failed,'MARKET_CHECKPOINT_BUSY')

 def close(self):
  if self._cleanup_failed:
   self._dispose_producer();self._active=None
  elif self._active is not None:self._stop('INTERRUPTED','OWNER_CLOSED')
  self._dispose_producer();self._cipher=None
