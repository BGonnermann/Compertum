"""Full independent native owners/1 GiB reserve and real loopback WinHTTP."""
import json,os,shutil,subprocess,sys,time
from pathlib import Path
from uuid import uuid4
import pytest
from compertum.runtime.supervisor import control
from compertum.runtime.errors import RuntimeRefused
ROOT=Path(__file__).parents[2]

def launch(root,mode):
 env={k:v for k,v in os.environ.items() if k.upper() in {'SYSTEMROOT','WINDIR','PYTHONPATH','TEMP','TMP'}}
 env.update(__PYVENV_LAUNCHER__=sys.executable,PYTHONNOUSERSITE='1',PYTHONDONTWRITEBYTECODE='1')
 p=subprocess.Popen([sys.executable,'-B',str(ROOT/'tests/helpers/paper_read_supervisor.py'),str(root),mode],executable=sys._base_executable,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=0x08000000)
 end=time.monotonic()+15
 while time.monotonic()<end:
  if p.poll() is not None:
   out,err=p.communicate();pytest.fail(err.decode())
  try:
   status=control(root,'status');health=status.get('watchdog',{})
   execution=health.get('owners',{}).get('execution',{})
   if (health.get('status')=='HEALTHY' and health.get('mutual',{}).get('verified') is True
       and execution.get('status')=='HEALTHY' and execution.get('mutual',{}).get('verified') is True):
    return p,status
  except (RuntimeRefused,OSError):pass
  time.sleep(.05)
 p.kill();out,err=p.communicate(timeout=5);pytest.fail('SUPERVISOR_START_TIMEOUT '+err.decode())

def stop(root,p):
 control(root,'shutdown');out,err=p.communicate(timeout=10)
 assert p.returncode==0 and err==b'',err.decode()
 return json.loads(out)
def call(root,operation,**kw):return control(root,'paper_read',dict(operation=operation,**kw))

def test_full_native_read_publication_lost_reply_cancel_and_restart(tmp_path):
 shutil.copyfile(ROOT/'config/default.toml',tmp_path/'config.toml');p,initial=launch(tmp_path,'complete')
 try:
  reserve=initial['watchdog']['owners']['execution']['reserve']
  assert reserve['capacity_bytes']==1024**3 and reserve['allocated_bytes']>=1024**3 and reserve['sparse'] is False
  packet=str(uuid4());prepared=call(tmp_path,'prepare',packet_id=packet,account_alias='fixture');sha=prepared['plan_sha256']
  with pytest.raises(RuntimeRefused,match='READ_GRANT_REQUIRED'):call(tmp_path,'start',packet_id=packet,plan_sha256=sha)
  call(tmp_path,'authorize',packet_id=packet,plan_sha256=sha)
  started=call(tmp_path,'start',packet_id=packet,plan_sha256=sha);assert started['consumed']
  end=time.monotonic()+20
  while time.monotonic()<end:
   result=call(tmp_path,'status',packet_id=packet)
   if result['publication']['state'] in {'PUBLISHED','FAILED','NO_EVIDENCE'}:break
   time.sleep(.05)
  assert result['state']=='PUBLISHED' and result['publication']['state']=='PUBLISHED',result
  assert result['responses']==6 and result['attempts']==6 and all(r['http_status']==200 for r in result['requests'])
  assert result['evidence']['size_bytes']>32768
  preflight=result['fixture_preflight']
  assert preflight['transport_provenance']=='LOOPBACK_FIXTURE' and preflight['response_count']==6
  assert preflight['preflight_status']=='BLOCKED' and preflight['transport_authorized'] is False
  assert preflight['actual_flat'] is None and 'NATIVE_PAPER_TRANSPORT_UNVERIFIED' in preflight['deficiencies']
  binding=call(tmp_path,'account_propose',packet_id=packet)
  assert not binding['confirmation_recorded'] and binding['transport_authorized'] is False
  with pytest.raises(RuntimeRefused,match='PAPER_ACCOUNT_NATIVE_ORIGIN_REQUIRED'):
   call(tmp_path,'account_confirm',packet_id=packet,proposal_sha256=binding['proposal_sha256'],acknowledgement=binding['required_acknowledgement'])
  assert call(tmp_path,'account_status',packet_id=packet)['identity_status']=='UNCONFIRMED'
  call(tmp_path,'start',packet_id=packet,plan_sha256=sha);time.sleep(.2)
  assert call(tmp_path,'status',packet_id=packet)['publication']['state']=='PUBLISHED'
  complete=stop(tmp_path,p);assert len(complete['requests'])==6 and complete['lost_start_receipts']==1
  p,restarted=launch(tmp_path,'restart')
  restored=call(tmp_path,'status',packet_id=packet)
  assert restored['state']=='PUBLISHED' and restored['fixture_preflight'] is None
  stale=call(tmp_path,'account_status',packet_id=packet)
  assert stale['identity_status']=='UNCONFIRMED' and stale['live_context']=='UNAVAILABLE'
  with pytest.raises(RuntimeRefused,match='READ_COORDINATOR_RESTARTED'):call(tmp_path,'start',packet_id=packet,plan_sha256=sha)
  again=stop(tmp_path,p);assert again['requests']==[]
  p,initial=launch(tmp_path,'cancel');canceled=str(uuid4());prepared=call(tmp_path,'prepare',packet_id=canceled,account_alias='fixture');csha=prepared['plan_sha256']
  call(tmp_path,'authorize',packet_id=canceled,plan_sha256=csha);call(tmp_path,'start',packet_id=canceled,plan_sha256=csha)
  end=time.monotonic()+5
  while not control(tmp_path,'status')['fixture_requests'] and time.monotonic()<end:time.sleep(.05)
  assert call(tmp_path,'cancel',packet_id=canceled)['state']=='CANCELED'
  canceled_receipt=stop(tmp_path,p);assert len(canceled_receipt['requests'])==1
  (tmp_path/'native-read-receipt.json').write_text(json.dumps(dict(complete=complete,restart=again,cancel=canceled_receipt,reserve=reserve,receipt=result,financial_accepted=False)))
 finally:
  if p.poll() is None:p.kill();p.communicate(timeout=5)
