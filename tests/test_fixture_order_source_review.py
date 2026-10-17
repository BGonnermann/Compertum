"""Review findings for the invented local source. No native authority is supplied."""
import json
import pytest
from compertum.runtime.errors import RuntimeRefused
from test_fixture_order_source import source,record,execute

@pytest.mark.parametrize('event',['ack','fee'])
@pytest.mark.parametrize('reopened',[False,True])
def test_order_cannot_precede_either_sources_durable_clock(source,event,reopened):
 from helpers.stateful_economic_fixture import ControlledEconomicSource
 from helpers.stateful_order_fixture import ControlledOrderSource
 value=record(source);source.clock.value='2026-10-17T19:00:10Z'
 if event=='ack':source.economic.snapshot(opening_sha256='0'*64,history_sha256='0'*64,until='2026-10-17T19:00:02Z')
 else:source.economic.append(dict(event_id='later-fee',kind='ACCRUAL',rule_id='account-fee',amount='0.02'))
 if reopened:
  ep,op=source.economic.path,source.orders.path;source.orders.close();source.economic.close()
  source.economic=ControlledEconomicSource.open(ep,source.clock)
  source.orders=ControlledOrderSource.open(op,source.economic,source.clock,source.guard,source.quotes)
 before=(source.orders.path.read_bytes(),source.economic.path.read_bytes());source.clock.value='2026-10-17T19:00:04Z'
 with pytest.raises(RuntimeRefused):execute(source,value)
 assert (source.orders.path.read_bytes(),source.economic.path.read_bytes())==before

@pytest.mark.parametrize('quote',['unavailable','malformed'])
def test_cancel_needs_no_quote_callback(source,quote):
 _,raw=execute(source,record(source,resting=True));order=json.loads(raw)
 value=record(source,cancel=order['id']);calls=[]
 def bad():
  calls.append(True)
  if quote=='unavailable':raise RuntimeRefused('QUOTE_UNAVAILABLE')
  return ('bad',)
 source.orders.quotes=bad
 assert execute(source,value)==(204,b'')
 observed=source.orders.observations()
 assert calls==[] and observed['cash']=='1000' and observed['orders'][0]['status']=='canceled'
