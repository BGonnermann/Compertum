"""Portable validation only; these tests do not authenticate OS peers."""
from dataclasses import replace
import json
import pickle
import pytest

from compertum.domain import ProcessIdentity
from compertum.runtime.errors import RuntimeRefused
from compertum.runtime.identity import PeerObservation
from compertum.runtime.ipc import PeerRegistration, ScopedCapability, authorize_envelope, decode_envelope, encode_envelope, request

PID = ProcessIdentity("00000000-0000-4000-8000-000000000001", 321, 100, "S-1-5-21-1", "coordinator")
PEER = PeerObservation(321, 100, "S-1-5-21-1", "S-1-5-5-1-2")
REG = PeerRegistration(PID, "S-1-5-5-1-2", "a" * 64, 2, "operator")


def envelope():
    return {"schema_version": 1, "request_id": "00000000-0000-4000-8000-000000000002",
            "target_role": "coordinator", "target_generation": 3, "action": "status",
            "payload": {}, "actor": {"kind": "operator"}}


def check(value, registration=REG, observed=PEER, **kw):
    return authorize_envelope(value, registration=registration, observed=observed,
                              target_project_id="a" * 64, target_role="coordinator",
                              target_generation=3, allowed_commands=frozenset({"status", "checkpoint"}), **kw)


def test_valid_operator_request_is_protocol_evidence_only():
    result = check(envelope())
    assert result.status == "PROTOCOL_VALIDATED_ONLY"
    assert result.can_dispatch is False


@pytest.mark.parametrize("changes", [{"pid": 999}, {"creation_filetime": 101},
                                    {"operator_sid": "S-1-5-21-2"}, {"logon_sid": "S-1-5-5-1-3"}])
def test_observed_peer_must_match_the_live_registration(changes):
    with pytest.raises(RuntimeRefused, match="PEER_MISMATCH"):
        check(envelope(), observed=replace(PEER, **changes))


@pytest.mark.parametrize("changes", [{"target_role": "execution"}, {"target_generation": 4}])
def test_wrong_role_or_generation_denied(changes):
    value = envelope(); value.update(changes)
    with pytest.raises(RuntimeRefused, match="TARGET_MISMATCH"):
        check(value)


def test_spoofed_pid_does_not_authenticate():
    value = envelope(); value["actor"]["pid"] = 321
    with pytest.raises(RuntimeRefused, match="INVALID_ENVELOPE"):
        check(value)


def test_cli_cannot_claim_writer():
    value = envelope(); value["actor"] = {"kind": "worker", "role": "coordinator",
        "instance_id": PID.process_instance_id, "generation": 2}
    with pytest.raises(RuntimeRefused, match="ROLE_DENIED"):
        check(value)


def test_action_allowlist_cannot_enable_financial_commands():
    value = envelope(); value["action"] = "paper.arm"
    with pytest.raises(RuntimeRefused, match="COMMAND_DENIED"):
        authorize_envelope(value, registration=REG, observed=PEER, target_project_id="a" * 64,
                           target_role="coordinator", target_generation=3, allowed_commands=frozenset({"paper.arm"}))


def test_operator_receipt_subject_survives_a_new_authenticated_cli_process():
    next_id = replace(PID, pid=777, creation_filetime=300, process_instance_id="00000000-0000-4000-8000-000000000003")
    next_reg = replace(REG, identity=next_id)
    next_observed = replace(PEER, pid=777, creation_filetime=300)
    assert check(envelope()).subject_key == check(envelope(), next_reg, next_observed).subject_key


def test_changed_payload_has_a_different_replay_fingerprint():
    value = envelope(); value["payload"] = {"reason": "changed"}
    assert check(value).payload_hash != check(envelope()).payload_hash


def test_worker_capability_is_scoped_and_expires_on_generation_change():
    reg = replace(REG, subject_kind="worker")
    value = envelope(); value["actor"] = {"kind": "worker", "role": "coordinator",
        "instance_id": PID.process_instance_id, "generation": 2}
    cap = ScopedCapability(reg, frozenset({"status"}))
    result = check(value, reg, capability=cap, secret=cap.secret)
    assert result.can_dispatch is False
    with pytest.raises(RuntimeRefused, match="CAPABILITY_DENIED"):
        check(value, replace(reg, generation=3), capability=cap, secret=cap.secret)
    with pytest.raises(RuntimeRefused, match="CAPABILITY_DENIED"):
        check(value, reg, capability=cap, secret="x" * 64)
    assert cap.secret not in repr(cap)
    with pytest.raises(RuntimeRefused, match="PRIVATE_CAPABILITY"):
        pickle.dumps(cap)


@pytest.mark.parametrize("raw", [b'{"schema_version":1,"schema_version":1}', b'[]',
    b'{"x":NaN}', b'\xff', b'{', b' ' * 65537])
def test_malformed_duplicate_nonfinite_or_oversized_messages_are_denied(raw):
    with pytest.raises(RuntimeRefused):
        decode_envelope(raw)


def test_encoding_roundtrip_is_detached_and_canonical():
    value = envelope(); value["payload"] = {"b": 2, "a": 1}
    raw = encode_envelope(value)
    decoded = decode_envelope(raw)
    value["payload"]["a"] = 9
    assert decoded["payload"] == {"a": 1, "b": 2}
    assert b'"a":1,"b":2' in raw


def test_deeply_nested_or_nonfinite_payloads_are_rejected():
    value = envelope(); value["payload"] = {"x": float("inf")}
    with pytest.raises(RuntimeRefused): encode_envelope(value)
    nested = {}; value = envelope(); value["payload"] = nested
    for _ in range(40): nested["x"] = {}; nested = nested["x"]
    with pytest.raises(RuntimeRefused): encode_envelope(value)


def test_no_effectful_dispatch_without_native_transport_and_durable_receipts():
    with pytest.raises(RuntimeRefused, match="DURABLE_DISPATCH_UNAVAILABLE"):
        request(object(), envelope())


def test_non_ascii_capability_text_is_denied_without_an_uncaught_error():
    reg = replace(REG, subject_kind="worker")
    value = envelope(); value["actor"] = {"kind": "worker", "role": "coordinator",
        "instance_id": PID.process_instance_id, "generation": 2}
    cap = ScopedCapability(reg, frozenset({"status"}))
    with pytest.raises(RuntimeRefused, match="CAPABILITY_DENIED"):
        check(value, reg, capability=cap, secret="ü" * 64)


@pytest.mark.parametrize("payload", [{"x": "x" * 65537}, {"x" * 65537: 0}, {"x": [0] * 4097},
                                     {"x": "ü" * 11000}, {"x": "x" * 33000, "y": "y" * 33000}])
def test_oversized_inputs_are_refused_before_serialization(monkeypatch, payload):
    from compertum.runtime import ipc
    value = envelope(); value["payload"] = payload
    def unexpected_serialization(*a, **kw): raise AssertionError("serialization preceded size refusal")
    monkeypatch.setattr(ipc.json, "dumps", unexpected_serialization)
    with pytest.raises(RuntimeRefused): encode_envelope(value)
