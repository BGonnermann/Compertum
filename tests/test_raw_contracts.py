import pytest
from compertum.domain import TaskSpec,validate_record,ContractError

def test_raw_budget_and_artifact_paths_are_rejected():
    task=TaskSpec().record();task['budget']['cpu_threads']=99
    with pytest.raises(ContractError):validate_record('task',task)
    payload={'schema_version':1,'artifact_id':'fixture','task_id':'fixture','path':'../protected','sha256':'0'*64,'bytes':1,'at':'2026-10-08T00:00:00Z'}
    with pytest.raises(ContractError,match='PATH'):validate_record('artifact_manifest',payload)

def test_record_at_cannot_use_non_utc_offset():
    with pytest.raises(ContractError,match='UTC'):validate_record('ai_proposal',{'schema_version':1,'task_id':'fixture','summary':'fixture','at':'2026-10-08T00:00:00-04:00'})
