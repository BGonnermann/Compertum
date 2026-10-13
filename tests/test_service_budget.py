"""Native dispatch quotas with explicit loopback-only clock fixtures."""
import pytest
from compertum.runtime.errors import RuntimeRefused
from compertum.runtime.identity import resolve_project
from compertum.runtime.owners import acquire_owner,release_owner,_LEASES
from compertum.runtime.service_budget import queue_for,_install_loopback_queue
from compertum.runtime._winhttp_get import _OwnedGet,_PENDING
from test_winhttp_get import server,start,finish
from test_winhttp_data import request,data_start

class Clock:
 def __init__(self):self.ns=0
 def __call__(self):return self.ns

@pytest.fixture
def budget_owner(tmp_path):
 lease=acquire_owner(resolve_project(tmp_path),'execution');clock=Clock();q=_install_loopback_queue(lease,clock)
 try:yield lease,clock,q
 finally:
  if lease in _LEASES:release_owner(lease)


def test_startup_fence_exact_boundary_native_no_early_send(budget_owner):
 lease,clock,q=budget_owner
 with server() as (port,_,seen):
  for at in (0,60*10**9-1):
   clock.ns=at
   with pytest.raises(RuntimeRefused,match='^HTTP_ADMISSION_WAITING$'):start(lease,port)
   assert not seen and not _PENDING and q.status()['queued']==0
  clock.ns=60*10**9;finish(start(lease,port));assert len(seen)==1 and q.status()['paper_used']==1


def test_independent_service_window_and_no_101st_dispatch(budget_owner):
 lease,clock,q=budget_owner;clock.ns=60*10**9
 with server() as (port,_,seen):
  for _ in range(100):finish(data_start(lease,port,request(lease)))
  assert len(seen)==100 and q.status()['data_used']==100 and q.status()['paper_used']==0
  with pytest.raises(RuntimeRefused,match='^HTTP_ADMISSION_WAITING$'):data_start(lease,port,request(lease))
  finish(start(lease,port));assert len(seen)==101 and q.status()['paper_used']==1
  clock.ns=120*10**9-1
  with pytest.raises(RuntimeRefused,match='^HTTP_ADMISSION_WAITING$'):data_start(lease,port,request(lease))
  clock.ns+=1;finish(data_start(lease,port,request(lease)));assert len(seen)==102 and q.status()['data_used']==1


def test_fixture_owner_never_reaches_production_tls(budget_owner,monkeypatch):
 lease,clock,q=budget_owner;clock.ns=60*10**9
 import compertum.runtime._winhttp_get as native
 monkeypatch.setattr(native,'_API',lambda:pytest.fail('native setup reached'))
 with pytest.raises(RuntimeRefused,match='^HTTP_FIXTURE_QUEUE_TLS_FORBIDDEN$'):
  _OwnedGet(lease,host='paper-api.alpaca.markets',port=443,secure=True,path='/v2/account',headers={'APCA-API-KEY-ID':'invented','APCA-API-SECRET-KEY':'invented'},timeout=1)
 assert q.status()['paper_used']==0


def test_queue_cannot_recreate_or_reset_on_close(budget_owner):
 lease,clock,q=budget_owner;clock.ns=60*10**9;assert queue_for(lease) is q
 q.close()
 with pytest.raises(RuntimeRefused,match='^HTTP_QUEUE_CLOSED$'):queue_for(lease)
 with pytest.raises(RuntimeRefused):_install_loopback_queue(lease,Clock())


def test_clock_regression_poison_is_permanent(budget_owner):
 lease,clock,q=budget_owner;clock.ns=60*10**9;q.status();clock.ns-=1
 with pytest.raises(RuntimeRefused,match='^HTTP_QUEUE_CLOCK_INVALID$'):q.status()
 clock.ns=120*10**9
 with pytest.raises(RuntimeRefused,match='^HTTP_QUEUE_CLOCK_INVALID$'):q.status()


def test_market_waiting_does_not_prepare_or_consume_attempt(budget_owner):
 lease,clock,q=budget_owner
 from compertum.runtime.paper_credentials import seal_paper_credentials
 import test_paper_market_collection as f
 protected=seal_paper_credentials(lease,'paper-primary',bytearray(f.KEY.encode()),bytearray(f.SECRET.encode()))
 with f.pages([f.body('HISTORY')]) as (port,seen):
  producer=f.collection(lease,protected,port)
  try:
   assert producer.dispatch()=='WAITING'
   assert producer._attempts==0 and producer._pending is None and producer._ids==set() and producer._state=='READY'
   assert q.status()['queued']==1 and not seen
   clock.ns=60*10**9;producer.dispatch();producer.poll()
   while producer._state=='PENDING':producer.poll()
   assert producer._attempts==1 and q.status()['data_used']==1
  finally:producer.close()
