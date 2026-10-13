"""Bounded real-data engineering replay; no financial or broker admission."""
from dataclasses import dataclass
from decimal import Decimal as D,ROUND_CEILING
import hashlib,json,re
from compertum.data.alpaca import SYMBOLS,_load
from compertum.data.calendar import session_times,utc_time,session_date
from compertum.data.encoding import canonical
from compertum.data.errors import DataError
from compertum.data.provider_snapshot import verify_provider_snapshot
from .market import Market
from .engine import _replay_market
from .policy import fixed_decimal

FEE_SCENARIO='US_EQUITY_REGULATORY_2023_ORDER_CEILING'
ACCOUNTING='KNOWN_ACTIONS_ONLY_COMPLETENESS_UNQUALIFIED'
IDENTITY='HISTORICAL_SECURITY_BINDING_BROKER_ELIGIBILITY_UNVERIFIED'
SECTORS='FIXED_DATED_GROUPS_NOT_HISTORICAL_GICS'

@dataclass(frozen=True)
class ProviderScenario:
 content:bytes
 sha256:str

def _hashes(values):
 if not isinstance(values,list) or not 1<=len(values)<=64 or any(not isinstance(h,str) or not re.fullmatch('[0-9a-f]{64}',h) for h in values) or len(set(values))!=len(values):
  raise DataError('SCENARIO_EVIDENCE')

def read_scenario(raw):
 if not isinstance(raw,bytes) or not 1<=len(raw)<=131072:raise DataError('INPUT_BOUND')
 try:v=_load(raw.decode('utf-8'))
 except (UnicodeError,ValueError):raise DataError('SCENARIO_SCHEMA') from None
 fields={'schema','snapshot_sha256','start','end','sectors','actions','evidence_sha256','fee_scenario','accounting_status','no_effective_split_assumption','identity_status','sector_status','financial_accepted'}
 if not isinstance(v,dict) or set(v)!=fields or v['schema']!='provider-replay-scenario-v1':raise DataError('SCENARIO_SCHEMA')
 if v['financial_accepted'] is not False or v['no_effective_split_assumption'] is not True or v['accounting_status']!=ACCOUNTING or v['identity_status']!=IDENTITY or v['sector_status']!=SECTORS or v['fee_scenario']!=FEE_SCENARIO:raise DataError('SCENARIO_QUALIFICATION')
 _hashes([v['snapshot_sha256']]);_hashes(v['evidence_sha256'])
 start= session_times(v['start']);end=session_times(v['end'])
 if not '2023-10-02'<=v['start']<=v['end']<='2023-11-30':raise DataError('SCENARIO_WINDOW')
 sectors=v['sectors']
 if not isinstance(sectors,dict) or set(sectors)!=set(SYMBOLS) or any(not isinstance(s,str) or not re.fullmatch('[A-Za-z][A-Za-z0-9 _-]{0,47}',s) for s in sectors.values()):raise DataError('SECTOR_MAPPING')
 actions=v['actions'];seen=set();semantic=set()
 if not isinstance(actions,list) or len(actions)>64:raise DataError('SCENARIO_ACTION')
 for a in actions:
  if not isinstance(a,dict) or set(a)!={'action_id','symbol','kind','effective_session','pay_date','amount','simulated_known_at','source_sha256'}:raise DataError('SCENARIO_ACTION')
  if not isinstance(a['action_id'],str) or not re.fullmatch('[A-Za-z0-9_-]{1,80}',a['action_id']) or a['action_id'] in seen or a['symbol'] not in SYMBOLS or a['kind']!='DIVIDEND':raise DataError('SCENARIO_ACTION')
  ex=session_times(a['effective_session']);pay=session_date(a['pay_date'])
  if not v['start']<=a['effective_session']<=v['end'] or pay.isoformat()<a['effective_session'] or pay.year!=2023:raise DataError('SCENARIO_ACTION')
  if not isinstance(a['amount'],str) or not re.fullmatch(r'[0-9]{1,6}(\.[0-9]{1,8})?',a['amount']) or D(a['amount'])<=0:raise DataError('SCENARIO_ACTION')
  if utc_time(a['simulated_known_at'])>ex.decision:raise DataError('ACTION_UNAVAILABLE')
  _hashes(a['source_sha256'])
  if not set(a['source_sha256'])<=set(v['evidence_sha256']):raise DataError('SCENARIO_EVIDENCE')
  key=(a['symbol'],a['effective_session'])
  if key in semantic:raise DataError('SCENARIO_ACTION')
  seen.add(a['action_id']);semantic.add(key)
 v['actions']=sorted(actions,key=lambda a:(a['effective_session'],a['symbol'],a['action_id']))
 content=canonical(v);return ProviderScenario(content,hashlib.sha256(content).hexdigest())

@fixed_decimal
def regulatory_fee(day,quantity,price,side):
 """Declared conservative order-level scenario, not actual customer billing."""
 if not isinstance(day,str) or not '2023-10-02'<=day<='2023-11-30' or type(quantity) is not int or not 0<quantity<=100000000 or not isinstance(price,D) or not price.is_finite() or price<=0 or side not in ('BUY','SELL'):raise DataError('FEE_INPUT')
 session_times(day)
 if side=='BUY':return D(0)
 sec=(quantity*price*D('.000008')).quantize(D('.01'),rounding=ROUND_CEILING)
 taf=min(D('7.27'),quantity*D('.000145')) if price>=D('.000145') else D(0)
 return sec+taf.quantize(D('.01'),rounding=ROUND_CEILING)

@dataclass
class ProviderMarket(Market):
 scenario:dict
 snapshot_sha256:str
 scenario_sha256:str
 def trade_fee(self,day,quantity,price,side):return regulatory_fee(day,quantity,price,side)
 def replay_metadata(self):
  return {'policy':'momentum-provider-engineering-v1','financial_status':'REAL_ENGINEERING_DIAGNOSTIC','financial_accepted':False,
   'strategy_qualification':'BLOCKED_INPUTS_AND_EVIDENCE_COUNT','snapshot_sha256':self.snapshot_sha256,'scenario_sha256':self.scenario_sha256,
   'fee_scenario':FEE_SCENARIO,'accounting_status':ACCOUNTING,'identity_status':IDENTITY,'sector_status':SECTORS,
   'evidence_sha256':self.scenario['evidence_sha256'],
   'assumptions':['CURRENT_VINTAGE_SIMULATED_AVAILABILITY','KNOWN_ACTIONS_PARTIAL_ACCOUNTING','NO_EFFECTIVE_SPLITS_IN_BOUND_WINDOW_ASSUMPTION',
    'RAW_PRICE_VOLUME_FEATURES','HISTORICAL_SECURITY_BROKER_ELIGIBILITY_UNVERIFIED','FIXED_DATED_SECTOR_GROUPS','REGULATORY_FEES_PER_MODELED_ORDER_CEILING_NOT_ACTUAL_CUSTOMER_BILLING',
    'NO_INTEREST_OR_FINANCING','HISTORICAL_REFERENCE_FILLS','NO_CONTINUOUS_INTRADAY_RISK','NO_LIVE_PLANNER_PARITY']}

def load_provider_market(snapshot,scenario):
 verify_provider_snapshot(snapshot)
 if type(scenario) is not ProviderScenario or read_scenario(scenario.content)!=scenario:raise DataError('SCENARIO_CORRUPT')
 v=json.loads(snapshot.content);s=json.loads(scenario.content)
 if (s['snapshot_sha256'],s['start'],s['end'])!=(snapshot.sha256,snapshot.start,snapshot.end):raise DataError('SCENARIO_BINDING')
 if not v['coverage']['complete']:raise DataError('PROVIDER_COVERAGE')
 rows={(r['symbol'],r['session_date'],r['reference']):r for r in v['rows'] if r['adjustment']=='raw'}
 identity=hashlib.sha256(canonical({'snapshot':snapshot.sha256,'scenario':scenario.sha256})).hexdigest()
 return ProviderMarket(tuple(v['symbols']),dict(s['sectors']),rows,tuple(s['actions']),identity,s,snapshot.sha256,scenario.sha256)

@fixed_decimal
def replay_provider(snapshot,scenario,horizon,*,cost_bps=10):
 market=load_provider_market(snapshot,scenario)
 return _replay_market(market,snapshot.start,snapshot.end,horizon,cost_bps=cost_bps)