"""Retained native consumption. Stored records never grant another send."""
from copy import deepcopy
from contextlib import contextmanager
import json,sqlite3
from decimal import Context,Decimal,Inexact,InvalidOperation,Overflow,Rounded,localcontext
from .data.encoding import canonical
from .domain import ContractError
from .events import uuid
from .paper_contracts import number
from .persistence import StateStore
from .storage import JournalReserve
from .fake_execution_journal import FakeIntentJournal,MAX_INTENTS
from .fake_attempt_guard import provision_attempt_guard,require_attempt_guard,append_record
from .attempt_records import is_native
from .native_attempt_records import validate_pair,STATES
from .runtime.execution_health import execution_durable
from .runtime.owners import require_live_owner
from .runtime.errors import RuntimeRefused
from .paper_contracts import utc
from .runtime.paper_read_packet import _nanoseconds

def _need(value,code='NATIVE_WRITE_RECORD_UNVERIFIED'):
 if not value:raise RuntimeRefused(code)

def _cell(value):
 if type(value) is bytes:return dict(sqlite_blob=value.hex())
 _need(value is None or type(value) in (str,int,float));return value

def _logical_snapshot(db):
 """Keep all surrounding execution rows private and bounded."""
 try:return _bounded_snapshot(db)
 except sqlite3.Error:raise RuntimeRefused('NATIVE_WRITE_HISTORY_BOUND') from None

def _bounded_snapshot(db):
 # Read lengths first. No unrestricted schema text or cell reaches Python
 # until its worst-case JSON size fits the remaining eight MiB allowance.
 limit=8*1024**2;used=0
 sizes=db.execute('SELECT length(type),length(name),length(tbl_name),length(sql) FROM sqlite_master ORDER BY type,name LIMIT 129').fetchall()
 _need(len(sizes)<=128,'NATIVE_WRITE_HISTORY_BOUND')
 for row in sizes:
  _need(all(value is None or type(value) is int and 0<=value<=bound for value,bound in zip(row,(32,256,256,65536))),'NATIVE_WRITE_HISTORY_BOUND')
  used+=sum(64+6*(value or 0) for value in row);_need(used<=limit,'NATIVE_WRITE_HISTORY_BOUND')
 schema=db.execute('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name LIMIT 129').fetchall()
 _need(len(schema)==len(sizes),'NATIVE_WRITE_HISTORY_BOUND')
 _need(len(schema)<=128,'NATIVE_WRITE_HISTORY_BOUND');tables=[row[1] for row in schema if row[0]=='table']
 _need(len(tables)<=64,'NATIVE_WRITE_HISTORY_BOUND');rows={};count=0
 for table in tables:
  quote=lambda name:'"'+name.replace('"','""')+'"'
  lengths=db.execute('SELECT length(CAST(name AS BLOB)),hidden FROM pragma_table_xinfo(?) LIMIT 257',(table,)).fetchall()
  # Execution records use ordinary stored columns. Refuse generated or hidden
  # columns before evaluating their expressions or selecting their contents.
  _need(0<len(lengths)<=256 and all(type(row[0]) is int and 0<row[0]<=256 and row[1]==0 for row in lengths),'NATIVE_WRITE_HISTORY_BOUND')
  names=[row[0] for row in db.execute('SELECT name FROM pragma_table_xinfo(?) LIMIT 257',(table,))]
  _need(len(names)==len(lengths),'NATIVE_WRITE_HISTORY_BOUND')
  quoted=quote(table);values=[];metadata=[];table_count=0
  for name in names:metadata.extend(('typeof('+quote(name)+')','length(CAST('+quote(name)+' AS BLOB))'))
  for dimensions in db.execute('SELECT '+','.join(metadata)+' FROM '+quoted+' LIMIT 4097'):
   count+=1;table_count+=1;_need(count<=4096,'NATIVE_WRITE_HISTORY_BOUND')
   for kind,length in zip(dimensions[::2],dimensions[1::2]):
    _need(kind in {'null','integer','real','text','blob'},'NATIVE_WRITE_HISTORY_BOUND')
    if kind in {'text','blob'}:
     _need(type(length) is int and length>=0,'NATIVE_WRITE_HISTORY_BOUND')
     used+=64+length*(6 if kind=='text' else 2)
    else:used+=64
    _need(used<=limit,'NATIVE_WRITE_HISTORY_BOUND')
  for row in db.execute('SELECT * FROM '+quoted+' LIMIT 4097'):
   _need(len(values)<table_count,'NATIVE_WRITE_HISTORY_BOUND');values.append([_cell(item) for item in row])
  _need(len(values)==table_count,'NATIVE_WRITE_HISTORY_BOUND')
  rows[table]=sorted(values,key=canonical)
 return dict(schema=schema,rows=rows)

def _replace(rows,key,value):
 found=[row for row in rows if row[0]==key];_need(len(found)<=1)
 if found:rows.remove(found[0])
 rows.append(value);rows.sort(key=canonical)

def _expected_event(snapshot,key,kind,event):
 rows=snapshot['rows'];prior=[row[1] for row in rows['sqlite_sequence'] if row[0]=='fake_intent_events']
 _need(len(prior)<=1);sequence=(prior[0] if prior else 0)+1
 rows['fake_intent_events'].append([sequence,*key,kind,canonical(event).decode()]);rows['fake_intent_events'].sort(key=canonical)
 _replace(rows['sqlite_sequence'],'fake_intent_events',['fake_intent_events',sequence])

class _NativeWriteJournal:
 def __init__(self,store,reserve):
  _need(type(store) is StateStore and type(reserve) is JournalReserve and reserve.lease is store.lease,'JOURNAL_UNRESERVED')
  require_live_owner(store.lease,'execution');_need(not store.conn.in_transaction,'NATIVE_WRITE_TRANSACTION_OPEN')
  self.store=store;self.db=store.conn;self.reserve=reserve
  with self._transaction():
   expected=deepcopy(_logical_snapshot(self.db));self._schema(expected)
   evidence=provision_attempt_guard(store);_need(evidence['status']=='VERIFIED','EXECUTION_COMPROMISED')
   if not any(row[0]=='fake_attempt_guard_head' for row in expected['rows']['state']):
    _replace(expected['rows']['state'],'fake_attempt_guard_head',['fake_attempt_guard_head',canonical(dict(sequence=0,sha256='0'*64)).decode()])
   _need(canonical(_logical_snapshot(self.db))==canonical(expected),'NATIVE_WRITE_UNEXPECTED_MUTATION')
   for record in evidence['records']:
    if not is_native(record['intent']):continue
    p=record['intent'];d=record['decision'];key=(p['account_alias'],p['intent_id'])
    old=self.db.execute('SELECT body,decision,state FROM fake_intents WHERE account=? AND intent_id=?',key).fetchone()
    if old is None:
     self._insert(p,d,'NATIVE_UNKNOWN');changed=True
     expected['rows']['fake_intents'].append([*key,p['client_order_id'],canonical(p).decode(),canonical(d).decode(),'NATIVE_UNKNOWN',None,0,'0',0])
    else:
     _need(old[:2]==(canonical(p).decode(),canonical(d).decode()) and old[2] in STATES)
     changed=old[2]=='NATIVE_CONSUMED'
     if changed:
      row=self.db.execute("UPDATE fake_intents SET state='NATIVE_UNKNOWN' WHERE account=? AND intent_id=?",key);_need(row.rowcount==1)
      matches=[row for row in expected['rows']['fake_intents'] if tuple(row[:2])==key];_need(len(matches)==1);matches[0][5]='NATIVE_UNKNOWN'
    if old is None or changed:
     event=dict(at=record['attempted_at'],automatic_send=False)
     FakeIntentJournal._event(self,*key,'NATIVE_RESTORED_UNKNOWN',event);_expected_event(expected,key,'NATIVE_RESTORED_UNKNOWN',event)
    expected['rows']['fake_intents'].sort(key=canonical)
    _need(canonical(_logical_snapshot(self.db))==canonical(expected),'NATIVE_WRITE_UNEXPECTED_MUTATION')
    self._row(*key)
 @contextmanager
 def _transaction(self):
  with self.store._live():
   require_live_owner(self.store.lease,'execution');_need(not self.db.in_transaction,'NATIVE_WRITE_TRANSACTION_OPEN')
   try:
    with self.db:
     self.db.execute('BEGIN IMMEDIATE');yield
   except sqlite3.Error:raise RuntimeRefused('NATIVE_WRITE_RECORD_UNVERIFIED') from None
 def _schema(self,expected):
  # Keep the complete shared schema required by account-history verification.
  # Creating missing empty tables must never run fake-session recovery.
  definitions={
   'fake_intents':'CREATE TABLE fake_intents(account TEXT NOT NULL,intent_id TEXT NOT NULL,client_id TEXT NOT NULL,body TEXT NOT NULL,decision TEXT NOT NULL,state TEXT NOT NULL,order_id TEXT,filled INTEGER NOT NULL,notional TEXT NOT NULL,conflict INTEGER NOT NULL,PRIMARY KEY(account,intent_id),UNIQUE(account,client_id))',
   'fake_intent_events':'CREATE TABLE fake_intent_events(seq INTEGER PRIMARY KEY AUTOINCREMENT,account TEXT NOT NULL,intent_id TEXT NOT NULL,kind TEXT NOT NULL,body TEXT NOT NULL)',
   'fake_broker_events':'CREATE TABLE fake_broker_events(account TEXT NOT NULL,event_id TEXT NOT NULL,sha256 TEXT NOT NULL,PRIMARY KEY(account,event_id))',
   'fake_event_applications':'CREATE TABLE fake_event_applications(account TEXT NOT NULL,event_id TEXT NOT NULL,intent_id TEXT NOT NULL,PRIMARY KEY(account,event_id,intent_id))',
   'fake_incidents':'CREATE TABLE fake_incidents(account TEXT NOT NULL,intent_id TEXT NOT NULL,next_index INTEGER NOT NULL,last_elapsed REAL NOT NULL,started_at TEXT,active INTEGER NOT NULL DEFAULT 1,PRIMARY KEY(account,intent_id))',
   'fake_execution_session':'CREATE TABLE fake_execution_session(singleton INTEGER PRIMARY KEY CHECK(singleton=1),owner_instance TEXT NOT NULL,state TEXT NOT NULL)'}
  for name,sql in definitions.items():
   found=[row for row in expected['schema'] if row[1]==name]
   if found:
    _need(len(found)==1 and found[0][:3]==('table',name,name),'NATIVE_WRITE_SCHEMA_UNVERIFIED')
    if name in {'fake_intents','fake_intent_events'}:_need(found[0][3]==sql,'NATIVE_WRITE_SCHEMA_UNVERIFIED')
    continue
   self.db.execute(sql);expected['schema'].append(('table',name,name,sql));expected['rows'][name]=[]
   indexes=(1,2) if name=='fake_intents' else (1,) if name in {'fake_broker_events','fake_event_applications','fake_incidents'} else ()
   for index in indexes:expected['schema'].append(('index','sqlite_autoindex_'+name+'_'+str(index),name,None))
   if name=='fake_intent_events' and 'sqlite_sequence' not in expected['rows']:
    expected['schema'].append(('table','sqlite_sequence','sqlite_sequence','CREATE TABLE sqlite_sequence(name,seq)'))
    expected['rows']['sqlite_sequence']=[]
  expected['schema'].sort(key=lambda row:row[:2])
 def __repr__(self):return '<NativeWriteJournal retained evidence redacted>'
 def __reduce_ex__(self,protocol):raise RuntimeRefused('NATIVE_WRITE_SERIALIZATION_FORBIDDEN')
 def _insert(self,p,d,state):
  _need(self.db.execute('SELECT count(*) FROM fake_intents').fetchone()[0]<MAX_INTENTS,'FAKE_JOURNAL_BOUND')
  result=self.db.execute("INSERT INTO fake_intents VALUES(?,?,?,?,?,?,NULL,0,'0',0)",
   (p['account_alias'],p['intent_id'],p['client_order_id'],canonical(p).decode(),canonical(d).decode(),state))
  _need(result.rowcount==1,'NATIVE_WRITE_IGNORED')
 def _row(self,account,intent_id):
  row=self.db.execute('SELECT CASE WHEN length(body)<=65536 THEN body END,CASE WHEN length(decision)<=65536 THEN decision END,state,client_id,order_id,filled,notional,conflict FROM fake_intents WHERE account=? AND intent_id=?',(account,intent_id)).fetchone()
  _need(row is not None,'INTENT_NOT_FOUND')
  try:
   _need(type(row[0]) is str and type(row[1]) is str and len(row[0].encode())+len(row[1].encode())<=65536)
   p,d,client=validate_pair(json.loads(row[0]),json.loads(row[1]))
   _need(canonical(p).decode()==row[0] and canonical(d).decode()==row[1])
   _need(p['project_id']==self.store.lease.project_id and p['account_alias']==account and p['intent_id']==intent_id)
   _need(row[2] in STATES and row[3]==client and type(row[5]) is int and row[5]>=0 and number(row[6])>=0 and row[7] in (0,1))
   maximum=int(p['request']['body']['qty']) if p['request']['operation']=='SUBMIT_ORDER' else 0
   _need(row[5]<=maximum)
   if row[4] is not None:uuid(row[4])
   return dict(intent=p,binding=d,status=row[2],client_order_id=client,order_id=row[4],filled_quantity=row[5],filled_notional=row[6],
    conflicting_observation=bool(row[7]),scope='RETAINED_NATIVE_EVIDENCE_ONLY',transport_authorized=False,financial_accepted=False)
  except (ValueError,TypeError,KeyError,ContractError):raise RuntimeRefused('NATIVE_WRITE_RECORD_UNVERIFIED') from None
 def read(self,account,intent_id):
  _need(not self.db.in_transaction,'NATIVE_WRITE_TRANSACTION_OPEN')
  with self._transaction():
   _logical_snapshot(self.db);require_attempt_guard(self.store);return self._row(account,intent_id)
 def consume(self,p,d,*,now):
  """Caller owns commit and the final authority checks at the send boundary."""
  _need(self.db is self.store.conn and self.db.in_transaction,'NATIVE_WRITE_TRANSACTION_REQUIRED')
  try:p,d,client=validate_pair(json.loads(canonical(p)),json.loads(canonical(d)))
  except (ValueError,ContractError):raise RuntimeRefused('NATIVE_WRITE_RECORD_UNVERIFIED') from None
  with self.store._live():
   require_live_owner(self.store.lease,'execution');before=_logical_snapshot(self.db)
   evidence=require_attempt_guard(self.store);key=(p['account_alias'],p['intent_id'])
   previous=next((item for item in evidence['records'] if (item['intent']['account_alias'],item['intent']['intent_id'])==key),None)
   if previous is not None:
    _need(previous['intent']==p and previous['decision']==d)
    return dict(first_consumption=False,record=self._row(*key),transport_authorized=False,financial_accepted=False)
   _need(not self.db.execute("SELECT 1 FROM fake_intents WHERE state IN ('NATIVE_CONSUMED','NATIVE_UNKNOWN') OR conflict<>0 LIMIT 1").fetchone(),'NATIVE_EFFECT_UNCERTAIN')
   _need(p['project_id']==self.store.lease.project_id and p['generation']==self.store.lease.generation
    and p['owner_instance']==self.store.lease.identity.process_instance_id,'NATIVE_WRITE_OWNER_CHANGED')
   execution_durable(self.store,self.reserve)
   _need(canonical(_logical_snapshot(self.db))==canonical(before),'NATIVE_WRITE_UNEXPECTED_MUTATION')
   record=dict(intent=p,decision=d,attempted_at=now,client_order_id=client)
   saved=append_record(self.store,record);_need(saved['first'],'NATIVE_WRITE_ALREADY_CONSUMED')
   self._insert(p,d,'NATIVE_CONSUMED');event=dict(at=now,request_sha256=p['request_sha256'])
   FakeIntentJournal._event(self,*key,'NATIVE_CONSUMED',event)
   after_guard=require_attempt_guard(self.store)
   _need(after_guard['sequence']==evidence['sequence']+1 and after_guard['records']==evidence['records']+[record]
    and after_guard['hashes'][:-1]==evidence['hashes'],'EXECUTION_COMPROMISED')
   expected=deepcopy(before);rows=expected['rows']
   rows['fake_intents'].append([*key,client,canonical(p).decode(),canonical(d).decode(),'NATIVE_CONSUMED',None,0,'0',0]);rows['fake_intents'].sort(key=canonical)
   sequence=self.db.execute("SELECT seq FROM sqlite_sequence WHERE name='fake_intent_events'").fetchone()[0]
   prior=[row[1] for row in rows['sqlite_sequence'] if row[0]=='fake_intent_events'];_need(sequence==(prior[0] if prior else 0)+1)
   rows['fake_intent_events'].append([sequence,*key,'NATIVE_CONSUMED',canonical(event).decode()]);rows['fake_intent_events'].sort(key=canonical)
   _replace(rows['sqlite_sequence'],'fake_intent_events',['fake_intent_events',sequence])
   _replace(rows['state'],'fake_attempt_guard_head',['fake_attempt_guard_head',canonical(dict(sequence=after_guard['sequence'],sha256=after_guard['sha256'])).decode()])
   _need(canonical(_logical_snapshot(self.db))==canonical(expected),'NATIVE_WRITE_UNEXPECTED_MUTATION')
   return dict(first_consumption=True,record=self._row(*key),transport_authorized=False,financial_accepted=False)
 def _observe_source(self,raw,*,economic_heads,now):
  """Backend accounting only. The runtime must first qualify both original sources."""
  from .fixture_order_journal import decode_order_journal
  _need(self.db is self.store.conn and self.db.in_transaction,'NATIVE_WRITE_TRANSACTION_REQUIRED')
  _need(type(now) is str and utc(now)==now)
  source=decode_order_journal(raw,economic_heads=economic_heads);begin=source['origin']
  _need(begin['project_id']==self.store.lease.project_id)
  _need(all(_nanoseconds(tx['at'])<=_nanoseconds(now) for tx in source['transactions']))
  with self.store._live(),localcontext(Context(prec=160,traps=[InvalidOperation,Overflow,Inexact,Rounded])):
   require_live_owner(self.store.lease,'execution');before=_logical_snapshot(self.db)
   execution_durable(self.store,self.reserve);guard=require_attempt_guard(self.store)
   _need(canonical(_logical_snapshot(self.db))==canonical(before),'NATIVE_WRITE_UNEXPECTED_MUTATION')
   native=[record for record in guard['records'] if is_native(record['intent']) and record['intent']['account_alias']==begin['account_alias']]
   _need(all(record in native for record in source['attempts']))
   orders=source['inventory']['orders'];fills=source['inventory']['fills'];expected=deepcopy(before);unresolved=0
   source_key='native_fixture_source:'+begin['account_alias']
   prior=self.store.get_state(source_key)
   descriptor=dict(version=1,producer_id=begin['producer_id'],genesis_sha256=source['genesis_sha256'],journal_sha256=source['journal_sha256'])
   if prior is not None:
    _need(type(prior) is dict and set(prior)==set(descriptor) and prior['version']==1
     and prior['producer_id']==descriptor['producer_id'] and prior['genesis_sha256']==descriptor['genesis_sha256']
     and prior['journal_sha256'] in source['prefix_sha256'],'NATIVE_SOURCE_HISTORY_REGRESSED')
   if prior!=descriptor:
    raw_descriptor=canonical(descriptor).decode()
    changed=self.db.execute('INSERT INTO state VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(source_key,raw_descriptor))
    _need(changed.rowcount==1,'NATIVE_WRITE_IGNORED')
    _replace(expected['rows']['state'],source_key,[source_key,raw_descriptor])
   _need(canonical(_logical_snapshot(self.db))==canonical(expected),'NATIVE_WRITE_UNEXPECTED_MUTATION')
   states={'new':'NATIVE_ACKNOWLEDGED','partially_filled':'NATIVE_PARTIALLY_FILLED','filled':'NATIVE_FILLED','canceled':'NATIVE_CANCELED','rejected':'NATIVE_REJECTED'}
   terminal={'NATIVE_FILLED','NATIVE_CANCELED','NATIVE_EXPIRED','NATIVE_REJECTED'}
   for record in native:
    p=record['intent'];key=(p['account_alias'],p['intent_id']);old=self._row(*key)
    _need(old['intent']==p and old['binding']==record['decision'] and not old['conflicting_observation'])
    outcome=source['request_outcomes'].get(p['intent_id'])
    if outcome is None:
     _need(old['status'] in {'NATIVE_CONSUMED','NATIVE_UNKNOWN'},'NATIVE_SOURCE_HISTORY_REGRESSED')
     state='NATIVE_UNKNOWN';order_id=old['order_id'];quantity=old['filled_quantity'];notional=old['filled_notional'];unresolved+=1
    elif p['request']['operation']=='CANCEL_ORDER':
     _need(outcome in {'CANCELED','REJECTED'} and record in source['attempts'])
     order_id=p['request']['parameters']['order_id'];_need(len([row for row in orders if row['id']==order_id])==1)
     state='NATIVE_'+outcome;quantity=0;notional='0'
    else:
     _need(record in source['attempts']);matches=[row for row in orders if row['client_order_id']==p['client_order_id']]
     _need(len(matches)==1);row=matches[0];_need(row['status'] in states)
     state=states[row['status']];order_id=row['id'];filled=number(row['filled_qty'])
     _need(filled==filled.to_integral_value());quantity=int(filled)
     amount=sum((number(fill['qty'],positive=True)*number(fill['price'],positive=True) for fill in fills if fill['order_id']==order_id),Decimal(0))
     notional=format(amount,'f');notional=notional.rstrip('0').rstrip('.') if '.' in notional else notional
    current=(state,order_id,quantity,notional);previous=(old['status'],old['order_id'],old['filled_quantity'],old['filled_notional'])
    _need(quantity>=old['filled_quantity'] and number(notional)>=number(old['filled_notional']),'NATIVE_SOURCE_HISTORY_REGRESSED')
    if old['status'] in terminal:_need(current==previous,'NATIVE_SOURCE_HISTORY_REGRESSED')
    if current!=previous:
     changed=self.db.execute('UPDATE fake_intents SET state=?,order_id=?,filled=?,notional=? WHERE account=? AND intent_id=?',(*current,*key))
     _need(changed.rowcount==1,'NATIVE_WRITE_IGNORED')
     rows=[row for row in expected['rows']['fake_intents'] if tuple(row[:2])==key];_need(len(rows)==1)
     rows[0][5:9]=list(current);expected['rows']['fake_intents'].sort(key=canonical)
     event=dict(at=now,source_journal_sha256=source['journal_sha256'],status=state,order_id=order_id,
      filled_quantity=quantity,filled_notional=notional,automatic_send=False)
     FakeIntentJournal._event(self,*key,'NATIVE_SOURCE_RECONCILED',event);_expected_event(expected,key,'NATIVE_SOURCE_RECONCILED',event)
    _need(canonical(_logical_snapshot(self.db))==canonical(expected),'NATIVE_WRITE_UNEXPECTED_MUTATION')
    self._row(*key)
   _need(canonical(require_attempt_guard(self.store))==canonical(guard),'EXECUTION_COMPROMISED')
   return dict(scope='RETAINED_CONTROLLED_SOURCE_ACCOUNTING_ONLY',observed_native_count=len(native),unresolved_count=unresolved,
    source_journal_sha256=source['journal_sha256'],financial_accepted=False,transport_authorized=False,automatic_send=False)
