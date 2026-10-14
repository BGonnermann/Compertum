"""Private cooperative market lifecycle hosted by PaperReadOwner."""
from datetime import datetime,timezone
import base64,hashlib,re,time
from zoneinfo import ZoneInfo
from compertum.data.encoding import canonical
from compertum.domain import ContractError
from compertum.events import uuid
from compertum.paper_contracts import timestamp,strict_json
from compertum.paper_market_inputs import OperationalMarketPlan,prepare_market_plan
from .errors import RuntimeRefused
from .owners import _owner_scope
from .paper_credential_slot import load_paper_slot,_coordinator_records
from .paper_credentials import open_paper_credentials
from .paper_read_secrecy import _reject_reflections
from .paper_market_grants import build_grant,initial_record
from .paper_market_records import MarketRecords
from .paper_market_collection import _MarketCollection
from .paper_market_evidence import protect_market_evidence,open_market_evidence
from .paper_market_fresh import _MarketFresh
from .paper_market_compose import compose_market_inputs
from .paper_market_collection import _scan_generated


def _need(value,code):
 if not value:raise RuntimeRefused(code)


def _now():return datetime.fromtimestamp(time.time(),timezone.utc).isoformat()


class _MarketOwner:
 def __init__(self,parent):
  self.parent=parent;self.lease=parent.lease;self.db=parent.db
  self.records=MarketRecords(self.db,self.lease.project_id);self.records.interrupt_unfinished()
  self._active=None;self._producer=None;self._cipher=None;self._cleanup_failed=False
  self._transfer_offset=0;self._last_offset=None
  self._fresh_job=None;self._fresh_view=None;self._history_context=None;self._opened=None;self._combined=None

 def __repr__(self):return '<PrivateMarketOwner>'
 def __reduce_ex__(self,protocol):raise RuntimeRefused('PAPER_MARKET_PRIVATE_SERIALIZATION_FORBIDDEN')

 def _reservation(self,g):
  with _owner_scope(self.lease) as guard,_coordinator_records(guard) as db:
   if g['mode']=='FRESH':
    row=db.execute('SELECT CASE WHEN length(value)<=8192 THEN value END FROM state WHERE key=?',('paper_market_route:'+g['job_id'],)).fetchone()
    try:r=strict_json(row[0].encode())
    except (TypeError,AttributeError,ValueError):raise RuntimeRefused('MARKET_STORAGE_UNVERIFIED') from None
    _need(db.execute("SELECT value FROM state WHERE key='paper_market_publication_version'").fetchone()==('1',)
          and type(r) is dict and r.get('version')==1 and r.get('purpose')=='COMPERTUM_MARKET_ROUTE_V1'
          and all(r.get(k)==g[k] for k in ('project_id','job_id','task_id','account_alias','subject_key','mode','reservation_id'))
          and r.get('symbol')==g['plan']['symbol'] and r.get('history_job_id')==g['history']['job_id']
          and r.get('grant_sha256') in (None,hashlib.sha256(canonical(g)).hexdigest())
          and r.get('publication')==dict(state='NO_EVIDENCE',reason=None,manifest=None),'MARKET_STORAGE_UNVERIFIED')
    return
   rows=db.execute('SELECT task,category,maximum,written,status,path FROM reservations WHERE id=? LIMIT 2',(g['reservation_id'],)).fetchall()
   _need(rows==[(g['task_id'],'records',3*1024**2,0,'RESERVED',None)],'MARKET_STORAGE_UNVERIFIED')

 def _live_grant(self,v):
  g=v['grant'];_need(g['owner_instance']==self.lease.identity.process_instance_id and g['owner_generation']==self.lease.generation,'MARKET_OWNER_CHANGED')
  now=timestamp(_now());created=timestamp(g['created_at']);elapsed=time.monotonic()-g['prepared_mono']
  _need(0<=elapsed<60 and created<=now<timestamp(g['start_expires_at']) and abs((now-created).total_seconds()-elapsed)<=5,'MARKET_GRANT_EXPIRED')
  if g['mode']!='FRESH':_need(now<timestamp(g['plan']['history_cutoff_at']),'MARKET_COLLECTION_CUTOFF')
  else:self._history(g['subject_key'],g['account_alias'],g['plan']['symbol'],g['history'],g['credential_sha256'])
  self.parent._ready();self._reservation(g)
  protected=load_paper_slot(self.lease,g['account_alias'])
  _need(hashlib.sha256(protected.ciphertext).hexdigest()==g['credential_sha256'],'MARKET_CREDENTIAL_CHANGED')
  return protected

 def _public(self,v):
  g=v['grant']
  result=dict(version=1,record_type='NativePaperMarketReceipt',scope='OPERATIONAL_MARKET_READ_ONLY',
              job_id=g['job_id'],task_id=g['task_id'],account_alias=g['account_alias'],mode=g['mode'],
              symbol=g['plan']['symbol'],grant_sha256=v['grant_sha256'],plan_sha256=g['plan_sha256'],plan=g['plan'],
              state=v['state'],consumed=v['consumed'],reason=v['reason'],summary=v['summary'],evidence=v['evidence'],
              manifest=v['manifest'],financial_accepted=False,research_eligible=False)
  if self._fresh_job==g['job_id'] and self._fresh_view is not None:
   try:
    self._fresh_current(v)
    result['fresh']=self._diagnostic(self._fresh_view.to_payload())
    self._scan_public(result)
   except RuntimeRefused as error:self._invalidate_fresh(g['job_id'],error.code);raise
  _need(len(canonical(result))<65536,'MARKET_SUMMARY_LIMIT')
  return result

 def _fresh_current(self,v):
  self.parent._ready();g=v['grant'];protected=load_paper_slot(self.lease,g['account_alias'])
  _need(hashlib.sha256(protected.ciphertext).hexdigest()==g['credential_sha256'],'MARKET_CREDENTIAL_CHANGED')

 def _invalidate_fresh(self,job,reason):
  if self._fresh_job!=job:return
  v=self.records.read(job)
  if v['state']=='COMPLETE':
   with self.db:v.update(state='INTERRUPTED',reason=reason);self.records.write(v)
  # A refused private view may have invalid internal clock state. Its durable
  # terminal summary is already recorded; cleanup must not ask it for status.
  self._active=None;self._dispose_producer()

 def _scan_public(self,result):
  _need(len(canonical(result))<65536,'MARKET_SUMMARY_LIMIT')
  with open_paper_credentials(self.lease,self._producer._protected) as opened:_scan_generated(result,tuple(opened.headers().values()))

 def _diagnostic(self,value):
  d=value['diagnostic'];_need(type(d) is dict,'MARKET_FRESH_UNVERIFIED')
  result=dict(age_basis_at=value['age_basis_at'],observed_at=value['observed_at'],status='BLOCKED',
    asset_valid=d['asset']['valid'],quote_valid=d['quote']['valid'],observed_sessions=d['history']['observed_sessions'],
    observed_conditions_met=d['observed_conditions_met'],deficiencies=d['deficiencies'],
    financial_accepted=False,transport_authorized=False,research_eligible=False)
  _need(len(canonical(result))<8192,'MARKET_SUMMARY_LIMIT')
  with open_paper_credentials(self.lease,self._producer._protected) as opened:_scan_generated(result,tuple(opened.headers().values()))
  return result

 def _history(self,subject,alias,symbol,reference,credential):
  _need(type(reference) is dict and set(reference)=={'job_id','task_id','grant_sha256','manifest'},'MARKET_HISTORY_REQUIRED')
  h=self.records.read(reference['job_id']);g=h['grant']
  _need(g['subject_key']==subject,'MARKET_OPERATOR_CHANGED')
  _need(h['state']=='PUBLISHED' and g['mode']=='HISTORY' and g['account_alias']==alias and g['plan']['symbol']==symbol
        and g['credential_sha256']==credential and reference==dict(job_id=g['job_id'],task_id=g['task_id'],grant_sha256=h['grant_sha256'],manifest=h['manifest']),
        'MARKET_HISTORY_REQUIRED')
  return h

 def _open_history(self,g):
  h=self._history(g['subject_key'],g['account_alias'],g['plan']['symbol'],g['history'],g['credential_sha256']);old=h['grant']
  self._history_context=open_market_evidence(self.lease,g['account_alias'],old['job_id'],h['manifest'])
  self._opened=self._history_context.__enter__();snapshot=self._opened.snapshot()
  _need(snapshot['metadata']['credential_sha256']==g['credential_sha256'] and snapshot['metadata']['execution_generation']==old['owner_generation']
        and snapshot['collection']['plan']==g['plan']==old['plan'] and snapshot['collection']['mode']=='HISTORY'
        and snapshot['collection']['state']=='PAGINATION_COMPLETE' and snapshot['collection']['complete_by_cutoff'] is True
        and snapshot['collection']['aggregate'] is not None,'MARKET_HISTORY_REQUIRED')

 def _compose(self,v):
  _need(v['state']=='COMPLETE' and self._fresh_job==v['grant']['job_id'] and self._fresh_view is not None and self._opened is not None,'MARKET_FRESH_UNAVAILABLE')
  try:
   self._fresh_current(v)
   if self._combined is None:self._combined=compose_market_inputs(self.lease,self._opened,self._fresh_view)
   value=self._combined.to_payload();result=self._diagnostic(value)
   result.update(history_job_id=v['grant']['history']['job_id'],history_sha256=value['history']['snapshot_sha256'],
                 fresh_job_id=v['grant']['job_id'],fresh_sha256=value['fresh']['snapshot_sha256'],plan_sha256=v['grant']['plan_sha256'])
   result=dict(self._public(v),composition=result);self._scan_public(result);return result
  except RuntimeRefused as error:self._invalidate_fresh(v['grant']['job_id'],error.code);raise

 def _capacity(self):
  _need(self._active is None and self._producer is None and self._cipher is None and not self._cleanup_failed,'MARKET_OWNER_CAPACITY')

 def handle(self,packet):
  _need(type(packet) is dict and set(packet)=={'subject_key','command'},'CONTROL_PAYLOAD_DENIED')
  subject=packet['subject_key'];c=packet['command']
  _need(type(subject) is str and re.fullmatch('[0-9a-f]{64}',subject) is not None,'CONTROL_PAYLOAD_DENIED')
  _need(type(c) is dict and type(c.get('operation')) is str,'CONTROL_PAYLOAD_DENIED')
  op=c['operation'];keys={'prepare':{'operation','job_id','task_id','account_alias','reservation_id','mode','symbol','history'},
   'authorize':{'operation','job_id','grant_sha256'},'start':{'operation','job_id','grant_sha256'},
   'status':{'operation','job_id'},'cancel':{'operation','job_id'},'compose':{'operation','job_id'}}
  _need(op in keys and set(c)==keys[op],'CONTROL_PAYLOAD_DENIED');uuid(c['job_id'])
  _need(not self.db.in_transaction,'MARKET_TRANSACTION_OPEN')
  if op=='prepare':return self._prepare(subject,c)
  v=self.records.read(c['job_id']);_need(v['grant']['subject_key']==subject,'MARKET_OPERATOR_CHANGED')
  if op=='status':return self._public(v)
  if op=='compose':return self._compose(v)
  if op=='cancel':
   if c['job_id'] in (self._active,self._fresh_job):self._stop('CANCELED','OPERATOR_CANCELED')
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
   try:
    if g['mode']=='FRESH':
     self._open_history(g)
     self._producer=_MarketFresh(self.lease,OperationalMarketPlan(canonical(g['plan'])),protected,pair_id=g['job_id'])
    else:self._producer=_MarketCollection(self.lease,OperationalMarketPlan(canonical(g['plan'])),protected,collection_id=g['job_id'],mode=g['mode'])
   except RuntimeRefused as error:self._stop('ABORTED',error.code)
  return self._public(self.records.read(c['job_id']))

 def _prepare(self,subject,c):
  from .paper_market_records import PREFIX
  if self.db.execute('SELECT 1 FROM state WHERE key=?',(PREFIX+c['job_id'],)).fetchone():
   v=self.records.read(c['job_id']);g=v['grant']
   _need(g['subject_key']==subject and all(g[k]==c[k] for k in ('task_id','account_alias','reservation_id','mode','history')) and g['plan']['symbol']==c['symbol'],'MARKET_JOB_CONFLICT')
   return self._public(v)
  self._capacity();self.parent._ready()
  _need(type(c['mode']) is str and c['mode'] in {'HISTORY','CURRENT_ACTIONS','FRESH'},'MARKET_HISTORY_REQUIRED')
  uuid(c['task_id'])
  if c['mode']=='FRESH':_need(c['reservation_id'] is None,'MARKET_STORAGE_UNVERIFIED')
  else:uuid(c['reservation_id']);_need(c['history'] is None,'MARKET_HISTORY_REQUIRED')
  protected=load_paper_slot(self.lease,c['account_alias']);at=_now()
  try:
   if c['mode']=='FRESH':
    h=self._history(subject,c['account_alias'],c['symbol'],c['history'],hashlib.sha256(protected.ciphertext).hexdigest())
    plan=OperationalMarketPlan(canonical(h['grant']['plan']))
   else:plan=prepare_market_plan(project_id=self.lease.project_id,account_alias=c['account_alias'],symbol=c['symbol'],
       session_date=timestamp(at).astimezone(ZoneInfo('America/New_York')).date().isoformat(),created_at=at)
  except ContractError:raise RuntimeRefused('MARKET_PLAN_INVALID') from None
  grant=build_grant(job_id=c['job_id'],task_id=c['task_id'],reservation_id=c['reservation_id'],project_id=self.lease.project_id,
      owner_instance=self.lease.identity.process_instance_id,owner_generation=self.lease.generation,subject_key=subject,
      credential_sha256=hashlib.sha256(protected.ciphertext).hexdigest(),mode=c['mode'],plan=plan,history=c['history'],created_at=at,prepared_mono=time.monotonic())
  v=initial_record(grant);self._reservation(v['grant'])
  with open_paper_credentials(self.lease,protected) as opened:_reject_reflections(canonical(v),tuple(opened.headers().values()))
  with self.db:self.records.write(v,new=True)
  return self._public(v)

 def _summary(self):
  s=self._producer.status()
  return dict(state=s['state'],reason=s['reason'],attempts=s['attempts'],responses=s.get('pages',s.get('responses')))

 def _dispose_producer(self):
  if self._combined is not None:self._combined.close();self._combined=None
  self._fresh_view=None
  if self._history_context is not None:self._history_context.__exit__(None,None,None);self._history_context=None;self._opened=None
  if self._producer is not None:
   try:
    self._producer.close()
    _need(self._producer._pending is None and getattr(self._producer,'_cleanup_pending',None) is None,'HTTP_CLEANUP_UNVERIFIED')
   except BaseException:self._cleanup_failed=True;raise
   self._producer=None;self._cleanup_failed=False
  self._fresh_job=None

 def _finish(self,v):
  if v['grant']['mode']=='FRESH':
   if self._producer is not None:v['summary']=self._summary()
   with self.db:self.records.write(v)
   if v['state']=='COMPLETE':self._fresh_view=self._producer.private_snapshot();self._fresh_job=v['grant']['job_id']
   else:self._dispose_producer()
   self._active=None;return
  if self._producer is not None:
   v['summary']=self._summary()
   if self._cipher is None:self._cipher=protect_market_evidence(self.lease,self._producer.private_snapshot(),task_id=v['grant']['task_id'])
   v['evidence']=dict(size_bytes=len(self._cipher.ciphertext),sha256=hashlib.sha256(self._cipher.ciphertext).hexdigest())
  with self.db:self.records.write(v)
  self._dispose_producer();self._active=None

 def _stop(self,state,reason):
  job=self._active or self._fresh_job
  if job is None:return
  v=self.records.read(job)
  if job==self._fresh_job:
   if v['state']=='COMPLETE':
    with self.db:v.update(state=state,reason=reason);self.records.write(v)
   self._dispose_producer();return
  v.update(state=state,reason=reason);error=None
  if self._producer is not None and not self._cleanup_failed:
   if self._producer.status()['state'] in {'READY','PENDING','WAITING'}:
    try:self._producer.cancel()
    except RuntimeRefused as caught:error=caught;v['reason']=caught.code
  # A failed native cancellation can still leave a valid terminal snapshot.
  # Seal it before retrying disposal; retain the producer if cleanup is uncertain.
  self._finish(v)
  if error is not None:raise error

 def tick(self):
  if self._fresh_job is not None:
   try:self.parent._ready()
   except RuntimeRefused as error:self._stop('INTERRUPTED',error.code)
   return
  if self._active is None or self._cleanup_failed:return
  v=self.records.read(self._active)
  try:
   self.parent._ready();state=self._producer.status()['state']
   if state in {'READY','WAITING'}:self._producer.dispatch()
   elif state=='PENDING':self._producer.poll()
   v['summary']=self._summary()
   if v['summary']['state'] in {'PAGINATION_COMPLETE','INCOMPLETE','PAIR_COMPLETE'}:
    terminal=('COMPLETE' if v['summary']['state']=='PAIR_COMPLETE' else 'ABORTED') if v['grant']['mode']=='FRESH' else 'EVIDENCE_READY'
    v.update(state=terminal,reason=v['summary']['reason']);self._finish(v)
   else:
    with self.db:self.records.write(v)
  except RuntimeRefused as error:
   if self._cleanup_failed:raise
   self._stop('ABORTED',error.code)

 def require_checkpoint(self):
  _need(self._active is None and self._producer is None and self._cipher is None and not self._cleanup_failed,'MARKET_CHECKPOINT_BUSY')

 def transfer(self,payload):
  _need(type(payload) is dict and type(payload.get('operation')) is str,'MARKET_TRANSFER_INVALID')
  op=payload['operation'];keys={'chunk':{'operation','job_id','offset','sha256'},'ack':{'operation','job_id','manifest'}}
  _need(op in keys and set(payload)==keys[op],'MARKET_TRANSFER_INVALID');uuid(payload['job_id'])
  _need(not self.db.in_transaction,'MARKET_TRANSACTION_OPEN')
  v=self.records.read(payload['job_id']);g=v['grant'];e=v['evidence']
  _need(e is not None and g['mode'] in {'HISTORY','CURRENT_ACTIONS'},'MARKET_EVIDENCE_UNAVAILABLE')
  if op=='ack':
   manifest=payload['manifest']
   _need(type(manifest) is dict and manifest.get('task_id')==g['task_id'] and all(manifest.get(k)==e[k] for k in ('sha256','size_bytes')),'MARKET_PUBLICATION_UNVERIFIED')
   # Historical publication is recoverable after restart; it renews no grant.
   with open_market_evidence(self.lease,g['account_alias'],g['job_id'],manifest) as opened:
    snapshot=opened.snapshot();meta=snapshot['metadata'];collection=snapshot['collection']
    _need(meta['credential_sha256']==g['credential_sha256'] and meta['execution_generation']==g['owner_generation']
          and collection['plan']==g['plan'] and collection['mode']==g['mode'],'MARKET_PUBLICATION_UNVERIFIED')
   if v['state']!='PUBLISHED':
    v.update(state='PUBLISHED',manifest=manifest)
    with self.db:self.records.write(v)
    _need(not self.db.in_transaction and self.records.read(g['job_id'])==v,'MARKET_WRITE_UNVERIFIED')
   else:_need(v['manifest']==manifest,'MARKET_PUBLICATION_UNVERIFIED')
   if self._cipher is not None and self._cipher.collection_id==g['job_id']:
    self._cipher=None;self._transfer_offset=0;self._last_offset=None
   return self._public(v)
  _need(self._cipher is not None and self._cipher.collection_id==g['job_id'] and payload['sha256']==e['sha256'],'MARKET_EVIDENCE_UNAVAILABLE')
  self._cipher._verify()
  _need((self._cipher.project_id,self._cipher.account_alias,self._cipher.task_id)==(g['project_id'],g['account_alias'],g['task_id'])
        and len(self._cipher.ciphertext)==e['size_bytes'] and hashlib.sha256(self._cipher.ciphertext).hexdigest()==e['sha256'],'MARKET_EVIDENCE_UNAVAILABLE')
  offset=payload['offset']
  _need(type(offset) is int and 0<=offset<e['size_bytes'] and offset in (self._transfer_offset,self._last_offset),'MARKET_TRANSFER_ORDER')
  data=self._cipher.ciphertext[offset:offset+32768]
  if offset==self._transfer_offset:self._last_offset=offset;self._transfer_offset+=len(data)
  return dict(project_id=g['project_id'],job_id=g['job_id'],task_id=g['task_id'],account_alias=g['account_alias'],mode=g['mode'],
              grant_sha256=v['grant_sha256'],sha256=e['sha256'],total_bytes=e['size_bytes'],offset=offset,data=base64.b64encode(data).decode())

 def close(self):
  if self._cleanup_failed:
   self._dispose_producer();self._active=None
  elif self._active is not None or self._fresh_job is not None:self._stop('INTERRUPTED','OWNER_CLOSED')
  self._dispose_producer();self._cipher=None
