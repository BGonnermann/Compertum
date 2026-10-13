"""Corporate action evidence must not fabricate coverage or confuse tickers."""
import hashlib,importlib.util,json
from dataclasses import replace
from decimal import localcontext,ROUND_UP
import pytest
from compertum.data.errors import DataError

def api():
 assert importlib.util.find_spec('compertum.data.actions') is not None,'Action evidence reader is not implemented'
 from compertum.data import actions
 return actions

def encode(v):return json.dumps(v,separators=(',',':')).encode()
def payload():
 records={'cash_dividends':[{'id':'00000000-0000-4000-8000-000000000001','symbol':'NVDA','cusip':'67066G104','ex_date':'2021-06-09','record_date':'2021-06-10','payable_date':'2021-07-01','process_date':'2021-07-01','rate':0.16,'foreign':False,'special':False}], 'forward_splits':[{'id':'00000000-0000-4000-8000-000000000002','symbol':'NVDA','cusip':'67066G104','ex_date':'2021-07-20','record_date':'2021-06-21','payable_date':'2021-07-19','due_bill_redemption_date':'2021-07-21','process_date':'2021-07-20','new_rate':4,'old_rate':1}]}
 params={'symbols':'NVDA,SPY','start':'2021-01-01','end':'2021-12-31','limit':100,'sort':'asc','data_quality':'all','region':'us'}
 body=json.dumps({'corporate_actions':records,'next_page_token':None})
 page={'request_id':'actions-2021','page':0,'params':dict(params),'status':200,'started_utc':'2026-10-10T03:00:00Z','received_utc':'2026-10-10T03:00:01Z','body_utf8':body,'body_sha256':hashlib.sha256(body.encode()).hexdigest()}
 return {'schema_version':'alpaca-actions-v1','host':'https://data.alpaca.markets','requests':[{'id':'actions-2021','path':'/v1/corporate-actions','params':params}],'pages':[page]}
def edit_body(v,edit):
 p=v['pages'][0];b=json.loads(p['body_utf8']);edit(b);p['body_utf8']=json.dumps(b);p['body_sha256']=hashlib.sha256(p['body_utf8'].encode()).hexdigest()
def identity(symbol='NVDA',cusip='67066G104',aliases=('NVDA',)):
 return api().DeclaredIdentity(symbol,cusip,aliases,'a'*64)
def observation(**changes):
 return api().DividendObservation(**dict({'symbol':'NVDA','cusip':'67066G104','ex_date':'2021-06-09','amount':'0.16','record_date':'2021-06-10','payable_date':'2021-07-01','publication_bound':'2021-05-27T04:00:00Z','lineage_sha256':'b'*64},**changes))

def test_original_evidence_and_economic_dates_stay_distinct():
 raw=encode(payload());v=api().read_action_evidence(raw)
 assert v.sha256==hashlib.sha256(raw).hexdigest() and len(v.actions)==2
 a=v.actions[0];assert a.economic_date=='2021-06-09' and a.process_date=='2021-07-01'
 assert 'ACTION_KNOWLEDGE_UNVERIFIED' in a.issues
 c=json.loads(api().classify_actions(v,(identity(),)).content)
 assert c['counts']['IDENTITY_MATCHED']==2 and c['financial_accepted'] is False
 assert c['coverage']=='UNVERIFIED_PROVIDER_COVERAGE'

def test_absent_records_are_not_zero_actions_or_verified_coverage():
 v=payload();edit_body(v,lambda b:b.update(corporate_actions={}))
 evidence=api().read_action_evidence(encode(v));assert evidence.actions==()
 r=json.loads(api().reconcile_dividends(evidence,(observation(),)).content)
 assert r['counts']['MISSING_PROVIDER_ACTION']==1 and not r['financial_accepted']

def test_matching_subset_cannot_establish_coverage():
 evidence=api().read_action_evidence(encode(payload()))
 r=json.loads(api().reconcile_dividends(evidence,(observation(),)).content)
 assert r['counts']['MATCHED_DECLARED_FIELDS']==1
 assert r['coverage']=='UNVERIFIED_PROVIDER_COVERAGE' and not r['financial_accepted']
 assert r['historical_provider_availability']=='UNVERIFIED'

def test_missing_dates_and_cusip_remain_explicit():
 v=payload()
 def incomplete(b):
  a=b['corporate_actions']['cash_dividends'][0];a['cusip']='';a.pop('payable_date');a.pop('record_date')
 edit_body(v,incomplete);evidence=api().read_action_evidence(encode(v))
 a=evidence.actions[0];assert {'MISSING_CUSIP','MISSING_PAYABLE_DATE','MISSING_RECORD_DATE'}<=set(a.issues)
 c=json.loads(api().classify_actions(evidence,(identity(),)).content)
 assert c['rows'][0]['state']=='IDENTITY_UNVERIFIED'
 r=json.loads(api().reconcile_dividends(evidence,(observation(),)).content)
 assert r['rows'][0]['state']=='PROVIDER_FIELDS_UNVERIFIED'
 assert {'cusip','record_date','payable_date'}<=set(r['rows'][0]['unverified_fields'])

def test_amount_mismatch_is_not_hidden_by_rounding():
 e=api().read_action_evidence(encode(payload()))
 r=json.loads(api().reconcile_dividends(e,(observation(amount='0.160000000001'),)).content)
 assert r['rows'][0]['state']=='PROVIDER_SOURCE_CONFLICT' and r['rows'][0]['conflicting_fields']==['amount']

def test_meta_ticker_reuse_and_merger_direction():
 v=payload();params=v['requests'][0]['params'];params.update(symbols='META,FB,XOM',start='2022-01-01',end='2022-12-31');v['pages'][0]['params']=dict(params)
 records={'name_changes':[{'id':'00000000-0000-4000-8000-000000000003','old_symbol':'META','new_symbol':'METV','old_cusip':'53656F417','new_cusip':'53656F417','process_date':'2022-01-31'},{'id':'00000000-0000-4000-8000-000000000004','old_symbol':'FB','new_symbol':'META','old_cusip':'30303M102','new_cusip':'30303M102','process_date':'2022-06-09'}], 'stock_mergers':[{'id':'00000000-0000-4000-8000-000000000005','acquiree_symbol':'DEN','acquirer_symbol':'XOM','acquiree_cusip':'24790A101','acquirer_cusip':'30231G102','acquiree_rate':1,'acquirer_rate':0.84,'effective_date':'2022-11-02','payable_date':'2022-11-02','process_date':'2022-11-02'}]}
 edit_body(v,lambda b:b.update(corporate_actions=records));e=api().read_action_evidence(encode(v))
 c=json.loads(api().classify_actions(e,(identity('META','30303M102',('META','FB')),identity('XOM','30231G102',('XOM',)))).content)
 assert [r['state'] for r in c['rows']]==['SYMBOL_IDENTITY_CONFLICT','IDENTITY_MATCHED','COUNTERPARTY_ONLY']
 assert c['rows'][2]['affected_assets']==[]
 assert 'ECONOMIC_DATE_UNVERIFIED' in e.actions[1].issues

@pytest.mark.parametrize('edit,reason',[
 (lambda v:v.update(host='https://example.com'),'PROVIDER_HOST'),
 (lambda v:v['pages'][0].update(body_sha256='0'*64),'PROVIDER_HASH'),
 (lambda v:v['pages'][0].update(status=403),'PROVIDER_STATUS'),
 (lambda v:v['pages'][0]['params'].update(limit=100.0),'PROVIDER_REQUEST_BINDING'),
 (lambda v:v['pages'].append(dict(v['pages'][0])),'PROVIDER_PAGE_ORDER'),
 (lambda v:v['requests'][0]['params'].update(start='2024-01-01'),'PROTECTED_ACTION_DATE'),
 (lambda v:v['requests'][0]['params'].update(data_quality='complete'),'ACTION_PROFILE'),
 (lambda v:v['requests'][0].update(path='/v2/account'),'ACTION_PROFILE'),
 (lambda v:v['pages'][0].update(received_utc='2020-01-01T00:00:00Z'),'PROVIDER_TIMING'),
 (lambda v:edit_body(v,lambda b:b.pop('next_page_token')),'PROVIDER_RESPONSE_FIELDS'),
 (lambda v:edit_body(v,lambda b:b.update(next_page_token='more')),'PROVIDER_PAGINATION'),
 (lambda v:edit_body(v,lambda b:b['corporate_actions']['cash_dividends'].append(dict(b['corporate_actions']['cash_dividends'][0]))),'DUPLICATE_ACTION_ID'),
 (lambda v:edit_body(v,lambda b:b['corporate_actions']['cash_dividends'][0].update(rate=True)),'INVALID_PROVIDER_NUMBER'),
 (lambda v:edit_body(v,lambda b:b['corporate_actions']['cash_dividends'][0].update(process_date='2020-07-01')),'ACTION_PROCESS_WINDOW'),
 (lambda v:edit_body(v,lambda b:b['corporate_actions']['cash_dividends'][0].update(symbol='TSLA')),'ACTION_SYMBOL_BINDING'),
])
def test_invalid_action_envelope_refused(edit,reason):
 v=payload();edit(v)
 with pytest.raises(DataError,match=reason):api().read_action_evidence(encode(v))

def test_forged_objects_duplicate_sources_and_invalid_identity_refused():
 e=api().read_action_evidence(encode(payload()))
 with pytest.raises(DataError,match='ACTION_EVIDENCE_CORRUPT'):api().classify_actions(replace(e,actions=()),(identity(),))
 with pytest.raises(DataError,match='DUPLICATE_SOURCE_OBSERVATION'):api().reconcile_dividends(e,(observation(),observation()))
 with pytest.raises(DataError,match='INVALID_ACTION_IDENTITY'):api().classify_actions(e,(identity(cusip=''),))
 with pytest.raises(DataError,match='AMBIGUOUS_ACTION_IDENTITY'):api().classify_actions(e,(identity(),identity('AAPL','67066G104',('AAPL',))))

def test_output_independent_of_decimal_context():
 e=api().read_action_evidence(encode(payload()));a=api().reconcile_dividends(e,(observation(),)).content
 with localcontext() as ctx:
  ctx.prec=6;ctx.rounding=ROUND_UP
  assert api().reconcile_dividends(e,(observation(),)).content==a

def test_complete_linked_pages_preserve_both_original_bodies():
 v=payload();first=v['pages'][0];body=json.loads(first['body_utf8']);split=body['corporate_actions'].pop('forward_splits');body['next_page_token']='page2'
 first['body_utf8']=json.dumps(body);first['body_sha256']=hashlib.sha256(first['body_utf8'].encode()).hexdigest()
 second=dict(first,page=1,params=dict(first['params'],page_token='page2'),started_utc='2026-10-10T03:00:02Z',received_utc='2026-10-10T03:00:03Z')
 second['body_utf8']=json.dumps({'corporate_actions':{'forward_splits':split},'next_page_token':None});second['body_sha256']=hashlib.sha256(second['body_utf8'].encode()).hexdigest();v['pages'].append(second)
 e=api().read_action_evidence(encode(v));assert len(e.actions)==2 and e.actions[0].body_sha256!=e.actions[1].body_sha256
 v['pages'][1]['params']['page_token']='wrong'
 with pytest.raises(DataError,match='PROVIDER_REQUEST_BINDING'):api().read_action_evidence(encode(v))


def test_unsupported_or_extended_schema_never_silently_qualified():
 for kind,extra in [('unrecognized_actions',{}),('cash_dividends',{'new_vendor_field':'unknown'})]:
  v=payload()
  def edit(b):
   record=b['corporate_actions']['cash_dividends'][0];record.update(extra);b['corporate_actions']={kind:[record]}
  edit_body(v,edit);e=api().read_action_evidence(encode(v))
  r=json.loads(api().classify_actions(e,(identity(),)).content)
  assert r['rows'][0]['state']=='ACTION_SCHEMA_UNVERIFIED' and not r['rows'][0]['affected_assets']


def test_duplicate_economic_event_never_arbitrarily_selected():
 v=payload()
 def edit(b):
  rows=b['corporate_actions']['cash_dividends'];rows.append(dict(rows[0],id='00000000-0000-4000-8000-000000000099',special=True))
 edit_body(v,edit);e=api().read_action_evidence(encode(v))
 r=json.loads(api().reconcile_dividends(e,(observation(),)).content)
 assert r['rows'][0]['state']=='AMBIGUOUS_PROVIDER_ACTION'


@pytest.mark.parametrize('amount',['0','-1','NaN','Infinity','1e999','1.'+'0'*13,True,None])
def test_unbounded_or_malformed_source_amount_refused(amount):
 e=api().read_action_evidence(encode(payload()))
 with pytest.raises(DataError):api().reconcile_dividends(e,(observation(amount=amount),))


@pytest.mark.parametrize('change',[
 {'symbol':[]},{'cusip':[]},{'aliases':[]},{'aliases':('NVDA','NVDA')},{'lineage_sha256':None},
])
def test_untrusted_identity_input_has_stable_refusal(change):
 e=api().read_action_evidence(encode(payload()));i=replace(identity(),**change)
 with pytest.raises(DataError,match='INVALID_ACTION_IDENTITY'):api().classify_actions(e,(i,))


def test_source_missing_fields_not_filled_from_provider():
 e=api().read_action_evidence(encode(payload()))
 r=json.loads(api().reconcile_dividends(e,(observation(cusip=None,record_date=None,payable_date=None,publication_bound=None),)).content)
 assert r['rows'][0]['state']=='PROVIDER_FIELDS_UNVERIFIED'
 assert r['rows'][0]['issues']==['SOURCE_PUBLICATION_UNVERIFIED']


def test_nonfinite_duplicate_keys_and_oversized_input_refused():
 v=encode(payload())
 for bad in (v.replace(b'"host":',b'"host":"https://data.alpaca.markets","host":'),b' '*1048577):
  with pytest.raises(DataError):api().read_action_evidence(bad)
 v=payload();edit_body(v,lambda b:b['corporate_actions']['cash_dividends'][0].update(rate=float('nan')))
 with pytest.raises(DataError,match='INVALID_PROVIDER_NUMBER'):api().read_action_evidence(encode(v))

def test_nested_unrecognized_fields_are_bounded_before_normalization():
 v=payload();nested='leaf'
 for _ in range(40):nested={'nested':nested}
 edit_body(v,lambda b:b['corporate_actions']['cash_dividends'][0].update(extension=nested))
 with pytest.raises(DataError,match='INPUT_BOUND'):api().read_action_evidence(encode(v))
