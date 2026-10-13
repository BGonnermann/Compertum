"""Small transport/import-order tests; numerical results and handles are simulated."""
from copy import deepcopy
import io,json,os,sys
from types import SimpleNamespace
import pytest
from test_final_audit_request import audit_packet,saved,environment
from compertum.data.encoding import canonical
from compertum.data.errors import DataError
from compertum.review_evidence import sha
from compertum.review_frame import result_binding,pack_review,verify_review
from compertum.runtime import final_audit_worker as m


@pytest.fixture
def setup(audit_packet,monkeypatch):
 raw,manifest,frame=audit_packet;v=json.loads(raw);calls=[]
 startup=dict(schema='observed-python-startup-v1',pid=os.getpid(),plan_sha256='9'*64)
 real_verify=m.verify_input
 def verified(*args,**kwargs):
  result=real_verify(*args,**kwargs);calls.append('environment');return result
 monkeypatch.setattr(m,'verify_input',verified)
 monkeypatch.setattr(m,'runtime_identity',lambda:v['auditor_runtime'])
 def numerical(plan,payload,**pins):
  assert calls==['environment'];calls.append('numerical')
  assert sha(plan)==pins['plan_sha256']==v['original']['plan_sha256'] and sha(payload)==pins['payload_sha256']==v['original']['payload_sha256']
  body=canonical(dict(status='VERIFIED_PASS',numeric_gates={'confidence':False},financial_accepted=False,full_M3=False));return SimpleNamespace(content=body,sha256=sha(body))
 monkeypatch.setitem(sys.modules,'compertum.audit_generated_final',SimpleNamespace(audit_generated_final=numerical))
 return SimpleNamespace(raw=raw,manifest=manifest,frame=frame,value=v,startup=startup,expected=v['auditor_environment'],calls=calls)


def compute(s):return m.compute(s.raw,sha(s.raw),s.frame,s.manifest,startup=s.startup,expected=s.expected)


def test_worker_checks_environment_and_original_frame_before_equations(setup):
 s=setup;out=compute(s);v=s.value;observed={**s.expected,'schema':'observed-final-auditor-environment-v1'}
 binding=result_binding('final_audit',v['task_id'],v['original']['evaluation_id'],sha(s.raw),v['auditor_runtime'],os.getpid(),startup=s.startup,auditor_environment=observed)
 checked=verify_review(io.BytesIO(out),binding);body=json.loads(out.split(b'\n',1)[1])
 assert s.calls==['environment','numerical'] and checked['header']['schema']=='consumed-final-audit-frame-v1'
 assert body['original_evidence_sha256']==sha(canonical(v['original'])) and body['audit']['numeric_gates']['confidence'] is False
 assert body['audit_sha256']==sha(canonical(body['audit'])) and len(out)<2*1024**2


@pytest.mark.parametrize('fault',['startup_pid','expected_task','manifest','manifest_truncated','manifest_runtime','runtime','frame','frame_truncated','frame_author','frame_payload'])
def test_bad_original_or_auditor_inputs_never_reach_equations(setup,monkeypatch,fault):
 s=setup
 if fault=='startup_pid':s.startup['pid']+=1
 elif fault=='expected_task':s.expected={**s.expected,'task_id':s.value['original']['evaluation_id']}
 elif fault=='manifest':s.manifest=s.manifest[:-1]+b'x'
 elif fault=='manifest_truncated':s.manifest=s.manifest[:-1]
 elif fault=='manifest_runtime':s.value['auditor_runtime']['package_sha256']='9'*64;s.raw=canonical(s.value)
 elif fault=='runtime':monkeypatch.setattr(m,'runtime_identity',lambda:{**s.value['auditor_runtime'],'package_sha256':'9'*64})
 elif fault=='frame':s.frame=s.frame[:-1]+b'x'
 elif fault=='frame_truncated':s.frame=s.frame[:-1]
 elif fault=='frame_author':
  header,payload=s.frame.split(b'\n',1);header=json.loads(header);header['worker_pid']+=1;s.frame=canonical(header)+b'\n'+payload;s.value['original']['frame'].update(size_bytes=len(s.frame),sha256=sha(s.frame));s.raw=canonical(s.value)
 else:s.value['original']['payload_sha256']='9'*64;s.raw=canonical(s.value)
 with pytest.raises(DataError):compute(s)
 assert 'numerical' not in s.calls


@pytest.mark.parametrize('fault',['missing','campaign','other_kind','task','startup','oversized_payload','oversized_frame'])
def test_audit_framing_requires_distinct_complete_binding(setup,fault):
 s=setup;v=s.value;kwargs=dict(startup=s.startup,auditor_environment={**s.expected,'schema':'observed-final-auditor-environment-v1'});kind='final_audit'
 if fault=='missing':kwargs.pop('auditor_environment')
 elif fault=='campaign':kwargs['environment']={}
 elif fault=='other_kind':kind='aggregate'
 elif fault=='task':kwargs['auditor_environment']['task_id']=v['original']['evaluation_id']
 elif fault=='startup':kwargs['startup']=None
 with pytest.raises(DataError):
  binding=result_binding(kind,v['task_id'],v['original']['evaluation_id'],sha(s.raw),v['auditor_runtime'],os.getpid(),**kwargs)
  if fault=='oversized_payload':pack_review(b'x'*(2*1024**2),binding)
  elif fault=='oversized_frame':pack_review(b'x'*(2*1024**2-1),binding)


@pytest.mark.parametrize('args',[
 [],['1','1','1','a'*64,'3','4','2097152'],['1','2','1','a'*64,'1','4','2097152'],['1','2','1','a'*64,'3','2','2097152'],['1','2','0','a'*64,'3','4','2097152'],['1','2','65537','a'*64,'3','4','2097152'],['1','2','1','a'*64,'3','4','16777216'],['-1','2','1','a'*64,'3','4','2097152']])
def test_worker_rejects_bad_handle_contract_before_native_calls(monkeypatch,args):
 monkeypatch.setattr(m,'WindowsAPI',lambda:pytest.fail('Unexpected native call'))
 assert m.main(args,startup=None)==4


def test_environment_failure_prevents_numerical_import(setup,monkeypatch):
 s=setup
 def rejected(*args,**kwargs):raise DataError('ENVIRONMENT_MANIFEST_UNVERIFIED')
 monkeypatch.setattr(m,'verify_input',rejected)
 with pytest.raises(DataError):compute(s)
 assert s.calls==[]
