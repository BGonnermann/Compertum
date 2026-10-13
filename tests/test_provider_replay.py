"""Real inputs stay diagnostic; hand checks cover cash fees and dated entitlement."""
from dataclasses import replace
from decimal import Decimal as D,localcontext,ROUND_DOWN
import importlib.util,json
import pytest
from compertum.data.errors import DataError
from compertum.data.encoding import canonical
from compertum.data.calendar import session_times
from test_provider_snapshot import envelopes,build,START,END

def api():
 assert importlib.util.find_spec('compertum.simulation.provider_replay'), 'Provider replay missing'
 from compertum.simulation import provider_replay
 return provider_replay

@pytest.fixture(scope='module')
def snapshot(envelopes):return build(envelopes)

def document(s):
 return {'schema':'provider-replay-scenario-v1','snapshot_sha256':s.sha256,'start':s.start,'end':s.end,
  'sectors':{x:('BENCHMARK' if x=='SPY' else x) for x in json.loads(s.content)['symbols']},
  'actions':[],'evidence_sha256':['1'*64],'fee_scenario':'US_EQUITY_REGULATORY_2023_ORDER_CEILING',
  'accounting_status':'KNOWN_ACTIONS_ONLY_COMPLETENESS_UNQUALIFIED','no_effective_split_assumption':True,
  'identity_status':'HISTORICAL_SECURITY_BINDING_BROKER_ELIGIBILITY_UNVERIFIED',
  'sector_status':'FIXED_DATED_GROUPS_NOT_HISTORICAL_GICS','financial_accepted':False}

def scenario(s,edit=None):
 v=document(s)
 if edit:edit(v)
 return api().read_scenario(canonical(v))

def dividend(day=END,pay='2023-12-14'):
 return {'action_id':'sample-dividend','symbol':'AAPL','kind':'DIVIDEND','effective_session':day,'pay_date':pay,'amount':'0.24','simulated_known_at':session_times(START).decision.isoformat(),'source_sha256':['1'*64]}

def test_real_replay_never_passes_as_synthetic_or_financial(snapshot):
 a=api();r=a.replay_provider(snapshot,scenario(snapshot),1);v=json.loads(r.content)
 assert v['financial_status']=='REAL_ENGINEERING_DIAGNOSTIC' and v['financial_accepted'] is False
 assert v['accounting_status']=='KNOWN_ACTIONS_ONLY_COMPLETENESS_UNQUALIFIED'
 assert v['snapshot_sha256']==snapshot.sha256 and 'ZERO_UNVERIFIED_FEES' not in v['assumptions']
 trades=v['portfolios']['spy60']['trades'];assert trades
 assert all(D(t['fee'])>0 for t in trades if t['side']=='SELL')
 assert all(D(t['fee'])==0 for t in trades if t['side']=='BUY')
 assert v['portfolios']['zero']['metrics']['sharpe'] is None
 assert v['strategy_qualification']=='BLOCKED_INPUTS_AND_EVIDENCE_COUNT'

@pytest.mark.parametrize('h',[1,5,21])
@pytest.mark.parametrize('cost',[10,20])
def test_every_horizon_cost_is_repeatable(snapshot,h,cost):
 a=api();s=scenario(snapshot);r=a.replay_provider(snapshot,s,h,cost_bps=cost)
 with localcontext() as ctx:
  ctx.prec=8;ctx.rounding=ROUND_DOWN
  assert a.replay_provider(snapshot,s,h,cost_bps=cost)==r

@pytest.mark.parametrize('field,value',[
 ('financial_accepted',True),('snapshot_sha256','0'*64),('start','2024-01-02'),
 ('fee_scenario','ZERO'),('accounting_status','QUALIFIED'),('no_effective_split_assumption',False),
 ('sectors',{}),('evidence_sha256',[]),('identity_status','VERIFIED_BROKER_PERMISSIONS')])
def test_invalid_scenario_cannot_enter(snapshot,field,value):
 with pytest.raises(DataError):api().replay_provider(snapshot,scenario(snapshot,lambda v:v.update({field:value})),1)

def test_duplicate_or_late_action_rejected(snapshot):
 a=dividend()
 with pytest.raises(DataError,match='SCENARIO_ACTION'):scenario(snapshot,lambda v:v.update(actions=[a,a]))
 a['simulated_known_at']='2023-11-27T14:25:00Z'
 with pytest.raises(DataError,match='ACTION_UNAVAILABLE'):scenario(snapshot,lambda v:v.update(actions=[a]))

def test_unknown_action_is_not_silently_zero(snapshot):
 a=dividend();a['kind']='UNKNOWN_MERGER'
 with pytest.raises(DataError):scenario(snapshot,lambda v:v.update(actions=[a]))

def test_snapshot_tamper_and_missing_reference_refused(snapshot,envelopes):
 with pytest.raises(DataError):api().replay_provider(replace(snapshot,sha256='0'*64),scenario(snapshot),1)
 missing=build(envelopes[:-1])
 with pytest.raises(DataError,match='PROVIDER_COVERAGE'):api().replay_provider(missing,scenario(missing),1)

@pytest.mark.parametrize('day,qty,price,side,expected',[
 ('2023-10-02',100,D('100'),'SELL',D('.10')),
 ('2023-11-30',10,D('99.9'),'SELL',D('.02')),
 ('2023-11-30',100000,D('1'),'SELL',D('8.07')),
 ('2023-11-30',10,D('100'),'BUY',D('0')),
 ('2023-11-30',1,D('.0001'),'SELL',D('.01'))])
def test_hand_fee_schedule(day,qty,price,side,expected):
 assert api().regulatory_fee(day,qty,price,side)==expected

@pytest.mark.parametrize('day,qty,price,side',[
 ('2024-01-02',1,D(1),'SELL'),('2023-10-02',True,D(1),'SELL'),
 ('2023-10-02',0,D(1),'SELL'),('2023-10-02',1,D('NaN'),'SELL'),
 ('2023-10-02',1,D(1),'SHORT')])
def test_invalid_fee_inputs_refused(day,qty,price,side):
 with pytest.raises(DataError):api().regulatory_fee(day,qty,price,side)

def test_hand_ledger_dividend_receivable_survives_terminal_sale(snapshot):
 from compertum.simulation.engine import Ledger
 a=api();m=a.load_provider_market(snapshot,scenario(snapshot,lambda v:v.update(actions=[dividend()])));l=Ledger('spy60')
 l.fill(m,START,'AAPL',10,'BUY',D('.001'));cash=l.cash
 assert cash==D('8997.74875') # 10 * 100.125 * 1.001
 l.apply_actions(m,END);assert l.cash==cash and l.nav({'AAPL':D('100')})==cash+1000+D('2.4')
 l.fill(m,END,'AAPL',10,'SELL',D('.001'),terminal=True)
 assert not l.positions and l.cash==D('9997.97750') and l.nav({})==D('10000.37750')
 assert l.trades[-1]['fee']=='0.02'
 l.apply_actions(m,'2023-12-14');assert not l.receivables and l.cash==D('10000.37750')

def test_ex_date_purchase_gets_no_dividend(snapshot):
 from compertum.simulation.engine import Ledger
 m=api().load_provider_market(snapshot,scenario(snapshot,lambda v:v.update(actions=[dividend(day=START)])))
 l=Ledger('spy60');l.apply_actions(m,START);l.fill(m,START,'AAPL',10,'BUY',D('.001'))
 assert not l.receivables and not l.actions

def test_future_adjusted_price_scale_cannot_change_raw_features(envelopes):
 original=build(envelopes);altered=json.loads(json.dumps(envelopes))
 for e in altered:
  if e['requests'][0]['params']['adjustment']!='split':continue
  for p in e['pages']:
   b=json.loads(p['body_utf8'])
   for bars in b['bars'].values():
    for row in bars:
     for k in ('o','h','l','c','vw'):row[k]/=10
     row['v']*=10
   p['body_utf8']=json.dumps(b);p['body_sha256']=__import__('hashlib').sha256(p['body_utf8'].encode()).hexdigest()
 changed=build(altered);a=api().load_provider_market(original,scenario(original));b=api().load_provider_market(changed,scenario(changed))
 assert a.features('NVDA',START,21)==b.features('NVDA',START,21)
 assert a.reference('NVDA',START,'entry')==b.reference('NVDA',START,'entry')
 a.rows[('AAPL',session_times(START).previous_date,'daily')]['simulated_available_at']='2023-11-27T14:25:00Z'
 assert a.features('AAPL',START,1)==(None,'FEATURE_UNAVAILABLE')
@pytest.mark.parametrize('field,value',[('snapshot_sha256',{}),('evidence_sha256',[[]])])
def test_malformed_hash_binding_is_explicit_data_rejection(snapshot,field,value):
 with pytest.raises(DataError,match='SCENARIO_EVIDENCE'):scenario(snapshot,lambda v:v.update({field:value}))