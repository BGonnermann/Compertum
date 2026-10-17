"""Exercise advancing clocks and the durable clock fence before an order write."""
from datetime import datetime,timedelta,timezone
import json
import pytest
from compertum.runtime.errors import RuntimeRefused
from test_fixture_order_source import source,record,execute

def test_order_clock_can_advance_while_the_transaction_is_prepared(source):
 value=record(source)
 class Clock:
  def __init__(self):self.at=datetime(2026,10,17,19,0,2,tzinfo=timezone.utc)
  def __call__(self):
   self.at+=timedelta(microseconds=1);return self.at.isoformat().replace('+00:00','Z')
 clock=Clock();source.clock=source.economic.clock=source.orders.clock=clock
 assert execute(source,value)[0]==200
 at=source.orders.snapshot()['transactions'][0]['at']
 assert datetime.fromisoformat(at.replace('Z','+00:00'))<clock.at

def test_clock_ack_before_failed_order_write_does_not_invent_an_effect(source):
 from helpers.stateful_economic_fixture import ControlledEconomicSource
 value=record(source);before=source.orders.path.read_bytes();stream=source.orders._stream
 class FailedWrite:
  def __getattr__(self,name):return getattr(stream,name)
  def write(self,raw):raise OSError('INVENTED_WRITE_FAILURE')
 source.orders._stream=FailedWrite()
 with pytest.raises(RuntimeRefused):execute(source,value)
 assert source.orders.path.read_bytes()==before and source.orders.snapshot()['inventory']['orders']==[]
 ack=json.loads(source.economic.path.read_bytes().splitlines()[-1])
 assert ack['kind']=='CLOCK_ACK' and ack['at']=='2026-10-17T19:00:02Z' and ack['covered_until']<ack['at']
 path=source.economic.path;source.orders.close();source.economic.close();source.clock.value='2026-10-17T19:00:01.5Z'
 with pytest.raises(RuntimeRefused):ControlledEconomicSource.open(path,source.clock)
