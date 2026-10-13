"""Full native supervisor; one controlled transport interruption before receipt commit."""
from pathlib import Path
import hashlib,json,sys
import compertum
from uuid import uuid4
from compertum.runtime.owner_rpc import call_owner
from compertum.runtime.errors import RuntimeRefused
from compertum.config import load_config
import compertum.runtime.supervisor as module
root=Path(sys.argv[1]).resolve();mode=sys.argv[2]
assert mode in {'normal','drop_reply','drop_plan_reply','drop_step_reply','drop_resume_reply'}
s=module.Supervisor(load_config(root/'config.toml',root));lost=[]
barrier_checked=False
execution_status=call_owner(s.execution.remote,'status',{})
execution_job=next(j for j in s.jobs if j.pid==execution_status['startup']['pid'])
execution_plan=json.loads(execution_job._startup_plan_raw)
assert Path(execution_plan['package_root']).resolve()==Path(compertum.__file__).resolve().parent
assert hashlib.sha256(execution_job._startup_plan_raw).hexdigest()==execution_status['startup']['plan_sha256']
execution_origin=dict(package_root=execution_plan['package_root'],startup=execution_status['startup'])
if mode in {'drop_reply','drop_plan_reply','drop_step_reply','drop_resume_reply'}:
 packet=dict(request_id=str(uuid4()),subject_key='a'*64,command={'operation':'status'})
 call_owner(s.execution.remote,'fake_operator',packet)
 task=str(uuid4());grant=s.storage.reserve_bytes(task,'backups',16*1024**2)
 with s.execution._live():
  s.storage.checkpoint(grant,s.execution,str(uuid4()),f'backups/{task}/barrier.sqlite')
  for operation in ('status','supervise','halt','resume','prepare_plan','inspect_plan','approve_plan','start_plan','advance_plan','reconcile_plan','operation_status'):
   packet=dict(request_id=str(uuid4()),subject_key='a'*64,command={'operation':operation})
   try:call_owner(s.execution.remote,'fake_operator',packet)
   except RuntimeRefused as error:assert error.code=='BARRIER_HELD'
   else:raise AssertionError('operator mutation crossed checkpoint barrier')
 barrier_checked=True
if mode in {'drop_reply','drop_plan_reply','drop_step_reply','drop_resume_reply'}:
 class BeforeCoordinatorReceipt(Exception):pass
 dispatch=s._dispatch;serve=module.serve_control_once
 def interrupted(decision,action,payload):
  result=dispatch(decision,action,payload)
  if action=='fake_operator' and payload.get('operation')==({'drop_plan_reply':'approve_plan','drop_step_reply':'advance_plan','drop_resume_reply':'resume'}.get(mode,'supervise')) and not lost:
   lost.append(result);raise BeforeCoordinatorReceipt()
  return result
 def reconnect(*args,**kwargs):
  try:return serve(*args,**kwargs)
  except BeforeCoordinatorReceipt:return None
 s._dispatch=interrupted;module.serve_control_once=reconnect
s.run(maximum_seconds=50)
print(json.dumps(dict(disconnected_after_execution_commit=lost,barrier_checked=barrier_checked,execution_origin=execution_origin)),flush=True)
