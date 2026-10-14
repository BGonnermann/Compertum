"""Actual supervisor/owner channels with test-only local market producers."""
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.parse import urlparse,parse_qs
import json,os,subprocess,sys
from compertum.config import load_config
from compertum.data.encoding import canonical
from compertum.runtime.paper_credential_slot import SLOT_PATH
from compertum.runtime.errors import RuntimeRefused

root=Path(sys.argv[1]).resolve();mode=sys.argv[2];assert mode in {'collect','fresh','verify'}
assert '.cache' in root.parts and 'test-runs' in root.parts
config=load_config(root/'config.toml',root)
if not (root/SLOT_PATH).exists():
 env={k:v for k,v in os.environ.items() if k.upper() in {'SYSTEMROOT','WINDIR','PYTHONPATH','TEMP','TMP'}}
 env.update(__PYVENV_LAUNCHER__=sys.executable,PYTHONNOUSERSITE='1',PYTHONDONTWRITEBYTECODE='1')
 child=subprocess.run([sys.executable,'-B',str(Path(__file__).with_name('provision_paper_read.py')),str(root)],executable=sys._base_executable,env=env,capture_output=True,timeout=15,creationflags=0x08000000)
 assert child.returncode==0,child.stderr.decode()
rows=json.loads((root/'market-fixture-rows.json').read_text());assert len(rows)==252;seen=[]
class Handler(BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def do_GET(self):
  assert self.headers.get('X-Compertum-Test')=='synthetic'
  assert not any(k.lower().startswith('apca-') for k in self.headers)
  seen.append(self.path);url=urlparse(self.path)
  if url.path=='/v2/stocks/bars':
   assert mode=='collect';index=int(parse_qs(url.query).get('page_token',['0'])[0]);assert index in (0,1,2)
   payload=dict(bars={'MSFT':rows[index*100:(index+1)*100]},next_page_token=str(index+1) if index<2 else None,padding='x'*40000)
  elif url.path=='/v2/assets/MSFT':
   assert mode=='fresh';payload=dict(id='12345678-1234-4234-8234-123456789099',symbol='MSFT',exchange='NASDAQ',status='active',tradable=True);payload['class']='us_equity'
  else:
   assert mode=='fresh' and url.path=='/v2/stocks/quotes/latest'
   payload=dict(quotes={'MSFT':dict(t='2023-11-24T14:35:00+00:00',bp=100.125,ap=100.25,bs=10,**{'as':20},bx='V',ax='V')})
  raw=canonical(payload);self.send_response(200);self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
server=ThreadingHTTPServer(('127.0.0.1',0),Handler);server.daemon_threads=True
(root/'market-loopback-fixture.json').write_text(json.dumps(dict(port=server.server_port,kind='invented-native-market-test')))
thread=Thread(target=server.serve_forever,daemon=True);thread.start()
original=subprocess.list2cmdline;helper=Path(__file__).with_name('paper_market_execution.py').resolve()
def command(args):
 if len(args)>=6 and args[2:4]==['-m','compertum.runtime.managed_owner'] and json.loads(args[-1])['role']=='execution':args=args[:2]+[str(helper)]+args[4:]
 return original(args)
subprocess.list2cmdline=command
import compertum.runtime.supervisor as module
import compertum.runtime.paper_market_publication as publication
call=publication.call_owner;lost=[]
def drop_ack(remote,action,payload):
 result=call(remote,action,payload)
 if mode=='collect' and action=='paper_market_transfer' and payload.get('operation')=='ack' and not lost:
  lost.append(True);raise RuntimeRefused('FIXTURE_ACK_REPLY_LOST')
 return result
publication.call_owner=drop_ack
try:
 s=module.Supervisor(config);status=s.status;s.status=lambda:dict(status(),fixture_requests=list(seen))
 s.run(maximum_seconds=55)
finally:
 server.shutdown();server.server_close();thread.join(2)
 print(json.dumps(dict(requests=seen,lost_ack_receipts=len(lost),real_provider_requests=0)),flush=True)
