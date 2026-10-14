"""Reproductions from integration review; injected API only."""
from contextlib import contextmanager
from datetime import datetime,timezone
from types import SimpleNamespace
from uuid import UUID
import time
import pytest
from compertum.paper_market_inputs import prepare_market_request
from compertum.runtime.errors import RuntimeRefused
from compertum.runtime.http_retry import normalize_retry_after
import compertum.runtime._winhttp_get as native
import compertum.runtime._winhttp_data as data
import compertum.runtime.paper_market_collection as producer
import compertum.runtime.paper_market_qualification as qualification
from test_market_dispatch_observer import injected
from test_collection_retry_injected import collection_fixture,step,validate_snapshot
import test_paper_market_attempts as f


def test_observer_work_cannot_dispatch_after_native_deadline(injected):
 lease,trace,_=injected
 def observer(transport,stage):
  if stage=='COMMITTED':transport._deadline=time.monotonic()-1
 req=prepare_market_request(f.plan(),operation='HISTORY',request_id=str(UUID(int=1)),created_at=f.stamp(1))
 with pytest.raises(RuntimeRefused,match='HTTP_DEADLINE'):
  data._OwnedDataGet(lease,request=req,headers={'X-Compertum-Test':'synthetic'},_test_port=12345,_native_observer=observer)
 assert 'SEND' not in trace


def test_retry_header_metadata_secret_is_rejected_before_retention(collection_fixture,monkeypatch):
 c,clock,_=collection_fixture
 @contextmanager
 def credentials(*a):yield SimpleNamespace(headers=lambda:{'APCA-API-KEY-ID':'DELAY_SECONDS','APCA-API-SECRET-KEY':'invented_secret'})
 monkeypatch.setattr(producer,'open_paper_credentials',credentials);monkeypatch.setattr(qualification,'open_paper_credentials',credentials)
 h=normalize_retry_after('3',observed_at=datetime(2026,10,9,13,20,tzinfo=timezone.utc),monotonic_ns=clock['ns'])
 clock['responses']=[(429,b'{"message":"busy"}',h)];step(c)
 assert 'DELAY_SECONDS' not in repr(c._chain)
 v=c.private_snapshot().to_payload();assert v['reason']=='REPLY_REFUSED' and v['attempt_chain'][0]['retry_after'] is None

@pytest.mark.parametrize('status',[204,302])
def test_rejected_observed_http_status_is_retained_without_qualified_reply(collection_fixture,monkeypatch,status):
 c,clock,_=collection_fixture
 def rejected(t):t.status_code=status;t.close();raise RuntimeRefused('HTTP_STATUS_UNACCEPTABLE')
 monkeypatch.setattr(native._OwnedHTTP,'poll',rejected);step(c);v=c.private_snapshot().to_payload()
 assert v['state']=='INCOMPLETE' and v['attempt_chain'][0]['observed_status']==status and v['attempt_chain'][0]['reply'] is None
 assert validate_snapshot(c)['selected_records']==[]
@pytest.mark.parametrize('shared_native_clock',[False,True])
def test_observer_expiry_preserves_publishable_no_send_evidence(collection_fixture,injected,monkeypatch,shared_native_clock):
 c,clock,_=collection_fixture;_,trace,_=injected;original=qualification._PreparedMarketExchange._observe_native
 if shared_native_clock:monkeypatch.setattr(native,'time',SimpleNamespace(monotonic=lambda:clock['ns']/10**9))
 def delayed(self,transport,stage):
  if stage=='COMMITTED':clock['ns']=c._deadline_ns
  return original(self,transport,stage)
 monkeypatch.setattr(qualification._PreparedMarketExchange,'_observe_native',delayed)
 with pytest.raises(RuntimeRefused):c.dispatch()
 assert 'SEND' not in trace
 v=validate_snapshot(c);attempt=v['collection']['attempt_chain'][0]
 assert attempt['dispatch_committed_ns'] is None and attempt['native_closed'] and attempt['reply'] is None