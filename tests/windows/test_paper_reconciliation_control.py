"""Fresh loopback observations in a preserved stationary 1 GiB native fixture."""
import hashlib,json,os,shutil,subprocess,sys,time
from pathlib import Path
from uuid import uuid4
import pytest
from compertum.runtime.errors import RuntimeRefused
from test_paper_activity_control import ROOT,control,output,stop,account,activity

RECORDS=ROOT/'artifacts/m5/ownership-economics-20261016-01'
EVIDENCE=RECORDS/'native-reconciliation'

def launch_reconciliation(root,mode):
    env={k:v for k,v in os.environ.items() if k.upper() in {'SYSTEMROOT','WINDIR','PYTHONPATH','TEMP','TMP'}}
    env.update(__PYVENV_LAUNCHER__=sys.executable,PYTHONNOUSERSITE='1',PYTHONDONTWRITEBYTECODE='1')
    evidence=EVIDENCE;assert evidence.is_dir()
    token=str(uuid4());stdout=evidence/f'activity-supervisor-{token}.stdout';stderr=evidence/f'activity-supervisor-{token}.stderr'
    with stdout.open('xb') as out,stderr.open('xb') as err:
        p=subprocess.Popen([sys.executable,'-B',str(ROOT/'tests/helpers/paper_reconciliation_supervisor.py'),str(root),mode],
            executable=sys._base_executable,env=env,stdout=out,stderr=err,creationflags=0x08000000)
    p._fixture_stdout=stdout;p._fixture_stderr=stderr
    until=time.monotonic()+20
    while time.monotonic()<until:
        if p.poll() is not None:pytest.fail(output(p)[1].decode())
        try:
            status=control(root,'status',timeout=2);w=status.get('watchdog',{});e=w.get('owners',{}).get('execution',{})
            if w.get('mutual',{}).get('verified') and e.get('mutual',{}).get('verified'):return p,status
        except (RuntimeRefused,OSError):pass
        time.sleep(.05)
    p.kill();p.wait(timeout=5);_,err=output(p);pytest.fail('NATIVE_ACTIVITY_START_TIMEOUT '+err.decode())


def admitted_root():
 selected=os.environ.get('COMPERTUM_RECONCILIATION_FIXTURE')
 assert selected,'NATIVE_RECONCILIATION_CAPACITY_NOT_ADMITTED'
 root=Path(selected)
 assert root==ROOT/'.cache/test-runs/native-activity-20261016-02/native-shared'
 admission=json.loads((RECORDS/'reuse-capacity03-result.json').read_text())
 assert admission['status']=='CAPACITY_GATE_PASSED'
 saved=json.loads((RECORDS/'reuse-preservation01-result.json').read_text())
 assert saved['status']=='STOPPED_NATIVE_FIXTURE_PRESERVED'
 assert saved['fixture']==str(root) and root.is_dir()
 for label in ('reuse-capacity03','reuse-preservation01'):
  closed=json.loads((RECORDS/(label+'.closure.json')).read_text())
  assert closed['status']=='PASSED' and closed['remaining_children']==0 and closed['exit_observed'] is True
 from compertum.runtime._windows import WindowsAPI
 from compertum.runtime.identity import resolve_project
 api=WindowsAPI();assert resolve_project(root).project_id==saved['project_id']
 with api.open_file(root/'state/execution-reserve.bin',0x80,1) as handle:
  assert list(api.file_identity(handle))==saved['reserve_identity']
 assert not (root/'state/watchdog/halt.json').exists()
 config=root/'config.toml'
 assert config.read_bytes()==(ROOT/'config/default.toml').read_bytes()
 lane='source' if str(Path(__import__('compertum').__file__)).startswith(str(ROOT/'src')) else 'installed'
 return root,lane

def test_native_original_reconciliation_and_single_use():
 root,lane=admitted_root();receipt=EVIDENCE/f'{lane}-originals.json';assert not receipt.exists()
 p,initial=launch_reconciliation(root,'restart')
 try:
  reserve=initial['watchdog']['owners']['execution']['reserve']
  assert reserve['capacity_bytes']==1024**3 and reserve['allocated_bytes']>=1024**3 and reserve['sparse'] is False
  packet=account(root);aid=str(uuid4());prepared=activity(root,'prepare',activity_id=aid,packet_id=packet)
  for op in ('authorize','start'):activity(root,op,activity_id=aid,plan_sha256=prepared['plan_sha256'])
  until=time.monotonic()+30
  while time.monotonic()<until:
   observed=activity(root,'status',activity_id=aid)
   if observed['publication']['state']=='PUBLISHED':break
   time.sleep(.025)
  assert observed['publication']['state']=='PUBLISHED',observed
  result=observed['fixture_reconciliation']
  assert result['observation_status']=='MATCHING_LOOPBACK_OBSERVATIONS'
  assert result['status']=='BLOCKED' and result['transport_authorized'] is result['financial_accepted'] is False
  assert result['order_count']==result['fill_count']==result['position_count']==0
  assert observed['fixture_single_use_refused'] is True
  final=stop(root,p);assert len(final['requests'])==7 and final['real_account_calls']==0
  with receipt.open('x') as f:json.dump(dict(activity_id=aid,packet_id=packet,observed=observed,reserve=reserve,closure=final),f,indent=2)
 finally:
  if p.poll() is None:p.kill();p.wait(timeout=5)

def test_native_restart_does_not_restore_reconciliation_freshness():
 root,lane=admitted_root();previous=json.loads((EVIDENCE/f'{lane}-originals.json').read_text())
 p,_=launch_reconciliation(root,'restart')
 try:
  observed=activity(root,'status',activity_id=previous['activity_id'])
  assert observed['state']=='PUBLISHED'
  assert 'fixture_reconciliation_error' in observed and 'fixture_reconciliation' not in observed
  final=stop(root,p);assert final['requests']==[]
  with (EVIDENCE/f'{lane}-restart.json').open('x') as f:json.dump(dict(observed=observed,closure=final),f,indent=2)
 finally:
  if p.poll() is None:p.kill();p.wait(timeout=5)
