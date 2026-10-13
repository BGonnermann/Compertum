"""Finite fake close envelopes, independently hand-counted against settled fills."""
from copy import deepcopy
from decimal import Decimal
from datetime import timedelta
import pytest
from compertum.domain import ExecutionObservation,ExecutionIntent,ExecutionPlan,ContractError
from compertum.execution_contracts import instant
from compertum.execution_plans import build_plan,authorize_fake_plan,assess_control,digest,start_operation
from compertum.execution_risk import snapshot_sha256,client_order_id
from test_execution_risk import observation,holding,order,NOW,intent,calendar


def setup(quantity=45,kind='CLOSE_LONG'):
 o=observation();o['authority'].update(halted=True,armed=False,strategy_admitted=False);o['account'].update(sleeve_cash=str(10000-100*quantity),broker_cash=str(10000-100*quantity),submissions=6);o['positions']=[holding('AAPL',quantity)]
 return o


def records(o,kind='CLOSE_LONG'):
 record=ExecutionObservation(o);p=build_plan(record,kind=kind,now=NOW,calendar=calendar());a=authorize_fake_plan(p,record,now=NOW,calendar=calendar())
 return p,a,start_operation(p,a,record,now=NOW,calendar=calendar())


def request(o,p,a,index=0,quantity=None):
 plan=p.to_payload();child=plan['children'][index]
 i=intent(o,kind='CLOSE_LONG',side='sell',quantity=quantity or child['maximum_quantity'],symbol=child['symbol'])
 i.update(intent_id=child['intent_id'],plan_id=plan['plan_id'],child_index=index,authorization_sha256=digest(a),snapshot_sha256=snapshot_sha256(ExecutionObservation(o)),expires_at=plan['deadline'])
 return ExecutionIntent(i)


def evaluate(o,p,a,start,index=0,quantity=None,now=NOW):
 return assess_control(request(o,p,a,index,quantity),ExecutionObservation(o),p,a,start=start,now=now,calendar=calendar())


def test_halted_close_has_fixed_children_and_ignores_strategy_loss_gate():
 o=setup();o['account']['prior_peak_nav']='20000';p,a,start=records(o);v=p.to_payload()
 assert [c['maximum_quantity'] for c in v['children']]==[19,19,7]
 assert [c['planned_notional'] for c in v['children']]==['1919','1919','707']
 assert [c['maximum_notional'] for c in v['children']]==['2000']*3
 assert evaluate(o,p,a,start)['allowed']
 assert v['deadline']=='2023-10-17T13:45:10+00:00'
 assert v['start_expires_at']=='2023-10-17T13:36:10+00:00'


def test_terminal_partial_children_leave_exact_residual_without_extra_child():
 o=setup();p,a,start=records(o)
 for index,filled in enumerate((7,19,7)):
  i=request(o,p,a,index);assert evaluate(o,p,a,start,index)['allowed']
  event=order(quantity=i.to_payload()['quantity'],filled=filled,side='sell',status='FILLED' if filled==i.to_payload()['quantity'] else 'CANCELED');event['client_order_id']=client_order_id(i);o['orders'].append(event)
  o['positions'][0]=holding('AAPL',o['positions'][0]['owned_quantity']-filled)
  o['account']['sleeve_cash']=str(Decimal(o['account']['sleeve_cash'])+100*filled);o['account']['broker_cash']=o['account']['sleeve_cash']
 assert o['positions']==[holding('AAPL',12)] and o['account']['sleeve_cash']=='8800'
 assert len(p.to_payload()['children'])==3
 assert 'CHILD_ALREADY_OBSERVED' in evaluate(o,p,a,start,2)['reasons']


def test_price_change_downsizes_but_never_enlarges_child():
 o=setup();p,a,start=records(o);o['quotes'][0]['ask']='110'
 assert evaluate(o,p,a,start,quantity=18)['allowed']
 assert 'CHILD_ENVELOPE_EXCEEDED' in evaluate(o,p,a,start,quantity=19)['reasons']
 o['quotes'][0]['ask']='2000'
 result=evaluate(o,p,a,start,quantity=1)
 assert not result['allowed'] and result['maximum_quantity']==0


def test_twelve_child_bound_and_one_share_over_cap():
 o=setup(229);o['account'].update(sleeve_cash='10000',broker_cash='10000');p,a,start=records(o);v=p.to_payload()
 assert len(v['children'])==12 and v['positions'][0]['planned_quantity']==228 and v['positions'][0]['residual_quantity']==1
 assert o['positions'][0]['quantity']=='229'
 o=setup(1);o['quotes'][0].update(bid='2000',ask='2000');p,a,start=records(o)
 assert p.to_payload()['children']==[] and p.to_payload()['positions'][0]['residual_quantity']==1


@pytest.mark.parametrize('mutation,reason',[
 (lambda o:o['health'].update(execution_at='2023-10-17T13:34:00+00:00'),'HEARTBEAT_STALE'),
 (lambda o:o['health'].update(durable=False),'DURABILITY_UNVERIFIED'),
 (lambda o:o['health'].update(supervision_at='2023-10-17T13:00:00+00:00'),'SUPERVISION_EXPIRED'),
 (lambda o:o['authority'].update(unknown_intents=True),'UNKNOWN_INTENT'),
 (lambda o:o['authority'].update(halted=False),'HALT_REQUIRED'),
 (lambda o:o['positions'].__setitem__(0,holding('AAPL',44)),'PLAN_QUANTITY_CHANGED'),
 (lambda o:o.update(generation=2),'PLAN_BINDING_CHANGED'),
 (lambda o:o['quotes'][0].update(liquidity_verified=False),'LIQUIDITY_UNVERIFIED')])
def test_close_cannot_bypass_mandatory_control_gate(mutation,reason):
 o=setup();p,a,start=records(o);mutation(o);result=evaluate(o,p,a,start)
 assert not result['allowed'] and reason in result['reasons']


def test_previous_child_must_be_terminal_before_next():
 o=setup();p,a,start=records(o)
 assert 'PRIOR_CHILD_UNCONFIRMED' in evaluate(o,p,a,start,1)['reasons']
 first=request(o,p,a);pending=order(quantity=19,filled=0,side='sell',status='ACKNOWLEDGED');pending['client_order_id']=client_order_id(first);o['orders']=[pending]
 assert 'PRIOR_CHILD_UNCONFIRMED' in evaluate(o,p,a,start,1)['reasons']
 pending['status']='UNKNOWN'
 assert 'UNKNOWN_INTENT' in evaluate(o,p,a,start,1)['reasons']


def test_cancellation_ignores_quotes_and_regular_window_but_is_not_a_fill():
 o=setup();o['orders']=[order(filled=0,status='ACKNOWLEDGED')];o['quotes']=[];p,a,start=records(o,'CANCEL')
 i=intent(o,kind='CANCEL',side=None,quantity=0);i.update(intent_id=p.to_payload()['cancel_orders'][0]['intent_id'],plan_id=p.to_payload()['plan_id'],order_id=o['orders'][0]['order_id'],authorization_sha256=digest(a),snapshot_sha256=snapshot_sha256(ExecutionObservation(o)))
 r=assess_control(ExecutionIntent(i),ExecutionObservation(o),p,a,start=start,now=NOW,calendar=calendar())
 assert r['allowed'] and o['positions'][0]['owned_quantity']==45
 i['order_id']='11111111-1111-1111-1111-111111111111'
 assert 'CANCEL_TARGET_CHANGED' in assess_control(ExecutionIntent(i),ExecutionObservation(o),p,a,start=start,now=NOW,calendar=calendar())['reasons']


def test_fill_during_prerequisite_cancel_requires_new_plan():
 o=setup();o['orders']=[order(filled=0,status='ACKNOWLEDGED')];p,a,start=records(o)
 assert 'CANCELLATION_UNCONFIRMED' in evaluate(o,p,a,start)['reasons']
 o['orders'][0].update(status='CANCELED',filled_quantity=1,filled_notional='100');o['positions']=[holding('AAPL',46)]
 assert 'PLAN_QUANTITY_CHANGED' in evaluate(o,p,a,start)['reasons']


def test_authorization_cannot_follow_changed_economic_snapshot_or_expiry():
 o=setup();p,a,start=records(o);o['account']['broker_cash']='5501'
 with pytest.raises(ContractError,match='PLAN_SNAPSHOT_CHANGED'):authorize_fake_plan(p,ExecutionObservation(o),now=NOW,calendar=calendar())
 o=setup();p,a,start=records(o)
 refresh(o,p.to_payload()['start_expires_at'])
 with pytest.raises(ContractError,match='PLAN_EXPIRED'):authorize_fake_plan(p,ExecutionObservation(o),now=p.to_payload()['start_expires_at'],calendar=calendar())
 assert 'PLAN_EXPIRED' in evaluate(o,p,a,start,now=p.to_payload()['deadline'])['reasons']


def test_enlarging_immutable_plan_breaks_authorization():
 o=setup();p,a,start=records(o);mutated=p.to_payload();mutated['children'][0]['intent_id']='11111111-1111-1111-1111-111111111111';changed=ExecutionPlan(mutated)
 assert 'PLAN_AUTHORIZATION_CHANGED' in evaluate(o,changed,a,start)['reasons']


def test_plan_contract_rejects_hidden_extra_quantity():
 o=setup();p,a,start=records(o);v=p.to_payload();v['positions'][0]['quantity']+=1
 with pytest.raises(ContractError):ExecutionPlan(v)



def refresh(o,time):
 o['observed_at']=time;o['account']['reconciled_at']=time
 for k in ('execution_at','watchdog_at','supervision_at'):o['health'][k]=time
 o['clock'].update(observed_at=time,broker_at=time)
 for q in o['quotes']:q['observed_at']=time


def test_changed_balances_between_authorization_and_start_refuse():
 o=setup();p,a,start=records(o);o['account']['broker_cash']='5501'
 with pytest.raises(ContractError,match='PLAN_SNAPSHOT_CHANGED'):start_operation(p,a,ExecutionObservation(o),now=NOW,calendar=calendar())


def test_coherent_enlargement_cannot_get_new_authorization():
 o=setup();p,a,start=records(o);v=p.to_payload();v['positions'][0].update(quantity=46,planned_quantity=46);v['children'][2].update(maximum_quantity=8,planned_notional='808')
 with pytest.raises(ContractError,match='PLAN_ENVELOPE_CHANGED'):authorize_fake_plan(ExecutionPlan(v),ExecutionObservation(o),now=NOW,calendar=calendar())


def test_exact_derived_decimal_precision_is_preserved():
 o=setup();o['quotes'][0]['ask']='100.00000001';o['quotes'][0]['mean_dollar_volume']='100000.00000001';p,a,start=records(o)
 assert p.to_payload()['children'][0]['maximum_quantity']==9
 assert p.to_payload()['children'][0]['planned_notional']=='909.0000000909'
 assert p.to_payload()['children'][0]['maximum_notional']=='1000.0000000001'
 assert evaluate(o,p,a,start,quantity=9)['allowed']


def test_realized_child_notional_breach_halts_following_child():
 o=setup();p,a,start=records(o);first=request(o,p,a);done=order(quantity=19,filled=19,side='sell',status='FILLED');done.update(client_order_id=client_order_id(first),filled_notional='2090');o['orders']=[done];o['positions']=[holding('AAPL',26)];o['account'].update(sleeve_cash='7590',broker_cash='7590')
 assert 'REALIZED_NOTIONAL_BREACH' in evaluate(o,p,a,start,1)['reasons']


def test_cancellation_binds_original_symbol():
 o=setup();o['orders']=[order(filled=0,status='ACKNOWLEDGED')];p,a,start=records(o,'CANCEL');o['orders'][0]['symbol']='MSFT'
 i=intent(o,kind='CANCEL',side=None,quantity=0,symbol='MSFT');i.update(intent_id=p.to_payload()['cancel_orders'][0]['intent_id'],plan_id=p.to_payload()['plan_id'],order_id=o['orders'][0]['order_id'],authorization_sha256=digest(a),snapshot_sha256=snapshot_sha256(ExecutionObservation(o)))
 result=assess_control(ExecutionIntent(i),ExecutionObservation(o),p,a,start=start,now=NOW,calendar=calendar())
 assert not result['allowed'] and 'CANCEL_TARGET_CHANGED' in result['reasons']


def test_cancellation_after_hours_needs_explicit_broker_permission():
 o=setup();at='2023-10-17T20:30:00+00:00';refresh(o,at);o['quotes']=[];o['orders']=[order(filled=0,status='ACKNOWLEDGED')];record=ExecutionObservation(o)
 p=build_plan(record,kind='CANCEL',now=at,calendar=calendar());a=authorize_fake_plan(p,record,now=at,calendar=calendar());start=start_operation(p,a,record,now=at,calendar=calendar())
 i=intent(o,kind='CANCEL',side=None,quantity=0);i.update(intent_id=p.to_payload()['cancel_orders'][0]['intent_id'],created_at=at,expires_at=p.to_payload()['deadline'],plan_id=p.to_payload()['plan_id'],order_id=o['orders'][0]['order_id'],authorization_sha256=digest(a),snapshot_sha256=snapshot_sha256(record))
 assert assess_control(ExecutionIntent(i),record,p,a,start=start,now=at,calendar=calendar())['allowed']
 o['health']['broker_cancel_allowed']=False;i['snapshot_sha256']=snapshot_sha256(ExecutionObservation(o))
 assert 'CANCELLATION_NOT_PERMITTED' in assess_control(ExecutionIntent(i),ExecutionObservation(o),p,a,start=start,now=at,calendar=calendar())['reasons']
 with pytest.raises(ContractError,match='REGULAR_SESSION_REQUIRED'):build_plan(record,kind='CLOSE_LONG',now=at,calendar=calendar())


def test_close_plan_authorizes_only_its_reviewed_cancel_prerequisite():
 o=setup();o['orders']=[order(filled=0,status='ACKNOWLEDGED')];p,a,start=records(o)
 i=intent(o,kind='CANCEL',side=None,quantity=0);i.update(intent_id=p.to_payload()['cancel_orders'][0]['intent_id'],plan_id=p.to_payload()['plan_id'],order_id=o['orders'][0]['order_id'],authorization_sha256=digest(a),snapshot_sha256=snapshot_sha256(ExecutionObservation(o)))
 assert assess_control(ExecutionIntent(i),ExecutionObservation(o),p,a,start=start,now=NOW,calendar=calendar())['allowed']
 i['intent_id']='11111111-1111-1111-1111-111111111111'
 assert 'CANCEL_TARGET_CHANGED' in assess_control(ExecutionIntent(i),ExecutionObservation(o),p,a,start=start,now=NOW,calendar=calendar())['reasons']
 o['orders'][0]['status']='CANCELED'
 assert evaluate(o,p,a,start)['allowed']


@pytest.mark.parametrize('day,expected_close,expected_entry',[
 ('2023-11-24','2023-11-24T18:00:00+00:00','2023-11-24T14:35:00+00:00'),
 ('2023-03-13','2023-03-13T20:00:00+00:00','2023-03-13T13:35:00+00:00'),
 ('2023-11-06','2023-11-06T21:00:00+00:00','2023-11-06T14:35:00+00:00')])
def test_pinned_calendar_honors_early_close_and_daylight_saving(day,expected_close,expected_entry):
 from compertum.data.calendar import session_times
 from compertum.domain import ExecutionCalendar
 from compertum.execution_contracts import record_sha256,calendar_reasons
 c=session_times(day);cal=ExecutionCalendar(dict(schema_version='1',record_type='ExecutionCalendar',scope='DETERMINISTIC_FAKE',session_date=day,prior_session=c.previous_date,session_open_at=c.open.isoformat(),session_close_at=c.close.isoformat(),source_sha256='f'*64))
 assert c.close.isoformat()==expected_close and c.entry.isoformat()==expected_entry
 o=setup();at=(c.close-timedelta(seconds=20)).isoformat();refresh(o,at)
 o['clock'].update(calendar_sha256=record_sha256(cal),prior_session=c.previous_date,session_open_at=c.open.isoformat(),session_close_at=c.close.isoformat(),strategy_open_at=c.entry.isoformat(),strategy_close_at=(c.entry+timedelta(minutes=1)).isoformat());o['quotes'][0]['liquidity_as_of']=c.previous_date
 record=ExecutionObservation(o);assert calendar_reasons(record,cal)==[]
 plan=build_plan(record,kind='CLOSE_LONG',now=at,calendar=cal)
 assert plan.to_payload()['deadline']==expected_close==plan.to_payload()['start_expires_at']
 changed=o['clock'].copy();o['clock']['session_close_at']=(c.close+timedelta(minutes=1)).isoformat()
 assert calendar_reasons(ExecutionObservation(o),cal)==['CALENDAR_MISMATCH']
