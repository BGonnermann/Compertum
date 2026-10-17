"""Real Windows files and owners. Full reserve capacity is not tested here."""
import hashlib
import json
import os
from pathlib import Path
from uuid import uuid4

import pytest

from test_persistence import owned
from test_storage import manager
from compertum.runtime.errors import RuntimeRefused


def original(storage, raw=b'unchanged original evidence'):
    task = str(uuid4())
    writer = storage.open_artifact(storage.reserve_bytes(task, 'records', max(1, len(raw))),
                                   f'artifacts/runs/{task}/input.bin')
    try:
        writer.write(raw)
        record = writer.publish()
    finally:
        writer.close()
    return {k: record[k] for k in ('artifact_id', 'path', 'size_bytes', 'sha256')} | {'parent_artifact_ids': []}


def copies(storage, grant, artifacts, check=lambda: None):
    from compertum.backup_artifacts import shared_backup_artifacts
    with shared_backup_artifacts(storage, grant, artifacts, check=check) as result:
        return result


def grant(storage, size=2 * 1024**2):
    return storage.reserve_bytes(str(uuid4()), 'backups', size)


def test_repeated_artifact_keeps_one_independent_backup(owned):
    storage = manager(owned)
    item = original(storage)
    first = copies(storage, grant(storage), [item])[0]
    before = (storage.root / first['path']).read_bytes()
    second = copies(storage, grant(storage), [item])[0]
    assert first == second
    assert first['path'] != item['path']
    assert (storage.root / first['path']).stat().st_ino != (storage.root / item['path']).stat().st_ino
    assert (storage.root / first['path']).stat().st_nlink == 1
    assert (storage.root / first['path']).read_bytes() == before
    assert storage.store.conn.execute("SELECT count(*) FROM reservations WHERE category='backups' AND status='PUBLISHED'").fetchone() == (1,)


def test_equal_bytes_with_different_artifact_ids_keep_distinct_paths(owned):
    storage = manager(owned)
    a, b = original(storage), original(storage)
    result = copies(storage, grant(storage), [a, b])
    assert a['sha256'] == b['sha256']
    assert result[0]['path'] != result[1]['path']
    assert [r['artifact_id'] for r in result] == [a['artifact_id'], b['artifact_id']]


@pytest.mark.parametrize('damage', ['missing', 'changed', 'truncated', 'hardlink', 'ledger', 'oversized_manifest', 'unpublished'])
def test_damaged_backup_is_refused_without_replacing_it(owned, damage):
    storage = manager(owned)
    item = original(storage)
    parent = grant(storage)
    saved = copies(storage, parent, [item])[0]
    path = storage.root / saved['path']
    if damage == 'missing':
        path.rename(path.with_suffix('.retained'))
    elif damage == 'changed':
        path.write_bytes(b'x' * item['size_bytes'])
    elif damage == 'truncated':
        path.write_bytes(b'x')
    elif damage == 'hardlink':
        os.link(path, path.with_suffix('.linked'))
    elif damage == 'ledger':
        record = json.loads(storage.store.conn.execute('SELECT manifest FROM reservations WHERE path=?', (saved['path'],)).fetchone()[0])
        record['sha256'] = '0' * 64
        with storage.store.conn:
            storage.store.conn.execute('UPDATE reservations SET manifest=? WHERE path=?', (json.dumps(record), saved['path']))
    elif damage == 'oversized_manifest':
        with storage.store.conn:
            storage.store.conn.execute('UPDATE reservations SET manifest=? WHERE path=?', ('x' * 4097, saved['path']))
    else:
        with storage.store.conn:
            storage.store.conn.execute("UPDATE reservations SET status='ABANDONED' WHERE path=?", (saved['path'],))
    before = path.read_bytes() if path.exists() else None
    with pytest.raises((RuntimeRefused, OSError)):
        copies(storage, parent, [item])
    assert (path.read_bytes() if path.exists() else None) == before
    assert (storage.root / item['path']).read_bytes() == b'unchanged original evidence'


def test_reuse_still_requires_matching_original_bytes(owned):
    storage = manager(owned)
    item = original(storage)
    saved = copies(storage, grant(storage), [item])[0]
    (storage.root / item['path']).write_bytes(b'changed original')
    with pytest.raises(RuntimeRefused):
        copies(storage, grant(storage), [item])
    assert hashlib.sha256((storage.root / saved['path']).read_bytes()).hexdigest() == item['sha256']


def test_unregistered_file_is_never_adopted(owned):
    storage = manager(owned)
    item = original(storage)
    parent = grant(storage)
    saved = copies(storage, parent, [item])[0]
    with storage.store.conn:
        storage.store.conn.execute('DELETE FROM reservations WHERE path=?', (saved['path'],))
    with pytest.raises(RuntimeRefused):
        copies(storage, parent, [item])
    assert (storage.root / saved['path']).read_bytes() == (storage.root / item['path']).read_bytes()


def test_held_original_and_backup_cannot_be_written_or_renamed(owned):
    from compertum.backup_artifacts import shared_backup_artifacts
    storage = manager(owned)
    item = original(storage)
    with shared_backup_artifacts(storage, grant(storage), [item], check=lambda: None) as result:
        for record in (item, result[0]):
            path = storage.root / record['path']
            with pytest.raises(OSError):
                with path.open('r+b'):
                    pass
            with pytest.raises(OSError):
                path.rename(path.with_suffix('.replaced'))


def test_reuse_needs_only_manifest_headroom_but_new_copy_keeps_its_bound(owned):
    storage = manager(owned)
    item = original(storage, b'x' * 131072)
    with pytest.raises(RuntimeRefused, match='RECOVERY_BOUND_EXCEEDED'):
        copies(storage, grant(storage, 1024**2), [item])
    saved = copies(storage, grant(storage), [item])
    assert copies(storage, grant(storage, 1024**2), [item]) == saved


def test_deadline_refusal_retains_existing_backup(owned):
    storage = manager(owned)
    item = original(storage)
    saved = copies(storage, grant(storage), [item])[0]
    def expired():
        raise RuntimeRefused('RECOVERY_BARRIER_TIMEOUT')
    with pytest.raises(RuntimeRefused, match='RECOVERY_BARRIER_TIMEOUT'):
        copies(storage, grant(storage), [item], check=expired)
    assert (storage.root / saved['path']).exists()


def test_old_recovery_layout_remains_valid_without_rewriting_it(owned):
    from copy import deepcopy
    from test_recovery_snapshot_closure import prepared
    from compertum.data.encoding import canonical
    from compertum.recovery import validate_recovery_set
    seals, _, item, collected = prepared(owned)
    storage = seals.test_storage
    before = Path(collected['manifest_path']).read_bytes()
    legacy = deepcopy(collected['manifest'])
    parent = grant(storage)
    raw = (storage.root / item['path']).read_bytes()
    child = storage.split_grant(parent, max(1, len(raw)))
    path = f"backups/{parent.task_id}/{uuid4()}/blobs/{item['artifact_id']}.bin"
    writer = storage.open_artifact(child, path)
    try:
        writer.write(raw)
        writer.publish()
    finally:
        writer.close()
    next(a for a in legacy['artifacts'] if a['artifact_id'] == item['artifact_id'])['path'] = path
    saved = storage.root / 'legacy-manifest.json'
    saved.write_bytes(canonical(legacy))
    assert validate_recovery_set(saved, project_root=storage.root)['status'] == 'VERIFIED'
    assert Path(collected['manifest_path']).read_bytes() == before


def test_two_snapshot_restore_uses_shared_copy_after_original_is_retained(tmp_path):
    import subprocess
    import sys
    from test_recovery_snapshot_closure import invoke
    helper = Path(__file__).parent / 'helpers/shared_backup_fixture.py'
    env = {k: v for k, v in os.environ.items() if k.upper() in
           {'SYSTEMROOT', 'WINDIR', 'PYTHONPATH', 'PYTHONDONTWRITEBYTECODE', 'TEMP', 'TMP'}}
    result = subprocess.run([sys.executable, '-B', str(helper), str(tmp_path)],
                            env=env, capture_output=True, text=True, timeout=40)
    assert result.returncode == 0, result.stderr
    saved = json.loads(result.stdout)
    assert saved['first_copy'] == saved['second_copy'] and saved['copy_count'] == 1
    restored = invoke(tmp_path, 'restore', saved['first_manifest'])
    assert restored['status'] == 'RESTORED' and restored['admission'] == 'HALTED'
    assert hashlib.sha256((tmp_path / saved['artifact']['path']).read_bytes()).hexdigest() == saved['artifact']['sha256']
    assert Path(saved['retained_original']).exists()
    collected = subprocess.run([sys.executable, '-B', str(helper), str(tmp_path), 'collect', json.dumps(saved['artifact'])],
                              env=env, capture_output=True, text=True, timeout=40)
    assert collected.returncode == 0, collected.stderr
    again = json.loads(collected.stdout)
    assert again['second_copy'] == saved['first_copy'] and again['copy_count'] == 1
    for path, pin in saved['manifest_hashes'].items():
        assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == pin
