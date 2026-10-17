"""Exact observed USD fee cash effects. No complete billing or liability claim."""
from dataclasses import dataclass,field
from datetime import date
from decimal import Context,Decimal,DecimalException,DivisionByZero,Inexact
from decimal import InvalidOperation,Overflow,ROUND_HALF_EVEN,Rounded,localcontext
import json,math,re

from .data.encoding import canonical
from .domain import ContractError
from .paper_activity_records import _token
from .paper_reconciliation import validate_fill_history,_decimal_text
from .runtime.errors import RuntimeRefused
from .runtime.paper_read_packet import _nanoseconds

_FIELDS={'project_id','account_alias','opening_cash','current_cash','attempts','orders','positions','activities'}
_COLLECTIONS={'attempts':256,'orders':200,'positions':64,'activities':200}
_FEE_FIELDS={'id','activity_type','date','net_amount'}
_LIMIT=1024**2
_INVALID=(ContractError,DecimalException,ValueError,TypeError,KeyError,AttributeError,
          OverflowError,RecursionError,UnicodeError)


def _need(value):
    if not value:raise RuntimeRefused('PAPER_POSTED_FEES_UNVERIFIED')


def _arguments_json(raw):
    _need(type(raw) is bytes and 0<len(raw)<=_LIMIT)
    def pairs(items):
        result={}
        for key,value in items:
            _need(key not in result);result[key]=value
        return result
    def constant(value):
        _need(False)
    def depth(value,level=0):
        _need(level<=32)
        if type(value) is dict:
            for item in value.values():depth(item,level+1)
        elif type(value) is list:
            for item in value:depth(item,level+1)
        elif type(value) is float:_need(math.isfinite(value))
    value=json.loads(raw.decode('utf-8'),object_pairs_hook=pairs,parse_constant=constant)
    depth(value)
    return value


def _date(value):
    _need(type(value) is str)
    if re.fullmatch(r'\d{4}-\d{2}-\d{2}',value):
        parsed=date.fromisoformat(value)
        _need(parsed.isoformat()==value)
    else:
        _need(re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?Z',value) is not None)
        _nanoseconds(value);parsed=date.fromisoformat(value[:10])
    _need(2000<=parsed.year<=2100)


def _amount(row):
    _need(_FEE_FIELDS<=set(row)<=_FEE_FIELDS|{'description'} and row['activity_type']=='FEE')
    _token(row['id']);_date(row['date'])
    if 'description' in row:
        _need(type(row['description']) is str and len(row['description'].encode('utf-8'))<=1024)
    value=row['net_amount']
    _need(type(value) is str and re.fullmatch(r'-?(?:0|[1-9][0-9]{0,8})(?:\.[0-9]{1,12})?',value) is not None)
    amount=Decimal(value);_need(abs(amount)<=100000000)
    return amount


def _calculate(values):
    _need(type(values) is dict and set(values)==_FIELDS)
    for key,bound in _COLLECTIONS.items():
        _need(type(values[key]) is tuple and len(values[key])<=bound)
    # Check every row and every original byte before separating fills and fees.
    _need(len(canonical(values))<=_LIMIT)
    seen=set();fills=[];fees=[]
    for row in values['activities']:
        _need(type(row) is dict)
        identity=_token(row.get('id'));_need(identity not in seen);seen.add(identity)
        kind=row.get('activity_type');_need(kind in {'FILL','FEE'})
        (fills if kind=='FILL' else fees).append(row)
    original=validate_fill_history(**dict(values,activities=tuple(fills)))
    debit=credit=Decimal(0);debit_count=credit_count=zero_count=0
    for row in fees:
        amount=_amount(row)
        if amount<0:debit-=amount;debit_count+=1
        elif amount>0:credit+=amount;credit_count+=1
        else:zero_count+=1
    effect=credit-debit
    fill_cash=Decimal(original['expected_cash']);expected=fill_cash+effect
    observed=Decimal(values['current_cash']);difference=observed-expected
    return dict(version=1,record_type='PaperPostedFeeCalculation',scope='UNQUALIFIED_POSTED_CASH_CALCULATION',
        status='BLOCKED',opening_cash=values['opening_cash'],observed_cash=values['current_cash'],
        fill_expected_cash=original['expected_cash'],expected_cash=_decimal_text(expected),
        unadjusted_cash_difference=original['cash_difference'],cash_difference=_decimal_text(difference),
        calculation_matches=abs(difference)<=Decimal('0.01'),posted_debits=_decimal_text(debit),
        posted_credits=_decimal_text(credit),posted_cash_effect=_decimal_text(effect),
        posted_fee_count=len(fees),posted_debit_count=debit_count,posted_credit_count=credit_count,
        posted_zero_count=zero_count,posted_fees=[dict(row) for row in fees],
        owned_positions=original['owned_positions'],remaining_quantities=original['remaining_quantities'],
        order_count=original['order_count'],fill_count=original['fill_count'],actual_billed_fee=None,actual_flat=None,
        deficiencies=['FEE_POSTING_INTERVAL_UNVERIFIED','FEE_LIABILITIES_UNVERIFIED','FEE_REVERSALS_UNVERIFIED',
            'FEE_ACCOUNT_DAY_COVERAGE_UNVERIFIED','FEE_ORDER_LIFETIME_COVERAGE_UNVERIFIED',
            'FEE_ACCOUNT_APPLICABILITY_UNVERIFIED','ACTION_EVIDENCE_UNVERIFIED','CURRENT_BINDINGS_UNVERIFIED',
            'POSITION_COST_RECONSTRUCTION_UNVERIFIED','NATIVE_PROVENANCE_UNVERIFIED'],
        financial_accepted=False,transport_authorized=False)


def _checked(values):
    try:
        context=Context(prec=160,rounding=ROUND_HALF_EVEN,Emin=-999999,Emax=999999,
            capitals=1,clamp=0,flags=[],traps=[InvalidOperation,DivisionByZero,Overflow,Inexact,Rounded])
        with localcontext(context):
            result=canonical(_calculate(values));_need(len(result)<=_LIMIT)
            return result
    except _INVALID:
        raise RuntimeRefused('PAPER_POSTED_FEES_UNVERIFIED') from None


@dataclass(frozen=True,slots=True,repr=False)
class PostedFeeCalculation:
    arguments:bytes=field(repr=False)
    content:bytes=field(repr=False)

    def __post_init__(self):
        try:
            _need(type(self.arguments) is bytes and len(self.arguments)<=_LIMIT)
            _need(type(self.content) is bytes and len(self.content)<=_LIMIT)
            values=_arguments_json(self.arguments)
            _need(type(values) is dict and set(values)==_FIELDS and canonical(values)==self.arguments)
            for key in _COLLECTIONS:
                _need(type(values[key]) is list);values[key]=tuple(values[key])
            _need(_checked(values)==self.content)
        except _INVALID:
            raise RuntimeRefused('PAPER_POSTED_FEES_UNVERIFIED') from None

    def __repr__(self):return '<PostedFeeCalculation private amounts redacted>'
    def to_payload(self):
        self.__post_init__()
        return json.loads(self.content)


def calculate_posted_fees(*,project_id,account_alias,opening_cash,current_cash,
                          attempts,orders,positions,activities):
    values=dict(project_id=project_id,account_alias=account_alias,opening_cash=opening_cash,
        current_cash=current_cash,attempts=attempts,orders=orders,positions=positions,activities=activities)
    content=_checked(values)
    return PostedFeeCalculation(canonical(values),content)
