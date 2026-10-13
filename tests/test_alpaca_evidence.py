"""Provider evidence stays distinct from synthetic snapshots and accepted strategies."""
import hashlib,importlib.util,json
from dataclasses import replace
from decimal import localcontext,ROUND_UP
from fractions import Fraction
import pytest
from compertum.data.errors import DataError
from compertum.data.snapshot import validate_snapshot

def api():
 assert importlib.util.find_spec('compertum.data.alpaca') is not None,'Real-provider evidence reader is not implemented'
 from compertum.data import alpaca
 return alpaca

def payload(*,feed='sip',missing=False):
 raw={'NVDA':[{'t':'2021-07-19T04:00:00Z','o':715.55,'h':751.88,'l':712.25,'c':751.07,'v':374003,'n':300,'vw':730.125}, {'t':'2021-07-20T04:00:00Z','o':187.2,'h':188.9,'l':183.3,'c':186.055,'v':489903,'n':400,'vw':185.375}, {'t':'2021-07-21T04:00:00Z','o':188.93,'h':195.27,'l':187.43,'c':194.22,'v':508841,'n':500,'vw':191.315}]}
 if missing:raw['NVDA'].pop(1)
 body=json.dumps({'bars':raw,'next_page_token':None},separators=(',',':'))
 params={'symbols':'NVDA','start':'2021-07-19T00:00:00Z','end':'2021-07-21T23:59:59Z','timeframe':'1Day','adjustment':'raw','feed':feed,'asof':'2021-07-21','sort':'asc','currency':'USD','limit':100}
 request={'id':'nvda-raw','path':'/v2/stocks/bars','params':params}
 page={'request_id':'nvda-raw','page':0,'params':dict(params),'status':200,'started_utc':'2026-10-10T03:00:00Z','received_utc':'2026-10-10T03:00:01Z','body_utf8':body,'body_sha256':hashlib.sha256(body.encode()).hexdigest()}
 return {'schema_version':'alpaca-bars-v1','host':'https://data.alpaca.markets','requests':[request],'pages':[page]}
def encode(value):return json.dumps(value,separators=(',',':')).encode()
def body_edit(value,edit):
 p=value['pages'][0];b=json.loads(p['body_utf8']);edit(b);p['body_utf8']=json.dumps(b,separators=(',',':'));p['body_sha256']=hashlib.sha256(p['body_utf8'].encode()).hexdigest()
def action(**changes):
 return api().SplitEvent(**dict({'action_id':'nvda-2021','symbol':'NVDA','effective_session':'2021-07-20','new_shares':4,'old_shares':1,'known_at':'2021-06-04T23:59:59Z','lineage_sha256':'a'*64},**changes))
def normalize(bundle,actions=None):
 return api().normalize_splits(bundle,'NVDA','2021-07-19','2021-07-21','2021-07-22T13:25:00Z',(action(),) if actions is None else actions)
def test_raw_provider_bytes_and_exact_normalization():
 m=api();raw=encode(payload());b=m.read_bar_evidence(raw)
 assert b.sha256==hashlib.sha256(raw).hexdigest() and b.feed=='sip' and not b.missing
 n=normalize(b);v=json.loads(n.content)
 assert Fraction(v['rows'][0]['close'])==Fraction('751.07')/4
 assert Fraction(v['rows'][0]['volume'])==374003*4
 assert Fraction(v['rows'][1]['close'])==Fraction('186.055')
 assert v['status']=='REAL_DATA_ENGINEERING_DIAGNOSTIC' and not v['financial_accepted']
 assert v['source_sha256']==b.sha256
 with pytest.raises(DataError):validate_snapshot(n.content)
def test_future_splits_do_not_change_previous_normalization():
 b=api().read_bar_evidence(encode(payload()));base=normalize(b)
 later=action(action_id='later',effective_session='2024-06-10',new_shares=10,known_at=None,lineage_sha256='b'*64)
 assert normalize(b,(action(),later)).content==base.content
@pytest.mark.parametrize('known', [None,'2021-07-23T00:00:00Z'])
def test_unknown_or_future_required_action_knowledge_refuses(known):
 b=api().read_bar_evidence(encode(payload()))
 with pytest.raises(DataError,match='ACTION_KNOWLEDGE_UNVERIFIED'):normalize(b,(action(known_at=known),))
def test_missing_rows_reported_and_required_window_refused():
 b=api().read_bar_evidence(encode(payload(missing=True)))
 assert len(b.missing)==1
 with pytest.raises(DataError,match='MISSING_PROVIDER_ROW'):normalize(b)
@pytest.mark.parametrize('change,reason',[
 (lambda v:v.update(host='https://example.org'),'PROVIDER_HOST'),
 (lambda v:v['pages'][0].update(body_sha256='0'*64),'PROVIDER_HASH'),
 (lambda v:v['pages'][0].update(status=403),'PROVIDER_STATUS'),
 (lambda v:v['pages'][0]['params'].update(feed='iex'),'PROVIDER_REQUEST_BINDING'),
 (lambda v:v['requests'][0]['params'].update(start='2024-01-01T00:00:00Z'),'PROTECTED_PROVIDER_DATE'),
 (lambda v:v['requests'][0]['params'].update(adjustment='all'),'PROVIDER_PROFILE'),
 (lambda v:v['pages'][0].update(received_utc='2020-01-01T00:00:00Z'),'PROVIDER_TIMING'),
 (lambda v:v['pages'].append(dict(v['pages'][0])),'PROVIDER_PAGE_ORDER'),
 (lambda v:body_edit(v,lambda b:b.update(next_page_token='more')),'PROVIDER_PAGINATION'),
 (lambda v:body_edit(v,lambda b:b.pop('next_page_token')),'PROVIDER_RESPONSE_FIELDS'),
 (lambda v:body_edit(v,lambda b:b['bars']['NVDA'].append(dict(b['bars']['NVDA'][0]))),'DUPLICATE_PROVIDER_ROW'),
 (lambda v:body_edit(v,lambda b:b['bars']['NVDA'][0].update(l=-1)),'INVALID_PROVIDER_NUMBER'),
 (lambda v:body_edit(v,lambda b:b['bars']['NVDA'][0].update(o=1)),'INVALID_OHLC'),
 (lambda v:body_edit(v,lambda b:b['bars']['NVDA'][0].update(t='2025-01-01T05:00:00Z')),'PROTECTED_PROVIDER_DATE'),
])
def test_invalid_provider_evidence_refused(change,reason):
 v=payload();change(v)
 with pytest.raises(DataError,match=reason):api().read_bar_evidence(encode(v))
def test_caller_cannot_forge_verified_rows():
 b=api().read_bar_evidence(encode(payload()))
 with pytest.raises(DataError,match='PROVIDER_EVIDENCE_CORRUPT'):normalize(replace(b,rows=()))
def test_canonical_output_ignores_ambient_decimal_context():
 b=api().read_bar_evidence(encode(payload()));expected=normalize(b).content
 with localcontext() as ctx:
  ctx.prec=6;ctx.rounding=ROUND_UP
  assert normalize(b).content==expected
@pytest.mark.parametrize('new,old',[(0,1),(1,0),(True,1),(1,1),(1000001,1)])
def test_invalid_split_factors_refused(new,old):
 b=api().read_bar_evidence(encode(payload()))
 with pytest.raises(DataError,match='INVALID_SPLIT_EVENT'):normalize(b,(action(new_shares=new,old_shares=old),))
def test_duplicate_events_and_past_decision_refused():
 b=api().read_bar_evidence(encode(payload()))
 with pytest.raises(DataError,match='DUPLICATE_SPLIT_EVENT'):normalize(b,(action(),action()))
 with pytest.raises(DataError,match='NORMALIZATION_CUTOFF'):api().normalize_splits(b,'NVDA','2021-07-19','2021-07-21','2021-07-20T13:25:00Z',(action(),))


def paged():
 v=payload();p=v['pages'][0];body=json.loads(p['body_utf8']);last=body['bars']['NVDA'].pop()
 v['requests'][0]['params']['limit']=2;p['params']['limit']=2
 body['next_page_token']='page-two';p['body_utf8']=json.dumps(body);p['body_sha256']=hashlib.sha256(p['body_utf8'].encode()).hexdigest()
 q={**p,'page':1,'params':{**p['params'],'page_token':'page-two'},'started_utc':'2026-10-10T03:00:02Z','received_utc':'2026-10-10T03:00:03Z'}
 q['body_utf8']=json.dumps({'bars':{'NVDA':[last]},'next_page_token':None});q['body_sha256']=hashlib.sha256(q['body_utf8'].encode()).hexdigest();v['pages'].append(q)
 return v

def test_linked_pages_have_identical_rows_to_single_page():
 a=api().read_bar_evidence(encode(payload()));b=api().read_bar_evidence(encode(paged()))
 assert [(r.timestamp,r.close) for r in a.rows]==[(r.timestamp,r.close) for r in b.rows]
 assert not b.missing

@pytest.mark.parametrize('edit,reason',[
 (lambda v:v['pages'].pop(),'PROVIDER_PAGINATION'),
 (lambda v:v['pages'][1]['params'].update(page_token='wrong'),'PROVIDER_REQUEST_BINDING'),
 (lambda v:v['pages'].reverse(),'PROVIDER_PAGE_ORDER'),
 (lambda v:v['pages'][1].update(started_utc='2026-10-10T03:00:00Z'),'PROVIDER_TIMING'),
 (lambda v:v['pages'][0]['params'].update(limit=2.0),'PROVIDER_REQUEST_BINDING'),
])
def test_page_chain_refuses_missing_reordered_retyped_or_overlapping_receipts(edit,reason):
 v=paged();edit(v)
 with pytest.raises(DataError,match=reason):api().read_bar_evidence(encode(v))

def test_holiday_and_weekend_denominator():
 v=payload();params=v['requests'][0]['params'];params.update(start='2023-11-20T00:00:00Z',end='2023-11-26T23:59:59Z',asof='2023-11-26');v['pages'][0]['params']=dict(params)
 body_edit(v,lambda b:b.update(bars={'NVDA':[{**b['bars']['NVDA'][0],'t':f'2023-11-{day}T05:00:00Z'} for day in ('20','21','22','24')]}))
 assert not api().read_bar_evidence(encode(v)).missing

def test_json_symbol_member_order_is_not_bar_order():
 v=payload();v['requests'][0]['params']['symbols']='NVDA,AAPL';v['pages'][0]['params']['symbols']='NVDA,AAPL'
 body_edit(v,lambda b:b['bars'].update(AAPL=[dict(r) for r in b['bars']['NVDA']]))
 b=api().read_bar_evidence(encode(v));assert len(b.rows)==6 and not b.missing

def test_mixed_feeds_refused_even_when_each_request_is_well_formed():
 a=payload();b=payload(feed='iex');b['requests'][0]['id']='other';b['pages'][0]['request_id']='other'
 a['requests']+=b['requests'];a['pages']+=b['pages']
 with pytest.raises(DataError,match='PROVIDER_MIXED_FEEDS'):api().read_bar_evidence(encode(a))

@pytest.mark.parametrize('number',['NaN','Infinity','-Infinity','1e9999999999999999999','1e-9999999999999999999','1e100','0.0000000000001','true','"715.55"'])
def test_numeric_tokens_fail_closed_independent_of_decimal_traps(number):
 from decimal import InvalidOperation
 v=payload();p=v['pages'][0];p['body_utf8']=p['body_utf8'].replace('"o":715.55','"o":'+number,1);p['body_sha256']=hashlib.sha256(p['body_utf8'].encode()).hexdigest()
 for trap in (True,False):
  with localcontext() as ctx:
   ctx.traps[InvalidOperation]=trap
   with pytest.raises(DataError,match='INVALID_PROVIDER_NUMBER'):api().read_bar_evidence(encode(v))

def test_duplicate_keys_unknown_fields_and_oversized_input_refused():
 v=payload();p=v['pages'][0];p['body_utf8']=p['body_utf8'].replace('"o":715.55','"o":715.55,"o":715.55',1);p['body_sha256']=hashlib.sha256(p['body_utf8'].encode()).hexdigest()
 with pytest.raises(DataError,match='DUPLICATE_KEY'):api().read_bar_evidence(encode(v))
 v=payload();v['ignored']='field'
 with pytest.raises(DataError,match='PROVIDER_ENVELOPE'):api().read_bar_evidence(encode(v))
 with pytest.raises(DataError,match='INPUT_BOUND'):api().read_bar_evidence(b' '*(1024*1024+1))

def test_exact_split_volume_and_dollar_value_invariant():
 b=api().read_bar_evidence(encode(payload()));n=json.loads(normalize(b).content)
 for raw,derived in zip(b.rows,n['rows'],strict=True):
  assert Fraction(raw.close)*Fraction(raw.volume)==Fraction(derived['close'])*Fraction(derived['volume'])

@pytest.mark.parametrize('date,minute',[('2023-11-24','17:59'),('2023-03-13','13:35')])
def test_exact_minute_calendar_accepts_early_close_and_dst(date,minute):
 v=payload();params=v['requests'][0]['params'];params.update(start=f'{date}T{minute}:00Z',end=f'{date}T{minute}:59Z',asof=date,timeframe='1Min');v['pages'][0]['params']=dict(params)
 body_edit(v,lambda b:b.update(bars={'NVDA':[{**b['bars']['NVDA'][0],'t':params['start']}]}))
 assert not api().read_bar_evidence(encode(v)).missing
 params['start']=f'{date}T14:00:00Z';params['end']=f'{date}T14:00:59Z';v['pages'][0]['params']=dict(params)
 with pytest.raises(DataError,match='PROVIDER_MINUTE_WINDOW'):api().read_bar_evidence(encode(v))
