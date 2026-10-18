"""Native test owners with optional market time. Actual timeout clocks stay real."""
from datetime import datetime,timedelta,time as daytime,timezone
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo
import hashlib,json,os,sqlite3,subprocess,sys,time
import pytest
from compertum.data.calendar import session_times
from compertum.fake_attempt_guard import verify_attempt_guard
from compertum.persistence import _active_store_path
from compertum.runtime.control import durable_request
from compertum.runtime.errors import RuntimeRefused
from compertum.runtime.identity import resolve_project
from compertum.runtime.supervisor import discover
from compertum.runtime._windows import WindowsAPI

ROOT=Path(__file__).parents[2];O=ROOT/'artifacts/m5/risk-dispatch-20261017-01';NY=ZoneInfo('America/New_York')
WORK_SECONDS=88;CLEANUP_SECONDS=17;FRAMEWORK_SECONDS=15

class Driver:
 def __init__(self,root):
  self.root=root;self.started=time.monotonic();self.end=self.started+WORK_SECONDS;self.cleanup_end=self.end+CLEANUP_SECONDS
 def check(self):assert time.monotonic()<self.end,'NATIVE_REHEARSAL_WORK_DEADLINE'
 def call(self,action,payload=None,*,request_id=None,timeout=5):
  self.check();route=discover(self.root)
  packet=dict(schema_version=1,request_id=request_id or str(uuid4()),target_role='supervisor',target_generation=route.registration.generation,
   action=action,payload=payload or {},actor=dict(kind='operator'))
  return durable_request(route,packet,timeout=min(timeout,5,self.end-time.monotonic()))
 def wait(self,call,condition):
  while True:
   self.check();value=call()
   if condition(value):return value
   time.sleep(.05)
 def market(self,operation,**fields):return self.call('paper_market_read',dict(operation=operation,**fields))
 def activity(self,operation,**fields):return self.call('paper_activity',dict(operation=operation,**fields))
 def warmup(self,packet):
  value=self.wait(lambda:self.call('paper_read',dict(operation='status',packet_id=packet)),lambda v:v['fixture_queue']['ready'])
  assert value['fixture_queue']['fixture_only'] is False and value['fixture_queue']['wait_ns']==0
  return value['fixture_queue']
 def account(self,part):
  pid=part['packet_id'];p=self.call('paper_read',dict(operation='prepare',packet_id=pid,account_alias='fixture'))
  for op in ('authorize','start'):self.call('paper_read',dict(operation=op,packet_id=pid,plan_sha256=p['plan_sha256']))
  self.wait(lambda:self.call('paper_read',dict(operation='status',packet_id=pid)),lambda v:v['publication']['state']=='PUBLISHED')
  proposal=self.call('paper_read',dict(operation='account_propose',packet_id=pid))
  self.call('paper_read',dict(operation='account_confirm',packet_id=pid,proposal_sha256=proposal['proposal_sha256'],acknowledgement=proposal['required_acknowledgement']))
  aid=part['activity_id'];a=self.activity('prepare',activity_id=aid,packet_id=pid)
  for op in ('authorize','start'):self.activity(op,activity_id=aid,plan_sha256=a['plan_sha256'])
  self.wait(lambda:self.activity('status',activity_id=aid),lambda v:v['publication']['state']=='PUBLISHED')
  return self.call('paper_presence',dict(operation='acknowledge',packet_id=pid),request_id=part['presence_id'])
 def fresh(self,part,history):
  p=self.market('prepare',job_id=part['fresh_job_id'],account_alias='fixture',mode='FRESH',symbol='MSFT',history_job_id=history)
  for op in ('authorize','start'):self.market(op,job_id=p['job_id'],grant_sha256=p['grant_sha256'])
  self.wait(lambda:self.market('status',job_id=p['job_id']),lambda v:v['state']=='COMPLETE')
  self.market('publish_lineage',capture_id=part['capture_id'],job_id=p['job_id'],grant_sha256=p['grant_sha256'])
  self.wait(lambda:self.market('lineage_status',capture_id=part['capture_id']),lambda v:v['publication']['state']=='PUBLISHED')
  return p
 def step(self,part,identity):
  result=self.wait(lambda:self.call('paper_presence',dict(operation='inspect',presence_id=part['presence_id']),request_id=identity),
   lambda v:v['fixture_step']['status'] in {'DONE','REFUSED'})
  assert result['fixture_step']['status']=='DONE',result['fixture_step'];return result['fixture_step']

def counts(root):
 project=resolve_project(root);result={}
 for role,table,prefix in [('execution','paper_read_packets','paper_activity:'),('coordinator','paper_read_routes','paper_activity_route:')]:
  with sqlite3.connect(_active_store_path(root,project.project_id,role).as_uri()+'?mode=ro',uri=True,timeout=1) as db:
   db.execute('PRAGMA query_only=ON');result[role+':account']=db.execute('SELECT count(*) FROM '+table).fetchone()[0]
   result[role+':activity']=db.execute('SELECT count(*) FROM state WHERE substr(key,1,?)=?',(len(prefix),prefix)).fetchone()[0]
 return result

def window(plan,*,now=None):
 now=datetime.now(timezone.utc) if now is None else now
 local=now.astimezone(NY);assert local.date().isoformat()==plan['session_date'],'NATIVE_PLAN_DATE_NOT_CURRENT'
 session=session_times(plan['session_date'])
 if plan['phase']=='HISTORY':assert now+timedelta(seconds=120)<datetime.combine(local.date(),daytime(9,25),NY),'NATIVE_HISTORY_WINDOW_UNAVAILABLE'
 elif plan['phase'] in {'BUY','REST'}:
  assert datetime.combine(local.date(),daytime(9,35),NY)<=now and now+timedelta(seconds=120)<datetime.combine(local.date(),daytime(10,5),NY),'NATIVE_BUY_WINDOW_UNAVAILABLE'
 else:assert session.open<=now and now+timedelta(seconds=120)<session.close,'NATIVE_CLOSE_WINDOW_UNAVAILABLE'

def run_phase(phase):
 plan_path=Path(os.environ['COMPERTUM_DISPATCH_PLAN']).resolve();assert plan_path.parent==O
 plan_raw=plan_path.read_bytes();plan=json.loads(plan_raw)
 assert plan['phase']==phase and plan['scope']=='CONTROLLED_LOCAL_REHEARSAL'
 market_clock=None;clock_path=None;clock_sha=None
 if plan.get('market_clock') is not None:
  from helpers.fixture_market_clock import clock_for_plan
  frame=dict(kind='SIMULATED_MARKET_CLOCK',version=1,start_at=plan['market_clock']['start_at'],
   actual_anchor_monotonic_ns=time.monotonic_ns(),maximum_elapsed_seconds=120,
   plan_sha256=hashlib.sha256(plan_raw).hexdigest(),project_id=plan['project_id'])
  market_clock=clock_for_plan(plan,frame,plan_sha256=frame['plan_sha256'])
  clock_path=O/(plan_path.stem+'-clock.json')
  with clock_path.open('x') as out:json.dump(frame,out,indent=2)
  clock_sha=hashlib.sha256(clock_path.read_bytes()).hexdigest()
 window(plan,now=None if market_clock is None else market_clock.now())
 root=Path(os.environ['COMPERTUM_DISPATCH_FIXTURE']).resolve();assert root==ROOT/'.cache/test-runs/native-economic-fresh-20261017-01/native-shared'
 project=resolve_project(root);assert project.project_id==plan['project_id'] and not (root/'state/watchdog/halt.json').exists()
 lane='source' if Path(__import__('compertum').__file__).resolve()==ROOT/'src/compertum/__init__.py' else 'installed';assert lane==plan['lane']
 before=counts(root);assert before==plan['counts_before']
 assert all(before[k]+len(plan['parts'])<=32 for k in before)
 saved=json.loads((O.with_name('native-economics-20261017-01')/'fresh-native-fixture-result.json').read_text());api=WindowsAPI()
 with api.open_file(root/'state/execution-reserve.bin',0x80,1) as handle:assert list(api.file_identity(handle))==saved['reserve_identity']
 prefix=plan.get('receipt_prefix','native-rehearsal')
 assert prefix=='native-rehearsal' if market_clock is None else prefix in {'simclock01','simclock02'}
 if market_clock is not None: assert plan_path.name==f'{prefix}-{lane}-{phase.lower()}-plan.json'
 receipt=O/(prefix+'-'+lane+'-'+phase.lower()+'-receipt.json');assert not receipt.exists()
 token=str(uuid4());stdout=O/(token+'.supervisor.stdout');stderr=O/(token+'.supervisor.stderr')
 env={k:v for k,v in os.environ.items() if k.upper() in {'SYSTEMROOT','WINDIR','PYTHONPATH','TEMP','TMP'}}
 env.update(__PYVENV_LAUNCHER__=sys.executable,PYTHONNOUSERSITE='1',PYTHONDONTWRITEBYTECODE='1')
 driver=Driver(root);process=None;fresh=None
 record=dict(status='FAILED',lane=lane,phase=phase,clock_substituted=market_clock is not None,
  queue_clock_substituted=False,actual_timeout_clocks_substituted=False,clock_frame_sha256=clock_sha)
 try:
  with stdout.open('xb') as out,stderr.open('xb') as err:
   arguments=[sys.executable,'-B',str(ROOT/'tests/helpers/paper_fixture_rehearsal_supervisor.py'),str(root),str(plan_path)]
   if market_clock is not None:arguments.extend([str(clock_path),clock_sha])
   process=subprocess.Popen(arguments,
    executable=sys._base_executable,env=env,stdout=out,stderr=err,creationflags=0x08000000)
  def healthy():
   assert process.poll() is None,'NATIVE_SUPERVISOR_EXITED'
   try:return driver.call('status')
   except (RuntimeRefused,OSError):return {}
  initial=driver.wait(healthy,lambda v:v.get('watchdog',{}).get('mutual',{}).get('verified') is True
   and v.get('watchdog',{}).get('owners',{}).get('execution',{}).get('mutual',{}).get('verified') is True)
  record['generation']=initial['watchdog']['owners']['execution']['generation'];record['queue']=driver.warmup(plan['warmup_packet_id'])
  if phase=='HISTORY':
   h=driver.market('prepare',job_id=plan['history_job_id'],account_alias='fixture',mode='HISTORY',symbol='MSFT',history_job_id=None)
   for op in ('authorize','start'):driver.market(op,job_id=h['job_id'],grant_sha256=h['grant_sha256'])
   record['history']=driver.wait(lambda:driver.market('status',job_id=h['job_id']),lambda v:v['publication']['state']=='PUBLISHED')
   assert (datetime.now(NY) if market_clock is None else market_clock.now(NY)).time()<daytime(9,25)
  else:
   history=json.loads((O/plan['history_receipt']).read_text());assert history['status']=='PASSED';events=[]
   for index,part in enumerate(plan['parts']):
    driver.account(part)
    if index==0:
     if plan.get('prior_intent_id'):
      old=driver.call('paper_intent',dict(operation='inspect',intent_id=plan['prior_intent_id']));assert old['intent_status']=='INVALIDATED'
      events.append(driver.step(part,plan['replay_step_id']))
     if phase!='CANCEL':fresh=driver.fresh(part,history['history']['job_id'])
     terms=plan['terms']
     if phase=='CANCEL':
      previous=json.loads((O/plan['resting_receipt']).read_text());rows=[r for r in previous['closure']['inventory']['orders'] if r['status']=='new']
      assert len(rows)==1;terms=dict(symbol='MSFT',order_id=rows[0]['id'])
     fields=dict(operation='prepare',packet_id=part['packet_id'],presence_id=part['presence_id'],purpose=plan['purpose'],terms=terms)
     if phase!='CANCEL':fields.update(fresh_job_id=part['fresh_job_id'],capture_id=part['capture_id'])
     intent=driver.call('paper_intent',fields,request_id=plan['intent_id'])
     driver.call('paper_intent',dict(operation='confirm',intent_id=intent['intent_id'],intent_sha256=intent['intent_sha256']),request_id=plan['confirmation_id'])
    event=driver.step(part,part['step_id']);events.append(event)
    assert driver.step(part,part['step_id'])==event
    if index==0:
     assert event['reply_lost'] is (phase=='BUY')
     if fresh is not None:driver.market('cancel',job_id=fresh['job_id']);fresh=None
    elif part['operation']=='reconcile':assert event['reconciliation']['unresolved_count']==0
   record['steps']=events
   if phase=='CLOSE':assert events[-1]['closing']['completed_children']==1 and events[-1]['closing']['fixture_flat']
   if phase in {'REST','CLOSE'}:
    record['native_halt']=driver.step(plan['parts'][-1],plan['native_halt_step_id'])
    assert all(record['native_halt'][k] for k in ('native_component_closed','dispatch_refused','reinstall_refused','guard_unchanged'))
    assert driver.step(plan['parts'][-1],plan['native_halt_step_id'])==record['native_halt']
    record['research_stop']=driver.call('stop_research');assert record['research_stop']['confirmed'] is True
   record['stopped_status']=driver.call('status');assert record['stopped_status']['order_admission']=='DISARMED'
  driver.call('shutdown');process.wait(timeout=5);assert process.returncode==0 and stderr.read_bytes()==b''
  record['closure']=json.loads(stdout.read_bytes());closure=record['closure']
  assert closure['real_account_calls']==closure['actual_broker_actions']==0 and not closure['source_errors']
  assert closure['clock_substituted'] is (market_clock is not None)
  assert closure['queue_clock_substituted'] is False
  if market_clock is not None:
   assert closure['actual_timeout_clocks_substituted'] is False and closure['clock_frame_sha256']==clock_sha
   assert hashlib.sha256(clock_path.read_bytes()).hexdigest()==clock_sha
  assert len(closure['writes'])==int(phase!='HISTORY') and closure['reply_lost'] is (phase=='BUY')
  if phase=='CLOSE':assert not closure['inventory']['positions'] and all(r['status'] in {'filled','canceled','expired','rejected'} for r in closure['inventory']['orders'])
  assert verify_attempt_guard(project)['sequence']==plan['attempts_after']
  after=counts(root);assert after=={k:v+len(plan['parts']) for k,v in before.items()}
  with sqlite3.connect(_active_store_path(root,project.project_id,'execution').as_uri()+'?mode=ro',uri=True,timeout=1) as db:
   values={key:json.loads(value) for key,value in db.execute("SELECT key,value FROM state WHERE key IN ('armed','approved_plan','admission')")}
  assert values==dict(armed=False,approved_plan=None,admission='HALTED')
  assert not (root/'state/watchdog/halt.json').exists();record.update(status='PASSED',counts_after=after,actual_broker_disarmed_verified=True)
 finally:
  if process is not None and process.poll() is None:
   driver.end=driver.cleanup_end
   if fresh is not None:
    try:driver.call('paper_market_read',dict(operation='cancel',job_id=fresh['job_id']),timeout=2)
    except (RuntimeRefused,AssertionError,OSError):pass
   try:
    driver.call('shutdown',timeout=3);process.wait(timeout=max(.01,min(5,driver.cleanup_end-time.monotonic()-2)))
   except (RuntimeRefused,AssertionError,OSError,subprocess.TimeoutExpired):
    if process.poll() is None:process.kill();process.wait(timeout=2)
  record['elapsed_seconds']=time.monotonic()-driver.started
  record['supervisor_exit_observed']=process is not None and process.poll() is not None
  with receipt.open('x') as out:json.dump(record,out,indent=2)

def test_native_history_before_cutoff():run_phase('HISTORY')
def test_native_buy_lost_reply_and_owned_reconciliation():run_phase('BUY')
def test_native_resting_order_and_operator_stop():run_phase('REST')
def test_native_restart_and_exact_cancellation():run_phase('CANCEL')
def test_native_one_child_close_flat_and_disarmed():run_phase('CLOSE')
