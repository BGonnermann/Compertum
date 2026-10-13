"""Shared policy and native dispatch lifetime; invented loopback fixtures only."""
import time
import pytest
from compertum.runtime.errors import RuntimeRefused
from compertum.runtime.owners import _LEASES,release_owner,acquire_owner
from compertum.runtime.identity import resolve_project
from compertum.runtime.service_budget import _Permit,queue_for,_install_loopback_queue
from compertum.runtime._winhttp_get import _OwnedGet,_PENDING
from test_service_budget import budget_owner,Clock
from test_winhttp_get import server,start,finish
from test_winhttp_data import data_start,request


def native(lease,port,permit):
 return _OwnedGet(lease,host='127.0.0.1',port=port,secure=False,path='/fixture',headers={'X-Compertum-Test':'synthetic'},timeout=3,_permit=permit)


def test_priority_fifo_and_direct_call_cannot_jump_queue(budget_owner):
 lease,clock,q=budget_owner;clock.ns=60*10**9;deadline=time.monotonic_ns()+10*10**9
 low=q._enqueue('DATA',2,'HISTORY',deadline);high=q._enqueue('PAPER',0,'READ',deadline);second=q._enqueue('PAPER',0,'READ',deadline)
 with server() as (port,_,seen):
  assert q._claim(low) is None and q._claim(second) is None
  with pytest.raises(RuntimeRefused,match='HTTP_ADMISSION_WAITING'):start(lease,port)
  assert not seen
  q._commit(q._claim(high),'PAPER','READ');assert q._claim(low) is None
  q._commit(q._claim(second),'PAPER','READ')
  q._commit(q._claim(low),'DATA','HISTORY')
  assert len(seen)==0 and q.status()['paper_used']==2 and q.status()['data_used']==1 and q.status()['queued']==0


def test_forged_wrong_service_and_reused_permits_fail_before_setup(budget_owner,monkeypatch):
 lease,clock,q=budget_owner;clock.ns=60*10**9
 import compertum.runtime._winhttp_get as common
 with server() as (port,_,seen):
  with pytest.raises(RuntimeRefused,match='HTTP_PERMIT_INVALID'):native(lease,port,_Permit())
  ticket=q._enqueue('DATA',2,'QUOTE',time.monotonic_ns()+10*10**9);permit=q._claim(ticket)
  with pytest.raises(RuntimeRefused,match='HTTP_PERMIT_WRONG_REQUEST'):native(lease,port,permit)
  assert not seen and q.status()['data_used']==0
  q.cancel(ticket);op=data_start(lease,port,request(lease));used=op._admission[1];finish(op)
  with pytest.raises(RuntimeRefused,match='HTTP_PERMIT_INVALID'):data_start(lease,port,request(lease),_permit=used)
  assert len(seen)==1 and q.status()['data_used']==1


@pytest.mark.parametrize('stage,charged',[('Open',0),('SendRequest',1)])
def test_setup_failure_vs_uncertain_send_charge(budget_owner,monkeypatch,stage,charged):
 lease,clock,q=budget_owner;clock.ns=60*10**9
 import compertum.runtime._winhttp_get as common
 actual=common._API()
 class Failing:
  callback_type=actual.callback_type
  def __getattr__(self,name):return (lambda *args:0) if name==stage else getattr(actual,name)
 monkeypatch.setattr(common,'_API',Failing)
 with pytest.raises(RuntimeRefused,match='HTTP_NATIVE_FAILED'):start(lease,12345)
 assert q.status()['paper_used']==charged and q.status()['queued']==0 and not _PENDING


def test_uncertain_close_does_not_refund_or_release_occupancy(budget_owner,monkeypatch):
 lease,clock,q=budget_owner;clock.ns=60*10**9
 with server(stall=True) as (port,arrived,seen):
  op=start(lease,port);assert arrived.wait(1)
  with monkeypatch.context() as patch:
   patch.setattr(op._closing,'wait',lambda timeout:False)
   with pytest.raises(RuntimeRefused,match='HTTP_CLEANUP_UNVERIFIED'):op.close()
   assert q.status()['paper_used']==1 and id(op) in _PENDING
   with pytest.raises(RuntimeRefused,match='HTTP_BUSY'):start(lease,port)
  op.close();assert len(seen)==1 and not _PENDING and q.status()['paper_used']==1


def test_expired_ticket_removed_without_renewal(budget_owner):
 lease,clock,q=budget_owner;clock.ns=60*10**9
 ticket=q._enqueue('PAPER',0,'READ',time.monotonic_ns()+20_000_000);time.sleep(.03)
 with pytest.raises(RuntimeRefused,match='HTTP_TICKET_EXPIRED'):q._claim(ticket)
 assert q.status()['queued']==0 and q.status()['paper_used']==0


def test_bounded_queue_cancel_and_release(budget_owner):
 lease,clock,q=budget_owner;deadline=time.monotonic_ns()+10*10**9
 tickets=[q._enqueue('PAPER',0,'READ',deadline) for _ in range(16)]
 with pytest.raises(RuntimeRefused,match='HTTP_QUEUE_CAPACITY'):q._enqueue('PAPER',0,'READ',deadline)
 q.cancel(tickets[0]);assert q.status()['queued']==15
 release_owner(lease);assert q._closed and not q._entries
 with pytest.raises(RuntimeRefused):q._claim(tickets[1])


def test_wrong_owner_and_mutated_accounting_refused(budget_owner,tmp_path):
 lease,clock,q=budget_owner;clock.ns=60*10**9
 ticket=q._enqueue('PAPER',0,'READ',time.monotonic_ns()+10*10**9);permit=q._claim(ticket)
 other=tmp_path/'other';other.mkdir();e=acquire_owner(resolve_project(other),'execution');c=Clock();_install_loopback_queue(e,c);c.ns=60*10**9
 try:
  with server() as (port,_,seen):
   with pytest.raises(RuntimeRefused,match='HTTP_PERMIT_INVALID'):native(e,port,permit)
   assert not seen
 finally:release_owner(e)
 q.cancel(ticket);q._used['PAPER'].append(1)
 with pytest.raises(RuntimeRefused,match='HTTP_QUEUE_CONTEXT_CHANGED'):q.status()


def test_production_clock_queue_keeps_owner_acquisition_anchor(tmp_path):
 lease=acquire_owner(resolve_project(tmp_path),'execution')
 try:
  anchor=_LEASES[lease].acquired_monotonic_ns;time.sleep(.01);q=queue_for(lease)
  assert q._anchor==anchor and not q.status()['ready'] and 0<q.status()['wait_ns']<60*10**9
  with server() as (port,_,seen):
   with pytest.raises(RuntimeRefused,match='HTTP_ADMISSION_WAITING'):start(lease,port)
   assert not seen
 finally:release_owner(lease)


def test_paper_cap_also_blocks_asset_but_data_stays_independent(budget_owner):
 lease,clock,q=budget_owner;clock.ns=60*10**9
 from compertum.runtime._winhttp_asset import _OwnedAssetGet
 with server() as (port,_,seen):
  for _ in range(100):finish(start(lease,port))
  with pytest.raises(RuntimeRefused,match='HTTP_ADMISSION_WAITING'):_OwnedAssetGet(lease,request=request(lease,'ASSET'),headers={'X-Compertum-Test':'synthetic'},_test_port=port)
  finish(data_start(lease,port,request(lease)))
  assert len(seen)==101 and q.status()['paper_used']==100 and q.status()['data_used']==1


def credentials(lease):
 from compertum.runtime.paper_credentials import seal_paper_credentials
 import test_paper_market_collection as f
 return seal_paper_credentials(lease,'paper-primary',bytearray(f.KEY.encode()),bytearray(f.SECRET.encode()))


def test_producer_recreation_does_not_reset_spent_quota(budget_owner):
 lease,clock,q=budget_owner;clock.ns=60*10**9;protected=credentials(lease)
 import test_paper_market_collection as f
 for i in range(2):
  with f.pages([f.body('HISTORY')]) as (port,_):
   p=f.collection(lease,protected,port);f.run(p);p.close()
  assert queue_for(lease) is q and q.status()['data_used']==i+1


@pytest.mark.parametrize('kind',['HISTORY','FRESH'])
def test_waiting_deadlines_cancel_ticket_without_attempt(kind,budget_owner,monkeypatch):
 lease,clock,q=budget_owner;protected=credentials(lease)
 import test_paper_market_collection as f
 import test_paper_market_fresh as g
 simulated=f.Clock()
 with f.pages([f.body('HISTORY')]) as (port,seen):
  p=f.collection(lease,protected,port,clock=simulated) if kind=='HISTORY' else g.pair(lease,protected,port,clock=simulated)
  try:
   assert p.dispatch()=='WAITING' and p._attempts==0 and not p._ids
   simulated.mono=81 if kind=='HISTORY' else 21
   with pytest.raises(RuntimeRefused,match='DEADLINE'):p.dispatch()
   assert p._state=='INCOMPLETE' and p._attempts==0 and q.status()['queued']==0 and not seen
  finally:p.close()


def test_history_cutoff_still_applies_while_queued(budget_owner):
 lease,clock,q=budget_owner;protected=credentials(lease)
 import test_paper_market_collection as f
 simulated=f.Clock()
 with f.pages([f.body('HISTORY')]) as (port,seen):
  p=f.collection(lease,protected,port,clock=simulated)
  try:
   assert p.dispatch()=='WAITING';simulated.at='2026-10-09T13:25:00Z'
   with pytest.raises(RuntimeRefused,match='CUTOFF'):p.dispatch()
   assert q.status()['queued']==0 and p._attempts==0 and not seen
  finally:p.close()
