"""Real inherited-handle fixtures. Skips never qualify native bootstrap."""
from dataclasses import asdict
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from uuid import uuid4
import pytest
from fixture_processes import python_process
from fixture_files import publish_gate

pytestmark = pytest.mark.skipif(os.name != "nt", reason="NATIVE_WINDOWS_UNAVAILABLE")
ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def owners():
    from compertum.runtime.identity import resolve_project
    from compertum.runtime.owners import acquire_owner, release_owner
    from compertum.runtime.ipc import start_role_pipe
    root = ROOT / ".cache/test-runs" / ("native-bootstrap-" + str(uuid4()))
    root.mkdir(parents=True)
    project = resolve_project(root)
    supervisor = acquire_owner(project, "supervisor")
    target = acquire_owner(project, "coordinator")
    endpoint = start_role_pipe(target, frozenset({"status", "resume_research", "pause_research"}))
    try: yield root, project, supervisor, target, endpoint
    finally:
        from compertum.runtime.owners import _LEASES
        for lease in (target, supervisor):
            if lease in _LEASES: release_owner(lease)


def launch(state, mode="normal", *, deliver=True):
    from compertum.runtime.bootstrap import prepare_bootstrap
    from compertum.runtime.owners import _LEASES
    root, _, supervisor, _, ep = state
    offer = prepare_bootstrap(supervisor, ep, role="watchdog", generation=1, commands=frozenset({"status"}))
    gate = root / (str(uuid4()) + ".go")
    public = root / (str(uuid4()) + ".json")
    public.write_text(json.dumps({"supervisor": asdict(offer.registration), "gate": str(gate), "mode": mode,
                                  "ready": str(gate) + ".ready", "received": str(gate) + ".received"}))
    env = {k: v for k, v in os.environ.items() if k.upper() in {"SYSTEMROOT", "WINDIR"}}
    env["PYTHONPATH"] = str(ROOT / "src"); env["PYTHONDONTWRITEBYTECODE"] = "1"
    with offer.inheritance() as handle:
        assert offer.api.handle_flags(offer.client) & 1
        assert not offer.api.handle_flags(offer.server) & 1
        assert not _LEASES[supervisor].api.handle_flags(_LEASES[supervisor].lock) & 1
        startup = subprocess.STARTUPINFO()
        startup.lpAttributeList = {"handle_list": [handle]}
        proc = python_process(["-B", str(ROOT / "tests/helpers/bootstrap_child.py"), str(handle), str(public)],
            cwd=ROOT, env=env, close_fds=True, startupinfo=startup,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        if not deliver: return proc, offer, gate
        child = offer.deliver(int(proc._handle))
        assert offer.client.closed and offer.server.closed
        secret = offer.enrollment.capability.secret
        if secret in public.read_text() or secret in repr(offer) or any(secret in str(part) for part in proc.args):
            from compertum.runtime.errors import RuntimeRefused
            raise RuntimeRefused("FIXTURE_CAPABILITY_EXPOSURE")
        assert child.identity.pid == proc.pid
        return proc, offer, gate
    except BaseException:
        proc.terminate(); proc.wait(timeout=3); offer.close(); raise


def finish(proc):
    try: out, err = proc.communicate(timeout=8)
    except subprocess.TimeoutExpired:
        proc.terminate(); proc.communicate(timeout=3)
        pytest.fail("bootstrap child exceeded fixture bound")
    assert not err
    return proc.returncode, json.loads(out)


def test_private_inherited_capability_authenticates_only_the_registered_native_child(owners):
    proc, offer, gate = launch(owners)
    publish_gate(gate, {})
    result = owners[-1].inspect_once(timeout=5)
    code, reply = finish(proc)
    assert code == 0 and reply["status"] == "PROTOCOL_VALIDATED_ONLY"
    assert reply["request_id"] == result.request_id and not result.can_dispatch
    offer.close()


@pytest.mark.parametrize("mode,reason", [("wrong_role", "ROLE_DENIED"), ("wrong_generation", "ROLE_DENIED"),
    ("wrong_instance", "ROLE_DENIED"), ("wrong_secret", "CAPABILITY_DENIED"), ("operator", "ROLE_DENIED")])
def test_worker_cannot_change_role_generation_instance_secret_or_claim_operator(owners, mode, reason):
    from compertum.runtime.errors import RuntimeRefused
    proc, _, gate = launch(owners, mode)
    publish_gate(gate, {})
    with pytest.raises(RuntimeRefused, match=reason): owners[-1].inspect_once(timeout=5)
    code, reply = finish(proc)
    assert code == 3 and not reply["can_dispatch"]


def test_supervisor_release_revokes_worker_without_operator_fallback(owners):
    from compertum.runtime.owners import release_owner
    from compertum.runtime.errors import RuntimeRefused
    proc, offer, gate = launch(owners, "operator")
    release_owner(owners[2])
    assert offer.closed and not offer.enrollment.active and offer.enrollment.process.closed
    publish_gate(gate, {})
    with pytest.raises(RuntimeRefused, match="CAPABILITY_DENIED"): owners[-1].inspect_once(timeout=5)
    assert finish(proc)[0] == 3


def test_enrolled_worker_cannot_claim_operator_at_second_owner_endpoint(owners):
    from compertum.runtime.ipc import start_role_pipe
    from compertum.runtime.errors import RuntimeRefused
    second = start_role_pipe(owners[2], frozenset({"resume_research"}))
    proc, _, gate = launch(owners, "operator")
    publish_gate(gate, {"target": asdict(second.descriptor.registration)})
    with pytest.raises(RuntimeRefused, match="ROLE_DENIED"): second.inspect_once(timeout=5)
    assert finish(proc)[0] == 3


def test_target_release_retires_the_bootstrap_and_old_transport(owners):
    from compertum.runtime.owners import release_owner
    from compertum.runtime.errors import RuntimeRefused
    proc, offer, gate = launch(owners, "raw")
    release_owner(owners[3])
    assert owners[-1].closed and offer.closed and not offer.enrollment.active
    publish_gate(gate, {})
    with pytest.raises(RuntimeRefused, match="OWNER_UNVERIFIED"): owners[-1].inspect_once(timeout=5)
    assert finish(proc)[0] == 3


def test_parent_handle_cannot_be_bound_as_its_own_child(owners):
    from compertum.runtime.bootstrap import prepare_bootstrap
    from compertum.runtime.errors import RuntimeRefused
    offer = prepare_bootstrap(owners[2], owners[-1], role="watchdog", generation=1, commands=frozenset({"status"}))
    with offer.inheritance(): pass  # no child launched; closes the parent client copy
    with offer.api.open_process(os.getpid()) as own:
        with pytest.raises(RuntimeRefused, match="PEER_MISMATCH"): offer.deliver(own.get())
    assert offer.closed and not owners[-1]._workers


def wait_marker(path, proc):
    end = time.monotonic() + 5
    while not path.exists():
        if proc.poll() is not None or time.monotonic() >= end: pytest.fail("bootstrap fault fixture never reached expected phase")
        time.sleep(.01)


@pytest.mark.parametrize("mode,reason", [("bootstrap_bad_ack", "BOOTSTRAP_ACK_DENIED"),
                                       ("bootstrap_no_ack", "PIPE_DEADLINE_EXCEEDED")])
def test_bad_or_missing_bootstrap_ack_revokes_native_enrollment(owners, mode, reason):
    from compertum.runtime.errors import RuntimeRefused
    proc, offer, gate = launch(owners, mode, deliver=False)
    try:
        wait_marker(Path(str(gate) + ".ready"), proc)
        with pytest.raises(RuntimeRefused, match=reason): offer.deliver(int(proc._handle), timeout=.5)
        assert Path(str(gate) + ".received").exists()
        assert offer.closed and not offer.enrollment.active and offer.enrollment.process.closed
    finally: publish_gate(gate, {}); finish(proc)


def test_live_sibling_handle_cannot_assign_its_capability_to_the_actual_recipient(owners):
    from compertum.runtime.errors import RuntimeRefused
    proc, offer, gate = launch(owners, deliver=False)
    other = python_process(["-B", "-c", "import time; time.sleep(8)"],
        env={k: v for k, v in os.environ.items() if k.upper() in {"SYSTEMROOT", "WINDIR"}})
    try:
        with pytest.raises(RuntimeRefused): offer.deliver(int(other._handle))
        assert other.poll() is None  # wrong live sibling, not a dead-handle rejection
        assert finish(proc) == (3, {"status": "PEER_MISMATCH", "can_dispatch": False})
        assert offer.closed and not offer.enrollment.active and offer.enrollment.process.closed
    finally:
        if proc.poll() is None: proc.terminate(); proc.communicate(timeout=3)
        other.terminate(); other.wait(timeout=3)


def test_interruption_after_real_pending_inherited_read_revokes_enrollment(owners, monkeypatch):
    import ctypes as c
    from compertum.runtime import _pipes
    proc, offer, gate = launch(owners, "bootstrap_no_ack", deliver=False)
    pending = []; native = offer.api.ReadFile
    def read(*args):
        wait_marker(Path(str(gate) + ".received"), proc)
        ok = native(*args); error = c.get_last_error()
        if not ok and error == 997: pending.append(True); raise KeyboardInterrupt()
        c.set_last_error(error); return ok
    try:
        wait_marker(Path(str(gate) + ".ready"), proc)
        with monkeypatch.context() as patch:
            patch.setattr(offer.api, "ReadFile", read)
            with pytest.raises(KeyboardInterrupt): offer.deliver(int(proc._handle))
        assert pending and offer.closed and not offer.enrollment.active and offer.enrollment.process.closed
        assert not _pipes._INFLIGHT and not _pipes._UNCERTAIN
        _pipes.NativePipeAPI()  # native transport gate remains admissible after observed cancellation
    finally: publish_gate(gate, {}); finish(proc)
