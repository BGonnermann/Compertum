"""Transport policy tests, never native Windows acceptance."""
from dataclasses import replace
import json
import os
import struct
import pytest

from compertum.runtime import ipc
from compertum.runtime.errors import RuntimeRefused
from compertum.runtime.identity import PeerObservation
from compertum.runtime._pipes import frame_bytes, frame_length, pipe_name, pipe_security, verify_peer
from test_ipc_protocol import REG, PEER, envelope


def test_frame_is_bounded_before_allocating_or_writing():
    assert frame_bytes(b"abc") == b"\x03\x00\x00\x00abc"
    assert frame_length(struct.pack("<I", 65536)) == 65536
    for value in (b"", b"x" * 65537, "abc"):
        with pytest.raises(RuntimeRefused, match="FRAME_DENIED"): frame_bytes(value)
    for header in (b"", b"abc", struct.pack("<I", 0), struct.pack("<I", 65537)):
        with pytest.raises(RuntimeRefused, match="FRAME_DENIED"): frame_length(header)


def test_pipe_policy_excludes_create_instance_and_remote_paths():
    name = pipe_name(REG)
    assert name.startswith("\\\\.\\pipe\\compertum-")
    assert REG.project_id in name and REG.identity.process_instance_id in name
    dacl = pipe_security(REG.identity.operator_sid, REG.logon_sid)
    assert "WD" not in dacl and "AN" not in dacl and "GA" not in dacl and "GW" not in dacl
    assert "0x00100083" in dacl  # data read/write, read attributes, synchronize; never bit 4.
    assert REG.identity.operator_sid in dacl and REG.logon_sid in dacl
    for sid in ("S-1-5-21-1)(A;;GA;;;WD", "WD", ""):
        with pytest.raises(RuntimeRefused, match="PIPE_SID_DENIED"): pipe_security(sid, REG.logon_sid)


@pytest.mark.parametrize("change", [{"pid": 999}, {"creation_filetime": 1},
    {"operator_sid": "S-1-5-21-9"}, {"logon_sid": "S-1-5-5-9-9"}])
def test_response_peer_is_checked_against_all_registered_native_fields(change):
    verify_peer(REG, PEER)
    with pytest.raises(RuntimeRefused, match="PEER_MISMATCH"):
        verify_peer(REG, replace(PEER, **change))


def test_protocol_reply_is_correlated_and_cannot_claim_an_effect():
    decision = ipc.authorize_envelope(envelope(), registration=REG, observed=PEER,
        target_project_id=REG.project_id, target_role="coordinator", target_generation=3,
        allowed_commands=frozenset({"status"}))
    raw = ipc.encode_protocol_reply(decision)
    result = ipc.decode_protocol_reply(raw, decision)
    assert result == decision and not result.can_dispatch
    payload = json.loads(raw)
    for key, value in (("request_id", "00000000-0000-4000-8000-000000000003"),
                       ("payload_hash", "b" * 64), ("can_dispatch", True),
                       ("status", "CONFIRMED"), ("target_generation", 4)):
        changed = dict(payload); changed[key] = value
        with pytest.raises(RuntimeRefused, match="REPLY_DENIED"):
            ipc.decode_protocol_reply(json.dumps(changed).encode(), decision)
    with pytest.raises(RuntimeRefused, match="REPLY_DENIED"):
        ipc.decode_protocol_reply(raw[:-1], decision)


@pytest.mark.skipif(os.name == "nt", reason="non-Windows refusal test")
def test_native_pipe_adapter_refuses_cloud_without_creating_a_transport():
    from compertum.runtime._pipes import NativePipeAPI
    with pytest.raises(RuntimeRefused, match="NATIVE_WINDOWS_UNAVAILABLE"): NativePipeAPI()


def test_constructed_endpoint_cannot_grant_transport_or_dispatch():
    with pytest.raises(RuntimeRefused, match="ENDPOINT_UNVERIFIED"):
        ipc.inspect_request(object(), envelope())
    with pytest.raises(RuntimeRefused, match="DURABLE_DISPATCH_UNAVAILABLE"):
        ipc.request(object(), envelope())


@pytest.mark.parametrize("completion_error,uncertain", [(995, False), (996, True), (6, True)])
def test_cancellation_keeps_native_buffers_until_completion_is_known(monkeypatch, completion_error, uncertain):
    """Injected Win32 results exercise disposal policy, not native cancellation."""
    import ctypes
    from types import SimpleNamespace
    from compertum.runtime import _pipes
    held = []
    monkeypatch.setattr(_pipes, "_UNCERTAIN", held)
    monkeypatch.setattr(ctypes, "get_last_error", lambda: completion_error, raising=False)
    api = object.__new__(_pipes.NativePipeAPI)
    api.CancelIoEx = lambda *a: True
    api.WaitForSingleObject = lambda *a: 0
    api.GetOverlappedResult = lambda *a: False
    pipe = SimpleNamespace(get=lambda: 1)
    op = _pipes._Operation(SimpleNamespace(get=lambda: 2), _pipes.OVERLAPPED(), ctypes.create_string_buffer(16))
    if uncertain:
        with pytest.raises(RuntimeRefused, match="PIPE_CANCELLATION_UNVERIFIED"): api._cancel(pipe, op)
        assert held[0][2].buffer is op.buffer
        with pytest.raises(RuntimeRefused, match="PIPE_CANCELLATION_UNVERIFIED"): api._admit()
    else:
        api._cancel(pipe, op)
        assert held == []


@pytest.mark.parametrize("interrupt_at", ["submit", "cancel"])
def test_interrupted_native_operation_retains_buffers_and_closes_the_pipe_gate(monkeypatch, interrupt_at):
    """Injected interrupts prove Python lifetime policy only, not Win32 I/O."""
    import ctypes
    import time
    from types import SimpleNamespace
    from compertum.runtime import _pipes
    held = []; closed = []
    monkeypatch.setattr(_pipes, "_UNCERTAIN", held)
    monkeypatch.setattr(_pipes, "_INFLIGHT", {}, raising=False)
    monkeypatch.setattr(ctypes, "get_last_error", lambda: 997, raising=False)
    api = object.__new__(_pipes.NativePipeAPI)
    event = SimpleNamespace(get=lambda: 2, close=lambda: closed.append("event"))
    api.CreateEventW = lambda *a: 2
    api._handle = lambda *a: event
    def submit(*a):
        if interrupt_at == "submit": raise KeyboardInterrupt()
        return False
    api.ReadFile = submit
    api.WaitForSingleObject = lambda *a: 258
    def cancel(*a): raise KeyboardInterrupt()
    api.CancelIoEx = cancel
    buffer = ctypes.create_string_buffer(16)
    with pytest.raises(KeyboardInterrupt):
        api._io(SimpleNamespace(get=lambda: 1), "read", buffer, 16, time.monotonic() + 1)
    assert closed == []
    assert held and held[0][2].buffer is buffer
    with pytest.raises(RuntimeRefused, match="PIPE_CANCELLATION_UNVERIFIED"): api._admit()
