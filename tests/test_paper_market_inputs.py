"""Invented operational data. No provider access or real provenance claim."""
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal,localcontext,ROUND_UP
import hashlib,json
from uuid import uuid4
import pytest
from compertum.data.calendar import session_times
from compertum.data.encoding import canonical
from compertum.domain import ContractError
from compertum.paper_market_inputs import (OperationalMarketInputs,prepare_market_plan,prepare_market_request,observe_market_reply,qualify_market_inputs)


def stamp(value):return value.isoformat().replace('+00:00','Z')

def plan(day='2026-10-09'):
 times=session_times(day)
 return prepare_market_plan(project_id='a'*64,account_alias='fixture',symbol='MSFT',session_date=day,created_at=stamp(times.decision-timedelta(minutes=25)))


def observed(p,op,body,*,page_token=None,at=None,received=None,status=200):
 times=session_times(p.to_payload()['session_date'])
 at=at or stamp(times.entry);received=received or stamp(times.entry+timedelta(seconds=1))
 req=prepare_market_request(p,operation=op,request_id=str(uuid4()),created_at=at,page_token=page_token)
 raw=body if type(body) is bytes else canonical(body)
 return observe_market_reply(req,raw,status=status,received_at=received)


def sample(day='2026-10-09',volume=20000):
 p=plan(day);pp=p.to_payload();times=session_times(day)
 asset=dict(id='11111111-1111-4111-8111-111111111111',symbol='MSFT',**{'class':'us_equity'},exchange='NASDAQ',status='active',tradable=True,optional_metadata='retained')
 quote={'quotes':{'MSFT':dict(t=stamp(times.entry),bp=100,bs=2,ap=101,**{'as':3},bx='V',ax='V',c=['R'],z='C')}}
 rows=[dict(t=t,o=100,h=102,l=99,c=100,v=volume,n=10,vw=100) for t in pp['daily_labels']]
 records=[]
 for i in range(0,len(rows),100):
  j=i//100;token=None if j==0 else 'page'+str(j)
  at=times.decision-timedelta(minutes=5)+timedelta(seconds=j*2)
  records.append(observed(p,'HISTORY',dict(bars={'MSFT':rows[i:i+100]},next_page_token=('page'+str(j+1) if i+100<len(rows) else None)),page_token=token,at=stamp(at),received=stamp(at+timedelta(seconds=1))))
 records += [observed(p,'ASSET',asset),observed(p,'QUOTE',quote)]
 return p,tuple(records),stamp(times.entry+timedelta(seconds=1))


def mutate(record,edit):
 body=json.loads(record.raw);edit(body)
 return observe_market_reply(record.request,canonical(body),status=record.status,received_at=record.received_at)


def result(p,records,now):return qualify_market_inputs(p,records,as_of=now).to_payload()


def test_complete_rows_derive_facts_without_actual_authority():
 p,records,now=sample();e=qualify_market_inputs(p,records,as_of=now);v=e.to_payload()
 assert v['history']['observed_sessions']==252 and v['history']['complete'] is True
 assert v['history']['prior_raw_close']=='100' and v['history']['mean_dollar_volume']=='2000000'
 assert v['history']['intent_notional_cap']=='2000' and v['quote']['valid'] is True
 assert v['observed_conditions_met'] is True and v['status']=='BLOCKED'
 assert v['native_provenance']=='UNVERIFIED' and v['feed_entitlement']=='UNVERIFIED'
 assert not v['transport_authorized'] and not v['financial_accepted'] and not v['research_eligible']
 assert {'ACTION_HALT_COVERAGE_UNVERIFIED','FEE_APPLICABILITY_UNVERIFIED'} <= set(v['deficiencies'])
 assert qualify_market_inputs(p,records,as_of=now).content==e.content
 assert e.evidence_sha256==hashlib.sha256(e.evidence_bytes()).hexdigest()
 assert all(r.raw.decode() in json.loads(e.evidence_bytes())['responses'][i]['body_utf8'] for i,r in enumerate(records))
 with pytest.raises(ContractError):replace(e,content=canonical(dict(v,transport_authorized=True)))


@pytest.mark.parametrize('field,value',[('feed','sip'),('symbol','BTCUSD'),('project_id','bad'),('account_alias','../../x'),('session_date','2026-10-10')])
def test_plan_rejects_wrong_profile(field,value):
 p=plan().to_payload();kw={k:p[k] for k in ('project_id','account_alias','symbol','session_date','created_at')};kw[field]=value
 with pytest.raises((ContractError,TypeError)):prepare_market_plan(**kw)


@pytest.mark.parametrize('kind',['symbol','feed','adjustment','host','plan','request_id','duplicate_request'])
def test_exact_request_binding_rejects_substitution(kind):
 p,records,now=sample();r=records[0]
 if kind=='duplicate_request':
  with pytest.raises(ContractError):result(p,records+(r,),now)
  return
 if kind=='plan':
  other=prepare_market_plan(project_id='b'*64,account_alias='fixture',symbol='MSFT',session_date='2026-10-09',created_at=p.to_payload()['created_at'])
  with pytest.raises(ContractError):result(other,records,now)
  return
 v=r.request.to_payload()
 if kind=='host':v['origin']='https://evil.invalid'
 elif kind=='request_id':v['request_id']=None
 else:v['parameters'][kind if kind!='symbol' else 'symbols']='wrong'
 with pytest.raises(ContractError):replace(r.request,content=canonical(v))


@pytest.mark.parametrize('kind',['crossed','stale','future','missing','wrong_venue','zero'])
def test_unusable_quote_is_explicitly_blocked(kind):
 p,records,now=sample();q=records[-1];times=session_times('2026-10-09')
 def edit(b):
  v=b['quotes']['MSFT']
  if kind=='crossed':v['bp']=102
  elif kind=='zero':v['bp']=0
  elif kind=='stale':v['t']=stamp(times.entry-timedelta(seconds=30))
  elif kind=='future':v['t']='2026-10-09T13:35:01.000000001Z'
  elif kind=='wrong_venue':v['bx']='Q'
  else:b['quotes']={}
 v=result(p,records[:-1]+(mutate(q,edit),),now)
 assert v['quote']['valid'] is False and not v['observed_conditions_met']


def test_exact_nanosecond_quote_boundaries_and_decimal_prices():
 p,records,now=sample();q=records[-1]
 raw=b'{"quotes":{"MSFT":{"t":"2026-10-09T13:34:31.000000000Z","bp":100.123456789123,"ap":100.123456789124,"bs":0.5,"as":1.25,"bx":"V","ax":"V"}}}'
 q=observe_market_reply(q.request,raw,status=200,received_at=q.received_at)
 v=result(p,records[:-1]+(q,),now);assert v['quote']['valid'] and v['quote']['bid']=='100.123456789123'
 raw=raw.replace(b'13:34:31.000000000',b'13:34:30.999999999');q=observe_market_reply(q.request,raw,status=200,received_at=q.received_at)
 assert not result(p,records[:-1]+(q,),now)['quote']['valid']


@pytest.mark.parametrize('raw',[b'{"quotes":{},"quotes":{}}',b'{"x":NaN}',b'{"x":1e10000}',b'{"x":0.1234567891234}',b'[]',b'x',b' '*65537],ids=['duplicate-key','nonfinite','huge-exponent','excess-precision','array','invalid-json','oversize'])
def test_malformed_or_unbounded_provider_bodies_refuse(raw):
 p,records,now=sample()
 with pytest.raises(ContractError):
  q=observe_market_reply(records[-1].request,raw,status=200,received_at=now)
  result(p,records[:-1]+(q,),now)


@pytest.mark.parametrize('kind',['missing','continuation','late','inactive','untradable','foreign_class','low_price','low_volume'])
def test_incomplete_or_ineligible_inputs_preserve_blockers(kind):
 p,records,now=sample();r=list(records)
 if kind=='missing':r[0]=mutate(r[0],lambda b:b['bars']['MSFT'].pop(0))
 elif kind=='continuation':r[2]=mutate(r[2],lambda b:b.update(next_page_token='more'))
 elif kind=='late':r[0]=replace(r[0],request=prepare_market_request(p,operation='HISTORY',request_id=str(uuid4()),created_at='2026-10-09T13:25:00Z'),received_at='2026-10-09T13:25:00.000000001Z');r=r[:1]+r[3:]
 elif kind in ('inactive','untradable','foreign_class'):
  key,val={'inactive':('status','inactive'),'untradable':('tradable',False),'foreign_class':('class','crypto')}[kind]
  r[-2]=mutate(r[-2],lambda b:b.update({key:val}))
 else:
  for i in range(3):
   def edit(b):
    for row in b['bars']['MSFT']:
     if kind=='low_price':row.update(o=4,h=4,l=4,c=4,vw=4)
     else:row['v']=1
   r[i]=mutate(r[i],edit)
 v=result(p,tuple(r),now);assert not v['observed_conditions_met'] and v['status']=='BLOCKED'
 if kind=='low_volume':assert v['history']['intent_notional_cap']=='1'


@pytest.mark.parametrize('kind',['duplicate_row','bad_label','bad_token','repeated_token','out_of_order','wrong_symbol','bool_price','bad_ohlc','extra_page'])
def test_corrupt_history_is_refused(kind):
 p,records,now=sample();r=list(records)
 if kind=='duplicate_row':r[1]=mutate(r[1],lambda b:b['bars']['MSFT'].__setitem__(0,json.loads(r[0].raw)['bars']['MSFT'][-1]))
 elif kind=='bad_label':r[0]=mutate(r[0],lambda b:b['bars']['MSFT'][0].update(t=b['bars']['MSFT'][0]['t'].replace('04:00','04:01').replace('05:00','05:01')))
 elif kind=='bad_token':r[1]=replace(r[1],request=prepare_market_request(p,operation='HISTORY',request_id=str(uuid4()),created_at=r[1].request.to_payload()['created_at'],page_token='other'))
 elif kind=='repeated_token':r[1]=mutate(r[1],lambda b:b.update(next_page_token='page1'))
 elif kind=='out_of_order':r[0]=mutate(r[0],lambda b:b['bars']['MSFT'].reverse())
 elif kind=='wrong_symbol':r[0]=mutate(r[0],lambda b:b['bars'].update(AAPL=[]))
 elif kind=='bool_price':r[0]=mutate(r[0],lambda b:b['bars']['MSFT'][0].update(c=True))
 elif kind=='bad_ohlc':r[0]=mutate(r[0],lambda b:b['bars']['MSFT'][0].update(c=103))
 else:r.insert(3,observed(p,'HISTORY',dict(bars={},next_page_token=None),page_token='anything'))
 with pytest.raises(ContractError):result(p,tuple(r),now)


def test_forbidden_flags_and_derived_tampering_cannot_qualify():
 p,records,now=sample();e=qualify_market_inputs(p,records,as_of=now);v=e.to_payload();v['history']['mean_dollar_volume']='999999999'
 with pytest.raises(ContractError):replace(e,content=canonical(v))
 with pytest.raises(TypeError):qualify_market_inputs(p,records,as_of=now,verified=True)
 with pytest.raises(ContractError):replace(e,observations=records[:-1])


@pytest.mark.parametrize('day',['2026-11-27','2026-03-09','2026-10-13'])
def test_calendar_early_close_dst_and_holiday_boundaries(day):
 p,records,now=sample(day);v=result(p,records,now)
 assert v['history']['complete'] and p.to_payload()['history_sessions'][-1]==session_times(day).previous_date
 assert v['history']['observed_sessions']==252


def test_arithmetic_is_independent_of_caller_decimal_context():
 p,records,now=sample();expected=qualify_market_inputs(p,records,as_of=now).content
 with localcontext() as ctx:
  ctx.prec=3;ctx.rounding=ROUND_UP
  assert qualify_market_inputs(p,records,as_of=now).content==expected


def test_http_denial_never_establishes_entitlement():
 p,records,now=sample();q=observe_market_reply(records[-1].request,b'{"message":"invented denial"}',status=403,received_at=now)
 v=result(p,records[:-1]+(q,),now)
 assert not v['quote']['valid'] and v['feed_entitlement']=='UNVERIFIED' and 'QUOTE_HTTP_REFUSED' in v['deficiencies']


@pytest.mark.parametrize('kind',['too_many_responses','too_many_history_pages','too_many_rows','bool_status','late_response','future_receipt','wrong_day','bad_asset_type'])
def test_resource_type_and_chronology_bounds(kind):
 p,records,now=sample()
 with pytest.raises(ContractError):
  if kind=='too_many_responses':result(p,records+records+records[:1],now)
  elif kind=='too_many_history_pages':result(p,(records[0],)*9,now)
  elif kind=='too_many_rows':result(p,(mutate(records[0],lambda b:b['bars']['MSFT'].append(b['bars']['MSFT'][0])),)+records[1:],now)
  elif kind=='bool_status':replace(records[-1],status=True)
  elif kind=='late_response':replace(records[-1],received_at='2026-10-09T13:35:10.000000001Z')
  elif kind=='future_receipt':result(p,records,'2026-10-09T13:35:00.999999999Z')
  elif kind=='wrong_day':result(p,records,'2026-10-10T13:35:01Z')
  else:result(p,records[:-2]+(mutate(records[-2],lambda b:b.update(tradable=1)),records[-1]),now)


def test_eight_pages_with_continuation_remain_incomplete():
 p,records,now=sample();allrows=sum((json.loads(r.raw)['bars']['MSFT'] for r in records[:3]),[]);history=[]
 times=session_times('2026-10-09')
 for i in range(8):
  at=times.decision-timedelta(minutes=4)+timedelta(seconds=2*i)
  history.append(observed(p,'HISTORY',dict(bars={'MSFT':allrows[i*32:(i+1)*32]},next_page_token='page'+str(i+1)),page_token=None if i==0 else 'page'+str(i),at=stamp(at),received=stamp(at+timedelta(seconds=1))))
 v=result(p,tuple(history)+records[-2:],now)
 assert v['history']['observed_sessions']==252 and not v['history']['complete']
 assert 'HISTORY_PAGINATION_INCOMPLETE' in v['deficiencies']


def test_history_cutoff_uses_nanoseconds_even_with_complete_rows():
 p,records,now=sample();r=list(records)
 r[2]=replace(r[2],request=prepare_market_request(p,operation='HISTORY',request_id=str(uuid4()),created_at='2026-10-09T13:25:00Z',page_token='page2'),received_at='2026-10-09T13:25:00Z')
 assert result(p,tuple(r),now)['history']['complete']
 r[2]=replace(r[2],received_at='2026-10-09T13:25:00.000000001Z')
 v=result(p,tuple(r),now);assert v['history']['observed_sessions']==252 and not v['history']['complete']
 assert 'HISTORY_AFTER_CUTOFF' in v['deficiencies']


def test_fractional_provider_values_remain_exact_under_hostile_decimal_context():
 p,records,now=sample();r=list(records)
 for i in range(3):
  raw=r[i].raw.replace(b'"c":100',b'"c":100.123456789123').replace(b'"v":20000',b'"v":0.123456789123')
  r[i]=observe_market_reply(r[i].request,raw,status=200,received_at=r[i].received_at)
 r=tuple(r);expected=qualify_market_inputs(p,r,as_of=now).content
 with localcontext() as ctx:
  ctx.prec=80;expected_mean=Decimal('100.123456789123')*Decimal('0.123456789123')
 assert result(p,r,now)['history']['mean_dollar_volume']==format(expected_mean,'f')
 with localcontext() as ctx:
  ctx.prec=3;ctx.rounding=ROUND_UP
  assert qualify_market_inputs(p,r,as_of=now).content==expected


def test_historical_development_parser_remains_protected():
 from compertum.data.alpaca import _timestamp
 from compertum.data.errors import DataError
 with pytest.raises(DataError,match='PROTECTED_PROVIDER_DATE'):_timestamp('2026-10-09T13:35:00Z')
