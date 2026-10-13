import importlib,json,sys
import pytest
from compertum.domain import TaskSpec,Budget
from compertum.runtime.owners import acquire_owner,resolve_project

def api():
    try:return importlib.import_module('compertum.runtime.jobs')
    except ImportError:pytest.fail('native Job Object launcher missing')

def test_assigned_before_resume_and_cpu_affinity(tmp_path):
    m=api();owner=acquire_owner(resolve_project(tmp_path),'coordinator')
    try:
        job=m.launch_bounded(owner,TaskSpec(budget=Budget(ram_bytes=128*1024**2,wall_seconds=5)),['fixture'])
        result=job.wait()
        assert result['assigned_before_resume'] and result['exit_code']==0
        data=json.loads(result['stdout']);assert data['in_job'] and data['cpu_mask'].bit_count()<=4
        assert data['sum']==14 and data['pid']==result['root_pid']
    finally:owner.close()

def test_tree_and_output_capture_limit(tmp_path):
    m=api();owner=acquire_owner(resolve_project(tmp_path),'coordinator')
    try:
        tree=m.launch_bounded(owner,TaskSpec(budget=Budget(ram_bytes=128*1024**2,wall_seconds=1)),['tree']).wait()
        assert tree['timed_out'] and tree['active_processes']==0
        output=m.launch_bounded(owner,TaskSpec(budget=Budget(ram_bytes=128*1024**2,wall_seconds=5,output_bytes=131072)),['grow']).wait()
        assert output['output_limit'] and len(output['stdout'].encode())<=131072 and output['active_processes']==0
    finally:owner.close()

def test_timeout_terminates_process_tree(tmp_path):
    m=api();owner=acquire_owner(resolve_project(tmp_path),'coordinator')
    try:
        job=m.launch_bounded(owner,TaskSpec(budget=Budget(ram_bytes=128*1024**2,wall_seconds=1)),['sleep'])
        result=job.wait();assert result['timed_out'] and result['active_processes']==0
    finally:owner.close()

def test_native_memory_and_breakaway_limits(tmp_path):
    m=api();owner=acquire_owner(resolve_project(tmp_path),'coordinator')
    try:
        for kind in ('memory','breakaway'):
            result=m.launch_bounded(owner,TaskSpec(budget=Budget(ram_bytes=128*1024**2,wall_seconds=5)),[kind]).wait()
            assert result['assigned_before_resume'] and result['active_processes']==0
            if kind=='memory':assert result['exit_code']!=0 and 'MemoryError' in result['stderr']
            else:assert json.loads(result['stdout'])['breakaway_denied']
    finally:owner.close()

def test_failed_assignment_never_resumes_native_child(tmp_path,monkeypatch):
    m=api();owner=acquire_owner(resolve_project(tmp_path),'coordinator');resumed=[];terminated=[];native=m.TerminateProcess
    def terminate(handle,code):
        result=native(handle,code);assert m.w.Wait(handle,3000)==0;terminated.append(True);return result
    monkeypatch.setattr(m,'Assign',lambda *a:False);monkeypatch.setattr(m,'Resume',lambda *a:resumed.append(True));monkeypatch.setattr(m,'TerminateProcess',terminate)
    try:
        with pytest.raises(OSError,match='ASSIGNMENT'):m.launch_bounded(owner,TaskSpec(),['fixture'])
        assert not resumed and terminated==[True]
    finally:owner.close()

def test_nested_fixture_roots_share_one_native_resource_slot(tmp_path):
    m=api();one=tmp_path/'one';two=tmp_path/'two';one.mkdir();two.mkdir()
    with m.ResourceSlot(resolve_project(one)):
        with pytest.raises(ValueError,match='RESOURCE_BUSY'):m.ResourceSlot(resolve_project(two))
