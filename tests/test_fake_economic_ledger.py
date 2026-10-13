"""Independent arithmetic and corruption cases for declared-opening economics."""
from copy import deepcopy
from decimal import localcontext,ROUND_DOWN
from pathlib import Path
import sys
from uuid import uuid4,uuid5,NAMESPACE_URL
sys.path.insert(0,str(Path.cwd()/'tests'))
import pytest
from test_execution_risk import observation,intent,bind
from compertum.domain import ExecutionIntent,ExecutionObservation
from compertum.execution_risk import client_order_id,snapshot_sha256
from compertum.runtime.errors import RuntimeRefused
from compertum.fake_economic_ledger import reconcile

def case(side="sell"):
 o=observation();bind(o);p=intent(o,quantity=19,side=side);p['snapshot_sha256']=snapshot_sha256(ExecutionObservation(o));i=ExecutionIntent(p)
 client=client_order_id(i)
 order=dict(order_id=str(uuid5(NAMESPACE_URL,'compertum-fixture:fake-account:'+client)),client_order_id=client,symbol='AAPL',side=side,quantity=19,filled_quantity=0,filled_notional='0',status='ACKNOWLEDGED',owned=True)
 opening={'account_alias':'fake-account','cash':'5500','positions':{'AAPL':45}}
 evidence={'status':'VERIFIED','records':[{'intent':i.to_payload(),'client_order_id':client}]}
 snapshot={'scope':'DETERMINISTIC_FAKE','account_alias':'fake-account','cash':'5500','positions':{'AAPL':45},'orders':[order], 'event_sequence':1,'events':[{'sequence':1,'event_id':str(uuid4()),'order':deepcopy(order)}],'calls':[]}
 if side=='buy':
  opening.update(cash='10000',positions={});snapshot.update(cash='10000',positions={})
 return opening,evidence,snapshot

def event(s,*,quantity,notional,status):
 s['orders'][0].update(filled_quantity=quantity,filled_notional=notional,status=status)
 s['event_sequence']+=1;s['events'].append({'sequence':s['event_sequence'],'event_id':str(uuid4()),'order':deepcopy(s['orders'][0])})

def test_opening_is_independent_of_broker_current_balance():
 o,e,s=case();r=reconcile(o,e,s)
 assert r=={'expected_cash':'5500','owned_positions':{'AAPL':45},'cash_difference':'0','orders':1,'events':1}

@pytest.mark.parametrize('delta',['0.01','-0.01'])
def test_exact_one_cent_boundary_preserves_independent_expected_cash(delta):
 from decimal import Decimal
 o,e,s=case();s['cash']=str(Decimal('5500')+Decimal(delta))
 r=reconcile(o,e,s);assert r['expected_cash']=='5500' and r['cash_difference']==delta

@pytest.mark.parametrize('change',['share','cash','foreign_order','owned_flag','missing_event','missing_middle_event','sequence_gap','reordered','unknown_intent','changed_intent','changed_order_id','decreasing_quantity','decreasing_notional','notional_without_fill','terminal_rewrite','duplicate_event_id','missing_final_order','wrong_account','unverified_guard'])
def test_unexplained_or_incomplete_evidence_refuses(change):
 o,e,s=case();event(s,quantity=4,notional='399.6',status='PARTIALLY_FILLED');event(s,quantity=19,notional='1900.2',status='FILLED');s.update(cash='7400.2',positions={'AAPL':26})
 if change=='share':s['positions']['AAPL']+=1
 elif change=='cash':s['cash']='7400.22'
 elif change=='foreign_order':s['orders'].append(dict(s['orders'][0],order_id=str(uuid4()),client_order_id='foreign'))
 elif change=='owned_flag':s['orders'][0]['owned']=False
 elif change=='missing_event':s['events'].pop()
 elif change=='missing_middle_event':s['events'].pop(1)
 elif change=='sequence_gap':s['events'][1]['sequence']=4
 elif change=='reordered':s['events'][1],s['events'][2]=s['events'][2],s['events'][1]
 elif change=='unknown_intent':e['records']=[]
 elif change=='changed_intent':e['records'][0]['intent']['quantity']=20
 elif change=='changed_order_id':s['orders'][0]['order_id']=str(uuid4())
 elif change=='decreasing_quantity':s['events'][1]['order']['filled_quantity']=20
 elif change=='decreasing_notional':s['events'][1]['order']['filled_notional']='2000'
 elif change=='notional_without_fill':s['events'][0]['order']['filled_notional']='1'
 elif change=='terminal_rewrite':s['events'][1]['order']['status']='CANCELED'
 elif change=='duplicate_event_id':s['events'][1]['event_id']=s['events'][0]['event_id']
 elif change=='missing_final_order':s['orders']=[]
 elif change=='wrong_account':s['account_alias']='fake-other'
 elif change=='unverified_guard':e['status']='EXECUTION_COMPROMISED'
 with pytest.raises(RuntimeRefused,match='FAKE_ECONOMIC_RECONCILIATION'):reconcile(o,e,s)

def test_partial_fills_use_cumulative_differences_once_then_cancel():
 o,e,s=case();event(s,quantity=4,notional='399.6',status='PARTIALLY_FILLED');event(s,quantity=7,notional='699.9',status='PARTIALLY_FILLED');event(s,quantity=7,notional='699.9',status='CANCELED')
 p=intent(observation(),quantity=0,kind='CANCEL',side=None);p.update(order_id=s['orders'][0]['order_id'],plan_id=str(uuid4()),snapshot_sha256='a'*64)
 i=ExecutionIntent(p);e['records'].append({'intent':i.to_payload(),'client_order_id':client_order_id(i)})
 s.update(cash='6199.9',positions={'AAPL':38});r=reconcile(o,e,s)
 assert r=={'expected_cash':'6199.9','owned_positions':{'AAPL':38},'cash_difference':'0','orders':1,'events':4}

def test_full_restore_economics_matches_hand_calculated_sale():
 o,e,s=case();event(s,quantity=19,notional='1900',status='FILLED');s.update(cash='7400',positions={'AAPL':26})
 r=reconcile(o,e,s);assert r['expected_cash']=='7400' and r['owned_positions']=={'AAPL':26}

def test_process_decimal_context_cannot_change_reconciliation():
 o,e,s=case();event(s,quantity=19,notional='1900.12345678',status='FILLED');s.update(cash='7400.12345678',positions={'AAPL':26})
 with localcontext() as context:
  context.prec=4;context.rounding=ROUND_DOWN
  assert reconcile(o,e,s)['expected_cash']=='7400.12345678'

def test_no_orders_or_events_is_valid_only_against_declared_opening():
 o,e,s=case();e['records']=[];s.update(orders=[],events=[],event_sequence=0)
 assert reconcile(o,e,s)['owned_positions']=={'AAPL':45}

def test_buy_fill_debits_cash_and_adds_owned_quantity():
 o,e,s=case("buy");event(s,quantity=19,notional="1900",status="FILLED");s.update(cash="8100",positions={"AAPL":19})
 r=reconcile(o,e,s);assert r["expected_cash"]=="8100" and r["owned_positions"]=={"AAPL":19}

def test_cancel_without_preserved_authorization_is_foreign_activity():
 o,e,s=case();event(s,quantity=0,notional="0",status="CANCELED")
 with pytest.raises(RuntimeRefused,match="FAKE_ECONOMIC_RECONCILIATION"):reconcile(o,e,s)

@pytest.mark.parametrize('cash', ['999999999999999999999.13345679','999999999999999999999.11345677'])
def test_large_opening_cent_adjacent_discrepancy_is_not_rounded_away(cash):
 o,e,s=case();o['cash']='999999999999999999999.12345678';s['cash']=cash
 with pytest.raises(RuntimeRefused,match='FAKE_ECONOMIC_RECONCILIATION'):reconcile(o,e,s)

@pytest.mark.parametrize('cash,difference', [('999999999999999999999.13345678','0.01'),('999999999999999999999.11345678','-0.01')])
def test_large_opening_exact_cent_preserves_all_digits(cash,difference):
 o,e,s=case();o['cash']='999999999999999999999.12345678';s['cash']=cash
 r=reconcile(o,e,s);assert r['expected_cash']==o['cash'] and r['cash_difference']==difference

def test_cancel_symbol_must_match_the_order():
 o,e,s=case();event(s,quantity=4,notional='399.6',status='PARTIALLY_FILLED');event(s,quantity=4,notional='399.6',status='CANCELED')
 p=intent(observation(),quantity=0,kind='CANCEL',side=None);p.update(order_id=s['orders'][0]['order_id'],symbol='MSFT',plan_id=str(uuid4()),snapshot_sha256='a'*64)
 i=ExecutionIntent(p);e['records'].append({'intent':i.to_payload(),'client_order_id':client_order_id(i)})
 s.update(cash='5899.6',positions={'AAPL':41})
 with pytest.raises(RuntimeRefused,match='FAKE_ECONOMIC_RECONCILIATION'):reconcile(o,e,s)
