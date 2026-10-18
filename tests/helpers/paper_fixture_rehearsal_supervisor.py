"""One bounded native rehearsal phase with invented local source replies."""
from pathlib import Path
import hashlib,json,os,subprocess,sys
master=Path(__file__).parents[2];sys.path.insert(0,str(master/'tests'))
from helpers.fixture_rehearsal_source import OriginalSourceServer
from compertum.config import load_config
from compertum.runtime.paper_credential_slot import SLOT_PATH
from compertum.runtime.identity import resolve_project
root=Path(sys.argv[1]).resolve();plan_path=Path(sys.argv[2]).resolve()
assert plan_path.parent==master/'artifacts/m5/risk-dispatch-20261017-01'
raw=plan_path.read_bytes();plan=json.loads(raw)
assert plan['scope']=='CONTROLLED_LOCAL_REHEARSAL' and plan['project_id']==resolve_project(root).project_id
assert (root/SLOT_PATH).is_file() and not (root/'state/watchdog/halt.json').exists()
assert (root/'config.toml').read_bytes()==(master/'config/default.toml').read_bytes()
app=OriginalSourceServer(root,lose_buy_reply=plan['phase']=='BUY')
fixture=dict(kind='controlled-native-rehearsal',port=app.server.server_port,plan_path=str(plan_path),plan_sha256=hashlib.sha256(raw).hexdigest())
(root/'loopback-fixture.json').write_text(json.dumps(fixture))
original=subprocess.list2cmdline;helper=Path(__file__).with_name('paper_fixture_rehearsal_execution.py').resolve()
def command(args):
 if len(args)>=6 and args[2:4]==['-m','compertum.runtime.managed_owner'] and json.loads(args[-1])['role']=='execution':args=args[:2]+[str(helper)]+args[4:]
 return original(args)
subprocess.list2cmdline=command
from compertum.runtime.supervisor import Supervisor
app.start()
try:
 s=Supervisor(load_config(root/'config.toml',root));app.supervisor=s
 s.run(maximum_seconds=96)
 snapshot=app.orders.snapshot()
finally:app.close()
print(json.dumps(dict(requests=app.requests,writes=app.writes,source_errors=app.errors,reply_lost=app.lost,
 inventory=snapshot['inventory'],source_journal_sha256=snapshot['journal_sha256'],real_account_calls=0,actual_broker_actions=0,
 clock_substituted=False,queue_clock_substituted=False,source_origin='INVENTED_CONTROLLED_LOCAL_SOURCE')),flush=True)
