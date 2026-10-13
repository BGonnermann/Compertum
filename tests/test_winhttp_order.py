"""Native order methods against an invented loopback service only."""
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import threading
import time
import pytest
from compertum.runtime.errors import RuntimeRefused
from compertum.runtime.owners import release_owner, _LEASES
from compertum.runtime._winhttp_get import _PENDING
from compertum.runtime._winhttp_order import _OwnedOrderHTTP
from test_winhttp_get import owner, finish

pytestmark=pytest.mark.skipif(os.name!='nt',reason='NATIVE_WINDOWS_UNAVAILABLE')
ORDER='11111111-1111-4111-8111-111111111111'
BODY=dict(symbol='AAPL',qty='1',side='buy',type='market',time_in_force='day',extended_hours=False,client_order_id='cmp-test-order')

@contextmanager
def service(*,status=200,body=b'{"status":"accepted"}',headers=(),mode=None):
    seen=[];arrived=threading.Event();release=threading.Event()
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def handle_request(self):
            raw=self.rfile.read(int(self.headers.get('Content-Length','0')))
            seen.append(dict(method=self.command,path=self.path,headers=dict(self.headers),body=raw));arrived.set()
            if mode=='stall':release.wait(10)
            if mode=='disconnect':self.close_connection=True;return
            try:
                self.send_response(status)
                for key,value in headers:self.send_header(key,value)
                self.end_headers();self.wfile.write(body);self.wfile.flush()
                if mode=='stall_after':release.wait(10)
            except (BrokenPipeError,ConnectionResetError,ConnectionAbortedError):pass
        do_GET=do_POST=do_DELETE=handle_request
    http=ThreadingHTTPServer(('127.0.0.1',0),Handler);http.daemon_threads=True
    thread=threading.Thread(target=http.serve_forever,kwargs={'poll_interval':.01},daemon=True);thread.start()
    try:yield http.server_port,arrived,seen
    finally:
        release.set();http.shutdown();http.server_close();thread.join(2)
        assert not thread.is_alive()

def start(owner,port,**change):
    args=dict(operation='SUBMIT_ORDER',body=BODY.copy(),headers={'X-Compertum-Test':'synthetic'},timeout=3,_test_port=port)
    args.update(change)
    return _OwnedOrderHTTP(owner,**args)

@pytest.mark.parametrize('operation,parameters,body,status,target,method',[
    ('SUBMIT_ORDER',None,BODY,200,'/v2/orders','POST'),
    ('SUBMIT_ORDER',None,dict(BODY,type='limit',limit_price='100.25'),200,'/v2/orders','POST'),
    ('CANCEL_ORDER',{'order_id':ORDER},None,204,'/v2/orders/'+ORDER,'DELETE'),
    ('ORDER_BY_ID',{'order_id':ORDER},None,200,'/v2/orders/'+ORDER,'GET'),
    ('ORDER_BY_CLIENT_ID',{'client_order_id':'cmp-test-order'},None,200,'/v2/orders:by_client_order_id?client_order_id=cmp-test-order','GET'),
])
def test_exact_native_wire_and_terminal_buffer_cleanup(owner,operation,parameters,body,status,target,method):
    reply=b'' if status==204 else b'{"status":"accepted"}'
    with service(status=status,body=reply) as (port,_,seen):
        op=start(owner,port,operation=operation,parameters=parameters,body=body)
        result=finish(op)
        assert result.status_code==status and result.body==reply
        assert len(seen)==1 and seen[0]['method']==method and seen[0]['path']==target
        assert seen[0]['body']==(json.dumps(body,sort_keys=True,separators=(',',':')).encode() if body else b'')
        assert seen[0]['headers']['Accept-Encoding']=='identity'
        if body:assert seen[0]['headers']['Content-Type']=='application/json'
        assert not any(bytes(op._upload)) and not any(bytes(op._headers)) and op.native_closed and not _PENDING
        assert 'accepted' not in repr(result) and 'AAPL' not in repr(op)
        assert finish(op) is result and len(seen)==1

@pytest.mark.parametrize('status',[400,401,403,404,408,422,429,500,503,599])
def test_error_response_is_returned_once_without_retry_or_effect_claim(owner,status):
    with service(status=status,body=b'{"code":999}',headers=(('WWW-Authenticate','Negotiate'),)) as (port,_,seen):
        op=start(owner,port);result=finish(op)
        assert result.status_code==status and result.body==b'{"code":999}' and op.status_code==status
        assert len(seen)==1 and op.native_closed
        assert not hasattr(result,'filled') and not hasattr(result,'canceled')

@pytest.mark.parametrize('status',[201,202,204,301,302,307,308])
def test_unexpected_success_or_redirect_is_refused_without_repeat(owner,status):
    with service(status=status,headers=(('Location','http://127.0.0.1:9/forbidden'),)) as (port,_,seen):
        op=start(owner,port)
        with pytest.raises(RuntimeRefused,match='^HTTP_STATUS_UNACCEPTABLE$'):finish(op)
        assert len(seen)==1 and op.status_code==status and op.native_closed

@pytest.mark.parametrize('mode',['stall','disconnect'])
def test_accepted_request_with_no_reply_stays_uncertain_and_is_never_repeated(owner,mode):
    with service(mode=mode) as (port,arrived,seen):
        op=start(owner,port,timeout=.15)
        assert arrived.wait(1)
        with pytest.raises(RuntimeRefused):finish(op)
        assert len(seen)==1 and op._result is None and op.native_closed
        with pytest.raises(RuntimeRefused,match='^HTTP_CLOSED$'):op.poll()
        assert len(seen)==1 and not any(bytes(op._upload))

def test_upload_memory_survives_uncertain_close_then_is_wiped(owner,monkeypatch):
    with service(mode='stall') as (port,arrived,seen):
        op=start(owner,port);assert arrived.wait(1)
        assert b'cmp-test-order' in bytes(op._upload)
        with monkeypatch.context() as patch:
            patch.setattr(op._closing,'wait',lambda timeout:False)
            with pytest.raises(RuntimeRefused,match='^HTTP_CLEANUP_UNVERIFIED$'):op.close()
            assert b'cmp-test-order' in bytes(op._upload) and _PENDING[id(op)] is op
        op.close()
        assert not any(bytes(op._upload)) and op.native_closed and len(seen)==1

def test_owner_release_cancels_write_and_clears_owned_buffers(owner):
    with service(mode='stall') as (port,arrived,seen):
        op=start(owner,port);assert arrived.wait(1);release_owner(owner)
        assert owner not in _LEASES and op.native_closed and not any(bytes(op._upload))
        assert len(seen)==1

def test_caller_body_mutation_cannot_change_frozen_upload(owner):
    draft=BODY.copy()
    with service() as (port,_,seen):
        op=start(owner,port,body=draft);draft['qty']='999';finish(op)
        assert json.loads(seen[0]['body'])==BODY

@pytest.mark.parametrize('change',[
    {'operation':'CLOSE_ALL'}, {'operation':'CANCEL_ORDER','parameters':{},'body':None},
    {'operation':'CANCEL_ORDER','parameters':{'order_id':ORDER+'/bad'},'body':None},
    {'operation':'ORDER_BY_CLIENT_ID','parameters':{'client_order_id':'cmp-x&extra=yes'},'body':None},
    {'body':dict(BODY,qty='1.5')},{'body':dict(BODY,qty='0')},{'body':dict(BODY,time_in_force='gtc')},
    {'body':dict(BODY,extended_hours=True)},{'body':dict(BODY,notional='10')},
    {'body':dict(BODY,symbol='A'*65537)},{'body':dict(BODY,client_order_id='x'*129)},
    {'body':dict(BODY,type='limit',limit_price='NaN')},{'body':dict(BODY,side='short')},
    {'parameters':{'url':'https://api.alpaca.markets'}},{'timeout':11},{'_test_port':True},
    {'headers':{'APCA-API-KEY-ID':'invented','APCA-API-SECRET-KEY':'invented'}},
])
def test_invalid_shape_or_routing_is_rejected_before_any_native_request(owner,change,monkeypatch):
    import compertum.runtime._winhttp_get as backend
    def forbidden():raise AssertionError('invalid request reached native API')
    monkeypatch.setattr(backend,'_API',forbidden)
    with pytest.raises(RuntimeRefused):start(owner,12345,**change)
    assert not _PENDING

@pytest.mark.parametrize('body,headers',[(b'x'*65537,()),(b'x'*65536,(('Content-Encoding','gzip'),)),(b'short',(('Content-Length','100'),))],ids=['overflow','compression','truncated'])
def test_private_error_body_bounds_and_headers_still_apply(owner,body,headers):
    with service(status=500,body=body,headers=headers) as (port,_,seen):
        op=start(owner,port)
        with pytest.raises(RuntimeRefused):finish(op)
        assert len(seen)==1 and op.status_code==500 and op.native_closed

@pytest.mark.parametrize('status',[200,422])
def test_cancel_request_does_not_claim_terminal_cancellation(owner,status):
    with service(status=status) as (port,_,seen):
        op=start(owner,port,operation='CANCEL_ORDER',parameters={'order_id':ORDER},body=None)
        if status==200:
            with pytest.raises(RuntimeRefused,match='^HTTP_STATUS_UNACCEPTABLE$'):finish(op)
        else:assert finish(op).status_code==422
        assert len(seen)==1 and op.native_closed
