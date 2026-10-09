"""Private inherited startup channel and scoped, effect-free worker inspection.

The channel is a preconnected overlapped named pipe, with a random unpublished
name. Only its client handle is inherited. Anonymous pipes cannot provide the
required overlapped deadlines. This is not a launcher or a Job isolation gate.
"""
from contextlib import contextmanager
from dataclasses import asdict, dataclass, replace
import hashlib
import hmac
import json
import os
import re
import threading
from uuid import uuid4
import weakref
from compertum.domain import ProcessIdentity, capability_for
from .errors import RuntimeRefused
from .identity import PeerObservation
from .ipc import PeerRegistration, ScopedCapability, encode_envelope, decode_envelope

_ROLE_COMMANDS = {"watchdog": frozenset({"status", "pause_research"}),
    **{role: frozenset({"status", "checkpoint"})
       for role in ("coordinator", "evaluation", "execution", "recovery")}}
_CREDENTIALS = weakref.WeakKeyDictionary()
_CREDENTIAL_LOCK = threading.RLock()
_INHERIT_LOCK = threading.Lock()


def validate_worker_commands(role, commands):
    if (not isinstance(role, str) or role not in _ROLE_COMMANDS
            or not isinstance(commands, frozenset) or not commands
            or not commands <= _ROLE_COMMANDS[role]
            or any(capability_for(x).exit_code != 0 for x in commands)):
        raise RuntimeRefused("WORKER_COMMAND_DENIED")


def _secret(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise RuntimeRefused("CAPABILITY_DENIED")
    return value


def _load(raw, maximum, reason):
    if not isinstance(raw, bytes) or not 0 < len(raw) <= maximum: raise RuntimeRefused(reason)
    def pairs(values):
        result = {}
        for key, value in values:
            if key in result: raise ValueError()
            result[key] = value
        return result
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (UnicodeError, ValueError, RecursionError): raise RuntimeRefused(reason) from None


@dataclass(frozen=True, repr=False)
class BootstrapPacket:
    """Wire content only. Constructing one never enrolls a native worker."""
    supervisor: PeerRegistration
    target: PeerRegistration
    child: PeerRegistration
    commands: frozenset
    secret: str

    def __post_init__(self):
        peers = (self.supervisor, self.target, self.child)
        if (any(not isinstance(p, PeerRegistration) or p.subject_kind != "worker" for p in peers)
                or self.supervisor.identity.role != "supervisor"
                or len({(p.project_id, p.identity.operator_sid, p.logon_sid) for p in peers}) != 1):
            raise RuntimeRefused("BOOTSTRAP_DENIED")
        validate_worker_commands(self.child.identity.role, self.commands)
        _secret(self.secret)

    def __repr__(self): return "<BootstrapPacket private>"
    def __getstate__(self): raise RuntimeRefused("PRIVATE_CAPABILITY")


def encode_bootstrap(packet):
    if not isinstance(packet, BootstrapPacket): raise RuntimeRefused("BOOTSTRAP_DENIED")
    packet.__post_init__()
    data = {"schema_version": 1, "supervisor": asdict(packet.supervisor),
        "target": asdict(packet.target), "child": asdict(packet.child),
        "commands": sorted(packet.commands), "capability": packet.secret}
    raw = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    if len(raw) > 8192: raise RuntimeRefused("BOOTSTRAP_DENIED")
    return raw


def _registration(value):
    if (not isinstance(value, dict) or set(value) != {"identity", "logon_sid", "project_id", "generation", "subject_kind"}
            or not isinstance(value["identity"], dict)):
        raise RuntimeRefused("BOOTSTRAP_DENIED")
    return PeerRegistration(**{**value, "identity": ProcessIdentity(**value["identity"])})


def decode_bootstrap(raw, *, expected_supervisor, observed_supervisor, observed_child):
    from ._pipes import verify_peer
    value = _load(raw, 8192, "BOOTSTRAP_DENIED")
    try:
        if (not isinstance(value, dict) or set(value) != {"schema_version", "supervisor", "target", "child", "commands", "capability"}
                or type(value["schema_version"]) is not int or value["schema_version"] != 1
                or not isinstance(value["commands"], list) or not 1 <= len(value["commands"]) <= 2
                or any(not isinstance(x, str) for x in value["commands"])
                or len(set(value["commands"])) != len(value["commands"])):
            raise RuntimeRefused("BOOTSTRAP_DENIED")
        packet = BootstrapPacket(_registration(value["supervisor"]), _registration(value["target"]),
            _registration(value["child"]), frozenset(value["commands"]), value["capability"])
    except (TypeError, ValueError, KeyError): raise RuntimeRefused("BOOTSTRAP_DENIED") from None
    if packet.supervisor != expected_supervisor: raise RuntimeRefused("PEER_MISMATCH")
    verify_peer(packet.supervisor, observed_supervisor)
    verify_peer(packet.child, observed_child)
    if packet.child.identity.creation_filetime < packet.supervisor.identity.creation_filetime:
        raise RuntimeRefused("PEER_MISMATCH")
    return packet


def encode_worker_frame(value, secret):
    _secret(secret)
    envelope = encode_envelope(value)
    if value["actor"]["kind"] != "worker": raise RuntimeRefused("ROLE_DENIED")
    raw = b'{"capability":"' + secret.encode("ascii") + b'","envelope":' + envelope + b'}'
    if len(raw) > 65536: raise RuntimeRefused("ENVELOPE_TOO_LARGE")
    return raw


def decode_request_frame(raw):
    value = _load(raw, 65536, "INVALID_ENVELOPE")
    if isinstance(value, dict) and set(value) == {"envelope", "capability"}:
        secret = _secret(value["capability"])
        envelope = decode_envelope(encode_envelope(value["envelope"]))
        if envelope["actor"]["kind"] != "worker": raise RuntimeRefused("ROLE_DENIED")
        return envelope, secret
    return decode_envelope(raw), None


def _observation(api, process):
    pid = api.GetProcessId(process.get())
    sid, logon = api.token_sids(process)
    if not pid or api.WaitForSingleObject(process.get(), 0) != 258: raise RuntimeRefused("PEER_UNVERIFIED")
    return PeerObservation(pid, api.creation_time(process), sid, logon)


@contextmanager
def _target_scope(endpoint):
    from .ipc import RoleEndpoint
    from .owners import _owner_scope
    from .owner_channel import RemoteRoleEndpoint, _remote_scope
    if type(endpoint) is RemoteRoleEndpoint:
        with _remote_scope(endpoint): yield
    elif isinstance(endpoint, RoleEndpoint):
        with _owner_scope(endpoint.lease) as guard:
            if endpoint not in guard.resources or endpoint.closed or endpoint._owner_channel is not None:
                raise RuntimeRefused("ENDPOINT_UNVERIFIED")
            yield
    else: raise RuntimeRefused("ENDPOINT_UNVERIFIED")


def prepare_bootstrap(supervisor, endpoint, *, role, generation, commands):
    from .owners import _owner_scope
    from ._pipes import NativePipeAPI, deadline_after
    with _owner_scope(supervisor) as parent:
        if supervisor.identity.role != "supervisor": raise RuntimeRefused("ROLE_DENIED")
        validate_worker_commands(role, commands)
        if type(generation) is not int or not 1 <= generation < 2**63: raise RuntimeRefused("BOOTSTRAP_DENIED")
        with _target_scope(endpoint), endpoint._lock:
            target = endpoint.descriptor.registration
            if (target.project_id != supervisor.project_id
                    or (parent.project.operator_sid, parent.project.logon_sid) !=
                       (target.identity.operator_sid, target.logon_sid)
                    or getattr(endpoint, "supervisor", supervisor) is not supervisor
                    or not commands <= endpoint.allowed_commands
                    or len(endpoint._offers) >= 64):
                raise RuntimeRefused("BOOTSTRAP_DENIED")
            registration = PeerRegistration(supervisor.identity, parent.project.logon_sid,
                supervisor.project_id, supervisor.generation, "worker")
            route = replace(registration, identity=replace(supervisor.identity, process_instance_id=str(uuid4())))
            api = NativePipeAPI(); server = api.server(route); client = None
            try:
                client = api.client(route)
                api.connect(server, deadline_after(5))
                offer = BootstrapOffer(supervisor, endpoint, registration, role, generation, commands, api, server, client)
                endpoint._offers.append(offer)
                parent.resources.append(offer)
                return offer
            except BaseException:
                try:
                    if client is not None: client.close()
                finally: server.close()
                raise


class BootstrapOffer:
    """Owned private channel. The caller must use an explicit handle-list launch.

    GetNamedPipeClientProcessId on an inherited connection names its original
    opener, not the child. Child binding instead observes the launcher's retained
    native process handle plus parentage. Normal worker requests open a new pipe.
    """
    def __init__(self, supervisor, endpoint, registration, role, generation, commands, api, server, client):
        self.supervisor = supervisor; self.endpoint = endpoint; self.registration = registration
        self.role = role; self.generation = generation; self.commands = commands
        self.api = api; self.server = server; self.client = client
        self.closed = False; self.launched = False; self.delivered = False; self.enrollment = None

    def __repr__(self): return "<BootstrapOffer private>"
    def __getstate__(self): raise RuntimeRefused("PRIVATE_CAPABILITY")

    @contextmanager
    def inheritance(self):
        from .owners import _owner_scope
        with _INHERIT_LOCK, _owner_scope(self.supervisor), _target_scope(self.endpoint), self.endpoint._lock:
            if self.closed or self.launched: raise RuntimeRefused("BOOTSTRAP_DENIED")
            self.launched = True
            try:
                self.api.set_inheritable(self.client, True)
                yield self.client.get()
            except BaseException:
                self.close(); raise
            finally:
                try:
                    if not self.client.closed:
                        try: self.api.set_inheritable(self.client, False)
                        finally: self.client.close()
                except BaseException:
                    # A failed inheritance reset or client-copy disposal must
                    # retire the entire offer, even after a successful spawn.
                    self.close()
                    raise

    def deliver(self, native_child_handle, *, timeout=5):
        from .owners import _owner_scope
        from ._pipes import deadline_after
        from ._windows import OwnedHandle
        with _owner_scope(self.supervisor), _target_scope(self.endpoint), self.endpoint._lock:
            if self.closed or not self.launched or self.delivered or not self.client.closed:
                raise RuntimeRefused("BOOTSTRAP_DENIED")
            process = None
            try:
                deadline = deadline_after(timeout)
                if type(native_child_handle) is not int or native_child_handle <= 0: raise RuntimeRefused("PEER_UNVERIFIED")
                # Borrow the launcher's handle; never close it. Retain our own
                # native handle only after both observations agree.
                supplied = _observation(self.api, OwnedHandle(self.api, native_child_handle))
                process = self.api.open_process(supplied.pid)
                observed = _observation(self.api, process)
                if (observed != supplied or self.api.parent_pid(observed.pid) != self.supervisor.identity.pid
                        or observed.creation_filetime < self.supervisor.identity.creation_filetime
                        or (observed.operator_sid, observed.logon_sid) !=
                           (self.supervisor.identity.operator_sid, self.registration.logon_sid)):
                    raise RuntimeRefused("PEER_MISMATCH")
                identity = ProcessIdentity(str(uuid4()), observed.pid, observed.creation_filetime, observed.operator_sid, self.role)
                child = PeerRegistration(identity, observed.logon_sid, self.supervisor.project_id, self.generation, "worker")
                capability = ScopedCapability(child, self.commands)
                packet = BootstrapPacket(self.registration, self.endpoint.descriptor.registration, child, self.commands, capability.secret)
                self.enrollment = self.endpoint._enroll(self, capability, process)
                process = None  # enrollment owns the retained handle
                raw = encode_bootstrap(packet)
                self.api.write_frame(self.server, raw, deadline)
                if not hmac.compare_digest(self.api.read_frame(self.server, deadline), hashlib.sha256(raw).digest()):
                    raise RuntimeRefused("BOOTSTRAP_ACK_DENIED")
                self.delivered = True
                self.server.close()
                return child
            except BaseException:
                try:
                    if process is not None: process.close()
                finally: self.close()
                raise

    def close(self):
        with self.endpoint._lock:
            if self.closed: return
            self.closed = True
            failure = None
            resources = [self.server, self.client]
            if self.enrollment is not None:
                self.enrollment.active = False
                resources.append(self.enrollment.process)
            for resource in resources:
                try: resource.close()
                except BaseException as error:
                    if failure is None: failure = error
            if failure is not None: raise failure


class WorkerCredential:
    __slots__ = ("__weakref__",)
    def __init__(self): raise RuntimeRefused("BOOTSTRAP_DENIED")
    def __repr__(self): return "<WorkerCredential private>"
    def __getstate__(self): raise RuntimeRefused("PRIVATE_CAPABILITY")
    @property
    def registration(self): return _credential(self).child
    @property
    def target(self): return _credential(self).target
    @property
    def commands(self): return _credential(self).commands


def _credential(value):
    with _CREDENTIAL_LOCK:
        if type(value) is not WorkerCredential or value not in _CREDENTIALS: raise RuntimeRefused("BOOTSTRAP_DENIED")
        return _CREDENTIALS[value]


def receive_bootstrap(handle_value, *, expected_supervisor, timeout=5):
    from ._pipes import NativePipeAPI, deadline_after, verify_peer
    from ._windows import OwnedHandle
    api = NativePipeAPI(); deadline = deadline_after(timeout)
    if type(handle_value) is not int or handle_value <= 0: raise RuntimeRefused("BOOTSTRAP_DENIED")
    with OwnedHandle(api, handle_value) as handle:
        if not api.handle_flags(handle) & 1: raise RuntimeRefused("BOOTSTRAP_DENIED")
        api.set_inheritable(handle, False)
        with api.peer(handle, server_side=False) as observed:
            verify_peer(expected_supervisor, observed)
            with api.open_process(os.getpid()) as own:
                child = _observation(api, own)
            raw = api.read_frame(handle, deadline)
            packet = decode_bootstrap(raw, expected_supervisor=expected_supervisor,
                observed_supervisor=observed, observed_child=child)
            api.write_frame(handle, hashlib.sha256(raw).digest(), deadline)
    credential = object.__new__(WorkerCredential)
    with _CREDENTIAL_LOCK: _CREDENTIALS[credential] = packet
    return credential


def inspect_worker_request(credential, command, *, timeout=5):
    from ._pipes import NativePipeAPI, deadline_after, verify_peer
    from .ipc import authorize_envelope, decode_protocol_reply
    packet = _credential(credential)
    raw = encode_worker_frame(command, packet.secret)
    api = NativePipeAPI(); deadline = deadline_after(timeout)
    with api.client(packet.target) as handle, api.peer(handle, server_side=False) as peer:
        verify_peer(packet.target, peer)
        with api.open_process(os.getpid()) as process: observed = _observation(api, process)
        capability = ScopedCapability(packet.child, packet.commands)
        object.__setattr__(capability, "secret", packet.secret)
        expected = authorize_envelope(command, registration=packet.child, observed=observed,
            target_project_id=packet.target.project_id, target_role=packet.target.identity.role,
            target_generation=packet.target.generation, allowed_commands=packet.commands,
            capability=capability, secret=packet.secret)
        api.write_frame(handle, raw, deadline)
        reply = api.read_frame(handle, deadline)
        result = decode_protocol_reply(reply, expected)
        api.write_frame(handle, hashlib.sha256(reply).digest(), deadline)
        return result
