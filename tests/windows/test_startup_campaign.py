"""Startup binding through actual committed campaign and owner paths."""
import hashlib,json
from pathlib import Path
from uuid import uuid4
import pytest
from test_native_seals import state,start
from test_native_development_seals import setup
from test_campaign_job import finish_unit
from compertum.runtime.errors import RuntimeRefused
from compertum.runtime.owner_rpc import call_owner


def test_managed_owner_startup_proof_matches_held_launch_and_restart(state):
 first,remote=start(state);a=call_owner(remote,'status',{})['startup']
 assert a['pid']==first.pid and a['plan_sha256']==first.startup_evidence['plan_sha256']
 assert not Path(first.startup_plan['cache_prefix']).exists()
 first.close()
 second,remote2=start(state);b=call_owner(remote2,'status',{})['startup']
 assert b['pid']==second.pid and b['plan_sha256']==second.startup_evidence['plan_sha256']
 assert first.startup_plan['cache_prefix']!=second.startup_plan['cache_prefix']
 assert a['plan_sha256']!=b['plan_sha256']


def test_native_campaign_records_observed_startup_before_resume(state,monkeypatch):
 controller,run,*_=setup(state)
 import compertum.runtime.jobs as jobs
 factory=jobs.JobAPI;captured=[]
 def make_api():
  api=factory();resume=api.ResumeThread
  def invoke(thread):
   attempt=controller.runs._load(run)['attempts'][-1]
   native=attempt['native_execution'];assert native['schema']=='native-template-execution-v2'
   assert native['startup']['plan_sha256'];captured.append(native);return resume(thread)
  api.ResumeThread=invoke;return api
 monkeypatch.setattr(jobs,'JobAPI',make_api)
 try:
  controller.step(run);job=controller.active[2];receipt=job.wait();controller.tick()
  assert receipt['exit_code']==0 and receipt['execution_identity']==captured[0]
  assert receipt['execution_identity']['startup']==job.startup_evidence
  assert len(json.dumps(receipt,separators=(',',':')).encode())<=2048
  assert controller.runs.summary(run)['completed_units']==1
 finally:controller.pause()


def test_cache_created_in_admission_callback_never_resumes_campaign(state,monkeypatch):
 controller,run,*_=setup(state)
 import compertum.runtime.jobs as jobs
 create=jobs.create_suspended;original=controller.runs.begin_campaign;observed=[]
 def capture(api,argv,env,cwd,inherited=()):
  info=create(api,argv,env,cwd,inherited);observed.append((api,api.open_process(info.pid),json.loads(env['COMPERTUM_STARTUP'])))
  return info
 def inject(*args,**kwargs):
  result=original(*args,**kwargs);Path(observed[0][2]['cache_prefix']).mkdir();return result
 monkeypatch.setattr(jobs,'create_suspended',capture);monkeypatch.setattr(controller.runs,'begin_campaign',inject)
 try:
  with pytest.raises(RuntimeRefused,match='STARTUP_CACHE_UNVERIFIED'):controller.step(run)
  assert all(api.WaitForSingleObject(process.get(),0)==0 for api,process,_ in observed)
  result=controller.runs.summary(run);assert result['state']=='BLOCKED' and result['completed_units']==0
  assert result['attempts'][-1]['reason']=='LAUNCH_FAILED'
 finally:
  controller.pause()
  for api,process,_ in observed:process.close()


def test_consistently_substituted_child_plan_cannot_complete_campaign(state,monkeypatch):
 controller,run,*_=setup(state)
 import compertum.runtime.jobs as jobs
 create=jobs.create_suspended
 def substitute(api,argv,env,cwd,inherited=()):
  env=dict(env);plan=json.loads(env['COMPERTUM_STARTUP']);plan['token']=str(uuid4())
  plan['cache_prefix']=str(Path(plan['cache_prefix']).parent/('.python-cache-'+plan['token']))
  env['COMPERTUM_STARTUP']=json.dumps(plan,sort_keys=True,separators=(',',':'),ensure_ascii=False)
  env['PYTHONPYCACHEPREFIX']=plan['cache_prefix']
  return create(api,argv,env,cwd,inherited)
 monkeypatch.setattr(jobs,'create_suspended',substitute)
 try:
  controller.step(run);receipt=controller.active[2].wait();assert receipt['exit_code']==0
  controller.tick();result=controller.runs.summary(run)
  assert result['state']=='BLOCKED' and result['completed_units']==0
  assert result['attempts'][-1]['reason']=='UNIT_INTEGRITY_FAILURE'
 finally:controller.pause()


def test_binding_release_failure_does_not_leave_campaign_child_live(state,monkeypatch):
 controller,run,*_=setup(state)
 import compertum.runtime.jobs as jobs
 create=jobs.create_suspended;close=jobs.StartupBinding.close;children=[];raised=[]
 def capture(api,*args,**kwargs):
  info=create(api,*args,**kwargs);children.append((api,api.open_process(info.pid)));return info
 def fail(binding):
  close(binding)
  if children and not raised:raised.append(True);raise RuntimeRefused('INJECTED_STARTUP_RELEASE_FAILURE')
 monkeypatch.setattr(jobs,'create_suspended',capture);monkeypatch.setattr(jobs.StartupBinding,'close',fail)
 try:
  with pytest.raises(RuntimeRefused,match='INJECTED_STARTUP_RELEASE_FAILURE'):controller.step(run)
  assert all(api.WaitForSingleObject(process.get(),0)==0 for api,process in children)
 finally:
  controller.pause()
  for api,process in children:
   if api.WaitForSingleObject(process.get(),0)!=0:api.TerminateProcess(process.get(),125);api.WaitForSingleObject(process.get(),3000)
   process.close()

@pytest.mark.parametrize('case',['substituted_plan','release_failure'])
def test_managed_owner_startup_failure_leaves_no_live_child(state,monkeypatch,case):
 import compertum.runtime.managed as managed
 factory=managed.JobAPI;children=[];raised=[];close=managed.StartupBinding.close;apply=managed.StartupBinding.apply
 def make_api():
  api=factory();create=api.CreateProcessW
  def observed(*args):
   result=create(*args)
   if result:children.append((api,api.open_process(args[-1]._obj.pid)))
   return result
  api.CreateProcessW=observed;return api
 monkeypatch.setattr(managed,'JobAPI',make_api)
 if case=='substituted_plan':
  def changed(binding,env):
   apply(binding,env);plan=json.loads(env['COMPERTUM_STARTUP']);plan['token']=str(uuid4())
   plan['cache_prefix']=str(Path(plan['cache_prefix']).parent/('.python-cache-'+plan['token']))
   env['COMPERTUM_STARTUP']=json.dumps(plan,sort_keys=True,separators=(',',':'),ensure_ascii=False);env['PYTHONPYCACHEPREFIX']=plan['cache_prefix']
  monkeypatch.setattr(managed.StartupBinding,'apply',changed)
 else:
  def fail(binding):
   close(binding)
   if children and not raised:raised.append(True);raise RuntimeRefused('INJECTED_STARTUP_RELEASE_FAILURE')
  monkeypatch.setattr(managed.StartupBinding,'close',fail)
 try:
  with pytest.raises(RuntimeRefused,match='STARTUP_PROOF_UNVERIFIED' if case=='substituted_plan' else 'INJECTED_STARTUP_RELEASE_FAILURE'):start(state)
  assert children and all(api.WaitForSingleObject(p.get(),0)==0 for api,p in children)
 finally:
  for api,p in children:
   if api.WaitForSingleObject(p.get(),0)!=0:api.TerminateProcess(p.get(),125);api.WaitForSingleObject(p.get(),3000)
   p.close()
