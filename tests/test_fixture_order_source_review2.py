"""Check causal time and coverage across the two original local journals."""
import pytest
from compertum.runtime.errors import RuntimeRefused
from test_fixture_order_source import source,record,execute
from test_fixture_order_source_binding import prepared

@pytest.mark.parametrize('operation',['append','snapshot'])
@pytest.mark.parametrize('reopened',[False,True])
def test_economic_writes_cannot_precede_a_durable_order(source,operation,reopened):
 from helpers.stateful_economic_fixture import ControlledEconomicSource
 from helpers.stateful_order_fixture import ControlledOrderSource
 execute(source,record(source))
 if reopened:
  ep,op=source.economic.path,source.orders.path;source.orders.close();source.economic.close()
  source.economic=ControlledEconomicSource.open(ep,source.clock)
  source.orders=ControlledOrderSource.open(op,source.economic,source.clock,source.guard,source.quotes)
 before=source.economic.path.read_bytes(),source.orders.path.read_bytes()
 source.clock.value='2026-10-17T19:00:01.5Z'
 with pytest.raises(RuntimeRefused):
  if operation=='append':source.economic.append(dict(event_id='backdated',kind='ACCRUAL',rule_id='account-fee',amount='0.02'))
  else:source.economic.snapshot(opening_sha256='0'*64,history_sha256='0'*64,until=source.clock())
 assert (source.economic.path.read_bytes(),source.orders.path.read_bytes())==before

@pytest.mark.parametrize('kind',['fill','cancel'])
@pytest.mark.parametrize('boundary',['before','at','after'])
def test_economic_coverage_contains_every_current_order_transaction(source,monkeypatch,kind,boundary):
 import json
 import test_fixture_order_source_binding as binding
 if kind=='cancel':
  original_record=binding.record
  monkeypatch.setattr(binding,'record',lambda f:original_record(f,resting=True))
  def pair(f,value):
   _,raw=execute(f,value);execute(f,record(f,cancel=json.loads(raw)['id']))
  monkeypatch.setattr(binding,'execute',pair)
 module,owner,context,base,originals,rows,orders=prepared(source,monkeypatch)
 second='02' if kind=='fill' else '04'
 until=f'2026-10-17T19:00:{second}Z'
 if boundary=='before':until=f'2026-10-17T19:00:{int(second)-1:02}.999999Z'
 if boundary=='after':until=f'2026-10-17T19:00:{second}.000001Z'
 rows['current'][1]['ledger']['covered_until']=until
 # Model an original account receipt after the requested coverage boundary.
 rows['current'][0]['parsed']['received_at']='2026-10-17T19:00:05Z'
 if boundary=='after':
  source.clock.value='2026-10-17T19:00:05Z'
  source.economic.snapshot(opening_sha256='0'*64,history_sha256='0'*64,until=until)
  from compertum.fixture_source_journal import decode_source_journal
  monkeypatch.setattr(module,'source_file',lambda lease:(decode_source_journal(source.economic.path.read_bytes()),[1,'0'*32]))
 if boundary=='before':
  with pytest.raises(RuntimeRefused):module._source_snapshot(owner,context,base,originals)
 else:module._source_snapshot(owner,context,base,originals)[2]()
