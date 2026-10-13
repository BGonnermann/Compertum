"""Separate auditor pins cannot be interpreted as legacy campaign authority."""
from copy import deepcopy
import hashlib,json,os
from pathlib import Path
from uuid import uuid4
import pytest
from test_environment_manifest import environment
from compertum.data.encoding import canonical
from compertum.data.errors import DataError
from compertum.runtime.errors import RuntimeRefused
from compertum.runtime import auditor_environment as m,campaign_environment as campaign,startup
from compertum.runtime.job_identity import validate_execution_identity,capture_execution_identity
from compertum.runtime.identity import PeerObservation
from compertum.runtime.startup_record import expected_proof


def expected():return dict(schema='expected-final-auditor-environment-v1',manifest_sha256='a'*64,environment_id='auditor-source',lane='source',task_id=str(uuid4()))


def native(binding=None):
 binding=binding or expected()
 return dict(schema='native-template-final-auditor-v1',process=dict(pid=123,creation_filetime=456,operator_sid='S-1-5-21-1'),task_id=binding['task_id'],role='experiment_auditor',entrypoint='compertum.runtime.audit_worker',code_sha256='b'*64,lock_sha256='c'*64,task_sha256='d'*64,startup=dict(image_sha256='e'*64,volume_serial=1,file_id='f'*32,plan_sha256='0'*64),auditor_environment=binding)


@pytest.mark.parametrize('lane',['source','wheel'])
def test_manifest_bytes_verified_in_both_lanes_without_admission(environment,lane):
 value=environment(lane);record=m.environment.build_manifest(value);binding=m.expected_from_manifest(record.content,record.sha256,str(uuid4()))
 proof=m.verify_input(record.content,record.sha256,expected=binding)
 assert proof=={**binding,'schema':'observed-final-auditor-environment-v1'}
 assert m.validate_observed(proof)==proof


@pytest.mark.parametrize('fault',['schema','extra','missing','manifest','environment','lane','task','nil','boolean'])
def test_expected_contract_refuses_substitution(fault):
 value=expected()
 if fault=='schema':value['schema']='expected-clean-campaign-v1'
 elif fault=='extra':value['verified']=True
 elif fault=='missing':value.pop('manifest_sha256')
 elif fault=='manifest':value['manifest_sha256']='bad'
 elif fault=='environment':value['environment_id']='../source'
 elif fault=='lane':value['lane']='other'
 elif fault=='task':value['task_id']='bad'
 elif fault=='nil':value['task_id']='00000000-0000-0000-0000-000000000000'
 else:value['task_id']=True
 with pytest.raises(DataError):m.validate_expected(value)


@pytest.mark.parametrize('fault',['manifest','environment','lane'])
def test_manifest_mismatch_precedes_byte_scans(environment,monkeypatch,fault):
 value=environment();record=m.environment.build_manifest(value);binding=m.expected_from_manifest(record.content,record.sha256,str(uuid4()))
 if fault=='manifest':binding['manifest_sha256']='9'*64
 elif fault=='environment':binding['environment_id']='other'
 else:binding['lane']='wheel'
 monkeypatch.setattr(m.environment,'verify_environment',lambda *args,**kwargs:pytest.fail('Unexpected environment scan'))
 with pytest.raises(DataError):m.verify_input(record.content,record.sha256,expected=binding)


def test_native_auditor_cannot_be_downgraded_to_legacy_campaign():
 value=native();validate_execution_identity(value)
 assert expected_proof(value)['pid']==123
 assert m.observed_from_native(value)['task_id']==value['task_id']
 with pytest.raises(DataError):campaign.observed_from_native(value)
 with pytest.raises(DataError):campaign.check_native(value,None)


@pytest.mark.parametrize('fault',['legacy','runner','task','clean','missing_startup','missing_environment','oversize'])
def test_native_contract_cannot_lose_auditor_binding(fault):
 value=native()
 if fault=='legacy':value['schema']='native-template-execution-v2'
 elif fault=='runner':value.update(role='experiment_runner',entrypoint='compertum.runtime.campaign_worker')
 elif fault=='task':value['task_id']=str(uuid4())
 elif fault=='clean':value['clean_environment']={}
 elif fault=='missing_startup':value.pop('startup')
 elif fault=='missing_environment':value.pop('auditor_environment')
 else:value['auditor_environment']['environment_id']='a'*97
 with pytest.raises(DataError):validate_execution_identity(value)


def plan(tmp_path,binding):
 token=str(uuid4())
 return dict(schema='native-python-auditor-startup-v1',token=token,cache_prefix=str(tmp_path/('.python-cache-'+token)),executable=str(tmp_path/'python.exe'),base_executable=str(tmp_path/'base.exe'),prefix=str(tmp_path),base_prefix=str(tmp_path),package_root=str(tmp_path/'compertum'),auditor_environment=binding)


def test_startup_separates_auditor_from_campaign(tmp_path,monkeypatch):
 value=plan(tmp_path,expected());raw=canonical(value);monkeypatch.setenv('COMPERTUM_STARTUP',raw.decode())
 proof=dict(schema='observed-python-startup-v1',pid=os.getpid(),plan_sha256=hashlib.sha256(raw).hexdigest())
 assert startup._read_plan(raw)==value and startup.expected_auditor_environment(proof)==value['auditor_environment']
 with pytest.raises(DataError):startup.expected_clean_environment(proof)
 value.pop('auditor_environment');value['schema']='native-python-startup-v1';raw=canonical(value);monkeypatch.setenv('COMPERTUM_STARTUP',raw.decode());proof['plan_sha256']=hashlib.sha256(raw).hexdigest()
 assert startup.expected_clean_environment(proof) is None
 with pytest.raises(DataError):startup.expected_auditor_environment(proof)


@pytest.mark.parametrize('fault',['both','schema','missing','task','proof'])
def test_startup_rejects_cross_contracts(tmp_path,monkeypatch,fault):
 value=plan(tmp_path,expected())
 if fault=='both':value['clean_environment']={}
 elif fault=='schema':value['schema']='native-python-startup-v2'
 elif fault=='missing':value.pop('auditor_environment')
 elif fault=='task':value['auditor_environment']['task_id']='bad'
 raw=canonical(value);monkeypatch.setenv('COMPERTUM_STARTUP',raw.decode())
 proof=dict(schema='observed-python-startup-v1',pid=os.getpid(),plan_sha256='9'*64 if fault=='proof' else hashlib.sha256(raw).hexdigest())
 with pytest.raises((DataError,RuntimeRefused)):startup.expected_auditor_environment(proof)


def test_capture_requires_matching_role_task_and_one_environment():
 value=native();p=value['process'];observation=PeerObservation(p['pid'],p['creation_filetime'],p['operator_sid'],'S-1-5-5-1-2')
 task=dict(task_id=value['task_id'],role=value['role'],code_sha256=value['code_sha256'],lock_sha256=value['lock_sha256'])
 got=capture_execution_identity(observation,task,value['entrypoint'],startup=value['startup'],auditor_environment=value['auditor_environment'])
 validate_execution_identity(got);assert got['auditor_environment']==value['auditor_environment']
 with pytest.raises(DataError):capture_execution_identity(observation,task,value['entrypoint'],auditor_environment=value['auditor_environment'])
 with pytest.raises(DataError):capture_execution_identity(observation,task,value['entrypoint'],startup=value['startup'],clean_environment={},auditor_environment=value['auditor_environment'])
