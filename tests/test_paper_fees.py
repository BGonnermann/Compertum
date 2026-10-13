"""Declared fee arithmetic cannot establish actual fees or account applicability."""
from dataclasses import replace
from decimal import Decimal, localcontext, ROUND_DOWN, Inexact, Rounded
from uuid import UUID
import hashlib,json
import pytest
from compertum.domain import ContractError
from compertum.data.encoding import canonical
from compertum.paper_fees import FeeSource, FeeSchedule, FeeBatch, FeeCalculation, calculate_fees


def uid(n):return str(UUID(int=n))
def source(raw=b'Invented fee source'):
 return FeeSource(raw,'https://example.invalid/fees','text/plain','2026-10-01T12:00:00Z')
def rule(code='SEC',**edit):
 v=dict(component=code,charged_sides=['SELL'],basis='PRINCIPAL',rate='0.0000206',minimum='0.00',cap=None,limit_unit='ACCOUNT_DAY',rounding_unit='ACCOUNT_DAY',rounding='CEILING')
 if 'aggregation' in edit:
  unit=edit.pop('aggregation');edit.update(limit_unit=unit,rounding_unit=unit)
 v.update(edit);return v
def schedule(rules=None,**edit):
 src=source()
 v=dict(version=1,schedule_id=uid(1),source_sha256=[src.sha256],declared_from='2026-10-01',declared_until='2026-11-01',currency='USD',product='NMS_EQUITY',rules=rules if rules is not None else [rule(),rule('TAF',basis='SHARES',rate='0'),rule('CAT',charged_sides=['BUY','SELL'],basis='SHARES',rate='0.000003'),rule('COMMISSION',charged_sides=['BUY','SELL'],basis='PRINCIPAL',rate='0')])
 v.update(edit);return FeeSchedule((src,),canonical(v))
def fill(n=1,**edit):
 v=dict(execution_id=uid(100+n),order_id=uid(200+n),symbol='AAPL',side='SELL',executed_at='2026-10-09T13:35:00.123456789Z',quantity='1',price='100')
 v.update(edit);return v
def batch(fills=None,**edit):
 v=dict(version=1,project_id='a'*64,account_alias='paper-primary',execution_date='2026-10-09',currency='USD',product='NMS_EQUITY',executions=fills if fills is not None else [fill()])
 v.update(edit);return FeeBatch(canonical(v))
def result(b=None,ss=None):return calculate_fees(b or batch(),ss if ss is not None else (schedule(),))
def payload(b=None,ss=None):return json.loads(result(b,ss).content)
def component(v,code):return next(c for c in v['components'] if c['component']==code)


def test_source_and_declared_hand_fee_never_imply_actual_acceptance():
 s=schedule();b=batch();r=calculate_fees(b,(s,));v=json.loads(r.content)
 assert v['declared_batch_fee']=='0.02' and v['calculation_status']=='DECLARED_BATCH_CALCULATED'
 assert v['actual_billed_fee'] is None and v['status']=='BLOCKED'
 assert v['account_applicability']=='UNVERIFIED' and v['daily_fill_completeness']=='UNVERIFIED'
 assert v['financial_accepted'] is False and v['transport_authorized'] is False
 assert v['batch_sha256']==b.sha256 and v['schedule_sha256']==[s.sha256]
 assert s.sources[0].raw==b'Invented fee source' and s.sources[0].body_sha256==hashlib.sha256(s.sources[0].raw).hexdigest()
 assert s.sources[0].raw.decode() not in repr(s.sources[0])
 assert result()==result()


def test_missing_schedules_are_unknown_not_zero():
 v=payload(ss=())
 assert v['declared_batch_fee'] is None and v['calculation_status']=='INCOMPLETE_DECLARATIONS'
 assert len(v['components'])==4 and all(c['status']=='MISSING_EFFECTIVE_RULE' for c in v['components'])


@pytest.mark.parametrize('unit,expected',[('FILL','0.03'),('ORDER','0.02'),('ACCOUNT_DAY','0.01')])
def test_partial_fill_aggregation_is_explicit(unit,expected):
 s=schedule([rule(rate='0.00001',aggregation=unit),rule('TAF',rate='0'),rule('CAT',rate='0'),rule('COMMISSION',rate='0')])
 b=batch([fill(1),fill(2,order_id=uid(201)),fill(3)])
 assert component(payload(b,(s,)),'SEC')['declared_fee']==expected


def test_account_day_includes_both_sides_symbols_and_fractional_quantity():
 s=schedule([rule('CAT',charged_sides=['BUY','SELL'],basis='SHARES',rate='0.004')])
 v=payload(batch([fill(1,quantity='0.125',symbol='AAPL',side='BUY'),fill(2,quantity='0.125',symbol='MSFT',side='SELL')]),(s,))
 c=component(v,'CAT');assert c['declared_fee']=='0.01' and len(c['groups'])==1
 assert c['groups'][0]['raw_fee']=='0.001' and c['groups'][0]['quantity']=='0.25'
 assert v['declared_batch_fee'] is None


@pytest.mark.parametrize('rounding,expected',[('CEILING','0.01'),('HALF_UP','0.00')])
def test_declared_rounding_applied_once_after_aggregation(rounding,expected):
 s=schedule([rule(rate='0.00001',rounding=rounding)])
 assert component(payload(ss=(s,)),'SEC')['declared_fee']==expected


@pytest.mark.parametrize('rate,minimum,cap,expected',[('0.000001','0.02',None,'0.02'),('1','0.00','0.03','0.03'),('0','0.00',None,'0.00')])
def test_minimum_cap_and_explicit_zero(rate,minimum,cap,expected):
 assert component(payload(ss=(schedule([rule(rate=rate,minimum=minimum,cap=cap)]),)),'SEC')['declared_fee']==expected


def test_buy_is_explicitly_not_charged_but_cat_is_calculated():
 v=payload(batch([fill(side='BUY')]))
 assert component(v,'SEC')['declared_fee']=='0.00' and component(v,'SEC')['groups']==[]
 assert component(v,'CAT')['declared_fee']=='0.01'
 assert v['declared_batch_fee']=='0.01'


@pytest.mark.parametrize('start,end,expected',[('2026-10-09','2026-10-10',True),('2026-10-10','2026-10-11',False),('2026-10-01','2026-10-09',False)])
def test_declared_interval_is_start_inclusive_end_exclusive(start,end,expected):
 v=payload(ss=(schedule(declared_from=start,declared_until=end),))
 assert (v['declared_batch_fee'] is not None)==expected


def test_overlapping_schedules_conflict_even_when_rates_match():
 a=schedule();b=schedule(schedule_id=uid(2));v=payload(ss=(a,b))
 assert v['declared_batch_fee'] is None
 assert all(c['status']=='AMBIGUOUS_EFFECTIVE_RULE' for c in v['components'])


def test_disjoint_intervals_do_not_conflict_and_order_is_canonical():
 a=schedule(declared_until='2026-10-09');b=schedule(schedule_id=uid(2),declared_from='2026-10-09')
 assert result(ss=(a,b))==result(ss=(b,a))
 assert payload(ss=(a,b))['declared_batch_fee']=='0.02'


def test_decimal_context_cannot_change_result_or_rounding():
 expected=result()
 with localcontext() as ctx:
  ctx.prec=2;ctx.rounding=ROUND_DOWN;ctx.traps[Inexact]=True;ctx.traps[Rounded]=True
  assert result()==expected


@pytest.mark.parametrize('field,value',[('rate',True),('rate',1.2),('rate','1e-5'),('rate','NaN'),('rate','-1'),('rate','0.0000000000001'),('rate','100000001'),('minimum','0.001'),('cap','0.001'),('cap','-1'),('charged_sides',[]),('charged_sides',['SELL','SELL']),('basis','TOTAL'),('rounding_unit','UNSPECIFIED'),('rounding','INHERITED'),('component','OTHER')])
def test_malformed_rules_refused(field,value):
 with pytest.raises(ContractError):schedule([rule(**{field:value})])


def test_cap_below_minimum_and_duplicate_component_refused():
 with pytest.raises(ContractError):schedule([rule(minimum='0.02',cap='0.01')])
 with pytest.raises(ContractError):schedule([rule(),rule()])


@pytest.mark.parametrize('field,value',[('quantity',True),('quantity','0'),('quantity','-1'),('price','NaN'),('price','1e9'),('price','0'),('symbol','FOREIGN'),('side','SHORT'),('executed_at','2026-10-10T13:35:00Z'),('execution_id',uid(0)),('order_id','secret')])
def test_invalid_execution_refused(field,value):
 with pytest.raises(ContractError):batch([fill(**{field:value})])


def test_duplicate_execution_and_mixed_order_identity_refused():
 with pytest.raises(ContractError):batch([fill(),fill()])
 with pytest.raises(ContractError):batch([fill(),fill(2,order_id=uid(201),symbol='MSFT')])
 with pytest.raises(ContractError):batch([fill(),fill(2,order_id=uid(201),side='BUY')])


def test_empty_batch_still_does_not_prove_daily_completeness_or_unknown_zero():
 v=payload(batch([]));assert v['declared_batch_fee']=='0.00' and v['daily_fill_completeness']=='UNVERIFIED'
 assert payload(batch([]),())['declared_batch_fee'] is None


def test_source_schedule_batch_result_tampering_is_refused():
 s=schedule();b=batch();r=result(b,(s,))
 with pytest.raises(ContractError):replace(s,sources=(source(b'Changed'),))
 v=json.loads(s.content);v['verified']=True
 with pytest.raises(ContractError):FeeSchedule(s.sources,canonical(v))
 v=json.loads(b.content);v['complete']=True
 with pytest.raises(ContractError):FeeBatch(canonical(v))
 for key,value in [('declared_batch_fee','0.00'),('financial_accepted',True),('account_applicability','VERIFIED'),('actual_billed_fee','0.02')]:
  v=json.loads(r.content);v[key]=value
  with pytest.raises(ContractError):replace(r,content=canonical(v))


@pytest.mark.parametrize('raw',[b'{"version":1,"version":1}',b'[]',b'null',b'{"x":NaN}',b'X'*65537],ids=['duplicate','list','null','nonfinite','oversize'])
def test_bounded_strict_json(raw):
 with pytest.raises(ContractError):FeeBatch(raw)
 with pytest.raises(ContractError):FeeSchedule((source(),),raw)


def test_bounds_and_redacted_source_validation():
 with pytest.raises(ContractError):source(b'')
 with pytest.raises(ContractError):source(b'x'*(2*1024**2+1))
 with pytest.raises(ContractError):replace(source(),url='https://name:password@example.invalid/fees')
 with pytest.raises(ContractError):replace(source(),url='https://example.invalid/fees?key=private')
 with pytest.raises(ContractError):replace(source(),media_type='application/octet-stream')
 with pytest.raises(ContractError):batch([fill(n) for n in range(1,130)])
 with pytest.raises(ContractError):schedule(rules=[])
 with pytest.raises(ContractError):result(ss=(schedule(),)*9)


@pytest.mark.parametrize('quantity,expected',[('60000','19.58'),('1','0.01')])
def test_per_order_cap_then_daily_rounding(quantity,expected):
 s=schedule([rule('TAF',basis='SHARES',rate='0.000195',cap='9.79',limit_unit='ORDER',rounding_unit='ACCOUNT_DAY')])
 v=payload(batch([fill(1,quantity=quantity),fill(2,quantity=quantity)]),(s,))
 c=component(v,'TAF')
 assert c['declared_fee']==expected and len(c['limit_groups'])==2 and len(c['groups'])==1
 assert v['order_lifetime_completeness']=='UNVERIFIED'


def test_rounding_unit_cannot_be_finer_than_limit_unit():
 with pytest.raises(ContractError):schedule([rule(limit_unit='ACCOUNT_DAY',rounding_unit='ORDER')])


def test_combined_original_source_bytes_are_bounded():
 schedules=[]
 for n in range(5):
  src=source(bytes([65+n])*(2*1024**2));v=schedule().to_payload();v.update(schedule_id=uid(n+1),source_sha256=[src.sha256])
  schedules.append(FeeSchedule((src,),canonical(v)))
 with pytest.raises(ContractError):result(ss=tuple(schedules))



def test_corrupt_schedule_is_rejected_before_hashing():
 s=schedule();object.__setattr__(s,'content',None)
 with pytest.raises(ContractError):result(ss=(s,))


def test_oversized_collection_is_rejected_before_any_schedule_hash(monkeypatch):
 s=schedule()
 def forbidden(_):raise AssertionError('Schedule hash accessed before collection bound')
 monkeypatch.setattr(FeeSchedule,'sha256',property(forbidden))
 with pytest.raises(ContractError):result(ss=(s,)*9)
