"""Real Windows owners with one original controlled local economic source."""
from dataclasses import asdict
from datetime import datetime,timedelta,timezone
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from threading import Thread,RLock
import json,os,socket,sqlite3,subprocess,sys,time
from stateful_economic_fixture import ControlledEconomicSource
from compertum.config import load_config
from compertum.data.encoding import canonical
from compertum.persistence import _active_store_path
from compertum.runtime.identity import resolve_project
from compertum.runtime._windows import WindowsAPI
from compertum.fixture_order_origin import decode_order_origin

root=Path(sys.argv[1]).resolve();mode=sys.argv[2];foreign_port=int(sys.argv[3])
assert mode in {'positive','change','restart'}
master=Path(__file__).parents[2];records=master/'artifacts/m5/native-economics-20261017-01'
assert root==master/'.cache/test-runs/native-economic-fresh-20261017-01/native-shared'
birth=json.loads((records/'original-source-birth01.json').read_text())
project=resolve_project(root);assert project.project_id==birth['project_id']
stamp=lambda:datetime.now(timezone.utc).isoformat().replace('+00:00','Z')
source=ControlledEconomicSource.open(root/'state/fixture-economic-source.jsonl',stamp)
assert source._producer==birth['producer_id'] and source._genesis==birth['genesis_sha256']
order_birth=json.loads((records/'original-order-source-birth01.json').read_text())
order_path=root/'state/fixture-order-source.jsonl';order_raw=order_path.read_bytes();order_origin=json.loads(order_raw)
import hashlib
assert hashlib.sha256(order_raw).hexdigest()==order_birth['origin_sha256']
assert canonical(order_origin)+b'\n'==order_raw and order_origin['kind']=='ORDER_SOURCE_BEGIN'
assert order_origin['project_id']==project.project_id and order_origin['economic_producer_id']==source._producer
assert order_origin['economic_genesis_sha256']==source._genesis
assert order_origin['initial_inventory']==dict(orders=[],positions=[],fills=[])
order_source=decode_order_origin(order_raw)
def order_inventory():
 api=WindowsAPI()
 with api.open_file(order_path,0x80000000,1) as handle:
  assert list(api.file_identity(handle))==order_birth['file_identity']
  assert order_path.read_bytes()==order_raw
 return json.loads(canonical(order_origin['initial_inventory']))
config=load_config(root/'config.toml',root)
from compertum.runtime.paper_credential_slot import SLOT_PATH
if not (root/SLOT_PATH).exists():
 env={k:v for k,v in os.environ.items() if k.upper() in {'SYSTEMROOT','WINDIR','PYTHONPATH','TEMP','TMP'}}
 env.update(__PYVENV_LAUNCHER__=sys.executable,PYTHONNOUSERSITE='1',PYTHONDONTWRITEBYTECODE='1')
 child=subprocess.run([sys.executable,'-B',str(Path(__file__).with_name('provision_paper_read.py')),str(root)],
  executable=sys._base_executable,env=env,capture_output=True,timeout=15,creationflags=0x08000000)
 assert child.returncode==0,child.stderr.decode()
lock=RLock();seen=[];s=None

def opening_confirmed():
 path=_active_store_path(root,project.project_id,'execution')
 if not path.exists():return False
 with sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=1) as db:
  return db.execute("SELECT 1 FROM state WHERE key='paper_opening:fixture'").fetchone() is not None

def pay_once():
 if not opening_confirmed():return
 ids={e['event_id'] for e in source._events}
 if 'native-economic-accrual' not in ids:
  source.append(dict(event_id='native-economic-accrual',kind='ACCRUAL',amount='0.02',rule_id='account-fee'))
 if 'native-economic-payment' not in ids:
  source.append(dict(event_id='native-economic-payment',kind='PAYMENT',amount='0.02',
   accrual_id='native-economic-accrual',activity_id='original::native-economic-payment'))

class Handler(BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def do_GET(self):
  assert self.headers.get('X-Compertum-Test')=='synthetic'
  assert not any(k.lower().startswith('apca-') for k in self.headers)
  with lock:
   seen.append(self.path);now=datetime.now(timezone.utc);path=self.path.split('?')[0]
   if path in {'/v2/account','/v2/account/activities'}:pay_once()
   if path=='/v2/account':
    observation=source.observations();snapshot=source.snapshot(opening_sha256='0'*64,history_sha256='0'*64,until=stamp())
    peer=dict(project_id=project.project_id,generation=s.supervisor.generation,identity=asdict(s.supervisor.identity),logon_sid=project.logon_sid)
    payload=dict(id='11111111-1111-4111-8111-111111111111',status='ACTIVE',currency='USD',
     cash=observation['cash'],equity=observation['cash'],buying_power='4000',trading_blocked=False,account_blocked=False,
     trade_suspended_by_user=False,compertum_fixture_source=dict(version=1,producer_id=snapshot['producer_id'],
      genesis_sha256=snapshot['genesis_sha256'],ledger=snapshot['ledger'],served_by=peer,
      order_source={k:order_source[k] for k in ('producer_id','genesis_sha256','journal_sha256')}))
   elif path=='/v2/account/activities':payload=[*source.observations()['activities'],*order_inventory()['fills']]
   elif path in {'/v2/positions','/v2/orders'}:payload=order_inventory()['positions' if path=='/v2/positions' else 'orders']
   else:
    payload={'/v2/clock':dict(timestamp=now.isoformat(),is_open=False,next_open=(now+timedelta(days=1)).isoformat(),
     next_close=(now+timedelta(days=1,hours=6)).isoformat()),'/v2/calendar':[]}[path]
   raw=json.dumps(payload).encode()
  self.send_response(200);self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)

class ExclusiveServer(ThreadingHTTPServer):
 allow_reuse_address=False
 daemon_threads=True
 def server_bind(self):
  self.socket.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)
  super().server_bind()
server=ExclusiveServer(('127.0.0.1',0),Handler)
(root/'loopback-fixture.json').write_text(json.dumps(dict(port=server.server_port,kind='original-native-economic-test',foreign_port=foreign_port)))
thread=Thread(target=server.serve_forever,daemon=True);thread.start()
original=subprocess.list2cmdline;helper=Path(__file__).with_name('paper_economic_execution.py').resolve()
def command(args):
 if len(args)>=6 and args[2:4]==['-m','compertum.runtime.managed_owner'] and json.loads(args[-1])['role']=='execution':args=args[:2]+[str(helper)]+args[4:]
 return original(args)
subprocess.list2cmdline=command
import compertum.runtime.supervisor as module
s=module.Supervisor(config);dispatch=s._dispatch;changed=[]
def observed_dispatch(decision,action,payload):
 result=dispatch(decision,action,payload)
 if mode=='change' and action=='paper_activity' and payload.get('operation')=='status' and result.get('fixture_economic_phase')=='VERIFY' and not changed:
  with lock:source.snapshot(opening_sha256='0'*64,history_sha256='0'*64,until=stamp())
  changed.append(True)
 return result
s._dispatch=observed_dispatch
try:s.run(maximum_seconds=75)
finally:server.shutdown();server.server_close();thread.join(2);source.close()
print(json.dumps(dict(requests=seen,source_changes=len(changed),real_account_calls=0,actual_broker_actions=0,
 account_opening_origin='INVENTED_TEST_ONLY',activity_origin='LOOPBACK_FIXTURE')),flush=True)
