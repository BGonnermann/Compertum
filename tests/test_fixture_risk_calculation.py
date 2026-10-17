"""Proposed local risk arithmetic. These simulated inputs grant no authority."""
from copy import deepcopy
import pytest
from compertum.runtime.errors import RuntimeRefused
from compertum.runtime.paper_native_intent_terms import exact_terms
from compertum.paper_portfolio import build_portfolio_bundle
from test_paper_fixture_plans import portfolio,facts,position,order,INTENT,NOW,at_portfolio

def calculate(*,purpose='FIXTURE_BUY',terms=None,**changes):
 from compertum.fixture_risk import calculate_fixture_risk
 proposed={'FIXTURE_BUY':dict(fixture_id='local-finish',symbol='AAPL'),
  'FIXTURE_RESTING_BUY':dict(fixture_id='local-finish',symbol='AAPL',limit_price='80'),
  'CANCEL':dict(symbol='AAPL',order_id=order()['id']),
  'CLOSE_LONG':dict(symbol='AAPL',quantity=1,children=[dict(maximum_quantity=1,notional_cap='2000')])}
 values=dict(portfolio=portfolio(),inputs=facts(),purpose=purpose,
  terms=exact_terms(purpose,proposed[purpose]) if terms is None else terms,
  intent_id=INTENT,now=NOW,outstanding_fees='0')
 values.update(changes);return calculate_fixture_risk(**values)

def test_one_share_reuses_existing_cost_and_exposure_calculation():
 result=calculate().to_payload()
 assert result['planned_notional']=='101.101' and result['projected_exposure']=='101.101'
 assert result['available_cash']=='1000' and result['original_cash']=='1000'
 assert result['request']['body']['qty']=='1'
 assert result['scope']=='UNQUALIFIED_LOCAL_RISK_CALCULATION'
 assert result['source_qualified'] is result['financial_accepted'] is result['transport_authorized'] is False

def test_unpaid_liability_changes_cash_admission_without_rewriting_observation():
 original=portfolio(cash='101.102');saved=original.content
 assert calculate(portfolio=original).to_payload()['available_cash']=='101.102'
 with pytest.raises(RuntimeRefused):calculate(portfolio=original,outstanding_fees='0.002')
 assert original.content==saved

@pytest.mark.parametrize('liability',['-0.01','NaN','Infinity',True,'1000.01'])
def test_invalid_or_unfunded_liability_refuses(liability):
 with pytest.raises(RuntimeRefused):calculate(outstanding_fees=liability)

@pytest.mark.parametrize('change',['quantity','exposure','symbol','fixture','unknown'])
def test_changed_exact_terms_refuse(change):
 terms=exact_terms('FIXTURE_BUY',dict(fixture_id='local-finish',symbol='AAPL'))
 if change=='quantity':terms['quantity']=2
 elif change=='exposure':terms['maximum_exposure']='251'
 elif change=='symbol':terms['symbol']='MSFT'
 elif change=='fixture':terms['fixture_id']=''
 else:terms['approved']=True
 with pytest.raises(RuntimeRefused):calculate(terms=terms)

@pytest.mark.parametrize('fault',['held','order','exposure','stale','ineligible'])
def test_existing_fixture_refusals_remain_active(fault):
 changes={
  'held':dict(portfolio=portfolio(positions=[position()])),
  'order':dict(portfolio=portfolio(orders=[order()])),
  'exposure':dict(inputs=facts(ask='250',bid='249')),
  'stale':dict(inputs=facts(quote_change={'observed_at':'2023-11-24T14:34:00Z'})),
  'ineligible':dict(inputs=facts(security_change={'tradable':False}))}
 with pytest.raises(RuntimeRefused):calculate(**changes[fault])

def test_resting_order_retains_discount_holding_and_total_exposure():
 result=calculate(purpose='FIXTURE_RESTING_BUY',portfolio=portfolio(positions=[position()])).to_payload()
 assert result['planned_notional']=='80.8808' and result['projected_exposure']=='180.8808'
 assert result['request']['body']['limit_price']=='80'

def test_cancel_needs_no_quote_or_exchange_calendar():
 original=portfolio(orders=[order()])
 account_only=build_portfolio_bundle(account=original.account,positions=original.positions,orders=original.orders,
  clock=None,calendar=None,as_of=NOW)
 result=calculate(purpose='CANCEL',portfolio=account_only,inputs=None).to_payload()
 assert result['request']['method']=='DELETE' and result['request']['parameters']=={'order_id':order()['id']}
 assert result['planned_notional'] is None

def test_cancel_missing_target_refuses():
 with pytest.raises(RuntimeRefused):calculate(purpose='CANCEL',inputs=None)

@pytest.mark.parametrize('at,allowed',[
 ('2023-11-24T14:34:59.999999Z',False),('2023-11-24T14:35:00Z',True),
 ('2023-11-24T15:04:59.999999Z',True),('2023-11-24T15:05:00Z',False)])
def test_opening_window_keeps_exact_boundaries(at,allowed):
 current=facts(created_at=at,supervision_at=at,quote_change={'observed_at':at})
 values=dict(portfolio=at_portfolio(at),inputs=current,now=at)
 if allowed:assert calculate(**values).to_payload()['request']['body']['qty']=='1'
 else:
  with pytest.raises(RuntimeRefused):calculate(**values)

def test_close_uses_current_owned_quantity_and_exact_child_limits():
 result=calculate(purpose='CLOSE_LONG',portfolio=portfolio(positions=[position()])).to_payload()
 assert result['request']['body']['side']=='sell' and result['request']['body']['qty']=='1'
 enlarged=exact_terms('CLOSE_LONG',dict(symbol='AAPL',quantity=2,children=[dict(maximum_quantity=2,notional_cap='2000')]))
 with pytest.raises(RuntimeRefused):calculate(purpose='CLOSE_LONG',terms=enlarged,portfolio=portfolio(positions=[position()]))

def test_strategy_cannot_enter_fixture_risk_factory():
 from compertum.fixture_risk import calculate_fixture_risk
 with pytest.raises(RuntimeRefused):calculate_fixture_risk(portfolio=portfolio(),inputs=facts(),purpose='STRATEGY',
  terms={},intent_id=INTENT,now=NOW,outstanding_fees='0')
