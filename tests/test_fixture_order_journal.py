"""Invented order history. Parsing cannot grant native source or broker authority."""
from copy import deepcopy
import hashlib,json
from uuid import UUID,uuid5
import pytest
from compertum.data.encoding import canonical
from compertum.fixture_order_origin import decode_order_origin
from compertum.runtime.errors import RuntimeRefused
from test_fixture_order_origin import origin
from test_native_attempt_records import records
from test_paper_portfolio import order

HEAD='d'*64
def sha(value):return hashlib.sha256(canonical(value)).hexdigest()
def seal(tx):
 tx.pop('sha256',None);tx.pop('commit_sha256',None);tx['sha256']=sha(tx)
 tx['commit_sha256']=sha(dict(scope='CONTROLLED_ORDER_TRANSACTION_COMMIT_V1',transaction_sha256=tx['sha256']))
 return tx

def native_record(*,resting=False,cancel=None,at='2026-10-17T19:00:01Z'):
 p,d=records(operation='SUBMIT_ORDER' if cancel is None else 'CANCEL_ORDER')
 p['created_at']=p['request']['created_at']=at;p['expires_at']='2026-10-17T19:01:00Z'
 if cancel is None:
  p['request']['body']['symbol']='MSFT'
  if resting:p['purpose']='FIXTURE_RESTING_BUY';p['request']['body'].update(type='limit',limit_price='80')
 else:p['request']['parameters']['order_id']=cancel
 from compertum.runtime._winhttp_order import _wire
 method,target,_=_wire(p['request']['operation'],p['request']['parameters'],p['request']['body'])
 p['request'].update(method=method,target=target);p['request_sha256']=sha(p['request']);d['intent_sha256']=sha(p)
 return dict(intent=p,decision=d,attempted_at=at,client_order_id=p['client_order_id'])

def append(raw,record,events,*,at='2026-10-17T19:00:02Z'):
 lines=raw.splitlines();begin=json.loads(lines[0]);previous=json.loads(lines[-1])
 p=record['intent'];identity=str(uuid5(UUID(begin['producer_id']),p['client_order_id']+':'+p['request_sha256']))
 events=deepcopy(events)
 for index,event in enumerate(events):event['event_id']=str(uuid5(UUID(identity),'event:'+str(index)))
 tx=dict(version=1,kind='ORDER_TRANSACTION',transaction_id=identity,sequence=len(lines),
  previous_sha256=decode_order_origin(lines[0]+b'\n')['genesis_sha256'] if len(lines)==1 else previous['sha256'],
  at=at,economic_head_sha256=HEAD,attempt=record,events=events)
 return raw+canonical(seal(tx))+b'\n'

def example(*,resting=False):
 begin=origin();raw=canonical(begin)+b'\n';record=native_record(resting=resting);p=record['intent']
 identity=str(uuid5(UUID(begin['producer_id']),p['client_order_id']))
 observed=order(id=identity,client_order_id=p['client_order_id'],asset_id=begin['asset_id'],symbol='MSFT',qty='1',
  submitted_at=p['created_at'],type='limit' if resting else 'market',limit_price='80' if resting else None)
 events=[dict(kind='ORDER_ACCEPTED',order=observed)]
 if not resting:
  filled=dict(observed,status='filled',filled_qty='1',filled_avg_price='100')
  fill=dict(id='trade::'+identity,activity_type='FILL',order_id=identity,transaction_time='2026-10-17T19:00:02Z',
   type='fill',symbol='MSFT',side='buy',qty='1',cum_qty='1',leaves_qty='0',price='100')
  events += [dict(kind='ORDER_FILLED',order=filled,fill=fill),dict(kind='CASH_MOVEMENT',order_id=identity,fill_id=fill['id'],currency='USD',amount='-100')]
 return append(raw,record,events),record,observed

def decode(raw,heads=(HEAD,)):
 from compertum.fixture_order_journal import decode_order_journal
 return decode_order_journal(raw,economic_heads=heads)

def changed(raw,change):
 lines=raw.splitlines();tx=json.loads(lines[-1]);change(tx)
 return b'\n'.join(lines[:-1])+b'\n'+canonical(seal(tx))+b'\n'

def test_committed_order_fill_and_cash_preserve_the_original_beginning():
 raw,record,observed=example();result=decode(raw)
 assert result['origin']==origin() and result['transaction_count']==1
 assert result['inventory']['orders'][0]['status']=='filled'
 assert result['inventory']['positions'][0]['qty']=='1' and result['inventory']['positions'][0]['cost_basis']=='100'
 assert len(result['inventory']['fills'])==1 and result['cash_delta']=='-100'
 first=canonical(origin())+b'\n'
 assert hashlib.sha256(first).hexdigest() in result['prefix_sha256']
 assert result['journal_sha256']==hashlib.sha256(raw).hexdigest()
 assert result['source_qualified'] is result['financial_accepted'] is result['transport_authorized'] is False

def test_empty_original_source_remains_compatible():
 raw=canonical(origin())+b'\n';result=decode(raw,())
 assert result['inventory']==dict(orders=[],positions=[],fills=[]) and result['cash_delta']=='0'
 assert result['transaction_count']==0

def test_resting_order_and_exact_cancellation_have_no_cash_effect():
 raw,_,observed=example(resting=True);record=native_record(cancel=observed['id'],at='2026-10-17T19:00:03Z')
 raw=append(raw,record,[dict(kind='ORDER_CANCELED',order=dict(observed,status='canceled'))],at='2026-10-17T19:00:04Z')
 result=decode(raw)
 assert result['inventory']['orders'][0]['status']=='canceled' and result['cash_delta']=='0'
 assert result['inventory']['positions']==result['inventory']['fills']==[] and result['transaction_count']==2

@pytest.mark.parametrize('fault',['version','sequence','previous','economic','request','commit','event-id','asset','cash','fill-quantity','fill-price','future-fill','unknown-kind','missing-cash','cash-without-fill','extra-field'])
def test_valid_hashes_cannot_hide_invalid_effects(fault):
 raw,_,_=example()
 def damage(tx):
  if fault=='version':tx['version']=True
  elif fault=='sequence':tx['sequence']=True
  elif fault=='previous':tx['previous_sha256']='e'*64
  elif fault=='economic':tx['economic_head_sha256']='e'*64
  elif fault=='request':tx['attempt']['intent']['request_sha256']='e'*64
  elif fault=='event-id':tx['events'][1]['event_id']=tx['events'][0]['event_id']
  elif fault=='asset':tx['events'][1]['order']['asset_id']='33333333-3333-4333-8333-333333333333'
  elif fault=='cash':tx['events'][2]['amount']='-99'
  elif fault=='fill-quantity':tx['events'][1]['fill']['cum_qty']='2'
  elif fault=='fill-price':tx['events'][1]['order']['filled_avg_price']='99'
  elif fault=='future-fill':tx['events'][1]['fill']['transaction_time']='2026-10-17T19:00:03Z'
  elif fault=='unknown-kind':tx['events'][0]['kind']='INVENTED'
  elif fault=='missing-cash':tx['events'].pop()
  elif fault=='cash-without-fill':tx['events']=[tx['events'][0],tx['events'][2]]
  elif fault=='extra-field':tx['approved']=True
 if fault=='commit':
  lines=raw.splitlines();tx=json.loads(lines[-1]);tx['commit_sha256']='e'*64;raw=lines[0]+b'\n'+canonical(tx)+b'\n'
 else:raw=changed(raw,damage)
 with pytest.raises(RuntimeRefused):decode(raw)

@pytest.mark.parametrize('fault',['partial','oversize','duplicate','unknown-head','changed-origin','backward-time'])
def test_incomplete_or_replayed_history_refuses(fault):
 raw,record,_=example()
 if fault=='partial':raw=raw[:-1]
 elif fault=='oversize':raw=b'x'*(128*1024+1)
 elif fault=='duplicate':raw=append(raw,record,json.loads(raw.splitlines()[-1])['events'],at='2026-10-17T19:00:03Z')
 elif fault=='changed-origin':
  lines=raw.splitlines();begin=json.loads(lines[0]);begin['initial_cash']='999';raw=canonical(begin)+b'\n'+lines[1]+b'\n'
 elif fault=='backward-time':raw=changed(raw,lambda tx:tx.update(at='2026-10-17T18:59:59Z'))
 with pytest.raises(RuntimeRefused):decode(raw,() if fault=='unknown-head' else (HEAD,))
