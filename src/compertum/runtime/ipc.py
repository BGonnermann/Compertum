"""Protocol checks only. No OS peer authentication or effectful dispatch."""
from dataclasses import dataclass
import hashlib
import hmac
import json
import math
import re
import secrets
from uuid import UUID
from compertum.domain import ProcessIdentity, capability_for
from .errors import RuntimeRefused
from .identity import PeerObservation


@dataclass(frozen=True)
class PeerRegistration:
    identity: ProcessIdentity
    logon_sid: str
    project_id: str
    generation: int
    subject_kind: str

    def __post_init__(self):
        if (not isinstance(self.identity, ProcessIdentity) or not isinstance(self.logon_sid, str)
                or not re.fullmatch(r"S-1-5-5-\d+-\d+", self.logon_sid)
                or not isinstance(self.project_id, str) or not re.fullmatch(r"[0-9a-f]{64}", self.project_id)
                or type(self.generation) is not int or not 1 <= self.generation < 2**63
                or self.subject_kind not in ("operator", "worker")):
            raise RuntimeRefused("INVALID_REGISTRATION")


class ScopedCapability:
    __slots__ = ("registration", "commands", "secret")

    def __init__(self, registration, commands):
        if (not isinstance(registration, PeerRegistration) or registration.subject_kind != "worker"
                or not isinstance(commands, frozenset) or not commands or any(not isinstance(x, str) for x in commands)):
            raise RuntimeRefused("INVALID_CAPABILITY")
        object.__setattr__(self, "registration", registration)
        object.__setattr__(self, "commands", commands)
        object.__setattr__(self, "secret", secrets.token_hex(32))

    def __setattr__(self, name, value):
        raise AttributeError("immutable capability")

    def __delattr__(self, name):
        raise AttributeError("immutable capability")

    def __repr__(self):
        return "<ScopedCapability private; protocol-only>"

    def __getstate__(self):
        raise RuntimeRefused("PRIVATE_CAPABILITY")


def encode_envelope(value):
    _validate(value)
    try: data = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False, ensure_ascii=True).encode("utf-8")
    except (ValueError, TypeError, RecursionError): raise RuntimeRefused("INVALID_ENVELOPE") from None
    if len(data) > 65536: raise RuntimeRefused("ENVELOPE_TOO_LARGE")
    return data


def decode_envelope(raw):
    if not isinstance(raw, bytes) or len(raw) > 65536: raise RuntimeRefused("ENVELOPE_TOO_LARGE")
    def pairs(values):
        result = {}
        for key, value in values:
            if key in result: raise ValueError("duplicate key")
            result[key] = value
        return result
    def nonfinite(_): raise ValueError("nonfinite")
    try: value = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=nonfinite)
    except (UnicodeError, ValueError, RecursionError): raise RuntimeRefused("INVALID_ENVELOPE") from None
    _validate(value)
    return value


def authorize_envelope(value, *, registration, observed, target_project_id, target_role, target_generation,
                       allowed_commands, capability=None, secret=None):
    value = decode_envelope(encode_envelope(value))
    if (not isinstance(registration, PeerRegistration) or not isinstance(observed, PeerObservation)
            or type(observed.pid) is not int or type(observed.creation_filetime) is not int
            or (observed.pid, observed.creation_filetime, observed.operator_sid, observed.logon_sid) !=
               (registration.identity.pid, registration.identity.creation_filetime,
                registration.identity.operator_sid, registration.logon_sid)):
        raise RuntimeRefused("PEER_MISMATCH")
    if (registration.project_id != target_project_id or value["target_role"] != target_role
            or value["target_generation"] != target_generation): raise RuntimeRefused("TARGET_MISMATCH")
    action = value["action"]
    if (not isinstance(allowed_commands, frozenset) or action not in allowed_commands
            or capability_for(action).exit_code != 0): raise RuntimeRefused("COMMAND_DENIED")
    actor = value["actor"]
    if actor["kind"] != registration.subject_kind: raise RuntimeRefused("ROLE_DENIED")
    if actor["kind"] == "worker":
        if (not isinstance(capability, ScopedCapability) or capability.registration != registration
                or action not in capability.commands or not isinstance(secret, str)
                or not re.fullmatch(r"[0-9a-f]{64}", secret)
                or not hmac.compare_digest(capability.secret, secret)):
            raise RuntimeRefused("CAPABILITY_DENIED")
        identity = registration.identity
        if (actor["role"], actor["instance_id"], actor["generation"]) != (
                identity.role, identity.process_instance_id, registration.generation):
            raise RuntimeRefused("ROLE_DENIED")
        subject = ["worker", identity.operator_sid, registration.logon_sid, identity.pid,
                   identity.creation_filetime, identity.process_instance_id, identity.role, registration.generation]
    else:
        if capability is not None or secret is not None: raise RuntimeRefused("ROLE_DENIED")
        subject = ["operator", observed.operator_sid, observed.logon_sid, "control"]
    subject_key = hashlib.sha256(json.dumps(subject, separators=(",", ":")).encode()).hexdigest()
    fingerprint = {"subject": subject_key, "action": action, "payload": value["payload"],
                   "target_role": target_role, "target_generation": target_generation, "project_id": target_project_id}
    digest = hashlib.sha256(json.dumps(fingerprint, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    return ProtocolDecision(value["request_id"], subject_key, digest, target_generation)


def request(endpoint, command):
    # Task 4 must supply durable authenticated receiver state before any effect.
    raise RuntimeRefused("DURABLE_DISPATCH_UNAVAILABLE")


@dataclass(frozen=True)
class ProtocolDecision:
    request_id: str
    subject_key: str
    payload_hash: str
    target_generation: int
    status: str = "PROTOCOL_VALIDATED_ONLY"
    can_dispatch: bool = False


def _uuid(value):
    try: return isinstance(value, str) and str(UUID(value)) == value
    except (ValueError, TypeError, AttributeError): return False


def _validate(value):
    stack = [(value, 0)]; visited = 0; size = 0
    while stack:
        node, depth = stack.pop(); visited += 1
        if depth > 32 or visited > 4096: raise RuntimeRefused("ENVELOPE_TOO_COMPLEX")
        if isinstance(node, dict):
            if visited + len(stack) + len(node) > 4096: raise RuntimeRefused("ENVELOPE_TOO_COMPLEX")
            if any(not isinstance(k, str) for k in node): raise RuntimeRefused("INVALID_ENVELOPE")
            size += 2 + max(0, len(node) - 1) + len(node)
            for key in node:
                size += _string_size(key)
                if size > 65536: raise RuntimeRefused("ENVELOPE_TOO_LARGE")
            stack.extend((v, depth + 1) for v in node.values())
        elif isinstance(node, list):
            if visited + len(stack) + len(node) > 4096: raise RuntimeRefused("ENVELOPE_TOO_COMPLEX")
            size += 2 + max(0, len(node) - 1)
            stack.extend((v, depth + 1) for v in node)
        elif node is None: size += 4
        elif type(node) is bool: size += 4 if node else 5
        elif type(node) is str: size += _string_size(node)
        elif type(node) is int:
            if node.bit_length() > 217706: raise RuntimeRefused("ENVELOPE_TOO_LARGE")
            try: size += len(str(node))
            except ValueError: raise RuntimeRefused("INVALID_ENVELOPE") from None
        elif type(node) is float and math.isfinite(node): size += len(repr(node))
        else: raise RuntimeRefused("INVALID_ENVELOPE")
        if size > 65536: raise RuntimeRefused("ENVELOPE_TOO_LARGE")
    keys = {"schema_version", "request_id", "target_role", "target_generation", "action", "payload", "actor"}
    roles = {"supervisor", "coordinator", "evaluation", "execution", "watchdog", "recovery"}
    if (not isinstance(value, dict) or set(value) != keys or type(value["schema_version"]) is not int
            or value["schema_version"] != 1 or not _uuid(value["request_id"])
            or not isinstance(value["target_role"], str) or value["target_role"] not in roles
            or type(value["target_generation"]) is not int or not 1 <= value["target_generation"] < 2**63
            or not isinstance(value["action"], str) or not re.fullmatch(r"[a-z][a-z_.]{0,63}", value["action"])
            or not isinstance(value["payload"], dict) or not isinstance(value["actor"], dict)):
        raise RuntimeRefused("INVALID_ENVELOPE")
    actor = value["actor"]
    if actor.get("kind") == "operator" and set(actor) == {"kind"}: return
    if (actor.get("kind") == "worker" and set(actor) == {"kind", "role", "instance_id", "generation"}
            and isinstance(actor["role"], str) and actor["role"] in roles and _uuid(actor["instance_id"])
            and type(actor["generation"]) is int and 1 <= actor["generation"] < 2**63): return
    raise RuntimeRefused("INVALID_ENVELOPE")


def _string_size(value):
    if len(value) > 65534: raise RuntimeRefused("ENVELOPE_TOO_LARGE")
    size = 2
    for char in value:
        code = ord(char)
        if char in '\\"\b\t\n\f\r': size += 2
        elif code < 32 or 127 < code <= 65535: size += 6
        elif code > 65535: size += 12
        else: size += 1
        if size > 65536: raise RuntimeRefused("ENVELOPE_TOO_LARGE")
    return size


def start_role_pipe(lease, allowed_commands):
    from .owners import require_live_owner
    require_live_owner(lease)
    # Named-pipe DACLs, overlapped I/O, native mutual peer checks and private
    # bootstrap delivery must be implemented and qualified in Task 3B.
    raise RuntimeRefused("NATIVE_PIPE_UNVERIFIED")
