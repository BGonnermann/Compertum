"""Explicit opening pinned before any fake-broker effects.

Partial provision records are retained and refused; reads never repair them.
"""
from contextlib import contextmanager,closing
from pathlib import Path
import hashlib,json,os,sqlite3
from compertum.persistence import StateStore,checked_path
from compertum.runtime.errors import RuntimeRefused
from compertum.runtime.owners import require_live_owner
from compertum.deterministic_broker import DeterministicBroker
from compertum.fake_attempt_guard import require_attempt_guard
from compertum.data.encoding import canonical
from compertum.fake_economic_ledger import money,positions
from compertum.simulation.policy import number

CODE='FAKE_OPENING_UNVERIFIED'
KEY='fake_economic_opening'
MAX_BYTES=8192

def require(value):
 if not value:raise RuntimeRefused(CODE)

@contextmanager
def scope(store,broker):
 try:
  require(type(store) is StateStore and type(broker) is DeterministicBroker)
  with store._live() as guard:
   require_live_owner(store.lease,'execution')
   require(not store.conn.in_transaction and not broker.db.in_transaction)
   expected=checked_path(store.root,store.root/'state/fake-broker/deterministic-broker.sqlite')
   require(broker.path==expected)
   path=checked_path(store.root,store.root/'state/fake-economic-opening.json')
   require_attempt_guard(store)
   yield guard,path
 except (OSError,ValueError,TypeError,KeyError,sqlite3.Error,RuntimeRefused):raise RuntimeRefused(CODE) from None

def mirror(store):
 row=store.conn.execute("SELECT CASE WHEN length(CAST(value AS BLOB))<=1024 THEN value END FROM state WHERE key=?",(KEY,)).fetchone()
 if row is None:return None
 require(row[0] is not None)
 return json.loads(row[0])

def identity(broker):
 rows=broker.db.execute('SELECT CASE WHEN length(key)<=64 THEN key END,CASE WHEN length(value)<=128 THEN value END FROM fixture_identity LIMIT 6').fetchall()
 require(len(rows)<=4 and all(k is not None and v is not None for k,v in rows))
 return dict(rows)

def payload(project,account,cash,holdings):
 cash=number(money(cash));normalized=positions(holdings)
 require(type(account) is str and account.startswith('fake-'))
 result={'schema':'fake-economic-opening-v1','project_id':project,'account_alias':account,'cash':cash,'positions':normalized}
 require(len(canonical(result))<=MAX_BYTES)
 return result

def _read(store,broker,guard,path):
 with guard.api.open_file(path,0x80000000,1) as pin:
  info=guard.api.file_info(pin)
  require(not info.attributes&(0x400|0x10) and info.links==1 and (info.size_hi<<32|info.size_lo)<=MAX_BYTES)
  raw=guard.api.read_regular(path,MAX_BYTES);value=json.loads(raw)
  require(type(value) is dict and set(value)=={'schema','project_id','account_alias','cash','positions'})
  require(value==payload(store.lease.project_id,broker.account,value['cash'],value['positions']) and canonical(value)==raw)
  sha=hashlib.sha256(raw).hexdigest();pin_value={'schema':'fake-economic-opening-pin-v1','sha256':sha,'account_alias':broker.account}
  require(mirror(store)==pin_value)
  require(identity(broker)=={'schema':'2','scope':'DETERMINISTIC_FAKE','account':broker.account,'opening_sha256':sha})
  return value,pin_value

def require_opening(store,broker):
 with scope(store,broker) as (guard,path):
  value,_=_read(store,broker,guard,path)
  return {k:value[k] for k in ('account_alias','cash','positions')}

def provision_opening(store,broker,*,cash,positions):
 with scope(store,broker) as (guard,path):
  value=payload(store.lease.project_id,broker.account,cash,positions);raw=canonical(value)
  if path.exists() or mirror(store) is not None or 'opening_sha256' in identity(broker):
   old,pin=_read(store,broker,guard,path);require(old==value);return pin
  require(require_attempt_guard(store)['sequence']==0)
  pin={'schema':'fake-economic-opening-pin-v1','sha256':hashlib.sha256(raw).hexdigest(),'account_alias':broker.account}
  with broker._transaction():
   require(identity(broker)=={'schema':'1','scope':'DETERMINISTIC_FAKE','account':broker.account})
   require(broker.db.execute("SELECT CASE WHEN typeof(alias)='text' AND length(CAST(alias AS BLOB))<=64 THEN alias END,CASE WHEN typeof(cash)='text' AND length(CAST(cash AS BLOB))<=30 THEN cash END FROM account LIMIT 2").fetchall()==[(broker.account,value['cash'])])
   rows=broker.db.execute("SELECT CASE WHEN typeof(symbol)='text' AND length(CAST(symbol AS BLOB))<=8 THEN symbol END,CASE WHEN typeof(quantity)='integer' AND quantity BETWEEN 0 AND 1000000000 THEN quantity END FROM positions LIMIT 65").fetchall()
   require(len(rows)<=64 and all(s is not None and n is not None for s,n in rows) and {s:n for s,n in rows if n}==value['positions'])
   require(all(broker.db.execute('SELECT COUNT(*) FROM '+table).fetchone()==(0,) for table in ('orders','calls','broker_events')))
   require(not broker.db.execute('SELECT 1 FROM sqlite_sequence WHERE seq>0 LIMIT 1').fetchone())
   with path.open('xb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
   broker.db.execute("UPDATE fixture_identity SET value='2' WHERE key='schema'")
   broker.db.execute("INSERT INTO fixture_identity VALUES('opening_sha256',?)",(pin['sha256'],))
  with store.conn:store.conn.execute('INSERT INTO state VALUES(?,?)',(KEY,canonical(pin).decode()))
  _read(store,broker,guard,path)
  return pin


def validate_pin(value):
 import re
 require(type(value) is dict and set(value)=={'schema','sha256','account_alias'} and value['schema']=='fake-economic-opening-pin-v1')
 require(type(value['sha256']) is str and re.fullmatch('[0-9a-f]{64}',value['sha256']) and type(value['account_alias']) is str and re.fullmatch('fake-[a-z0-9_-]{1,48}',value['account_alias']))
 return value


def verify_opening(project):
 """Read-only recovery proof. Missing legacy opening never creates authority."""
 from compertum.runtime._windows import WindowsAPI
 failed={'status':'EXECUTION_COMPROMISED','pin':None}
 try:
  root=project.root_path;path=checked_path(root,root/'state/fake-economic-opening.json');dbpath=checked_path(root,root/'state/fake-broker/deterministic-broker.sqlite')
  ident=None
  if dbpath.exists():
   for suffix in ('-wal','-shm'):checked_path(root,Path(str(dbpath)+suffix))
   with closing(sqlite3.connect(dbpath.as_uri()+'?mode=ro',uri=True,timeout=1)) as conn:
    rows=conn.execute('SELECT CASE WHEN length(key)<=64 THEN key END,CASE WHEN length(value)<=128 THEN value END FROM fixture_identity LIMIT 6').fetchall()
    require(len(rows)<=4 and all(k is not None and v is not None for k,v in rows));ident=dict(rows)
  if not path.exists():
   require(ident is None or set(ident)=={'schema','scope','account'} and ident['schema']=='1' and ident['scope']=='DETERMINISTIC_FAKE')
   return {'status':'UNRECORDED','pin':None}
  api=WindowsAPI()
  with api.open_file(path,0x80000000,1) as held:
   info=api.file_info(held);require(not info.attributes&(0x400|0x10) and info.links==1 and (info.size_hi<<32|info.size_lo)<=MAX_BYTES)
   raw=api.read_regular(path,MAX_BYTES);value=json.loads(raw)
   require(type(value) is dict and set(value)=={'schema','project_id','account_alias','cash','positions'})
   require(value==payload(project.project_id,value['account_alias'],value['cash'],value['positions']) and canonical(value)==raw)
   pin=validate_pin({'schema':'fake-economic-opening-pin-v1','sha256':hashlib.sha256(raw).hexdigest(),'account_alias':value['account_alias']})
   require(ident=={'schema':'2','scope':'DETERMINISTIC_FAKE','account':pin['account_alias'],'opening_sha256':pin['sha256']})
   return {'status':'VERIFIED','pin':pin}
 except (OSError,ValueError,TypeError,KeyError,sqlite3.Error,RuntimeRefused):return failed
