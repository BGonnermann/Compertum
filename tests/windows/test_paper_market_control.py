"""Real authenticated process/RPC lifecycle, full1GiB reserve, invented loopback inputs."""
import json,os,shutil,subprocess,sys,time
from pathlib import Path
from uuid import uuid4
import pytest
from compertum.runtime.supervisor import control
from compertum.runtime.errors import RuntimeRefused
ROOT=Path(__file__).parents[2]


def capture(root,p,timeout=10):
 out,err=p.communicate(timeout=timeout)
 for name,data in [('stdout',out),('stderr',err)]:
  path=root/f'market-process-{p.pid}-{name}.log'
  if path.exists():assert path.read_bytes()==data
  else:path.write_bytes(data)
 return out,err


def launch(root,mode):
 env={k:v for k,v in os.environ.items() if k.upper() in {'SYSTEMROOT','WINDIR','PYTHONPATH','TEMP','TMP'}}
 env.update(__PYVENV_LAUNCHER__=sys.executable,PYTHONNOUSERSITE='1',PYTHONDONTWRITEBYTECODE='1')
 p=subprocess.Popen([sys.executable,'-B',str(ROOT/'tests/helpers/paper_market_supervisor.py'),str(root),mode],executable=sys._base_executable,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=0x08000000)
 end=time.monotonic()+15;observations=[];polls=0
 try:
  while time.monotonic()<end:
   if p.poll() is not None:
    out,err=capture(root,p);pytest.fail(err.decode())
   try:
    state=control(root,'status');health=state.get('watchdog',{});execution=health.get('owners',{}).get('execution',{})
    observed={role:{k:value.get(k) for k in ('status','reason','generation','mutual')} for role,value in (('watchdog',health),('execution',execution))}
    healthy=health.get('status')=='HEALTHY' and health.get('mutual',{}).get('verified') is True and execution.get('status')=='HEALTHY' and execution.get('mutual',{}).get('verified') is True
   except (RuntimeRefused,OSError) as error:
    observed={'error':str(error)};healthy=False
   polls+=1
   if not observations or observations[-1]!=observed:observations.append(observed);observations=observations[-64:]
   if healthy:return p,state
   time.sleep(.05)
  p.kill();out,err=capture(root,p,5);pytest.fail('MARKET_SUPERVISOR_START_TIMEOUT '+json.dumps(observations[-1:])+' '+err.decode())
 finally:
  # Test telemetry belongs to admitted test scratch, outside the live project.
  (root.parent/f'{root.name}-market-process-{p.pid}-startup.json').write_text(json.dumps(dict(polls=polls,observations=observations)))


def stop(root,p):
 control(root,'shutdown');out,err=capture(root,p)
 assert p.returncode==0 and err==b'',err.decode()
 return json.loads(out)


def call(root,operation,**fields):return control(root,'paper_market_read',dict(operation=operation,**fields))
def begin(root,p):
 call(root,'authorize',job_id=p['job_id'],grant_sha256=p['grant_sha256'])
 return call(root,'start',job_id=p['job_id'],grant_sha256=p['grant_sha256'])
def wait(root,job,predicate):
 end=time.monotonic()+20
 while time.monotonic()<end:
  result=call(root,'status',job_id=job)
  if predicate(result):return result
  time.sleep(.05)
 raise AssertionError('Market state not reached: '+json.dumps(result))


def test_actual_market_channels_ack_recovery_both_restarts_and_uncached_composition(tmp_path):
 from compertum.paper_market_inputs import prepare_market_plan
 from compertum.runtime.identity import resolve_project
 plan=prepare_market_plan(project_id=resolve_project(tmp_path).project_id,account_alias='fixture',symbol='MSFT',session_date='2023-11-24',created_at='2023-11-24T14:00:00+00:00').to_payload()
 rows=[dict(t=t,o=100,h=102,l=99,c=100.125,v=20000) for t in plan['daily_labels']]
 (tmp_path/'market-fixture-rows.json').write_text(json.dumps(rows))
 shutil.copyfile(ROOT/'config/default.toml',tmp_path/'config.toml');p,initial=launch(tmp_path,'collect')
 try:
  execution=initial['watchdog']['owners']['execution'];reserve=execution['reserve'];first_generation=execution['generation']
  assert reserve['capacity_bytes']==reserve['unused_bytes']==1024**3 and reserve['allocated_bytes']>=1024**3 and reserve['sparse'] is False
  history=call(tmp_path,'prepare',job_id=str(uuid4()),account_alias='fixture',mode='HISTORY',symbol='MSFT',history_job_id=None)
  with pytest.raises(RuntimeRefused,match='MARKET_GRANT_REQUIRED'):call(tmp_path,'start',job_id=history['job_id'],grant_sha256=history['grant_sha256'])
  begin(tmp_path,history)
  published=wait(tmp_path,history['job_id'],lambda r:r['publication']['state']=='FAILED')
  assert published['state']=='PUBLISHED' and published['publication']['reason']=='FIXTURE_ACK_REPLY_LOST'
  assert published['manifest']==published['publication']['manifest'] and published['evidence']['size_bytes']>32768
  first=stop(tmp_path,p);assert len(first['requests'])==3 and first['lost_ack_receipts']==1
  p,second_initial=launch(tmp_path,'fresh');second_generation=second_initial['watchdog']['owners']['execution']['generation'];assert second_generation>first_generation
  recovered=wait(tmp_path,history['job_id'],lambda r:r['publication']['state']=='PUBLISHED')
  assert recovered['manifest']==published['manifest'] and control(tmp_path,'status')['fixture_requests']==[]
  assert call(tmp_path,'start',job_id=history['job_id'],grant_sha256=history['grant_sha256'])['state']=='PUBLISHED'
  assert control(tmp_path,'status')['fixture_requests']==[]
  fresh=call(tmp_path,'prepare',job_id=str(uuid4()),account_alias='fixture',mode='FRESH',symbol='MSFT',history_job_id=history['job_id'])
  assert fresh['plan']==history['plan'];begin(tmp_path,fresh)
  complete=wait(tmp_path,fresh['job_id'],lambda r:r['state']=='COMPLETE');assert complete['evidence'] is complete['manifest'] is None
  request_id=str(uuid4());command=dict(operation='compose',job_id=fresh['job_id'])
  current=control(tmp_path,'paper_market_read',command,request_id=request_id)['composition']
  assert current['observed_sessions']==252 and current['observed_conditions_met'] and current['quote_valid'] and current['asset_valid']
  assert current['history_job_id']==history['job_id'] and current['status']=='BLOCKED' and current['financial_accepted'] is False
  tmp_path.with_name(tmp_path.name+'-advance-market-age.fixture').write_text('fixture-only advance31seconds')
  stale=control(tmp_path,'paper_market_read',command,request_id=request_id)['composition']
  assert not stale['quote_valid'] and not stale['asset_valid'] and not stale['observed_conditions_met'] and stale['age_basis_at']!=current['age_basis_at']
  with pytest.raises(RuntimeRefused,match='MARKET_CHECKPOINT_BUSY'):control(tmp_path,'shutdown')
  # An acknowledged busy reply must leave every healthy owner channel usable.
  still_complete=call(tmp_path,'status',job_id=fresh['job_id'])
  assert still_complete['state']=='COMPLETE' and still_complete['grant_sha256']==fresh['grant_sha256']
  # The existing fixture deadline closes the processes without a checkpoint.
  # A deliberate forbidden command is fatal and belongs after restart checks.
  out,err=capture(tmp_path,p,60)
  assert p.returncode==0 and err==b'',err.decode()
  second=json.loads(out);assert len(second['requests'])==2 and all('/v2/stocks/bars' not in path for path in second['requests'])
  second['closure']='CONTROLLED_FIXTURE_DEADLINE';second['exit_code']=p.returncode
  p,third_initial=launch(tmp_path,'verify');assert third_initial['watchdog']['owners']['execution']['generation']>second_generation
  interrupted=call(tmp_path,'status',job_id=fresh['job_id']);assert interrupted['state']=='INTERRUPTED' and 'fresh' not in interrupted
  assert interrupted['reason']=='OWNER_RESTARTED' and interrupted['grant_sha256']==fresh['grant_sha256']
  with pytest.raises(RuntimeRefused):call(tmp_path,'compose',job_id=fresh['job_id'])
  with pytest.raises(RuntimeRefused):call(tmp_path,'start',job_id=fresh['job_id'],grant_sha256=fresh['grant_sha256'])
  restored=wait(tmp_path,history['job_id'],lambda r:r['publication']['state']=='PUBLISHED');assert restored['manifest']==published['manifest']
  assert control(tmp_path,'status')['fixture_requests']==[]
  with pytest.raises(RuntimeRefused):control(tmp_path,'paper_market_transfer',dict(operation='chunk',job_id=str(uuid4()),offset=0,sha256='a'*64))
  out,err=capture(tmp_path,p)
  assert p.returncode!=0 and b'COMMAND_DENIED' in err,err.decode()
  third=json.loads(out);assert third['requests']==[]
  third['closure']='INTENTIONAL_COMMAND_DENIED';third['exit_code']=p.returncode
  receipt=dict(first=first,second=second,third=third,reserve=reserve,history=published,current=current,stale=stale,financial_accepted=False)
  raw=json.dumps(receipt);assert 'INVENTED_KEY' not in raw and 'INVENTED_SECRET' not in raw and 'body_utf8' not in raw
  (tmp_path/'native-market-receipt.json').write_text(raw)
 finally:
  if p.poll() is None:p.kill()
  capture(tmp_path,p,5)
