"""Reproduce unexplained economics under real owners; small reserve is simulated."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path.cwd()/'tests'))
import pytest
from test_execution_observations import observed_owner
from test_execution_authority import authority
from test_execution_health import pair
from compertum.deterministic_broker import DeterministicBroker
from compertum.runtime.errors import RuntimeRefused

@pytest.mark.parametrize('change',['share','cash'])
def test_unexplained_broker_change_cannot_be_adopted_as_owned_economics(authority,change):
 owner=observed_owner(authority)
 broker=DeterministicBroker(authority[0].store.root/'state/fake-broker',create=False)
 try:
  with broker.db:
   if change=='share':broker.db.execute("UPDATE positions SET quantity=quantity+1 WHERE symbol='AAPL'")
   else:broker.db.execute("UPDATE account SET cash='5500.02'")
 finally:broker.close()
 with pytest.raises(RuntimeRefused,match='FAKE_ECONOMIC_RECONCILIATION'):
  owner.read()


from test_fake_execution_journal import native
from test_fake_execution_driver import records
from test_execution_risk import NOW,calendar
from compertum.fake_economic_opening import provision_opening
from compertum.fake_execution_driver import FakeExecutionDriver
from compertum.fake_attempt_guard import require_attempt_guard

@pytest.mark.parametrize('change',['cash','share','foreign_order'])
def test_both_driver_observation_and_dispatch_refuse_unexplained_economics(native,change):
 project,lease,store,j=native;b=DeterministicBroker(project.root_path/'state/fake-broker')
 try:
  provision_opening(store,b,cash='10000',positions={});driver=FakeExecutionDriver(j,b);i,o,inputs=records(lease)
  if change=='cash':
   with b.db:b.db.execute("UPDATE account SET cash='10000.02'")
  elif change=='share':
   with b.db:b.db.execute("INSERT INTO positions VALUES('AAPL',1)")
  else:b.submit(i)
  calls=b.snapshot()['calls']
  with pytest.raises(RuntimeRefused,match='FAKE_ECONOMIC_RECONCILIATION'):driver.observation(o,now=NOW)
  with pytest.raises(RuntimeRefused,match='FAKE_ECONOMIC_RECONCILIATION'):driver.dispatch(i,o,now=NOW,calendar=calendar(),inputs=inputs)
  assert b.snapshot()['calls']==calls and require_attempt_guard(store)['sequence']==0
 finally:b.close()


def test_missing_final_fill_event_cannot_hide_changed_cash(native):
 project,lease,store,j=native;b=DeterministicBroker(project.root_path/'state/fake-broker')
 try:
  provision_opening(store,b,cash='10000',positions={});driver=FakeExecutionDriver(j,b);i,o,inputs=records(lease)
  first=driver.dispatch(i,o,now=NOW,calendar=calendar(),inputs=inputs);b.fill(first['order_id'],1,'100')
  with b.db:b.db.execute('DELETE FROM broker_events WHERE sequence=2')
  assert b.snapshot()['event_sequence']==2
  with pytest.raises(RuntimeRefused,match='FAKE_ECONOMIC_RECONCILIATION'):driver.observation(o,now=NOW)
  assert len(b.snapshot()['calls'])==1
 finally:b.close()
