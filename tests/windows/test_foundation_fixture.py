"""Pause a real metered fixture Job, then validate and continue its checkpoint."""
import hashlib
import shutil
from pathlib import Path
import time
import pytest
from compertum.config import load_config
from compertum.coordinator import Coordinator
from compertum.persistence import open_store
from compertum.runtime.identity import resolve_project
from compertum.runtime.owners import acquire_owner,release_owner
from compertum.runtime.ipc import ProtocolDecision
from compertum.runtime.errors import RuntimeRefused
from compertum.storage import StorageManager
from compertum.foundation import FixtureController,fixture_spec
from uuid import uuid4


def test_native_fixture_pause_resume_and_exact_artifact(tmp_path):
    shutil.copyfile(Path(__file__).parents[2]/'config/default.toml',tmp_path/'config.toml')
    lease=acquire_owner(resolve_project(tmp_path),'coordinator')
    try:
        c=Coordinator(open_store(lease,'coordinator'),health=lambda:{'status':'HEALTHY','observed_monotonic':time.monotonic()})
        manager=StorageManager(lease,load_config(tmp_path/'config.toml',tmp_path));fixtures=FixtureController(c,manager)
        c.control(ProtocolDecision(str(uuid4()),'a'*64,'b'*64,1),'resume_research',{})
        spec=fixture_spec(tmp_path);r=fixtures.submit(spec);time.sleep(.3);fixtures.pause('pause_research')
        paused=fixtures.records()[0]
        assert paused['status']=='PAUSED' and paused['checkpoint']['size_bytes']<28
        fixtures.resume(r['task_id'])
        deadline=time.monotonic()+5
        while fixtures.active and time.monotonic()<deadline: fixtures.tick();time.sleep(.05)
        final=fixtures.records()[0]
        assert final['status']=='COMPLETED' and final['attempt']==2
        expected=b'compertum-offline-fixture-v1\n'
        assert final['artifact']['sha256']==hashlib.sha256(expected).hexdigest()
        assert (tmp_path/final['artifact']['path']).read_bytes()==expected
        assert [a['status'] for a in c.store.attempts()]==['PAUSED','COMPLETED']
    finally: release_owner(lease)
