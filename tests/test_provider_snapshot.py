"""Provider snapshots retain evidence; they cannot claim synthetic/financial admission."""
from dataclasses import replace
from datetime import timedelta
import hashlib,importlib.util,json
import pytest
from compertum.data.alpaca import read_bar_evidence, SYMBOLS
from compertum.data.calendar import session_times
from compertum.data.errors import DataError
from compertum.data.snapshot import validate_snapshot

START='2023-11-22';END='2023-11-24'

def api():
 assert importlib.util.find_spec('compertum.data.provider_snapshot') is not None, 'Distinct provider snapshot adapter missing'
 from compertum.data import provider_snapshot
 return provider_snapshot

def request(ident,days,adjustment,reference='daily',feed='sip'):
 times=session_times(days[0]);stamp=times.entry if reference=='entry' else times.close_reference
 params={'symbols':','.join(sorted(SYMBOLS)),'start':days[0]+'T00:00:00Z' if reference=='daily' else stamp.isoformat(),'end':days[-1]+'T23:59:59Z' if reference=='daily' else (stamp+timedelta(seconds=59)).isoformat(),'timeframe':'1Day' if reference=='daily' else '1Min','adjustment':adjustment,'feed':feed,'asof':END,'sort':'asc','currency':'USD','limit':100}
 records=[]
 for symbol in sorted(SYMBOLS):
  for day in days:
   t=day+'T05:00:00Z' if reference=='daily' else stamp.isoformat()
   # Midnight NY label may differ during DST.
   if reference=='daily':
    from datetime import datetime,time,timezone
    from compertum.data.calendar import NY
    t=datetime.combine(__import__('datetime').date.fromisoformat(day),time(),NY).astimezone(timezone.utc).isoformat()
   records.append((symbol,{'t':t,'o':100.125,'h':102,'l':99,'c':101.375,'v':100000,'n':50,'vw':101.05}))
 pages=[]
 for index in range(0,len(records),100):
  body={}
  for symbol,b in records[index:index+100]:body.setdefault(symbol,[]).append(b)
  number=index//100;next_page=str(number+1) if index+100<len(records) else None
  raw=json.dumps({'bars':body,'next_page_token':next_page},separators=(',',':'))
  actual=dict(params)
  if number:actual['page_token']=str(number)
  pages.append({'request_id':ident,'page':number,'params':actual,'status':200,'started_utc':f'2026-10-10T14:{number:02}:00Z','received_utc':f'2026-10-10T14:{number:02}:01Z','body_utf8':raw,'body_sha256':hashlib.sha256(raw.encode()).hexdigest()})
 return {'schema_version':'alpaca-bars-v1','host':'https://data.alpaca.markets','requests':[{'id':ident,'path':'/v2/stocks/bars','params':params}],'pages':pages}

def encode(v):return json.dumps(v,separators=(',',':')).encode()

@pytest.fixture(scope='module')
def envelopes():
 dates=[START]
 for _ in range(252):dates.insert(0,session_times(dates[0]).previous_date)
 dates.append(END)
 # Each bundle stays within the existing 40-page/4096-row/1MiB limits.
 return tuple([request('daily-'+a+'-'+str(i),part,a) for a in ('raw','split') for i,part in enumerate((dates[:127],dates[127:]))]+[request(ref+'-'+a+'-'+day,[day],a,ref) for day in (START,END) for ref in ('entry','close') for a in ('raw','split')])

def build(envelopes,**changes):
 return api().build_provider_snapshot(tuple(read_bar_evidence(encode(v)) for v in envelopes),**dict({'start':START,'end':END,'feed':'sip'},**changes))

def test_complete_provider_snapshot_retains_prices_times_and_lineage(envelopes):
 s=build(envelopes);v=json.loads(s.content)
 assert v['provider']=='alpaca' and v['financial_accepted'] is False
 assert v['availability_basis']=='CURRENT_VINTAGE_SIMULATED_AVAILABILITY'
 assert v['warmup_sessions']==252 and len(v['symbols'])==13
 assert v['coverage']['complete'] is True and not v['missing']
 row=next(r for r in v['rows'] if r['symbol']=='AAPL' and r['session_date']==END and r['reference']=='close' and r['adjustment']=='raw')
 assert row['close']=='101.375' and row['session_close']=='2023-11-24T18:00:00+00:00'
 assert row['bar_label_time']=='2023-11-24T17:59:00+00:00'
 assert row['simulated_available_at']=='2023-11-27T14:25:00+00:00'
 assert row['first_seen_at'].startswith('2026-10-10') and row['provider_timestamp'] is None
 assert row['source_body_sha256'] and row['source_evidence_sha256']
 assert api().verify_provider_snapshot(s)==s
 with pytest.raises(DataError):validate_snapshot(s.content)

def test_cross_chunk_duplicate_is_rejected(envelopes):
 with pytest.raises(DataError,match='DUPLICATE_PROVIDER_ROW'):build(envelopes+(envelopes[-1],))

def test_missing_reference_remains_visible_not_filled(envelopes):
 values=json.loads(json.dumps(envelopes));p=values[-1]['pages'][0];body=json.loads(p['body_utf8']);del body['bars']['AAPL'];p['body_utf8']=json.dumps(body);p['body_sha256']=hashlib.sha256(p['body_utf8'].encode()).hexdigest()
 v=json.loads(build(values).content)
 assert v['coverage']['complete'] is False
 assert ['AAPL',END,'close','split'] in v['missing']
 assert len(v['symbols'])==13 and v['coverage']['symbols']['AAPL']['scored_daily_expected']==2

def test_omitted_request_is_not_omitted_from_denominator(envelopes):
 v=json.loads(build(envelopes[:-1]).content)
 assert len(v['missing'])==13 and not v['coverage']['complete']
 assert v['coverage']['symbols']['AAPL']['references_expected']==4

def test_corrupt_object_is_revalidated(envelopes):
 s=build(envelopes)
 with pytest.raises(DataError,match='PROVIDER_SNAPSHOT_CORRUPT'):api().verify_provider_snapshot(replace(s,sha256='0'*64))

@pytest.mark.parametrize('changes,code',[
 ({'start':'2024-01-02','end':'2024-01-03'},'PROTECTED_PROVIDER_DATE'),
 ({'feed':'all'},'PROVIDER_PROFILE'),
 ({'start':END,'end':START},'PROVIDER_WINDOW'),
 ({'end':'2023-11-27'},'PROVIDER_ASOF'),
])
def test_invalid_profile_refused(envelopes,changes,code):
 with pytest.raises(DataError,match=code):build(envelopes,**changes)

def test_mixed_feed_refused(envelopes):
 values=json.loads(json.dumps(envelopes));v=values[-1]
 v['requests'][0]['params']['feed']='iex'
 for p in v['pages']:p['params']['feed']='iex'
 with pytest.raises(DataError,match='PROVIDER_MIXED_FEEDS'):build(values)

def test_uniform_iex_does_not_satisfy_frozen_sip_profile(envelopes):
 values=json.loads(json.dumps(envelopes))
 for v in values:
  v['requests'][0]['params']['feed']='iex'
  for p in v['pages']:p['params']['feed']='iex'
 with pytest.raises(DataError,match='PROVIDER_PROFILE'):build(values,feed='iex')

@pytest.mark.parametrize('reference',['daily','entry'])
def test_empty_out_of_scope_requests_are_rejected(envelopes,reference):
 first=envelopes[0]['requests'][0]['params']['start'][:10]
 day=session_times(first).previous_date if reference=='daily' else first
 extra=request('outside-empty',[day],'raw',reference)
 for p in extra['pages']:
  p['body_utf8']=json.dumps({'bars':{},'next_page_token':None})
  p['body_sha256']=hashlib.sha256(p['body_utf8'].encode()).hexdigest()
 with pytest.raises(DataError,match='PROVIDER_SCOPE'):build(envelopes+(extra,))

def test_receipt_does_not_invent_actual_validation_or_first_ever_availability(envelopes):
 v=json.loads(build(envelopes).content);row=v['rows'][0]
 assert row['feature_available_at'] is None
 assert row['actual_availability_basis']=='VALIDATION_ADMISSION_TIME_NOT_RECORDED'
 assert row['first_seen_basis']=='RETAINED_ENVELOPE_RECEIPT_NOT_FIRST_EVER'
 assert row['first_seen_at']==row['retrieved_at']