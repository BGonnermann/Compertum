"""Independent observed growth and conservative storage admission."""
import importlib
import os
from pathlib import Path
import subprocess
import sys
import time
import pytest
from fixture_processes import python_process
from compertum.runtime.identity import resolve_project
from compertum.runtime.errors import RuntimeRefused

pytestmark=pytest.mark.skipif(os.name!='nt',reason='NATIVE_WINDOWS_UNAVAILABLE')


def test_independent_process_growth_trips_watchdog_within_five_seconds(tmp_path):
    storage=importlib.import_module('compertum.storage'); watch=importlib.import_module('compertum.watchdog')
    project=resolve_project(tmp_path); first=storage.sample_storage(project)
    target=tmp_path/'unmetered.bin'
    env={k:v for k,v in os.environ.items() if k.upper() in {'SYSTEMROOT','WINDIR'}}
    started=time.monotonic()
    child=python_process(['-B','-c','from pathlib import Path; import sys; Path(sys.argv[1]).write_bytes(b"x"*65536)',str(target)],env=env)
    try:
        child.wait(timeout=2)
        second=storage.sample_storage(project)
        result=watch.check_storage(second,[],previous=first)
        assert result['status']=='RESEARCH_BLOCKED' and result['reason']=='UNACCOUNTED_GROWTH'
        assert time.monotonic()-started<5
        assert target.stat().st_size==65536
    finally:
        if child.poll() is None: child.terminate(); child.wait(timeout=2)


def test_low_free_space_and_stale_monitor_never_admit(tmp_path):
    storage=importlib.import_module('compertum.storage'); watch=importlib.import_module('compertum.watchdog')
    observation=storage.sample_storage(resolve_project(tmp_path))
    for change,reason in (({'free_bytes':49*1024**3},'FREE_SPACE_FLOOR'),({'completed_monotonic':time.monotonic()-storage.INVENTORY_MAX_AGE-1},'STORAGE_STALE')):
        result=watch.check_storage({**observation,**change},[])
        assert result['status']=='RESEARCH_BLOCKED' and result['reason']==reason
        assert result['broker_capability']=='CAPABILITY_UNAVAILABLE'
