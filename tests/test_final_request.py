"""Final transport checks; simulated environment gate, no native admission."""
import hashlib,io,json,os,subprocess,sys
from copy import deepcopy
from uuid import uuid4
import pytest
from test_generated_final import plan
from compertum.data.encoding import canonical
from compertum.data.errors import DataError
from compertum.final_request import build_request,read_request
from compertum.runtime import final_worker
from compertum.review_frame import verify_review,result_binding

def sha(raw):return hashlib.sha256(raw).hexdigest()
def packet():
 p=plan();run=str(uuid4())
 source=canonical(dict(clean_pair=dict(record=dict(project_id=p['project_id'],source=dict(seal_id=p['seal_id']),holdout_manifest_sha256=p['inputs']['input_sha256']))))
 artifact=dict(artifact_id=str(uuid4()),task_id=run,path=f'artifacts/runs/{run}/baseline/inputs.json',size_bytes=len(source),sha256=sha(source))
 raw=build_request(p,plan_sha256=sha(canonical(p)),consumption_sha256='c'*64,number=1,source_artifact=artifact)
 return raw,source

def test_request_reproduces_fixed_attempt_and_source_pins():
 raw,source=packet();v=read_request(raw,expected_sha256=sha(raw))
 assert canonical(v)==raw and len(raw)<=32768 and v['number']==1 and v['source_artifact']['sha256']==sha(source)
 assert v['financial_accepted'] is False

@pytest.mark.parametrize('fault',['hash','bytes','extra','schema','number','boolean','attempt','consumption','source_path','source_task','source_size','source_hash','source_extra','plan_hash','nil_id','recipe','checkpoint','budget','financial'])
def test_rehashed_request_cannot_change_closed_fields(fault):
 raw,source=packet();v=json.loads(raw)
 if fault=='hash':
  with pytest.raises(DataError):read_request(raw,expected_sha256='0'*64)
  return
 if fault=='bytes':raw=b' '+raw
 else:
  if fault=='extra':v['authorize']=True
  elif fault=='schema':v['schema']='anything'
  elif fault=='number':v['number']=3
  elif fault=='boolean':v['number']=True
  elif fault=='attempt':v['attempt_id']=str(uuid4())
  elif fault=='consumption':v['consumption_sha256']='bad'
  elif fault=='source_path':v['source_artifact']['path']+='/other'
  elif fault=='source_task':v['source_artifact']['task_id']=v['plan']['evaluation_id']
  elif fault=='source_size':v['source_artifact']['size_bytes']=20*1024**2+1
  elif fault=='source_hash':v['source_artifact']['sha256']='bad'
  elif fault=='source_extra':v['source_artifact']['trusted']=True
  elif fault=='plan_hash':v['plan_sha256']='0'*64
  elif fault=='nil_id':v['plan']['evaluation_id']='00000000-0000-0000-0000-000000000000'
  elif fault=='recipe':v['plan']['recipe']['seed']+=1
  elif fault=='checkpoint':v['plan']['checkpoint']['position']='AFTER_BATCH'
  elif fault=='budget':v['plan']['budget']['wall_seconds']=121
  else:v['financial_accepted']=1
  if fault in ('nil_id','recipe','checkpoint','budget'):v['plan_sha256']=sha(canonical(v['plan']))
  raw=canonical(v)
 with pytest.raises(DataError):read_request(raw,expected_sha256=sha(raw))

def test_owner_request_import_has_no_numerical_dependencies():
 code="""import sys,importlib.abc
class Deny(importlib.abc.MetaPathFinder):
 def find_spec(self,name,path=None,target=None):
  if name.split('.')[0] in {'numpy','pandas','scipy','sklearn','exchange_calendars'} or name.startswith('compertum.modeling'):raise AssertionError(name)
sys.meta_path.insert(0,Deny())
import compertum.final_request,compertum.final_plan
"""
 result=subprocess.run([sys.executable,'-B','-c',code],capture_output=True,text=True,timeout=15)
 assert result.returncode==0,result.stderr

@pytest.mark.parametrize('fault',[None,'project','seal','holdout'])
def test_worker_checks_environment_and_runtime_before_numerical_call(monkeypatch,fault):
 raw,source=packet();v=json.loads(raw);events=[]
 if fault:
  body=json.loads(source);pair=body['clean_pair']['record']
  if fault=='project':pair['project_id']='9'*64
  elif fault=='seal':pair['source']['seal_id']=str(uuid4())
  else:pair['holdout_manifest_sha256']='9'*64
  source=canonical(body);v['source_artifact'].update(size_bytes=len(source),sha256=sha(source));raw=canonical(v)
 startup=dict(schema='observed-python-startup-v1',pid=os.getpid(),plan_sha256='d'*64)
 expected=dict(schema='expected-clean-campaign-v1',pair_sha256='e'*64,manifest_sha256='f'*64,lane='source',run_id=v['source_artifact']['task_id'])
 observed={**expected,'schema':'observed-clean-environment-v1'}
 monkeypatch.setattr(final_worker,'runtime_identity',lambda:v['plan']['runtime'])
 def environment(data,pin,*,expected):
  assert data==source and pin==sha(source);events.append('environment');return observed
 monkeypatch.setattr(final_worker,'verify_input',environment)
 from compertum.modeling import generated_final
 def compute(data,expected_sha256):
  assert events==['environment'] and data==canonical(v['plan']) and expected_sha256==v['plan_sha256'];events.append('numerical')
  return generated_final.GeneratedFinal(b'{"simulated":true}',sha(b'{"simulated":true}'))
 monkeypatch.setattr(generated_final,'evaluate_generated_final',compute)
 if fault:
  with pytest.raises(DataError):final_worker.compute(raw,sha(raw),source,startup=startup,expected=expected)
  assert events==['environment'];return
 output=final_worker.compute(raw,sha(raw),source,startup=startup,expected=expected)
 binding=result_binding('final',v['plan']['evaluation_id'],v['source_artifact']['task_id'],sha(raw),v['plan']['runtime'],os.getpid(),startup=startup,environment=observed)
 assert verify_review(io.BytesIO(output),binding)['payload_bytes']==18 and events==['environment','numerical']
 events.clear()
 def deny(*args,**kwargs):raise DataError('CLEAN_ENVIRONMENT_UNVERIFIED')
 monkeypatch.setattr(final_worker,'verify_input',deny)
 with pytest.raises(DataError):final_worker.compute(raw,sha(raw),source,startup=startup,expected=expected)
 assert events==[]
