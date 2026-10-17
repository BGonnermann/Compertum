"""Real Windows owners, original journal, and invented local account replies."""
import json,os,socket,sqlite3,subprocess,sys,time
from pathlib import Path
from uuid import uuid4
import pytest
from compertum.runtime.errors import RuntimeRefused
from test_paper_activity_control import ROOT,control,output,stop,account,activity

RECORDS=ROOT/'artifacts/m5/native-economics-20261017-01'

def admitted_root():
 root=Path(os.environ['COMPERTUM_ECONOMIC_FIXTURE'])
 assert root==ROOT/'.cache/test-runs/native-economic-fresh-20261017-01/native-shared'
 admitted=json.loads((RECORDS/'capacity-activation.json').read_text())['admission']
 assert admitted['scratch_cap_gib']==15 and admitted['additional_native_folders']==1
 saved=json.loads((RECORDS/'fresh-native-fixture-result.json').read_text())
 from compertum.runtime._windows import WindowsAPI
 from compertum.runtime.identity import resolve_project
 assert resolve_project(root).project_id==saved['project_id']
 api=WindowsAPI()
 with api.open_file(root/'state/execution-reserve.bin',0x80,1) as handle:
  assert list(api.file_identity(handle))==saved['reserve_identity']
 assert not (root/'state/watchdog/halt.json').exists()
 assert (root/'config.toml').read_bytes()==(ROOT/'config/default.toml').read_bytes()
 # This continuation must retain the original opening and bounded history.
 with sqlite3.connect((root/'state/execution.sqlite').as_uri()+'?mode=ro',uri=True) as db:
  assert db.execute("SELECT count(*) FROM state WHERE key='paper_opening:fixture'").fetchone()==(1,)
  assert db.execute('SELECT count(*) FROM paper_read_packets').fetchone()[0]<=28
 lane='source' if str(Path(__import__('compertum').__file__)).startswith(str(ROOT/'src')) else 'installed'
 return root,lane

def launch(root,mode,port):
 env={k:v for k,v in os.environ.items() if k.upper() in {'SYSTEMROOT','WINDIR','PYTHONPATH','TEMP','TMP'}}
 env.update(__PYVENV_LAUNCHER__=sys.executable,PYTHONNOUSERSITE='1',PYTHONDONTWRITEBYTECODE='1')
 token=str(uuid4());stdout=RECORDS/f'economic-supervisor-{token}.stdout';stderr=RECORDS/f'economic-supervisor-{token}.stderr'
 with stdout.open('xb') as out,stderr.open('xb') as err:
  p=subprocess.Popen([sys.executable,'-B',str(ROOT/'tests/helpers/paper_economic_supervisor.py'),str(root),mode,str(port)],
   executable=sys._base_executable,env=env,stdout=out,stderr=err,creationflags=0x08000000)
 p._fixture_stdout=stdout;p._fixture_stderr=stderr
 until=time.monotonic()+20
 while time.monotonic()<until:
  if p.poll() is not None:pytest.fail(output(p)[1].decode())
  try:
   value=control(root,'status',timeout=2);w=value.get('watchdog',{});e=w.get('owners',{}).get('execution',{})
   if w.get('mutual',{}).get('verified') and e.get('mutual',{}).get('verified'):return p,value
  except (RuntimeRefused,OSError):pass
  time.sleep(.05)
 p.kill();p.wait(timeout=5);pytest.fail('NATIVE_ECONOMIC_START_TIMEOUT '+output(p)[1].decode())

def collect(root):
 packet=account(root);identity=str(uuid4());prepared=activity(root,'prepare',activity_id=identity,packet_id=packet)
 for operation in ('authorize','start'):activity(root,operation,activity_id=identity,plan_sha256=prepared['plan_sha256'])
 until=time.monotonic()+30
 while time.monotonic()<until:
  value=activity(root,'status',activity_id=identity)
  if value['publication']['state']=='PUBLISHED' and value.get('fixture_economic_phase')=='DONE':break
  time.sleep(.025)
 assert value['publication']['state']=='PUBLISHED'
 return packet,identity,value

def run_case(mode):
 root,lane=admitted_root();receipt=RECORDS/f'review3-native-{lane}-{mode}.json';assert not receipt.exists()
 with socket.socket() as foreign:
  foreign.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1);foreign.bind(('127.0.0.1',0));foreign.listen(1)
  p,initial=launch(root,mode,foreign.getsockname()[1])
  try:
   if mode=='restart':
    previous=json.loads((RECORDS/f'review3-native-{lane}-positive.json').read_text())
    observed=activity(root,'status',activity_id=previous['activity_id'])
    assert observed['state']=='PUBLISHED' and 'fixture_economic_error' in observed and 'fixture_economic' not in observed
    packet=previous['packet_id'];identity=previous['activity_id']
   else:
    packet,identity,observed=collect(root)
    assert observed['fixture_foreign_listener_refused'] is True
    if mode=='positive':
     result=observed['fixture_economic']
     assert result['record_type']=='FixtureEconomicContextDiagnostic' and result['scope']=='ENGINEERING_FIXTURE_ECONOMICS'
     assert result['source_qualified'] and result['event_count']==2
     assert result['fee_liability_status']=='ZERO_FROM_COMPLETE_CONTROLLED_LEDGER'
     assert result['financial_accepted'] is result['transport_authorized'] is False
     assert observed['fixture_single_use_refused'] is True
    else:assert 'fixture_economic_error' in observed and 'fixture_economic' not in observed
   reserve=initial['watchdog']['owners']['execution']['reserve']
   assert reserve['capacity_bytes']==1024**3 and reserve['allocated_bytes']>=1024**3 and reserve['sparse'] is False
   final=stop(root,p);assert final['real_account_calls']==final['actual_broker_actions']==0
   assert final['source_changes']==int(mode=='change')
   if mode=='restart':assert final['requests']==[]
   with receipt.open('x') as out:json.dump(dict(packet_id=packet,activity_id=identity,observed=observed,reserve=reserve,closure=final),out,indent=2)
  finally:
   if p.poll() is None:
    try:control(root,'shutdown');p.wait(timeout=10)
    except (RuntimeRefused,OSError,subprocess.TimeoutExpired):
     if p.poll() is None:p.kill();p.wait(timeout=5)

def test_native_original_economics_and_single_use():run_case('positive')
def test_native_changed_source_refuses_captured_proof():run_case('change')
def test_native_restart_does_not_restore_economic_freshness():run_case('restart')
