"""Native async WinHTTP against this test's loopback server; no broker calls."""
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import os
import threading
import time
import pytest
from compertum.runtime.errors import RuntimeRefused
from compertum.runtime.identity import resolve_project
from compertum.runtime.owners import acquire_owner,release_owner,_LEASES
from compertum.runtime._winhttp_get import _OwnedGet,_PENDING

pytestmark=pytest.mark.skipif(os.name!='nt',reason='NATIVE_WINDOWS_UNAVAILABLE')

def warm_budget(lease):
    from compertum.runtime.service_budget import _install_loopback_queue
    from compertum.runtime.owners import _LEASES
    if _LEASES[lease]._service_queue is not None:
        assert _LEASES[lease]._service_queue._fixture
        return _LEASES[lease]._service_queue
    class Clock:
        ns=0
        def __call__(self):return self.ns
    clock=Clock();q=_install_loopback_queue(lease,clock);clock.ns=60*10**9
    return q

@pytest.fixture
def owner(tmp_path):
    lease=acquire_owner(resolve_project(tmp_path),'execution');warm_budget(lease)
    try:yield lease
    finally:
        if lease in _LEASES:release_owner(lease)

@contextmanager
def server(body=b'{"ok":true}',status=200,headers=(),stall=False,stall_after_body=False):
    arrived=threading.Event();release=threading.Event();seen=[]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):
            seen.append((self.path,dict(self.headers)));arrived.set()
            if stall:release.wait(10)
            try:
                self.send_response(status)
                for key,value in headers:self.send_header(key,value)
                self.end_headers();self.wfile.write(body);self.wfile.flush()
                if stall_after_body:release.wait(10)
            except (BrokenPipeError,ConnectionResetError,ConnectionAbortedError):pass
    http=ThreadingHTTPServer(('127.0.0.1',0),Handler);http.daemon_threads=True
    thread=threading.Thread(target=http.serve_forever,kwargs={'poll_interval':.01},daemon=True);thread.start()
    try:yield http.server_port,arrived,seen
    finally:
        release.set();http.shutdown();http.server_close();thread.join(2)
        assert not thread.is_alive()


def start(lease,port,**kwargs):
    return _OwnedGet(lease,host='127.0.0.1',port=port,secure=False,path='/fixture',headers={'X-Compertum-Test':'synthetic'},timeout=kwargs.get('timeout',3))


def finish(operation):
    deadline=time.monotonic()+5
    while time.monotonic()<deadline:
        value=operation.poll()
        if value is not None:return value
        time.sleep(.002)
    raise AssertionError('poll did not terminate')


def test_real_async_success_and_child_handle_closure(owner):
    with server() as (port,arrived,seen):
        begin=time.monotonic();op=start(owner,port)
        assert time.monotonic()-begin<.5
        result=finish(op)
        assert result.status_code==200 and result.body==b'{"ok":true}'
        assert len(seen)==1 and seen[0][0]=='/fixture'
        assert seen[0][1]['X-Compertum-Test']=='synthetic'
        assert seen[0][1]['Accept-Encoding']=='identity'
        assert op.native_closed and id(op) not in _PENDING
        assert not any(bytes(op._headers))
        assert 'synthetic' not in repr(op) and 'ok' not in repr(result)
        op.close();op.close()


@pytest.mark.parametrize('size',[0,65535,65536])
def test_eof_confirms_body_at_or_below_cap(owner,size):
    with server(body=b'x'*size) as (port,_,seen):
        op=start(owner,port)
        try:assert finish(op).body==b'x'*size
        finally:op.close()
        assert len(seen)==1 and op.native_closed and op.status_code==200


@pytest.mark.parametrize('size',[65537,80000])
def test_body_overflow_is_refused_and_handles_close(owner,size):
    with server(body=b'x'*size) as (port,_,seen):
        op=start(owner,port)
        with pytest.raises(RuntimeRefused,match='^HTTP_BODY_LIMIT$'):finish(op)
        assert op.native_closed and len(seen)==1 and id(op) not in _PENDING


@pytest.mark.parametrize('status,headers',[(302,(('Location','http://127.0.0.1:9/forbidden'),)),(401,(('WWW-Authenticate','Negotiate'),)),(500,()),(408,())])
def test_status_never_follows_redirect_authenticates_or_retries(owner,status,headers):
    with server(status=status,headers=headers) as (port,_,seen):
        op=start(owner,port)
        with pytest.raises(RuntimeRefused,match='^HTTP_STATUS_UNACCEPTABLE$'):finish(op)
        assert len(seen)==1 and op.native_closed and op.status_code==status


def test_unexpected_compression_is_rejected(owner):
    with server(headers=(('Content-Encoding','gzip'),)) as (port,_,seen):
        op=start(owner,port)
        with pytest.raises(RuntimeRefused,match='^HTTP_ENCODING_UNACCEPTABLE$'):finish(op)
        assert len(seen)==1 and op.native_closed


def test_stalled_request_remains_pollable_and_cancels(owner):
    with server(stall=True) as (port,arrived,_):
        op=start(owner,port);assert arrived.wait(1)
        begin=time.monotonic()
        for _ in range(10):assert op.poll() is None
        assert time.monotonic()-begin<.5
        op.close()
        assert op.native_closed and id(op) not in _PENDING
        with pytest.raises(RuntimeRefused,match='^HTTP_CLOSED$'):op.poll()


def test_total_deadline_refuses_stalled_request(owner):
    with server(stall=True) as (port,_,_):
        op=start(owner,port,timeout=.15);begin=time.monotonic()
        with pytest.raises(RuntimeRefused,match='^HTTP_DEADLINE_EXCEEDED$'):finish(op)
        assert time.monotonic()-begin<2 and op.native_closed


def test_releasing_execution_owner_cancels_native_request(owner):
    with server(stall=True) as (port,arrived,_):
        op=start(owner,port);assert arrived.wait(1);release_owner(owner)
        assert op.native_closed and id(op) not in _PENDING
        with pytest.raises(RuntimeRefused):op.poll()


@pytest.mark.parametrize('change',[{'host':'api.alpaca.markets'},{'host':'paper-api.alpaca.markets','secure':False},{'path':'https://example.com/'},{'path':'/bad\r\nInjected: x'},{'headers':{'X-Compertum-Test':'has\nnewline'}},{'headers':{'APCA-API-KEY-ID':'secret'}},{'timeout':0},{'timeout':11}])
def test_invalid_boundary_refuses_before_native_request(owner,change):
    args=dict(host='127.0.0.1',port=12345,secure=False,path='/fixture',headers={'X-Compertum-Test':'synthetic'},timeout=3);args.update(change)
    with pytest.raises(RuntimeRefused,match='^HTTP_INPUT_INVALID$'):_OwnedGet(owner,**args)
    assert not _PENDING


def test_conflicting_duplicate_encoding_is_refused(owner):
    with server(headers=(('Content-Encoding','identity'),('Content-Encoding','gzip'))) as (port,_,_):
        op=start(owner,port)
        with pytest.raises(RuntimeRefused,match='^HTTP_HEADERS_INVALID$'):finish(op)
        assert op.native_closed


def test_exact_cap_without_eof_is_not_success(owner):
    with server(body=b'x'*65536,stall_after_body=True) as (port,_,_):
        op=start(owner,port,timeout=.15)
        with pytest.raises(RuntimeRefused,match='^HTTP_DEADLINE_EXCEEDED$'):finish(op)
        assert op.native_closed


def test_expiry_during_finalization_cannot_publish_success(owner,monkeypatch):
    with server() as (port,_,_):
        op=start(owner,port);actual_close=op.close
        def slow_close():
            actual_close();op._deadline=time.monotonic()-1
        monkeypatch.setattr(op,'close',slow_close)
        with pytest.raises(RuntimeRefused,match='^HTTP_DEADLINE_EXCEEDED$'):finish(op)
        assert op._result is None and op.native_closed


@pytest.mark.parametrize('headers,body',[(('Content-Length','50'),b'short'),(('X-Oversized','x'*20000),b'body')],ids=['truncated','oversize_headers'])
def test_malformed_or_oversized_response_refuses(owner,headers,body):
    with server(headers=(headers,),body=body) as (port,_,_):
        op=start(owner,port)
        with pytest.raises(RuntimeRefused):finish(op)
        assert op.native_closed


@pytest.mark.parametrize('stage',['Open','SetTimeouts','Connect','OpenRequest','SetOption','SetStatusCallback','SendRequest'])
def test_setup_failures_release_every_created_native_handle(owner,monkeypatch,stage):
    import compertum.runtime._winhttp_get as module
    real=module._API();live=set()
    class FailingAPI:
        callback_type=real.callback_type
        def __getattr__(self,name):
            fn=getattr(real,name)
            def call(*args):
                if name==stage:return module.H(-1).value if name=='SetStatusCallback' else 0
                result=fn(*args)
                if name in ('Open','Connect','OpenRequest') and result:live.add(result)
                if name=='CloseHandle' and result:live.remove(args[0])
                return result
            return call
    monkeypatch.setattr(module,'_API',FailingAPI)
    with pytest.raises(RuntimeRefused,match='^HTTP_NATIVE_FAILED$'):start(owner,12345)
    assert not live and not _PENDING


def test_uncertain_closure_retains_callback_storage_until_closing_is_seen(owner,monkeypatch):
    with server(stall=True) as (port,arrived,_):
        op=start(owner,port);assert arrived.wait(1)
        with monkeypatch.context() as patch:
            patch.setattr(op._closing,'wait',lambda timeout:False)
            with pytest.raises(RuntimeRefused,match='^HTTP_CLEANUP_UNVERIFIED$'):op.close()
            assert not op.native_closed and _PENDING[id(op)] is op and op._callback is not None
        op.close()
        assert op.native_closed and id(op) not in _PENDING


def test_only_one_native_request_per_execution_owner(owner):
    with server(stall=True) as (port,arrived,seen):
        first=start(owner,port);assert arrived.wait(1)
        with pytest.raises(RuntimeRefused,match='^HTTP_BUSY$'):start(owner,port)
        first.close();assert len(seen)==1


def test_enormous_timeout_is_a_fixed_input_refusal(owner):
    with pytest.raises(RuntimeRefused,match='^HTTP_INPUT_INVALID$'):start(owner,12345,timeout=10**500)


def test_expired_setup_cannot_start_network(owner,monkeypatch):
    from types import SimpleNamespace
    import compertum.runtime._winhttp_get as module
    real=module._API();shift=[0];sent=[];clock=time.monotonic
    monkeypatch.setattr(module,'time',SimpleNamespace(monotonic=lambda:clock()+shift[0]))
    class SlowSetup:
        callback_type=real.callback_type
        def __getattr__(self,name):
            fn=getattr(real,name)
            def call(*args):
                if name=='SendRequest':sent.append(True)
                result=fn(*args)
                if name=='SetStatusCallback':shift[0]=20
                return result
            return call
    monkeypatch.setattr(module,'_API',SlowSetup)
    with pytest.raises(RuntimeRefused,match='^HTTP_DEADLINE_EXCEEDED$'):start(owner,12345)
    assert sent==[] and not _PENDING


def test_serial_requests_leave_no_owned_transport_resources(owner):
    before=list(_LEASES[owner].resources)
    with server(body=bytes(range(256))*64) as (port,_,seen):
        for _ in range(12):
            op=start(owner,port);assert finish(op).body==bytes(range(256))*64
            assert op.native_closed and not _PENDING and _LEASES[owner].resources==before
        assert len(seen)==12
