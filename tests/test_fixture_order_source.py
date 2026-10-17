"""Future local order events with real files and invented clocks and requests."""
from copy import deepcopy
from types import SimpleNamespace
import json
import pytest
from compertum.data.encoding import canonical
from compertum.runtime.errors import RuntimeRefused
from test_fixture_economics import example as economics
from test_fixture_order_origin import origin
from test_fixture_order_journal import native_record,sha

@pytest.fixture
def source(tmp_path):
 from helpers.stateful_economic_fixture import ControlledEconomicSource
 from helpers.stateful_order_fixture import ControlledOrderSource
 class Clock:
  value='2026-10-17T19:00:00Z'
  def __call__(self):return self.value
 clock=Clock();begin=origin();header=economics()['ledger']
 header.update(project_id=begin['project_id'],account_alias=begin['account_alias'],asset_id=begin['asset_id'],symbol=begin['symbol'])
 economic=ControlledEconomicSource.create(tmp_path/'economic.jsonl',header,clock)
 begin.update(economic_producer_id=economic._producer,economic_genesis_sha256=economic._genesis)
 saved=dict(status='VERIFIED',records=[]);prices=['99','100']
 guard=lambda:deepcopy(saved);quotes=lambda:tuple(prices)
 orders=ControlledOrderSource.create(tmp_path/'orders.jsonl',begin,economic,clock,guard,quotes)
 f=SimpleNamespace(orders=orders,economic=economic,clock=clock,guard=guard,quotes=quotes,saved=saved,prices=prices)
 try:yield f
 finally:f.orders.close();f.economic.close()

def record(f,*,resting=False,cancel=None,sell=False):
 at='2026-10-17T19:00:01Z' if not f.saved['records'] else '2026-10-17T19:00:03Z'
 value=native_record(resting=resting,cancel=cancel,at=at)
 if sell:
  p=value['intent'];p['purpose']='CLOSE_LONG';p['request']['body']['side']='sell'
  p['request_sha256']=sha(p['request']);value['decision']['intent_sha256']=sha(p)
 f.saved['records'].append(value);f.clock.value='2026-10-17T19:00:02Z' if len(f.saved['records'])==1 else '2026-10-17T19:00:04Z'
 return value

def execute(f,value,**changes):
 p=value['intent'];request=p['request']
 args=dict(client_id=p['client_order_id'],operation=request['operation'],parameters=request['parameters'],body=request['body']);args.update(changes)
 return f.orders.execute(**args)

def test_accepted_fill_and_cash_are_durable_before_reply(source):
 value=record(source);status,raw=execute(source,value);order=json.loads(raw)
 assert status==200 and order['status']=='filled' and order['filled_avg_price']=='100'
 observed=source.orders.observations()
 assert observed['cash']=='900' and observed['positions'][0]['qty']=='1'
 assert observed['activities'][0]['order_id']==order['id']
 assert source.orders.snapshot()['transaction_count']==1
 assert source.orders.snapshot()['attempts']==[value]

def test_duplicate_after_expiry_returns_original_reply_without_new_effect(source):
 value=record(source);first=execute(source,value);before=source.orders.path.read_bytes()
 source.clock.value='2026-10-17T19:02:00Z'
 assert execute(source,value)==first and source.orders.path.read_bytes()==before

def test_reopen_keeps_original_beginning_and_committed_effect(source):
 from helpers.stateful_order_fixture import ControlledOrderSource
 value=record(source);first=execute(source,value);path=source.orders.path;before=path.read_bytes();source.orders.close()
 reopened=ControlledOrderSource.open(path,source.economic,source.clock,source.guard,source.quotes)
 try:
  assert reopened.observations()['cash']=='900'
  assert reopened.execute(client_id=value['client_order_id'],operation='SUBMIT_ORDER',parameters={},body=value['intent']['request']['body'])==first
  assert path.read_bytes()==before
 finally:reopened.close()

def test_resting_order_and_cancellation_preserve_cash_and_have_distinct_attempts(source):
 buy=record(source,resting=True);_,raw=execute(source,buy);order=json.loads(raw)
 assert order['status']=='new' and source.orders.observations()['cash']=='1000'
 cancel=record(source,cancel=order['id']);assert execute(source,cancel)==(204,b'')
 before=source.orders.path.read_bytes();assert execute(source,cancel)==(204,b'')
 observed=source.orders.observations()
 assert observed['orders'][0]['status']=='canceled' and observed['positions']==[] and observed['cash']=='1000'
 assert source.orders.snapshot()['attempts']==[buy,cancel] and source.orders.path.read_bytes()==before

def test_closing_reduces_owned_quantity_to_zero_and_records_cash(source):
 execute(source,record(source));close=record(source,sell=True);status,raw=execute(source,close)
 assert status==200 and json.loads(raw)['side']=='sell'
 observed=source.orders.observations();assert observed['positions']==[] and observed['cash']=='999'
 assert len(observed['activities'])==2 and all(row['status']=='filled' for row in observed['orders'])

@pytest.mark.parametrize('fault',['missing','unverified','changed-body','changed-client','changed-operation'])
def test_unconsumed_or_changed_request_refuses_without_appending(source,fault):
 value=record(source);before=source.orders.path.read_bytes();changes={}
 if fault=='missing':source.saved['records']=[]
 elif fault=='unverified':source.saved['status']='UNVERIFIED'
 elif fault=='changed-body':changes['body']=dict(value['intent']['request']['body'],qty='2')
 elif fault=='changed-client':changes['client_id']='cmp-'+'f'*40
 else:changes.update(operation='CANCEL_ORDER',parameters={'order_id':'11111111-1111-4111-8111-111111111111'},body=None)
 with pytest.raises(RuntimeRefused):execute(source,value,**changes)
 assert source.orders.path.read_bytes()==before

def test_cash_shortfall_refuses_before_any_source_change(source):
 value=record(source);before=source.orders.path.read_bytes();source.prices[:]=['1000','1001']
 with pytest.raises(RuntimeRefused):execute(source,value)
 assert source.orders.path.read_bytes()==before

def test_partial_tail_is_preserved_and_refused_after_reopen(source):
 from helpers.stateful_order_fixture import ControlledOrderSource
 path=source.orders.path;source.orders.close();broken=path.read_bytes()+b'{';path.write_bytes(broken)
 with pytest.raises(RuntimeRefused):ControlledOrderSource.open(path,source.economic,source.clock,source.guard,source.quotes)
 assert path.read_bytes()==broken

def test_backward_clock_refuses_without_a_new_event(source):
 value=record(source);before=source.orders.path.read_bytes();source.clock.value='2026-10-17T18:59:59Z'
 with pytest.raises(RuntimeRefused):execute(source,value)
 assert source.orders.path.read_bytes()==before

@pytest.mark.parametrize('phase',['same-time','reopened','later'])
def test_acknowledged_coverage_closes_both_journals_to_later_backdating(source,phase):
 from helpers.stateful_economic_fixture import ControlledEconomicSource
 from helpers.stateful_order_fixture import ControlledOrderSource
 value=record(source)
 source.economic.snapshot(opening_sha256='0'*64,history_sha256='0'*64,until=source.clock())
 if phase=='reopened':
  economic_path=source.economic.path;order_path=source.orders.path;source.orders.close();source.economic.close()
  source.economic=ControlledEconomicSource.open(economic_path,source.clock)
  source.orders=ControlledOrderSource.open(order_path,source.economic,source.clock,source.guard,source.quotes)
 before=(source.orders.path.read_bytes(),source.economic.path.read_bytes())
 if phase=='later':
  source.clock.value='2026-10-17T19:00:03Z';assert execute(source,value)[0]==200
  assert source.orders.snapshot()['transaction_count']==1
 else:
  with pytest.raises(RuntimeRefused):execute(source,value)
  assert (source.orders.path.read_bytes(),source.economic.path.read_bytes())==before

@pytest.mark.parametrize('field',[0,1])
def test_changed_economic_or_order_head_refuses_the_bound_request(source,field):
 value=record(source);current=source.orders.snapshot();heads=[source.economic._head,current['journal_sha256']]
 heads[field]='e'*64;before=source.orders.path.read_bytes()
 with pytest.raises(RuntimeRefused):execute(source,value,expected_heads=tuple(heads))
 assert source.orders.path.read_bytes()==before

def test_original_posted_fee_and_trade_cash_are_combined_without_rewriting_either(source):
 source.clock.value='2026-10-17T19:00:00.000001Z'
 source.economic.append(dict(event_id='order-fee-accrual',kind='ACCRUAL',rule_id='account-fee',amount='0.02'))
 source.clock.value='2026-10-17T19:00:00.000002Z'
 source.economic.append(dict(event_id='order-fee-paid',kind='PAYMENT',accrual_id='order-fee-accrual',activity_id='fixture::order-fee',amount='0.02'))
 fee_events=deepcopy(source.economic._events)
 execute(source,record(source));observed=source.orders.observations()
 assert observed['cash']=='899.98' and len(observed['activities'])==2
 assert source.economic._events==fee_events and source.orders.snapshot()['cash_delta']=='-100'
