"""Fresh asset and quote pair: invented credentials and native local requests."""
from dataclasses import replace
from uuid import uuid4
import json,pickle
import pytest
from compertum.data.encoding import canonical
from compertum.paper_market_inputs import prepare_market_request
from compertum.runtime.errors import RuntimeRefused
from compertum.runtime.owners import _LEASES,release_owner
from compertum.runtime.paper_credentials import seal_paper_credentials
from compertum.runtime.paper_market_qualification import prepare_market_exchange,start_market_exchange,qualify_market_reply
from compertum.runtime.paper_market_fresh import _MarketFresh
from compertum.runtime._winhttp_asset import _OwnedAssetGet
from compertum.runtime._winhttp_data import _OwnedDataGet
from test_winhttp_get import owner,finish as http_finish
from test_paper_market_qualification import credentials
import test_paper_market_collection as f

AT='2026-10-09T13:35:00Z'
def asset(**kw):
 p=dict(id='12345678-1234-4234-8234-123456789099',symbol='AAPL',exchange='NASDAQ',status='active',tradable=True);p['class']='us_equity';p.update(kw);return canonical(p)
def quote(**kw):
 p=dict(t=AT,bp=100.125,ap=100.25,bs=10,**{'as':20},bx='V',ax='V');p.update(kw);return canonical(dict(quotes={'AAPL':p}))
def pair(owner,credentials,port,clock=None,**kw):
 clock=clock or f.Clock();clock.at=AT if clock.at==f.AT else clock.at
 return _MarketFresh(owner,f.plan(owner),credentials,pair_id=f.CID,_test_port=port,_test_clock=clock.now,_test_monotonic=clock.monotonic,**kw)
def run(p):
 while p.status()['state']=='READY':p.dispatch();f.finish(p)
 return p.private_snapshot()


def test_exact_native_asset_route_and_private_exchange(owner,credentials):
 req=prepare_market_request(f.plan(owner),operation='ASSET',request_id=str(uuid4()),created_at=AT)
 with f.pages([asset()]) as (port,seen):
  x=prepare_market_exchange(owner,credentials,req);t=start_market_exchange(x,_test_port=port);result=http_finish(t)
  assert type(t) is _OwnedAssetGet and seen[0][0]=='/v2/assets/AAPL'
  r=qualify_market_reply(owner,credentials,x,result.body,status=result.status_code,received_at=AT,result=result)
  assert r.raw==asset() and r.to_payload()['transport_provenance']=='LOOPBACK_FIXTURE' and r.to_payload()['operation']=='ASSET'
  assert r.to_payload()['credential_dispatch_binding']=='NOT_SENT_FIXTURE'

@pytest.mark.parametrize('operation',['QUOTE','HISTORY'])
def test_asset_adapter_rejects_other_operations_before_native(owner,monkeypatch,operation):
 from compertum.runtime import _winhttp_get as native
 monkeypatch.setattr(native,'_API',lambda:pytest.fail('native dispatch of wrong operation'))
 req=prepare_market_request(f.plan(owner),operation=operation,request_id=str(uuid4()),created_at=AT)
 with pytest.raises(RuntimeRefused):_OwnedAssetGet(owner,request=req,headers={'X-Compertum-Test':'synthetic'},_test_port=12345)


def test_pair_retains_originals_and_requalifies_at_use_after_cutoff(owner,credentials):
 clock=f.Clock()
 with f.pages([asset(),quote()]) as (port,seen):
  p=pair(owner,credentials,port,clock);view=run(p);v=view.to_payload()
  assert [x[0] for x in seen]==['/v2/assets/AAPL','/v2/stocks/quotes/latest?symbols=AAPL&feed=iex&currency=USD']
  assert v['state']=='PAIR_COMPLETE' and [r['body_utf8'].encode() for r in v['records']]==[asset(),quote()]
  assert v['diagnostic']['asset']['valid'] and v['diagnostic']['quote']['valid']
  assert v['diagnostic']['quote']['bid']=='100.125' and 'HISTORY_ROWS_MISSING' in v['diagnostic']['deficiencies']
  assert v['financial_accepted'] is v['transport_authorized'] is v['research_eligible'] is False
  clock.at='2026-10-09T13:35:30Z';clock.mono=30;assert view.to_payload()['diagnostic']['quote']['valid']
  clock.at='2026-10-09T13:35:30.000000001Z';clock.mono=30.000000001;late=view.to_payload()['diagnostic'];assert not late['quote']['valid'] and not late['asset']['valid']
  for obj in (p,view):
   with pytest.raises(RuntimeRefused):pickle.dumps(obj)
   assert f.KEY not in repr(obj)
  p.close()
  with pytest.raises(RuntimeRefused):view.to_payload()

@pytest.mark.parametrize('change,code',[({'t':'2026-10-09T13:35:00.000000001Z'},'QUOTE_FUTURE'),({'bp':101,'ap':100},'QUOTE_PRICE_INVALID'),({'bp':0},'QUOTE_PRICE_INVALID'),({'bx':'N'},'QUOTE_VENUE_MISMATCH')])
def test_quote_issues_stay_blocked(owner,credentials,change,code):
 with f.pages([asset(),quote(**change)]) as (port,_):v=run(pair(owner,credentials,port)).to_payload()
 assert code in v['diagnostic']['deficiencies'] and not v['diagnostic']['quote']['valid']

@pytest.mark.parametrize('change',[{'status':'inactive'},{'tradable':False},{'symbol':'MSFT'}])
def test_asset_issues_stay_blocked(owner,credentials,change):
 with f.pages([asset(**change),quote()]) as (port,_):v=run(pair(owner,credentials,port)).to_payload()
 assert v['diagnostic'] is None or not v['diagnostic']['asset']['valid']
 assert not v['financial_accepted']

@pytest.mark.parametrize('failure',['http','malformed','secret','cancel','total'])
def test_partial_failure_keeps_only_safe_records(owner,credentials,failure):
 clock=f.Clock();second={'http':b'{"message":"refused"}','malformed':b'{','secret':canonical(dict(message=f.KEY))}.get(failure,quote())
 with f.pages([asset(),second],[200,403] if failure=='http' else None) as (port,seen):
  p=pair(owner,credentials,port,clock);p.dispatch();f.finish(p)
  if failure=='cancel':p.cancel()
  elif failure=='total':
   clock.mono=20;clock.at='2026-10-09T13:35:20Z'
   with pytest.raises(RuntimeRefused):p.dispatch()
  else:p.dispatch();f.finish(p)
  v=p.private_snapshot().to_payload();assert v['state']=='INCOMPLETE' and v['records'][0]['body_utf8'].encode()==asset()
  assert len(v['records'])==(2 if failure=='http' else 1)
  assert f.KEY not in json.dumps(v)
  with pytest.raises(RuntimeRefused):p.dispatch()

@pytest.mark.parametrize('field',['_pair_id','_plan','_credential_sha','_started_at','_start_mono','_real_started','_records','_state'])
def test_private_state_changes_are_rejected(owner,credentials,field):
 with f.pages([asset(),quote()]) as (port,_):
  p=pair(owner,credentials,port);run(p)
  old=getattr(p,field);setattr(p,field,[] if field=='_records' else 'changed')
  with pytest.raises(RuntimeRefused):p.private_snapshot().to_payload()
  setattr(p,field,old)


def test_capacity_pending_and_owner_revocation(owner,credentials):
 with f.pages([asset(),quote()]) as (port,_):
  p=pair(owner,credentials,port)
  with pytest.raises(RuntimeRefused):pair(owner,credentials,port)
  p.dispatch()
  with pytest.raises(RuntimeRefused):p.dispatch()
  f.finish(p);p.dispatch();f.finish(p);v=p.private_snapshot();release_owner(owner)
  with pytest.raises(RuntimeRefused):v.to_payload()

@pytest.mark.parametrize('at',['2026-10-09T13:34:59Z','2026-10-10T13:35:00Z'])
def test_private_view_refuses_backward_or_wrong_day_clock(owner,credentials,at):
 clock=f.Clock()
 with f.pages([asset(),quote()]) as (port,_):p=pair(owner,credentials,port,clock);v=run(p)
 clock.at=at
 with pytest.raises(RuntimeRefused):v.to_payload()

@pytest.mark.parametrize('stage',['prepare','native_setup','validation'])
def test_setup_and_validation_count_against_total_budget(owner,credentials,monkeypatch,stage):
 import compertum.runtime.paper_market_fresh as module
 import compertum.runtime._winhttp_get as native
 clock=f.Clock();target=native if stage=='native_setup' else module
 name={'prepare':'prepare_market_exchange','native_setup':'_API','validation':'qualify_market_inputs'}[stage];original=getattr(target,name)
 def delayed(*a,**kw):
  value=original(*a,**kw);clock.mono=20;return value
 monkeypatch.setattr(target,name,delayed)
 with f.pages([asset()]) as (port,seen):
  p=pair(owner,credentials,port,clock)
  if stage=='validation':p.dispatch();f.finish(p)
  else:
   with pytest.raises(RuntimeRefused):p.dispatch()
  assert p.status()['state']=='INCOMPLETE' and len(seen)==(1 if stage=='validation' else 0)


def test_absolute_deadline_covers_native_start_delay(owner,credentials,monkeypatch):
 import time
 import compertum.runtime.paper_market_fresh as module
 clock=f.Clock();original=module.start_market_exchange
 def delayed(*a,**kw):time.sleep(.03);return original(*a,**kw)
 monkeypatch.setattr(module,'start_market_exchange',delayed)
 with f.pages([asset()]) as (port,seen):
  p=pair(owner,credentials,port,clock);clock.mono=19.99
  with pytest.raises(RuntimeRefused):p.dispatch()
  assert not seen and p.status()['state']=='INCOMPLETE'


def test_actual_dispatch_time_is_distinct_from_creation(owner,credentials,monkeypatch):
 import compertum.runtime.paper_market_fresh as module
 clock=f.Clock();original=module.prepare_market_exchange
 def delayed(*a,**kw):
  result=original(*a,**kw);clock.at='2026-10-09T13:35:01Z';return result
 monkeypatch.setattr(module,'prepare_market_exchange',delayed)
 with f.pages([asset(),quote()]) as (port,_):v=run(pair(owner,credentials,port,clock)).to_payload()
 assert v['records'][0]['request']['created_at']==AT and v['records'][0]['dispatched_at']==clock.at


def test_uncertain_cleanup_retains_pending_until_native_close(owner,credentials,monkeypatch):
 from compertum.runtime._winhttp_get import _PENDING
 with f.server(stall=True) as (port,arrived,_):
  p=pair(owner,credentials,port);p.dispatch();assert arrived.wait(1);t=p._pending._transport
  with monkeypatch.context() as patch:
   patch.setattr(t._closing,'wait',lambda _:False)
   with pytest.raises(RuntimeRefused,match='HTTP_CLEANUP_UNVERIFIED'):p.cancel()
   assert not t.native_closed and _PENDING
   with pytest.raises(RuntimeRefused):p.private_snapshot()
  p.close();assert t.native_closed and not _PENDING


def test_test_hooks_and_wrong_identity_refused_before_native(owner,credentials,monkeypatch):
 import compertum.runtime._winhttp_get as native
 monkeypatch.setattr(native,'_API',lambda:pytest.fail('unexpected native call'))
 with pytest.raises(RuntimeRefused):_MarketFresh(owner,f.plan(owner),credentials,pair_id=f.CID,_test_clock=lambda:AT)
 for changed in (replace(credentials,project_id='f'*64),replace(credentials,account_alias='wrong')):
  with pytest.raises(RuntimeRefused):pair(owner,changed,12345)


def test_generated_reflection_keeps_safe_original_without_diagnostic(owner):
 c=seal_paper_credentials(owner,'paper-primary',bytearray(b'HISTORY_ROWS_MISSING'),bytearray(f.SECRET.encode()))
 with f.pages([asset()]) as (port,_):v=run(pair(owner,c,port))
 data=v.to_payload();assert data['diagnostic'] is None and len(data['records'])==1
 assert b'HISTORY_ROWS_MISSING' not in v.content

@pytest.mark.parametrize('location',['raw','escaped'])
def test_asset_reflection_is_rejected_before_any_retention(owner,credentials,location):
 raw=canonical(dict(message=f.KEY)) if location=='raw' else ('{"unknown":"'+''.join('\\u%04x'%ord(x) for x in f.KEY)+'"}').encode()
 with f.pages([raw]) as (port,_):v=run(pair(owner,credentials,port)).to_payload()
 assert v['state']=='INCOMPLETE' and v['records']==[] and f.KEY not in json.dumps(v)


def test_native_asset_cannot_qualify_copied_result(owner,credentials):
 req=prepare_market_request(f.plan(owner),operation='ASSET',request_id=str(uuid4()),created_at=AT)
 with f.pages([asset()]) as (port,_):
  x=prepare_market_exchange(owner,credentials,req);op=start_market_exchange(x,_test_port=port);result=http_finish(op)
  with pytest.raises(RuntimeRefused):qualify_market_reply(owner,credentials,x,result.body,status=200,received_at=AT,result=replace(result))

@pytest.mark.parametrize('status',[403,404,422,500])
def test_native_asset_http_refusals_remain_private_observations(owner,credentials,status):
 with f.pages([b'{"message":"refused"}'],[status]) as (port,_):v=run(pair(owner,credentials,port)).to_payload()
 assert v['state']=='INCOMPLETE' and v['records'][0]['diagnostic']['status']==status and not v['financial_accepted']


def test_two_large_original_replies_remain_bounded(owner,credentials):
 bodies=[]
 for raw in (asset(),quote()):
  v=json.loads(raw);v['unknown_padding']='safe'*12000;bodies.append(canonical(v))
 with f.pages(bodies) as (port,_):v=run(pair(owner,credentials,port))
 assert [r['body_utf8'].encode() for r in v.to_payload()['records']]==bodies and 65536<len(v.content)<=524288

@pytest.mark.parametrize('stage',['qualification','scan'])
def test_review_mutation_during_diagnostic_never_returns_or_reseals(owner,credentials,monkeypatch,stage):
 import compertum.runtime.paper_market_fresh as module
 with f.pages([asset(),quote()]) as (port,_):p=pair(owner,credentials,port);view=run(p)
 old=p._state_sha
 if stage=='qualification':
  original=module.qualify_market_inputs
  def mutate(*a,**kw):value=original(*a,**kw);p._records.clear();return value
  monkeypatch.setattr(module,'qualify_market_inputs',mutate)
 else:
  original=p._scan
  def mutate(value):original(value);p._records.clear()
  monkeypatch.setattr(p,'_scan',mutate)
 with pytest.raises(RuntimeRefused):view.to_payload()
 assert p._state_sha==old
 with pytest.raises(RuntimeRefused):p.status()

@pytest.mark.parametrize('mono',[31,-1])
def test_review_diagnostic_rejects_stalled_or_regressing_elapsed_clock(owner,credentials,mono):
 clock=f.Clock()
 with f.pages([asset(),quote()]) as (port,_):p=pair(owner,credentials,port,clock);view=run(p)
 clock.mono=mono
 with pytest.raises(RuntimeRefused):view.to_payload()


def test_elapsed_clock_conservatively_ages_quote_within_allowed_clock_drift(owner,credentials):
 clock=f.Clock()
 with f.pages([asset(),quote()]) as (port,_):p=pair(owner,credentials,port,clock);view=run(p)
 clock.at='2026-10-09T13:35:29Z';clock.mono=31
 v=view.to_payload()
 assert v['observed_at']==clock.at and v['age_basis_at']=='2026-10-09T13:35:31.000000000Z'
 assert not v['diagnostic']['quote']['valid'] and not v['diagnostic']['asset']['valid']
