"""Actual Windows execution leases and SQLite; invented effects only."""
import os
from copy import deepcopy
from uuid import uuid4
import pytest
from compertum.domain import ExecutionObservation,ExecutionIntent
from compertum.execution_risk import assess,snapshot_sha256
from compertum.runtime.identity import resolve_project
from compertum.runtime.owners import acquire_owner,release_owner
from compertum.runtime.errors import RuntimeRefused
from compertum.persistence import open_store
from test_execution_risk import observation,intent,bind,calendar,NOW,order

pytestmark=pytest.mark.skipif(os.name!='nt',reason='NATIVE_WINDOWS_UNAVAILABLE')


@pytest.fixture
def native(tmp_path):
 from compertum.fake_execution_journal import FakeIntentJournal
 project=resolve_project(tmp_path);lease=acquire_owner(project,'execution');store=open_store(lease,'execution');journal=FakeIntentJournal(store)
 try:yield project,lease,store,journal
 finally:
  from compertum.runtime.owners import _LEASES
  if lease in _LEASES:release_owner(lease)


def checked_records(lease):
 o=observation();o['generation']=lease.generation;inputs=bind(o);record=ExecutionObservation(o);i=intent(o);i['snapshot_sha256']=snapshot_sha256(record);i=ExecutionIntent(i)
 return i,assess(i,record,now=NOW,calendar=calendar(),inputs=inputs)


def test_intent_is_immutable_and_fake_attempt_granted_once(native):
 _,lease,store,journal=native;i,d=checked_records(lease);first=journal.record_checked(i,d)
 assert first['status']=='CHECKED' and journal.record_checked(i,d)==first
 args=(i.to_payload()['account_alias'],i.to_payload()['intent_id'])
 assert journal.begin_attempt(*args,now=NOW)['simulate_once']
 assert not journal.begin_attempt(*args,now=NOW)['simulate_once']
 p=i.to_payload();p['quantity']-=1
 with pytest.raises(RuntimeRefused,match='INTENT_CONFLICT'):journal.record_checked(ExecutionIntent(p),d)
 assert store.inspect()['synchronous']==2


def arguments(i):
 p=i.to_payload();return p['account_alias'],p['intent_id']


def observed(i,lease,*,filled=0,status='ACKNOWLEDGED',order_id=None):
 o=observation();o['generation']=lease.generation;p=i.to_payload();v=order(symbol=p['symbol'],quantity=p['quantity'],filled=filled,side=p['side'],status=status);v['client_order_id']=__import__('compertum.execution_risk',fromlist=['client_order_id']).client_order_id(i)
 if order_id:v['order_id']=order_id
 o['orders']=[v];return ExecutionObservation(o)


def test_lookup_404_never_reopens_a_lost_reply_for_retry(native):
 _,lease,_,j=native;i,d=checked_records(lease);j.record_checked(i,d);j.begin_attempt(*arguments(i),now=NOW)
 for reason in ('TIMEOUT','LOOKUP_404','LOOKUP_404'):
  assert j.uncertain(*arguments(i),reason=reason,now=NOW)['status']=='UNKNOWN'
  assert not j.begin_attempt(*arguments(i),now=NOW)['simulate_once']
 other,decision=checked_records(lease);j.record_checked(other,decision)
 with pytest.raises(RuntimeRefused,match='UNKNOWN_INTENT'):j.begin_attempt(*arguments(other),now=NOW)
 assert j.status()['order_admission']=='DISARMED'


def test_duplicate_and_out_of_order_fills_never_double_count_or_regress(native):
 _,lease,_,j=native;i,d=checked_records(lease);j.record_checked(i,d);j.begin_attempt(*arguments(i),now=NOW)
 ack=observed(i,lease);broker_id=ack.to_payload()['orders'][0]['order_id'];j.observe(*arguments(i),ack,event_id=str(uuid4()))
 partial=observed(i,lease,filled=7,status='PARTIALLY_FILLED',order_id=broker_id);event=str(uuid4())
 first=j.observe(*arguments(i),partial,event_id=event)
 assert first['filled_quantity']==7 and first['filled_notional']=='700'
 assert j.observe(*arguments(i),partial,event_id=event)==first
 stale=j.observe(*arguments(i),ack,event_id=str(uuid4()))
 assert stale['status']=='PARTIALLY_FILLED' and stale['filled_quantity']==7
 done=observed(i,lease,filled=7,status='CANCELED',order_id=broker_id)
 assert j.observe(*arguments(i),done,event_id=str(uuid4()))['status']=='CANCELED'
 assert j.observe(*arguments(i),partial,event_id=str(uuid4()))['status']=='CANCELED'
 with pytest.raises(RuntimeRefused,match='BROKER_EVENT_CONFLICT'):j.observe(*arguments(i),done,event_id=event)


def test_fill_after_terminal_cancellation_remains_uncertain(native):
 _,lease,_,j=native;i,d=checked_records(lease);j.record_checked(i,d);j.begin_attempt(*arguments(i),now=NOW)
 canceled=observed(i,lease,filled=7,status='CANCELED');order_id=canceled.to_payload()['orders'][0]['order_id'];j.observe(*arguments(i),canceled,event_id=str(uuid4()))
 later=observed(i,lease,filled=19,status='FILLED',order_id=order_id)
 result=j.observe(*arguments(i),later,event_id=str(uuid4()))
 assert result['status']=='UNKNOWN' and result['filled_quantity']==7 and result['filled_notional']=='700' and result['conflicting_observation']
 assert not j.begin_attempt(*arguments(i),now=NOW)['simulate_once']



def test_expired_checked_intent_has_no_attempt(native):
 _,lease,_,j=native;i,d=checked_records(lease);j.record_checked(i,d)
 result=j.begin_attempt(*arguments(i),now=i.to_payload()['expires_at'])
 assert not result['simulate_once'] and result['record']['status']=='SKIPPED_WINDOW_EXPIRED'


def test_wrong_or_released_owner_cannot_use_execution_journal(native):
 from compertum.fake_execution_journal import FakeIntentJournal
 project,lease,_,j=native;wrong=acquire_owner(project,'coordinator')
 try:
  with pytest.raises(RuntimeRefused,match='WRONG_OWNER_ROLE'):FakeIntentJournal(open_store(wrong,'coordinator'))
 finally:release_owner(wrong)
 release_owner(lease)
 with pytest.raises(RuntimeRefused):j.status()


def test_unapproved_or_mismatched_decision_never_creates_intent(native):
 from compertum.domain import ExecutionDecision
 _,lease,_,j=native;i,d=checked_records(lease);p=d.to_payload();p.update(allowed=False,reasons=['OFFLINE'])
 with pytest.raises(RuntimeRefused,match='DECISION_BINDING_DENIED'):j.record_checked(i,ExecutionDecision(p))
 p=d.to_payload();p['intent_sha256']='f'*64
 with pytest.raises(RuntimeRefused,match='DECISION_BINDING_DENIED'):j.record_checked(i,ExecutionDecision(p))
 assert j.status()['intents']==0


@pytest.mark.parametrize('change',[
 lambda o:o['orders'][0].update(quantity=20),
 lambda o:o['orders'][0].update(symbol='MSFT'),
 lambda o:o['orders'][0].update(side='sell'),
 lambda o:o['orders'][0].update(owned=False),
 lambda o:o.update(account_alias='fake-other')])
def test_misbound_broker_observation_never_becomes_acknowledgment(native,change):
 _,lease,_,j=native;i,d=checked_records(lease);j.record_checked(i,d);j.begin_attempt(*arguments(i),now=NOW);o=observed(i,lease).to_payload();change(o)
 with pytest.raises(RuntimeRefused):j.observe(*arguments(i),ExecutionObservation(o),event_id=str(uuid4()))
 assert j.read(*arguments(i))['status']=='SUBMITTING'


@pytest.mark.parametrize('point,expected,acceptances',[
 ('before_attempt','SKIPPED_RESTART',0),('after_attempt','UNKNOWN',0),
 ('after_acceptance','UNKNOWN',1),('after_ack','ACKNOWLEDGED',1),('after_late_incident','UNKNOWN',1),('before_attempt_guard_head','SKIPPED_RESTART',0),('after_attempt_guard_head','UNKNOWN',0)])
def test_real_process_exit_never_reissues_simulated_attempt(tmp_path,point,expected,acceptances):
 import subprocess,sys,json,sqlite3
 from pathlib import Path
 from compertum.fake_execution_journal import FakeIntentJournal
 child=subprocess.run([sys.executable,'-B',str(Path(__file__).parent/'helpers/fake_journal_crash.py'),str(tmp_path),point],capture_output=True,text=True,timeout=20)
 assert child.returncode==23,child.stderr
 data=json.loads((tmp_path/'fixture.json').read_text());project=resolve_project(tmp_path);lease=acquire_owner(project,'execution')
 try:
  assert lease.generation==2
  journal=FakeIntentJournal(open_store(lease,'execution'));i=ExecutionIntent(data['intent']);waiting=ExecutionIntent(data['waiting'])
  assert journal.read(*arguments(i))['status']==expected
  assert journal.read(*arguments(waiting))['status']=='SKIPPED_RESTART'
  if point=='before_attempt_guard_head':
   other,decision=checked_records(lease);journal.record_checked(other,decision)
   with pytest.raises(RuntimeRefused,match='EXECUTION_COMPROMISED'):journal.begin_attempt(*arguments(other),now=NOW)

  if point=='after_late_incident':
   from datetime import timedelta
   from compertum.execution_contracts import instant
   def at(seconds):return (instant(NOW)+timedelta(seconds=seconds)).isoformat()
   result=journal.reserve_poll(*arguments(i),now=at(133));assert not result['poll'] and result['elapsed_seconds']==3
   assert journal.reserve_poll(*arguments(i),now=at(135))['poll']
   assert journal.reserve_poll(*arguments(i),now=at(250))['status']=='UNRESOLVED_LIMIT'

  for _ in range(3):assert not journal.begin_attempt(*arguments(i),now=NOW)['simulate_once']
  with sqlite3.connect(tmp_path/'independent-fake-broker.sqlite') as broker:assert broker.execute('SELECT COUNT(*) FROM accepted').fetchone()[0]==acceptances
 finally:release_owner(lease)


def test_contradictory_notional_is_sticky_and_never_overwrites_accepted_fills(native):
 _,lease,_,j=native;i,d=checked_records(lease);j.record_checked(i,d);j.begin_attempt(*arguments(i),now=NOW)
 first=observed(i,lease,filled=4,status='PARTIALLY_FILLED');order_id=first.to_payload()['orders'][0]['order_id'];j.observe(*arguments(i),first,event_id=str(uuid4()))
 raw=observed(i,lease,filled=5,status='PARTIALLY_FILLED',order_id=order_id).to_payload();raw['orders'][0]['filled_notional']='300'
 for _ in range(2):
  result=j.observe(*arguments(i),ExecutionObservation(raw),event_id=str(uuid4()))
  assert result['status']=='UNKNOWN' and result['filled_quantity']==4 and result['filled_notional']=='400' and result['conflicting_observation']
 raw['orders'][0]['filled_notional']='500'
 assert j.observe(*arguments(i),ExecutionObservation(raw),event_id=str(uuid4()))['status']=='UNKNOWN'


def test_same_terminal_event_updates_order_and_authorized_cancellation(native):
 from compertum.execution_plans import build_plan,authorize_fake_plan,start_operation,digest,assess_control
 _,lease,_,j=native;i,d=checked_records(lease);j.record_checked(i,d);j.begin_attempt(*arguments(i),now=NOW)
 ack=observed(i,lease);j.observe(*arguments(i),ack,event_id=str(uuid4()));o=ack.to_payload();o['authority'].update(halted=True,armed=False)
 record=ExecutionObservation(o);plan=build_plan(record,kind='CANCEL',now=NOW,calendar=calendar());authorization=authorize_fake_plan(plan,record,now=NOW,calendar=calendar());start=start_operation(plan,authorization,record,now=NOW,calendar=calendar())
 p=intent(o,kind='CANCEL',side=None,quantity=0);p.update(intent_id=plan.to_payload()['cancel_orders'][0]['intent_id'],order_id=o['orders'][0]['order_id'],plan_id=plan.to_payload()['plan_id'],authorization_sha256=digest(authorization),snapshot_sha256=snapshot_sha256(record));cancel=ExecutionIntent(p)
 decision=assess_control(cancel,record,plan,authorization,start=start,now=NOW,calendar=calendar());j.record_checked(cancel,decision);assert j.begin_attempt(*arguments(cancel),now=NOW)['simulate_once']
 o['orders'][0]['status']='CANCELED';terminal=ExecutionObservation(o);event=str(uuid4())
 assert j.observe(*arguments(i),terminal,event_id=event)['status']=='CANCELED'
 assert j.observe(*arguments(cancel),terminal,event_id=event)['status']=='CANCELED'
 assert j.observe(*arguments(cancel),terminal,event_id=event)['status']=='CANCELED'


@pytest.mark.parametrize('status',['PARTIALLY_FILLED','CANCELED'])
def test_explicit_observation_conflict_cannot_be_cleared_by_repeated_data(native,status):
 _,lease,_,j=native;i,d=checked_records(lease);j.record_checked(i,d);j.begin_attempt(*arguments(i),now=NOW)
 observation=observed(i,lease,filled=4,status=status);j.observe(*arguments(i),observation,event_id=str(uuid4()))
 result=j.uncertain(*arguments(i),reason='CONFLICTING_OBSERVATION',now=NOW)
 assert result['status']=='UNKNOWN' and result['conflicting_observation']
 result=j.observe(*arguments(i),observation,event_id=str(uuid4()))
 assert result['status']=='UNKNOWN' and result['filled_quantity']==4 and result['filled_notional']=='400'
