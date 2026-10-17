"""Unqualified local economic arithmetic. Native source authority is separate."""
from dataclasses import dataclass,field
from decimal import Context,Decimal,DecimalException,Inexact,InvalidOperation,Overflow,Rounded,localcontext
import hashlib,json,re

from .data.encoding import canonical
from .domain import ContractError
from .paper_contracts import identifier,utc
from .paper_activity_records import _token
from .paper_posted_fees import calculate_posted_fees,_arguments_json
from .paper_reconciliation import _decimal_text
from .runtime.errors import RuntimeRefused
from .runtime.paper_read_packet import _nanoseconds

_FIELDS={'originals','ledger','opening_sha256','history_sha256','asset_id','symbol','required_after','required_until'}
_LEDGER={'version','purpose','project_id','account_alias','opening_sha256','history_sha256','asset_id','symbol',
         'opening_cash','covered_after','covered_until','fee_rules','action_events','events','event_count','ledger_head_sha256'}
_ENVELOPE={'events','event_count','ledger_head_sha256','opening_sha256','history_sha256','covered_until'}
_COMMON={'event_id','kind','at','sequence','previous_sha256','sha256','amount'}
_INVALID=(RuntimeRefused,ContractError,DecimalException,ValueError,TypeError,KeyError,AttributeError,
          OverflowError,RecursionError,UnicodeError)

def _need(value):
    if not value:raise RuntimeRefused('FIXTURE_ECONOMICS_UNVERIFIED')

def _sha(value):return hashlib.sha256(canonical(value)).hexdigest()

def _hash(value):
    _need(type(value) is str and re.fullmatch('[0-9a-f]{64}',value) is not None)

def _id(value):
    _need(type(value) is str and re.fullmatch('[A-Za-z0-9._:-]{1,128}',value) is not None)
    return value

def _when(value):
    _need(type(value) is str and value==utc(value));return _nanoseconds(value)

def _amount(value,*,zero=False):
    _need(type(value) is str and re.fullmatch(r'(?:0|[1-9][0-9]{0,8})(?:\.[0-9]{1,12})?',value) is not None)
    amount=Decimal(value);_need((amount>=0 if zero else amount>0) and amount<=100000000)
    return amount

def _calculate(values):
    _need(type(values) is dict and set(values)==_FIELDS)
    ledger=values['ledger'];originals=values['originals']
    _need(type(ledger) is dict and set(ledger)==_LEDGER and len(canonical(ledger))<=128*1024)
    _need(type(ledger['version']) is int and ledger['version']==1 and ledger['purpose']=='CONTROLLED_LOCAL_ECONOMICS')
    for key in ('opening_sha256','history_sha256'):
        _hash(values[key]);_need(ledger[key]==values[key])
    identifier(values['asset_id'])
    _need(type(values['symbol']) is str and re.fullmatch('[A-Z][A-Z0-9.]{0,9}',values['symbol']) is not None)
    _need(all(ledger[key]==values[key] for key in ('asset_id','symbol')))
    _need(all(ledger[key]==originals[key] for key in ('project_id','account_alias','opening_cash')))
    after=_when(values['required_after']);until=_when(values['required_until'])
    _need(_when(ledger['covered_after'])<=after<until==_when(ledger['covered_until']))
    _need(type(ledger['action_events']) is list and ledger['action_events']==[])
    rules=ledger['fee_rules'];_need(type(rules) is list and 1<=len(rules)<=8)
    rates={};zero_rules=0
    for rule in rules:
        _need(type(rule) is dict and set(rule)=={'rule_id','kind','rate','currency'})
        name=_id(rule['rule_id']);_need(name not in rates and rule['currency']=='USD')
        amount=_amount(rule['rate'],zero=True)
        if rule['kind']=='ZERO_TRANSACTION_FEES':_need(amount==0);zero_rules+=1
        else:_need(rule['kind']=='FIXED_USD_PER_EVENT' and amount>0)
        rates[name]=(rule['kind'],amount)
    _need(zero_rules==1)
    posted=calculate_posted_fees(**originals).to_payload()
    for row in (*originals['orders'],*originals['positions']):
        _need(row['asset_id']==values['asset_id'] and row['symbol']==values['symbol'])
    for row in originals['activities']:
        if row['activity_type']=='FILL':_need(row['symbol']==values['symbol'])
    for row in originals['attempts']:
        request=row['intent']['request']
        if request['operation']!='CANCEL_ORDER':_need(request['body']['symbol']==values['symbol'])
    fee_rows={row['id']:Decimal(row['net_amount']) for row in posted['posted_fees']}
    events=ledger['events'];_need(type(events) is list and len(events)<=128)
    _need(type(ledger['event_count']) is int and ledger['event_count']==len(events))
    head=_sha({k:v for k,v in ledger.items() if k not in _ENVELOPE})
    seen={};balances={};payments={};reversed_ids=set();cancelled=set();used_cash=set()
    paid=Decimal(0);credits=Decimal(0);previous_time=after
    def cash(identity,amount):
        identity=_token(identity);_need(identity in fee_rows and identity not in used_cash and fee_rows[identity]==amount)
        used_cash.add(identity)
    for sequence,event in enumerate(events,1):
        _need(type(event) is dict)
        identity=_id(event['event_id']);_need(identity not in seen)
        _need(type(event['sequence']) is int and event['sequence']==sequence and event['previous_sha256']==head)
        _hash(event['sha256']);head=_sha({k:v for k,v in event.items() if k!='sha256'})
        _need(event['sha256']==head)
        at=_when(event['at']);_need(previous_time<=at<=until);previous_time=at
        amount=_amount(event['amount']);kind=event['kind']
        if kind=='ACCRUAL':
            _need(set(event)==_COMMON|{'rule_id'} and event['rule_id'] in rates)
            rule,rated=rates[event['rule_id']];_need(rule=='FIXED_USD_PER_EVENT' and amount==rated)
            balances[identity]=amount
        elif kind=='PAYMENT':
            _need(set(event)==_COMMON|{'accrual_id','activity_id'})
            accrual=event['accrual_id'];_need(type(accrual) is str and accrual in balances and accrual not in cancelled and amount<=balances[accrual])
            cash(event['activity_id'],-amount);balances[accrual]-=amount;payments[identity]=(accrual,amount);paid+=amount
        elif kind=='REVERSAL':
            _need(set(event)==_COMMON|{'event_id_reversed','activity_id'})
            original=event['event_id_reversed'];_need(type(original) is str and original in seen and original not in reversed_ids)
            first=seen[original];_need(amount==_amount(first['amount']))
            if first['kind']=='PAYMENT':
                accrual,paid_amount=payments[original];_need(accrual not in cancelled and paid_amount==amount)
                cash(event['activity_id'],amount);balances[accrual]+=amount;paid-=amount
            else:
                _need(first['kind']=='ACCRUAL' and event['activity_id'] is None and balances[original]==amount)
                balances[original]=Decimal(0);cancelled.add(original)
            reversed_ids.add(original)
        elif kind=='UNLINKED_CREDIT':
            _need(set(event)==_COMMON|{'activity_id'});cash(event['activity_id'],amount);credits+=amount
        else:_need(False)
        seen[identity]=event
    _need(ledger['ledger_head_sha256']==head and used_cash==set(fee_rows))
    return dict(version=1,record_type='FixtureEconomicCalculation',scope='UNQUALIFIED_LOCAL_ECONOMIC_CALCULATION',
        source_qualified=False,financial_accepted=False,transport_authorized=False,
        outstanding_fees=_decimal_text(sum(balances.values(),Decimal(0))),paid_fees=_decimal_text(paid),
        unlinked_credits=_decimal_text(credits),observed_cash=posted['observed_cash'],cash_matches=posted['calculation_matches'],
        local_action_calendar_empty=True,event_count=len(events),ledger_head_sha256=head,
        unverified_requirements=['ORIGINAL_CONTROLLED_SOURCE_UNVERIFIED','CURRENT_NATIVE_BINDINGS_UNVERIFIED',
          'ACTUAL_BILLING_UNVERIFIED','ACTUAL_ACTION_COVERAGE_UNVERIFIED','RISK_UNVERIFIED','DURABLE_DISPATCH_UNVERIFIED'])

def _checked(values):
    try:
        _need(len(canonical(values))<=1024**2)
        context=Context(prec=160,traps=[InvalidOperation,Overflow,Inexact,Rounded])
        with localcontext(context):return canonical(_calculate(values))
    except _INVALID:raise RuntimeRefused('FIXTURE_ECONOMICS_UNVERIFIED') from None

@dataclass(frozen=True,slots=True,repr=False)
class FixtureEconomicCalculation:
    arguments:bytes=field(repr=False)
    content:bytes=field(repr=False)
    def __post_init__(self):
        try:
            _need(type(self.arguments) is bytes and type(self.content) is bytes and len(self.content)<=1024**2)
            values=_arguments_json(self.arguments)
            _need(type(values) is dict and set(values)==_FIELDS and canonical(values)==self.arguments)
            for key in ('attempts','orders','positions','activities'):
                _need(type(values['originals'][key]) is list);values['originals'][key]=tuple(values['originals'][key])
            _need(_checked(values)==self.content)
        except _INVALID:raise RuntimeRefused('FIXTURE_ECONOMICS_UNVERIFIED') from None
    def __repr__(self):return '<FixtureEconomicCalculation private values redacted>'
    def to_payload(self):self.__post_init__();return json.loads(self.content)

def calculate_fixture_economics(*,originals,ledger,opening_sha256,history_sha256,asset_id,symbol,required_after,required_until):
    values=dict(originals=originals,ledger=ledger,opening_sha256=opening_sha256,history_sha256=history_sha256,
                asset_id=asset_id,symbol=symbol,required_after=required_after,required_until=required_until)
    try:return FixtureEconomicCalculation(canonical(values),_checked(values))
    except _INVALID:raise RuntimeRefused('FIXTURE_ECONOMICS_UNVERIFIED') from None
