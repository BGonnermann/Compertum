"""Policy results are decisions, never evidence that a native call happened."""
from pathlib import Path
import os
import uuid
import pytest

from compertum.domain import OwnerLease, ProcessIdentity
from compertum.runtime.errors import RuntimeRefused
from compertum.runtime.identity import resolve_project
from compertum.runtime.owners import ProcessProbe, classify_prior_exit, require_live_owner, verify_prior_exit


PREVIOUS = ProcessIdentity("00000000-0000-4000-8000-000000000001", 321, 100, "S-1-5-21-1", "coordinator")


@pytest.mark.parametrize("probe,want", [
    (ProcessProbe(creation_filetime=100, wait_result=0), "VERIFIED_EXIT"),
    (ProcessProbe(creation_filetime=100, wait_result=258), "LIVE_MATCH"),
    (ProcessProbe(creation_filetime=200, wait_result=258), "VERIFIED_PID_REUSED"),
    (ProcessProbe(creation_filetime=100, wait_result=0xFFFFFFFF), "UNVERIFIED"),
    (ProcessProbe(open_error=5, snapshot_pids=frozenset()), "UNVERIFIED"),
    (ProcessProbe(open_error=87, snapshot_pids=None), "UNVERIFIED"),
    (ProcessProbe(open_error=87, snapshot_pids=frozenset({321})), "UNVERIFIED"),
    (ProcessProbe(open_error=87, snapshot_pids=frozenset({1, 2})), "VERIFIED_ABSENT"),
    (ProcessProbe(open_error=6, snapshot_pids=frozenset()), "UNVERIFIED"),
    (ProcessProbe(creation_filetime=None, wait_result=0), "UNVERIFIED"),
])
def test_prior_exit_does_not_confuse_missing_or_denied_evidence_with_exit(probe, want):
    assert classify_prior_exit(PREVIOUS, probe) == want


def test_shape_only_lease_cannot_authorize_a_writer():
    fake = OwnerLease("a" * 64, 1, PREVIOUS, object())
    with pytest.raises(RuntimeRefused, match="OWNER_UNVERIFIED"):
        require_live_owner(fake)


def test_pid_identity_alone_cannot_verify_takeover():
    with pytest.raises(RuntimeRefused, match="EXCLUSIVE_CONTEXT_REQUIRED"):
        verify_prior_exit(PREVIOUS)


@pytest.mark.skipif(os.name == "nt", reason="non-Windows refusal fixture")
def test_non_windows_identity_refuses_before_any_files_are_created():
    namespace = Path(__file__).resolve().parents[1] / ".cache/test-runs" / f"runtime-policy-{uuid.uuid4()}"
    namespace.mkdir(parents=True)
    absent = namespace / "uncreated-project"
    with pytest.raises(RuntimeRefused, match="NATIVE_WINDOWS_UNAVAILABLE"):
        resolve_project(absent)
    assert not absent.exists()


def test_contradictory_probe_cannot_make_an_exit_claim():
    probe = ProcessProbe(open_error=87, creation_filetime=100, wait_result=0, snapshot_pids=frozenset())
    assert classify_prior_exit(PREVIOUS, probe) == "UNVERIFIED"


@pytest.mark.parametrize("close_failure", [False, True])
def test_authority_loss_revokes_authority_and_attempts_all_handle_cleanup(monkeypatch, close_failure):
    # Lifecycle policy injection only; not evidence of a live Windows handle.
    from types import SimpleNamespace
    from compertum.runtime import owners
    fake = OwnerLease("a" * 64, 1, PREVIOUS, object())
    closed = []
    def handle(name):
        def close():
            closed.append(name)
            if close_failure and name == "lock": raise RuntimeRefused("CLOSE_FAILED")
        return SimpleNamespace(closed=False, close=close)
    lock = handle("lock"); directories = [handle("root"), handle("state"), handle("locks")]
    api = SimpleNamespace(file_identity=lambda h: (1, id(h)))
    state = SimpleNamespace(closed=False, pid=os.getpid(), api=api, lock=lock,
                            lock_identity=(1, id(lock)), directories=directories,
                            directory_identities=[(1, id(h)) for h in directories])
    monkeypatch.setitem(owners._LEASES, fake, state)
    def lost(_): raise RuntimeRefused("HANDLE_CLOSED")
    monkeypatch.setattr(owners, "_validate_guard", lost)
    with pytest.raises(RuntimeRefused, match="OWNER_UNVERIFIED"): owners.require_live_owner(fake)
    assert state.closed is True
    assert fake not in owners._LEASES
    assert closed == ["lock", "locks", "state", "root"]
    with pytest.raises(RuntimeRefused, match="OWNER_UNVERIFIED"): owners.require_live_owner(fake)


def test_cleanup_never_closes_a_reused_handle_for_a_different_file(monkeypatch):
    from types import SimpleNamespace
    from compertum.runtime import owners
    fake = OwnerLease("a" * 64, 1, PREVIOUS, object())
    closed = []
    lock = SimpleNamespace(closed=False, close=lambda: closed.append("foreign-lock"))
    root = SimpleNamespace(closed=False, close=lambda: closed.append("root"))
    api = SimpleNamespace(file_identity=lambda h: (1, "replacement" if h is lock else "root"))
    state = SimpleNamespace(closed=False, pid=os.getpid(), api=api, lock=lock,
                            lock_identity=(1, "original"), directories=[root],
                            directory_identities=[(1, "root")])
    monkeypatch.setitem(owners._LEASES, fake, state)
    def lost(_): raise RuntimeRefused("HANDLE_REUSED")
    monkeypatch.setattr(owners, "_validate_guard", lost)
    with pytest.raises(RuntimeRefused, match="OWNER_UNVERIFIED"): owners.require_live_owner(fake)
    assert closed == ["root"]
    assert lock.closed is True
