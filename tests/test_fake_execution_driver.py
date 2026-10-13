"""Joined fixture driver: no second submit after uncertain acceptance."""
from datetime import timedelta
import pytest
from compertum.domain import ExecutionObservation,ExecutionIntent
from compertum.execution_contracts import instant
from compertum.execution_risk import snapshot_sha256
from compertum.deterministic_broker import DeterministicBroker
from compertum.fake_economic_opening import provision_opening
from compertum.fake_execution_driver import FakeExecutionDriver
from test_fake_execution_journal import native,arguments
from test_execution_risk import observation,intent,bind,calendar,NOW


def records(lease):
 o=observation();o['generation']=lease.generation;inputs=bind(o);record=ExecutionObservation(o);p=intent(o);p['snapshot_sha256']=snapshot_sha256(record)
 return ExecutionIntent(p),record,inputs


def at(seconds):return (instant(NOW)+timedelta(seconds=seconds)).isoformat()


def test_lost_acceptance_polls_on_schedule_without_reposting(native):
 project,lease,_,j=native;b=DeterministicBroker(project.root_path/'state/fake-broker');provision_opening(j.store,b,cash='10000',positions={});driver=FakeExecutionDriver(j,b);i,o,inputs=records(lease)
 try:
  result=driver.dispatch(i,o,now=NOW,calendar=calendar(),inputs=inputs,outcome='TIMEOUT_AFTER_ACCEPT',invisible_lookups=2)
  assert result['status']=='UNKNOWN'
  assert driver.dispatch(i,o,now=NOW,calendar=calendar(),inputs=inputs)['status']=='UNKNOWN'
  assert driver.poll(i,o,now=at(0))['status']=='UNKNOWN'
  assert driver.poll(i,o,now=at(1))['status']=='UNKNOWN'
  assert driver.poll(i,o,now=at(2))['status']=='UNKNOWN'
  assert driver.poll(i,o,now=at(5))['status']=='ACKNOWLEDGED'
  calls=b.snapshot()['calls'];assert sum(v['kind']=='SUBMIT' for v in calls)==1 and sum(v['kind']=='LOOKUP' for v in calls)==3
 finally:b.close()


def test_404_budget_expires_but_never_proves_absence_or_retries(native):
 project,lease,_,j=native;b=DeterministicBroker(project.root_path/'state/fake-broker');provision_opening(j.store,b,cash='10000',positions={});driver=FakeExecutionDriver(j,b);i,o,inputs=records(lease)
 try:
  driver.dispatch(i,o,now=NOW,calendar=calendar(),inputs=inputs,outcome='TIMEOUT_BEFORE_ACCEPT')
  for seconds in (0,2,5,10,20,30):assert driver.poll(i,o,now=at(seconds))['status']=='UNKNOWN'
  result=driver.poll(i,o,now=at(120));assert result['status']=='UNKNOWN' and result['incident']['status']=='UNRESOLVED_LIMIT'
  assert driver.dispatch(i,o,now=at(121),calendar=calendar(),inputs=inputs)['status']=='UNKNOWN'
  s=b.snapshot();assert s['orders']==[] and sum(v['kind']=='SUBMIT' for v in s['calls'])==1 and sum(v['kind']=='LOOKUP' for v in s['calls'])==6
 finally:b.close()


def test_stale_input_cannot_reach_fixture_and_ack_is_not_fill(native):
 project,lease,_,j=native;b=DeterministicBroker(project.root_path/'state/fake-broker');provision_opening(j.store,b,cash='10000',positions={});driver=FakeExecutionDriver(j,b);i,o,inputs=records(lease)
 try:
  assert driver.dispatch(i,o,now=at(31),calendar=calendar(),inputs=inputs)['status']=='REFUSED'
  assert b.snapshot()['calls']==[]
  result=driver.dispatch(i,o,now=NOW,calendar=calendar(),inputs=inputs)
  assert result['status']=='ACKNOWLEDGED' and result['filled_quantity']==0 and b.snapshot()['positions']=={}
 finally:b.close()


def test_missed_poll_offsets_never_burst_or_rewind_clock(native):
 from compertum.runtime.errors import RuntimeRefused
 project,lease,_,j=native;b=DeterministicBroker(project.root_path/'state/fake-broker');provision_opening(j.store,b,cash='10000',positions={});driver=FakeExecutionDriver(j,b);i,o,inputs=records(lease)
 try:
  driver.dispatch(i,o,now=NOW,calendar=calendar(),inputs=inputs,outcome='TIMEOUT_BEFORE_ACCEPT')
  for _ in range(3):driver.poll(i,o,now=at(30))
  assert sum(v['kind']=='LOOKUP' for v in b.snapshot()['calls'])==1
  with pytest.raises(RuntimeRefused,match='INCIDENT_CLOCK_REVERSED'):driver.poll(i,o,now=at(20))
 finally:b.close()


def control_fixture(project,lease,j,*,quantity=45):
 from compertum.execution_plans import build_plan,authorize_fake_plan,start_operation
 b=DeterministicBroker(project.root_path/'state/fake-broker',cash=str(10000-quantity*100),positions={'AAPL':quantity});provision_opening(j.store,b,cash=str(10000-quantity*100),positions={'AAPL':quantity});driver=FakeExecutionDriver(j,b)
 raw=observation();raw['generation']=lease.generation;raw['authority'].update(halted=True,armed=False,strategy_admitted=False);o=driver.observation(ExecutionObservation(raw),now=NOW)
 p=build_plan(o,kind='CLOSE_LONG',now=NOW,calendar=calendar());a=authorize_fake_plan(p,o,now=NOW,calendar=calendar());start=start_operation(p,a,o,now=NOW,calendar=calendar())
 return b,driver,o,p,a,start


def close_request(o,p,a,index,quantity=None):
 from compertum.execution_plans import digest
 child=p.to_payload()['children'][index];raw=o.to_payload();i=intent(raw,kind='CLOSE_LONG',side='sell',quantity=quantity or child['maximum_quantity'],symbol=child['symbol'])
 i.update(intent_id=child['intent_id'],plan_id=p.to_payload()['plan_id'],child_index=index,authorization_sha256=digest(a),snapshot_sha256=snapshot_sha256(o),expires_at=p.to_payload()['deadline'])
 return ExecutionIntent(i)


def test_joined_partial_close_finishes_children_and_reports_owned_residual(native):
 project,lease,_,j=native;b,driver,o,p,a,start=control_fixture(project,lease,j)
 try:
  for index,filled in enumerate((7,19,7)):
   o=driver.observation(o,now=NOW);i=close_request(o,p,a,index);result=driver.dispatch(i,o,now=NOW,calendar=calendar(),plan=p,authorization=a,start=start)
   assert result['status']=='ACKNOWLEDGED' and result['filled_quantity']==0
   b.fill(result['order_id'],filled,'100')
   if filled<i.to_payload()['quantity']:
    from compertum.execution_plans import build_plan,authorize_fake_plan,start_operation,digest
    current=driver.observation(o,now=NOW);cp=build_plan(current,kind='CANCEL',now=NOW,calendar=calendar());ca=authorize_fake_plan(cp,current,now=NOW,calendar=calendar());cs=start_operation(cp,ca,current,now=NOW,calendar=calendar())
    raw=intent(current.to_payload(),kind='CANCEL',side=None,quantity=0)
    raw.update(intent_id=cp.to_payload()['cancel_orders'][0]['intent_id'],order_id=result['order_id'],plan_id=cp.to_payload()['plan_id'],authorization_sha256=digest(ca),snapshot_sha256=snapshot_sha256(current))
    ci=ExecutionIntent(raw);assert driver.dispatch(ci,current,now=NOW,calendar=calendar(),plan=cp,authorization=ca,start=cs)['status']=='PARTIALLY_FILLED'
    b.finish_cancel(result['order_id']);assert driver.poll(ci,current,now=NOW)['status']=='CANCELED'
   result=driver.poll(i,o,now=NOW);assert result['status'] in {'FILLED','CANCELED'} and result['filled_quantity']==filled
  s=b.snapshot();assert s['positions']=={'AAPL':12} and s['cash']=='8800'
  assert sum(v['kind']=='SUBMIT' for v in s['calls'])==3 and len(p.to_payload()['children'])==3
 finally:b.close()


def test_unknown_close_child_prevents_all_remaining_children_even_after_deadline(native):
 project,lease,_,j=native;b,driver,o,p,a,start=control_fixture(project,lease,j)
 try:
  first=close_request(o,p,a,0);result=driver.dispatch(first,o,now=NOW,calendar=calendar(),plan=p,authorization=a,start=start,outcome='TIMEOUT_AFTER_ACCEPT',invisible_lookups=6)
  assert result['status']=='UNKNOWN'
  o=driver.observation(o,now=NOW);second=close_request(o,p,a,1)
  assert driver.dispatch(second,o,now=NOW,calendar=calendar(),plan=p,authorization=a,start=start)['status']=='REFUSED'
  for seconds in (0,2,5,10,20,30):assert driver.poll(first,o,now=at(seconds))['status']=='UNKNOWN'
  assert driver.poll(first,o,now=at(600))['status']=='UNKNOWN'
  s=b.snapshot();assert s['positions']=={'AAPL':45} and len(s['orders'])==1 and s['orders'][0]['status']=='ACKNOWLEDGED' and sum(v['kind']=='SUBMIT' for v in s['calls'])==1
 finally:b.close()


def test_joined_cancel_requires_terminal_observation_and_keeps_fill(native):
 from compertum.execution_plans import build_plan,authorize_fake_plan,start_operation,digest
 project,lease,_,j=native;b=DeterministicBroker(project.root_path/'state/fake-broker');provision_opening(j.store,b,cash='10000',positions={});driver=FakeExecutionDriver(j,b);i,o,inputs=records(lease)
 try:
  accepted=driver.dispatch(i,o,now=NOW,calendar=calendar(),inputs=inputs);b.fill(accepted['order_id'],4,'100');driver.poll(i,o,now=NOW)
  raw=driver.observation(o,now=NOW).to_payload();raw['authority'].update(halted=True,armed=False);o=ExecutionObservation(raw)
  plan=build_plan(o,kind='CANCEL',now=NOW,calendar=calendar());auth=authorize_fake_plan(plan,o,now=NOW,calendar=calendar());start=start_operation(plan,auth,o,now=NOW,calendar=calendar())
  p=intent(raw,kind='CANCEL',side=None,quantity=0);p.update(intent_id=plan.to_payload()['cancel_orders'][0]['intent_id'],order_id=accepted['order_id'],plan_id=plan.to_payload()['plan_id'],authorization_sha256=digest(auth),snapshot_sha256=snapshot_sha256(o));cancel=ExecutionIntent(p)
  pending=driver.dispatch(cancel,o,now=NOW,calendar=calendar(),plan=plan,authorization=auth,start=start)
  assert pending['status']=='PARTIALLY_FILLED' and b.snapshot()['positions']=={'AAPL':4}
  b.fill(accepted['order_id'],3,'100');b.finish_cancel(accepted['order_id'])
  terminal=driver.poll(cancel,o,now=NOW);assert terminal['status']=='CANCELED' and terminal['filled_quantity']==7
  driver.poll(i,o,now=NOW);assert j.read(*arguments(i))['status']=='CANCELED' and b.snapshot()['cash']=='9300'
  driver.dispatch(cancel,o,now=NOW,calendar=calendar(),plan=plan,authorization=auth,start=start)
  assert sum(v['kind']=='CANCEL' for v in b.snapshot()['calls'])==1
 finally:b.close()


def test_lookup_failure_after_ack_durably_blocks_new_attempt(native,monkeypatch):
 import sqlite3
 from compertum.runtime.errors import RuntimeRefused
 project,lease,_,j=native;b=DeterministicBroker(project.root_path/'state/fake-broker');provision_opening(j.store,b,cash='10000',positions={});driver=FakeExecutionDriver(j,b);i,o,inputs=records(lease)
 raw=i.to_payload();raw['quantity']=10;i=ExecutionIntent(raw)
 try:
  driver.dispatch(i,o,now=NOW,calendar=calendar(),inputs=inputs)
  def failure(_):raise sqlite3.OperationalError('fixture read failure')
  monkeypatch.setattr(b,'lookup',failure)
  result=driver.poll(i,o,now=NOW);assert result['status']=='UNKNOWN' and not result['conflicting_observation']
  current=driver.observation(o,now=NOW);p=intent(current.to_payload(),quantity=1);p['snapshot_sha256']=snapshot_sha256(current)
  with pytest.raises(RuntimeRefused,match='UNKNOWN_INTENT'):driver.dispatch(ExecutionIntent(p),current,now=NOW,calendar=calendar(),inputs=inputs)
  assert sum(v['kind']=='SUBMIT' for v in b.snapshot()['calls'])==1
 finally:b.close()


@pytest.mark.parametrize('phase',['lookup','observe'])
def test_binding_failure_after_ack_latches_reconciliation_conflict(native,monkeypatch,phase):
 from compertum.runtime.errors import RuntimeRefused
 project,lease,_,j=native;b=DeterministicBroker(project.root_path/'state/fake-broker');provision_opening(j.store,b,cash='10000',positions={});driver=FakeExecutionDriver(j,b);i,o,inputs=records(lease)
 try:
  driver.dispatch(i,o,now=NOW,calendar=calendar(),inputs=inputs)
  def failure(*args,**kwargs):raise RuntimeRefused('ORDER_BINDING_DENIED')
  monkeypatch.setattr(b if phase=='lookup' else driver,'lookup' if phase=='lookup' else '_observe',failure)
  result=driver.poll(i,o,now=NOW);assert result['status']=='UNKNOWN' and result['conflicting_observation']
  assert sum(v['kind']=='SUBMIT' for v in b.snapshot()['calls'])==1
 finally:b.close()


def test_new_disconnect_gets_own_durable_budget_and_same_evidence_resolves(native,monkeypatch):
 import sqlite3,json
 from compertum.fake_execution_journal import FakeIntentJournal
 project,lease,store,j=native;b=DeterministicBroker(project.root_path/'state/fake-broker');provision_opening(j.store,b,cash='10000',positions={});driver=FakeExecutionDriver(j,b);i,o,inputs=records(lease)
 try:
  driver.dispatch(i,o,now=NOW,calendar=calendar(),inputs=inputs)
  lookup=b.lookup
  def failure(_):raise sqlite3.OperationalError('fixture read failure')
  monkeypatch.setattr(b,'lookup',failure)
  assert driver.poll(i,o,now=at(130))['status']=='UNKNOWN'
  # Reopening the journal must retain this incident instead of using submission time.
  driver.journal=FakeIntentJournal(store)
  monkeypatch.setattr(b,'lookup',lambda _:None)
  assert driver.poll(i,o,now=at(130))['status']=='UNKNOWN'
  assert driver.poll(i,o,now=at(132))['status']=='UNKNOWN'
  driver.poll(i,o,now=at(249))
  result=driver.poll(i,o,now=at(249));assert result['incident']['elapsed_seconds']==119
  result=driver.poll(i,o,now=at(250));assert result['incident']['status']=='UNRESOLVED_LIMIT'
  # Direct positive reconciliation can resolve ordinary uncertainty after expiry.
  monkeypatch.setattr(b,'lookup',lookup)
  result=driver._observe(i,o,now=at(251));assert result['status']=='ACKNOWLEDGED'
  monkeypatch.setattr(b,'lookup',failure)
  assert driver.poll(i,o,now=at(300))['status']=='UNKNOWN'
  monkeypatch.setattr(b,'lookup',lookup)
  assert driver.poll(i,o,now=at(300))['status']=='ACKNOWLEDGED'
  events=[(kind,json.loads(body)) for kind,body in store.conn.execute("SELECT kind,body FROM fake_intent_events WHERE kind LIKE 'INCIDENT_%' ORDER BY seq")]
  assert [v['at'] for k,v in events if k=='INCIDENT_STARTED']==[NOW,at(130),at(300)]
  assert len([k for k,v in events if k=='INCIDENT_RESOLVED'])==3
  assert sum(v['kind']=='SUBMIT' for v in b.snapshot()['calls'])==1
 finally:b.close()


def test_exhausted_broker_lookup_bound_is_durable_unknown(native):
 project,lease,_,j=native;b=DeterministicBroker(project.root_path/'state/fake-broker');provision_opening(j.store,b,cash='10000',positions={});driver=FakeExecutionDriver(j,b);i,o,inputs=records(lease)
 try:
  accepted=driver.dispatch(i,o,now=NOW,calendar=calendar(),inputs=inputs)
  for _ in range(511):b.lookup(accepted['client_order_id'])
  assert len(b.snapshot()['calls'])==512
  result=driver.poll(i,o,now=NOW);assert result['status']=='UNKNOWN'
  assert j.read(*arguments(i))['status']=='UNKNOWN'
  assert driver.dispatch(i,o,now=NOW,calendar=calendar(),inputs=inputs)['status']=='UNKNOWN'
  assert sum(v['kind']=='SUBMIT' for v in b.snapshot()['calls'])==1
 finally:b.close()
