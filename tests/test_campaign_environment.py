"""Clean expectations must be supplied separately from included input bytes."""
import hashlib,json,subprocess,sys
import pytest
from compertum.data.encoding import canonical
from compertum.data.errors import DataError
from compertum import clean_pair
from test_clean_pair import pair_inputs
from test_environment_manifest import environment
from test_campaign_import_boundary import GUARD

def module():
 from compertum.runtime import campaign_environment
 return campaign_environment

def sha(raw):return hashlib.sha256(raw).hexdigest()

def wrapped(pair_inputs,lane='source'):
 args,raw=pair_inputs;pair=clean_pair.build_pair(**args);record=json.loads(pair.content)
 return clean_pair.attach_environment(raw,pair=pair,manifest=args[lane],lane=lane),{'schema':'expected-clean-campaign-v1','pair_sha256':pair.sha256,'manifest_sha256':args[lane].sha256,'lane':lane,'run_id':record[lane]['run_id']}

@pytest.mark.parametrize('lane',['source','wheel'])
def test_expected_pair_is_checked_before_actual_environment_scan(pair_inputs,monkeypatch,lane):
 m=module();raw,binding=wrapped(pair_inputs,lane);calls=[]
 def observe(content,*,expected_sha256):
  v=json.loads(content);calls.append(expected_sha256)
  return {'status':'ENVIRONMENT_BYTES_VERIFIED','manifest_sha256':expected_sha256,'environment_id':v['environment_id'],'lane':v['lane'],'campaign_admitted':False}
 monkeypatch.setattr(m.environment,'verify_environment',observe)
 proof=m.verify_input(raw,sha(raw),expected=binding)
 assert calls==[binding['manifest_sha256']]
 assert proof=={'schema':'observed-clean-environment-v1',**{k:v for k,v in binding.items() if k!='schema'}}

@pytest.mark.parametrize('fault',['missing','pair_sha256','manifest_sha256','lane','run_id','extra','boolean'])
def test_mismatched_expectations_fail_before_file_scans(pair_inputs,monkeypatch,fault):
 m=module();raw,binding=wrapped(pair_inputs)
 def forbidden(*a,**k):raise AssertionError('Unexpected byte scan')
 monkeypatch.setattr(m.environment,'verify_environment',forbidden)
 if fault=='missing':binding=None
 elif fault in ('pair_sha256','manifest_sha256'):binding[fault]='0'*64
 elif fault=='lane':binding['lane']='wheel'
 elif fault=='run_id':binding['run_id']='00000000-0000-4000-8000-000000000001'
 elif fault=='extra':binding['approved']=True
 else:binding['run_id']=True
 with pytest.raises(DataError):m.verify_input(raw,sha(raw),expected=binding)


def test_legacy_input_cannot_satisfy_clean_expectation(pair_inputs):
 m=module();_,binding=wrapped(pair_inputs);_,raw=pair_inputs
 assert m.verify_input(raw,sha(raw),expected=None) is None
 with pytest.raises(DataError):m.verify_input(raw,sha(raw),expected=binding)

@pytest.mark.parametrize('fault',['hash','canonical','bound','not_dict','schema'])
def test_bad_input_refused(pair_inputs,fault):
 m=module();_,raw=pair_inputs;pin=sha(raw)
 if fault=='hash':pin='0'*64
 elif fault=='canonical':raw=json.dumps(json.loads(raw)).encode();pin=sha(raw)
 elif fault=='bound':raw=b' '*(20*1024**2+1);pin=sha(raw)
 elif fault=='not_dict':raw=b'[]';pin=sha(raw)
 else:raw=b'{"schema":"unknown"}';pin=sha(raw)
 with pytest.raises(DataError):m.verify_input(raw,pin,expected=None)

@pytest.mark.parametrize('mode',['campaign','audit','scorecard','aggregate'])
def test_worker_refuses_unregistered_clean_input_before_numerical_import(mode):
 code=GUARD.replace("raise AssertionError('Numerical import before admission: '+fullname)","attempted.append(fullname);raise AssertionError('Numerical import before admission: '+fullname)")+'\nattempted=[]\n'
 code+='''import hashlib,json,os
from compertum.data.encoding import canonical
raw=canonical({'schema':'synthetic-campaign-v2'})
class API:
 def handle_flags(self,h):return 1
 def set_inheritable(self,h,v):pass
class Handle:
 def __init__(self,api,value):self.value=value
 def close(self):pass
'''
 if mode in ('campaign','audit'):
  code+='from compertum.runtime import '+('campaign_worker' if mode=='campaign' else 'audit_worker')+' as m\n'
  code+='m.expected_clean_environment=lambda proof:None\nm.WindowsAPI=API;m.OwnedHandle=Handle;m._read=lambda *a:raw\n'
  args=['worker','101','102',str(len(b'{"schema":"synthetic-campaign-v2"}')),'DIGEST','0','1024']
  args+=['0','0','-','-'] if mode=='campaign' else ['103','1','DIGEST','0','0','-','-','00000000-0000-4000-8000-000000000001']
  code+='sys.argv='+repr(args)+'\nsys.argv=[hashlib.sha256(raw).hexdigest() if a=="DIGEST" else a for a in sys.argv]\nassert m.main()==6\n'
 else:
  code+='''from compertum.runtime import campaign_review_worker as m
m.expected_clean_environment=lambda proof:None
m.WindowsAPI=API;m.OwnedHandle=Handle;m._read=lambda *a:raw
m.read_bundle=lambda *a,**k:({'records':[{'kind':'campaign','artifact':{'size_bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}}]},b'{}')
m.read_declared_bundle=m.read_bundle
runtime_calls=[];original_runtime=m.runtime_identity
def record_runtime():runtime_calls.append(True);return original_runtime()
m.runtime_identity=record_runtime
startup={'schema':'observed-python-startup-v1','pid':os.getpid(),'plan_sha256':'f'*64}
'''
  code+='assert m.main('+repr(mode)+',["101","102",str(len(raw)),hashlib.sha256(raw).hexdigest(),"00000000-0000-4000-8000-000000000001","00000000-0000-4000-8000-000000000002","16777216","103"],startup=startup)==6\n'
 if mode in ('scorecard','aggregate'):code+='assert not runtime_calls,runtime_calls\n'
 code+='assert not attempted,attempted\n'
 result=subprocess.run([sys.executable,'-B','-c',code],capture_output=True,text=True,timeout=15)
 assert result.returncode==0,result.stderr
