"""Native Job Object gates; bounded trusted fixture children only."""
from datetime import datetime, timedelta, timezone
import importlib
import json
import os
from pathlib import Path
import time
import pytest
_contract_spec=importlib.util.spec_from_file_location('contracts_fixture',Path(__file__).parents[1]/'test_contracts.py')
_contracts=importlib.util.module_from_spec(_contract_spec)
_contract_spec.loader.exec_module(_contracts)
task_payload=_contracts.task
from compertum.domain import TaskSpec
from compertum.runtime.identity import resolve_project
from compertum.runtime.owners import acquire_owner,release_owner
from compertum.runtime.errors import RuntimeRefused

pytestmark=pytest.mark.skipif(os.name!='nt',reason='NATIVE_WINDOWS_UNAVAILABLE')

@pytest.fixture
def owner(tmp_path):
    lease=acquire_owner(resolve_project(tmp_path),'coordinator')
    try: yield lease,tmp_path
    finally: release_owner(lease)


def spec(root,wall=2,ram=128*1024*1024):
    value=task_payload(); value['budget'].update(wall_seconds=wall,ram_bytes=ram,cpu_threads=2,output_bytes=4096)
    now=datetime.now(timezone.utc); value['created_at']=now.isoformat(); value['deadline_at']=(now+timedelta(seconds=wall)).isoformat()
    return TaskSpec(value,project_root=root)


def jobs(): return importlib.import_module('compertum.runtime.jobs')


def output_path(root,name):
    return root/task_payload()['permissions']['output_directory']/name


def test_job_assigned_before_fixture_runs_and_limits_are_observed(owner):
    lease,root=owner; output=output_path(root,'result.json')
    with jobs().launch_bounded(lease,spec(root),['fixture','echo',str(output)]) as job:
        receipt=job.wait()
        assert receipt['exit_code']==0 and receipt['active_processes']==0
        assert receipt['assigned_before_resume'] and receipt['affinity'].bit_count()<=2
        assert receipt['memory_limit']==128*1024*1024
    assert json.loads(output.read_text())['result']=='OFFLINE_FIXTURE_OK'


def test_failed_assignment_never_resumes_child(owner,monkeypatch):
    lease,root=owner; output=output_path(root,'never.json'); module=jobs()
    original=module.JobAPI.assign
    def fail(self,*args): raise RuntimeRefused('ASSIGNMENT_UNVERIFIED')
    monkeypatch.setattr(module.JobAPI,'assign',fail)
    with pytest.raises(RuntimeRefused,match='ASSIGNMENT_UNVERIFIED'):
        module.launch_bounded(lease,spec(root),['fixture','echo',str(output)])
    assert not output.exists()


def test_timeout_terminates_observed_entire_process_tree(owner):
    lease,root=owner; output=output_path(root,'tree.json')
    with jobs().launch_bounded(lease,spec(root,wall=1),['fixture','tree',str(output)]) as job:
        deadline=time.monotonic()+.8
        while not output.exists() and time.monotonic()<deadline: time.sleep(.01)
        assert output.exists()
        child=json.loads(output.read_text())['child_pid']
        handle=job.api.open_process(child)
        try:
            receipt=job.wait()
            assert receipt['timed_out'] and receipt['active_processes']==0
            assert job.api.WaitForSingleObject(handle.get(),0)==0
        finally: handle.close()


def test_native_job_denies_breakaway(owner):
    lease,root=owner; output=output_path(root,'breakaway.json')
    with jobs().launch_bounded(lease,spec(root),['fixture','breakaway',str(output)]) as job:
        receipt=job.wait()
    assert receipt['exit_code']==0
    assert json.loads(output.read_text())['breakaway_winerror']==5


def test_native_committed_memory_limit_rejects_allocation(owner):
    lease,root=owner; output=output_path(root,'memory.json')
    with jobs().launch_bounded(lease,spec(root,ram=64*1024*1024),['fixture','memory',str(output)]) as job:
        receipt=job.wait()
    assert receipt['exit_code']==0 and receipt['peak_job_memory']<=64*1024*1024
    assert json.loads(output.read_text())['allocation']=='DENIED'


def test_unknown_command_and_path_escape_never_launch(owner):
    lease,root=owner
    for command in (['powershell','anything'],['fixture','echo',str(root.parent/'outside.json')]):
        with pytest.raises(RuntimeRefused): jobs().launch_bounded(lease,spec(root),command)


def test_second_heavy_job_is_refused_while_first_is_live(owner):
    lease,root=owner
    with jobs().launch_bounded(lease,spec(root),['fixture','sleep',str(output_path(root,'first.json'))]):
        with pytest.raises(RuntimeRefused,match='JOB_SLOT_BUSY'):
            with jobs().launch_bounded(lease,spec(root),['fixture','echo',str(output_path(root,'second.json'))]): pass
    assert not output_path(root,'second.json').exists()


def test_low_available_ram_refuses_launch_before_any_child(owner,monkeypatch):
    lease,root=owner; module=jobs()
    monkeypatch.setattr(module,'available_physical_memory',lambda:5*1024**3,raising=False)
    with pytest.raises(RuntimeRefused,match='AVAILABLE_RAM_FLOOR'):
        with module.launch_bounded(lease,spec(root),['fixture','echo',str(output_path(root,'low.json'))]): pass
    assert not output_path(root,'low.json').exists()


def test_deadline_kills_tree_without_supervisor_polling(owner):
    """A blocked control/health caller cannot extend the worker wall clock."""
    lease,root=owner; output=output_path(root,'unpolled-tree.json')
    with jobs().launch_bounded(lease,spec(root,wall=1),['fixture','tree',str(output)]) as job:
        until=time.monotonic()+.8
        while not output.exists() and time.monotonic()<until: time.sleep(.01)
        assert output.exists()
        child=job.api.open_process(json.loads(output.read_text())['child_pid'])
        try:
            # Deliberately make no JobHandle.wait or controller.tick call.
            assert job.api.WaitForSingleObject(job.process.get(),2500)==0
            assert job.api.WaitForSingleObject(child.get(),500)==0
            assert job.api.active(job.job)==0
            receipt=job.wait()
            assert receipt['timed_out'] and receipt['exit_code']==124
        finally: child.close()


def test_failed_deadline_monitor_start_never_leaves_suspended_child(owner,monkeypatch):
    lease,root=owner;module=jobs();observed=[]
    create=module.create_suspended;start=module.threading.Thread.start
    def capture(api,*args,**kwargs):
        info=create(api,*args,**kwargs)
        observed.append((api,api.open_process(info.pid)))
        return info
    def fail(thread):
        if thread.name=='compertum-job-deadline':raise RuntimeError('MONITOR_START_REFUSED')
        return start(thread)
    monkeypatch.setattr(module,'create_suspended',capture)
    monkeypatch.setattr(module.threading.Thread,'start',fail)
    output=output_path(root,'monitor-failed.json')
    try:
        with pytest.raises(RuntimeError):module.launch_bounded(lease,spec(root),['fixture','echo',str(output)])
        assert observed and not output.exists()
        assert all(api.WaitForSingleObject(handle.get(),500)==0 for api,handle in observed)
    finally:
        for api,handle in observed:
            if api.WaitForSingleObject(handle.get(),0)!=0:
                api.TerminateProcess(handle.get(),125);api.WaitForSingleObject(handle.get(),3000)
            handle.close()


@pytest.mark.parametrize("charged", [7078, 7200, 86400])
def test_elapsed_daily_usage_does_not_block_or_reset_bounded_job(owner, charged):
    from compertum.persistence import open_store
    lease, root = owner
    store = open_store(lease, "coordinator")
    day = datetime.now().astimezone().date().isoformat()
    with store.conn:
        store.conn.execute("CREATE TABLE IF NOT EXISTS job_budget(id TEXT PRIMARY KEY,day TEXT NOT NULL,charged INTEGER NOT NULL,status TEXT NOT NULL)")
        store.conn.execute("INSERT INTO job_budget VALUES(?,?,?,?)", ("historical-charge", day, charged, "FINISHED"))
    jobs().preflight_campaign(lease)
    output = output_path(root, "after-daily-usage.json")
    with jobs().launch_bounded(lease, spec(root), ["fixture", "echo", str(output)]) as job:
        receipt = job.wait()
        assert receipt["exit_code"] == 0 and receipt["active_processes"] == 0
        assert receipt["memory_limit"] == 128 * 1024 * 1024
        assert receipt["affinity"].bit_count() <= 2
        assert receipt["assigned_before_resume"] and not receipt["timed_out"]
    assert store.conn.execute("SELECT day,charged,status FROM job_budget WHERE id='historical-charge'").fetchone() == (day, charged, "FINISHED")
    fresh = store.conn.execute("SELECT day,charged,status FROM job_budget WHERE id!='historical-charge'").fetchall()
    assert len(fresh) == 1 and fresh[0][0] == day and fresh[0][1] > 0 and fresh[0][2] == "FINISHED"
    assert json.loads(output.read_text())["result"] == "OFFLINE_FIXTURE_OK"
