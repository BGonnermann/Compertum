import importlib
from pathlib import Path
import math
import pytest

def api():
    try: return importlib.import_module('compertum.domain')
    except ImportError: pytest.fail('foundation contracts missing')

def test_unknown_fields_and_schema_rejected():
    d=api()
    with pytest.raises(d.ContractError): d.validate_record('unknown', {})
    with pytest.raises(d.ContractError): d.validate_record('ai_proposal', {'schema_version':1,'task_id':'fixture','summary':'ok','unexpected':True})

def test_nonfinite_and_non_utc_rejected():
    d=api()
    with pytest.raises(d.ContractError): d.ensure_safe({'score':math.inf})
    with pytest.raises(d.ContractError): d.utc_time('2026-10-08T09:25:00-04:00')
    assert d.utc_time('2026-10-08T13:25:00Z').utcoffset().total_seconds()==0

def test_budget_increase_and_financial_kind_rejected():
    d=api()
    with pytest.raises(d.ContractError): d.Budget(cpu_threads=5)
    with pytest.raises(d.ContractError): d.TaskSpec(kind='PAPER_ORDER')
    with pytest.raises(d.ContractError): d.TaskSpec(permissions=('broker',))

def test_artifact_escape_rejected(tmp_path):
    d=api()
    with pytest.raises(d.ContractError): d.within(tmp_path,'../outside')
    assert d.within(tmp_path,'safe/file.json').is_relative_to(tmp_path)
