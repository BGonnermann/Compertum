"""Local fixture arithmetic. A calculation never supplies source or send authority."""
from dataclasses import dataclass,field
from decimal import Context,Decimal,Inexact,InvalidOperation,Overflow,Rounded,localcontext
import hashlib,json
from .data.encoding import canonical
from .domain import ContractError
from .paper_contracts import identifier,number,read_request,timestamp
from .paper_fixture_plans import PaperFixtureInputs,build_fixture_proposal
from .paper_portfolio import PaperPortfolioBundle,TERMINAL,build_portfolio_bundle
from .paper_responses import PaperResponse,parse_response
from .runtime.errors import RuntimeRefused
from .runtime.paper_native_intent_terms import exact_terms
from .runtime._winhttp_order import _wire

_INVALID=(ContractError,ValueError,TypeError,KeyError,AttributeError,OverflowError,RecursionError,UnicodeError,InvalidOperation,Inexact,Rounded)
def _need(value):
 if not value:raise RuntimeRefused('FIXTURE_RISK_UNVERIFIED')
def _text(value):
 value=format(value,'f');return value.rstrip('0').rstrip('.') if '.' in value else value
def _response(value):
 if value is None:return None
 _need(type(value) is PaperResponse);value.__post_init__()
 return dict(request=json.loads(value.request.content),origin=value.origin,account_id=value.account_id,
  status=value.status,raw=value.raw.decode('utf-8'),received_at=value.received_at)
def _restore(value):
 if value is None:return None
 _need(type(value) is dict and set(value)=={'request','origin','account_id','status','raw','received_at'})
 return parse_response(read_request(canonical(value['request'])),origin=value['origin'],account_id=value['account_id'],
  status=value['status'],raw=value['raw'].encode('utf-8'),received_at=value['received_at'])

def _arguments(*,portfolio,inputs,purpose,terms,intent_id,now,outstanding_fees):
 _need(type(portfolio) is PaperPortfolioBundle);portfolio.__post_init__()
 _need(inputs is None or type(inputs) is PaperFixtureInputs)
 if inputs is not None:inputs.__post_init__()
 return dict(portfolio=dict(account=_response(portfolio.account),positions=_response(portfolio.positions),
  orders=[_response(item) for item in portfolio.orders],clock=_response(portfolio.clock),calendar=_response(portfolio.calendar),as_of=portfolio.as_of),
  inputs=None if inputs is None else json.loads(inputs.content),purpose=purpose,terms=terms,intent_id=intent_id,now=now,outstanding_fees=outstanding_fees)

def _calculate(values):
 _need(set(values)=={'portfolio','inputs','purpose','terms','intent_id','now','outstanding_fees'})
 purpose=values['purpose'];_need(type(purpose) is str and purpose in {'FIXTURE_BUY','FIXTURE_RESTING_BUY','CANCEL','CLOSE_LONG'})
 terms=values['terms'];_need(exact_terms(purpose,terms,stored=True)==terms)
 original=values['portfolio'];_need(set(original)=={'account','positions','orders','clock','calendar','as_of'})
 account,positions,clock,calendar=(_restore(original[key]) for key in ('account','positions','clock','calendar'))
 orders=tuple(_restore(item) for item in original['orders']);now=values['now'];timestamp(now);identifier(values['intent_id'])
 _need(account is not None);cash=number(account.to_payload()['observation']['cash'])
 fees=number(values['outstanding_fees']);_need(fees>=0)
 available=cash-fees
 buying=purpose in {'FIXTURE_BUY','FIXTURE_RESTING_BUY'}
 if buying:_need(available>=0)
 # This temporary arithmetic projection does not replace the original observation.
 raw=json.loads(account.raw);raw['cash']=_text(available if buying else cash)
 adjusted=parse_response(account.request,origin=account.origin,account_id=account.account_id,status=account.status,
  raw=canonical(raw),received_at=account.received_at)
 if purpose=='CANCEL':clock=calendar=None
 portfolio=build_portfolio_bundle(account=adjusted,positions=positions,orders=orders,clock=clock,calendar=calendar,as_of=now)
 observed=portfolio.to_payload();symbol=terms['symbol'];children=[];residual=None;planned=exposure=None
 if purpose=='CANCEL':
  _need(set(observed['deficiencies'])<={'CLOCK_MISSING','CALENDAR_MISSING'})
  target=[row for row in observed['orders'] if row['id']==terms['order_id'] and row['symbol']==symbol and row['status'] not in TERMINAL]
  _need(len(target)==1);operation='CANCEL_ORDER';parameters={'order_id':terms['order_id']};body=None
  proposal_sha=hashlib.sha256(canonical(dict(portfolio=observed,terms=terms))).hexdigest()
 else:
  _need(values['inputs'] is not None);inputs=PaperFixtureInputs(canonical(values['inputs']))
  kind={'FIXTURE_BUY':'OPEN_BUY','FIXTURE_RESTING_BUY':'RESTING_BUY','CLOSE_LONG':'CLOSE_LONG'}[purpose]
  proposal=build_fixture_proposal(portfolio=portfolio,inputs=inputs,kind=kind,symbol=symbol,intent_id=values['intent_id'],now=now,
   limit_price=terms.get('limit_price'));value=proposal.to_payload();_need(value['requests'] and value['proposal_status']!='BLOCKED_RESIDUAL')
  request=value['requests'][0];operation=request['operation'];parameters=request['parameters'];body=dict(request['body'])
  planned=value['planned_notional'];exposure=value['projected_exposure'];proposal_sha=proposal.sha256
  if purpose=='CLOSE_LONG':
   held=[row for row in observed['positions'] if row['symbol']==symbol];_need(len(held)==1 and number(held[0]['qty'])==terms['quantity'])
   children=terms['children'];quantity=min(int(body['qty']),children[0]['maximum_quantity'])
   _need(quantity>0);notional=Decimal(value['quote']['ask'])*Decimal(inputs.to_payload()['adverse_buy_buffer'])*quantity
   _need(notional<=number(children[0]['notional_cap'],positive=True))
   body['qty']=str(quantity);planned=_text(notional);residual=terms['quantity']-quantity
 method,target,_=_wire(operation,parameters,body)
 return dict(version=1,record_type='FixtureRiskCalculation',scope='UNQUALIFIED_LOCAL_RISK_CALCULATION',source_qualified=False,
  financial_accepted=False,transport_authorized=False,purpose=purpose,terms=terms,proposal_sha256=proposal_sha,
  original_cash=_text(cash),outstanding_fees=_text(fees),available_cash=_text(available),planned_notional=planned,
  projected_exposure=exposure,children=children,residual_quantity=residual,
  request=dict(operation=operation,method=method,target=target,parameters=parameters,body=body))

def _checked(values):
 try:
  _need(len(canonical(values))<=1024**2)
  with localcontext(Context(prec=160,traps=[InvalidOperation,Overflow,Inexact,Rounded])):return canonical(_calculate(values))
 except _INVALID:raise RuntimeRefused('FIXTURE_RISK_UNVERIFIED') from None

@dataclass(frozen=True,slots=True,repr=False)
class FixtureRiskCalculation:
 arguments:bytes=field(repr=False)
 content:bytes=field(repr=False)
 def __post_init__(self):
  try:
   _need(type(self.arguments) is bytes and type(self.content) is bytes and len(self.arguments)<=1024**2)
   values=json.loads(self.arguments);_need(canonical(values)==self.arguments and _checked(values)==self.content)
  except _INVALID:raise RuntimeRefused('FIXTURE_RISK_UNVERIFIED') from None
 def __repr__(self):return '<FixtureRiskCalculation private values redacted>'
 def __reduce_ex__(self,protocol):raise RuntimeRefused('FIXTURE_RISK_SERIALIZATION_FORBIDDEN')
 def to_payload(self):self.__post_init__();return json.loads(self.content)

def calculate_fixture_risk(**values):
 try:
  arguments=canonical(_arguments(**values));return FixtureRiskCalculation(arguments,_checked(json.loads(arguments)))
 except _INVALID:raise RuntimeRefused('FIXTURE_RISK_UNVERIFIED') from None
