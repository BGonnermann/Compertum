import json,time,subprocess,sys
import pytest
from compertum.cli import start_research,control
from compertum.domain import digest
from compertum.coordinator import FIXTURE
from compertum.runtime import win32 as w

def healthy(root):
    deadline=time.monotonic()+12
    while time.monotonic()<deadline:
        status=control(root,'status')['result']
        if status['storage_healthy']:return status
        time.sleep(.1)
    pytest.fail('native watchdog health unverified')

def stopped(root):
    meta=json.loads((root/'state/runtime/supervisor.json').read_text());deadline=time.monotonic()+15
    while time.monotonic()<deadline:
        if w.process_absent(meta['pid']):return
        try:
            if w.identity(meta['pid'])['exited']:return
        except OSError:pass
        time.sleep(.1)
    pytest.fail('original supervisor still alive')

def test_two_terminal_attach_pause_restart_artifact_and_stop(tmp_path):
    first=start_research(tmp_path);second=start_research(tmp_path)
    assert first['generation']==second['generation']
    try:
        healthy(tmp_path)
        assert control(tmp_path,'watchdog-health')['exit_code']==3
        paused=subprocess.run([sys.executable,'-B','-m','compertum','--root',str(tmp_path),'research','pause','--reason','operator','--json'],capture_output=True,text=True,timeout=10)
        assert paused.returncode==0 and json.loads(paused.stdout)['result']['state']=='PAUSED'
        assert control(tmp_path,'resume')['exit_code']==0
        task=control(tmp_path,'fixture',request_id='fixture-once')['result']
        duplicate=control(tmp_path,'fixture',request_id='fixture-once')['result'];assert duplicate['task_id']==task['task_id']
        time.sleep(.3);started=time.monotonic();assert control(tmp_path,'pause')['exit_code']==0;assert time.monotonic()-started<30
        paused=control(tmp_path,'status')['result']['tasks'][0];assert paused['state']=='PAUSED'
        assert control(tmp_path,'shutdown')['exit_code']==0;stopped(tmp_path)
        third=start_research(tmp_path);assert third['generation']!=first['generation'];healthy(tmp_path)
        assert control(tmp_path,'resume')['exit_code']==0
        deadline=time.monotonic()+12
        while time.monotonic()<deadline:
            result=control(tmp_path,'status')['result']['tasks'][0]
            if result['state']=='COMPLETE':break
            time.sleep(.1)
        assert result['state']=='COMPLETE' and result['attempts']==2
        assert result['artifact']['sha256']==digest(FIXTURE)
        assert (tmp_path/result['artifact']['path']).read_bytes()==b'{"answer":14,"fixture":"m0-v1"}'
        other=control(tmp_path,'fixture')['result'];assert control(tmp_path,'stop',run_id=other['task_id'])['result']['state']=='STOPPED'
    finally:
        try:control(tmp_path,'shutdown');stopped(tmp_path)
        except (OSError,RuntimeError):pass

def test_ai_absence_does_not_stop_foundation(tmp_path):
    from compertum.foundation import run_foundation_suite
    r=run_foundation_suite(tmp_path);assert r['result']['sha256']==digest(FIXTURE)

def test_mismatched_checkpoint_hash_refuses_restart(tmp_path):
    start_research(tmp_path);healthy(tmp_path);control(tmp_path,'resume');control(tmp_path,'fixture');control(tmp_path,'pause');control(tmp_path,'shutdown');stopped(tmp_path)
    script='''
import sys
from pathlib import Path
from compertum.runtime.identity import resolve_project
from compertum.runtime.owners import acquire_owner
from compertum.persistence import open_store
p=resolve_project(Path(sys.argv[1]))
with acquire_owner(p,'coordinator') as l:
 s=open_store(l,'coordinator');key=s.db.execute("SELECT key FROM kv WHERE key LIKE 'task:%'").fetchone()[0];v=s.get(key);v['code_hash']='synthetic mismatch';s.set(key,v);s.close()
'''
    changed=subprocess.run([sys.executable,'-B','-c',script,str(tmp_path)],capture_output=True,text=True,timeout=10);assert changed.returncode==0,changed.stderr
    try:
        start_research(tmp_path);healthy(tmp_path);assert control(tmp_path,'resume')['exit_code']==3
        assert control(tmp_path,'status')['result']['research_paused'] is True
    finally:control(tmp_path,'shutdown');stopped(tmp_path)
