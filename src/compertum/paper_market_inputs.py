"""Inert operational input evidence. No transport, native provenance or research use."""
from dataclasses import dataclass,field
from datetime import datetime,time,timedelta,timezone
from decimal import Decimal,Context,localcontext,InvalidOperation,DivisionByZero,Overflow,Inexact
from functools import lru_cache
import hashlib,json,re
from urllib.parse import urlencode
from .data.calendar import NY,session_times,session_date
from .data.encoding import canonical
from .data.errors import DataError
from .domain import ContractError
from .execution_contracts import WATCHLIST
from .paper_contracts import identifier,strict_json

_NS=10**9
_EPOCH=datetime(1970,1,1,tzinfo=timezone.utc)
_DATA='https://data.alpaca.markets'
_PAPER='https://paper-api.alpaca.markets'
_MISSING=('NATIVE_PROVENANCE_UNVERIFIED','FEED_ENTITLEMENT_UNVERIFIED','ACCOUNT_BINDING_UNVERIFIED','ACTION_HALT_COVERAGE_UNVERIFIED','FEE_APPLICABILITY_UNVERIFIED','SECTOR_MAPPING_UNVERIFIED','OWNERSHIP_RECONCILIATION_UNVERIFIED')


def _need(value):
 if not value:raise ContractError('MARKET_INPUT_INVALID')


def _sha(raw):return hashlib.sha256(raw).hexdigest()


def _ns(value):
 _need(type(value) is str)
 match=re.fullmatch(r'(20[0-9]{2}|2100)(-\d\d-\d\dT\d\d:\d\d:\d\d)(?:\.(\d{1,9}))?(?:Z|\+00:00)',value)
 _need(match is not None)
 try:base=datetime.fromisoformat(match[1]+match[2]+'+00:00')
 except ValueError:raise ContractError('MARKET_INPUT_INVALID') from None
 delta=base-_EPOCH
 return (delta.days*86400+delta.seconds)*_NS+int((match[3] or '').ljust(9,'0'))


def _day(value):
 # Integer seconds suffice only for identifying the civil date, never freshness.
 return (_EPOCH+timedelta(seconds=_ns(value)//_NS)).astimezone(NY).date().isoformat()


def _stamp(value):return value.isoformat().replace('+00:00','Z')


@lru_cache(maxsize=16)
def _calendar_rows(day):
 try:
  session_date(day);times=session_times(day);rows=[];previous=times.previous_date
  for _ in range(252):rows.append(previous);previous=session_times(previous).previous_date
  rows.reverse()
  labels=[_stamp(datetime.combine(session_date(d),time(),NY).astimezone(timezone.utc)) for d in rows]
  return tuple(rows),tuple(labels),_stamp(times.decision)
 except (DataError,ValueError,TypeError):raise ContractError('MARKET_INPUT_INVALID') from None


def _plan_payload(project_id,account_alias,symbol,session_date,created_at,feed='iex'):
 _need(type(project_id) is str and re.fullmatch('[0-9a-f]{64}',project_id) is not None)
 _need(type(account_alias) is str and re.fullmatch('[A-Za-z0-9][A-Za-z0-9_-]{0,63}',account_alias) is not None)
 _need(type(symbol) is str and symbol in set(WATCHLIST)|{'SPY'} and feed=='iex' and type(feed) is str)
 _need(type(session_date) is str)
 rows,labels,cutoff=_calendar_rows(session_date)
 _need(_day(created_at)==session_date and _ns(created_at)<=_ns(cutoff))
 return dict(version=1,record_type='OperationalMarketPlan',scope='PREPARATION_ONLY',project_id=project_id,account_alias=account_alias,
  symbol=symbol,session_date=session_date,created_at=created_at,feed=feed,currency='USD',history_sessions=list(rows),daily_labels=list(labels),
  history_cutoff_at=cutoff,maximum_history_pages=8,maximum_page_rows=100,maximum_responses=10,maximum_response_bytes=65536,
  maximum_envelope_bytes=1048576,transport_authorized=False,financial_accepted=False,research_eligible=False)


@dataclass(frozen=True,slots=True)
class OperationalMarketPlan:
 content:bytes
 def __post_init__(self):
  p=strict_json(self.content);keys=('project_id','account_alias','symbol','session_date','created_at','feed')
  _need(type(p) is dict and all(k in p for k in keys))
  _need(canonical(_plan_payload(**{k:p[k] for k in keys}))==self.content)
 def to_payload(self):return json.loads(self.content)
 @property
 def sha256(self):return _sha(self.content)


def prepare_market_plan(**values):return OperationalMarketPlan(canonical(_plan_payload(**values)))


def _token(value):
 _need(value is None or type(value) is str and re.fullmatch('[A-Za-z0-9_+/=-]{1,1024}',value) is not None)
 return value


def _request_payload(plan,operation,request_id,created_at,page_token):
 _need(type(plan) is OperationalMarketPlan);plan.__post_init__();p=plan.to_payload();identifier(request_id)
 _need(type(operation) is str and operation in {'ASSET','QUOTE','HISTORY'})
 _need(_day(created_at)==p['session_date'] and _ns(created_at)>=_ns(p['created_at']))
 if operation=='HISTORY':
  parameters=dict(symbols=p['symbol'],timeframe='1Day',start=p['daily_labels'][0],end=p['daily_labels'][-1],adjustment='raw',feed=p['feed'],asof=p['session_date'],sort='asc',currency='USD',limit=100)
  if _token(page_token) is not None:parameters['page_token']=page_token
  origin,path=_DATA,'/v2/stocks/bars'
 else:
  _need(page_token is None)
  if operation=='ASSET':origin,path,parameters=_PAPER,'/v2/assets/'+p['symbol'],{}
  else:origin,path,parameters=_DATA,'/v2/stocks/quotes/latest',dict(symbols=p['symbol'],feed=p['feed'],currency='USD')
 return dict(version=1,record_type='OperationalMarketRequest',scope='PREPARATION_ONLY',plan_sha256=plan.sha256,request_id=request_id,
  operation=operation,created_at=created_at,origin=origin,method='GET',path=path,parameters=parameters,target=path+('?' +urlencode(parameters) if parameters else ''),
  transport_authorized=False,financial_accepted=False)


@dataclass(frozen=True,slots=True)
class OperationalMarketRequest:
 plan:OperationalMarketPlan
 content:bytes
 def __post_init__(self):
  p=strict_json(self.content);keys=('operation','request_id','created_at')
  _need(type(p) is dict and all(k in p for k in keys) and type(p.get('parameters')) is dict)
  _need(canonical(_request_payload(self.plan,**{k:p[k] for k in keys},page_token=p['parameters'].get('page_token')))==self.content)
 def to_payload(self):return json.loads(self.content)
 @property
 def sha256(self):return _sha(self.content)


def prepare_market_request(plan,*,operation,request_id,created_at,page_token=None):
 return OperationalMarketRequest(plan,canonical(_request_payload(plan,operation,request_id,created_at,page_token)))


def _numeric(value,*,positive=False,integer=False):
 _need(type(value) in (int,Decimal))
 d=Decimal(value)
 _need(d.is_finite() and d>=0 and (not positive or d>0) and d<10**16)
 _need(len(d.as_tuple().digits)<=28 and d.as_tuple().exponent>=-12)
 if integer:_need(d==d.to_integral_value())
 return d


def _body(raw):
 _need(type(raw) is bytes and 0<len(raw)<=65536)
 def number(token):
  _need(len(token)<=48 and re.fullmatch(r'-?\d+(?:\.\d+)?(?:[eE][+-]?\d{1,3})?',token) is not None)
  d=Decimal(token)
  _need(d.is_finite() and len(d.as_tuple().digits)<=28 and -12<=d.as_tuple().exponent<=16 and d.copy_abs()<10**16)
  return d
 def pairs(items):
  value={}
  for k,v in items:_need(k not in value);value[k]=v
  return value
 def invalid(_):raise ContractError('MARKET_INPUT_INVALID')
 try:parsed=json.loads(raw.decode('utf-8'),object_pairs_hook=pairs,parse_float=number,parse_int=lambda t:int(t) if len(t)<=17 else invalid(t),parse_constant=invalid)
 except (ValueError,UnicodeError,RecursionError,InvalidOperation):raise ContractError('MARKET_INPUT_INVALID') from None
 pending=[(parsed,0)];count=0
 while pending:
  v,depth=pending.pop();count+=1;_need(depth<=16 and count<=10000)
  if type(v) is dict:pending.extend((x,depth+1) for x in v.values())
  elif type(v) is list:pending.extend((x,depth+1) for x in v)
 _need(type(parsed) is dict)
 return parsed


@dataclass(frozen=True,slots=True,repr=False)
class MarketObservation:
 request:OperationalMarketRequest
 raw:bytes=field(repr=False)
 status:int
 received_at:str
 def __post_init__(self):
  _need(type(self.request) is OperationalMarketRequest);self.request.__post_init__()
  _need(type(self.status) is int and (self.status==200 or 400<=self.status<=599))
  _need(0<=_ns(self.received_at)-_ns(self.request.to_payload()['created_at'])<=10*_NS)
  _need(_day(self.received_at)==self.request.plan.to_payload()['session_date']);_body(self.raw)
 def __repr__(self):return '<MarketObservation retained body redacted>'


def observe_market_reply(request,raw,*,status,received_at):return MarketObservation(request,raw,status,received_at)


def _text(value,maximum=64):_need(type(value) is str and 0<len(value)<=maximum);return value


def _fields(value,required):
 _need(type(value) is dict and set(required)<=set(value) and len(value)<=32)
 _need(all(type(k) is str and 0<len(k)<=64 for k in value))


def _evidence(plan,observations):
 _need(type(plan) is OperationalMarketPlan);plan.__post_init__()
 _need(type(observations) is tuple and len(observations)<=10)
 records=[];ids=set()
 for r in observations:
  _need(type(r) is MarketObservation);r.__post_init__();request=r.request.to_payload()
  _need(r.request.plan.content==plan.content and request['request_id'] not in ids);ids.add(request['request_id'])
  records.append(dict(request=request,body_utf8=r.raw.decode('utf-8'),status=r.status,received_at=r.received_at))
 raw=canonical(dict(plan=plan.to_payload(),responses=records));_need(len(raw)<=1048576)
 return raw


def _asset(record,symbol,now,reasons):
 result=dict(valid=False,asset_id=None,status=None,tradable=None,asset_class=None)
 if record is None:reasons.append('ASSET_MISSING');return result
 if record.status!=200:reasons.append('ASSET_HTTP_REFUSED');return result
 body=_body(record.raw);_fields(body,('id','class','symbol','exchange','status','tradable'))
 identifier(body['id']);_need(body['symbol']==symbol and type(body['tradable']) is bool)
 for k in ('class','exchange','status'):_text(body[k])
 result.update(asset_id=body['id'],status=body['status'],tradable=body['tradable'],asset_class=body['class'])
 checks=[]
 if now-_ns(record.request.to_payload()['created_at'])>30*_NS:checks.append('ASSET_STALE')
 if body['class']!='us_equity' or body['status']!='active' or body['tradable'] is not True:checks.append('ASSET_NOT_ACTIVE_TRADABLE_EQUITY')
 reasons.extend(checks);result['valid']=not checks;return result


def _quote(record,symbol,now,reasons):
 result=dict(valid=False,bid=None,ask=None,observed_at=None,age_ns=None)
 if record is None:reasons.append('QUOTE_MISSING');return result
 if record.status!=200:reasons.append('QUOTE_HTTP_REFUSED');return result
 body=_body(record.raw);_fields(body,('quotes',));quotes=body['quotes'];_need(type(quotes) is dict and set(quotes)<=set([symbol]))
 if symbol not in quotes or quotes[symbol] is None:reasons.append('QUOTE_MISSING');return result
 q=quotes[symbol];_fields(q,('t','bp','ap','bs','as'))
 bid,ask=_numeric(q['bp']),_numeric(q['ap']);_numeric(q['bs']);_numeric(q['as']);at=_ns(q['t']);checks=[]
 result.update(bid=_decimal_text(bid),ask=_decimal_text(ask),observed_at=q['t'],age_ns=now-at)
 if not 0<bid<=ask:checks.append('QUOTE_PRICE_INVALID')
 if at>_ns(record.received_at):checks.append('QUOTE_FUTURE')
 if now-at>30*_NS or now-_ns(record.request.to_payload()['created_at'])>30*_NS:checks.append('QUOTE_STALE')
 if any(k in q and q[k]!='V' for k in ('bx','ax')):checks.append('QUOTE_VENUE_MISMATCH')
 reasons.extend(checks);result['valid']=not checks;return result


def _decimal_text(d):
 s=format(d,'f');return (s.rstrip('0').rstrip('.') if '.' in s else s) if d else '0'


def _history(plan,records,reasons):
 p=plan.to_payload();_need(len(records)<=8)
 expected={_ns(t):d for t,d in zip(p['daily_labels'],p['history_sessions'])};rows={};token=None;tokens=set();last_at=-1;last_received=-1;terminal=False;frozen=True;http_ok=True
 for record in records:
  request=record.request.to_payload();_need(not terminal and request['parameters'].get('page_token')==token)
  _need(_ns(request['created_at'])>=last_received);last_received=_ns(record.received_at)
  if last_received>_ns(p['history_cutoff_at']):frozen=False
  if record.status!=200:
   http_ok=False;terminal=True;continue
  body=_body(record.raw);_fields(body,('bars','next_page_token'));bars=body['bars']
  _need(type(bars) is dict and set(bars)<=set([p['symbol']]))
  page=bars.get(p['symbol'],[]);_need(type(page) is list and len(page)<=100)
  for row in page:
   _fields(row,('t','o','h','l','c','v'));at=_ns(row['t'])
   _need(at in expected and at>last_at);last_at=at
   values={k:_numeric(row[k],positive=True) for k in ('o','h','l','c')};volume=_numeric(row['v'])
   _need(values['l']<=min(values['o'],values['c'])<=max(values['o'],values['c'])<=values['h'])
   if row.get('n') is not None:_numeric(row['n'],integer=True)
   if row.get('vw') is not None:_numeric(row['vw'],positive=True)
   rows[expected[at]]=(values['c'],volume);_need(len(rows)<=252)
  token=_token(body['next_page_token']);terminal=token is None
  if token is not None:_need(token not in tokens);tokens.add(token)
 missing=[d for d in p['history_sessions'] if d not in rows]
 complete=bool(records) and terminal and http_ok and not missing and frozen
 if not records:reasons.append('HISTORY_MISSING')
 if not http_ok:reasons.append('HISTORY_HTTP_REFUSED')
 if not terminal:reasons.append('HISTORY_PAGINATION_INCOMPLETE')
 if missing:reasons.append('HISTORY_ROWS_MISSING')
 if not frozen:reasons.append('HISTORY_AFTER_CUTOFF')
 prior=rows.get(p['history_sessions'][-1]);window=p['history_sessions'][-20:];mean=cap=None
 if all(d in rows for d in window):
  context=Context(prec=80,flags=[],traps=[InvalidOperation,DivisionByZero,Overflow,Inexact])
  with localcontext(context):
   average=sum((rows[d][0]*rows[d][1] for d in window),Decimal(0))/20
   cap=_decimal_text(min(Decimal(2000),average/100));mean=_decimal_text(average)
  if average<1000000:reasons.append('LIQUIDITY_BELOW_MINIMUM')
 else:reasons.append('LIQUIDITY_WINDOW_INCOMPLETE')
 if prior is None or prior[0]<5:reasons.append('PRIOR_RAW_PRICE_BELOW_MINIMUM_OR_MISSING')
 return dict(complete=complete,frozen_before_cutoff=frozen,terminal_pagination=terminal and http_ok,observed_sessions=len(rows),missing_sessions=missing,
  prior_session=p['history_sessions'][-1],prior_raw_close=None if prior is None else _decimal_text(prior[0]),mean_dollar_volume=mean,intent_notional_cap=cap)


def _result(plan,observations,as_of):
 evidence=_evidence(plan,observations);p=plan.to_payload();now=_ns(as_of);_need(_day(as_of)==p['session_date'])
 groups={k:[] for k in ('ASSET','QUOTE','HISTORY')}
 for r in observations:
  _need(_ns(r.received_at)<=now);groups[r.request.to_payload()['operation']].append(r)
 _need(len(groups['ASSET'])<=1 and len(groups['QUOTE'])<=1)
 reasons=[]
 asset=_asset(groups['ASSET'][0] if groups['ASSET'] else None,p['symbol'],now,reasons)
 quote=_quote(groups['QUOTE'][0] if groups['QUOTE'] else None,p['symbol'],now,reasons)
 history=_history(plan,groups['HISTORY'],reasons);observed=not reasons
 return dict(version=1,record_type='OperationalMarketInputDiagnostic',scope='PREPARATION_ONLY',plan_sha256=plan.sha256,evidence_sha256=_sha(evidence),
  project_id=p['project_id'],account_alias=p['account_alias'],symbol=p['symbol'],feed=p['feed'],session_date=p['session_date'],as_of=as_of,
  status='BLOCKED',asset=asset,quote=quote,history=history,observed_conditions_met=observed,deficiencies=sorted(set(reasons)|set(_MISSING)),
  native_provenance='UNVERIFIED',feed_entitlement='UNVERIFIED',historical_availability='UNVERIFIED',transport_authorized=False,financial_accepted=False,research_eligible=False)


@dataclass(frozen=True,slots=True,repr=False)
class OperationalMarketInputs:
 plan:OperationalMarketPlan
 observations:tuple=field(repr=False)
 as_of:str
 content:bytes
 def __post_init__(self):
  _need(type(self.content) is bytes and len(self.content)<=65536 and canonical(_result(self.plan,self.observations,self.as_of))==self.content)
 def __repr__(self):return '<OperationalMarketInputs unverified provenance>'
 def to_payload(self):return json.loads(self.content)
 def evidence_bytes(self):return _evidence(self.plan,self.observations)
 @property
 def evidence_sha256(self):return _sha(self.evidence_bytes())


def qualify_market_inputs(plan,observations,*,as_of):
 return OperationalMarketInputs(plan,observations,as_of,canonical(_result(plan,observations,as_of)))
