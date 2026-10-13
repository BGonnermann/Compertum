from functools import lru_cache
import hashlib,json
from uuid import uuid4
import pytest
from compertum.runtime.audit_worker import compute,exit_code_for_error
from compertum.runtime.campaign_worker import compute as experiment
from compertum.simulation.campaign_record import verify_result
from compertum.simulation.runs import runtime_identity
from compertum.modeling.campaign import build_campaign
from compertum.data.errors import DataError
from helpers.saved_campaign_fixture import campaign_folds


def sha(raw):return hashlib.sha256(raw).hexdigest()

@lru_cache(maxsize=2)
def prepared(ridge=False):
    c=build_campaign(campaign_folds(ridge),identity=runtime_identity());kwargs={};unit=4 if ridge else 0
    if ridge:
        fit=experiment(c.content,c.sha256,3);pin=sha(verify_result(fit,c.sha256,3));kwargs=dict(fit_raw=fit,fit_sha=sha(fit),fit_payload_sha=pin)
        result=experiment(c.content,c.sha256,unit,dependency_raw=fit,dependency_digest=sha(fit),dependency_payload_sha256=pin)
    else:result=experiment(c.content,c.sha256,unit)
    return c,unit,result,kwargs


@pytest.mark.parametrize('ridge',[False,True])
def test_worker_fresh_source_execution_audit_has_no_native_authority(ridge):
    c,unit,result,kwargs=prepared(ridge);task=str(uuid4());raw=compute(c.content,c.sha256,unit,result,sha(result),audit_id=task,**kwargs);v=json.loads(raw)
    assert v['task_id']==task and v['role']=='experiment_auditor' and v['unit']==unit
    assert v['input_sha256']==c.sha256 and v['result_frame_sha256']==sha(result)
    assert v['audit']['status']=='VERIFIED_PASS' and v['native_authority']=='AWAITING_COORDINATOR_RECEIPT'
    assert v['audit_sha256']==sha(__import__('compertum.data.encoding',fromlist=['canonical']).canonical(v['audit']))
    assert v['financial_accepted'] is False


@pytest.mark.parametrize('case',['input_pin','result_pin','wrong_unit','boolean_unit','fit_unit','task_uuid','unexpected_fit','missing_fit','fit_frame_pin','fit_payload_pin','changed_runtime'])
def test_worker_denies_changed_admission_or_dependency(case,monkeypatch):
    c,unit,result,kwargs=prepared(case in ('missing_fit','fit_frame_pin','fit_payload_pin'));kwargs=dict(kwargs);raw=c.content;pin=c.sha256;rpin=sha(result);task=str(uuid4())
    if case=='input_pin':pin='0'*64
    elif case=='result_pin':rpin='0'*64
    elif case=='wrong_unit':unit=1
    elif case=='boolean_unit':unit=True
    elif case=='fit_unit':unit=3
    elif case=='task_uuid':task='caller-pass-flag'
    elif case=='unexpected_fit':kwargs=dict(fit_raw=b'{}',fit_sha='0'*64,fit_payload_sha='0'*64)
    elif case=='missing_fit':kwargs={}
    elif case=='fit_frame_pin':kwargs['fit_sha']='0'*64
    elif case=='fit_payload_pin':kwargs['fit_payload_sha']='0'*64
    else:
        import compertum.runtime.audit_worker as module
        identity=runtime_identity();identity['package_sha256']='0'*64;monkeypatch.setattr(module,'runtime_identity',lambda:identity)
    with pytest.raises(DataError):compute(raw,pin,unit,result,rpin,audit_id=task,**kwargs)


@pytest.mark.parametrize('error,expected',[(OSError('private text'),5),(DataError('AUDIT_POLICY_MISMATCH'),4),(DataError('CAMPAIGN_DEPENDENCY_INVALID'),6),(ValueError('private text'),6)])
def test_worker_exit_classification_preserves_integrity(error,expected):assert exit_code_for_error(error)==expected


def test_worker_cleanup_attempts_every_inherited_handle(monkeypatch):
    import compertum.runtime.audit_worker as module
    from compertum.runtime.errors import RuntimeRefused
    closed=[]
    class API:
        def handle_flags(self,h):raise RuntimeRefused('INVALID_HANDLE')
    class Handle:
        def __init__(self,api,value):self.value=value
        def close(self):
            closed.append(self.value)
            if self.value==101:raise RuntimeRefused('CLOSE_INVALID_HANDLE')
    monkeypatch.setattr(module,'WindowsAPI',API);monkeypatch.setattr(module,'OwnedHandle',Handle)
    monkeypatch.setattr(module.sys,'argv',['worker','101','102','1','0'*64,'0','1024','103','1','0'*64,'0','0','-','-',str(uuid4())])
    assert module.main()==6 and closed==[101,102,103]


def test_coherent_fit_frame_with_wrong_original_fold_metadata_is_rejected():
    from compertum.data.encoding import canonical
    from compertum.simulation.campaign_record import pack_result
    c,unit,result,kwargs=prepared(True);fit=json.loads(verify_result(kwargs['fit_raw'],c.sha256,3));fit['source_market_sha256']='0'*64;fit_raw=pack_result(canonical(fit),c.sha256,3);fit_pin=sha(canonical(fit))
    body=verify_result(result,c.sha256,unit,kwargs['fit_payload_sha']);result=pack_result(body,c.sha256,unit,fit_pin)
    with pytest.raises(DataError):compute(c.content,c.sha256,unit,result,sha(result),audit_id=str(uuid4()),fit_raw=fit_raw,fit_sha=sha(fit_raw),fit_payload_sha=fit_pin)

@pytest.mark.parametrize('case',['changed_rows_digest','missing_rows_digest','extra_field'])
def test_coherent_parent_fit_requires_exact_fields_and_rows_digest(case):
    from compertum.data.encoding import canonical
    from compertum.simulation.campaign_record import pack_result
    c,unit,result,kwargs=prepared(True);fit=json.loads(verify_result(kwargs['fit_raw'],c.sha256,3))
    if case=='changed_rows_digest':fit['fit_rows_sha256']='0'*64
    elif case=='missing_rows_digest':del fit['fit_rows_sha256']
    else:fit['caller_approved']=True
    body=canonical(fit);fit_raw=pack_result(body,c.sha256,3);fit_pin=sha(body)
    body=verify_result(result,c.sha256,unit,kwargs['fit_payload_sha']);result=pack_result(body,c.sha256,unit,fit_pin)
    with pytest.raises(DataError):compute(c.content,c.sha256,unit,result,sha(result),audit_id=str(uuid4()),fit_raw=fit_raw,fit_sha=sha(fit_raw),fit_payload_sha=fit_pin)
