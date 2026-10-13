"""Clean environment observations are inseparable from native launch and output."""
from dataclasses import asdict
import copy,hashlib,io,json,os
from pathlib import Path
from uuid import uuid4
import pytest
from compertum.data.encoding import canonical
from compertum.data.errors import DataError
from compertum.campaign_contract import UNITS,variant
from compertum.runtime.identity import PeerObservation
from compertum.runtime.job_identity import capture_execution_identity,validate_execution_identity
from compertum.runtime.startup_record import expected_proof,check_report
from compertum.simulation.campaign_record import pack_result,verify_result
from compertum.review_frame import result_binding,pack_review,verify_review


def pins():return dict(schema='expected-clean-campaign-v1',pair_sha256='a'*64,manifest_sha256='b'*64,lane='source',run_id=str(uuid4()))

def native(expected):
 return capture_execution_identity(PeerObservation(123,123456789,'S-1-5-21-1-2-3-1001','S-1-5-5-100-200'),
  {'task_id':expected['run_id'],'role':'experiment_runner','code_sha256':'c'*64,'lock_sha256':'d'*64},'compertum.runtime.campaign_worker',
  startup={'image_sha256':'e'*64,'volume_serial':123,'file_id':'f'*32,'plan_sha256':'1'*64},clean_environment=expected)


def test_native_identity_retains_compact_preregistered_expectations():
 from compertum.runtime.campaign_environment import observed_from_native,check_native
 expected=pins();n=native(expected);validate_execution_identity(n);check_native(n,expected)
 assert n['schema']=='native-template-execution-v3' and n['clean_environment']==expected and len(canonical(n))<=1536
 observed=observed_from_native(n);assert observed=={**expected,'schema':'observed-clean-environment-v1'}
 with pytest.raises(DataError):check_native(n,None)
 with pytest.raises(DataError):check_native(n,{**expected,'manifest_sha256':'0'*64})
 stripped={k:v for k,v in n.items() if k!='clean_environment'};stripped['schema']='native-template-execution-v2'
 with pytest.raises(DataError):check_native(stripped,expected)


@pytest.mark.parametrize('fault',['strip','pair','manifest','lane','run','schema','extra'])
def test_campaign_frame_requires_exact_observation(fault):
 from compertum.runtime.campaign_environment import observed_from_native
 n=native(pins());proof=expected_proof(n);observed=observed_from_native(n)
 body=canonical(dict(schema='synthetic-candidate-fold-v1',financial_accepted=False,full_M2=False,status='SYNTHETIC_ENGINEERING',year=2021,candidate=asdict(variant(UNITS[0].candidate_id))))
 frame=pack_result(body,'d'*64,0,startup=proof,environment=observed)
 assert verify_result(frame,'d'*64,0,expected_startup=proof,expected_environment=observed)==body
 header=json.loads(frame.split(b'\n',1)[0])
 if fault=='strip':header.pop('environment');header['format']='compertum-campaign-unit-v2'
 elif fault=='schema':header['format']='compertum-campaign-unit-v2'
 elif fault=='extra':header['environment']['approved']=True
 elif fault=='run':header['environment']['run_id']=str(uuid4())
 elif fault=='lane':header['environment']['lane']='wheel'
 else:header['environment'][fault+'_sha256']='0'*64
 with pytest.raises(DataError):verify_result(canonical(header)+b'\n'+body,'d'*64,0,expected_startup=proof,expected_environment=observed)


@pytest.mark.parametrize('kind',['scorecard','aggregate'])
def test_review_frame_cannot_drop_clean_observation(kind):
 from compertum.runtime.campaign_environment import observed_from_native
 n=native(pins());proof=expected_proof(n);observed=observed_from_native(n)
 runtime={'package_sha256':'c'*64,'lock_sha256':'d'*64,'python':'3.14.7','distributions':[['a','1']]}
 args=(kind,str(uuid4()),n['task_id'],'e'*64,runtime,123)
 binding=result_binding(*args,startup=proof,environment=observed);raw=pack_review(b'{}',binding)
 assert verify_review(io.BytesIO(raw),binding)['payload_bytes']==2
 stripped=pack_review(b'{}',result_binding(*args,startup=proof))
 with pytest.raises(DataError):verify_review(io.BytesIO(stripped),binding)


def test_audit_report_cannot_drop_clean_observation():
 from compertum.runtime.campaign_environment import observed_from_native
 n=native(pins());proof=expected_proof(n);observed=observed_from_native(n)
 value=dict(schema='synthetic-native-unit-audit-v3',startup=proof,environment=observed)
 check_report(value,{'schema'},n)
 value.pop('environment');value['schema']='synthetic-native-unit-audit-v2'
 with pytest.raises(DataError):check_report(value,{'schema'},n)


def test_launch_expectations_are_read_from_the_verified_startup_plan(monkeypatch,tmp_path):
 from compertum.runtime import startup
 expected=pins();token=str(uuid4());plan=dict(schema='native-python-startup-v2',token=token,cache_prefix=str(tmp_path/('.python-cache-'+token)),executable=str(tmp_path/'python.exe'),base_executable=str(tmp_path/'base.exe'),prefix=str(tmp_path),base_prefix=str(tmp_path),package_root=str(tmp_path/'compertum'),clean_environment=expected)
 raw=canonical(plan);assert startup._read_plan(raw)==plan
 proof=dict(schema='observed-python-startup-v1',pid=os.getpid(),plan_sha256=hashlib.sha256(raw).hexdigest())
 monkeypatch.setenv('COMPERTUM_STARTUP',raw.decode())
 assert startup.expected_clean_environment(proof)==expected
 monkeypatch.setenv('COMPERTUM_STARTUP',canonical({**plan,'clean_environment':{**expected,'lane':'wheel'}}).decode())
 with pytest.raises(DataError):startup.expected_clean_environment(proof)
