"""Native single-dispatch Retry-After evidence against invented local services."""
from datetime import datetime,timezone
import os
import pytest
from compertum.runtime.errors import RuntimeRefused
from compertum.runtime._winhttp_get import _PENDING
from compertum.runtime._winhttp_asset import _OwnedAssetGet
from test_winhttp_get import owner,server,start,finish
from test_winhttp_data import request,data_start
from test_winhttp_order import service,start as order_start

pytestmark=pytest.mark.skipif(os.name!='nt',reason='NATIVE_WINDOWS_UNAVAILABLE')

@pytest.mark.parametrize('status',[200,302,401,403,429,503])
def test_header_survives_status_refusal_without_retry(owner,status):
 with server(status=status,headers=(('Retry-After','4'),)) as (port,_,seen):
  op=start(owner,port)
  if status==200:
   result=finish(op);assert result.retry_after is op.retry_after
  else:
   with pytest.raises(RuntimeRefused,match='^HTTP_STATUS_UNACCEPTABLE$'):finish(op)
  assert op.retry_after.delay_ns==4*10**9 and op.status_code==status
  assert op.retry_after.not_before_ns==op.retry_after.observed_monotonic_ns+4*10**9
  assert op.native_closed and not _PENDING and len(seen)==1

@pytest.mark.parametrize('kind',['QUOTE','HISTORY','ACTION','ASSET'])
def test_fixed_typed_get_result_has_normalized_retry_evidence(owner,kind):
 with server(status=429,body=b'{"refusal":true}',headers=(('Retry-After','1'),)) as (port,_,seen):
  if kind=='ASSET':op=_OwnedAssetGet(owner,request=request(owner,kind),headers={'X-Compertum-Test':'synthetic'},_test_port=port)
  else:op=data_start(owner,port,request(owner,kind),kind)
  result=finish(op);assert result.body==b'{"refusal":true}' and result.status_code==429
  assert result.retry_after is op.retry_after and result.retry_after.delay_ns==10**9
  assert len(seen)==1 and op.native_closed and not _PENDING

@pytest.mark.parametrize('kind',['SUBMIT_ORDER','CANCEL_ORDER','ORDER_BY_ID'])
def test_order_methods_observe_header_but_never_resend(owner,kind):
 from test_winhttp_order import ORDER
 with service(status=503,headers=(('Retry-After','0'),)) as (port,_,seen):
  extra={} if kind=='SUBMIT_ORDER' else dict(parameters={'order_id':ORDER},body=None)
  op=order_start(owner,port,operation=kind,**extra);result=finish(op)
  assert result.retry_after.delay_ns==0 and len(seen)==1 and op.native_closed
  assert finish(op) is result and len(seen)==1

@pytest.mark.parametrize('headers,expected',[
 ((('Retry-After','4'),('Retry-After','4')),'HTTP_HEADERS_INVALID'),
 ((('Retry-After','4'),('Retry-After','9')),'HTTP_HEADERS_INVALID'),
 ((('Retry-After','secret-value'),),'HTTP_RETRY_AFTER_INVALID'),
 ((('Retry-After','2147483648'),),'HTTP_RETRY_AFTER_INVALID'),
 ((('Retry-After','x'*129),),'HTTP_RETRY_AFTER_INVALID'),
 ((('Retry-After','4, 9'),),'HTTP_RETRY_AFTER_INVALID'),
])
def test_invalid_header_closes_before_status_decision(owner,headers,expected):
 with server(status=429,headers=headers) as (port,_,seen):
  op=start(owner,port)
  with pytest.raises(RuntimeRefused,match='^'+expected+'$'):finish(op)
  assert op.retry_after is None and op.native_closed and not _PENDING and len(seen)==1

@pytest.mark.parametrize('text',['Fri, 09 Oct 2026 13:20:10 GMT','Friday, 09-Oct-26 13:20:10 GMT','Fri Oct  9 13:20:10 2026'])
def test_native_date_header_observed_at_fixed_clock(owner,monkeypatch,text):
 import compertum.runtime._winhttp_get as common
 monkeypatch.setattr(common,'_utc_now',lambda:datetime(2026,10,9,13,20,0,123456,tzinfo=timezone.utc))
 with server(headers=(('Retry-After',text),)) as (port,_,seen):
  op=start(owner,port);result=finish(op)
  assert result.retry_after.delay_ns==9_876_544_000 and result.retry_after.kind=='HTTP_DATE' and len(seen)==1

def test_absence_does_not_invent_timing(owner):
 with server() as (port,_,seen):
  op=start(owner,port);result=finish(op);assert result.retry_after is None and op.retry_after is None and len(seen)==1
