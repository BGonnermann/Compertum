"""Owner integration: real local ASSET/QUOTE, published HISTORY, private composition."""
from datetime import datetime,timezone
from uuid import uuid4
import json,time
import pytest
from compertum.data.encoding import canonical
from compertum.runtime.errors import RuntimeRefused
from compertum.runtime.paper_market_fresh import _MarketFresh
from compertum.runtime.service_budget import queue_for
from test_execution_health import pair
from test_paper_read_owner import owner
from test_paper_market_owner_native import native_market
from test_paper_market_publication import publication,command,prepare,start,until
from test_paper_market_collection import pages
from test_paper_read_preparation import KEY,SECRET


@pytest.fixture
def history(publication,monkeypatch):
 o=publication;p=prepare(o)
 rows=[dict(t=t,o=100,h=102,l=99,c=100.125,v=20000) for t in p['plan']['daily_labels']]
 responses=[canonical(dict(bars={'MSFT':rows[i*100:(i+1)*100]},next_page_token=str(i+1) if i<2 else None)) for i in range(3)]
 with pages(responses) as (port,seen):
  o.market_port=port;start(o,p);until(o,p,'DONE');assert len(seen)==3
 status=command(o,'status',job_id=p['job_id']);assert status['summary']['state']=='PAGINATION_COMPLETE'
 from compertum.runtime.paper_market_evidence import open_market_evidence
 with open_market_evidence(o.e.lease,'fixture',p['job_id'],status['manifest']) as opened:
  snapshot=opened.snapshot()['collection'];assert snapshot['complete_by_cutoff'] and snapshot['state']=='PAGINATION_COMPLETE'
 o.history=p;o.clock.utc+=2100;o.clock.mono+=2100
 def fresh(*a,**kw):
  record=o.a._market.records.read(kw['pair_id'])
  assert record['consumed'] and record['state']=='RUNNING' and not o.a.db.in_transaction
  return _MarketFresh(*a,**kw,_test_port=o.market_port,
   _test_clock=lambda:datetime.fromtimestamp(o.clock.utc,timezone.utc).isoformat(),_test_monotonic=lambda:o.clock.mono)
 monkeypatch.setattr(o.market_module,'_MarketFresh',fresh,raising=False)
 return o


def fresh_prepare(o,**changes):
 fields=dict(job_id=str(uuid4()),account_alias='fixture',mode='FRESH',symbol='MSFT',history_job_id=o.history['job_id']);fields.update(changes)
 return command(o,'prepare',**fields)


def bodies(o):
 at=datetime.fromtimestamp(o.clock.utc,timezone.utc).isoformat()
 asset=dict(id=str(uuid4()),symbol='MSFT',exchange='NASDAQ',status='active',tradable=True);asset['class']='us_equity'
 quote=dict(t=at,bp=100.125,ap=100.25,bs=10,bx='V',ax='V');quote['as']=20
 return [canonical(asset),canonical(dict(quotes={'MSFT':quote}))]


def finish(o,p):
 deadline=time.monotonic()+8
 while time.monotonic()<deadline:
  o.a.tick();o.pub.tick();s=command(o,'status',job_id=p['job_id'])
  if s['state']!='RUNNING':return s
  time.sleep(.002)
 raise AssertionError('fresh owner did not terminate')


def completed(o):
 p=fresh_prepare(o)
 with pages(bodies(o)) as (port,seen):
  o.market_port=port;start(o,p);s=finish(o,p)
  assert s['state']=='COMPLETE' and len(seen)==2
 return p,s


def test_fresh_reuses_exact_old_plan_without_reservation_and_composes_at_use(history):
 o=history;before=o.manager.store.conn.execute('SELECT count(*) FROM reservations').fetchone();p,s=completed(o)
 assert p['plan']==o.history['plan'] and p['plan_sha256']==o.history['plan_sha256']
 g=o.a._market.records.read(p['job_id'])['grant'];assert g['reservation_id'] is None and g['created_at']>g['plan']['history_cutoff_at']
 assert o.manager.store.conn.execute('SELECT count(*) FROM reservations').fetchone()==before
 assert s['evidence'] is s['manifest'] is None and s['publication']['state']=='NO_EVIDENCE'
 result=command(o,'compose',job_id=p['job_id']);v=result['composition']
 assert v['history_job_id']==o.history['job_id'] and v['observed_sessions']==252 and v['observed_conditions_met']
 assert v['asset_valid'] and v['quote_valid'] and v['status']=='BLOCKED'
 assert all(v[k] is False for k in ('financial_accepted','transport_authorized','research_eligible'))
 raw=canonical(result);assert len(raw)<65536 and all(x.encode() not in raw for x in (KEY,SECRET,'"body_utf8":','"bid":','"ask":'))
 q=queue_for(o.e.lease).status();assert q['paper_used']==1 and q['data_used']==4
 assert start(o,p)['state']=='COMPLETE'
 o.clock.utc+=31;o.clock.mono+=31
 late=command(o,'compose',job_id=p['job_id'])['composition']
 assert not late['quote_valid'] and not late['asset_valid'] and not late['observed_conditions_met']
 assert late['age_basis_at']!=v['age_basis_at']
 stale=command(o,'status',job_id=p['job_id'])['fresh'];assert not stale['quote_valid'] and stale['age_basis_at']==late['age_basis_at']


@pytest.mark.parametrize('fault',['subject','alias','symbol','unknown_history','current_actions','missing_manifest'])
def test_fresh_history_mismatch_refused_before_execution_or_allocation(history,fault):
 o=history;before=len(o.rpc);rows=o.manager.store.conn.execute('SELECT count(*) FROM reservations').fetchone()
 changes={}
 if fault=='subject':changes['subject']='b'*64
 elif fault=='alias':changes['account_alias']='other'
 elif fault=='symbol':changes['symbol']='AAPL'
 elif fault=='unknown_history':changes['history_job_id']=str(uuid4())
 else:
  route=o.pub._route(o.history['job_id'])
  if fault=='current_actions':route['mode']='CURRENT_ACTIONS'
  else:route['publication']=dict(state='FAILED',reason='INJECTED_FAILURE',manifest=None)
  with o.pub.db:o.pub.db.execute('UPDATE state SET value=? WHERE key=?',(canonical(route).decode(),'paper_market_route:'+o.history['job_id']))
 with pytest.raises(RuntimeRefused):fresh_prepare(o,**changes)
 assert len(o.rpc)==before and o.manager.store.conn.execute('SELECT count(*) FROM reservations').fetchone()==rows


@pytest.mark.parametrize('delta',[60,-1])
def test_fresh_own_start_lifetime_is_not_renewed_by_historical_plan(history,delta):
 o=history;p=fresh_prepare(o);command(o,'authorize',job_id=p['job_id'],grant_sha256=p['grant_sha256'])
 o.clock.utc+=delta;o.clock.mono+=delta
 with pytest.raises(RuntimeRefused,match='MARKET_GRANT_EXPIRED'):command(o,'start',job_id=p['job_id'],grant_sha256=p['grant_sha256'])
 assert not o.a._market.records.read(p['job_id'])['consumed']


def test_cancel_revokes_private_views_and_allows_new_explicit_job(history):
 o=history;p,_=completed(o);command(o,'compose',job_id=p['job_id']);view=o.a._market._combined
 with pytest.raises(RuntimeRefused,match='MARKET_CHECKPOINT_BUSY'):o.a.require_checkpoint()
 with pytest.raises(RuntimeRefused):fresh_prepare(o)
 assert command(o,'cancel',job_id=p['job_id'])['state']=='CANCELED'
 with pytest.raises(RuntimeRefused):view.to_payload()
 with pytest.raises(RuntimeRefused):command(o,'compose',job_id=p['job_id'])
 o.a.require_checkpoint();assert fresh_prepare(o)['state']=='PREPARED'


def test_completed_fresh_views_do_not_survive_owner_recreation(history):
 o=history;p,_=completed(o);command(o,'compose',job_id=p['job_id']);view=o.a._market._combined
 o.a.close();o.a=o.module.PaperReadOwner(o.a.store,o.a.reserve,o.e)
 assert command(o,'status',job_id=p['job_id'])['state']=='INTERRUPTED'
 with pytest.raises(RuntimeRefused):command(o,'compose',job_id=p['job_id'])
 with pytest.raises(RuntimeRefused):view.to_payload()


def test_fresh_waiting_uses_original_deadline_and_no_extra_attempt(history,monkeypatch):
 o=history;p=fresh_prepare(o);q=queue_for(o.e.lease)
 monkeypatch.setattr(q,'_claim',lambda *a,**kw:None)
 with pages(bodies(o)) as (port,seen):
  o.market_port=port;start(o,p);o.a.tick();assert not seen
  o.clock.utc+=21;o.clock.mono+=21;o.a.tick()
  s=command(o,'status',job_id=p['job_id']);assert s['state']=='ABORTED' and s['summary']['attempts']==0 and not seen
 assert s['evidence'] is None and s['manifest'] is None


@pytest.mark.parametrize('fault',['health','credential'])
def test_current_context_failure_revokes_complete_private_views_before_return(history,monkeypatch,fault):
 o=history;p,_=completed(o);command(o,'compose',job_id=p['job_id']);view=o.a._market._combined
 if fault=='health':o.e.halt('FIXTURE_HEALTH_LOST')
 else:
  from compertum.runtime.paper_credentials import seal_paper_credentials
  changed=seal_paper_credentials(o.e.lease,'fixture',bytearray(KEY.encode()),bytearray(SECRET.encode()))
  monkeypatch.setattr(o.market_module,'load_paper_slot',lambda *a:changed)
 with pytest.raises(RuntimeRefused):command(o,'status',job_id=p['job_id'])
 assert o.a._market.records.read(p['job_id'])['state']=='INTERRUPTED'
 with pytest.raises(RuntimeRefused):view.to_payload()
 assert o.a._market._producer is None and o.a._market._opened is None


def test_failed_published_history_cannot_start_fresh_reads(publication):
 o=publication;p=prepare(o)
 with pages([b'{']) as (port,seen):
  o.market_port=port;start(o,p);until(o,p,'DONE');assert len(seen)==1
 assert command(o,'status',job_id=p['job_id'])['summary']['state']=='INCOMPLETE'
 o.history=p;o.clock.utc+=2100;o.clock.mono+=2100
 fresh=fresh_prepare(o)
 with pages(bodies(o)) as (port,seen):
  o.market_port=port;s=start(o,fresh)
  assert s['state']=='ABORTED' and s['reason']=='MARKET_HISTORY_REQUIRED' and not seen
 assert o.a._market._producer is None and o.a._market._opened is None


def test_fresh_uncertain_native_close_keeps_owner_and_checkpoint_blocked(history,monkeypatch):
 o=history;p=fresh_prepare(o)
 with pages(bodies(o)) as (port,seen):
  o.market_port=port;start(o,p);o.a.tick();producer=o.a._market._producer;pending=producer._pending;close=type(pending).close
  def fail(value):
   if value is pending:raise RuntimeRefused('HTTP_CLEANUP_UNVERIFIED')
   return close(value)
  monkeypatch.setattr(type(pending),'close',fail)
  with pytest.raises(RuntimeRefused):command(o,'cancel',job_id=p['job_id'])
  assert o.a._market._producer is producer and producer._pending is pending
  assert o.a._market._opened is None and o.a._market._fresh_view is None
  with pytest.raises(RuntimeRefused,match='MARKET_CHECKPOINT_BUSY'):o.a.require_checkpoint()
  with pytest.raises(RuntimeRefused):o.module.PaperReadOwner(o.a.store,o.a.reserve,o.e)
  monkeypatch.setattr(type(pending),'close',close);o.a.close()
  assert producer._pending is None


@pytest.mark.parametrize('operation,delta',[('status',6),('compose',6),('status',-1),('compose',86400)])
def test_completed_view_clock_error_revokes_without_revalidating_poisoned_producer(history,operation,delta):
 o=history;p,_=completed(o);command(o,'compose',job_id=p['job_id']);view=o.a._market._combined
 o.clock.utc+=delta
 with pytest.raises(RuntimeRefused):command(o,operation,job_id=p['job_id'])
 assert o.a._market.records.read(p['job_id'])['state']=='INTERRUPTED'
 assert o.a._market._producer is None and o.a._market._opened is None
 with pytest.raises(RuntimeRefused):view.to_payload()
 o.a.require_checkpoint();o.a.close()
