"""Actual separately limited owners, full allocated reserve, and peer loss."""
from pathlib import Path
import json,shutil,sqlite3,time
from dataclasses import asdict
import pytest
from compertum.config import load_config
from compertum.runtime.identity import resolve_project
from compertum.runtime.owners import acquire_owner,release_owner
from compertum.runtime.managed import launch_owner
from compertum.runtime.owner_rpc import call_owner
from compertum.runtime.bootstrap import validate_worker_commands
from compertum.runtime.errors import RuntimeRefused
from compertum.storage import StorageManager,reserve_runtime_paths


def test_actual_reserve_mutual_health_expiry_restart_and_peer_exit(tmp_path):
 shutil.copyfile(Path(__file__).parents[2]/'config/default.toml',tmp_path/'config.toml')
 project=resolve_project(tmp_path);supervisor=acquire_owner(project,'supervisor');coordinator=acquire_owner(project,'coordinator');jobs=[]
 def launch(role):
  job,remote=launch_owner(supervisor,role);jobs.append(job);return job,remote
 def state():
  with sqlite3.connect(tmp_path/'state/execution.sqlite') as db:return {k:json.loads(v) for k,v in db.execute('SELECT key,value FROM state')}
 def relay(e,w):
  es=call_owner(e,'status',{});ws=call_owner(w,'status',{})
  call_owner(e,'owner_heartbeat',ws['heartbeat']);call_owner(w,'owner_heartbeat',es['heartbeat'])
  return call_owner(e,'status',{}),call_owner(w,'status',{})
 try:
  manager=StorageManager(coordinator,load_config(tmp_path/'config.toml',tmp_path));reserve_runtime_paths(manager)
  ej,e=launch('execution');wj,w=launch('watchdog')
  first=call_owner(e,'status',{});reserve=first['reserve']
  assert reserve['capacity_bytes']==reserve['unused_bytes']==1024**3 and reserve['allocated_bytes']>=1024**3 and reserve['sparse'] is False
  assert not first['mutual']['verified'] and state()['armed'] is False and state()['admission']=='HALTED'
  assert ej.pid!=wj.pid and ej.api.limits(ej.job).job_memory==512*1024**2 and wj.api.limits(wj.job).job_memory==128*1024**2
  assert first['heartbeat']['identity']==asdict(e.descriptor.registration.identity)
  for role in ('execution','watchdog'):
   with pytest.raises(RuntimeRefused,match='WORKER_COMMAND_DENIED'):validate_worker_commands(role,frozenset({'owner_heartbeat'}))
  from compertum.runtime.supervisor import ACTIONS
  assert 'owner_heartbeat' not in ACTIONS
  es,ws=relay(e,w);assert es['mutual']['verified'] and ws['mutual']['verified']
  began=time.monotonic();expired=None
  # Keep supervisor/status alive but deliberately cease mutual relay.
  while time.monotonic()-began<17:
   es=call_owner(e,'status',{});ws=call_owner(w,'status',{})
   if es['mutual']['reason'] and ws['mutual']['reason']:expired=time.monotonic()-began;break
   time.sleep(.2)
  assert expired is not None and expired<16 and es['mutual']['reason']==ws['mutual']['reason']=='PEER_HEARTBEAT_STALE'
  assert state()['armed'] is False and state()['approved_plan'] is None and state()['execution_health_halt']=='PEER_HEARTBEAT_STALE'
  es,ws=relay(e,w);assert not es['mutual']['verified'] and not ws['mutual']['verified']
  # Restart is still disarmed and cannot silently use the previous peer generation.
  ej.close();wj.close();jobs.clear();ej,e=launch('execution');wj,w=launch('watchdog')
  assert state()['armed'] is False and call_owner(e,'status',{})['mutual']['verified'] is False
  # Retained watchdog incident is deliberately preserved, so restart health is blocked.
  es,ws=relay(e,w);assert not es['mutual']['verified'] and ws['reason']=='RETAINED_WATCHDOG_HALT'
  ej.close();jobs.remove(ej)
  began=time.monotonic()
  while time.monotonic()-began<2:
   ws=call_owner(w,'status',{})
   if ws['mutual']['reason']:break
   time.sleep(.05)
  assert ws['mutual']['reason'] in {'PEER_UNAVAILABLE','PEER_UNHEALTHY'}
  (tmp_path/'native-health-receipt.json').write_text(json.dumps(dict(reserve=reserve,expiry_seconds=expired,execution_pid=ej.pid,watchdog_pid=wj.pid,distinct_processes=True,restart_disarmed=True,retained_halt=True,worker_heartbeat_denied=True,financial_accepted=False)),encoding='utf-8')
 finally:
  for job in reversed(jobs):job.close()
  release_owner(coordinator);release_owner(supervisor)


@pytest.mark.parametrize('victim',['execution','watchdog'])
def test_full_supervisor_relay_and_actual_peer_exit(tmp_path,victim):
 import os,subprocess,sys
 shutil.copyfile(Path(__file__).parents[2]/'config/default.toml',tmp_path/'config.toml')
 env={k:v for k,v in os.environ.items() if k.upper() in {'SYSTEMROOT','WINDIR','PYTHONPATH','PYTHONDONTWRITEBYTECODE','TEMP','TMP'}}
 helper=Path(__file__).parents[1]/'helpers/mutual_supervisor_fixture.py'
 result=subprocess.run([sys.executable,'-B',str(helper),str(tmp_path),victim],env=env,capture_output=True,text=True,timeout=30)
 assert result.returncode==0,result.stderr
 assert result.stderr==''
 receipt=json.loads(result.stdout);assert receipt['status']=='PASS' and receipt['victim']==victim and receipt['supervisor_relay_verified']
 (tmp_path/'supervisor-health-receipt.json').write_text(json.dumps(receipt),encoding='utf-8')
