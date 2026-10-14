"""Real WinHTTP loopback retries and DPAPI evidence; invented inputs only."""
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urlparse,parse_qs
from uuid import uuid4
import json,threading,time,socket
import pytest
from compertum.data.encoding import canonical
from compertum.runtime.errors import RuntimeRefused
from compertum.runtime._winhttp_get import _PENDING
from compertum.runtime.paper_market_evidence import protect_market_evidence,publish_market_evidence,open_market_evidence
from compertum.runtime.paper_market_compose import compose_market_inputs
from compertum.runtime.paper_credentials import seal_paper_credentials
from test_winhttp_get import owner
from test_paper_market_qualification import credentials
from test_persistence import owned
from test_storage import manager
import test_paper_market_collection as f
import test_paper_market_compose as g

@contextmanager
def responses(items):
 seen=[]
 class Handler(BaseHTTPRequestHandler):
  def log_message(self,*a):pass
  def do_GET(self):
   i=len(seen);seen.append((time.monotonic_ns(),self.path,dict(self.headers)))
   status,body,headers=items[i] if i<len(items) else (599,b'{}',())
   if status is None:
    self.connection.shutdown(socket.SHUT_RDWR);self.connection.close();return
   self.send_response(status)
   for key,value in headers:self.send_header(key,value)
   self.end_headers();self.wfile.write(body)
 http=ThreadingHTTPServer(('127.0.0.1',0),Handler);http.daemon_threads=True
 thread=threading.Thread(target=http.serve_forever,kwargs={'poll_interval':.01},daemon=True);thread.start()
 try:yield http.server_port,seen
 finally:http.shutdown();http.server_close();thread.join(2);assert not thread.is_alive()

def run(c,limit=15):
 end=time.monotonic()+limit
 while c.status()['state'] in ('READY','PENDING'):
  assert time.monotonic()<end,'native retry fixture deadline'
  if c.status()['state']=='READY':c.dispatch()
  else:c.poll()
  time.sleep(.003)
 assert not _PENDING
 return c.private_snapshot().to_payload()

def seal(c,lease):
 return protect_market_evidence(lease,c.private_snapshot(),task_id=str(uuid4()))

@pytest.mark.parametrize('mode',['HISTORY','CURRENT_ACTIONS'])
def test_native_two_real_backoffs_preserve_cursor_and_failed_bodies(owner,credentials,mode):
 failed=b'{"message":"temporary local failure"}'
 items=[(200,f.body(mode,'next'),()),(503,failed,()),(429,failed,()),(200,f.body(mode),())]
 with responses(items) as (port,seen):
  c=f.collection(owner,credentials,port,mode);original=c._deadline_ns;v=run(c);seal(c,owner)
 assert v['version']==2 and v['state']=='PAGINATION_COMPLETE' and len(seen)==4 and len(v['selected_requests'])==2
 chain=v['attempt_chain'];assert [a['outcome'] for a in chain]==['SELECTED','RETRY','RETRY','SELECTED']
 assert [a['page_attempt'] for a in chain]==[1,1,2,3] and c._deadline_ns==original
 assert len({a['request']['request_id'] for a in chain})==4
 assert [parse_qs(urlparse(path).query).get('page_token') for _,path,_ in seen]==[None,['next'],['next'],['next']]
 for prior,next_attempt,seconds in ((chain[1],chain[2],1),(chain[2],chain[3],4)):
  assert next_attempt['pre_send_monotonic_ns']>=prior['completed_monotonic_ns']+seconds*10**9
  assert prior['native_closed'] and prior['reply']['body_utf8'].encode()==failed
 assert seen[2][0]-seen[1][0]>=10**9 and seen[3][0]-seen[2][0]>=4*10**9
 assert all(a['dispatch_committed_ns'] is not None and a['native_closed'] for a in chain)
 assert all('APCA-API-KEY-ID' not in headers for _,_,headers in seen)


def test_native_retry_after_controls_wait_without_consuming_attempt(owner,credentials):
 with responses([(429,b'{"message":"busy"}',(('Retry-After','2'),)),(200,f.body('HISTORY'),())]) as (port,seen):
  c=f.collection(owner,credentials,port);c.dispatch();f.finish(c)
  assert c.dispatch()=='WAITING' and len(seen)==1 and c.status()['attempts']==1 and not _PENDING
  v=run(c);seal(c,owner)
 a,b=v['attempt_chain'];assert a['retry_after']['delay_ns']==2*10**9
 assert b['pre_send_monotonic_ns']>=a['retry_after']['not_before_ns'] and len(seen)==2
 assert seen[1][0]-seen[0][0]>=2*10**9 and seen[1][0]>=a['retry_after']['not_before_ns']

@pytest.mark.parametrize('status,headers,raw',[(403,(),b'{"message":"denied"}'),(302,(('Location','http://127.0.0.1:9/no'),),b'{}'),(204,(),b''),(429,(('Retry-After','nonsense'),),b'{"message":"busy"}'),(503,(),b'{')])
def test_native_terminal_response_stays_single_attempt_and_publishable(owner,credentials,status,headers,raw):
 with responses([(status,raw,headers)]) as (port,seen):
  c=f.collection(owner,credentials,port);v=run(c);seal(c,owner)
 assert len(seen)==1 and v['state']=='INCOMPLETE' and v['attempts']==1 and v['version']==2
 a=v['attempt_chain'][0];assert a['observed_status']==status and a['native_closed'] and a['outcome']=='TERMINAL'
 if status in (302,204) or raw==b'{':assert a['reply'] is None


def test_native_third_failure_stops_with_all_bodies(owner,credentials):
 with responses([(503,b'{"message":"busy"}',())]*3) as (port,seen):
  c=f.collection(owner,credentials,port);v=run(c);seal(c,owner)
 assert len(seen)==3 and v['state']=='INCOMPLETE' and v['attempt_chain'][-1]['terminal_reason']=='PAGE_ATTEMPT_LIMIT'
 assert all(a['reply']['body_utf8']=='{"message":"busy"}' for a in v['attempt_chain'])


def test_native_retried_history_encrypts_reopens_and_composes_same_math(owned):
 project,leases=owned;e=leases['execution'];m=manager(owned)
 credential=seal_paper_credentials(e,'paper-primary',bytearray(f.KEY.encode()),bytearray(f.SECRET.encode()))
 rows=[dict(t=t,o=100,h=102,l=99,c=100.125,v=20000) for t in f.plan(e).to_payload()['daily_labels']]
 items=[(503,b'{"message":"busy"}',())]+[(200,f.body('HISTORY',str(i+1) if i<2 else None,rows[i*100:(i+1)*100]),()) for i in range(3)]
 with responses(items) as (port,seen):c=f.collection(e,credential,port);original=run(c)
 pair,_=g.fresh(e,credential);combined=compose_market_inputs(e,c.private_snapshot(),pair.private_snapshot());live=combined.to_payload();combined.close()
 protected=seal(c,e);grant=m.reserve_bytes(protected.task_id,'records',len(protected.ciphertext));receipt=publish_market_evidence(m,grant,protected)
 assert (project.root_path/receipt['path']).read_bytes()==protected.ciphertext
 assert b'{"message":"busy"}' not in protected.ciphertext and f.KEY.encode() not in protected.ciphertext
 c.close()
 with open_market_evidence(e,'paper-primary',protected.collection_id,receipt) as opened:
  v=opened.snapshot();assert v['collection']==original and len(v['selected_records'])==3
  out=compose_market_inputs(e,opened,pair.private_snapshot()).to_payload()
  assert out['diagnostic']==live['diagnostic'] and out['diagnostic']['history']['observed_sessions']==252
  assert out['diagnostic']['history']['mean_dollar_volume']=='2002500'
  assert out['history']['freshness']=='NOT_RESTORED' and not out['transport_authorized']
 assert len(seen)==4 and not _PENDING


def test_native_disconnect_is_terminal_without_invented_reply(owner,credentials):
 with responses([(None,b"",())]) as (port,seen):
  c=f.collection(owner,credentials,port);v=run(c);seal(c,owner)
 assert len(seen)==1 and v["state"]=="INCOMPLETE" and v["attempts"]==1 and not _PENDING
 a=v["attempt_chain"][0];assert a["observed_status"] is None and a["reply"] is None and a["native_closed"]


def test_direct_close_retains_uncertain_exchange_until_confirmed(owner,credentials,monkeypatch):
 with f.server(stall=True) as (port,arrived,seen):
  c=f.collection(owner,credentials,port);c.dispatch();assert arrived.wait(1);exchange=c._pending;t=exchange._transport
  with monkeypatch.context() as patch:
   patch.setattr(t._closing,"wait",lambda _:False)
   with pytest.raises(RuntimeRefused,match="HTTP_CLEANUP_UNVERIFIED"):c.close()
   assert not t.native_closed and _PENDING
  c.close();assert t.native_closed and not _PENDING and len(seen)==1


def test_native_reservation_refuses_large_next_page_before_dispatch(owner,credentials):
 rows=[dict(t=t,o=100,h=102,l=99,c=100.125,v=20000) for t in f.plan(owner).to_payload()['daily_labels']]
 bodies=[canonical(dict(json.loads(f.body('HISTORY',str(i+1) if i<7 else None,rows[i*32:(i+1)*32])),unknown_padding='\\"'*14000)) for i in range(8)]
 with responses([(200,b,()) for b in bodies]) as (port,seen):
  c=f.collection(owner,credentials,port)
  with pytest.raises(RuntimeRefused,match='^PAPER_COLLECTION_RETENTION_LIMIT$'):run(c)
  v=c.private_snapshot().to_payload();seal(c,owner);count=len(seen)
  assert 0<count<8 and v['attempts']==count and v['reason']=='RETENTION_LIMIT'
  assert [a['reply']['body_utf8'].encode() for a in v['attempt_chain']]==bodies[:count]
  assert all(a['outcome']=='SELECTED' and a['native_closed'] for a in v['attempt_chain'])
  with pytest.raises(RuntimeRefused):c.dispatch()
  assert len(seen)==count and not _PENDING
