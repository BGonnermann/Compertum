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
from fixture_processes import python_process

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
    return python_process(["-B", str(ROOT / "tests/helpers/pipe_client.py"), str(packet)],
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
    other = python_process(["-B", "-c", "import time; time.sleep(8)"],
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


def test_client_dacl_denies_create_instance_right_independently_of_first_instance(endpoint):
    import ctypes as c
    from compertum.runtime._pipes import SECURITY_ATTRIBUTES, pipe_security
    from compertum.runtime._windows import HANDLE, DWORD, NativeCallError
    root, _, ep = endpoint
    api = ep.api; registration = ep.descriptor.registration
    # Test server creation itself, without FIRST_PIPE_INSTANCE and with room
    # for a second instance. Client CreateFile does not test server authority.
    # A separate permissive fixture proves that the probe can create a server.
    for permissive in (False, True):
        sddl = pipe_security(registration.identity.operator_sid, registration.logon_sid)
        if permissive:
            sddl = sddl.replace('0x00100083', '0x001f01ff')
        descriptor = HANDLE(); size = DWORD()
        api.checked(api.ConvertStringSecurityDescriptorToSecurityDescriptorW(
            sddl, 1, c.byref(descriptor), c.byref(size)), 'fixture security')
        name = '\\\\.\\pipe\\compertum-dacl-fixture-' + str(uuid4())
        attributes = SECURITY_ATTRIBUTES(c.sizeof(SECURITY_ATTRIBUTES), descriptor, False)
        try:
            with api._handle(api.CreateNamedPipeW(name, 3 | 0x40000000, 8, 2,
                              65540, 65540, 5000, c.byref(attributes)), 'fixture first'):
                def create_second():
                    return api._handle(api.CreateNamedPipeW(name, 3 | 0x40000000, 8, 2,
                                       65540, 65540, 5000, None), 'fixture second')
                if permissive:
                    with create_second(): pass
                else:
                    with pytest.raises(NativeCallError) as denied:
                        with create_second(): pass
                    assert denied.value.winerror == 5
        finally:
            api.LocalFree(descriptor)
    proc = launch(root, ep.descriptor)
    assert not ep.inspect_once().can_dispatch and finish(proc)[0] == 0

def fault_client(root, descriptor, mode):
    key = str(uuid4()); ready = root / (key + ".ready"); stop = root / (key + ".stop")
    received = root / (key + ".received"); config = root / (key + ".json")
    command = {"schema_version": 1, "request_id": str(uuid4()), "target_role": descriptor.registration.identity.role,
        "target_generation": descriptor.registration.generation, "action": "status", "payload": {}, "actor": {"kind": "operator"}}
    config.write_text(json.dumps({"target": asdict(descriptor.registration), "mode": mode,
        "ready": str(ready), "stop": str(stop), "received": str(received), "command": command}))
    env = {k: v for k, v in os.environ.items() if k.upper() in {"SYSTEMROOT", "WINDIR"}}
    env["PYTHONPATH"] = str(ROOT / "src"); env["PYTHONDONTWRITEBYTECODE"] = "1"
    proc = python_process(["-B", str(ROOT / "tests/helpers/pipe_fault_client.py"), str(config)],
        cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    end = time.monotonic() + 5
    while not ready.exists():
        if proc.poll() is not None or time.monotonic() >= end:
            if proc.poll() is None: proc.terminate()
            proc.communicate(timeout=3); pytest.fail("native fault client never connected")
        time.sleep(.01)
    return proc, stop, received


@pytest.mark.parametrize("mode,reason", [("bad_ack", "REPLY_ACK_DENIED"), ("no_ack", "PIPE_DEADLINE_EXCEEDED")])
def test_missing_or_wrong_public_ack_refuses_completion_and_allows_a_fresh_connection(endpoint, mode, reason):
    from compertum.runtime.errors import RuntimeRefused
    root, _, ep = endpoint; proc, stop, received = fault_client(root, ep.descriptor, mode)
    try:
        with pytest.raises(RuntimeRefused, match=reason): ep.inspect_once(timeout=.5)
        assert received.exists()  # timeout occurred after reply, not during child startup
    finally:
        stop.touch(); finish(proc)
    other = launch(root, ep.descriptor)
    assert not ep.inspect_once().can_dispatch and finish(other)[0] == 0


@pytest.mark.parametrize("kind,interrupt", [("read", False), ("write", False), ("read", True), ("write", True)])
def test_actual_pending_io_is_completed_before_buffers_are_released(endpoint, monkeypatch, kind, interrupt):
    """Actual native I/O with optional injected Python interruption, not Ctrl+C."""
    import ctypes as c
    from compertum.runtime import _pipes
    from compertum.runtime.errors import RuntimeRefused
    root, _, ep = endpoint
    proc, stop, _ = fault_client(root, ep.descriptor, "partial" if kind == "read" else "hold")
    api = ep.api; pending = []; completed = []; cancellations = []
    submit_name = "ReadFile" if kind == "read" else "WriteFile"
    native_submit = getattr(api, submit_name); native_result = api.GetOverlappedResult; native_cancel = api.CancelIoEx
    def submit(*args):
        ok = native_submit(*args); error = c.get_last_error()
        if not ok and error == 997:
            pending.append(True)
            if interrupt: raise KeyboardInterrupt()
        c.set_last_error(error); return ok
    def cancel(*args):
        ok = native_cancel(*args); error = c.get_last_error(); cancellations.append(True)
        c.set_last_error(error); return ok
    def result(*args):
        ok = native_result(*args); error = c.get_last_error()
        if cancellations: completed.append((bool(ok), error))
        c.set_last_error(error); return ok
    try:
        api.connect(ep.handle, _pipes.deadline_after(5))
        with monkeypatch.context() as patch:
            patch.setattr(api, submit_name, submit); patch.setattr(api, "CancelIoEx", cancel)
            patch.setattr(api, "GetOverlappedResult", result)
            with pytest.raises(KeyboardInterrupt if interrupt else RuntimeRefused,
                               match=None if interrupt else "PIPE_DEADLINE_EXCEEDED"):
                deadline = _pipes.deadline_after(.5)
                if kind == "read": api.read_frame(ep.handle, deadline)
                else:
                    # At most 1 MiB and .5 s. Native ERROR_IO_PENDING, not this
                    # byte budget, is required as proof that cancellation ran.
                    for _ in range(16): api.write_frame(ep.handle, b"x" * 65536, deadline)
                    pytest.fail("NATIVE_PENDING_WRITE_NOT_OBSERVED")
        assert pending and cancellations and completed
        assert completed[-1][0] or completed[-1][1] == 995
        assert not _pipes._INFLIGHT and not _pipes._UNCERTAIN
    finally:
        api.disconnect(ep.handle); stop.touch(); finish(proc)
    other = launch(root, ep.descriptor)
    assert not ep.inspect_once().can_dispatch and finish(other)[0] == 0
