"""Coordinator-owned opaque publication and finite historical ACK recovery."""
import base64,hashlib,re
from uuid import uuid5,NAMESPACE_URL
from compertum.data.encoding import canonical
from compertum.events import uuid
from compertum.execution_contracts import WATCHLIST
from compertum.paper_contracts import strict_json
from compertum.persistence import checked_path
from .errors import RuntimeRefused
from .owner_channel import _remote_scope
from .owner_rpc import call_owner
from .paper_market_evidence import _ProtectedMarketEvidence,_FACTORY,_manifest,_pinned,publish_market_evidence

_PREFIX='paper_market_route:';_VERSION='paper_market_publication_version';_MAX=3*1024**2
_IMMUTABLE={'version','purpose','project_id','job_id','task_id','account_alias','mode','symbol','subject_key','reservation_id','history_job_id'}


def _need(value,code='MARKET_PUBLICATION_INVALID'):
 if not value:raise RuntimeRefused(code)
def _hash(v):return type(v) is str and re.fullmatch('[0-9a-f]{64}',v) is not None


class PaperMarketPublication:
 def __init__(self,manager,remote):
  self.manager=manager;self.remote=remote;self.db=manager.store.conn;self.entries={};self._cursor=0
  with manager.store._live(),_remote_scope(remote):
   r=remote.descriptor.registration;_need(r.identity.role=='execution' and r.project_id==manager.lease.project_id)
   _need(not self.db.in_transaction,'MARKET_TRANSACTION_OPEN')
   with self.db:
    version=self.db.execute('SELECT value FROM state WHERE key=?',(_VERSION,)).fetchone()
    rows=self._keys();_need(version==('1',) or version is None and not rows)
    if version is None:
     c=self.db.execute('INSERT INTO state VALUES(?,?)',(_VERSION,'1'));_need(c.rowcount==1,'MARKET_ROUTE_WRITE_UNVERIFIED')
    self._version()
    for key in rows:
     route=self._route(key);self.entries[key]=self._entry(route,phase='RECOVER')
   from .paper_market_lineage_publication import LineagePublication
   self._lineage=LineagePublication(self)

 def _keys(self):
  rows=self.db.execute('SELECT key FROM state WHERE substr(key,1,?)=? ORDER BY key LIMIT 33',(len(_PREFIX),_PREFIX)).fetchall()
  _need(len(rows)<=32,'MARKET_HISTORY_BOUND');return [key[len(_PREFIX):] for (key,) in rows]

 def _version(self):_need(self.db.execute('SELECT value FROM state WHERE key=?',(_VERSION,)).fetchone()==('1',),'MARKET_ROUTE_CORRUPT')

 def _validate(self,v):
  _need(type(v) is dict and set(v)==_IMMUTABLE|{'grant_sha256','publication'})
  _need(type(v['version']) is int and v['version']==1 and v['purpose']=='COMPERTUM_MARKET_ROUTE_V1' and v['project_id']==self.manager.lease.project_id)
  for key in ('job_id','task_id'):uuid(v[key])
  _need(v['task_id']==str(uuid5(NAMESPACE_URL,v['project_id']+'/paper-market/'+v['job_id'])))
  _need(_hash(v['subject_key']) and (v['grant_sha256'] is None or _hash(v['grant_sha256'])))
  _need(type(v['account_alias']) is str and re.fullmatch('[A-Za-z0-9][A-Za-z0-9_-]{0,63}',v['account_alias']) is not None)
  _need(type(v['mode']) is str and v['mode'] in {'HISTORY','CURRENT_ACTIONS','FRESH'})
  if v['mode']=='FRESH':uuid(v['history_job_id']);_need(v['reservation_id'] is None and v['history_job_id']!=v['job_id'])
  else:uuid(v['reservation_id']);_need(v['history_job_id'] is None)
  _need(type(v['symbol']) is str and v['symbol'] in set(WATCHLIST)|{'SPY'})
  p=v['publication'];_need(type(p) is dict and set(p)=={'state','reason','manifest'})
  _need(type(p['state']) is str and p['state'] in {'WAITING','TRANSFERRING','PUBLISHED','FAILED','NO_EVIDENCE'})
  _need(p['reason'] is None or type(p['reason']) is str and re.fullmatch('[A-Z][A-Z0-9_]{0,79}',p['reason']) is not None)
  if p['manifest'] is not None:_manifest(p['manifest'],v['task_id'],v['job_id']);_need(v['grant_sha256'] is not None)
  if p['state']=='PUBLISHED':_need(p['manifest'] is not None)
  if v['mode']=='FRESH':_need(p==dict(state='NO_EVIDENCE',reason=None,manifest=None))
  return v

 def _route(self,job_id):
  self._version();uuid(job_id)
  row=self.db.execute('SELECT CASE WHEN length(value)<=8192 THEN value END FROM state WHERE key=?',(_PREFIX+job_id,)).fetchone()
  _need(row is not None,'MARKET_JOB_UNKNOWN')
  try:
   v=self._validate(strict_json(row[0].encode()));_need(v['job_id']==job_id);return v
  except (ValueError,TypeError,AttributeError,KeyError):raise RuntimeRefused('MARKET_ROUTE_CORRUPT') from None

 def _save(self,route,*,new=False):
  self._version();self._validate(route);raw=canonical(route).decode();_need(len(raw.encode())<=8192)
  lock=self.db.execute("UPDATE state SET value=value WHERE key=? AND value='1'",(_VERSION,));_need(lock.rowcount==1,'MARKET_ROUTE_WRITE_UNVERIFIED')
  self._version();key=_PREFIX+route['job_id']
  if new:
   _need(len(self._keys())<32,'MARKET_HISTORY_BOUND')
   _need(route['reservation_id'] is None or all(self._route(k)['reservation_id']!=route['reservation_id'] for k in self._keys()),'MARKET_STORAGE_REUSED')
   c=self.db.execute('INSERT INTO state VALUES(?,?)',(key,raw))
  else:
   before=self._route(route['job_id'])
   _need(all(before[k]==route[k] for k in _IMMUTABLE),'MARKET_ROUTE_WRITE_UNVERIFIED')
   _need(before['grant_sha256'] is None or before['grant_sha256']==route['grant_sha256'],'MARKET_ROUTE_WRITE_UNVERIFIED')
   _need(before['publication']['manifest'] is None or before['publication']['manifest']==route['publication']['manifest'],'MARKET_ROUTE_WRITE_UNVERIFIED')
   c=self.db.execute('UPDATE state SET value=? WHERE key=? AND value=?',(raw,key,canonical(before).decode()))
  _need(c.rowcount==1 and self._route(route['job_id'])==route,'MARKET_ROUTE_WRITE_UNVERIFIED')

 def _entry(self,route,phase='PREPARED',grant=None):
  return dict(route=route,phase=phase,grant=grant,buffer=bytearray(),evidence=None,protected=None,child=None)

 def _check(self,route,result):
  _need(type(result) is dict and all(result.get(k)==route[k] for k in ('job_id','task_id','account_alias','mode','symbol')))
  _need(_hash(result.get('grant_sha256')) and (route['grant_sha256'] is None or result['grant_sha256']==route['grant_sha256']))
  return result

 def _call(self,route,command):
  return self._check(route,call_owner(self.remote,'paper_market_read',dict(subject_key=route['subject_key'],command=command)))

 def _history(self,subject,command):
  h=self._route(command['history_job_id'])
  _need(h['subject_key']==subject,'MARKET_OPERATOR_CHANGED')
  _need(h['mode']=='HISTORY' and h['account_alias']==command['account_alias'] and h['symbol']==command['symbol']
        and h['publication']['state']=='PUBLISHED' and h['publication']['manifest'] is not None,'MARKET_HISTORY_REQUIRED')
  manifest=self._ledger_manifest(h)
  return dict(job_id=h['job_id'],task_id=h['task_id'],grant_sha256=h['grant_sha256'],manifest=manifest)

 def handle(self,subject,command):
  with self.manager.store._live():
   _need(_hash(subject),'CONTROL_PAYLOAD_DENIED')
   _need(type(command) is dict and type(command.get('operation')) is str,'CONTROL_PAYLOAD_DENIED')
   if command['operation'] in {'publish_lineage','lineage_status'}:return self._lineage.handle(subject,command)
   op=command['operation'];keys={'prepare':{'operation','job_id','account_alias','mode','symbol','history_job_id'},
    'authorize':{'operation','job_id','grant_sha256'},'start':{'operation','job_id','grant_sha256'},
    'status':{'operation','job_id'},'cancel':{'operation','job_id'},'compose':{'operation','job_id'}}
   _need(op in keys and set(command)==keys[op],'CONTROL_PAYLOAD_DENIED');uuid(command['job_id']);job=command['job_id']
   _need(not self.db.in_transaction,'MARKET_TRANSACTION_OPEN')
   if op=='prepare':
    _need(type(command['mode']) is str and command['mode'] in {'HISTORY','CURRENT_ACTIONS','FRESH'},'CONTROL_PAYLOAD_DENIED')
    fresh=command['mode']=='FRESH'
    if fresh:uuid(command['history_job_id']);_need(command['history_job_id']!=job,'MARKET_HISTORY_REQUIRED')
    else:_need(command['history_job_id'] is None,'CONTROL_PAYLOAD_DENIED')
    _need(type(command['symbol']) is str and command['symbol'] in set(WATCHLIST)|{'SPY'},'CONTROL_PAYLOAD_DENIED')
    alias=command['account_alias'];_need(type(alias) is str and re.fullmatch('[A-Za-z0-9][A-Za-z0-9_-]{0,63}',alias) is not None,'CONTROL_PAYLOAD_DENIED')
    route=self._route(job) if job in self._keys() else None
    if route is not None:_need(route['subject_key']==subject,'MARKET_OPERATOR_CHANGED')
    history=self._history(subject,command) if fresh else None
    if route is not None:pass
    else:
     _need(len(self._keys())<32,'MARKET_HISTORY_BOUND')
     task=str(uuid5(NAMESPACE_URL,self.manager.lease.project_id+'/paper-market/'+job))
     _need(self.db.execute('SELECT 1 FROM reservations WHERE task=?',(task,)).fetchone() is None,'MARKET_STORAGE_REUSED')
     grant=None if fresh else self.manager.reserve_bytes(task,'records',_MAX)
     route=dict(version=1,purpose='COMPERTUM_MARKET_ROUTE_V1',project_id=self.manager.lease.project_id,job_id=job,task_id=task,
      account_alias=alias,mode=command['mode'],symbol=command['symbol'],subject_key=subject,reservation_id=None if fresh else grant.grant_id,
      history_job_id=command['history_job_id'],grant_sha256=None,publication=dict(state='NO_EVIDENCE' if fresh else 'WAITING',reason=None,manifest=None))
     with self.db:self._save(route,new=True)
     self.entries[job]=self._entry(route,grant=grant)
    _need(route['subject_key']==subject and all(route[k]==command[k] for k in ('account_alias','mode','symbol','history_job_id')),'MARKET_JOB_CONFLICT')
    private={k:command[k] for k in ('operation','job_id','account_alias','mode','symbol')}
    private.update(task_id=route['task_id'],reservation_id=route['reservation_id'],history=history)
    result=self._call(route,private)
    if route['grant_sha256'] is None:
     route['grant_sha256']=result['grant_sha256']
     with self.db:self._save(route)
    self.entries[job]['route']=route
   else:
    route=self._route(job);_need(route['subject_key']==subject,'MARKET_OPERATOR_CHANGED')
    if op in {'authorize','start'}:
     _need(command['grant_sha256']==route['grant_sha256'],'MARKET_GRANT_CHANGED')
     _need(job in self.entries and self.entries[job]['phase'] not in {'RECOVER','FAILED'},'MARKET_COORDINATOR_RESTARTED')
     if op=='start' and self.entries[job]['phase']=='PREPARED':
      _need(not any(k!=job and e['phase'] not in {'PREPARED','DONE','FAILED'} for k,e in self.entries.items()),'MARKET_PUBLICATION_CAPACITY')
      self.entries[job]['phase']='DONE' if route['mode']=='FRESH' else 'WAIT'
    result=self._call(route,command)
   return dict(result,publication=self._route(job)['publication'])

 def _ledger_manifest(self,route):
  task=route['task_id'];path=f'artifacts/runs/{task}/market-collection-{route["job_id"]}.bin'
  rows=self.db.execute('SELECT task,category,maximum,written,status,path,CASE WHEN length(manifest)<=4096 THEN manifest END FROM reservations WHERE path=? LIMIT 2',(path,)).fetchall()
  _need(len(rows)==1,'MARKET_PUBLICATION_UNVERIFIED');row=rows[0]
  try:manifest=strict_json(row[6].encode());_manifest(manifest,task,route['job_id'])
  except (ValueError,TypeError,AttributeError):raise RuntimeRefused('MARKET_PUBLICATION_UNVERIFIED') from None
  _need(row==(task,'records',manifest['size_bytes'],manifest['size_bytes'],'PUBLISHED',path,canonical(manifest).decode()),'MARKET_PUBLICATION_UNVERIFIED')
  parent=self.db.execute('SELECT task,category,maximum,written,status,path,manifest FROM reservations WHERE id=?',(route['reservation_id'],)).fetchone()
  _need(parent==(task,'records',_MAX,manifest['size_bytes'],'SPLIT',None,None),'MARKET_PUBLICATION_UNVERIFIED')
  _need(route['publication']['manifest'] is None or route['publication']['manifest']==manifest,'MARKET_PUBLICATION_UNVERIFIED')
  with self.manager.store._live() as guard:
   file=checked_path(self.manager.root,self.manager.root/path)
   with _pinned(guard,file):raw=guard.api.read_regular(file,maximum=_MAX)
   _need(len(raw)==manifest['size_bytes'] and hashlib.sha256(raw).hexdigest()==manifest['sha256'],'MARKET_PUBLICATION_UNVERIFIED')
  return manifest

 def tick(self):
  with self.manager.store._live():
   self._lineage.tick()
   ready=[key for key,e in self.entries.items() if e['phase'] not in {'PREPARED','DONE','FAILED'}]
   if not ready:return
   job=ready[self._cursor%len(ready)];self._cursor+=1;e=self.entries[job];route=e['route']
   try:
    if e['phase']=='RECOVER':
     if route['mode']=='FRESH':e['phase']='FAILED';return
     manifest=self._ledger_manifest(route)
     if route['publication']['state']=='PUBLISHED':e['phase']='DONE';return
     route['publication'].update(state='TRANSFERRING',reason=None,manifest=manifest)
     with self.db:self._save(route)
     e['phase']='ACK'
    elif e['phase']=='WAIT':
     status=self._call(route,dict(operation='status',job_id=job));evidence=status.get('evidence')
     if evidence is None:
      if status.get('state') in {'ABORTED','CANCELED','INTERRUPTED'}:
       route['publication'].update(state='NO_EVIDENCE',reason=status.get('reason'))
       with self.db:self._save(route)
       e['phase']='DONE'
      return
     _need(type(evidence) is dict and set(evidence)=={'size_bytes','sha256'} and type(evidence['size_bytes']) is int and 0<evidence['size_bytes']<=_MAX and _hash(evidence['sha256']))
     e['evidence']=evidence;route['publication']['state']='TRANSFERRING'
     with self.db:self._save(route)
     e['phase']='COLLECT'
    elif e['phase']=='COLLECT':
     expected={k:route[k] for k in ('project_id','job_id','task_id','account_alias','mode','grant_sha256')}
     expected.update(sha256=e['evidence']['sha256'],total_bytes=e['evidence']['size_bytes'],offset=len(e['buffer']))
     reply=call_owner(self.remote,'paper_market_transfer',dict(operation='chunk',job_id=job,offset=expected['offset'],sha256=expected['sha256']))
     _need(type(reply) is dict and set(reply)==set(expected)|{'data'} and all(type(reply[k]) is type(v) and reply[k]==v for k,v in expected.items()))
     _need(type(reply['data']) is str and len(reply['data'])<=43692)
     try:chunk=base64.b64decode(reply['data'],validate=True)
     except ValueError:raise RuntimeRefused('MARKET_PUBLICATION_INVALID') from None
     _need(len(chunk)==min(32768,expected['total_bytes']-expected['offset']));e['buffer'].extend(chunk)
     if len(e['buffer'])==expected['total_bytes']:
      _need(hashlib.sha256(e['buffer']).hexdigest()==expected['sha256'])
      e['protected']=_ProtectedMarketEvidence(route['project_id'],route['account_alias'],route['task_id'],job,bytes(e['buffer']),_factory=_FACTORY)
      e['buffer'].clear();e['phase']='PUBLISH'
    elif e['phase']=='PUBLISH':
     if e['child'] is None:e['child']=self.manager.split_grant(e['grant'],len(e['protected'].ciphertext))
     manifest=publish_market_evidence(self.manager,e['child'],e['protected']);route['publication']['manifest']=manifest
     with self.db:self._save(route)
     e['phase']='ACK'
    elif e['phase']=='ACK':
     manifest=self._ledger_manifest(route)
     # The durable route is checked again before the sole recovery RPC.
     _need(self._route(job)['publication']['manifest']==manifest,'MARKET_ROUTE_WRITE_UNVERIFIED')
     reply=self._check(route,call_owner(self.remote,'paper_market_transfer',dict(operation='ack',job_id=job,manifest=manifest)))
     _need(reply.get('state')=='PUBLISHED' and reply.get('manifest')==manifest and reply.get('evidence')=={k:manifest[k] for k in ('size_bytes','sha256')})
     route['publication'].update(state='PUBLISHED',reason=None)
     with self.db:self._save(route)
     e.update(phase='DONE',protected=None);e['buffer'].clear()
   except (RuntimeRefused,OSError) as error:
    e.update(phase='FAILED',protected=None);e['buffer'].clear()
    route['publication'].update(state='FAILED',reason=error.code if isinstance(error,RuntimeRefused) else 'MARKET_PUBLICATION_IO_FAILED')
    with self.db:self._save(route)
