from contextlib import contextmanager
from dataclasses import dataclass, asdict, field
import hashlib
import json
import os
from pathlib import Path
import re
import threading
from uuid import uuid4
from compertum.domain import ProcessIdentity, OwnerLease
from .errors import RuntimeRefused
from .identity import ProjectIdentity, resolve_project
from ._windows import WindowsAPI, NativeCallError

ROLES = frozenset({"supervisor", "coordinator", "evaluation", "execution", "watchdog", "recovery"})
_MUTEX = threading.RLock()
_LEASES = {}
_EXCLUSIVES = {}


@dataclass(frozen=True)
class ProcessProbe:
    creation_filetime: int | None = None
    wait_result: int | None = None
    open_error: int | None = None
    snapshot_pids: frozenset[int] | None = None


def classify_prior_exit(previous: ProcessIdentity, probe: ProcessProbe) -> str:
    """Pure decision over supplied observations; never native authority."""
    if not isinstance(previous, ProcessIdentity) or not isinstance(probe, ProcessProbe): return "UNVERIFIED"
    if probe.open_error is not None:
        if probe.creation_filetime is not None or probe.wait_result is not None: return "UNVERIFIED"
        if probe.open_error == 87 and probe.snapshot_pids is not None and previous.pid not in probe.snapshot_pids:
            return "VERIFIED_ABSENT"
        return "UNVERIFIED"
    if type(probe.creation_filetime) is not int or probe.creation_filetime <= 0: return "UNVERIFIED"
    if probe.creation_filetime != previous.creation_filetime: return "VERIFIED_PID_REUSED"
    if probe.wait_result == 0: return "VERIFIED_EXIT"
    if probe.wait_result == 258: return "LIVE_MATCH"
    return "UNVERIFIED"


def require_live_owner(lease, role=None):
    with _MUTEX:
        state = _LEASES.get(lease) if isinstance(lease, OwnerLease) else None
        if state is None or state.closed or state.pid != os.getpid(): raise RuntimeRefused("OWNER_UNVERIFIED")
        if role is not None and role != lease.identity.role: raise RuntimeRefused("WRONG_OWNER_ROLE")
        try:
            _validate_guard(state)
            with state.api.open_process(os.getpid()) as h:
                if state.api.creation_time(h) != lease.identity.creation_filetime:
                    raise RuntimeRefused("OWNER_UNVERIFIED")
            actual = state.api.read_regular(state.metadata)
            if actual != state.metadata_bytes: raise RuntimeRefused("OWNER_UNVERIFIED")
        except RuntimeRefused:
            state.closed = True
            _LEASES.pop(lease, None)
            try: _dispose_guard(state)
            except RuntimeRefused: pass  # Authority remains revoked even if cleanup is uncertain.
            raise RuntimeRefused("OWNER_UNVERIFIED") from None
        return lease


def verify_prior_exit(previous, *, exclusive=None):
    with _MUTEX:
        if exclusive is None or _EXCLUSIVES.get(id(exclusive)) is not exclusive:
            raise RuntimeRefused("EXCLUSIVE_CONTEXT_REQUIRED")
        _validate_guard(exclusive)
        if previous.role != exclusive.role or previous.operator_sid != exclusive.project.operator_sid:
            raise RuntimeRefused("OWNER_UNVERIFIED")
        api = exclusive.api
        try:
            with api.open_process(previous.pid) as h:
                probe = ProcessProbe(creation_filetime=api.creation_time(h), wait_result=api.WaitForSingleObject(h.get(), 0))
        except NativeCallError as e:
            if e.operation != "OpenProcess" or e.winerror != 87:
                raise RuntimeRefused("OWNER_UNVERIFIED") from None
            probe = ProcessProbe(open_error=87, snapshot_pids=api.process_snapshot())
        result = classify_prior_exit(previous, probe)
        if result == "LIVE_MATCH": raise RuntimeRefused("OWNER_BUSY")
        if result == "UNVERIFIED": raise RuntimeRefused("OWNER_UNVERIFIED")
        return ExitEvidence(result, previous.process_instance_id, previous.pid, previous.creation_filetime)


@dataclass(frozen=True)
class ExitEvidence:
    status: str
    process_instance_id: str
    pid: int
    creation_filetime: int


@dataclass
class _Exclusive:
    api: object
    project: ProjectIdentity
    role: str
    pid: int
    directories: list
    lock: object
    metadata: Path
    lock_identity: tuple
    directory_identities: list
    metadata_bytes: bytes = b""
    closed: bool = False
    cleanup_unverified: bool = False
    resources: list = field(default_factory=list)


def _close_handles(handles):
    failed = False
    for handle in handles:
        try: handle.close()
        except Exception: failed = True
    if failed: raise RuntimeRefused("OWNER_CLEANUP_UNVERIFIED")


def _dispose_guard(state):
    """Revoke before disposal; never close an observed foreign handle value."""
    state.closed = True
    failed = False
    # Transports/capabilities lose authority before any owner lock is released.
    for resource in reversed(getattr(state, "resources", [])):
        try: resource.close()
        except Exception: failed = True
    resources = [(state.lock, state.lock_identity), *reversed(list(zip(state.directories, state.directory_identities)))]
    for handle, expected in resources:
        if handle.closed: continue
        try:
            if state.api.file_identity(handle) != expected:
                raise RuntimeRefused("HANDLE_IDENTITY_CHANGED")
        except Exception:
            # An externally closed/reused numeric value is no longer ours.
            handle.closed = True
            failed = True
            continue
        try: handle.close()
        except Exception: failed = True
    state.cleanup_unverified = failed
    if failed: raise RuntimeRefused("OWNER_CLEANUP_UNVERIFIED")


def _validate_guard(state):
    if state.closed or state.pid != os.getpid(): raise RuntimeRefused("OWNER_UNVERIFIED")
    if state.api.handle_flags(state.lock) & 1: raise RuntimeRefused("OWNER_UNVERIFIED")
    info = state.api.file_info(state.lock)
    if info.attributes & (0x400 | 0x10) or info.links != 1: raise RuntimeRefused("OWNER_UNVERIFIED")
    if state.api.file_identity(state.lock) != state.lock_identity: raise RuntimeRefused("OWNER_UNVERIFIED")
    volume, file_id = state.api.file_identity(state.directories[0])
    if (volume, file_id) != (state.project.volume_serial, state.project.root_file_id):
        raise RuntimeRefused("ROOT_IDENTITY_CHANGED")


def _metadata(raw, project, role):
    def pairs(values):
        result = {}
        for key, value in values:
            if key in result: raise ValueError("duplicate")
            result[key] = value
        return result
    try:
        p = json.loads(raw, object_pairs_hook=pairs, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        if (set(p) != {"schema_version", "project_id", "role", "generation", "identity", "endpoint", "code_hash"}
                or type(p["schema_version"]) is not int or p["schema_version"] != 1 or p["project_id"] != project.project_id
                or p["role"] != role or type(p["generation"]) is not int or not 1 <= p["generation"] < 2**63 - 1
                or (p["endpoint"] is not None and p["endpoint"] != _endpoint_name(p))
                or not isinstance(p["code_hash"], str)
                or not re.fullmatch(r"[0-9a-f]{64}", p["code_hash"])):
            raise ValueError("invalid")
        identity = ProcessIdentity(**p["identity"])
        if identity.role != role or identity.operator_sid != project.operator_sid: raise ValueError("wrong identity")
        return p["generation"], identity
    except (ValueError, TypeError, KeyError, RecursionError, RuntimeError):
        raise RuntimeRefused("OWNER_METADATA_UNVERIFIED") from None


def _code_hash():
    h = hashlib.sha256()
    for name in ("__init__.py", "errors.py", "_windows.py", "_pipes.py", "identity.py", "owners.py", "ipc.py", "bootstrap.py", "owner_channel.py"):
        with Path(__file__).with_name(name).open("rb") as source: data = source.read(512 * 1024 + 1)
        if len(data) > 512 * 1024: raise RuntimeRefused("CODE_HASH_UNVERIFIED")
        h.update(name.encode() + b"\0" + data)
    return h.hexdigest()


def _endpoint_name(metadata):
    return ("\\\\.\\pipe\\compertum-" + metadata["project_id"] + "-" + metadata["role"]
            + "-" + metadata["identity"]["process_instance_id"] + "-" + str(metadata["generation"]))


@contextmanager
def _owner_scope(lease):
    # One lock order: owner registry then endpoint. Release waits for the bounded
    # exchange, preventing teardown racing an overlapped native operation.
    with _MUTEX:
        require_live_owner(lease)
        yield _LEASES[lease]
        require_live_owner(lease)


def _attach_endpoint(lease, resource, name):
    with _owner_scope(lease) as state:
        payload = json.loads(state.metadata_bytes)
        if payload["endpoint"] is not None or name != _endpoint_name(payload):
            raise RuntimeRefused("ENDPOINT_UNVERIFIED")
        state.resources.append(resource)
        payload["endpoint"] = name
        updated = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        state.api.publish_metadata(state.metadata, updated)
        state.metadata_bytes = updated


def acquire_owner(project: ProjectIdentity, role: str) -> OwnerLease:
    api = WindowsAPI()
    if not isinstance(project, ProjectIdentity) or role not in ROLES: raise RuntimeRefused("INVALID_OWNER_REQUEST")
    actual = resolve_project(project.root_path)
    if actual != project: raise RuntimeRefused("ROOT_IDENTITY_CHANGED")
    with _MUTEX:
        directories = []; lock = None; guard = None
        try:
            directories.append(api.open_directory(actual.root_path))
            for name in ("state", "locks"):
                path = actual.root_path / "state" if name == "state" else actual.root_path / "state/locks"
                try: path.mkdir()
                except FileExistsError: pass
                directories.append(api.open_directory(path))
            lock_path = actual.root_path / "state/locks" / (role + ".lock")
            try: lock = api.open_file(lock_path, 0xC0000000, 0, disposition=4)
            except NativeCallError as e:
                if e.winerror in (32, 33): raise RuntimeRefused("OWNER_BUSY") from None
                raise RuntimeRefused("OWNER_UNVERIFIED") from None
            guard = _Exclusive(api, actual, role, os.getpid(), directories, lock,
                               lock_path.with_suffix(".json"), api.file_identity(lock),
                               [api.file_identity(h) for h in directories])
            _EXCLUSIVES[id(guard)] = guard; _validate_guard(guard)
            previous = None
            try: previous = api.read_regular(guard.metadata)
            except NativeCallError as e:
                if e.winerror != 2 or not lock.created: raise RuntimeRefused("OWNER_UNVERIFIED") from None
            generation = 1
            if previous is not None:
                generation, prior = _metadata(previous, actual, role)
                verify_prior_exit(prior, exclusive=guard); generation += 1
            with api.open_process(os.getpid()) as process:
                sid, logon = api.token_sids(process)
                if (sid, logon) != (actual.operator_sid, actual.logon_sid): raise RuntimeRefused("OWNER_UNVERIFIED")
                identity = ProcessIdentity(str(uuid4()), os.getpid(), api.creation_time(process), sid, role)
            payload = {"schema_version": 1, "project_id": actual.project_id, "role": role, "generation": generation,
                       "identity": asdict(identity), "endpoint": None, "code_hash": _code_hash()}
            guard.metadata_bytes = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
            api.publish_metadata(guard.metadata, guard.metadata_bytes)
            lease = OwnerLease(actual.project_id, generation, identity, guard)
            _LEASES[lease] = guard
            return lease
        except BaseException as error:
            try:
                if guard is not None: _dispose_guard(guard)
                else: _close_handles(([lock] if lock is not None else []) + list(reversed(directories)))
            except RuntimeRefused:
                error.add_note("Ownership cleanup remains unverified.")
            raise
        finally:
            if guard is not None: _EXCLUSIVES.pop(id(guard), None)


def owner_handle_flags(lease):
    require_live_owner(lease)
    return _LEASES[lease].api.handle_flags(_LEASES[lease].lock)


def release_owner(lease):
    with _MUTEX:
        state = _LEASES.pop(lease, None) if isinstance(lease, OwnerLease) else None
        if state is None or state.closed: raise RuntimeRefused("OWNER_UNVERIFIED")
        state.closed = True
        _dispose_guard(state)
