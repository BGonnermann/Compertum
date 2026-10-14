"""Actual cooperative collection and WinHTTP/DPAPI; loopback and 64 KiB reserve."""
from datetime import datetime,timezone
import time
import pytest
from compertum.data.encoding import canonical
from compertum.runtime.errors import RuntimeRefused
from compertum.runtime.paper_market_collection import _MarketCollection
from compertum.runtime.paper_market_evidence import publish_market_evidence,open_market_evidence
from compertum.runtime.service_budget import queue_for
from test_paper_read_owner import owner
from test_execution_health import pair
from test_paper_market_owner import prepare,authorize,start,status,send
from test_paper_market_collection import pages
from test_winhttp_get import server,start as native_start


@pytest.fixture
def native_market(owner,monkeypatch):
 import compertum.runtime.paper_market_owner as module
 o=owner;o.market_module=module;o.clock.utc=datetime.fromisoformat('2023-11-24T14:00:00+00:00').timestamp();o.market_port=None
 monkeypatch.setattr(module,'time',o.module.time)
 def collection(*a,**kw):
  assert o.market_port is not None
  return _MarketCollection(*a,**kw,_test_port=o.market_port,
    _test_clock=lambda:datetime.fromtimestamp(o.clock.utc,timezone.utc).isoformat(),_test_monotonic=lambda:o.clock.mono)
 monkeypatch.setattr(module,'_MarketCollection',collection)
 return o


def finish(o,p):
 deadline=time.monotonic()+8
 while time.monotonic()<deadline:
  o.a.tick();s=status(o,p)
  if s['state']!='RUNNING':return s
  time.sleep(.002)
 raise AssertionError('native market owner did not terminate')


@pytest.mark.parametrize('mode',['HISTORY','CURRENT_ACTIONS'])
def test_native_owner_collection_uses_genuine_permit_and_seals_exact_evidence(native_market,mode):
 o=native_market;body=canonical(dict(bars={'MSFT':[]},next_page_token=None) if mode=='HISTORY' else dict(corporate_actions={'cash_dividends':[]},next_page_token=None))
 with pages([body]) as (port,seen):
  o.market_port=port;p=prepare(o,mode=mode);authorize(o,p);start(o,p);s=finish(o,p)
  assert s['state']=='EVIDENCE_READY' and s['summary']['responses']==1 and len(seen)==1
  assert queue_for(o.e.lease).status()['data_used']==1 and queue_for(o.e.lease).status()['paper_used']==0
  assert all('APCA-API-KEY-ID' not in h for _,h in seen)
 cipher=o.a._market._cipher;grant=o.manager.split_grant(o.grant,len(cipher.ciphertext))
 manifest=publish_market_evidence(o.manager,grant,cipher)
 with open_market_evidence(o.e.lease,'fixture',p['job_id'],manifest) as opened:
  snap=opened.snapshot();assert snap['collection']['records'][0]['body_utf8'].encode()==body
  assert snap['collection']['native_provenance']=='LOOPBACK_FIXTURE' and snap['freshness']=='NOT_RESTORED'


def test_native_zero_response_cancel_is_preserved_as_failed_evidence(native_market):
 o=native_market
 with pages([]) as (port,seen):
  o.market_port=port;p=prepare(o);authorize(o,p);start(o,p);s=send(o,'cancel',job_id=p['job_id'])
  assert s['state']=='CANCELED' and s['summary']['responses']==s['summary']['attempts']==0 and not seen
 cipher=o.a._market._cipher;grant=o.manager.split_grant(o.grant,len(cipher.ciphertext));manifest=publish_market_evidence(o.manager,grant,cipher)
 with open_market_evidence(o.e.lease,'fixture',p['job_id'],manifest) as opened:
  assert opened.snapshot()['collection']['reason']=='CANCELLED'


def test_native_waiting_keeps_original_deadline_and_no_attempt(native_market):
 o=native_market
 with server(stall=True) as (blocking_port,arrived,seen),pages([]) as (port,data_seen):
  blocker=native_start(o.e.lease,blocking_port);assert arrived.wait(1)
  try:
   o.market_port=port;p=prepare(o);authorize(o,p);start(o,p);producer=o.a._market._producer
   original=producer._deadline_ns;o.a.tick()
   assert status(o,p)['summary']['attempts']==0 and queue_for(o.e.lease).status()['queued']==1
   o.clock.mono+=81;o.clock.utc+=81;o.a.tick();s=status(o,p)
   assert s['state']=='ABORTED' and s['summary']['reason']=='TOTAL_DEADLINE' and not data_seen
   assert producer._deadline_ns==original and s['grant_sha256']==p['grant_sha256'] and queue_for(o.e.lease).status()['queued']==0
  finally:blocker.close()


def test_native_uncertain_cancel_seals_before_disposal_and_blocks_checkpoint(native_market,monkeypatch):
 o=native_market
 with server(stall=True) as (port,arrived,seen):
  o.market_port=port;p=prepare(o);authorize(o,p);start(o,p);o.a.tick();assert arrived.wait(1)
  producer=o.a._market._producer;transport=producer._pending._transport
  try:
   with monkeypatch.context() as patch:
    patch.setattr(transport._closing,'wait',lambda _:False)
    with pytest.raises(RuntimeRefused,match='HTTP_CLEANUP_UNVERIFIED'):send(o,'cancel',job_id=p['job_id'])
    s=status(o,p);assert s['evidence'] is not None
    assert s['summary']['state']=='INCOMPLETE' and s['summary']['reason']=='NATIVE_CLEANUP_UNVERIFIED'
    assert o.a._market._producer is producer
    with pytest.raises(RuntimeRefused,match='MARKET_CHECKPOINT_BUSY'):o.a.require_checkpoint()
   o.a.close();assert transport.native_closed
  finally:
   if not o.a._closed:o.a.close()
