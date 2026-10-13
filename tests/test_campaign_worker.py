from functools import lru_cache
import pytest
from compertum.runtime.campaign_worker import compute,exit_code_for_error
from compertum.simulation.campaign_record import verify_result
from compertum.simulation.runs import runtime_identity
from compertum.modeling.campaign import build_campaign,compute_campaign_unit
from compertum.data.errors import DataError
from helpers.saved_campaign_fixture import campaign_folds

@lru_cache(maxsize=1)
def campaign():return build_campaign(campaign_folds(),identity=runtime_identity())

def test_worker_baseline_exact_primary_binding():
    c=campaign();raw=compute(c.content,c.sha256,0)
    assert verify_result(raw,c.sha256,0)==compute_campaign_unit(c,0,identity=runtime_identity()).content

@pytest.mark.parametrize('case',['hash','unit','boolean','dependency','missing_fit'])
def test_worker_refuses_invalid_identity_before_work(case):
    c=campaign();pin=c.sha256;unit=0;kwargs={}
    if case=='hash':pin='0'*64
    elif case=='unit':unit=63
    elif case=='boolean':unit=True
    elif case=='missing_fit':unit=4
    else:kwargs=dict(dependency_raw=b'{}',dependency_digest='0'*64,dependency_payload_sha256='0'*64)
    with pytest.raises(DataError):compute(c.content,pin,unit,**kwargs)

@pytest.mark.parametrize('error,code',[(OSError('sensitive'),5),(DataError('NO_TRAINING_ROWS'),4),(DataError('FIT_CHECKPOINT_INVALID'),6),(ValueError('sensitive'),6)])
def test_worker_failures_keep_integrity_separate(error,code):
    assert exit_code_for_error(error)==code

def test_main_cleanup_attempts_every_handle_and_preserves_integrity_failure(monkeypatch):
    import compertum.runtime.campaign_worker as module
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
    monkeypatch.setattr(module.sys,'argv',['worker','101','102','1','0'*64,'0','1024','0','0','-','-'])
    assert module.main()==6 and closed==[101,102]

@pytest.mark.parametrize('unit,allowed',[(0,False),(3,True),(4,False),(19,True),(24,True),(40,True),(45,True),(61,True),(62,False),(63,False),(99,False)])
def test_task_schema_only_admits_fixed_fit_paths(unit,allowed):
    from compertum.domain import _campaign_fit_path
    run='00000000-0000-4000-8000-000000000001'
    path=f'artifacts/runs/{run}/baseline/unit-{unit:02}-attempt-1.campaign'
    assert _campaign_fit_path(path,run)==allowed
    assert not _campaign_fit_path(path.replace('attempt-1','attempt-3'),run)
    assert not _campaign_fit_path(path.replace(run,'00000000-0000-4000-8000-000000000002'),run)
