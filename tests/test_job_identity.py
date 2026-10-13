from dataclasses import replace
from uuid import uuid4
import copy,hashlib
import pytest
from compertum.runtime.job_identity import capture_execution_identity,validate_execution_identity,same_process
from compertum.runtime.identity import PeerObservation
from compertum.data.encoding import canonical
from compertum.data.errors import DataError


def fixture():
    observed=PeerObservation(100,123456789,'S-1-5-21-1-2-3-1001','S-1-5-5-100-200')
    task={'task_id':str(uuid4()),'role':'experiment_runner','code_sha256':'a'*64,'lock_sha256':'b'*64}
    return observed,task


def test_native_observation_binds_template_task_and_runtime():
    observation,task=fixture();value=capture_execution_identity(observation,task,'compertum.runtime.campaign_worker')
    validate_execution_identity(value)
    assert value['process']=={'pid':100,'creation_filetime':123456789,'operator_sid':observation.operator_sid}
    assert value['task_sha256']==hashlib.sha256(canonical(task)).hexdigest() and value['task_id']==task['task_id']


@pytest.mark.parametrize('case',['pid_bool','birth_bool','sid','role','entrypoint','digest','unknown','task_id'])
def test_identity_shape_does_not_accept_forged_values(case):
    observation,task=fixture();value=capture_execution_identity(observation,task,'compertum.runtime.campaign_worker')
    if case=='pid_bool':value['process']['pid']=True
    elif case=='birth_bool':value['process']['creation_filetime']=True
    elif case=='sid':value['process']['operator_sid']='caller'
    elif case=='role':value['role']='experiment_auditor'
    elif case=='entrypoint':value['entrypoint']='arbitrary.module'
    elif case=='digest':value['code_sha256']='caller-pass'
    elif case=='task_id':value['task_id']='not-a-task'
    else:value['approved']=True
    with pytest.raises(DataError):validate_execution_identity(value)


def test_auditor_template_cannot_be_relabelled_as_author():
    observation,task=fixture()
    with pytest.raises(DataError):capture_execution_identity(observation,task,'compertum.runtime.audit_worker')
    task['role']='experiment_auditor';value=capture_execution_identity(observation,task,'compertum.runtime.audit_worker');validate_execution_identity(value)


def test_pid_reuse_is_distinguished_by_native_creation_time():
    observation,task=fixture();a=capture_execution_identity(observation,task,'compertum.runtime.campaign_worker');task['role']='experiment_auditor'
    b=capture_execution_identity(observation,task,'compertum.runtime.audit_worker');assert same_process(a,b)
    b=capture_execution_identity(replace(observation,creation_filetime=123456790),task,'compertum.runtime.audit_worker');assert not same_process(a,b)


def test_identity_binding_rejects_plain_worker_json_as_an_observation():
    observation,task=fixture()
    with pytest.raises(DataError):capture_execution_identity({'pid':observation.pid},task,'compertum.runtime.campaign_worker')

@pytest.mark.parametrize('case',['valid','volume_bool','volume_zero','file','image','plan','extra','legacy_with_startup','modern_without_startup'])
def test_compact_startup_evidence_and_legacy_schema_stay_distinct(case):
 observation,task=fixture()
 startup={'image_sha256':'c'*64,'volume_serial':123,'file_id':'d'*32,'plan_sha256':'e'*64}
 value=capture_execution_identity(observation,task,'compertum.runtime.campaign_worker',startup=startup)
 assert len(canonical(value))<1536
 if case=='valid':
  validate_execution_identity(value);assert value['schema']=='native-template-execution-v2';return
 if case=='volume_bool':value['startup']['volume_serial']=True
 elif case=='volume_zero':value['startup']['volume_serial']=0
 elif case=='file':value['startup']['file_id']='d'*64
 elif case=='image':value['startup']['image_sha256']='unknown'
 elif case=='plan':value['startup']['plan_sha256']=False
 elif case=='extra':value['startup']['clean_campaign']=True
 elif case=='legacy_with_startup':value['schema']='native-template-execution-v1'
 else:value.pop('startup')
 with pytest.raises(DataError):validate_execution_identity(value)
