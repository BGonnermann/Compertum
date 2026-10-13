"""Actual public IPC and evaluation process; campaign numerical receipts simulated."""
import json,os,subprocess,time
from pathlib import Path
from uuid import uuid4
import pytest
from compertum.runtime.supervisor import control
from compertum.runtime.errors import RuntimeRefused
from compertum.evaluation_seals import verify_seal_journal
from compertum.runtime.identity import resolve_project


def child(root,operation):
 from test_fixture_processes import fixture_module
 env={k:v for k,v in os.environ.items() if k.upper() in {'SYSTEMROOT','WINDIR','TEMP','TMP','PYTHONPATH','PYTHONDONTWRITEBYTECODE','PYTHONNOUSERSITE'}}
 return fixture_module().python_process(['-B',str(Path('tests/helpers/final_control_holder.py').resolve()),str(root),operation],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)


def launch(root):
 p=child(root,'serve');deadline=time.monotonic()+8
 while p.poll() is None and time.monotonic()<deadline:
  try:
   status=control(root,'status')
   if status.get('final_runs'):return p,status
  except (RuntimeRefused,OSError):pass
  time.sleep(.05)
 if p.poll() is None:p.kill()
 out,err=p.communicate(timeout=5);pytest.fail('CONTROL_START_UNVERIFIED '+err)


def test_public_final_control_idempotence_no_redispatch_and_restart(tmp_path):
 root=tmp_path/'public';root.mkdir();p=child(root,'prepare');out,err=p.communicate(timeout=30);assert p.returncode==0,(out,err)
 expected=json.loads((root/'public-final.json').read_bytes());sid=expected['seal_id'];project=resolve_project(root)
 before=verify_seal_journal(project);measurements=[]
 for restart in range(2):
  p,status=launch(root)
  try:
   assert status['research_state']=='PAUSED' and status['active_final_pid'] is None
   assert status['final_runs']==[dict(seal_id=sid,evaluation_id=expected['evaluation_id'],status='NO_CANDIDATE_QUALIFIES',recovery_error=None)]
   for operation in ('status','recover','pause','stop'):
    request=str(uuid4());payload=dict(seal_id=sid,operation=operation);began=time.monotonic()
    assert control(root,'final',payload,request_id=request)==expected
    assert control(root,'final',payload,request_id=request)==expected
    measurements.append(time.monotonic()-began)
    # Read-only status deliberately creates no durable operator request.
    with pytest.raises(RuntimeRefused,match='RESEARCH_PAUSED' if operation=='status' else 'REQUEST_CONFLICT'):
     control(root,'final',dict(payload,operation='step'),request_id=request)
   with pytest.raises(RuntimeRefused,match='RESEARCH_PAUSED'):control(root,'final',dict(seal_id=sid,operation='step'))
   assert control(root,'stop_research',dict(run_id=expected['evaluation_id']))['confirmed']
   assert verify_seal_journal(project)==before
   control(root,'shutdown');out,err=p.communicate(timeout=5);assert p.returncode==0,(out,err)
  finally:
   if p.poll() is None:p.kill();p.wait(timeout=5)
 assert max(measurements)<5
 (root/'measurements.json').write_text(json.dumps(dict(scope='NATIVE_PUBLIC_CONTROLS_PARTIAL_SUPERVISOR_SIMULATED_CAMPAIGNS',roundtrip_pair_seconds=measurements,native_numerical=False,full_M3=False)))
