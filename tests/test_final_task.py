"""Task permissions and retry ceilings; these tests grant no dispatch authority."""
from datetime import datetime,timezone
import hashlib,json
from uuid import uuid4
import pytest
from test_final_request import packet,sha
from compertum.data.encoding import canonical
from compertum.data.errors import DataError
from compertum.domain import ContractError,TaskSpec
from compertum.runtime.identity_pins import runtime_identity
from compertum.final_task import build_task,validate_task

def request():
 raw,_=packet();v=json.loads(raw);v['plan']['runtime']=runtime_identity();v['plan_sha256']=sha(canonical(v['plan']));raw=canonical(v)
 task=v['plan']['evaluation_id'];a=dict(artifact_id=str(uuid4()),task_id=task,path=f'artifacts/runs/{task}/input/final/attempt-01.json',size_bytes=len(raw),sha256=sha(raw))
 return raw,a

@pytest.mark.parametrize('charged,remaining',[(0,120),(1,119),(1000,119),(34567,85),(119000,1)])
def test_remaining_time_rounds_down_and_permissions_are_exact(tmp_path,charged,remaining):
 raw,a=request();task=build_task(tmp_path,raw,a,charged_ms=charged,now=datetime.now(timezone.utc));v=task.to_payload()
 assert v['budget']['wall_seconds']==remaining and v['clock']['state']=='REGISTERED'
 assert v['permissions']['filesystem_bundle']==[a['path'],json.loads(raw)['source_artifact']['path']]
 assert v['permissions']['tools']==['trusted_fixture'] and not any(v['permissions'][k] for k in ('broker','shell','protected_data','network_destinations'))
 assert v['permissions']['output_directory']==f"artifacts/runs/{v['task_id']}/final"
 assert validate_task(tmp_path,v,raw,a,charged_ms=charged)==v

@pytest.mark.parametrize('charge',[True,-1,119001,120000,120001,1.5])
def test_exhausted_or_invalid_charge_never_gets_new_task(tmp_path,charge):
 raw,a=request()
 with pytest.raises(DataError):build_task(tmp_path,raw,a,charged_ms=charge,now=datetime.now(timezone.utc))

@pytest.mark.parametrize('fault',['time','source','extra_source','role','broker','shell','protected','output','schema','acceptance','code','clock','attempts','gpu','network','manifest'])
def test_changed_task_or_request_cannot_pass_final_binding(tmp_path,fault):
 raw,a=request();task=build_task(tmp_path,raw,a,charged_ms=34000,now=datetime.now(timezone.utc));v=task.to_payload()
 if fault=='time':v['budget']['wall_seconds']=120
 elif fault=='source':v['permissions']['filesystem_bundle'][1]=f'artifacts/runs/{uuid4()}/baseline/inputs.json'
 elif fault=='extra_source':v['permissions']['filesystem_bundle'].append('artifacts/fixture-input')
 elif fault=='role':v['role']='experiment_auditor'
 elif fault in ('broker','shell','protected'):v['permissions'][fault if fault!='protected' else 'protected_data']=True
 elif fault=='output':v['permissions']['output_directory']+='/other'
 elif fault=='schema':v['output_schema_sha256']='9'*64
 elif fault=='acceptance':v['acceptance_checks']=[]
 elif fault=='code':v['code_sha256']='9'*64
 elif fault=='clock':v['clock']['active_elapsed_seconds']=1
 elif fault=='attempts':v['budget']['max_attempts']=3
 elif fault=='gpu':v['budget']['gpu_training']=True
 elif fault=='network':v['permissions']['network_destinations']=['example.com']
 else:a['sha256']='9'*64
 with pytest.raises((DataError,ContractError)):validate_task(tmp_path,v,raw,a,charged_ms=34000)
