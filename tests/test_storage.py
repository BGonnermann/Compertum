import importlib
import pytest
from compertum.runtime.owners import acquire_owner,resolve_project
from compertum.persistence import open_store

def api():
    try:return importlib.import_module('compertum.storage')
    except ImportError:pytest.fail('bounded storage missing')

def test_crossing_write_refused_and_failed_bytes_retained(tmp_path):
    m=api();owner=acquire_owner(resolve_project(tmp_path),'coordinator');store=open_store(owner,'coordinator')
    try:
        manager=m.StorageManager(store,free_floor=0)
        grant=manager.reserve_bytes('task','scratch',4)
        writer=manager.open_artifact(grant,'.cache/out.bin');writer.write(b'ab')
        with pytest.raises(ValueError):writer.write(b'cde')
        writer.close()
        assert writer.staging.read_bytes()==b'ab'
        assert manager.reservations()[0]['written']==2
    finally:store.close();owner.close()

def test_reserve_release_floor_refill_and_wrong_role(tmp_path):
    m=api();p=resolve_project(tmp_path);execution=acquire_owner(p,'execution');coordinator=acquire_owner(p,'coordinator')
    try:
        initial=m.create_journal_reserve(execution,320*1024**2);assert initial['allocated_bytes']>=320*1024**2
        with pytest.raises(ValueError,match='DENIED'):m.release_journal_reserve(coordinator,64*1024**2,'bad')
        released=m.release_journal_reserve(execution,64*1024**2,'synthetic-incident');assert released['bytes']==256*1024**2
        with pytest.raises(ValueError,match='CAPACITY'):m.release_journal_reserve(execution,64*1024**2,'floor')
        assert m.refill_journal_reserve(execution,320*1024**2)['allocated_bytes']>=320*1024**2
    finally:execution.close();coordinator.close()

def test_reservations_and_publish_are_serialized(tmp_path):
    m=api();owner=acquire_owner(resolve_project(tmp_path),'coordinator');store=open_store(owner,'coordinator')
    try:
        manager=m.StorageManager(store,free_floor=0,category_caps={'scratch':8192})
        grant=manager.reserve_bytes('one','scratch',4096)
        with pytest.raises(ValueError):manager.reserve_bytes('two','scratch',8192)
        writer=manager.open_artifact(grant,'.cache/published.bin');writer.write(b'ok');manifest=writer.publish()
        assert manifest['bytes']==2 and (tmp_path/'.cache/published.bin').read_bytes()==b'ok'
        with pytest.raises(ValueError):writer.publish()
        assert manager.reservations()[0]['state']=='PUBLISHED'
    finally:store.close();owner.close()

def test_flush_failure_retains_evidence_without_publication(tmp_path,monkeypatch):
    m=api();owner=acquire_owner(resolve_project(tmp_path),'coordinator');store=open_store(owner,'coordinator')
    try:
        manager=m.StorageManager(store);grant=manager.reserve_bytes('flush','scratch',4096);writer=manager.open_artifact(grant,'.cache/flush.bin')
        original=m.os.fsync
        def failed(fd):raise OSError('INJECTED_FLUSH_FAILURE')
        monkeypatch.setattr(m.os,'fsync',failed)
        with pytest.raises(OSError,match='FLUSH'):writer.write(b'evidence')
        with pytest.raises(ValueError,match='UNFLUSHED'):writer.publish()
        monkeypatch.setattr(m.os,'fsync',original);writer.close();assert writer.staging.read_bytes()==b'evidence' and not writer.target.exists()
    finally:store.close();owner.close()

def test_simulated_free_space_drop_refuses_write(tmp_path,monkeypatch):
    m=api();owner=acquire_owner(resolve_project(tmp_path),'coordinator');store=open_store(owner,'coordinator')
    try:
        manager=m.StorageManager(store);grant=manager.reserve_bytes('low','scratch',4096);writer=manager.open_artifact(grant,'.cache/low.bin')
        original=m.shutil.disk_usage(tmp_path)
        monkeypatch.setattr(m.shutil,'disk_usage',lambda p:original._replace(free=49*1024**3))
        with pytest.raises(ValueError,match='WRITE_CAPACITY'):writer.write(b'x')
        writer.close();assert writer.staging.stat().st_size==0
    finally:store.close();owner.close()

def test_native_junction_artifact_target_refused(tmp_path):
    import subprocess
    m=api();owner=acquire_owner(resolve_project(tmp_path),'coordinator');store=open_store(owner,'coordinator')
    try:
        manager=m.StorageManager(store);grant=manager.reserve_bytes('reparse','scratch',4096)
        cache=tmp_path/'.cache';cache.mkdir();target=tmp_path/'target';target.mkdir();link=cache/'link'
        made=subprocess.run(['cmd','/c','mklink','/J',str(link),str(target)],capture_output=True,timeout=5);assert made.returncode==0
        try:
            with pytest.raises(ValueError,match='REPARSE'):manager.open_artifact(grant,'.cache/link/output')
            assert not list(target.iterdir())
        finally:link.rmdir()
    finally:store.close();owner.close()
