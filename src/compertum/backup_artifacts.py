"""Share verified copies of unchanged artifacts across recovery sets."""
from contextlib import ExitStack, contextmanager
import hashlib
import json

from .clean_registration import _text
from .events import canonical, uuid
from .persistence import checked_path
from .runtime.errors import RuntimeRefused


def _require(value):
    if not value:
        raise RuntimeRefused('RECOVERY_ARTIFACT_INVALID')


@contextmanager
def _locked_payload(manager, api, relative, item, check):
    """Keep path and byte identities fixed through manifest publication."""
    path = checked_path(manager.root, manager.root / relative)
    with ExitStack() as locks:
        current = manager.root
        locks.enter_context(api.open_directory(current))
        for part in path.parent.relative_to(manager.root).parts:
            current = current / part
            locks.enter_context(api.open_directory(current))
        handle = locks.enter_context(api.open_file(path, 0x80000080, 1))
        before = api.file_info(handle)
        _require(before.links == 1 and not before.attributes & 0x410)
        _require((before.size_hi << 32) | before.size_lo == item['size_bytes'])
        identity = api.file_identity(handle)
        digest = hashlib.sha256()
        with path.open('rb') as stream:
            remaining = item['size_bytes']
            while remaining:
                check()
                chunk = stream.read(min(8 * 1024**2, remaining))
                _require(chunk)
                digest.update(chunk)
                remaining -= len(chunk)
            _require(not stream.read(1))
        check()
        _require(digest.hexdigest() == item['sha256'])
        _require(api.file_identity(handle) == identity)
        yield path, identity


def _existing_copy(manager, item):
    suffix = f"/shared/{item['artifact_id']}-{item['sha256']}.bin"
    row = manager.store.conn.execute(
        'SELECT ' + _text('task', 36) + ',' + _text('path', 1024) +
        ',written,maximum,' + _text('manifest', 4096) +
        " FROM reservations WHERE category='backups' AND status='PUBLISHED'"
        ' AND substr(path,-?)=? ORDER BY id LIMIT 1', (len(suffix), suffix)).fetchone()
    if row is None:
        return None
    task, path, written, maximum, raw = row
    _require(type(task) is str and type(raw) is str)
    uuid(task)
    _require(path == f'backups/{task}' + suffix)
    _require(written == item['size_bytes'] and maximum == max(1, written))
    try:
        saved = json.loads(raw)
    except (ValueError, TypeError):
        raise RuntimeRefused('RECOVERY_ARTIFACT_INVALID') from None
    _require(type(saved) is dict and set(saved) == {'artifact_id', 'task_id', 'path', 'size_bytes', 'sha256'})
    uuid(saved['artifact_id'])
    _require(saved == dict(artifact_id=saved['artifact_id'], task_id=task, path=path,
                          size_bytes=item['size_bytes'], sha256=item['sha256']))
    _require(canonical(saved).decode() == raw)
    return path


@contextmanager
def shared_backup_artifacts(manager, grant, artifacts, *, check):
    """Copy new bytes through storage grants; pin every reused backup file.

    Distinct artifact identities keep distinct paths, even when their bytes match.
    Old recovery sets and unregistered files are never changed or adopted.
    """
    from .storage import owner_of_grant
    _require(owner_of_grant(grant) is manager and grant.category == 'backups')
    with manager.store._live() as guard, ExitStack() as locks:
        planned = []
        for item in artifacts:
            check()
            uuid(item['artifact_id'])
            _require(type(item['sha256']) is str and len(item['sha256']) == 64 and
                     all(c in '0123456789abcdef' for c in item['sha256']))
            _require(type(item['size_bytes']) is int and item['size_bytes'] >= 0)
            source, identity = locks.enter_context(
                _locked_payload(manager, guard.api, item['path'], item, check))
            existing = _existing_copy(manager, item)
            if existing is not None:
                _, backup_identity = locks.enter_context(
                    _locked_payload(manager, guard.api, existing, item, check))
                _require(identity != backup_identity)
            planned.append((item, source, existing))
        remaining = manager.store.conn.execute(
            'SELECT maximum-written FROM reservations WHERE id=?', (grant.grant_id,)).fetchone()[0]
        required = sum(max(1, item['size_bytes']) for item, _, existing in planned if existing is None)
        if required + 1024**2 > remaining:
            raise RuntimeRefused('RECOVERY_BOUND_EXCEEDED')
        result = []
        for item, source, existing in planned:
            if existing is None:
                child = manager.split_grant(grant, max(1, item['size_bytes']))
                relative = f"backups/{grant.task_id}/shared/{item['artifact_id']}-{item['sha256']}.bin"
                writer = manager.open_artifact(child, relative)
                try:
                    with source.open('rb') as stream:
                        while chunk := stream.read(8 * 1024**2):
                            check()
                            writer.write(chunk)
                    copied = writer.publish(before_publish=check)
                finally:
                    writer.close()
                _require(copied['sha256'] == item['sha256'] and copied['size_bytes'] == item['size_bytes'])
                existing = copied['path']
                locks.enter_context(_locked_payload(manager, guard.api, existing, item, check))
            result.append({**item, 'path': existing})
        check()
        yield result
