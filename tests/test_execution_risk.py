"""Invented fake-account fixtures. No real broker or financial admission."""
from copy import deepcopy
from uuid import uuid4
import pytest

from compertum.execution_contracts import record_sha256

NOW='2023-10-17T13:35:10+00:00'

def quote(symbol='AAPL',sector='TECH',price='100'):
 return dict(symbol=symbol,sector=sector,bid=price,ask=price,observed_at=NOW,feed='fixture',mean_dollar_volume='1000000',liquidity_sessions=20,liquidity_as_of='2023-10-16',liquidity_verified=True)


def observation():
 result=dict(schema_version='1',record_type='ExecutionObservation',scope='DETERMINISTIC_FAKE',currency='USD',
  account_alias='fake-account',generation=1,observation_id=str(uuid4()),observed_at=NOW,feed='fixture',
  clock=dict(observed_at=NOW,broker_at=NOW,calendar_sha256='a'*64,calendar_verified=True,prior_session='2023-10-16',session_open_at='2023-10-17T13:30:00+00:00',session_close_at='2023-10-17T20:00:00+00:00',strategy_open_at='2023-10-17T13:35:00+00:00',strategy_close_at='2023-10-17T13:36:00+00:00'),
  health=dict(execution_at=NOW,watchdog_at=NOW,supervision_at=NOW,connected=True,account_enabled=True,durable=True,resources_ok=True,exclusive_owner=True,journal_reserved=True,broker_cancel_allowed=True),
  authority=dict(ownership_complete=True,foreign_activity=False,unknown_intents=False,armed=True,halted=False,strategy_admitted=True,inputs_sha256='e'*64,strategy_sha256='b'*64,authorization_sha256='c'*64,rebalance_id=str(uuid4())),
  account=dict(reconciled_at=NOW,sleeve_cash='10000',broker_cash='10000',prior_close_nav='10000',prior_peak_nav='10000',submissions=0,dividend_receivables='0',undebited_liabilities='0'),positions=[],orders=[],quotes=[quote()])
 result['clock']['calendar_sha256']=record_sha256(calendar())
 return result


def intent(obs,*,quantity=19,kind='STRATEGY',side='buy',symbol='AAPL'):
 return dict(schema_version='1',record_type='ExecutionIntent',scope='DETERMINISTIC_FAKE',currency='USD',intent_id=str(uuid4()),account_alias=obs['account_alias'],generation=obs['generation'],created_at=NOW,expires_at='2023-10-17T13:36:00+00:00',kind=kind,side=side,symbol=symbol,quantity=quantity,inputs_sha256=obs['authority']['inputs_sha256'],strategy_sha256=obs['authority']['strategy_sha256'],authorization_sha256=obs['authority']['authorization_sha256'],rebalance_id=obs['authority']['rebalance_id'],snapshot_sha256=None,plan_id=None,child_index=None,order_id=None)


def test_buffered_buy_uses_exact_cash_and_cap():
 from compertum.domain import ExecutionObservation,ExecutionIntent
 from compertum.execution_risk import assess,snapshot_sha256
 obs=observation();inputs=bind(obs);request=intent(obs);request['snapshot_sha256']=snapshot_sha256(ExecutionObservation(obs))
 result=assess(ExecutionIntent(request),ExecutionObservation(obs),now=NOW,calendar=calendar(),inputs=inputs)
 assert result['allowed'] and result['maximum_quantity']==19 and result['reserved_notional']=='1920.919'
 request['quantity']=20
 refused=assess(ExecutionIntent(request),ExecutionObservation(obs),now=NOW,calendar=calendar(),inputs=inputs)
 assert not refused['allowed'] and 'INTENT_NOTIONAL_CAP' in refused['reasons']


def checked(obs,**changes):
 from compertum.domain import ExecutionObservation,ExecutionIntent
 from compertum.execution_risk import assess,snapshot_sha256
 inputs=bind(obs);request=intent(obs);request.update(changes);record=ExecutionObservation(obs)
 request['snapshot_sha256']=snapshot_sha256(record)
 return assess(ExecutionIntent(request),record,now=NOW,calendar=calendar(),inputs=inputs)


def holding(symbol,quantity):
 return dict(symbol=symbol,quantity=str(quantity),owned_quantity=quantity)


def order(symbol='AAPL',quantity=10,filled=4,side='buy',status='PARTIALLY_FILLED'):
 return dict(order_id=str(uuid4()),client_order_id='cmp-'+uuid4().hex+'a'*8,symbol=symbol,side=side,quantity=quantity,filled_quantity=filled,status=status,owned=True,filled_notional=str(100*filled))


def test_partial_fill_reserves_only_remaining_buy():
 obs=observation();obs['positions']=[holding('AAPL',4)];obs['account'].update(sleeve_cash='9600',broker_cash='9600');obs['orders']=[order()]
 result=checked(obs,quantity=9)
 assert result['allowed'] and result['maximum_quantity']==9
 assert result['existing_projected_exposure']=={'AAPL':'1006.606'}
 assert result['unreserved_cash']=='8993.394'
 assert 'NAME_LIMIT' in checked(obs,quantity=10)['reasons']


def test_unconfirmed_sell_never_releases_exposure_or_cash():
 obs=observation();obs['positions']=[holding(s,20) for s in ('AAPL','JPM','XOM')];obs['quotes']=[quote(s,s) for s in ('AAPL','JPM','XOM','JNJ')];obs['account'].update(sleeve_cash='4000',broker_cash='4000');obs['orders']=[order(quantity=20,filled=0,side='sell',status='ACKNOWLEDGED')]
 before=checked(obs,symbol='JNJ',quantity=1)
 assert before['maximum_quantity']==0 and 'GROSS_LIMIT' in before['reasons']
 obs['orders'][0].update(filled_quantity=20,filled_notional='2000',status='FILLED');obs['positions']=obs['positions'][1:];obs['account'].update(sleeve_cash='6000',broker_cash='6000')
 assert checked(obs,symbol='JNJ',quantity=19)['allowed']


def test_sector_and_gross_headroom():
 obs=observation();obs['positions']=[holding('MSFT',20),holding('NVDA',10)];obs['quotes']=[quote(s) for s in ('MSFT','NVDA','AAPL')];obs['account'].update(sleeve_cash='7000',broker_cash='7000')
 assert checked(obs,quantity=9)['allowed']
 assert 'SECTOR_LIMIT' in checked(obs,quantity=10)['reasons']
 obs['positions']=[holding('MSFT',20),holding('JPM',20),holding('XOM',19)];obs['quotes']=[quote(s,s) for s in ('MSFT','JPM','XOM')]+[quote('AAPL','TECH','10')];obs['account'].update(sleeve_cash='4100',broker_cash='4100')
 assert checked(obs,quantity=9)['allowed']
 assert 'GROSS_LIMIT' in checked(obs,quantity=10)['reasons']


@pytest.mark.parametrize('cash,prior,peak,reason,allowed',[
 ('9800','10000','10000','DAILY_LOSS',False),('9800.01','10000','10000','DAILY_LOSS',True),
 ('9000','9000','10000','DRAWDOWN',False),('9000.01','9000','10000','DRAWDOWN',True)])
def test_exact_loss_boundaries(cash,prior,peak,reason,allowed):
 obs=observation();obs['account'].update(sleeve_cash=cash,broker_cash=cash,prior_close_nav=prior,prior_peak_nav=peak)
 result=checked(obs,quantity=1)
 assert result['allowed']==allowed and (reason in result['reasons'])!=allowed


@pytest.mark.parametrize('path,value,reason',[
 ('health.connected',False,'OFFLINE'),('health.account_enabled',False,'ACCOUNT_BLOCKED'),
 ('health.durable',False,'DURABILITY_UNVERIFIED'),('health.resources_ok',False,'RESOURCE_BLOCKED'),
 ('health.execution_at','2023-10-17T13:34:54+00:00','HEARTBEAT_STALE'),
 ('health.watchdog_at','2023-10-17T13:35:11+00:00','HEARTBEAT_STALE'),
 ('health.supervision_at','2023-10-17T13:30:09+00:00','SUPERVISION_EXPIRED'),
 ('account.reconciled_at','2023-10-17T13:34:39+00:00','RECONCILIATION_STALE'),
 ('clock.calendar_verified',False,'CALENDAR_UNVERIFIED'),
 ('clock.broker_at','2023-10-17T13:35:16+00:00','CLOCK_MISMATCH'),
 ('authority.ownership_complete',False,'OWNERSHIP_UNVERIFIED'),('authority.foreign_activity',True,'OWNERSHIP_UNVERIFIED'),
 ('authority.unknown_intents',True,'UNKNOWN_INTENT'),('authority.armed',False,'STRATEGY_DISARMED'),
 ('authority.halted',True,'STRATEGY_DISARMED'),('authority.strategy_admitted',False,'STRATEGY_UNQUALIFIED'),
 ('account.submissions',6,'SUBMISSION_LIMIT'),('account.broker_cash','100','CASH_LIMIT')])
def test_independent_fail_closed_gates(path,value,reason):
 obs=observation();section,key=path.split('.');obs[section][key]=value
 result=checked(obs)
 assert not result['allowed'] and reason in result['reasons']


@pytest.mark.parametrize('field,value,reason',[
 ('bid','0','QUOTE_INVALID'),('bid','101','QUOTE_INVALID'),
 ('observed_at','2023-10-17T13:34:39+00:00','QUOTE_INVALID'),
 ('observed_at','2023-10-17T13:35:11+00:00','QUOTE_INVALID'),
 ('liquidity_verified',False,'LIQUIDITY_UNVERIFIED'),('liquidity_sessions',19,'LIQUIDITY_UNVERIFIED'),
 ('liquidity_as_of','2023-10-13','LIQUIDITY_UNVERIFIED')])
def test_quote_and_liquidity_gates(field,value,reason):
 obs=observation();obs['quotes'][0][field]=value
 result=checked(obs)
 assert not result['allowed'] and reason in result['reasons']


def test_no_short_and_pending_sell_reservation():
 obs=observation();obs['positions']=[holding('AAPL',10)];obs['account'].update(sleeve_cash='9000',broker_cash='9000');obs['orders']=[order(quantity=7,filled=0,side='sell',status='ACKNOWLEDGED')]
 assert checked(obs,side='sell',quantity=3)['allowed']
 assert 'OWNED_QUANTITY' in checked(obs,side='sell',quantity=4)['reasons']
 obs['positions'][0]['quantity']='10.5'
 assert 'FOREIGN_POSITION' in checked(obs,side='sell',quantity=1)['reasons']


def test_snapshot_and_identity_are_bound():
 from compertum.domain import ExecutionObservation,ExecutionIntent
 from compertum.execution_risk import assess,snapshot_sha256,client_order_id
 raw=observation();inputs=bind(raw);obs=ExecutionObservation(raw);p=intent(obs.to_payload());p['snapshot_sha256']=snapshot_sha256(obs)
 original=ExecutionIntent(p);p['account_alias']='fake-wrong'
 assert 'ACCOUNT_OR_GENERATION' in assess(ExecutionIntent(p),obs,now=NOW,calendar=calendar(),inputs=inputs)['reasons']
 p=original.to_payload();p['snapshot_sha256']='d'*64
 assert 'SNAPSHOT_CHANGED' in assess(ExecutionIntent(p),obs,now=NOW,calendar=calendar(),inputs=inputs)['reasons']
 p=original.to_payload();p['generation']=2;p['quantity']=1
 assert client_order_id(ExecutionIntent(p))==client_order_id(original)


@pytest.mark.parametrize('mutate',[
 lambda p:p.update(generation=1.0),lambda p:p.update(account_alias='paper-primary'),
 lambda p:p['quotes'].append(deepcopy(p['quotes'][0])),lambda p:p['account'].update(sleeve_cash='NaN'),
 lambda p:p.update(observation_id='00000000-0000-0000-0000-000000000000'),
 lambda p:p.update(extra=True)])
def test_invalid_contracts_rejected(mutate):
 from compertum.domain import ExecutionObservation,ContractError
 obs=observation();mutate(obs)
 with pytest.raises(ContractError):ExecutionObservation(obs)


from functools import lru_cache
@lru_cache(maxsize=1)
def calendar():
 from compertum.domain import ExecutionCalendar
 from compertum.data.calendar import session_times
 c=session_times('2023-10-17')
 return ExecutionCalendar(dict(schema_version='1',record_type='ExecutionCalendar',scope='DETERMINISTIC_FAKE',session_date='2023-10-17',prior_session=c.previous_date,session_open_at=c.open.isoformat(),session_close_at=c.close.isoformat(),source_sha256='f'*64))


def bind(obs):
 from compertum.domain import ExecutionInputs
 from compertum.data.encoding import canonical
 from compertum.execution_contracts import WATCHLIST
 import hashlib
 sectors={s:s for s in WATCHLIST};sectors.update({q['symbol']:q['sector'] for q in obs['quotes']})
 p=dict(schema_version='1',record_type='ExecutionInputs',scope='DETERMINISTIC_FAKE',strategy_sha256=obs['authority']['strategy_sha256'],authorization_sha256=obs['authority']['authorization_sha256'],rebalance_id=obs['authority']['rebalance_id'],session_date='2023-10-17',feature_session='2023-10-16',feature_available_at='2023-10-17T13:20:00+00:00',decision_at='2023-10-17T13:25:00+00:00',bundle_finalized_at='2023-10-17T13:30:00+00:00',arm_expires_at='2023-10-17T20:00:00+00:00',calendar_sha256=record_sha256(calendar()),sector_mapping_sha256=hashlib.sha256(canonical(sectors)).hexdigest(),securities=[dict(symbol=s,sector=sectors[s],provider_asset_id=str(uuid4()),feature_sessions=252,raw_close='100',mean_dollar_volume='1000000',tradable=True,actions_verified=True,mapping_verified=True) for s in WATCHLIST])
 record=ExecutionInputs(p);obs['authority']['inputs_sha256']=record_sha256(record)
 return record


def assess_pinned(o,inputs,*,now=NOW,**changes):
 from compertum.domain import ExecutionObservation,ExecutionIntent
 from compertum.execution_risk import snapshot_sha256,assess
 i=intent(o);i.update(quantity=1,**changes);i['snapshot_sha256']=snapshot_sha256(ExecutionObservation(o))
 return assess(ExecutionIntent(i),ExecutionObservation(o),now=now,calendar=calendar(),inputs=inputs)


def test_arbitrary_strategy_window_is_not_authorized_by_fresh_snapshot():
 o=observation();inputs=bind(o);o['clock'].update(strategy_open_at='2023-10-17T13:30:00+00:00',strategy_close_at='2023-10-17T14:30:00+00:00')
 assert 'STRATEGY_WINDOW_CHANGED' in assess_pinned(o,inputs)['reasons']


def test_terminal_fill_contradiction_is_refused():
 from compertum.domain import ExecutionObservation,ContractError
 o=observation();o['orders']=[order(quantity=19,filled=0,status='FILLED')]
 with pytest.raises(ContractError):ExecutionObservation(o)


def test_dividend_receivables_are_nav_but_not_buying_cash():
 o=observation();o['account'].update(sleeve_cash='9799',broker_cash='9799',dividend_receivables='201')
 result=checked(o,quantity=1)
 assert result['allowed'] and result['risk_nav']=='10000' and result['unreserved_cash']=='9799'
 o['account'].update(sleeve_cash='10000',broker_cash='10000',dividend_receivables='0',undebited_liabilities='200')
 result=checked(o,quantity=1)
 assert not result['allowed'] and result['risk_nav']=='9800' and result['unreserved_cash']=='9800' and 'DAILY_LOSS' in result['reasons']


@pytest.mark.parametrize('field,value',[
 ('feature_session','2023-10-13'),('feature_available_at','2023-10-17T13:25:01+00:00'),
 ('bundle_finalized_at','2023-10-17T13:35:00+00:00'),('bundle_finalized_at','2023-10-17T13:35:01+00:00'),('arm_expires_at','2023-10-18T20:00:00+00:00')])
def test_bad_strategy_inputs_cannot_be_admitted_by_hash_match(field,value):
 from compertum.domain import ExecutionInputs
 o=observation();p=bind(o).to_payload();p[field]=value;inputs=ExecutionInputs(p);o['authority']['inputs_sha256']=record_sha256(inputs)
 assert not assess_pinned(o,inputs)['allowed']


@pytest.mark.parametrize('field,value',[
 ('mean_dollar_volume','100000'),('raw_close','4.99'),('feature_sessions',251),
 ('tradable',False),('actions_verified',False),('mapping_verified',False)])
def test_selected_security_requires_all_frozen_eligibility_inputs(field,value):
 from compertum.domain import ExecutionInputs
 o=observation();p=bind(o).to_payload();p['securities'][0][field]=value;inputs=ExecutionInputs(p);o['authority']['inputs_sha256']=record_sha256(inputs)
 assert 'SYMBOL_INELIGIBLE' in assess_pinned(o,inputs)['reasons']


def test_changed_sector_label_cannot_evade_frozen_mapping():
 o=observation();inputs=bind(o);o['quotes'][0]['sector']='OTHER'
 assert 'SECTOR_MAPPING_CHANGED' in assess_pinned(o,inputs)['reasons']


def test_missing_independent_pins_refuse_even_self_consistent_snapshot():
 from compertum.domain import ExecutionObservation,ExecutionIntent
 from compertum.execution_risk import snapshot_sha256,assess
 o=observation();bind(o);i=intent(o);i['snapshot_sha256']=snapshot_sha256(ExecutionObservation(o))
 result=assess(ExecutionIntent(i),ExecutionObservation(o),now=NOW)
 assert {'STRATEGY_INPUTS_REQUIRED','CALENDAR_PIN_REQUIRED'}<=set(result['reasons'])


def test_risk_result_is_independent_of_ambient_decimal_context():
 from decimal import localcontext,ROUND_UP
 o=observation()
 with localcontext() as ctx:
  ctx.prec=3;ctx.rounding=ROUND_UP
  result=checked(o,quantity=19)
 assert result['allowed'] and result['reserved_notional']=='1920.919'


def test_decision_cannot_be_mutated_or_claim_financial_admission():
 o=observation();result=checked(o)
 with pytest.raises(TypeError):result.payload['allowed']=False
 with pytest.raises(TypeError):result.payload['dependencies']['calendar']='0'*64
 assert result['financial_accepted'] is False and result['allowed']


def test_plan_validation_has_fixed_decimal_context():
 from decimal import localcontext
 from test_execution_plans import setup,records
 from compertum.domain import ExecutionPlan
 o=setup();p,a,start=records(o)
 with localcontext() as context:
  context.prec=3
  assert ExecutionPlan(p.to_payload()).to_payload()==p.to_payload()
