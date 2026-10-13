"""A native supervisor and offline Job continue during manual wait/local timeout.

The disposable HTTP server is contract evidence, never live Strata acceptance.
"""
import hashlib
from pathlib import Path
import shutil
import time
from uuid import uuid4
import pytest
from test_ai_manual import bridge
from test_ai_strata_contract import server,adapter
from ai_fixture import ai_task
from test_m0_lifecycle import launch,stopped
from compertum.runtime.supervisor import control
from compertum.runtime.errors import RuntimeRefused


def test_provider_outage_does_not_stop_native_offline_work(bridge):
    b,airoot=bridge;root=airoot.parent/('offline-outage-'+str(uuid4()));root.mkdir()
    shutil.copyfile(Path(__file__).parents[2]/'config/default.toml',root/'config.toml')
    manual,relative=ai_task(airoot);b.export_subscription_task(manual,prompt='Synthetic manual wait.',files=[relative])
    child,status=launch(root)
    try:
        control(root,'resume_research');submitted=control(root,'foundation.check',{'operation':'submit'})
        with server('timeout') as (port,state):
            client=adapter(bridge,port);task,_=ai_task(airoot,'strata',deadline=1)
            with pytest.raises(RuntimeRefused,match='LOCAL_COMPLETION_UNVERIFIED'):
                client.request_proposal(task,[{'role':'user','content':'Synthetic timeout.'}],validate_proposal=False)
            assert client.state()=='OWNED_REQUEST_UNCERTAIN'
            deadline=time.monotonic()+8
            while time.monotonic()<deadline:
                status=control(root,'status');record=next(r for r in status['fixtures'] if r['task_id']==submitted['task_id'])
                if record['status']=='COMPLETED': break
                time.sleep(.1)
            assert record['status']=='COMPLETED'
            assert record['artifact']['sha256']==hashlib.sha256(b'compertum-offline-fixture-v1\n').hexdigest()
            assert status['watchdog']['status']=='HEALTHY' and status['order_admission']=='DISARMED'
            assert b.store.conn.execute('SELECT status FROM ai_tasks').fetchone()[0]=='WAITING_FOR_OPERATOR'
        control(root,'shutdown');stopped(child)
    finally:
        if child.poll() is None: child.kill();child.wait(timeout=5)


def test_native_adapter_process_has_one_cpu_and_256mib_limit(tmp_path):
    import os,subprocess,sys,json
    env={k:v for k,v in os.environ.items() if k.upper() in {'SYSTEMROOT','WINDIR','TEMP','TMP'}}
    env.update(PYTHONDONTWRITEBYTECODE='1',PYTHONNOUSERSITE='1')
    result=subprocess.run([sys.executable,'-B',str(Path(__file__).parents[1]/'helpers/ai_limits.py')],env=env,capture_output=True,text=True,timeout=10)
    assert result.returncode==0 and not result.stderr
    observed=json.loads(result.stdout)
    assert observed['verified'] and observed['memory_limit']==256*1024**2 and observed['affinity'].bit_count()==1 and observed['active_process_limit']==1
