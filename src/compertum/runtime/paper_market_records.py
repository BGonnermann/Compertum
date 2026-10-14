"""Bounded market job records in the existing execution state table."""
from compertum.data.encoding import canonical
from compertum.events import uuid
from compertum.paper_contracts import strict_json
from .errors import RuntimeRefused
from .paper_market_grants import validate_record

PREFIX='paper_market_job:'
VERSION='paper_market_owner_version'
_NEXT={'PREPARED':{'GRANTED','CANCELED','INTERRUPTED'},'GRANTED':{'RUNNING','CANCELED','INTERRUPTED'},
       'RUNNING':{'EVIDENCE_READY','COMPLETE','ABORTED','CANCELED','INTERRUPTED'},
       'EVIDENCE_READY':{'PUBLISHED','ABORTED','CANCELED','INTERRUPTED'},'COMPLETE':{'CANCELED','INTERRUPTED'},
       'ABORTED':{'PUBLISHED'},'CANCELED':{'PUBLISHED'},'INTERRUPTED':{'PUBLISHED'},'PUBLISHED':set()}


def _need(value,code='MARKET_STATE_CORRUPT'):
 if not value:raise RuntimeRefused(code)


class MarketRecords:
 def __init__(self,db,project_id):
  self.db=db;self.project_id=project_id
  _need(not db.in_transaction,'MARKET_TRANSACTION_OPEN')
  with db:
   row=db.execute('SELECT value FROM state WHERE key=?',(VERSION,)).fetchone()
   present=db.execute('SELECT 1 FROM state WHERE substr(key,1,?)=? LIMIT 1',(len(PREFIX),PREFIX)).fetchone()
   _need(row==('1',) or row is None and present is None)
   if row is None:
    c=db.execute('INSERT INTO state VALUES(?,?)',(VERSION,'1'))
    _need(c.rowcount==1 and db.execute('SELECT value FROM state WHERE key=?',(VERSION,)).fetchone()==('1',),'MARKET_WRITE_UNVERIFIED')
   self.all()

 def read(self,job_id):
  self._version()
  uuid(job_id)
  row=self.db.execute('SELECT CASE WHEN length(value)<=32768 THEN value END FROM state WHERE key=?',(PREFIX+job_id,)).fetchone()
  if row is None:raise RuntimeRefused('MARKET_JOB_UNKNOWN')
  try:
   v=validate_record(strict_json(row[0].encode()))
   _need(v['grant']['job_id']==job_id and v['grant']['project_id']==self.project_id)
   return v
  except (ValueError,TypeError,AttributeError):raise RuntimeRefused('MARKET_STATE_CORRUPT') from None

 def all(self):
  self._version()
  rows=self.db.execute('SELECT key FROM state WHERE substr(key,1,?)=? ORDER BY key LIMIT 33',(len(PREFIX),PREFIX)).fetchall()
  _need(len(rows)<=32,'MARKET_HISTORY_BOUND')
  values=[self.read(key[len(PREFIX):]) for (key,) in rows]
  tasks=[v['grant']['task_id'] for v in values];reservations=[v['grant']['reservation_id'] for v in values if v['grant']['reservation_id'] is not None]
  _need(len(tasks)==len(set(tasks)) and len(reservations)==len(set(reservations)),'MARKET_STORAGE_REUSED')
  return values

 def write(self,value,*,new=False):
  self._version()
  validate_record(value);g=value['grant'];_need(g['project_id']==self.project_id)
  raw=canonical(value).decode();key=PREFIX+g['job_id']
  # Callers own the transaction; force acquisition before inspecting capacity.
  lock=self.db.execute("UPDATE state SET value=value WHERE key=? AND value='1'",(VERSION,))
  _need(lock.rowcount==1,'MARKET_WRITE_UNVERIFIED');self._version()
  if new:
   previous=self.all();_need(len(previous)<32,'MARKET_HISTORY_BOUND')
   _need(all(v['grant']['task_id']!=g['task_id'] and (g['reservation_id'] is None or v['grant']['reservation_id']!=g['reservation_id']) for v in previous),'MARKET_STORAGE_REUSED')
   _need(self.db.execute('SELECT 1 FROM state WHERE key=?',(key,)).fetchone() is None,'MARKET_JOB_CONFLICT')
   c=self.db.execute('INSERT INTO state VALUES(?,?)',(key,raw))
  else:
   before=self.read(g['job_id']);_need(before['grant']==g and before['grant_sha256']==value['grant_sha256'],'MARKET_WRITE_UNVERIFIED')
   _need(not before['consumed'] or value['consumed'],'MARKET_WRITE_UNVERIFIED')
   _need(value['state']==before['state'] or value['state'] in _NEXT[before['state']],'MARKET_WRITE_UNVERIFIED')
   for field in ('evidence','manifest'):
    _need(before[field] is None or value[field]==before[field],'MARKET_WRITE_UNVERIFIED')
   if before['summary'] is not None:
    summary=value['summary'];old=before['summary']
    _need(summary is not None and summary['attempts']>=old['attempts'] and summary['responses']>=old['responses'],'MARKET_WRITE_UNVERIFIED')
    if old['state'] in {'PAGINATION_COMPLETE','PAIR_COMPLETE','INCOMPLETE'}:_need(summary==old,'MARKET_WRITE_UNVERIFIED')
   c=self.db.execute('UPDATE state SET value=? WHERE key=? AND value=?',(raw,key,canonical(before).decode()))
  _need(c.rowcount==1 and self.read(g['job_id'])==value,'MARKET_WRITE_UNVERIFIED')

 def _version(self):
  _need(self.db.execute('SELECT value FROM state WHERE key=?',(VERSION,)).fetchone()==('1',),'MARKET_STATE_CORRUPT')

 def interrupt_unfinished(self):
  _need(not self.db.in_transaction,'MARKET_TRANSACTION_OPEN')
  with self.db:
   for v in self.all():
    if v['state'] in {'PREPARED','GRANTED','RUNNING','EVIDENCE_READY','COMPLETE'}:
     v.update(state='INTERRUPTED',reason='OWNER_RESTARTED');self.write(v)
