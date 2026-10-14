"""Private sequential market collection: native loopback and invented inputs only."""
from contextlib import contextmanager
from dataclasses import replace
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json,pickle,threading,time
from urllib.parse import urlparse,parse_qs
import pytest
from compertum.data.encoding import canonical
from compertum.runtime.errors import RuntimeRefused
from compertum.runtime.owners import _LEASES,release_owner
from compertum.runtime._winhttp_get import _PENDING
from compertum.runtime.paper_market_collection import _MarketCollection,_PrivateCollectionSnapshot
from compertum.runtime.paper_market_qualification import _PreparedMarketExchange
from test_winhttp_get import owner,server
from test_winhttp_data import plan,AT
from test_paper_market_qualification import credentials,KEY,SECRET

CID='12345678-1234-4234-8234-123456789012'
class Clock:
 def __init__(self):self.at=AT;self.mono=0.0
 def now(self):return self.at
 def monotonic(self):return self.mono

@contextmanager
def pages(bodies,statuses=None):
 seen=[]
 class Handler(BaseHTTPRequestHandler):
  def log_message(self,*a):pass
  def do_GET(self):
   n=len(seen);seen.append((self.path,dict(self.headers)))
   self.send_response((statuses or [200]*len(bodies))[n]);self.end_headers();self.wfile.write(bodies[n])
 http=ThreadingHTTPServer(('127.0.0.1',0),Handler);http.daemon_threads=True
 thread=threading.Thread(target=http.serve_forever,kwargs={'poll_interval':.01},daemon=True);thread.start()
 try:yield http.server_port,seen
 finally:http.shutdown();http.server_close();thread.join(2);assert not thread.is_alive()

def body(mode,token=None,rows=None):
 return canonical(dict(bars={'AAPL':rows or []},next_page_token=token)) if mode=='HISTORY' else canonical(dict(corporate_actions={'cash_dividends':rows or []},next_page_token=token))

def collection(owner,credentials,port,mode='HISTORY',clock=None,**edit):
 from test_winhttp_get import warm_budget
 warm_budget(owner)
 clock=clock or Clock();v=dict(collection_id=CID,mode=mode,_test_port=port,_test_clock=clock.now,_test_monotonic=clock.monotonic);v.update(edit)
 return _MarketCollection(owner,plan(owner),credentials,**v)

def finish(c):
 deadline=time.monotonic()+5
 while time.monotonic()<deadline:
  if c.poll():return
  time.sleep(.002)
 raise AssertionError('collection poll did not complete')

def run(c):
 deadline=time.monotonic()+15
 while c.status()['state']=='READY':
  assert time.monotonic()<deadline
  if c.dispatch()=='WAITING':time.sleep(.003)
  else:finish(c)
 return c.private_snapshot().to_payload()

def retained_replies(payload):
 if payload['version']==1:return payload['records']
 assert payload['version']==2
 return [dict(a['reply'],request=a['request'],dispatched_at=a['pre_send_at']) for a in payload['attempt_chain'] if a['reply'] is not None]

@pytest.mark.parametrize('mode',['HISTORY','CURRENT_ACTIONS'])
def test_eight_pages_preserve_exact_bytes_cursors_and_release_exchanges(owner,credentials,mode):
 bodies=[body(mode,str(i+1) if i<7 else None) for i in range(8)]
 with pages(bodies) as (port,seen):
  c=collection(owner,credentials,port,mode);p=run(c)
  assert p['state']=='PAGINATION_COMPLETE' and p['complete_by_cutoff'] is True and len(p['records'])==8
  assert [r['body_utf8'].encode() for r in p['records']]==bodies
  assert [parse_qs(urlparse(path).query).get('page_token') for path,_ in seen]==[None]+[[str(i)] for i in range(1,8)]
  assert len({r['request']['request_id'] for r in p['records']})==8
  assert all(r['diagnostic']['transport_provenance']=='LOOPBACK_FIXTURE' for r in p['records'])
  assert p['native_provenance']=='LOOPBACK_FIXTURE' and p['purpose']=='OPERATIONAL_ONLY'
  assert p['research_eligible'] is p['financial_accepted'] is p['transport_authorized'] is False
  assert p['aggregate']['status']=='BLOCKED' and not _PENDING
  assert not any(type(x) is _PreparedMarketExchange for x in _LEASES[owner].resources)
  assert len(seen)==8 and all('APCA-API-KEY-ID' not in h for _,h in seen)
 c.close()


def test_full_history_preserves_decimal_liquidity_diagnostic(owner,credentials):
 pp=plan(owner).to_payload();rows=[dict(t=t,o=100,h=102,l=99,c=100.125,v=20000) for t in pp['daily_labels']]
 bodies=[body('HISTORY',str(i+1) if i<2 else None,rows[i*100:(i+1)*100]) for i in range(3)]
 with pages(bodies) as (port,seen):
  p=run(collection(owner,credentials,port));h=p['aggregate']['history']
  assert h['complete'] and h['observed_sessions']==252 and h['mean_dollar_volume']=='2002500'
  assert 'ASSET_MISSING' in p['aggregate']['deficiencies'] and len(seen)==3

@pytest.mark.parametrize('mode',['HISTORY','CURRENT_ACTIONS'])
@pytest.mark.parametrize('failure',['missing_token','repeated_token','cap','shape','row_cap','http','secret','malformed'])
def test_terminal_incomplete_preserves_safe_pages_without_retry(owner,credentials,mode,failure):
 first=body(mode,'a')
 second={'missing_token':b'{"bars":{"AAPL":[]},"corporate_actions":{}}','repeated_token':body(mode,'a'),
 'shape':canonical(dict(bars=[],corporate_actions=[],next_page_token=None)),
 'row_cap':body(mode,None,[{}]*101),'http':b'{"message":"refused"}','secret':json.dumps({'unknown':KEY}).encode(),'malformed':b'{'}
 bodies=[body(mode,str(i+1)) for i in range(8)] if failure=='cap' else [first,second[failure]]
 statuses=[200,403] if failure=='http' else None
 with pages(bodies,statuses) as (port,seen):
  c=collection(owner,credentials,port,mode);p=run(c)
  assert p['state']=='INCOMPLETE' and not p['complete_by_cutoff'] and len(seen)==len(bodies)
  assert len(retained_replies(p))==(1 if failure in ('secret','malformed') else len(bodies))
  assert retained_replies(p)[0]['body_utf8'].encode()==bodies[0]
  assert KEY not in json.dumps(p) and SECRET not in json.dumps(p)
  with pytest.raises(RuntimeRefused):c.dispatch()
  assert len(seen)==len(bodies) and not _PENDING


def test_validation_after_cutoff_keeps_late_evidence(owner,credentials,monkeypatch):
 import compertum.runtime.paper_market_collection as module
 clock=Clock();clock.at='2026-10-09T13:24:59Z';original=module.qualify_market_inputs
 def late(*a,**kw):
  result=original(*a,**kw);clock.at='2026-10-09T13:25:00.000000001Z';return result
 monkeypatch.setattr(module,'qualify_market_inputs',late)
 with pages([body('HISTORY')]) as (port,_):
  c=collection(owner,credentials,port,clock=clock);c.dispatch();clock.at='2026-10-09T13:24:59.500000000Z';finish(c);p=c.private_snapshot().to_payload()
  assert p['state']=='INCOMPLETE' and p['reason']=='INFORMATION_CUTOFF' and len(retained_replies(p))==1
  assert retained_replies(p)[0]['validated_at']==clock.at and not p['complete_by_cutoff']

@pytest.mark.parametrize('at,ok',[('2026-10-09T13:25:00Z',True),('2026-10-09T13:25:00.000000001Z',False)])
def test_receipt_and_validation_exact_cutoff(owner,credentials,at,ok):
 clock=Clock();clock.at='2026-10-09T13:24:59Z'
 with pages([body('HISTORY')]) as (port,_):
  c=collection(owner,credentials,port,clock=clock);c.dispatch();clock.at=at;finish(c);p=c.private_snapshot().to_payload()
  assert p['complete_by_cutoff'] is ok and (p['state']=='PAGINATION_COMPLETE') is ok

@pytest.mark.parametrize('change',['wall_back','mono_back','mono_deadline','wrong_day','wall_cutoff'])
def test_clock_and_total_deadline_block_next_dispatch(owner,credentials,change):
 clock=Clock()
 with pages([body('HISTORY','next')]) as (port,seen):
  c=collection(owner,credentials,port,clock=clock);c.dispatch();finish(c)
  if change=='wall_back':clock.at='2026-10-09T13:19:59Z'
  elif change=='mono_back':clock.mono=-1
  elif change=='mono_deadline':clock.mono=80
  elif change=='wrong_day':clock.at='2026-10-12T13:20:00Z'
  else:clock.at='2026-10-09T13:25:00Z'
  with pytest.raises(RuntimeRefused):c.dispatch()
  assert c.status()['state']=='INCOMPLETE' and len(retained_replies(c.private_snapshot().to_payload()))==1 and len(seen)==1


def test_capacity_pending_cancel_revocation_and_private_snapshot(owner,credentials):
 with server(stall=True) as (port,arrived,seen):
  c=collection(owner,credentials,port)
  with pytest.raises(RuntimeRefused):collection(owner,credentials,port)
  with pytest.raises(RuntimeRefused):c.private_snapshot()
  c.dispatch();assert arrived.wait(1)
  with pytest.raises(RuntimeRefused):c.dispatch()
  c.cancel();snap=c.private_snapshot();assert snap.to_payload()['reason']=='CANCELLED'
  assert not _PENDING and len(seen)==1
  for obj in (c,snap):
   assert KEY not in repr(obj)
   with pytest.raises(RuntimeRefused):pickle.dumps(obj)
  release_owner(owner)
  with pytest.raises(RuntimeRefused):snap.to_payload()
  assert c._closed


def test_uncertain_cleanup_remains_explicit_and_recoverable(owner,credentials,monkeypatch):
 with server(stall=True) as (port,arrived,_):
  c=collection(owner,credentials,port);c.dispatch();assert arrived.wait(1);t=c._pending._transport
  with monkeypatch.context() as patch:
   patch.setattr(t._closing,'wait',lambda _:False)
   with pytest.raises(RuntimeRefused,match='HTTP_CLEANUP_UNVERIFIED'):c.cancel()
   assert not t.native_closed and _PENDING
   p=c.private_snapshot().to_payload();assert p['reason']=='NATIVE_CLEANUP_UNVERIFIED' and p['attempt_chain'][0]['native_closed'] is False
  c.close();assert t.native_closed and not _PENDING

@pytest.mark.parametrize('change',['plan','envelope','collection_id','mode'])
def test_context_changes_fail_closed(owner,credentials,change):
 with pages([body('HISTORY')]) as (port,seen):
  c=collection(owner,credentials,port)
  if change=='plan':object.__setattr__(c._plan,'content',b'{}')
  elif change=='envelope':object.__setattr__(credentials,'ciphertext',b'changed')
  elif change=='collection_id':c._collection_id='22345678-1234-4234-8234-123456789012'
  else:c._mode='CURRENT_ACTIONS'
  with pytest.raises(RuntimeRefused):c.dispatch()
  assert not seen and not _PENDING


def test_invalid_contexts_and_fixture_hooks_never_start_real_transport(owner,credentials,monkeypatch):
 import compertum.runtime._winhttp_get as native
 monkeypatch.setattr(native,'_API',lambda:pytest.fail('native call'))
 for edit in ({'_test_port':None},{'mode':'QUOTE'},{'collection_id':'bad'},{'_test_port':True}):
  with pytest.raises(RuntimeRefused):collection(owner,credentials,12345,**edit)
 for p in (replace(credentials,project_id='b'*64),replace(credentials,account_alias='other')):
  with pytest.raises(RuntimeRefused):collection(owner,p,12345)
 with pytest.raises(RuntimeRefused):_PrivateCollectionSnapshot()


@pytest.mark.parametrize('mode',['HISTORY','CURRENT_ACTIONS'])
def test_large_safe_pages_are_retained_with_existing_body_limits(owner,credentials,mode):
 bodies=[]
 for i in range(8):
  value=json.loads(body(mode,str(i+1) if i<7 else None));value['retained_unknown']='safe'*10000
  raw=canonical(value);assert len(raw)<65536;bodies.append(raw)
 with pages(bodies) as (port,seen):
  c=collection(owner,credentials,port,mode);p=run(c)
  assert p['state']=='PAGINATION_COMPLETE' and len(p['records'])==8 and len(seen)==8
  assert [r['body_utf8'].encode() for r in p['records']]==bodies
  assert len(c.private_snapshot().content)>65536


@pytest.mark.parametrize('offset',[2040,2555,4090])
def test_generated_metadata_chunk_boundaries_cannot_hide_reflection(offset):
 from compertum.runtime.paper_market_collection import _scan_generated
 with pytest.raises(RuntimeRefused,match='PAPER_READ_SECRET_REFLECTION'):_scan_generated({'large':'x'*offset+KEY+'x'*65536},(KEY,SECRET))


@pytest.mark.parametrize('stage,change',[('prepare','cutoff'),('prepare','total'),('native_setup','cutoff')])
def test_review_no_dispatch_after_preparation_or_native_setup_budget(owner,credentials,monkeypatch,stage,change):
 import compertum.runtime.paper_market_collection as module
 import compertum.runtime._winhttp_get as native
 clock=Clock();clock.at='2026-10-09T13:24:59Z'
 def advance():
  if change=='cutoff':clock.at='2026-10-09T13:25:00Z'
  else:clock.mono=80
 target=module if stage=='prepare' else native;name='prepare_market_exchange' if stage=='prepare' else '_API';original=getattr(target,name)
 def delayed(*a,**kw):
  value=original(*a,**kw);advance();return value
 monkeypatch.setattr(target,name,delayed)
 with pages([body('HISTORY')]) as (port,seen):
  c=collection(owner,credentials,port,clock=clock)
  with pytest.raises(RuntimeRefused):c.dispatch()
  assert not seen and c.status()['state']=='INCOMPLETE' and not _PENDING


def test_review_preparation_uses_absolute_native_deadline(owner,credentials,monkeypatch):
 import compertum.runtime.paper_market_collection as module
 clock=Clock();clock.at='2026-10-09T13:24:59.950000Z';original=module.start_market_exchange
 def delayed(*a,**kw):time.sleep(.08);return original(*a,**kw)
 monkeypatch.setattr(module,'start_market_exchange',delayed)
 with pages([body('HISTORY')]) as (port,seen):
  c=collection(owner,credentials,port,clock=clock)
  with pytest.raises(RuntimeRefused):c.dispatch()
  assert not seen and not _PENDING

@pytest.mark.parametrize('field',['raw','aggregate','state','validated_at'])
def test_review_changed_retained_data_cannot_be_snapshotted(owner,credentials,field):
 with pages([body('HISTORY')]) as (port,_):
  c=collection(owner,credentials,port);c.dispatch();finish(c)
  if field=='raw':row=c._records[0];c._records[0]=(row[0],b'{}',row[2],row[3])
  elif field=='aggregate':c._aggregate=b'{}'
  elif field=='state':c._state='INCOMPLETE'
  else:row=c._records[0];c._records[0]=(*row[:3],'2026-10-09T13:20:01Z')
  with pytest.raises(RuntimeRefused):c.private_snapshot()


def test_review_generated_reflection_is_not_retained_and_safe_records_survive(owner):
 from compertum.runtime.paper_credentials import seal_paper_credentials
 protected=seal_paper_credentials(owner,'paper-primary',bytearray(b'HISTORY_ROWS_MISSING'),bytearray(SECRET.encode()))
 with pages([body('HISTORY')]) as (port,_):
  c=collection(owner,protected,port);c.dispatch();finish(c)
  assert c._aggregate is None
  p=c.private_snapshot().to_payload();assert p['state']=='INCOMPLETE' and len(retained_replies(p))==1
  assert 'HISTORY_ROWS_MISSING' not in c.private_snapshot().content.decode()



def test_native_dispatch_timestamp_and_post_snapshot_integrity(owner,credentials,monkeypatch):
 import compertum.runtime.paper_market_collection as module
 clock=Clock();original=module.prepare_market_exchange
 def delayed(*a,**kw):
  result=original(*a,**kw);clock.at='2026-10-09T13:20:01Z';return result
 monkeypatch.setattr(module,'prepare_market_exchange',delayed)
 with pages([body('HISTORY')]) as (port,_):
  c=collection(owner,credentials,port,clock=clock);c.dispatch();finish(c);snapshot=c.private_snapshot();p=snapshot.to_payload()
  row=p['records'][0];assert row['request']['created_at']==AT and row['dispatched_at']==clock.at
  c._aggregate=b'{}'
  with pytest.raises(RuntimeRefused):snapshot.content


@pytest.mark.parametrize('field,value',[('_started_at','2000-01-01T00:00:00Z'),('_start_mono',-999),('_real_started',10**10)])
def test_review_published_start_and_deadline_anchors_are_bound(owner,credentials,field,value):
 with pages([body('HISTORY')]) as (port,_):
  c=collection(owner,credentials,port);c.dispatch();finish(c);setattr(c,field,value)
  with pytest.raises(RuntimeRefused):c.private_snapshot()
