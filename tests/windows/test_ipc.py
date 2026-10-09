"""Real Win32 transport fixtures. Unrun/skip is never native acceptance."""
from dataclasses import asdict, replace
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from uuid import uuid4
import pytest

pytestmark = pytest.mark.skipif(os.name != "nt", reason="NATIVE_WINDOWS_UNAVAILABLE")
ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def endpoint():
    from compertum.runtime.identity import resolve_project
    from compertum.runtime.owners import acquire_owner, release_owner
    from compertum.runtime.ipc import start_role_pipe
    root = ROOT / ".cache/test-runs" / ("native-ipc-" + str(uuid4()))
    root.mkdir(parents=True)
    lease = acquire_owner(resolve_project(root), "coordinator")
    ep = start_role_pipe(lease, frozenset({"status"}))
    try: yield root, lease, ep
    finally: release_owner(lease)


def launch(root, descriptor, action="status", actor=None, change=None, raw=False):
    payload = {"schema_version": 1, "request_id": str(uuid4()),
        "target_role": descriptor.registration.identity.role,
        "target_generation": descriptor.registration.generation,
        "action": action, "payload": {}, "actor": actor or {"kind": "operator"}}
    if change: payload.update(change)
    packet = root / (str(uuid4()) + ".json")
    packet.write_text(json.dumps({"registration": asdict(descriptor.registration), "command": payload, "raw": raw}))
    env = {k: v for k, v in os.environ.items() if k.upper() in {"SYSTEMROOT", "WINDIR"}}
    env["PYTHONPATH"] = str(ROOT / "src"); env["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.Popen([sys.executable, "-B", str(ROOT / "tests/helpers/pipe_client.py"), str(packet)],
        cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def finish(proc):
    try: out, err = proc.communicate(timeout=8)
    except subprocess.TimeoutExpired:
        proc.terminate(); out, err = proc.communicate(timeout=3)
        pytest.fail("bounded client did not exit")
    assert not err
    return proc.returncode, json.loads(out)


def test_authenticated_operator_roundtrip_has_no_effect_and_no_writer_rights(endpoint):
    root, _, ep = endpoint
    proc = launch(root, ep.descriptor)
    result = ep.inspect_once(timeout=5)
    code, reply = finish(proc)
    assert code == 0 and reply["status"] == "PROTOCOL_VALIDATED_ONLY"
    assert result.request_id == reply["request_id"] and not result.can_dispatch


@pytest.mark.parametrize("change,reason", [({"target_generation": 999}, "TARGET_MISMATCH"),
    ({"target_role": "execution"}, "TARGET_MISMATCH"),
    ({"actor": {"kind": "operator", "pid": 1}}, "INVALID_ENVELOPE"),
    ({"actor": {"kind": "worker", "role": "execution", "generation": 1,
        "instance_id": "00000000-0000-4000-8000-000000000001"}}, "ROLE_DENIED"),
    ({"action": "paper.arm"}, "COMMAND_DENIED")])
def test_wrong_role_generation_spoofed_pid_and_financial_action_denied_before_dispatch(endpoint, change, reason):
    from compertum.runtime.errors import RuntimeRefused
    root, _, ep = endpoint
    proc = launch(root, ep.descriptor, change=change, raw=True)
    try:
        with pytest.raises(RuntimeRefused, match=reason): ep.inspect_once(timeout=5)
    finally:
        code, result = finish(proc)
    assert code == 3 and result["status"] != "PROTOCOL_VALIDATED_ONLY"


def test_occupied_first_instance_is_not_trusted(endpoint):
    from compertum.runtime._pipes import NativePipeAPI
    from compertum.runtime.errors import RuntimeRefused
    _, _, ep = endpoint
    with pytest.raises(RuntimeRefused, match="PIPE_NAME_OCCUPIED"):
        NativePipeAPI().server(ep.descriptor.registration)


def test_idle_connect_deadline_cancels_native_io_and_keeps_endpoint_reusable(endpoint):
    from compertum.runtime.errors import RuntimeRefused
    root, _, ep = endpoint
    began = time.monotonic()
    with pytest.raises(RuntimeRefused, match="PIPE_DEADLINE_EXCEEDED"):
        ep.inspect_once(timeout=0.25)
    assert time.monotonic() - began < 2
    proc = launch(root, ep.descriptor)
    result = ep.inspect_once(timeout=5)
    assert finish(proc)[0] == 0 and result.status == "PROTOCOL_VALIDATED_ONLY"


def test_unexpected_native_server_is_denied_before_client_sends_a_command(endpoint):
    from compertum.runtime._pipes import NativePipeAPI
    from compertum.runtime.ipc import PipeDescriptor
    from compertum.runtime.errors import RuntimeRefused
    root, _, ep = endpoint
    # Public metadata names a different instance of a real child process.
    other = subprocess.Popen([sys.executable, "-B", "-c", "import time; time.sleep(8)"],
        env={k: v for k, v in os.environ.items() if k.upper() in {"SYSTEMROOT", "WINDIR"}})
    api = NativePipeAPI()
    try:
        with api.open_process(other.pid) as handle:
            identity = replace(ep.descriptor.registration.identity, pid=other.pid,
                creation_filetime=api.creation_time(handle), process_instance_id=str(uuid4()))
        forged = replace(ep.descriptor.registration, identity=identity)
        with api.server(forged) as pipe:
            proc = launch(root, PipeDescriptor(forged))
            api.connect(pipe, time.monotonic() + 5)
            code, reply = finish(proc)
            assert code == 3 and reply["status"] == "PEER_MISMATCH"
            with pytest.raises(RuntimeRefused): api.read_frame(pipe, time.monotonic() + 0.5)
    finally:
        other.terminate(); other.wait(timeout=3)


def test_closed_endpoint_cannot_be_resurrected(endpoint):
    from compertum.runtime.errors import RuntimeRefused
    from compertum.runtime.owners import require_live_owner
    _, lease, ep = endpoint
    ep.close()
    assert ep.closed
    require_live_owner(lease)
    with pytest.raises(RuntimeRefused, match="ENDPOINT_UNVERIFIED"): ep.inspect_once(timeout=0.1)


def test_owner_release_closes_transport_before_a_new_owner_can_attempt_startup():
    from compertum.runtime.identity import resolve_project
    from compertum.runtime.owners import acquire_owner, release_owner
    from compertum.runtime.ipc import start_role_pipe
    from compertum.runtime.errors import RuntimeRefused
    root = ROOT / ".cache/test-runs" / ("native-ipc-release-" + str(uuid4()))
    root.mkdir(parents=True)
    lease = acquire_owner(resolve_project(root), "coordinator")
    ep = start_role_pipe(lease, frozenset({"status"}))
    release_owner(lease)
    assert ep.closed and ep.handle.closed
    with pytest.raises(RuntimeRefused, match="OWNER_UNVERIFIED"): ep.inspect_once(timeout=0.1)
