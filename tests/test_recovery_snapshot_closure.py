"""Real file/SQLite/owner integration. Reserve measurement is explicitly simulated.

This verifies recovery contracts, not full native reserve or campaign acceptance.
"""
from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4
import json,hashlib
import pytest
from test_persistence import owned
from test_storage import manager
from test_evaluation_seals import ledger,protocol,create,invalidate
from compertum.data.encoding import canonical
from compertum.persistence import open_store
from compertum.runtime.owners import acquire_owner,release_owner
from compertum.recovery import collect_recovery_set,validate_recovery_set,restore_recovery_set
from compertum.consumption import verify_consumption_guard
from compertum.evaluation_seals import verify_seal_journal


def prepared(owned,*,barrier_leases=None):
 project,leases=owned;seals=ledger(owned);storage=seals.test_storage;sid=str(uuid4());p=protocol();create(seals,sid,p.content,p.sha256)
 stores=[storage.store,seals.store,open_store(leases['execution'],'execution')]
 task=str(uuid4());raw=b'bounded synthetic input';writer=storage.open_artifact(storage.reserve_bytes(task,'records',len(raw)),f'artifacts/runs/{task}/baseline/input.bin');writer.write(raw);a=writer.publish();writer.close()
 value=dict(run_id=task,state='COMPLETED',input_artifact=a);body=canonical(value).decode()
 with storage.store.conn:
  storage.store.conn.execute('CREATE TABLE baseline_runs(run_id TEXT PRIMARY KEY,body TEXT)');storage.store.conn.execute('CREATE TABLE baseline_history(run_id,seq,body,sha256)')
  storage.store.conn.execute('INSERT INTO baseline_runs VALUES(?,?)',(task,body));storage.store.conn.execute('INSERT INTO baseline_history VALUES(?,?,?,?)',(task,1,body,hashlib.sha256(body.encode()).hexdigest()))
 extras=barrier_leases if barrier_leases is not None else {r:acquire_owner(project,r) for r in ('watchdog','recovery')}
 # The 1GiB reserve is not allocated by this small contract fixture.
 reserve=SimpleNamespace(lease=leases['execution'],receipt=lambda:dict(capacity_bytes=1024**3,unused_bytes=1024**3,allocated_bytes=1024**3))
 try:
  result=collect_recovery_set(project,stores,storage.reserve_bytes(str(uuid4()),'backups',4*1024**2),recovery_lease=extras['recovery'],watchdog_lease=extras['watchdog'],reserve=reserve)
 finally:
  if barrier_leases is None:
   for lease in extras.values():release_owner(lease)
 return seals,sid,a,result


def test_collected_boundary_and_published_closure_are_validated(owned):
 seals,sid,a,result=prepared(owned);project=owned[0];path=project.root_path/result['manifest_path']
 assert validate_recovery_set(path,project_root=project.root_path)['status']=='VERIFIED'
 m=result['manifest'];assert m['seal_journal']=={k:verify_seal_journal(project)[k] for k in ('sequence','sha256')}
 assert a['artifact_id'] in {x['artifact_id'] for x in m['artifacts']}
 for fault in ('omitted_artifact','wrong_head','wrong_consumption_order'):
  copy=deepcopy(m)
  if fault=='omitted_artifact':copy['artifacts']=[]
  elif fault=='wrong_head':copy['seal_journal']['sha256']='f'*64
  else:copy['consumption_order']=[str(uuid4())]
  altered=project.root_path/(fault+'.json');altered.write_bytes(canonical(copy))
  assert validate_recovery_set(altered,project_root=project.root_path)['status']=='RECOVERY_INVALID'


def invoke(root,action,manifest=None,expected_exit=0):
 import os,sys,subprocess
 from pathlib import Path
 env={k:v for k,v in os.environ.items() if k.upper() in {'SYSTEMROOT','WINDIR','PYTHONPATH','PYTHONDONTWRITEBYTECODE','TEMP','TMP'}}
 args=[sys.executable,'-B',str(Path(__file__).parent/'helpers/recovery_closure_fixture.py'),str(root),action]
 if manifest is not None:args.append(str(manifest))
 result=subprocess.run(args,env=env,capture_output=True,text=True,timeout=30)
 assert result.returncode==expected_exit,result.stderr
 assert result.stderr==''
 return json.loads(result.stdout) if result.stdout else None


def test_restore_recovers_bytes_and_retains_newer_invalidation(tmp_path):
 from compertum.runtime.identity import resolve_project
 result=invoke(tmp_path,'prepare_restore');project=resolve_project(tmp_path);a=result['artifact']
 done=invoke(tmp_path,'restore',result['manifest_path'])
 assert done['status']=='RESTORED' and done['admission']=='HALTED'
 assert hashlib.sha256((project.root_path/a['path']).read_bytes()).hexdigest()==a['sha256']
 assert verify_seal_journal(project)==result['latest']
 import sqlite3
 with sqlite3.connect(project.root_path/'state/generations'/done['generation']/'evaluation.sqlite') as db:
  assert db.execute('SELECT max(sequence) FROM evaluation_seal_events').fetchone()==(result['latest']['sequence'],)


def test_rolled_back_journal_is_detected_against_current_and_backup_mirrors(owned):
 from compertum.recovery import _preserved_seals
 from compertum.evaluation_seals import replay_seal_events
 seals,sid,a,result=prepared(owned);project=owned[0];old=verify_seal_journal(project);invalidate(seals,sid,'STATUS_UNCERTAIN')
 assert _preserved_seals(project,verify_seal_journal(project)) is True
 assert _preserved_seals(project,old) is False


def test_ready_restore_requires_unchanged_seal_head_before_recovery(tmp_path):
 result=invoke(tmp_path,'prepare_crash');invoke(tmp_path,'crash_restore',result['manifest_path'],expected_exit=17)
 assert json.loads((tmp_path/'state/restore-operation.json').read_bytes())['status']=='READY'
 assert invoke(tmp_path,'recover')['status']=='PUBLISHED'
