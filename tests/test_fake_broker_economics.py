"""Candidate transport evidence and arithmetic; never native acceptance."""
import sys
from pathlib import Path
from decimal import Decimal,localcontext
sys.path.insert(0,str(Path.cwd()/'tests'))
import pytest
from test_deterministic_broker import request
from test_execution_authority import authority
from test_execution_health import pair
from compertum.fake_execution_journal import FakeIntentJournal
from compertum.domain import ExecutionIntent
from compertum.deterministic_broker import DeterministicBroker
from compertum import fake_economic_opening as economic_opening

def test_opening_binding_survives_broker_reopen(authority,monkeypatch):
 store=authority[0].store;FakeIntentJournal(store);monkeypatch.setattr(economic_opening,'DeterministicBroker',DeterministicBroker)
 root=store.root/'state/fake-broker';b=DeterministicBroker(root,cash='5500',positions={'AAPL':45})
 try:economic_opening.provision_opening(store,b,cash='5500',positions={'AAPL':45})
 finally:b.close()
 b=DeterministicBroker(root,create=False)
 try:assert economic_opening.require_opening(store,b)=={'account_alias':'fake-account','cash':'5500','positions':{'AAPL':45}}
 finally:b.close()

@pytest.mark.parametrize('delete',['none','middle','last'])
def test_highwater_is_retained_independently_of_returned_event_count(tmp_path,delete):
 b=DeterministicBroker(tmp_path)
 try:
  order=b.submit(request());b.fill(order['order_id'],1,'100');b.fill(order['order_id'],1,'101')
  if delete!='none':
   with b.db:b.db.execute('DELETE FROM broker_events WHERE sequence=?',(2 if delete=='middle' else 3,))
  s=b.snapshot();assert s['event_sequence']==3
  assert [v['sequence'] for v in s['events']]==({'none':[1,2,3],'middle':[1,3],'last':[1,2]}[delete])
 finally:b.close()

def test_largest_fractional_fill_keeps_eight_decimal_places(tmp_path):
 b=DeterministicBroker(tmp_path,cash='5500',positions={'AAPL':999999999});p=request().to_payload();p.update(side='sell',quantity=999999999)
 try:
  ack=b.submit(ExecutionIntent(p));b.fill(ack['order_id'],999999999,'999999999999.12345678')
  s=b.snapshot()
  assert s['orders'][0]['filled_notional']=='999999998999123456780.87654322'
  assert s['cash']=='999999998999123462280.87654322'
 finally:b.close()
