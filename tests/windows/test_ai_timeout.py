from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
import threading,time,json,httpx
import pytest
from compertum.ai.strata import MODEL,request_proposal,native_post
from compertum.domain import TaskSpec,ContractError
from compertum.runtime.identity import resolve_project
from compertum.runtime.owners import acquire_owner
from compertum.persistence import open_store

def test_native_owned_socket_timeout_blocks_next_dispatch(tmp_path):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):
            value={'/health':{'model':MODEL,'loaded':True},'/v1/models':{'data':[{'id':MODEL}]},'/v1/status':{'model':MODEL,'engine':'fixture','concurrency':{'serving':1},'context':{'max_positions':65536},'activity':{'in_flight':0},'structured_output':{}}}[self.path]
            body=json.dumps(value).encode();self.send_response(200);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
        def do_POST(self):
            self.rfile.read(int(self.headers['Content-Length']));time.sleep(.5)
            try:self.send_response(200);self.end_headers();self.wfile.write(b'{}')
            except OSError:pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    class LoopbackFixtureTransport(httpx.BaseTransport):
        def __init__(self):self.native=httpx.HTTPTransport()
        def handle_request(self,r):return self.native.handle_request(httpx.Request(r.method,r.url.copy_with(port=server.server_port),headers=r.headers,content=r.content,extensions=r.extensions))
        def close(self):self.native.close()
    try:
        with acquire_owner(resolve_project(tmp_path),'coordinator') as lease:
            store=open_store(lease,'coordinator');task=TaskSpec(kind='AI_QUALIFICATION')
            with httpx.Client(transport=LoopbackFixtureTransport(),trust_env=False) as client:
                start=time.monotonic()
                with pytest.raises(ContractError,match='TIMEOUT'):request_proposal(store,task,[{'role':'user','content':'timeout'}],client=client,post=lambda b,t:native_post(b,t,server.server_port),timeout=.1,diagnostic=True)
                assert time.monotonic()-start<2 and store.get('local-timeout-unresolved') is True
                with pytest.raises(ContractError,match='UNCERTAIN'):request_proposal(store,task,[{'role':'user','content':'next'}],client=client,diagnostic=True)
            store.close()
    finally:server.shutdown();server.server_close();thread.join(2)

def test_native_absolute_deadline_with_slow_body(tmp_path):
    class Drip(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_POST(self):
            self.rfile.read(int(self.headers['Content-Length']));self.send_response(200);self.send_header('Content-Length','1000');self.end_headers()
            try:
                for n in range(40):self.wfile.write(b'x');self.wfile.flush();time.sleep(.03)
            except OSError:pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Drip);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        started=time.monotonic()
        with pytest.raises(httpx.ReadTimeout):native_post({'fixture':'slow body'},.2,server.server_port)
        assert .15<=time.monotonic()-started<.6
    finally:server.shutdown();server.server_close();thread.join(2)
