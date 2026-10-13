"""Reservations reject crossing writes and preserve all interrupted evidence."""
import importlib
from dataclasses import replace
from pathlib import Path
from uuid import uuid4
import pytest
from test_persistence import owned
from compertum.config import load_config
from compertum.runtime.errors import RuntimeRefused


def module(): return importlib.import_module('compertum.storage')


def manager(owned):
    project,leases=owned
    source=Path(__file__).parents[1]/'config/default.toml'
    config_path=project.root_path/'config.toml'; config_path.write_bytes(source.read_bytes())
    config=load_config(config_path,project.root_path)
    return module().StorageManager(leases['coordinator'],config)


def test_crossing_chunk_writes_no_bytes_and_publish_is_idempotent(owned):
    store=manager(owned); task=str(uuid4()); grant=store.reserve_bytes(task,'records',8)
    writer=store.open_artifact(grant,f'artifacts/runs/{task}/result.bin')
    writer.write(b'abcd')
    with pytest.raises(RuntimeRefused,match='OUTPUT_BOUND_EXCEEDED'): writer.write(b'12345')
    assert writer.path.read_bytes()==b'abcd'
    writer.write(b'efgh'); receipt=writer.publish()
    assert writer.publish()==receipt and receipt['size_bytes']==8
    assert (store.root/receipt['path']).read_bytes()==b'abcdefgh'
    assert store.reservations()[0]['status']=='PUBLISHED'


def test_reservations_serialize_and_cannot_raise_fixed_caps(owned):
    store=manager(owned)
    with pytest.raises(RuntimeRefused,match='STORAGE_CAPACITY'):
        store.reserve_bytes(str(uuid4()),'records',5*1024**3)
    task=str(uuid4()); grant=store.reserve_bytes(task,'records',100)
    with pytest.raises(RuntimeRefused): store.reserve_bytes(task,'unknown',100)
    with pytest.raises(RuntimeRefused): store.open_artifact(grant,'../outside.bin')
    with pytest.raises(RuntimeRefused): store.open_artifact(grant,'state/execution-reserve.bin')


def test_abandoned_bytes_remain_charged_after_manager_restart(owned):
    store=manager(owned); task=str(uuid4()); grant=store.reserve_bytes(task,'records',8192)
    writer=store.open_artifact(grant,f'artifacts/runs/{task}/incomplete.bin'); writer.write(b'x'*1024); writer.close()
    before=store.observation()['categories']['records']
    restarted=module().StorageManager(store.lease,store.config)
    assert restarted.observation()['categories']['records']>=before
    assert restarted.reservations()[0]['status']=='ABANDONED'
    assert writer.path.exists()


def test_native_scan_counts_allocation_and_rejects_reparse_escape(owned):
    project,_=owned
    file=project.root_path/'small.bin'; file.write_bytes(b'x')
    observed=module().sample_storage(project)
    assert observed['files']['small.bin']['allocated']>=1
    target=project.root_path.parent/'external'; target.mkdir(exist_ok=True)
    (project.root_path/'escape').symlink_to(target,target_is_directory=True)
    with pytest.raises(RuntimeRefused,match='STORAGE_REPARSE_ESCAPE'):
        module().sample_storage(project)


def test_execution_reserve_is_allocated_exclusive_and_role_scoped(owned):
    project,leases=owned
    with pytest.raises(RuntimeRefused,match='WRONG_OWNER_ROLE'):
        module().create_journal_reserve(leases['coordinator'],1024*1024)
    reserve=module().create_journal_reserve(leases['execution'],1024*1024)
    assert reserve.receipt()['allocated_bytes']>=1024*1024
    assert reserve.receipt()['sparse'] is False
    from compertum.runtime._windows import WindowsAPI,NativeCallError
    with pytest.raises(NativeCallError):
        with WindowsAPI().open_file(project.root_path/'state/execution-reserve.bin',0x40000000,0): pass
    reserve.release(65536,str(uuid4()))
    assert reserve.receipt()['unused_bytes']==1024*1024-65536


def test_concurrent_reservations_cannot_overbook_category(owned):
    from concurrent.futures import ThreadPoolExecutor
    store=manager(owned)
    def reserve_one(_):
        try: return store.reserve_bytes(str(uuid4()),'records',2*1024**3)
        except RuntimeRefused as error:
            assert error.code=='STORAGE_CAPACITY'; return None
    with ThreadPoolExecutor(max_workers=3) as pool: admitted=list(pool.map(reserve_one,range(3)))
    assert sum(item is not None for item in admitted)==1


def test_owner_release_closes_an_abandoned_open_writer(owned):
    from compertum.runtime.owners import release_owner
    store=manager(owned); task=str(uuid4()); grant=store.reserve_bytes(task,'records',100)
    writer=store.open_artifact(grant,f'artifacts/runs/{task}/abandoned.bin');writer.write(b'preserved')
    release_owner(store.lease)
    assert writer.closed and writer.path.read_bytes()==b'preserved'


def test_split_grant_cannot_duplicate_reserved_capacity(owned):
    store=manager(owned); parent=store.reserve_bytes(str(uuid4()),'backups',8192)
    child=store.split_grant(parent,4096)
    with pytest.raises(RuntimeRefused,match='GRANT_BOUND_EXCEEDED'):
        store.split_grant(parent,4097)
    assert child.maximum==4096
    with pytest.raises(RuntimeRefused): store.open_artifact(parent,f'backups/{parent.task_id}/parent.bin')


def test_reserve_release_and_refill_have_durable_idempotent_intents(owned):
    _,leases=owned;reserve=module().create_journal_reserve(leases['execution'],1024*1024)
    incident=str(uuid4());reserve.release(65536,incident);reserve.release(65536,incident)
    assert reserve.receipt()['unused_bytes']==1024*1024-65536
    refill=str(uuid4());reserve.refill(refill);reserve.refill(refill)
    assert reserve.receipt()['unused_bytes']==1024*1024
    reserve.release(65536,incident)
    assert reserve.receipt()['unused_bytes']==1024*1024
