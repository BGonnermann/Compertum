"""Full native owners with test-only loopback endpoint; no real credentials."""
from datetime import datetime,timedelta,timezone
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from zoneinfo import ZoneInfo
import json,os,subprocess,sys,time
from compertum.config import load_config
from compertum.runtime.identity import resolve_project
from compertum.runtime.owners import acquire_owner,release_owner
from compertum.runtime.paper_credentials import seal_paper_credentials
from compertum.runtime.paper_credential_slot import provision_paper_slot,SLOT_PATH
from compertum.storage import StorageManager,reserve_runtime_paths
root=Path(sys.argv[1]).resolve();mode=sys.argv[2];assert mode in {'complete','cancel','restart'}
assert '.cache' in root.parts and 'test-runs' in root.parts
config=load_config(root/'config.toml',root)
if not (root/SLOT_PATH).exists():
 env={k:v for k,v in os.environ.items() if k.upper() in {'SYSTEMROOT','WINDIR','PYTHONPATH','TEMP','TMP'}}
 env.update(__PYVENV_LAUNCHER__=sys.executable,PYTHONNOUSERSITE='1',PYTHONDONTWRITEBYTECODE='1')
 child=subprocess.run([sys.executable,'-B',str(Path(__file__).with_name('provision_paper_read.py')),str(root)],executable=sys._base_executable,env=env,capture_output=True,timeout=15,creationflags=0x08000000)
 assert child.returncode==0,child.stderr.decode()
seen=[]
class Handler(BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def do_GET(self):
  assert self.headers.get('X-Compertum-Test')=='synthetic'
  assert not any(k.lower().startswith('apca-') for k in self.headers)
  seen.append(self.path)
  if mode=='cancel' and self.path.startswith('/v2/account/activities'):time.sleep(3);return
  now=datetime.now(timezone.utc);stamp=now.isoformat()
  payload={'/v2/account/activities':[],'/v2/account':dict(id='11111111-1111-4111-8111-111111111111',status='ACTIVE',currency='USD',cash='1000',equity='1000',buying_power='4000',trading_blocked=False,account_blocked=False,trade_suspended_by_user=False,padding='x'*48000),
   '/v2/clock':dict(timestamp=stamp,is_open=False,next_open=(now+timedelta(days=1)).isoformat(),next_close=(now+timedelta(days=1,hours=6)).isoformat()),'/v2/calendar':[],'/v2/positions':[],'/v2/orders':[]}[self.path.split('?')[0]]
  raw=json.dumps(payload).encode();self.send_response(200);self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
server=ThreadingHTTPServer(('127.0.0.1',0),Handler);server.daemon_threads=True
(root/'loopback-fixture.json').write_text(json.dumps(dict(port=server.server_port,kind='invented-native-read-test')))
thread=Thread(target=server.serve_forever,daemon=True);thread.start()
original=subprocess.list2cmdline
helper=Path(__file__).with_name('paper_reconciliation_execution.py').resolve()
def command(args):
 if len(args)>=6 and args[2:4]==['-m','compertum.runtime.managed_owner'] and json.loads(args[-1])['role']=='execution':args=args[:2]+[str(helper)]+args[4:]
 return original(args)
subprocess.list2cmdline=command
import compertum.runtime.supervisor as module
s=module.Supervisor(config);status=s.status
s.status=lambda:dict(status(),fixture_requests=list(seen))
class LostReply(Exception):pass
lost=[];dispatch=s._dispatch;serve=module.serve_control_once
if mode=='complete':
 def drop(decision,action,payload):
  result=dispatch(decision,action,payload)
  if action=='paper_activity' and payload.get('operation')=='start' and not lost:lost.append(result);raise LostReply()
  return result
 def reconnect(*args,**kwargs):
  try:return serve(*args,**kwargs)
  except LostReply:return None
 s._dispatch=drop;module.serve_control_once=reconnect
import compertum.runtime.paper_activity_publication as activity_publication
native_call=activity_publication.call_owner
lost_ack=[]
def drop_ack(remote,action,payload):
 result=native_call(remote,action,payload)
 if mode=='complete' and action=='paper_activity_transfer' and payload.get('operation')=='ack' and not lost_ack:
  lost_ack.append(True)
  from compertum.runtime.errors import RuntimeRefused
  raise RuntimeRefused('FIXTURE_LOST_ACTIVITY_ACK')
 return result
activity_publication.call_owner=drop_ack
try:s.run(maximum_seconds=75)
finally:server.shutdown();server.server_close();thread.join(2)
print(json.dumps(dict(requests=seen,lost_start_receipts=len(lost),real_account_calls=0,lost_activity_acks=len(lost_ack),account_opening_origin='INVENTED_TEST_ONLY',activity_origin='LOOPBACK_FIXTURE')),flush=True)
