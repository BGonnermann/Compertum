"""Actual public pipe, independent owners and default1GiBreserve. Invented inputs only."""
import json,os,shutil,sqlite3,subprocess,sys,time
from pathlib import Path
from uuid import uuid4
import pytest
from test_execution_authority import profile
from compertum.runtime.supervisor import control
from compertum.runtime.errors import RuntimeRefused
ROOT=Path(__file__).parents[2]

def provision(root):
 env={k:v for k,v in os.environ.items() if k.upper() in {'SYSTEMROOT','WINDIR','PYTHONPATH','TEMP','TMP'}}
 env.update(__PYVENV_LAUNCHER__=sys.executable,PYTHONNOUSERSITE='1',PYTHONDONTWRITEBYTECODE='1')
 result=subprocess.run([sys.executable,'-B',str(ROOT/'tests/helpers/provision_fake_opening.py'),str(root)],executable=sys._base_executable,env=env,capture_output=True,timeout=15,creationflags=0x08000000)
 assert result.returncode==0,result.stderr.decode()
 import compertum
 receipt=json.loads(result.stdout);assert receipt['status']=='OPENING_PROVISIONED' and receipt['package_origin']==str(Path(compertum.__file__).resolve())
 return receipt


def launch(root,mode):
 env={k:v for k,v in os.environ.items() if k.upper() in {'SYSTEMROOT','WINDIR','PYTHONPATH','TEMP','TMP'}}
 env.update(__PYVENV_LAUNCHER__=sys.executable,PYTHONNOUSERSITE='1',PYTHONDONTWRITEBYTECODE='1')
 p=subprocess.Popen([sys.executable,'-B',str(ROOT/'tests/helpers/fake_operator_supervisor.py'),str(root),mode],executable=sys._base_executable,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=0x08000000)
 end=time.monotonic()+12
 while time.monotonic()<end:
  if p.poll() is not None:
   out,err=p.communicate();pytest.fail(err.decode())
  try:return p,control(root,'status')
  except (RuntimeRefused,OSError):time.sleep(.05)
 p.kill();out,err=p.communicate(timeout=5);pytest.fail('SUPERVISOR_START_TIMEOUT '+err.decode())

def stop(root,p):
 control(root,'shutdown');out,err=p.communicate(timeout=10)
 assert p.returncode==0 and err==b'',err.decode()
 return json.loads(out)

def call(root,operation,request_id=None,**kw):return control(root,'fake_operator',dict(operation=operation,**kw),request_id=request_id)

def test_public_retry_disconnect_restart_and_actual_reserve(tmp_path):
 shutil.copyfile(ROOT/'config/default.toml',tmp_path/'config.toml');p,status=launch(tmp_path,'drop_reply')
 try:
  assert status['research_state']=='PAUSED' and status['watchdog']['status']=='HEALTHY'
  reserve=status['watchdog']['owners']['execution']['reserve']
  assert reserve['capacity_bytes']==1024**3 and reserve['allocated_bytes']>=1024**3 and reserve['sparse'] is False
  sid=str(uuid4());frozen_profile=profile();opened=call(tmp_path,'open_session',session_id=sid,profile=frozen_profile)
  assert opened['financial_accepted'] is False and opened['armed'] is False
  request=str(uuid4());ack=call(tmp_path,'supervise',request_id=request)
  assert ack==call(tmp_path,'supervise',request_id=request)
  assert call(tmp_path,'status')['supervised'] and not call(tmp_path,'status')['armed']
  with pytest.raises(RuntimeRefused,match='REQUEST_CONFLICT'):call(tmp_path,'halt',request_id=request)
  with pytest.raises(RuntimeRefused,match='CONTROL_PAYLOAD_DENIED'):call(tmp_path,'supervise',health=True)
  with sqlite3.connect((tmp_path/'state/research.sqlite').as_uri()+'?mode=ro',uri=True) as db:before=db.execute('SELECT count(*) FROM operator_requests').fetchone()[0]
  call(tmp_path,'status');call(tmp_path,'status')
  with sqlite3.connect((tmp_path/'state/research.sqlite').as_uri()+'?mode=ro',uri=True) as db:assert db.execute('SELECT count(*) FROM operator_requests').fetchone()[0]==before
  with sqlite3.connect((tmp_path/'state/execution.sqlite').as_uri()+'?mode=ro',uri=True) as db:
   assert db.execute('SELECT count(*) FROM fake_operator_requests WHERE request_id=?',(request,)).fetchone()==(1,)
   state=json.loads(db.execute("SELECT value FROM state WHERE key='fake_operator_state'").fetchone()[0]);assert state['ack_mono']<=ack['recorded_monotonic']
  receipt=stop(tmp_path,p);assert receipt['disconnected_after_execution_commit']==[ack] and receipt['barrier_checked']
  p,after=launch(tmp_path,'normal');assert after['supervisor_generation']==status['supervisor_generation']+1
  current=call(tmp_path,'status');assert current['session_id']==sid and not current['armed'] and not current['supervised'] and current['market_at'] is None
  with pytest.raises(RuntimeRefused,match='SESSION_RESTARTED'):call(tmp_path,'supervise')
  with pytest.raises(RuntimeRefused,match='SESSION_RESTARTED'):call(tmp_path,'open_session',session_id=sid,profile=frozen_profile)
  call(tmp_path,'open_session',session_id=str(uuid4()),profile=profile());call(tmp_path,'supervise')
  assert call(tmp_path,'status')['supervised']
  call(tmp_path,'halt');assert not call(tmp_path,'status')['supervised']
  stop(tmp_path,p)
  (tmp_path/'fake-operator-receipt.json').write_text(json.dumps(dict(public_pipe=True,execution_commit_before_disconnect=True,identical_retry_receipt=True,restart_disarmed=True,research_paused_throughout=True,actual_reserve=reserve,financial_accepted=False)),encoding='utf-8')
 finally:
  if p.poll() is None:p.kill();p.communicate(timeout=5)
