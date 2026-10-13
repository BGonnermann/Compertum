"""Native data GET preparation: fixed validated requests, invented local server only."""
from dataclasses import replace
import hashlib,json,os
from uuid import UUID
import pytest
from compertum.data.encoding import canonical
from compertum.paper_market_inputs import prepare_market_plan,prepare_market_request,OperationalMarketRequest
from compertum.paper_action_inputs import prepare_action_query,CurrentActionQuery,CurrentActionPage
from compertum.runtime.errors import RuntimeRefused
from compertum.runtime.owners import _LEASES,release_owner
from compertum.runtime._winhttp_get import _OwnedGet,_OwnedHTTP,_PENDING
from compertum.runtime._winhttp_data import _OwnedDataGet
from test_winhttp_get import owner,server,finish,start

pytestmark=pytest.mark.skipif(os.name!='nt',reason='NATIVE_WINDOWS_UNAVAILABLE')
DAY='2026-10-09';AT='2026-10-09T13:20:00Z'
def uid(n):return str(UUID(int=n))
def plan(owner):return prepare_market_plan(project_id=owner.project_id,account_alias='paper-primary',symbol='AAPL',session_date=DAY,created_at=AT)
def request(owner,kind='QUOTE',token=None):
 p=plan(owner)
 if kind=='ACTION':return prepare_action_query(p)
 return prepare_market_request(p,operation=kind,request_id=uid(1),created_at=AT,page_token=token)
def args(kind='QUOTE',token=None):
 return dict(action_request_id=uid(2),action_requested_at=AT,action_page_token=token) if kind=='ACTION' else {}
def expected(req,kind,token=None):
 if kind!='ACTION':return req.to_payload()
 return CurrentActionPage(req,uid(2),token,AT,'2026-10-09T13:20:01Z',200,b'{"corporate_actions":{},"next_page_token":null}').request_payload()
def data_start(owner,port,req,kind='QUOTE',token=None,**edit):
 values=dict(request=req,headers={'X-Compertum-Test':'synthetic'},timeout=3,_test_port=port,**args(kind,token));values.update(edit)
 return _OwnedDataGet(owner,**values)


@pytest.mark.parametrize('kind,token',[('QUOTE',None),('HISTORY',None),('HISTORY','next+/='),('ACTION',None),('ACTION','next+/='),('HISTORY','+'*1024),('ACTION','+'*1024)],ids=['quote','history','history_next','action','action_next','history_max','action_max'])
def test_exact_native_targets_and_retained_request_binding(owner,kind,token):
 req=request(owner,kind,token if kind=='HISTORY' else None);e=expected(req,kind,token)
 with server(body=b'{"observed":true}') as (port,_,seen):
  op=data_start(owner,port,req,kind,token);reply=finish(op)
  assert len(seen)==1 and seen[0][0]==e['target'] and seen[0][1]['X-Compertum-Test']=='synthetic'
  assert reply.status_code==200 and reply.body==b'{"observed":true}' and op.native_closed
  assert op._request_bytes==canonical(e) and op._request_sha256==hashlib.sha256(op._request_bytes).hexdigest()
  assert op._method=='GET' and op._origin==('127.0.0.1',port,False) and not _PENDING
  assert not any(bytes(op._headers)) and 'synthetic' not in repr(op)
  if token and len(token)==1024:assert 2048<len(e['target'])<=4096


@pytest.mark.parametrize('status',[401,403,408,429,500,599])
def test_error_body_is_retained_without_retry_or_auth(owner,status):
 with server(body=b'{"message":"fixture refusal"}',status=status,headers=(('WWW-Authenticate','Negotiate'),)) as (port,_,seen):
  op=data_start(owner,port,request(owner));r=finish(op)
  assert r.status_code==status and r.body==b'{"message":"fixture refusal"}' and len(seen)==1 and op.native_closed


@pytest.mark.parametrize('status',[201,204,301,302,307,399])
def test_noncontract_status_never_redirects_or_succeeds(owner,status):
 with server(status=status,headers=(('Location','http://127.0.0.1:9/forbidden'),)) as (port,_,seen):
  op=data_start(owner,port,request(owner))
  with pytest.raises(RuntimeRefused,match='HTTP_STATUS_UNACCEPTABLE'):finish(op)
  assert len(seen)==1 and op.native_closed


@pytest.mark.parametrize('change',[{'origin':'https://api.alpaca.markets'},{'origin':'https://paper-api.alpaca.markets'},{'method':'POST'},{'target':'/v2/account'},{'parameters':{'feed':'sip'}},{'parameters':{'symbols':'MSFT'}},{'parameters':{'limit':1000}}])
def test_forged_market_request_refused_before_native_api(owner,monkeypatch,change):
 import compertum.runtime._winhttp_get as common
 monkeypatch.setattr(common,'_API',lambda:pytest.fail('native API initialized'))
 req=request(owner,'HISTORY');v=req.to_payload();v.update(change);object.__setattr__(req,'content',canonical(v))
 with pytest.raises(RuntimeRefused,match='HTTP_DATA_INPUT_INVALID'):_OwnedDataGet(owner,request=req,headers={},_test_port=12345)
 assert not _PENDING


def test_wrong_project_asset_and_mixed_action_arguments_refused_before_native(owner,monkeypatch):
 import compertum.runtime._winhttp_get as common
 monkeypatch.setattr(common,'_API',lambda:pytest.fail('native API initialized'))
 p=plan(owner).to_payload();p['project_id']='a'*64
 from compertum.paper_market_inputs import OperationalMarketPlan
 foreign=OperationalMarketPlan(canonical(p));r=prepare_market_request(foreign,operation='QUOTE',request_id=uid(1),created_at=AT)
 for req,extra in [(r,{}),(request(owner,'ASSET'),{}),(request(owner),{'action_page_token':'other'}),(request(owner),{'action_request_id':uid(2)}),(request(owner,'ACTION'),{})]:
  with pytest.raises(RuntimeRefused,match='HTTP_DATA_INPUT_INVALID'):_OwnedDataGet(owner,request=req,headers={},_test_port=12345,**extra)
 assert not _PENDING


def test_action_binding_rejects_modified_query(owner,monkeypatch):
 import compertum.runtime._winhttp_get as common
 monkeypatch.setattr(common,'_API',lambda:pytest.fail('native API initialized'))
 q=request(owner,'ACTION');v=q.to_payload();v['parameters']['data_quality']='complete';object.__setattr__(q,'content',canonical(v))
 with pytest.raises(RuntimeRefused,match='HTTP_DATA_INPUT_INVALID'):data_start(owner,12345,q,'ACTION')


@pytest.mark.parametrize('changes',[{'_test_port':True},{'_test_port':0},{'headers':{'APCA-API-KEY-ID':'invented','APCA-API-SECRET-KEY':'invented'}},{'headers':{'X-Compertum-Test':'has\r\ninjection'}},{'timeout':11},{'timeout':True}])
def test_invalid_data_transport_inputs_refuse_before_native(owner,monkeypatch,changes):
 import compertum.runtime._winhttp_get as common
 monkeypatch.setattr(common,'_API',lambda:pytest.fail('native API initialized'))
 with pytest.raises(RuntimeRefused):data_start(owner,12345,request(owner),**changes)
 assert not _PENDING


def test_legacy_get_and_order_backend_still_deny_data_host(owner,monkeypatch):
 import compertum.runtime._winhttp_get as common
 monkeypatch.setattr(common,'_API',lambda:pytest.fail('native API initialized'))
 values=dict(host='data.alpaca.markets',port=443,secure=True,path='/v2/stocks/quotes/latest',headers={'APCA-API-KEY-ID':'invented','APCA-API-SECRET-KEY':'invented'},timeout=3)
 with pytest.raises(RuntimeRefused,match='HTTP_INPUT_INVALID'):_OwnedGet(owner,**values)
 for method in ('GET','POST','DELETE'):
  with pytest.raises(RuntimeRefused,match='HTTP_INPUT_INVALID'):_OwnedHTTP(owner,method=method,body=b'',**values)
 values.update(host='127.0.0.1',port=12345,secure=False,path='/'+'x'*2048,headers={'X-Compertum-Test':'synthetic'})
 with pytest.raises(RuntimeRefused,match='HTTP_INPUT_INVALID'):_OwnedGet(owner,**values)
 assert not _PENDING


def test_production_adapter_validates_fixed_origin_but_fixture_queue_refuses_tls(owner,monkeypatch):
 import compertum.runtime._winhttp_get as common
 class ReachedValidatedBoundary(Exception):pass
 monkeypatch.setattr(common,'_API',lambda:(_ for _ in ()).throw(ReachedValidatedBoundary()))
 op=object.__new__(_OwnedDataGet)
 with pytest.raises(RuntimeRefused,match='^HTTP_FIXTURE_QUEUE_TLS_FORBIDDEN$'):op.__init__(owner,request=request(owner),headers={'APCA-API-KEY-ID':'invented','APCA-API-SECRET-KEY':'invented'})
 assert op._origin==('data.alpaca.markets',443,True) and op._method=='GET' and op._wire_path==request(owner).to_payload()['target']
 assert not _PENDING


def test_adapter_owner_cancellation_and_shared_occupancy(owner):
 with server(stall=True) as (port,arrived,seen):
  op=data_start(owner,port,request(owner));assert arrived.wait(1)
  with pytest.raises(RuntimeRefused,match='HTTP_BUSY'):start(owner,port)
  release_owner(owner)
  assert op.native_closed and not _PENDING and len(seen)==1


def test_data_and_legacy_serial_requests_restore_resources(owner):
 before=list(_LEASES[owner].resources)
 with server() as (port,_,seen):
  for kind in ('QUOTE','HISTORY','ACTION'):
   op=data_start(owner,port,request(owner,kind),kind);assert finish(op).status_code==200
   assert op.native_closed and _LEASES[owner].resources==before and not _PENDING
  assert len(seen)==3


@pytest.mark.parametrize('mode',['overflow','compression','truncated','deadline','uncertain_close'])
def test_data_adapter_keeps_existing_native_failure_behavior(owner,monkeypatch,mode):
 options={'overflow':dict(body=b'x'*65537),'compression':dict(headers=(('Content-Encoding','gzip'),)),'truncated':dict(body=b'x',headers=(('Content-Length','8'),)),'deadline':dict(stall=True),'uncertain_close':dict(stall=True)}[mode]
 with server(**options) as (port,arrived,seen):
  op=data_start(owner,port,request(owner),timeout=.15 if mode=='deadline' else 3)
  if mode=='uncertain_close':
   assert arrived.wait(1)
   with monkeypatch.context() as patch:
    patch.setattr(op._closing,'wait',lambda timeout:False)
    with pytest.raises(RuntimeRefused,match='HTTP_CLEANUP_UNVERIFIED'):op.close()
    assert _PENDING[id(op)] is op and not op.native_closed
   op.close()
  else:
   with pytest.raises(RuntimeRefused):finish(op)
  assert op.native_closed and not _PENDING and len(seen)==1


def test_data_policy_cannot_be_reused_for_write_or_changed_target(owner):
 op=object.__new__(_OwnedDataGet);op._data_origin=('data.alpaca.markets',443,True);op._data_target=request(owner).to_payload()['target']
 values=dict(host='data.alpaca.markets',port=443,secure=True,path=op._data_target,headers={'APCA-API-KEY-ID':'invented','APCA-API-SECRET-KEY':'invented'},timeout=3,method='GET',body=b'')
 for change in ({'method':'POST'},{'method':'DELETE'},{'body':b'{}'},{'path':'/v2/orders'},{'host':'paper-api.alpaca.markets'},{'secure':False}):
  with pytest.raises(RuntimeRefused):op._validate_inputs(**dict(values,**change))


def test_legacy_inflight_also_blocks_data_adapter(owner):
 with server(stall=True) as (port,arrived,seen):
  op=start(owner,port);assert arrived.wait(1)
  with pytest.raises(RuntimeRefused,match='HTTP_BUSY'):data_start(owner,port,request(owner))
  op.close();assert op.native_closed and not _PENDING and len(seen)==1


@pytest.mark.parametrize('deadline',[True,'later',float('nan'),float('inf')])
def test_parent_deadline_rejects_invalid_values_before_native(owner,monkeypatch,deadline):
 import compertum.runtime._winhttp_get as common
 monkeypatch.setattr(common,'_API',lambda:pytest.fail('native API initialized'))
 with pytest.raises(RuntimeRefused,match='HTTP_INPUT_INVALID'):data_start(owner,12345,request(owner),_deadline_at=deadline)


def test_parent_deadline_is_only_restrictive_and_hook_runs_before_send(owner):
 import time
 with server() as (port,_,seen):
  before=time.monotonic();called=[]
  t=data_start(owner,port,request(owner),timeout=3,_deadline_at=before+100,_pre_send=lambda:called.append(True))
  assert t._deadline<=before+3.1 and finish(t).status_code==200 and called==[True] and len(seen)==1
 with server() as (port,_,seen):
  with pytest.raises(RuntimeRefused,match='HTTP_DEADLINE'):data_start(owner,port,request(owner),_deadline_at=time.monotonic()-1)
  assert not seen and not _PENDING



def test_review_huge_absolute_deadline_is_static_input_error(owner,monkeypatch):
 import compertum.runtime._winhttp_get as common
 monkeypatch.setattr(common,'_API',lambda:pytest.fail('native API initialized'))
 with pytest.raises(RuntimeRefused,match='^HTTP_INPUT_INVALID$'):data_start(owner,12345,request(owner),_deadline_at=10**1000)
