"""Pure bootstrap contract tests. They never qualify Windows inheritance."""
from dataclasses import asdict, replace
import json
import pickle
import os
import pytest
from compertum.runtime import ipc
from compertum.runtime.errors import RuntimeRefused
from compertum.runtime.identity import PeerObservation
from compertum.runtime.bootstrap import (
    BootstrapPacket, encode_bootstrap, decode_bootstrap, validate_worker_commands,
    prepare_bootstrap, receive_bootstrap, encode_worker_frame, decode_request_frame,
)
from test_ipc_protocol import REG, PEER, envelope

SUPERVISOR = replace(REG, identity=replace(REG.identity, role="supervisor"), subject_kind="worker")
TARGET = replace(REG, generation=3, subject_kind="worker")
CHILD = replace(REG, identity=replace(REG.identity, pid=777, creation_filetime=200,
    process_instance_id="00000000-0000-4000-8000-000000000003", role="watchdog"), subject_kind="worker")
CHILD_PEER = PeerObservation(777, 200, PEER.operator_sid, PEER.logon_sid)


def packet(): return BootstrapPacket(SUPERVISOR, TARGET, CHILD, frozenset({"status"}), "a" * 64)


def test_private_packet_roundtrip_is_scoped_to_native_child_and_supervisor():
    original = packet()
    raw = encode_bootstrap(original)
    decoded = decode_bootstrap(raw, expected_supervisor=SUPERVISOR, observed_supervisor=PEER,
                               observed_child=CHILD_PEER)
    assert decoded.child == CHILD and decoded.commands == frozenset({"status"})
    assert decoded.secret == original.secret
    assert original.secret not in repr(decoded)
    with pytest.raises(RuntimeRefused, match="PRIVATE_CAPABILITY"): pickle.dumps(decoded)


@pytest.mark.parametrize("field,change", [("supervisor", {"pid": 888}),
    ("child", {"pid": 888}), ("child", {"creation_filetime": 999}),
    ("child", {"operator_sid": "S-1-5-21-9"}), ("child", {"logon_sid": "S-1-5-5-9-9"})])
def test_bootstrap_claimed_identity_never_replaces_native_observation(field, change):
    observed = PEER if field == "supervisor" else CHILD_PEER
    changed = replace(observed, **change)
    with pytest.raises(RuntimeRefused, match="PEER_MISMATCH"):
        decode_bootstrap(encode_bootstrap(packet()), expected_supervisor=SUPERVISOR,
            observed_supervisor=changed if field == "supervisor" else PEER,
            observed_child=changed if field == "child" else CHILD_PEER)


@pytest.mark.parametrize("commands", [frozenset({"resume_research"}), frozenset({"shutdown"}),
    frozenset({"paper.arm"}), frozenset(), {"status"}])
def test_watchdog_cannot_receive_operator_or_financial_authority(commands):
    with pytest.raises(RuntimeRefused, match="WORKER_COMMAND_DENIED"):
        validate_worker_commands("watchdog", commands)
    validate_worker_commands("watchdog", frozenset({"status", "pause_research"}))


def test_bootstrap_rejects_extra_fields_duplicate_keys_and_cross_project_target():
    raw = encode_bootstrap(packet()); payload = json.loads(raw)
    altered = dict(payload); altered["extra"] = "x"
    cross = json.loads(raw); cross["target"]["project_id"] = "b" * 64
    for bad in (json.dumps(altered).encode(), b'{"schema_version":1,"schema_version":1}',
                json.dumps(cross).encode(), b"x" * 8193):
        with pytest.raises(RuntimeRefused):
            decode_bootstrap(bad, expected_supervisor=SUPERVISOR, observed_supervisor=PEER, observed_child=CHILD_PEER)


def test_worker_frame_requires_secret_and_preserves_request_identity():
    value = envelope()
    value["actor"] = {"kind": "worker", "role": CHILD.identity.role,
        "instance_id": CHILD.identity.process_instance_id, "generation": CHILD.generation}
    raw = encode_worker_frame(value, "a" * 64)
    decoded, secret = decode_request_frame(raw)
    assert decoded == value and secret == "a" * 64
    ordinary, absent = decode_request_frame(ipc.encode_envelope(envelope()))
    assert ordinary == envelope() and absent is None
    for bad in ('{"envelope":{},"capability":"ü"}'.encode(), b'{"envelope":{},"capability":1}',
                b'{"envelope":{},"capability":"a","extra":true}'):
        with pytest.raises(RuntimeRefused): decode_request_frame(bad)
    with pytest.raises(RuntimeRefused): encode_worker_frame(value, "x" * 64)


def test_constructed_leases_do_not_mint_inherited_bootstrap_or_worker_rights():
    from compertum.domain import OwnerLease
    fake = OwnerLease(SUPERVISOR.project_id, 2, SUPERVISOR.identity, object())
    with pytest.raises(RuntimeRefused, match="OWNER_UNVERIFIED"):
        prepare_bootstrap(fake, object(), role="watchdog", generation=1, commands=frozenset({"status"}))


@pytest.mark.skipif(os.name == "nt", reason="cloud refusal test")
def test_cloud_cannot_receive_native_bootstrap_from_a_numeric_handle():
    with pytest.raises(RuntimeRefused, match="NATIVE_WINDOWS_UNAVAILABLE"):
        receive_bootstrap(123, expected_supervisor=SUPERVISOR)


def test_forged_credential_does_not_enable_a_worker_roundtrip():
    from compertum.runtime.bootstrap import WorkerCredential, inspect_worker_request
    with pytest.raises(RuntimeRefused, match="BOOTSTRAP_DENIED"): WorkerCredential()
    forged = object.__new__(WorkerCredential)
    with pytest.raises(RuntimeRefused, match="BOOTSTRAP_DENIED"):
        inspect_worker_request(forged, envelope())


@pytest.mark.parametrize("fault", ["operator", "wrong_secret", "wrong_role", "wrong_generation", "revoked", "dead", "supervisor_lost"])
def test_enrolled_worker_never_falls_back_to_operator_rights(monkeypatch, fault):
    from types import SimpleNamespace
    from compertum.runtime import owners
    from compertum.runtime.ipc import RoleEndpoint, PipeDescriptor, ScopedCapability, _WorkerEnrollment
    monkeypatch.setattr(owners, "require_live_owner", lambda _: None)
    api = SimpleNamespace(WaitForSingleObject=lambda *a: 258, creation_time=lambda _: CHILD_PEER.creation_filetime)
    process = SimpleNamespace(get=lambda: 99, close=lambda: None)
    lease = SimpleNamespace(project_id=TARGET.project_id, identity=TARGET.identity, generation=TARGET.generation)
    ep = RoleEndpoint(lease, ipc.PipeDescriptor(TARGET), frozenset({"status", "resume_research"}), api, process)
    cap = ScopedCapability(CHILD, frozenset({"status"}))
    entry = _WorkerEnrollment(cap, process, object())
    ep._workers[(CHILD_PEER.pid, CHILD_PEER.creation_filetime)] = entry
    value = envelope(); value["actor"] = {"kind": "worker", "role": "watchdog",
        "instance_id": CHILD.identity.process_instance_id, "generation": CHILD.generation}
    assert ep._authorize_peer(value, CHILD_PEER, cap.secret).can_dispatch is False
    secret = cap.secret
    if fault == "operator": value["actor"] = {"kind": "operator"}; value["action"] = "resume_research"; secret = None
    if fault == "wrong_secret": secret = "b" * 64
    if fault == "wrong_role": value["actor"]["role"] = "execution"
    if fault == "wrong_generation": value["actor"]["generation"] += 1
    if fault == "revoked": entry.active = False; value["actor"] = {"kind": "operator"}; secret = None
    if fault == "dead": api.WaitForSingleObject = lambda *a: 0
    if fault == "supervisor_lost":
        def lost(_): raise RuntimeRefused("OWNER_UNVERIFIED")
        monkeypatch.setattr(owners, "require_live_owner", lost)
    with pytest.raises(RuntimeRefused): ep._authorize_peer(value, CHILD_PEER, secret)


def test_worker_wrapper_budget_includes_capability_overhead():
    value = envelope(); value["actor"] = {"kind": "worker", "role": "watchdog",
        "instance_id": CHILD.identity.process_instance_id, "generation": CHILD.generation}
    value["payload"] = {"x": "x" * 65000}
    base = ipc.encode_envelope(value)
    value["payload"]["x"] += "x" * (65536 - len(base))
    assert len(ipc.encode_envelope(value)) == 65536
    with pytest.raises(RuntimeRefused, match="ENVELOPE_TOO_LARGE"): encode_worker_frame(value, "a" * 64)


@pytest.mark.parametrize("different_project", [False, True])
def test_known_worker_cannot_claim_operator_at_another_endpoint(monkeypatch, different_project):
    """Injected native identity classification, never Windows authentication."""
    from types import SimpleNamespace
    from compertum.runtime.ipc import RoleEndpoint, PipeDescriptor
    known = {(CHILD_PEER.pid, CHILD_PEER.creation_filetime)}
    monkeypatch.setattr(ipc, "_WORKER_IDENTITIES", known, raising=False)
    target = replace(TARGET, project_id="b" * 64) if different_project else TARGET
    lease = SimpleNamespace(project_id=target.project_id, identity=target.identity, generation=target.generation)
    ep = RoleEndpoint(lease, PipeDescriptor(target), frozenset({"status", "resume_research"}), object(), object())
    value = envelope(); value["action"] = "resume_research"
    # This endpoint never granted a capability, even if another endpoint's
    # enrollment has already been revoked and its handles closed.
    with pytest.raises(RuntimeRefused, match="ROLE_DENIED"):
        ep._authorize_peer(value, CHILD_PEER, None)


@pytest.mark.parametrize("failure_at", ["reset", "close"])
def test_inheritance_finalization_failure_irrevocably_closes_offer(monkeypatch, failure_at):
    """Injected disposal failures, never native inheritance qualification."""
    from contextlib import contextmanager
    import threading
    from types import SimpleNamespace
    from compertum.runtime import owners
    from compertum.runtime.bootstrap import BootstrapOffer
    @contextmanager
    def scope(_): yield None
    monkeypatch.setattr(owners, "_owner_scope", scope)
    def handle(value, fail=False):
        h = SimpleNamespace(closed=False, get=lambda: value)
        def close():
            h.closed = True
            if fail: raise KeyboardInterrupt()
        h.close = close
        return h
    server = handle(1); client = handle(2, failure_at == "close")
    def inheritable(h, flag):
        if not flag and failure_at == "reset": raise KeyboardInterrupt()
    api = SimpleNamespace(set_inheritable=inheritable)
    endpoint = SimpleNamespace(lease=object(), _lock=threading.RLock())
    offer = BootstrapOffer(object(), endpoint, SUPERVISOR, "watchdog", 1, frozenset({"status"}), api, server, client)
    with pytest.raises(KeyboardInterrupt):
        with offer.inheritance(): pass
    assert offer.closed and client.closed and server.closed


def test_worker_identity_bound_refuses_new_enrollment_without_discarding_tombstones(monkeypatch):
    from types import SimpleNamespace
    from compertum.runtime import owners
    from compertum.runtime.bootstrap import BootstrapOffer
    from compertum.runtime.ipc import RoleEndpoint, PipeDescriptor, ScopedCapability
    known = {(n, n) for n in range(1, 65)}
    monkeypatch.setattr(ipc, "_WORKER_IDENTITIES", known, raising=False)
    monkeypatch.setattr(owners, "require_live_owner", lambda _: None)
    lease = SimpleNamespace(project_id=TARGET.project_id, identity=TARGET.identity, generation=TARGET.generation)
    ep = RoleEndpoint(lease, PipeDescriptor(TARGET), frozenset({"status"}), object(), object())
    offer = BootstrapOffer(object(), ep, SUPERVISOR, "watchdog", CHILD.generation,
        frozenset({"status"}), object(), object(), object())
    ep._offers.append(offer)
    cap = ipc.ScopedCapability(CHILD, frozenset({"status"}))
    with pytest.raises(RuntimeRefused, match="BOOTSTRAP_DENIED"): ep._enroll(offer, cap, object())
    assert len(known) == 64 and not ep._workers
