import hashlib,io,json
from uuid import uuid4
import pytest
from compertum.review_frame import result_binding,pack_review,verify_review
from compertum.data.encoding import canonical
from compertum.data.errors import DataError


def binding(kind='scorecard'):
    identity={'package_sha256':'a'*64,'lock_sha256':'b'*64,'python':'3.14.7','distributions':[['compertum','0.0.1']]}
    return result_binding(kind,str(uuid4()),str(uuid4()),'c'*64,identity,123)


@pytest.mark.parametrize('kind',['scorecard','aggregate'])
def test_review_frame_preserves_exact_payload_and_authoritative_binding(kind):
    expected=binding(kind);payload=canonical({'result':'fixture','financial_accepted':False})
    raw=pack_review(payload,expected);verified=verify_review(io.BytesIO(raw),expected)
    assert verified['payload_sha256']==hashlib.sha256(payload).hexdigest() and verified['payload_bytes']==len(payload)
    assert verified['sha256']==hashlib.sha256(raw).hexdigest() and verified['size_bytes']==len(raw)
    assert 'payload' not in verified and verified['header']['native_authority']=='AWAITING_COORDINATOR_RECEIPT'


@pytest.mark.parametrize('case',['task','source','request','kind','pid','boolean_pid','financial_integer','runtime','extra_field','digest','length','truncated','trailing','encoding'])
def test_framed_output_cannot_be_relabelled_or_changed(case):
    expected=binding();raw=pack_review(b'{"value":1}',expected);line,payload=raw.split(b'\n',1);header=json.loads(line)
    if case=='task':header['task_id']=str(uuid4())
    elif case=='source':header['source_run_id']=str(uuid4())
    elif case=='request':header['request_sha256']='0'*64
    elif case=='kind':header['kind']='aggregate'
    elif case=='pid':header['worker_pid']+=1
    elif case=='boolean_pid':header['worker_pid']=True
    elif case=='financial_integer':header['financial_accepted']=0
    elif case=='runtime':header['runtime_identity']['package_sha256']='0'*64
    elif case=='extra_field':header['approved']=True
    elif case=='digest':header['payload_sha256']='0'*64
    elif case=='length':header['payload_bytes']+=1
    elif case=='truncated':payload=payload[:-1]
    elif case=='trailing':payload+=b' '
    else:line=b' '+line
    if case!='encoding':line=canonical(header)
    with pytest.raises(DataError):verify_review(io.BytesIO(line+b'\n'+payload),expected)


@pytest.mark.parametrize('case',['kind','same_task','zero_pid','boolean_pid','request','runtime'])
def test_invalid_result_identity_cannot_be_framed(case):
    e=binding();args=[e['kind'],e['task_id'],e['source_run_id'],e['request_sha256'],e['runtime_identity'],e['worker_pid']]
    if case=='kind':args[0]='arbitrary'
    elif case=='same_task':args[2]=args[1]
    elif case=='zero_pid':args[5]=0
    elif case=='boolean_pid':args[5]=True
    elif case=='request':args[3]='bad'
    else:args[4]['lock_sha256']='bad'
    with pytest.raises(DataError):result_binding(*args)


def test_stream_verification_has_bounded_reads_and_exact_eof():
    expected=binding();payload=b'x'*(2*1024**2+17);raw=pack_review(payload,expected)
    class Bounded(io.BytesIO):
        def read(self,n=-1):
            assert 0<n<=1024**2
            return super().read(n)
        def readline(self,n=-1):
            assert 0<n<=65537
            return super().readline(n)
    assert verify_review(Bounded(raw),expected)['size_bytes']==len(raw)
    with pytest.raises(DataError):verify_review(io.BytesIO(raw),expected,maximum=len(raw)-1)


def test_unterminated_header_and_oversize_payload_are_refused():
    expected=binding()
    with pytest.raises(DataError):verify_review(io.BytesIO(b'x'*65537),expected)
    with pytest.raises(DataError):pack_review(b'x'*(16*1024**2),expected)


def test_owner_verification_imports_no_numerical_or_calendar_stack():
    import subprocess,sys
    code='''import sys,importlib.abc
class Deny(importlib.abc.MetaPathFinder):
 def find_spec(self,fullname,path=None,target=None):
  if fullname.split('.')[0] in {'numpy','scipy','sklearn','pandas','exchange_calendars'} or fullname.startswith('compertum.modeling') or fullname=='compertum.data.calendar':
   raise AssertionError('Heavy owner import: '+fullname)
sys.meta_path.insert(0,Deny())
import compertum.review_frame
import compertum.review_bundle
import compertum.aggregate_evidence;import compertum.audit_history;import compertum.review_runs
import compertum.campaign_review
'''
    result=subprocess.run([sys.executable,'-B','-c',code],capture_output=True,text=True,timeout=15)
    assert result.returncode==0,result.stderr

@pytest.mark.parametrize('kind',['scorecard','aggregate'])
@pytest.mark.parametrize('mutation',['strip','pid','plan','schema','extra'])
def test_review_startup_frame_is_bound_and_cannot_downgrade(kind,mutation):
 e=binding(kind);proof={'schema':'observed-python-startup-v1','pid':e['worker_pid'],'plan_sha256':'f'*64}
 expected={**e,'startup':proof};raw=pack_review(b'{"same_math":true}',expected)
 assert verify_review(io.BytesIO(raw),expected)['header']['startup']==proof
 with pytest.raises(DataError):verify_review(io.BytesIO(pack_review(b'{"same_math":true}',e)),expected)
 with pytest.raises(DataError):verify_review(io.BytesIO(raw),e)
 header=json.loads(raw.split(b'\n',1)[0]);body=raw.split(b'\n',1)[1]
 if mutation=='strip':header.pop('startup');header['schema']='synthetic-campaign-review-frame-v1'
 elif mutation=='pid':header['startup']['pid']+=1
 elif mutation=='plan':header['startup']['plan_sha256']='0'*64
 elif mutation=='schema':header['schema']='synthetic-campaign-review-frame-v1'
 else:header['startup']['approved']=True
 with pytest.raises(DataError):verify_review(io.BytesIO(canonical(header)+b'\n'+body),expected)
