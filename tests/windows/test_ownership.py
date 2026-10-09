"""Actual Win32 fixtures. Skips never count toward native qualification."""
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid
import pytest
from fixture_processes import python_process

pytestmark = pytest.mark.skipif(os.name != "nt", reason="NATIVE_WINDOWS_UNAVAILABLE")
SOURCE_ROOT = Path(__file__).resolve().parents[2]


def test_fixture_process_handle_names_the_interpreter_and_preserves_qualified_environment():
    env = {k: v for k, v in os.environ.items() if k.upper() in {"SYSTEMROOT", "WINDIR"}}
    code = ("import json, os, sys, jsonschema; "
            "print(json.dumps({'pid': os.getpid(), 'prefix': sys.prefix, "
            "'executable': sys.executable, 'version': list(sys.version_info[:3])}))")
    proc = python_process(["-B", "-c", code], env=env,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try: out, err = proc.communicate(timeout=8)
    except subprocess.TimeoutExpired:
        proc.terminate(); proc.communicate(timeout=3)
        pytest.fail("fixture interpreter exceeded its exit bound")
    assert proc.returncode == 0 and not err
    observed = json.loads(out)
    assert observed["pid"] == proc.pid
    assert Path(observed["prefix"]).resolve() == Path(sys.prefix).resolve()
    assert Path(observed["executable"]).resolve() == Path(sys.executable).resolve()
    assert observed["version"] == list(sys.version_info[:3])


@pytest.fixture
def fixture_root():
    root = SOURCE_ROOT / ".cache" / "test-runs" / f"native-owner-{uuid.uuid4()}"
    root.mkdir(parents=True)
    project = root / "project"; project.mkdir()
    return root, project


def child(root, project, suffix, *flags):
    allowed = {"SYSTEMROOT", "WINDIR", "TEMP", "TMP", "USERPROFILE", "PATH"}
    env = {k: v for k, v in os.environ.items() if k.upper() in allowed}
    env["PYTHONPATH"] = str(SOURCE_ROOT / "src"); env["PYTHONDONTWRITEBYTECODE"] = "1"
    proc = python_process(["-B", str(SOURCE_ROOT / "tests/helpers/role_holder.py"),
        "--root", str(project), "--barrier", str(root / "barrier"), "--stop", str(root / f"stop-{suffix}"), *flags],
        cwd=SOURCE_ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return proc


def stop(root, proc, suffix):
    (root / f"stop-{suffix}").touch()
    try: return proc.communicate(timeout=8)
    except subprocess.TimeoutExpired:
        proc.terminate(); return proc.communicate(timeout=5)


def test_canonical_root_uses_native_volume_and_file_identity(fixture_root):
    from compertum.runtime.identity import resolve_project
    _, project = fixture_root
    a = resolve_project(project); b = resolve_project(Path(str(project).upper()))
    assert a.project_id == b.project_id
    assert len(a.root_file_id) == 32 and a.operator_sid.startswith("S-1-")


def test_two_synchronized_starts_have_exactly_one_owner(fixture_root):
    root, project = fixture_root
    a = child(root, project, "a"); b = child(root, project, "b")
    try:
        (root / "barrier").touch()
        outputs = [json.loads(a.stdout.readline()), json.loads(b.stdout.readline())]
        assert sorted(x["status"] for x in outputs) == ["HELD", "OWNER_BUSY"]
        metadata = json.loads((project / "state/locks/execution.json").read_text())
        winner = next(x for x in outputs if x["status"] == "HELD")
        assert metadata["identity"]["pid"] == winner["pid"]
    finally: stop(root, a, "a"); stop(root, b, "b")


@pytest.mark.parametrize("flag,want", [("--dead-thread", "HELD"), ("--release-live", "RELEASED_LIVE")])
def test_live_process_cannot_be_replaced_after_thread_or_handle_release(fixture_root, flag, want):
    from compertum.runtime.identity import resolve_project
    from compertum.runtime.owners import acquire_owner
    from compertum.runtime.errors import RuntimeRefused
    root, project = fixture_root; proc = child(root, project, "a", flag)
    try:
        (root / "barrier").touch(); assert json.loads(proc.stdout.readline())["status"] == want
        with pytest.raises(RuntimeRefused, match="OWNER_BUSY"):
            acquire_owner(resolve_project(project), "execution")
    finally: stop(root, proc, "a")


def test_prior_process_reclaimed_after_parent_handle_close_allows_one_replacement(fixture_root):
    from compertum.runtime.identity import resolve_project
    from compertum.runtime.owners import acquire_owner, require_live_owner, release_owner
    root, project = fixture_root; proc = child(root, project, "a")
    (root / "barrier").touch(); first = json.loads(proc.stdout.readline())
    stop(root, proc, "a"); assert proc.returncode == 0
    proc._handle.Close()  # Release the parent's retained Windows process object.
    lease = acquire_owner(resolve_project(project), "execution")
    try:
        assert lease.generation == first["generation"] + 1
        assert lease.identity.creation_filetime != first["creation_filetime"]
        require_live_owner(lease, "execution")
    finally: release_owner(lease)


def test_lock_handle_is_not_inherited_and_lost_handle_invalidates_authority(fixture_root):
    from compertum.runtime.identity import resolve_project
    from compertum.runtime.owners import acquire_owner, owner_handle_flags, require_live_owner, release_owner
    from compertum.runtime.errors import RuntimeRefused
    _, project = fixture_root; lease = acquire_owner(resolve_project(project), "coordinator")
    assert owner_handle_flags(lease) & 1 == 0
    release_owner(lease)
    with pytest.raises(RuntimeRefused, match="OWNER_UNVERIFIED"): require_live_owner(lease)


def test_external_lock_close_revokes_authority_and_disposes_remaining_handles(fixture_root):
    from compertum.runtime.identity import resolve_project
    from compertum.runtime import owners
    from compertum.runtime.errors import RuntimeRefused
    _, project = fixture_root
    lease = owners.acquire_owner(resolve_project(project), "coordinator")
    state = owners._LEASES[lease]  # Fixture-only observation, never fabricated authority.
    state.api.checked(state.api.CloseHandle(state.lock.get()), "CloseHandle")
    with pytest.raises(RuntimeRefused, match="OWNER_UNVERIFIED"): owners.require_live_owner(lease)
    assert lease not in owners._LEASES
    assert all(h.closed for h in state.directories)
    assert state.cleanup_unverified is True


def test_root_junction_alias_cannot_create_a_second_owner(fixture_root):
    from compertum.runtime.identity import resolve_project
    from compertum.runtime.owners import acquire_owner, release_owner
    from compertum.runtime.errors import RuntimeRefused
    root, project = fixture_root; alias = root / "alias"
    made = subprocess.run(["cmd", "/d", "/c", "mklink", "/J", str(alias), str(project)], capture_output=True, timeout=5)
    if made.returncode: pytest.skip("JUNCTION_FIXTURE_UNAVAILABLE; native requirement remains unverified")
    a = resolve_project(project); b = resolve_project(alias); assert a.project_id == b.project_id
    lease = acquire_owner(a, "coordinator")
    try:
        with pytest.raises(RuntimeRefused, match="OWNER_BUSY"): acquire_owner(b, "coordinator")
    finally: release_owner(lease)


def test_reparse_state_directory_cannot_redirect_owner_files(fixture_root):
    from compertum.runtime.identity import resolve_project
    from compertum.runtime.owners import acquire_owner
    from compertum.runtime.errors import RuntimeRefused
    root, project = fixture_root; outside = root / "outside"; outside.mkdir()
    made = subprocess.run(["cmd", "/d", "/c", "mklink", "/J", str(project / "state"), str(outside)], capture_output=True, timeout=5)
    if made.returncode: pytest.skip("JUNCTION_FIXTURE_UNAVAILABLE; native requirement remains unverified")
    with pytest.raises(RuntimeRefused, match="REPARSE_DENIED"): acquire_owner(resolve_project(project), "coordinator")
    assert list(outside.iterdir()) == []


def test_proved_dead_owner_with_published_endpoint_is_replaced_once(fixture_root):
    from compertum.runtime.identity import resolve_project
    from compertum.runtime.owners import acquire_owner, release_owner
    from compertum.runtime.ipc import start_role_pipe
    from compertum.runtime.errors import RuntimeRefused
    root, project = fixture_root; proc = child(root, project, "published", "--publish-pipe")
    try:
        (root / "barrier").touch(); first = json.loads(proc.stdout.readline())
        old = json.loads((project / "state/locks/execution.json").read_text())
        assert old["endpoint"] and old["identity"]["pid"] == proc.pid
        with pytest.raises(RuntimeRefused, match="OWNER_BUSY"):
            acquire_owner(resolve_project(project), "execution")
    finally: stop(root, proc, "published")
    assert proc.returncode == 0; proc._handle.Close()
    lease = acquire_owner(resolve_project(project), "execution")
    try:
        endpoint = start_role_pipe(lease, frozenset({"status"}))
        new = json.loads((project / "state/locks/execution.json").read_text())
        assert lease.generation == first["generation"] + 1
        assert new["endpoint"] != old["endpoint"] and new["identity"] != old["identity"]
        with pytest.raises(RuntimeRefused, match="OWNER_BUSY"):
            acquire_owner(resolve_project(project), "execution")
    finally: release_owner(lease)
    assert endpoint.closed
