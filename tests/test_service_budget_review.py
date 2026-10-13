"""Regression evidence for independent service-gate review."""
import time
import pytest
from compertum.runtime.errors import RuntimeRefused
from compertum.runtime.owners import _LEASES
from compertum.runtime.service_budget import queue_for,_install_loopback_queue
from compertum.runtime._winhttp_get import _PENDING
from test_service_budget import budget_owner,Clock
from test_service_budget_lifecycle import native
from test_winhttp_get import server,finish
from test_winhttp_data import data_start,request

@pytest.mark.parametrize('closed',[False,True])
@pytest.mark.parametrize('fixture',[False,True])
def test_cleared_queue_pointer_never_allows_replacement(budget_owner,closed,fixture):
 lease,clock,q=budget_owner;guard=_LEASES[lease]
 if closed:q.close()
 guard._service_queue=None
 try:
  with pytest.raises(RuntimeRefused):
   _install_loopback_queue(lease,Clock()) if fixture else queue_for(lease)
 finally:guard._service_queue=q


def test_unbound_priority_permit_cannot_send_arbitrary_request(budget_owner):
 lease,clock,q=budget_owner;clock.ns=60*10**9
 ticket=q._enqueue('PAPER',0,'READ',time.monotonic_ns()+10*10**9);permit=q._claim(ticket)
 with server() as (port,_,seen):
  op=None
  try:
   with pytest.raises(RuntimeRefused,match='HTTP_PERMIT_WRONG_REQUEST'):op=native(lease,port,permit)
   assert not seen and q.status()['paper_used']==0
  finally:
   if op is not None:op.close()
   q.cancel(ticket)


def test_corrupt_queue_still_closes_every_allocated_native_handle(budget_owner,monkeypatch):
 lease,clock,q=budget_owner;clock.ns=60*10**9
 import compertum.runtime._winhttp_get as common
 actual=common._API();closed=[]
 class Spy:
  callback_type=actual.callback_type
  def CloseHandle(self,h):closed.append(h);return actual.CloseHandle(h)
  def __getattr__(self,n):return getattr(actual,n)
 monkeypatch.setattr(common,'_API',Spy)
 with server() as (port,_,seen):
  try:
   with pytest.raises(RuntimeRefused,match='HTTP_QUEUE_CONTEXT_CHANGED'):
    data_start(lease,port,request(lease),_pre_send=lambda:q._used['DATA'].append(1))
   assert len(closed)==3 and not _PENDING and not seen
  finally:
   q._seal()
   for op in tuple(_PENDING.values()):
    if op._lease is lease:op.close()


from test_execution_health import pair
from test_paper_read_owner import owner,prepare,approve,start

@pytest.mark.parametrize('swap',['target','identity','adapter','pre_send'])
def test_authentic_read_permit_rejects_request_substitution(owner,monkeypatch,swap):
 o=owner;q=queue_for(o.e.lease)
 from compertum.runtime._winhttp_get import _OwnedGet
 from compertum.runtime._winhttp_order import _OwnedOrderHTTP
 import compertum.runtime._winhttp_get as common
 actual=common._API;opened=[]
 def api():opened.append(True);return actual()
 monkeypatch.setattr(common,'_API',api)
 with server() as (port,_,seen):
  def intercepted(lease,request,protected,timeout,*,_permit=None):
   if swap=='adapter':
    return _OwnedOrderHTTP(lease,operation='ORDER_BY_ID',parameters={'order_id':'00000000-0000-0000-0000-000000000001'},headers={'X-Compertum-Test':'synthetic'},_test_port=port,_permit=_permit)
   target=request.to_payload()['target'] if swap!='target' else '/fixture'
   source=request if swap!='identity' else None
   if swap=='pre_send':monkeypatch.setattr(_OwnedGet,'_before_send',lambda native:setattr(native,'_wire_path','/changed'))
   return _OwnedGet(lease,host='127.0.0.1',port=port,secure=False,path=target,headers={'X-Compertum-Test':'synthetic'},timeout=timeout,_permit=_permit,_read_request=source)
  monkeypatch.setattr(o.module,'_start_get',intercepted)
  p=prepare(o);approve(o,p);start(o,p);o.a.tick()
  state=o.a._read(p['packet_id'])
  assert state['state']=='ABORTED' and state['reason']=='HTTP_PERMIT_WRONG_REQUEST'
  assert q.status()['paper_used']==0 and not seen and not _PENDING
  assert len(opened)==(1 if swap=='pre_send' else 0)


@pytest.mark.parametrize('mode',['HISTORY','CURRENT_ACTIONS','FRESH'])
def test_authentic_market_permit_rejects_same_bytes_different_request(budget_owner,monkeypatch,mode):
 lease,clock,q=budget_owner;clock.ns=60*10**9
 from test_service_budget_lifecycle import credentials
 import test_paper_market_collection as f
 import test_paper_market_fresh as g
 import compertum.runtime.paper_market_collection as collection_module
 import compertum.runtime.paper_market_fresh as fresh_module
 from compertum.runtime._winhttp_data import _OwnedDataGet
 from compertum.runtime._winhttp_asset import _OwnedAssetGet
 from compertum.paper_market_inputs import OperationalMarketRequest
 from compertum.paper_action_inputs import prepare_action_query
 protected=credentials(lease)
 with server() as (port,_,seen):
  def intercepted(exchange,**options):
   req=exchange._request
   duplicate=OperationalMarketRequest(req.plan,req.content) if type(req) is OperationalMarketRequest else prepare_action_query(req.plan)
   assert duplicate is not req
   kwargs=dict(request=duplicate,headers={'X-Compertum-Test':'synthetic'},_test_port=port,_permit=options['_permit'])
   if mode=='FRESH':return _OwnedAssetGet(lease,**kwargs)
   if mode=='CURRENT_ACTIONS':
    rid,at,token=exchange._action;kwargs.update(action_request_id=rid,action_requested_at=at,action_page_token=token)
   return _OwnedDataGet(lease,**kwargs)
  monkeypatch.setattr(fresh_module if mode=='FRESH' else collection_module,'start_market_exchange',intercepted)
  p=g.pair(lease,protected,port) if mode=='FRESH' else f.collection(lease,protected,port,mode=mode)
  try:
   with pytest.raises(RuntimeRefused,match='HTTP_PERMIT_WRONG_REQUEST'):p.dispatch()
   assert not seen and not _PENDING and q.status()['paper_used']==q.status()['data_used']==0 and q.status()['queued']==0
  finally:p.close()
