"""Storage work must not monopolize the control loop or lose inventory."""
from contextlib import contextmanager
from types import SimpleNamespace
import json
import os
import time
from pathlib import Path
import pytest
import compertum.storage as storage
from compertum.config import load_config
from compertum.runtime.errors import RuntimeRefused
from compertum.runtime.identity import resolve_project
from test_persistence import owned

pytestmark=pytest.mark.skipif(os.name!='nt',reason='NATIVE_WINDOWS_UNAVAILABLE')


def test_complete_scan_can_exceed_five_seconds(tmp_path,monkeypatch):
    (tmp_path/'data').mkdir();(tmp_path/'data'/'one').write_bytes(b'x')
    project=resolve_project(tmp_path);clock=[100.0];callbacks=[]
    monkeypatch.setattr(storage.time,'monotonic',lambda:clock[0])
    def progress():
        clock[0]+=1;callbacks.append(clock[0])
    result=storage.sample_storage(project,volume_probe=progress)
    assert 5<result['scan_seconds']<=30 and result['files']['data/one']['size']==1
    assert len(callbacks)>5


def test_cooperative_scan_close_releases_open_directory(tmp_path,monkeypatch):
    (tmp_path/'one').write_bytes(b'x');handles=[];original=storage.Directory
    @contextmanager
    def opened(path,buffer):
        with original(path,buffer) as handle:handles.append(handle);yield handle
    monkeypatch.setattr(storage,'Directory',opened)
    scan=storage.iter_storage(resolve_project(tmp_path))
    next(scan);assert handles and not handles[0].closed
    scan.close();assert all(handle.closed for handle in handles)


def test_scan_deadline_includes_checked_close(tmp_path,monkeypatch):
    clock=[0.0];original=storage.Directory;handles=[]
    monkeypatch.setattr(storage.time,'monotonic',lambda:clock[0])
    @contextmanager
    def opened(path,buffer):
        with original(path,buffer) as handle:handles.append(handle);yield handle
        clock[0]=31.0
    monkeypatch.setattr(storage,'Directory',opened)
    with pytest.raises(RuntimeRefused,match='STORAGE_SCAN_DEADLINE'):
        storage.sample_storage(resolve_project(tmp_path))
    assert all(handle.closed for handle in handles)


def test_historical_config_gets_current_scratch_policy(tmp_path):
    raw=(Path(__file__).parents[2]/'config/default.toml').read_text()
    raw=raw.replace('scratch_bytes = 10737418240','scratch_bytes = 5368709120')
    path=tmp_path/'config.toml';path.write_text(raw)
    config=load_config(path,tmp_path)
    assert config.storage_categories['scratch']==10*1024**3
    assert config.storage_total_bytes==50*1024**3 and config.execution_reserve_bytes==1024**3


def test_watchdog_accepts_long_complete_scan_but_refuses_stale_inventory(monkeypatch):
    from compertum.watchdog import check_storage
    monkeypatch.setattr(storage.time,'monotonic',lambda:100.0)
    observed=dict(completed_monotonic=99.0,scan_seconds=20.0,free_bytes=100*1024**3,
                  total_bytes=0,categories=dict.fromkeys(storage.CAPS,0),files={})
    assert check_storage(observed,[])['status']=='STORAGE_OBSERVED'
    for changed in ({'completed_monotonic':64.0},{'completed_monotonic':101.0},{'scan_seconds':31.0}):
        assert check_storage({**observed,**changed},[])['reason']=='STORAGE_STALE'


def test_pending_watchdog_scan_keeps_status_responsive_and_checkpoint_blocked(owned,monkeypatch):
    from compertum.persistence import open_store
    from compertum.runtime.managed_owner import StorageMonitor
    import compertum.runtime.managed_owner as module
    project,leases=owned
    config_path=project.root_path/'config.toml'
    config_path.write_bytes((Path(__file__).parents[2]/'config/default.toml').read_bytes())
    manager=storage.StorageManager(leases['coordinator'],load_config(config_path,project.root_path))
    original=module.iter_storage;closed=[]
    def slow(*args,**kwargs):
        try:
            for _ in range(4):time.sleep(.06);yield None
            return (yield from original(*args,**kwargs))
        finally:closed.append(True)
    monkeypatch.setattr(module,'iter_storage',slow)
    from compertum.runtime.owners import acquire_owner,release_owner
    watchdog=acquire_owner(project,'watchdog')
    monitor=StorageMonitor(watchdog,project,expect_execution=False)
    try:
        began=time.monotonic();result=monitor.handle('status',{})
        assert time.monotonic()-began<.5
        assert result['reason']=='STORAGE_SCAN_PENDING' and result['heartbeat']['healthy']
        assert result['storage_observed_monotonic'] is None and monitor.reason is None
        from uuid import uuid4
        with pytest.raises(RuntimeRefused,match='WATCHDOG_BLOCKED'):
            monitor.handle('checkpoint',{'barrier_id':str(uuid4())})
        for _ in range(10):
            result=monitor.handle('status',{})
            if result['status']=='HEALTHY':break
        assert result['status']=='HEALTHY' and result['storage_observed_monotonic'] is not None
        assert closed and monitor.reason is None
    finally:monitor.close();release_owner(watchdog)


def test_admission_scan_services_health_without_local_state_writes(monkeypatch):
    from compertum.runtime.supervisor import Supervisor
    supervisor=object.__new__(Supervisor);supervisor.last_poll=0;calls=[]
    def poll(*,enforce):
        calls.append(enforce);supervisor.last_poll=time.monotonic();supervisor.health={'status':'HEALTHY'}
    supervisor.poll_health=poll
    supervisor.scan_health();supervisor.scan_health()
    assert calls==[False]
    supervisor.last_poll=0
    def failed(*,enforce):supervisor.health={'status':'RESEARCH_BLOCKED'}
    supervisor.poll_health=failed
    with pytest.raises(RuntimeRefused,match='HEALTH_UNVERIFIED'):supervisor.scan_health()


def test_recovery_budget_checks_scan_progress_and_restores_health_probe(monkeypatch):
    import compertum.recovery as recovery
    clock=[100.0];calls=[];original=lambda:calls.append(True)
    manager=SimpleNamespace(health_probe=original)
    monkeypatch.setattr(recovery.time,'monotonic',lambda:clock[0])
    with recovery._barrier_budget(manager,240) as check:
        manager.health_probe();assert calls==[True]
        clock[0]=341
        with pytest.raises(RuntimeRefused,match='RECOVERY_BARRIER_TIMEOUT'):manager.health_probe()
        with pytest.raises(RuntimeRefused,match='RECOVERY_BARRIER_TIMEOUT'):check()
    assert manager.health_probe is original


def test_recovery_deadline_prevents_manifest_rename_after_final_hash(owned,monkeypatch):
    import compertum.recovery as recovery
    from uuid import uuid4
    project,leases=owned;clock=[100.0]
    config_path=project.root_path/'config.toml'
    config_path.write_bytes((Path(__file__).parents[2]/'config/default.toml').read_bytes())
    manager=storage.StorageManager(leases['coordinator'],load_config(config_path,project.root_path))
    task=str(uuid4());grant=manager.reserve_bytes(task,'backups',8192)
    original=recovery.hashlib.file_digest
    def delayed_hash(*args,**kwargs):
        result=original(*args,**kwargs);clock[0]=341;return result
    monkeypatch.setattr(recovery.time,'monotonic',lambda:clock[0])
    monkeypatch.setattr(recovery.hashlib,'file_digest',delayed_hash)
    destination=f'backups/{task}/manifest.json'
    with recovery._barrier_budget(manager,240) as check:
        with pytest.raises(RuntimeRefused,match='RECOVERY_BARRIER_TIMEOUT'):
            recovery._write(manager,grant,destination,b'{"complete":true}',before_publish=check)
    assert not (project.root_path/destination).exists()
    assert list((project.root_path/'backups'/task).glob('manifest.json.partial-*'))
    assert manager.health_probe is None


def test_native_owners_keep_heartbeats_during_sixteen_second_scan(tmp_path):
    import subprocess,sys,shutil
    root=Path(__file__).parents[2]
    shutil.copyfile(root/'config/default.toml',tmp_path/'config.toml')
    env={k:v for k,v in os.environ.items() if k.upper() in {'SYSTEMROOT','WINDIR','TEMP','TMP','PYTHONPATH'}}
    env.update(__PYVENV_LAUNCHER__=sys.executable,PYTHONNOUSERSITE='1',PYTHONDONTWRITEBYTECODE='1')
    result=subprocess.run([sys.executable,'-B',str(root/'tests/helpers/storage_health_holder.py'),str(tmp_path)],
        executable=sys._base_executable,env=env,capture_output=True,text=True,timeout=45,creationflags=0x08000000)
    assert result.returncode==0,result.stderr
    record=json.loads(result.stdout)
    assert record['status']=='VERIFIED' and record['health_samples']>100
