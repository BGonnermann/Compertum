"""Pure final-attempt replay contracts; supplied native evidence is simulated."""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
from uuid import uuid4,uuid5,UUID
import pytest
from compertum.data.encoding import canonical
from compertum.data.errors import DataError
from compertum.final_attempts import replay_attempt,remaining_slots

SID='00000000-0000-4000-8000-000000000001'
EID='00000000-0000-4000-8000-000000000002'
WID='00000000-0000-4000-8000-000000000003'
RUN='00000000-0000-4000-8000-000000000004'
T=datetime(2026,10,11,tzinfo=timezone.utc)
def at(ms):return (T+timedelta(milliseconds=ms)).isoformat()
def context():
 from compertum.final_recipe import recipe
 plan=dict(recipe=recipe(),evaluation_id=EID,checkpoint_id=str(uuid5(UUID(EID),'synthetic-final-initial-v1')),seal_id=SID,selected=['ridge-h01-a001'],runtime=dict(package_sha256='a'*64,lock_sha256='b'*64))
 pair=dict(source=dict(seal_id=SID,run_id=RUN,manifest_sha256='c'*64),wheel=dict(seal_id=WID))
 row=dict(status='SEALED',final=dict(plan=plan,plan_sha256='d'*64),final_complete=None,freeze=dict(ticket=dict(pair=pair,pair_sha256='e'*64)))
 return {SID:row,WID:dict(status='SEALED')}
def common(op,ms=0):return dict(operation=op,seal_id=SID,created_at=at(ms),owner_instance=str(uuid4()),owner_generation=1)
def start(seals,number=1,ms=0):
 row=seals[SID];plan=row['final']['plan'];prior=row.get('final_attempts',[]);charged=prior[-1]['close']['charged_ms'] if prior else 0
 native=dict(schema='native-template-execution-v3',process=dict(pid=123+number,creation_filetime=100+number,operator_sid='S-1-5-21-1'),task_id=EID,role='experiment_runner',entrypoint='compertum.runtime.campaign_worker',code_sha256='a'*64,lock_sha256='b'*64,task_sha256='f'*64,
  startup=dict(image_sha256='0'*64,volume_serial=1,file_id='1'*32,plan_sha256='2'*64),clean_environment=dict(schema='expected-clean-campaign-v1',pair_sha256='e'*64,manifest_sha256='c'*64,lane='source',run_id=RUN))
 attempt=dict(number=number,attempt_id=str(uuid5(UUID(EID),f'synthetic-final-attempt-{number}')),evaluation_id=EID,checkpoint_id=plan['checkpoint_id'],plan_sha256='d'*64,consumption_sha256='3'*64,task_sha256='f'*64,reservation_id=str(uuid4()),output_path=f'artifacts/runs/{EID}/final/attempt-{number:02}.final',native_execution=native,charged_before_ms=charged,started_at=at(ms),deadline_at=at(ms+120000-charged))
 return dict(common('START_FINAL_BATCH',ms),attempt=attempt)
def close(seals,outcome='INTERRUPTED',ms=1000,charged=1000):
 a=seals[SID]['final_attempts'][-1]['start']['attempt'];n=a['native_execution']
 receipt=dict(pid=n['process']['pid'],exit_code=125,timed_out=False,active_processes=0,assigned_before_resume=True,affinity=15,memory_limit=4*1024**3,peak_job_memory=32000000,observed_child_pids=[],observed_children_exited=True,execution_identity=n)
 publication=None
 if outcome=='COMPLETED':
  receipt['exit_code']=0
  publication=dict(artifact=dict(artifact_id=str(uuid4()),task_id=EID,path=a['output_path'],size_bytes=1000,sha256='4'*64),payload_sha256='5'*64,payload_bytes=500)
 return dict(common('INTERRUPT_FINAL_BATCH' if outcome=='INTERRUPTED' else 'TERMINATE_FINAL_BATCH',ms),attempt_id=a['attempt_id'],outcome=outcome,charged_ms=charged,job_receipt=receipt,publication=publication)
def apply(seals,record,seq=1):replay_attempt(seals,SID,record,seq)

def test_two_attempts_share_budget_and_four_reserved_events():
 s=context();assert remaining_slots(s[SID])==4
 apply(s,start(s));assert remaining_slots(s[SID])==3
 apply(s,close(s),2);assert remaining_slots(s[SID])==2
 second=start(s,2,5000);assert second['attempt']['charged_before_ms']==1000 and second['attempt']['deadline_at']==at(124000)
 apply(s,second,3);assert remaining_slots(s[SID])==1
 apply(s,close(s,'COMPLETED',6000,2000),4)
 assert remaining_slots(s[SID])==0 and s[SID]['final_complete']['outcome']=='COMPLETED'
 assert s[SID]['final_attempts'][0]['close']['outcome']=='INTERRUPTED'
 with pytest.raises(DataError):apply(s,start(s,3,7000),5)

@pytest.mark.parametrize('outcome',['COMPLETED','REJECTED','STOPPED','EXHAUSTED'])
def test_terminal_state_never_reopens(outcome):
 s=context();apply(s,start(s));end=close(s,outcome,120000,120000) if outcome=='EXHAUSTED' else close(s,outcome)
 apply(s,end,2);saved=canonical(s)
 with pytest.raises(DataError):apply(s,end,3)
 with pytest.raises(DataError):apply(s,start(s,2,200000),4)
 assert canonical(s)==saved

@pytest.mark.parametrize('fault',['number','bool_number','attempt_id','evaluation','checkpoint','plan','consumption','task','reservation','path','runtime','lock','native_task','pid','legacy_native','environment','charge','deadline','extra','empty'])
def test_start_refuses_changed_binding_without_mutation(fault):
 s=context();r=start(s);a=r['attempt'];n=a['native_execution']
 if fault=='number':a['number']=2
 elif fault=='bool_number':a['number']=True
 elif fault=='attempt_id':a['attempt_id']=str(uuid4())
 elif fault=='evaluation':a['evaluation_id']=str(uuid4())
 elif fault=='checkpoint':a['checkpoint_id']=str(uuid4())
 elif fault=='plan':a['plan_sha256']='9'*64
 elif fault=='consumption':a['consumption_sha256']='bad'
 elif fault=='task':a['task_sha256']='9'*64
 elif fault=='reservation':a['reservation_id']='00000000-0000-0000-0000-000000000000'
 elif fault=='path':a['output_path']+='x'
 elif fault=='runtime':n['code_sha256']='9'*64
 elif fault=='lock':n['lock_sha256']='9'*64
 elif fault=='native_task':n['task_id']=str(uuid4())
 elif fault=='pid':n['process']['pid']=True
 elif fault=='legacy_native':n.pop('clean_environment');n['schema']='native-template-execution-v2'
 elif fault=='environment':n['clean_environment']['lane']='wheel'
 elif fault=='charge':a['charged_before_ms']=1
 elif fault=='deadline':a['deadline_at']=at(120001)
 elif fault=='extra':a['authorized']=True
 else:s[SID]['final']['plan']['selected']=[]
 saved=canonical(s)
 with pytest.raises(DataError):apply(s,r)
 assert canonical(s)==saved

@pytest.mark.parametrize('fault',['wrong_attempt','running','no_assignment','children','identity','limit','affinity','undercharge','boolean_charge','extra','publication_on_interrupt','missing_publication','wrong_output','oversize','payload_size','integrity_retry','timeout_retry','repeated_interrupt','charge_reset','consumption_reset','process_reuse'])
def test_close_or_retry_refuses_uncertain_evidence(fault):
 s=context();apply(s,start(s));r=close(s)
 if fault=='wrong_attempt':r['attempt_id']=str(uuid4())
 elif fault=='running':r['job_receipt']['active_processes']=1
 elif fault=='no_assignment':r['job_receipt']['assigned_before_resume']=False
 elif fault=='children':r['job_receipt']['observed_children_exited']=False
 elif fault=='identity':r['job_receipt']['execution_identity']=deepcopy(r['job_receipt']['execution_identity']);r['job_receipt']['execution_identity']['process']['creation_filetime']+=1
 elif fault=='limit':r['job_receipt']['memory_limit']*=2
 elif fault=='affinity':r['job_receipt']['affinity']=31
 elif fault=='undercharge':r['charged_ms']=999
 elif fault=='boolean_charge':r['charged_ms']=True
 elif fault=='extra':r['resumable']=True
 elif fault=='publication_on_interrupt':r['publication']={}
 elif fault in ('missing_publication','wrong_output','oversize','payload_size'):
  r=close(s,'COMPLETED')
  if fault=='missing_publication':r['publication']=None
  elif fault=='wrong_output':r['publication']['artifact']['path']+='x'
  elif fault=='oversize':r['publication']['artifact']['size_bytes']=16*1024**2+1
  else:r['publication']['payload_bytes']=1000
 elif fault=='integrity_retry':r['job_receipt']['exit_code']=4
 elif fault=='timeout_retry':r['job_receipt']['timed_out']=True
 else:
  apply(s,r,2);second=start(s,2,5000)
  if fault=='charge_reset':second['attempt']['charged_before_ms']=0;r=second
  elif fault=='consumption_reset':second['attempt']['consumption_sha256']='9'*64;r=second
  elif fault=='process_reuse':second['attempt']['native_execution']['process']=deepcopy(s[SID]['final_attempts'][0]['start']['attempt']['native_execution']['process']);r=second
  else:apply(s,second,3);r=close(s,'INTERRUPTED',6000,2000)
 saved=canonical(s)
 with pytest.raises(DataError):apply(s,r,4)
 assert canonical(s)==saved

@pytest.mark.parametrize('lane',[SID,WID])
@pytest.mark.parametrize('phase',['start','close'])
def test_either_revoked_lane_denies_new_transitions(lane,phase):
 s=context();r=start(s)
 if phase=='close':apply(s,r);r=close(s,'COMPLETED')
 s[lane]['status']='INVALIDATED';saved=canonical(s)
 with pytest.raises(DataError):apply(s,r,2)
 assert canonical(s)==saved

def test_close_cannot_predate_durable_start_commit():
 s=context();r=start(s);r['created_at']=at(1000);apply(s,r)
 saved=canonical(s)
 with pytest.raises(DataError):apply(s,close(s,ms=500,charged=500),2)
 assert canonical(s)==saved

def test_subsecond_remaining_budget_closes_instead_of_waiting_for_impossible_retry():
 s=context();apply(s,start(s));saved=canonical(s)
 with pytest.raises(DataError):apply(s,close(s,ms=119001,charged=119001),2)
 assert canonical(s)==saved
 apply(s,close(s,'EXHAUSTED',ms=119001,charged=119001),2)
 assert remaining_slots(s[SID])==0

def test_conservative_shorter_native_deadline_does_not_increase_total_budget():
 s=context();r=start(s);r['attempt']['deadline_at']=at(119000);apply(s,r)
 assert s[SID]['final_attempts'][0]['start']['attempt']['deadline_at']==at(119000)
