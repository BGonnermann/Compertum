"""Native independent monitor observes real bypass growth through private RPC."""
import shutil
import time
from pathlib import Path
import pytest
from compertum.config import load_config
from compertum.runtime.identity import resolve_project
from compertum.runtime.owners import acquire_owner,release_owner
from compertum.runtime.managed import launch_owner
from compertum.runtime.owner_rpc import call_owner
from compertum.storage import StorageManager,reserve_runtime_paths


def test_independent_watchdog_has_native_limits_and_detects_growth(tmp_path):
    shutil.copyfile(Path(__file__).parents[2]/'config/default.toml',tmp_path/'config.toml')
    project=resolve_project(tmp_path);supervisor=acquire_owner(project,'supervisor');coordinator=acquire_owner(project,'coordinator')
    job=None
    try:
        manager=StorageManager(coordinator,load_config(tmp_path/'config.toml',tmp_path));reserve_runtime_paths(manager)
        job,remote=launch_owner(supervisor,'watchdog')
        first=call_owner(remote,'status',{})
        assert first['status']=='HEALTHY'
        limits=job.api.limits(job.job)
        assert limits.job_memory==128*1024**2 and limits.basic.affinity.bit_count()==1
        began=time.monotonic();(tmp_path/'unexpected.bin').write_bytes(b'x'*65536)
        while time.monotonic()-began<5:
            result=call_owner(remote,'status',{})
            if result['status']=='RESEARCH_BLOCKED': break
            time.sleep(.1)
        assert result['reason']=='UNACCOUNTED_GROWTH' and time.monotonic()-began<5
        assert (tmp_path/'state/watchdog/halt.json').exists()
    finally:
        if job: job.close()
        release_owner(coordinator);release_owner(supervisor)


def test_grant_committed_during_scan_is_not_false_unaccounted_growth(tmp_path,monkeypatch):
    from uuid import uuid4
    import compertum.runtime.managed_owner as owner_module
    shutil.copyfile(Path(__file__).parents[2]/'config/default.toml',tmp_path/'config.toml')
    project=resolve_project(tmp_path);coordinator=acquire_owner(project,'coordinator');watchdog=acquire_owner(project,'watchdog')
    try:
        manager=StorageManager(coordinator,load_config(tmp_path/'config.toml',tmp_path));reserve_runtime_paths(manager)
        monitor=owner_module.StorageMonitor(watchdog,project);monitor.tick();monitor.last_scan=0
        actual=owner_module.iter_storage
        def concurrent_publication(*args,**kwargs):
            task_id=str(uuid4());writer=manager.open_artifact(manager.reserve_bytes(task_id,'records',128),f'artifacts/runs/{task_id}/concurrent.bin')
            try: writer.write(b'admitted during scan');writer.publish()
            finally: writer.close()
            return (yield from actual(*args,**kwargs))
        monkeypatch.setattr(owner_module,'iter_storage',concurrent_publication)
        monitor.tick()
        assert monitor.reason is None
        assert not (tmp_path/'state/watchdog/halt.json').exists()
    finally: release_owner(watchdog);release_owner(coordinator)


def test_full_watchdog_expires_execution_that_never_started(tmp_path):
    shutil.copyfile(Path(__file__).parents[2]/'config/default.toml',tmp_path/'config.toml')
    project=resolve_project(tmp_path);supervisor=acquire_owner(project,'supervisor');coordinator=acquire_owner(project,'coordinator');job=None
    try:
        manager=StorageManager(coordinator,load_config(tmp_path/'config.toml',tmp_path));reserve_runtime_paths(manager)
        job,remote=launch_owner(supervisor,'watchdog');began=time.monotonic();result=None
        while time.monotonic()-began<17:
            result=call_owner(remote,'status',{})
            if result['reason']:break
            time.sleep(.2)
        assert result['reason']=='PEER_HEARTBEAT_STALE' and not result['mutual']['verified']
        assert time.monotonic()-began<16
    finally:
        if job:job.close()
        release_owner(coordinator);release_owner(supervisor)
