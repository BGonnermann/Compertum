"""Test-only future order events. These invented replies grant no broker authority."""
from decimal import Context,Decimal,Inexact,InvalidOperation,Overflow,Rounded,localcontext
import hashlib,json,os,threading
from pathlib import Path
from uuid import UUID,uuid4,uuid5
from compertum.attempt_records import record_key
from compertum.data.encoding import canonical
from compertum.fixture_order_journal import decode_order_journal
from compertum.fixture_order_origin import decode_order_origin
from compertum.native_attempt_records import validate_pair
from compertum.paper_contracts import number
from compertum.runtime.errors import RuntimeRefused
from compertum.runtime.paper_read_packet import _nanoseconds
from .stateful_economic_fixture import ControlledEconomicSource,checked_path as economic_path

ROOT=Path(__file__).parents[2]
NATIVE=ROOT/'.cache/test-runs/native-economic-fresh-20261017-01/native-shared/state/fixture-order-source.jsonl'
_INVALID=(OSError,ValueError,TypeError,KeyError,AttributeError,OverflowError,RecursionError,UnicodeError,InvalidOperation,Inexact,Rounded)

def need(value):
 if not value:raise RuntimeRefused('CONTROLLED_ORDER_SOURCE_UNVERIFIED')

def sha(value):return hashlib.sha256(canonical(value)).hexdigest()

def text(value):
 value=format(value,'f');return value.rstrip('0').rstrip('.') if '.' in value else value

def checked_path(path):
 path=Path(path)
 if path!=NATIVE:return economic_path(path)
 need(path.is_absolute() and path==path.resolve() and path.is_file())
 current=path
 while current!=ROOT:
  need(not current.lstat().st_file_attributes&0x400);current=current.parent
 return path

class ControlledOrderSource:
 def __repr__(self):return '<ControlledOrderSource invented local values redacted>'
 @classmethod
 def create(cls,path,begin,economic,clock,guard,quotes,*,lock=None):
  try:
   path=checked_path(path);need(path!=NATIVE and not path.exists())
   raw=canonical(begin)+b'\n';decode_order_origin(raw)
   with path.open('xb',buffering=0) as stream:
    need(stream.write(raw)==len(raw));stream.flush();os.fsync(stream.fileno())
   return cls.open(path,economic,clock,guard,quotes,lock=lock)
  except _INVALID:raise RuntimeRefused('CONTROLLED_ORDER_SOURCE_UNVERIFIED') from None
 @classmethod
 def open(cls,path,economic,clock,guard,quotes,*,lock=None):
  value=cls.__new__(cls);value._stream=None
  try:
   value.path=checked_path(path);need(type(economic) is ControlledEconomicSource)
   need(callable(clock) and clock is economic.clock and callable(guard) and callable(quotes))
   value.economic=economic;value.clock=clock;value.guard=guard;value.quotes=quotes;value.lock=lock or threading.RLock()
   value._stream=value.path.open('r+b',buffering=0);info=os.fstat(value._stream.fileno());need(info.st_nlink==1)
   value._identity=(info.st_dev,info.st_ino);value._raw=value._stream.read(128*1024+1)
   decoded=value._decode(value._raw);begin=decoded['origin'];header=economic._header
   need(begin['economic_producer_id']==economic._producer and begin['economic_genesis_sha256']==economic._genesis)
   need(all(begin[key]==header[key] for key in ('project_id','account_alias','asset_id','symbol')) and begin['initial_cash']==header['opening_cash'])
   value._last_ns=_nanoseconds(decoded['transactions'][-1]['at'] if decoded['transactions'] else begin['created_at'])
   if value.path==NATIVE:
    birth=json.loads((ROOT/'artifacts/m5/native-economics-20261017-01/original-order-source-birth01.json').read_text())
    need(hashlib.sha256(value._raw.splitlines(keepends=True)[0]).hexdigest()==birth['origin_sha256'])
    from compertum.runtime._windows import WindowsAPI
    api=WindowsAPI()
    with api.open_file(value.path,0x80,1) as handle:need(list(api.file_identity(handle))==birth['file_identity'])
   value._live();value._now();return value
  except (RuntimeRefused,*_INVALID):value.close();raise RuntimeRefused('CONTROLLED_ORDER_SOURCE_UNVERIFIED') from None
 def _heads(self):
  return (self.economic._genesis,*(event['sha256'] for event in self.economic._events))
 def _decode(self,raw):return decode_order_journal(raw,economic_heads=self._heads())
 def _record(self,client):
  evidence=self.guard();need(type(evidence) is dict and evidence['status']=='VERIFIED' and type(evidence['records']) is list and len(evidence['records'])<=256)
  matches=[row for row in evidence['records'] if type(row) is dict and row.get('client_order_id')==client]
  need(len(matches)==1);record=json.loads(canonical(matches[0]));record_key(record);p,_,_=validate_pair(record['intent'],record['decision'])
  need(p['project_id']==self._begin['project_id'] and p['account_alias']==self._begin['account_alias']);return record
 def _live(self):
  need(self._stream is not None and not self._stream.closed);self.economic._live()
  info=self.path.stat(follow_symlinks=False);opened=os.fstat(self._stream.fileno())
  need((info.st_dev,info.st_ino)==self._identity==(opened.st_dev,opened.st_ino) and info.st_nlink==opened.st_nlink==1 and not info.st_file_attributes&0x400)
  self._stream.seek(0);need(self._stream.read(128*1024+1)==self._raw)
  result=self._decode(self._raw);self._begin=result['origin']
  for record in result['attempts']:need(self._record(record['client_order_id'])==record)
  return result
 def _now(self):
  stamp=self.clock();need(_nanoseconds(stamp)>=max(self._last_ns,self.economic._last_clock));return stamp
 def _fee_cash(self):
  # No coverage acknowledgement occurs while preparing an order. The write
  # must remain strictly after the last already acknowledged interval.
  cash=number(self.economic._header['opening_cash']);seen={}
  for event in self.economic._events:
   kind=event['kind'];amount=number(event['amount']);effect=Decimal(0)
   if kind=='PAYMENT':effect=-amount
   elif kind=='UNLINKED_CREDIT':effect=amount
   elif kind=='REVERSAL' and seen[event['event_id_reversed']]['kind']=='PAYMENT':effect=amount
   cash+=effect;seen[event['event_id']]=event
  return cash
 def snapshot(self):
  with self.lock:return json.loads(canonical(self._live()))
 def observations(self):
  with self.lock:
   current=self._live();self._now();economic=self.economic.observations()
   need(self.economic._closed_until>=self._last_ns);inventory=current['inventory']
   with localcontext(Context(prec=160,traps=[InvalidOperation,Overflow,Inexact,Rounded])):
    cash=text(number(economic['cash'])+number(current['cash_delta']))
   return dict(cash=cash,orders=inventory['orders'],positions=inventory['positions'],activities=[*economic['activities'],*inventory['fills']])
 def _reply(self,current,record):
  p=record['intent'];outcome=current['request_outcomes'][p['intent_id']]
  if p['request']['operation']=='CANCEL_ORDER':return (204,b'') if outcome=='CANCELED' else (409,canonical(dict(code='CONTROLLED_CANCEL_REJECTED')))
  rows=[row for row in current['inventory']['orders'] if row['client_order_id']==p['client_order_id']];need(len(rows)==1)
  return 200,canonical(rows[0])
 def execute(self,*,client_id,operation,parameters,body,expected_heads=None):
  try:
   with self.lock,localcontext(Context(prec=160,traps=[InvalidOperation,Overflow,Inexact,Rounded])):
    current=self._live();record=self._record(client_id);p=record['intent'];request=p['request']
    need(operation==request['operation'] and canonical(parameters)==canonical(request['parameters']) and canonical(body)==canonical(request['body']))
    if p['intent_id'] in current['request_outcomes']:return self._reply(current,record)
    if operation!='CANCEL_ORDER':
     prices=self.quotes();need(type(prices) in (tuple,list) and len(prices)==2)
     bid,ask=(number(price,positive=True) for price in prices);need(bid<=ask)
    self._live();need(self._record(client_id)==record)
    if expected_heads is not None:need(type(expected_heads) is tuple and expected_heads==(self.economic._head,current['journal_sha256']))
    at=self._now();need(_nanoseconds(at)>self.economic._closed_until)
    need(_nanoseconds(at)>_nanoseconds(self._begin['created_at']))
    events=[]
    if operation=='CANCEL_ORDER':
     rows=[row for row in current['inventory']['orders'] if row['id']==parameters['order_id'] and row['status'] in {'new','partially_filled'}]
     need(len(rows)==1);events=[dict(kind='ORDER_CANCELED',order=dict(rows[0],status='canceled'))]
    else:
     need(operation=='SUBMIT_ORDER' and type(body) is dict)
     row=dict(id=str(uuid5(UUID(self._begin['producer_id']),client_id)),client_order_id=client_id,
      asset_id=self._begin['asset_id'],asset_class='us_equity',order_class='simple',symbol=body['symbol'],qty=body['qty'],
      filled_qty='0',filled_avg_price=None,side=body['side'],type=body['type'],time_in_force=body['time_in_force'],
      extended_hours=False,status='new',limit_price=body.get('limit_price'),submitted_at=at,legs=None)
     events=[dict(kind='ORDER_ACCEPTED',order=row)]
     price=ask if body['side']=='buy' else bid
     if body['type']=='market' or price<=number(body['limit_price'],positive=True):
      quantity=number(body['qty'],positive=True);fill_id='controlled::'+row['id']
      filled=dict(row,status='filled',filled_qty=body['qty'],filled_avg_price=text(price))
      fill=dict(id=fill_id,activity_type='FILL',order_id=row['id'],transaction_time=at,type='fill',symbol=row['symbol'],side=row['side'],
       qty=body['qty'],cum_qty=body['qty'],leaves_qty='0',price=text(price))
      events.extend([dict(kind='ORDER_FILLED',order=filled,fill=fill),dict(kind='CASH_MOVEMENT',order_id=row['id'],fill_id=fill_id,
       currency='USD',amount=text(price*quantity*(-1 if row['side']=='buy' else 1)))])
    identity=str(uuid4())
    for index,event in enumerate(events):event['event_id']=str(uuid5(UUID(identity),'event:'+str(index)))
    transaction=dict(version=1,kind='ORDER_TRANSACTION',transaction_id=identity,sequence=current['transaction_count']+1,
     previous_sha256=current['head_sha256'],at=at,economic_head_sha256=self.economic._head,attempt=record,events=events)
    transaction['sha256']=sha(transaction);transaction['commit_sha256']=sha(dict(scope='CONTROLLED_ORDER_TRANSACTION_COMMIT_V1',transaction_sha256=transaction['sha256']))
    line=canonical(transaction)+b'\n';candidate=self._raw+line;need(len(line)<=65536 and len(candidate)<=128*1024)
    checked=self._decode(candidate);need(self._fee_cash()+number(checked['cash_delta'])>=0)
    self.economic.advance_order_clock(at)
    self._stream.seek(0,2);need(self._stream.write(line)==len(line));self._stream.flush();os.fsync(self._stream.fileno())
    self._raw=candidate;self._last_ns=_nanoseconds(at);need(self._live()==checked)
    return self._reply(checked,record)
  except _INVALID:raise RuntimeRefused('CONTROLLED_ORDER_SOURCE_UNVERIFIED') from None
 def close(self):
  if self._stream is not None:self._stream.close();self._stream=None
 def reject_unseen(self,*,client_id,expected_heads):
  """Record a future denial. A missing reply alone never establishes absence."""
  try:
   with self.lock,localcontext(Context(prec=160,traps=[InvalidOperation,Overflow,Inexact,Rounded])):
    current=self._live();record=self._record(client_id);p=record['intent'];request=p['request']
    if p['intent_id'] in current['request_outcomes']:return self._reply(current,record)
    need(type(expected_heads) is tuple and expected_heads==(self.economic._head,current['journal_sha256']))
    at=self._now();need(_nanoseconds(at)>max(self.economic._closed_until,self.economic._last_at,_nanoseconds(self._begin['created_at'])))
    if request['operation']=='CANCEL_ORDER':
     rows=[row for row in current['inventory']['orders'] if row['id']==request['parameters']['order_id'] and row['status'] in {'new','partially_filled'}]
     need(len(rows)==1);row=rows[0]
    else:
     body=request['body'];row=dict(id=str(uuid5(UUID(self._begin['producer_id']),client_id)),client_order_id=client_id,
      asset_id=self._begin['asset_id'],asset_class='us_equity',order_class='simple',symbol=body['symbol'],qty=body['qty'],
      filled_qty='0',filled_avg_price=None,side=body['side'],type=body['type'],time_in_force=body['time_in_force'],
      extended_hours=False,status='rejected',limit_price=body.get('limit_price'),submitted_at=at,legs=None)
    identity=str(uuid4());event=dict(event_id=str(uuid5(UUID(identity),'event:0')),kind='ORDER_REJECTED',order=row)
    transaction=dict(version=1,kind='ORDER_TRANSACTION',transaction_id=identity,sequence=current['transaction_count']+1,
     previous_sha256=current['head_sha256'],at=at,economic_head_sha256=self.economic._head,attempt=record,events=[event])
    transaction['sha256']=sha(transaction);transaction['commit_sha256']=sha(dict(scope='CONTROLLED_ORDER_TRANSACTION_COMMIT_V1',transaction_sha256=transaction['sha256']))
    line=canonical(transaction)+b'\n';candidate=self._raw+line;need(len(line)<=65536 and len(candidate)<=128*1024)
    checked=self._decode(candidate);self.economic.advance_order_clock(at)
    self._stream.seek(0,2);need(self._stream.write(line)==len(line));self._stream.flush();os.fsync(self._stream.fileno())
    self._raw=candidate;self._last_ns=_nanoseconds(at);need(self._live()==checked);return self._reply(checked,record)
  except _INVALID:raise RuntimeRefused('CONTROLLED_ORDER_SOURCE_UNVERIFIED') from None
