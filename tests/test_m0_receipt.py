"""No missing, skipped or blocked gate may become milestone acceptance."""
import importlib.util
from pathlib import Path
import pytest
spec=importlib.util.spec_from_file_location('verify_m0',Path(__file__).parents[1]/'tools/verify_m0.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

@pytest.mark.parametrize('status',['VERIFIED_FAIL','UNVERIFIED','PENDING_EXTERNAL_TIME'])
def test_one_unavailable_gate_blocks_m0(status):
    gates=dict.fromkeys(module.GATES,'VERIFIED_PASS');gates['local_fallback']=status
    result=module.aggregate(gates)
    assert result['status']=='M0_BLOCKED' and result['paper']=='DISABLED' and result['strategy_state']=='NOT_EVALUATED'

def test_missing_or_invented_gate_labels_are_rejected():
    with pytest.raises(ValueError): module.aggregate({})
    with pytest.raises(ValueError): module.aggregate(dict.fromkeys(module.GATES,'SKIPPED_PASS'))

def test_all_verified_is_only_ready_state():
    assert module.aggregate(dict.fromkeys(module.GATES,'VERIFIED_PASS'))['status']=='ENGINEERING_FOUNDATIONS_READY'


def passing_rows():
    return [{'name':'tests.windows.'+name+'.test_example','status':'PASS'} for name in sorted({n for names in module.TEST_GROUPS.values() for n in names})]


def test_managed_watchdog_junit_failure_blocks_resource_claim(tmp_path):
    import xml.etree.ElementTree as ET
    rows=passing_rows();suite=ET.Element('testsuite')
    for row in rows:
        cls,name=row['name'].rsplit('.',1);case=ET.SubElement(suite,'testcase',classname=cls,name=name)
        if 'test_managed_watchdog' in cls: ET.SubElement(case,'failure',message='Synthetic accounting regression')
    path=tmp_path/'result.xml';ET.ElementTree(suite).write(path)
    result=module.suite_gates(module.junit(path),1,len(rows))
    assert result['resources']=='VERIFIED_FAIL' and 'VERIFIED_PASS' not in result.values()

@pytest.mark.parametrize('change',['missing','unknown_skip','nonzero','missing_count'])
def test_failed_or_incomplete_collection_cannot_claim_native_pass(change):
    rows=passing_rows();expected=len(rows);exit_code=0
    if change=='missing': rows.pop()
    elif change=='unknown_skip': rows[0]['status']='SKIP'
    elif change=='nonzero': exit_code=2
    else: expected=None
    assert 'VERIFIED_PASS' not in module.suite_gates({'cases':rows},exit_code,expected).values()


def test_only_explicit_non_windows_refusals_can_be_excluded_on_windows():
    rows=passing_rows()+[{'name':next(iter(module.PLATFORM_REFUSALS)),'status':'SKIP'}]
    assert set(module.suite_gates({'cases':rows},0,len(rows)).values())=={'VERIFIED_PASS'}
