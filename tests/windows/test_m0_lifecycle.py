"""Two-terminal lifecycle with real supervisor, watcher and bounded fixture Jobs."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import pytest
from compertum.runtime.supervisor import control
from compertum.runtime.errors import RuntimeRefused

ROOT=Path(__file__).parents[2]

def launch(root):
    env={k:v for k,v in os.environ.items() if k.upper() in {'SYSTEMROOT','WINDIR','TEMP','TMP','PYTHONPATH'}}
    env.update(__PYVENV_LAUNCHER__=sys.executable,PYTHONNOUSERSITE='1',PYTHONDONTWRITEBYTECODE='1')
    child=subprocess.Popen([sys.executable,'-B',str(ROOT/'tests/helpers/supervisor_holder.py'),str(root)],
        executable=sys._base_executable,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=0x08000000)
    deadline=time.monotonic()+8
    while time.monotonic()<deadline:
        if child.poll() is not None:
            out,err=child.communicate();pytest.fail(err.decode())
        try:
            status=control(root,'status')
            return child,status
        except (RuntimeRefused,OSError): time.sleep(.05)
    child.kill();out,err=child.communicate(timeout=3);pytest.fail('SUPERVISOR_START_TIMEOUT '+err.decode())

def stopped(child):
    out,err=child.communicate(timeout=5)
    assert child.returncode==0,err.decode()

def test_terminal_pause_checkpoint_restart_resume(tmp_path):
    shutil.copyfile(ROOT/'config/default.toml',tmp_path/'config.toml')
    child,status=launch(tmp_path)
    try:
        assert status['research_state']=='PAUSED' and status['watchdog']['status']=='HEALTHY'
        control(tmp_path,'resume_research')
        task=control(tmp_path,'foundation.check',{'operation':'submit'});time.sleep(.3)
        began=time.monotonic();pause=control(tmp_path,'pause_research')
        assert pause['confirmed'] and time.monotonic()-began<30
        status=control(tmp_path,'status');checkpoint=status['fixtures'][0]['checkpoint']
        assert status['fixtures'][0]['status']=='PAUSED'
        assert (tmp_path/checkpoint['path']).is_file()
        control(tmp_path,'shutdown');stopped(child)
        child,status=launch(tmp_path)
        assert status['supervisor_generation']==2 and status['order_admission']=='DISARMED'
        control(tmp_path,'resume_research')
        control(tmp_path,'foundation.check',{'operation':'resume','task_id':task['task_id']})
        deadline=time.monotonic()+6
        while time.monotonic()<deadline:
            status=control(tmp_path,'status')
            if status['fixtures'][0]['status']=='COMPLETED': break
            time.sleep(.1)
        final=status['fixtures'][0]
        assert final['status']=='COMPLETED',status
        assert final['artifact']['sha256']==hashlib.sha256(b'compertum-offline-fixture-v1\n').hexdigest()
        assert status['watchdog']['status']=='HEALTHY'
        control(tmp_path,'shutdown');stopped(child)
    finally:
        if child.poll() is None: child.kill();child.wait(timeout=5)


def test_storage_trip_stops_active_job_and_blocks_resume(tmp_path):
    from compertum.runtime._windows import WindowsAPI
    shutil.copyfile(ROOT/'config/default.toml',tmp_path/'config.toml')
    child,status=launch(tmp_path)
    observed=None
    try:
        assert status['coordinator_limits']['memory_limit']==256*1024**2
        control(tmp_path,'resume_research');control(tmp_path,'foundation.check',{'operation':'submit'})
        status=control(tmp_path,'status');api=WindowsAPI();observed=api.open_process(status['active_job_pid'])
        began=time.monotonic();(tmp_path/'bypass.bin').write_bytes(b'x'*65536)
        deadline=began+5
        while time.monotonic()<deadline:
            status=control(tmp_path,'status')
            if status['watchdog']['status']=='RESEARCH_BLOCKED': break
            time.sleep(.1)
        assert time.monotonic()-began<5 and status['watchdog']['reason']=='UNACCOUNTED_GROWTH'
        assert api.WaitForSingleObject(observed.get(),0)==0
        assert status['research_state']=='PAUSED'
        with pytest.raises(RuntimeRefused,match='HEALTH_UNVERIFIED'): control(tmp_path,'resume_research')
        control(tmp_path,'shutdown');stopped(child)
        child,status=launch(tmp_path)
        assert status['watchdog']['status']=='RESEARCH_BLOCKED'
        assert status['watchdog']['reason']=='RETAINED_WATCHDOG_HALT'
        control(tmp_path,'shutdown');stopped(child)
    finally:
        if observed: observed.close()
        if child.poll() is None: child.kill();child.wait(timeout=5)


def test_request_id_is_bound_across_control_fixture_and_ai_branches(tmp_path):
    from uuid import uuid4
    shutil.copyfile(ROOT/'config/default.toml',tmp_path/'config.toml')
    child,status=launch(tmp_path)
    try:
        request_id=str(uuid4());control(tmp_path,'resume_research',request_id=request_id)
        with pytest.raises(RuntimeRefused,match='REQUEST_CONFLICT'):
            control(tmp_path,'foundation.check',{'operation':'submit'},request_id=request_id)
        assert control(tmp_path,'status')['fixtures']==[]
        request_id=str(uuid4());task_id=str(uuid4())
        first=control(tmp_path,'ai.export',{'task_id':task_id,'provider':'subscription'},request_id=request_id)
        assert first['status']=='WAITING_FOR_OPERATOR'
        assert control(tmp_path,'ai.export',{'task_id':task_id,'provider':'subscription'},request_id=request_id)==first
        with pytest.raises(RuntimeRefused,match='REQUEST_CONFLICT'):
            control(tmp_path,'ai.export',{'task_id':str(uuid4()),'provider':'subscription'},request_id=request_id)
        control(tmp_path,'shutdown');stopped(child)
    finally:
        if child.poll() is None: child.kill();child.wait(timeout=5)


def test_stop_named_run_and_pause_reason_are_applied(tmp_path):
    from uuid import uuid4
    shutil.copyfile(ROOT/'config/default.toml',tmp_path/'config.toml')
    child,status=launch(tmp_path)
    try:
        control(tmp_path,'resume_research');task=control(tmp_path,'foundation.check',{'operation':'submit'})
        with pytest.raises(RuntimeRefused,match='RUN_UNKNOWN'): control(tmp_path,'stop_research',{'run_id':str(uuid4())})
        assert control(tmp_path,'status')['active_job_pid'] is not None
        receipt=control(tmp_path,'stop_research',{'run_id':task['run_id']})
        assert receipt['confirmed'] and control(tmp_path,'status')['active_job_pid'] is None
        assert control(tmp_path,'status')['fixtures'][0]['status']=='FAILED'
        assert control(tmp_path,'pause_research',{'reason':'Synthetic operator checkpoint'})['confirmed']
        control(tmp_path,'shutdown');stopped(child)
    finally:
        if child.poll() is None: child.kill();child.wait(timeout=5)
