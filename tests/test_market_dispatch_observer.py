"""Injected API boundary checks only; these do not establish native acceptance."""
from contextlib import contextmanager
from types import SimpleNamespace
from uuid import UUID
import pytest
import compertum.runtime._winhttp_get as native
import compertum.runtime._winhttp_data as data
import compertum.runtime.service_budget as budget
from compertum.runtime.errors import RuntimeRefused
from compertum.paper_market_inputs import prepare_market_request
import test_paper_market_attempts as f

@pytest.fixture
def injected(monkeypatch):
 trace=[];fault={'stage':None};state=SimpleNamespace(project=SimpleNamespace(project_id='a'*64),resources=[],closed=False)
 lease=SimpleNamespace(project_id='a'*64)
 @contextmanager
 def scope(_):yield state
 for module in (native,data):
  monkeypatch.setattr(module,'_owner_scope',scope);monkeypatch.setattr(module,'require_live_owner',lambda *a:None)
 monkeypatch.setattr(native,'_PENDING',{})
 def permit(*args):trace.append('PERMIT');return object()
 def commit(*args):
  trace.append('QUEUE_COMMIT')
  if fault['stage']=='before':raise RuntimeRefused('INJECTED_BEFORE_SEND')
 monkeypatch.setattr(budget,'native_permit',permit);monkeypatch.setattr(budget,'commit_native',commit);monkeypatch.setattr(budget,'cancel_native',lambda *a:None)
 class API:
  def callback_type(self,fn):return fn
  def Open(self,*a):return 1
  def SetTimeouts(self,*a):return 1
  def SetOption(self,*a):return 1
  def Connect(self,*a):return 2
  def OpenRequest(self,*a):return 3
  def SetStatusCallback(self,request,callback,*a):self.callback=callback;return 0
  def SendRequest(self,*a):
   trace.append('SEND')
   if fault['stage'] in ('send','cleanup'):raise RuntimeRefused('INJECTED_SEND_FAILURE')
   return 1
  def CloseHandle(self,handle):
   trace.append('CLOSE')
   if handle==3:self.callback(3,id(self.callback.__self__),native.CLOSING,None,0)
   return 0 if fault['stage']=='cleanup' else 1
 monkeypatch.setattr(native,'_API',API)
 yield lease,trace,fault
 # Dispose only this injected fixture's objects; never touch real transports.
 for transport in list(native._PENDING.values()):
  transport._cleanup_failed=False;fault['stage']=None;transport.close()
 assert not native._PENDING

@pytest.mark.parametrize('failure',[None,'before','send','cleanup'])
def test_exact_native_boundary_observation_survives_constructor_failure(injected,failure):
 lease,trace,fault=injected;fault['stage']=failure;seen=[]
 req=prepare_market_request(f.plan(),operation='HISTORY',request_id=str(UUID(int=1)),created_at=f.stamp(1))
 def observe(transport,stage):
  trace.append(stage);seen.append((transport,stage))
  assert transport._lease is lease and transport._request_bytes==req.content
  assert transport._method=='GET' and transport._wire_path==req.to_payload()['target']
 options=dict(request=req,headers={'X-Compertum-Test':'synthetic'},_test_port=12345,_native_observer=observe)
 if failure is None:
  transport=data._OwnedDataGet(lease,**options);assert transport is seen[0][0];transport.close()
 else:
  with pytest.raises(RuntimeRefused):data._OwnedDataGet(lease,**options)
 assert seen[0][1]=='INITIALIZED'
 assert trace.index('INITIALIZED')<trace.index('PERMIT')<trace.index('QUEUE_COMMIT')
 if failure=='before':assert 'COMMITTED' not in trace and 'SEND' not in trace
 else:assert trace.index('QUEUE_COMMIT')<trace.index('COMMITTED')<trace.index('SEND')
 assert seen[0][0].native_closed is (failure!='cleanup')
 assert all(t is seen[0][0] for t,_ in seen)
@pytest.mark.parametrize('failure',[None,'before','send','cleanup'])
def test_prepared_exchange_retains_dispatch_and_cleanup_facts(injected,monkeypatch,failure):
 import compertum.runtime.paper_market_qualification as q
 from compertum.runtime.paper_credentials import ProtectedPaperCredentials
 lease,trace,fault=injected;fault['stage']=failure
 lease.generation=1;lease.identity=SimpleNamespace(process_instance_id=str(UUID(int=77)))
 monkeypatch.setattr(q,'_owner_scope',data._owner_scope);monkeypatch.setattr(q,'require_live_owner',lambda *a:None)
 @contextmanager
 def credentials(*args):yield SimpleNamespace(headers=lambda:{'APCA-API-KEY-ID':'invented_key','APCA-API-SECRET-KEY':'invented_secret'})
 monkeypatch.setattr(q,'open_paper_credentials',credentials)
 protected=ProtectedPaperCredentials('a'*64,'paper-primary',b'injected_not_encrypted')
 req=prepare_market_request(f.plan(),operation='HISTORY',request_id=str(UUID(int=1)),created_at=f.stamp(1))
 x=q.prepare_market_exchange(lease,protected,req)
 if failure is None:q.start_market_exchange(x,_test_port=12345);x.close()
 else:
  with pytest.raises(RuntimeRefused):q.start_market_exchange(x,_test_port=12345)
 facts=x._native_evidence()
 assert x._transport is not None
 assert (facts['dispatch_committed_ns'] is not None)==(failure!='before')
 assert facts['native_closed'] is (failure!='cleanup')
 assert facts['observed_status'] is None
 if failure=='cleanup':fault['stage']=None;x._transport._cleanup_failed=False;x.close()


def test_prepared_dispatch_fact_substitution_is_refused(injected,monkeypatch):
 import compertum.runtime.paper_market_qualification as q
 from compertum.runtime.paper_credentials import ProtectedPaperCredentials
 lease,trace,fault=injected;lease.generation=1;lease.identity=SimpleNamespace(process_instance_id=str(UUID(int=77)))
 monkeypatch.setattr(q,'_owner_scope',data._owner_scope);monkeypatch.setattr(q,'require_live_owner',lambda *a:None)
 @contextmanager
 def credentials(*args):yield SimpleNamespace(headers=lambda:{'APCA-API-KEY-ID':'invented_key','APCA-API-SECRET-KEY':'invented_secret'})
 monkeypatch.setattr(q,'open_paper_credentials',credentials)
 protected=ProtectedPaperCredentials('a'*64,'paper-primary',b'injected_not_encrypted')
 req=prepare_market_request(f.plan(),operation='HISTORY',request_id=str(UUID(int=1)),created_at=f.stamp(1))
 x=q.prepare_market_exchange(lease,protected,req);q.start_market_exchange(x,_test_port=12345);x.close()
 original=x._dispatch_commit_ns;object.__setattr__(x,'_dispatch_commit_ns',None)
 with pytest.raises(RuntimeRefused):x._native_evidence()
 object.__setattr__(x,'_dispatch_commit_ns',original);assert x._native_evidence()['native_closed']