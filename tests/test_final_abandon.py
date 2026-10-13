"""Pure unknown-exit forfeiture: no fabricated Job receipt or elapsed measurement."""
from copy import deepcopy
import pytest
from test_final_attempts import context,start,close,apply,common,SID,at
from compertum.final_attempts import remaining_slots
from compertum.data.encoding import canonical
from compertum.data.errors import DataError

def abandonment(s):
 a=s[SID]['final_attempts'][-1]['start']['attempt'];n=a['native_execution']
 proof=dict(schema='final-root-exit-v1',process=n['process'],status='VERIFIED_ABSENT',observed_at=at(3600000),observed_creation_filetime=None,wait_result=None)
 return dict(common('ABANDON_FINAL_BATCH',3600001),attempt_id=a['attempt_id'],outcome='EXHAUSTED',charged_ms=120000,budget_basis='UNKNOWN_EXIT_FORFEITS_TOTAL',process_exit=proof,publication=None)

def test_unknown_exit_forfeits_budget_without_inventing_measurement_or_result():
 s=context();apply(s,start(s));r=abandonment(s);apply(s,r,2)
 assert remaining_slots(s[SID])==0 and s[SID]['final_complete']['outcome']=='EXHAUSTED'
 assert 'job_receipt' not in s[SID]['final_attempts'][-1]['close'] and s[SID]['final_complete']['publication'] is None
 assert s[SID]['final_complete']['charged_ms']==120000 and s[SID]['final_complete']['budget_basis']=='UNKNOWN_EXIT_FORFEITS_TOTAL'
 with pytest.raises(DataError):apply(s,start(s,2,4000000),3)

@pytest.mark.parametrize('fault',['live','different_process','wrong_time','future_observation','partial_charge','fake_receipt','publication','reused_equal','exit_no_wait','unverified','boolean_charge','after_close'])
def test_uncertain_or_misbound_exit_cannot_forfeit_journal(fault):
 s=context();apply(s,start(s));r=abandonment(s);p=r['process_exit']
 if fault=='live':p.update(status='LIVE_MATCH',observed_creation_filetime=p['process']['creation_filetime'],wait_result=258)
 elif fault=='different_process':p['process']=deepcopy(p['process']);p['process']['pid']+=1
 elif fault=='wrong_time':p['observed_at']=at(-1)
 elif fault=='future_observation':p['observed_at']=at(4000000)
 elif fault=='partial_charge':r['charged_ms']=1000
 elif fault=='fake_receipt':r['job_receipt']={}
 elif fault=='publication':r['publication']={}
 elif fault=='reused_equal':p.update(status='VERIFIED_PID_REUSED',observed_creation_filetime=p['process']['creation_filetime'],wait_result=258)
 elif fault=='exit_no_wait':p.update(status='VERIFIED_EXIT',observed_creation_filetime=p['process']['creation_filetime'],wait_result=258)
 elif fault=='unverified':p['status']='UNVERIFIED'
 elif fault=='boolean_charge':r['charged_ms']=True
 else:apply(s,close(s),2)
 saved=canonical(s)
 with pytest.raises(DataError):apply(s,r,3)
 assert canonical(s)==saved


@pytest.mark.parametrize('has_native',[False,True])
def test_lost_preparation_invalidates_without_claiming_worker_started(has_native):
 s=context();a=start(s)['attempt']
 if not has_native:a['native_execution']=None
 proof=None if not has_native else dict(schema='final-root-exit-v1',process=deepcopy(a['native_execution']['process']),status='VERIFIED_ABSENT',observed_at=at(3600000),observed_creation_filetime=None,wait_result=None)
 r=dict(common('ABANDON_FINAL_PREPARATION',3600001),attempt=a,dispatch_sha256='a'*64,process_exit=proof,reason='STATUS_UNCERTAIN')
 apply(s,r)
 assert s[SID]['status']=='INVALIDATED' and not s[SID].get('final_attempts') and remaining_slots(s[SID])==0
 assert s[SID]['invalidation']['attempt']==a


def test_preparation_loss_cannot_erase_an_open_attempt():
 s=context();a=start(s)['attempt'];apply(s,start(s));saved=canonical(s)
 r=dict(common('ABANDON_FINAL_PREPARATION',3600001),attempt=a,dispatch_sha256='a'*64,process_exit=None,reason='STATUS_UNCERTAIN')
 with pytest.raises(DataError):apply(s,r,2)
 assert canonical(s)==saved



def test_lost_second_preparation_retains_first_attempt_charge():
 s=context();apply(s,start(s));apply(s,close(s),2);prior=deepcopy(s[SID]['final_attempts']);a=start(s,2,3000)['attempt'];a['native_execution']=None
 r=dict(common('ABANDON_FINAL_PREPARATION',4000),attempt=a,dispatch_sha256='a'*64,process_exit=None,reason='STATUS_UNCERTAIN');apply(s,r,3)
 assert s[SID]['status']=='INVALIDATED' and s[SID]['final_attempts']==prior and remaining_slots(s[SID])==0
