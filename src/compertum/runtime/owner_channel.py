"""Private, explicitly pumped owner registration; protocol inspection only.

Remote endpoints are worker-only. Every request needs fresh supervisor approval
under its live lease. Successful supervisor exchanges hold that scope through
the public receipt ACK. A timeout may follow delivery of an effect-free receipt;
it retires the session and never grants dispatch. There is no background reader,
cached lease-valid flag, production launcher, or effectful dispatch.
"""
from contextlib import contextmanager
from dataclasses import asdict, replace
import hashlib
import hmac
import json
import os
import secrets
import threading
from uuid import uuid4
import weakref
from compertum.domain import capability_for
from .bootstrap import _load, _registration, _secret, _observation, _INHERIT_LOCK
from .errors import RuntimeRefused
from .identity import PeerObservation
from .ipc import (PeerRegistration, PipeDescriptor, ScopedCapability, authorize_envelope,
                  encode_protocol_reply, decode_protocol_reply)

_REMOTES = weakref.WeakKeyDictionary()


class _OwnerReplyRefused(RuntimeRefused):
    """A validated, acknowledged owner reply; the transport remains usable."""


def _commands(value):
    if (not isinstance(value, list) or not 1 <= len(value) <= 16
            or any(not isinstance(x, str) for x in value) or len(set(value)) != len(value)
            or any(capability_for(x).exit_code != 0 for x in value)):
        raise RuntimeRefused("OWNER_CHANNEL_DENIED")
    return frozenset(value)


def _dump(value, maximum=8192):
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()
    if len(raw) > maximum: raise RuntimeRefused("OWNER_CHANNEL_DENIED")
    return raw


def _record(raw, keys, maximum=8192):
    obj = _load(raw, maximum, "OWNER_CHANNEL_DENIED")
    if (not isinstance(obj, dict) or set(obj) != keys | {"schema_version"}
            or type(obj["schema_version"]) is not int or obj["schema_version"] != 1):
        raise RuntimeRefused("OWNER_CHANNEL_DENIED")
    return obj


def _sequence(value):
    if type(value) is not int or not 1 <= value < 2**63: raise RuntimeRefused("OWNER_CHANNEL_DENIED")
    return value


def _session(obj, session, sequence):
    _secret(session); _sequence(sequence)
    if _secret(obj["session"]) != session or _sequence(obj["sequence"]) != sequence:
        raise RuntimeRefused("OWNER_CHANNEL_DENIED")


def encode_owner_hello(supervisor, target, commands, session):
    _secret(session); _commands(sorted(commands))
    return _dump({"schema_version": 1, "supervisor": asdict(supervisor), "target": asdict(target),
                  "commands": sorted(commands), "session": session})


def decode_owner_hello(raw, *, supervisor, observed, role, commands):
    from ._pipes import verify_peer
    obj = _record(raw, {"supervisor", "target", "commands", "session"})
    try:
        parent = _registration(obj["supervisor"]); target = _registration(obj["target"])
    except (TypeError, ValueError, KeyError): raise RuntimeRefused("OWNER_CHANNEL_DENIED") from None
    if (parent != supervisor or parent.identity.role != "supervisor"
            or parent.subject_kind != "worker" or target.subject_kind != "worker"
            or target.identity.role != role or role == "supervisor"
            or (target.project_id, target.identity.operator_sid, target.logon_sid) !=
               (parent.project_id, parent.identity.operator_sid, parent.logon_sid)
            or target.identity.creation_filetime < parent.identity.creation_filetime
            or _commands(obj["commands"]) != commands):
        raise RuntimeRefused("OWNER_CHANNEL_DENIED")
    verify_peer(target, observed)
    return target, _secret(obj["session"])


def encode_query(session, sequence, target, observed, value, secret):
    from .bootstrap import encode_worker_frame
    request = json.loads(encode_worker_frame(value, secret))
    return _dump({"schema_version": 1, "session": _secret(session), "sequence": _sequence(sequence),
                  "target_generation": target.generation, "observed": asdict(observed), "request": request}, 65536)


def decode_query(raw, *, session, sequence, target):
    from .bootstrap import decode_request_frame
    obj = _record(raw, {"session", "sequence", "target_generation", "observed", "request"}, 65536)
    _session(obj, session, sequence)
    if _sequence(obj["target_generation"]) != target.generation:
        raise RuntimeRefused("OWNER_CHANNEL_DENIED")
    try: observed = PeerObservation(**obj["observed"])
    except (TypeError, ValueError): raise RuntimeRefused("OWNER_CHANNEL_DENIED") from None
    if (type(observed.pid) is not int or not 0 < observed.pid < 2**32
            or type(observed.creation_filetime) is not int or not 0 < observed.creation_filetime < 2**64
            or (observed.operator_sid, observed.logon_sid) != (target.identity.operator_sid, target.logon_sid)):
        raise RuntimeRefused("PEER_MISMATCH")
    value, secret = decode_request_frame(_dump(obj["request"], 65536))
    if value["actor"]["kind"] != "worker" or secret is None: raise RuntimeRefused("ROLE_DENIED")
    return observed, value, secret


def encode_approval(session, sequence, registration, commands, decision):
    return _dump({"schema_version": 1, "session": _secret(session), "sequence": _sequence(sequence),
                  "registration": asdict(registration), "commands": sorted(commands),
                  "decision": json.loads(encode_protocol_reply(decision))})


def decode_approval(raw, *, session, sequence, target, allowed_commands, observed, value, secret):
    obj = _record(raw, {"session", "sequence", "registration", "commands", "decision"})
    _session(obj, session, sequence)
    try: registration = _registration(obj["registration"])
    except (TypeError, ValueError, KeyError): raise RuntimeRefused("OWNER_CHANNEL_DENIED") from None
    commands = _commands(obj["commands"])
    from .bootstrap import validate_worker_commands
    validate_worker_commands(registration.identity.role, commands)
    if not commands <= allowed_commands: raise RuntimeRefused("COMMAND_DENIED")
    capability = ScopedCapability(registration, commands)
    object.__setattr__(capability, "secret", _secret(secret))
    expected = authorize_envelope(value, registration=registration, observed=observed,
        target_project_id=target.project_id, target_role=target.identity.role, target_generation=target.generation,
        allowed_commands=allowed_commands, capability=capability, secret=secret)
    return decode_protocol_reply(_dump(obj["decision"], 2048), expected)


def _close_all(resources):
    failure = None
    for resource in resources:
        try: resource.close()
        except BaseException as error:
            if failure is None: failure = error
    if failure is not None: raise failure


def prepare_owner_channel(supervisor, *, role, allowed_commands):
    from .owners import _owner_scope
    from ._pipes import NativePipeAPI, deadline_after
    with _owner_scope(supervisor) as guard:
        if (supervisor.identity.role != "supervisor" or role not in
                {"coordinator", "evaluation", "execution", "watchdog", "recovery"}
                or not isinstance(allowed_commands, frozenset)
                or len([r for r in guard.resources if isinstance(r, OwnerChannelOffer)]) >= 64):
            raise RuntimeRefused("OWNER_CHANNEL_DENIED")
        _commands(sorted(allowed_commands))
        parent = PeerRegistration(supervisor.identity, guard.project.logon_sid,
                                  supervisor.project_id, supervisor.generation, "worker")
        route = replace(parent, identity=replace(parent.identity, process_instance_id=str(uuid4())))
        api = NativePipeAPI(); server = api.server(route); client = None
        try:
            client = api.client(route); api.connect(server, deadline_after(5))
            offer = OwnerChannelOffer(supervisor, parent, role, allowed_commands, api, server, client)
            guard.resources.append(offer)
            return offer
        except BaseException:
            _close_all([h for h in (client, server) if h is not None]); raise


class OwnerChannelOffer:
    def __init__(self, supervisor, registration, role, commands, api, server, client):
        self.supervisor = supervisor; self.registration = registration; self.role = role
        self.commands = commands; self.api = api; self.server = server; self.client = client
        self.closed = False; self.launched = False; self.remote = None
        self._lock = threading.RLock()

    def __repr__(self): return "<OwnerChannelOffer private>"
    def __getstate__(self): raise RuntimeRefused("PRIVATE_CAPABILITY")

    @contextmanager
    def inheritance(self):
        from .owners import _owner_scope
        with _INHERIT_LOCK, _owner_scope(self.supervisor), self._lock:
            if self.closed or self.launched: raise RuntimeRefused("OWNER_CHANNEL_DENIED")
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
                    self.close(); raise

    def accept(self, native_child_handle, *, timeout=5):
        from .owners import _owner_scope
        from ._pipes import deadline_after
        from ._windows import OwnedHandle
        with _owner_scope(self.supervisor), self._lock:
            if self.closed or not self.launched or not self.client.closed or self.remote is not None:
                raise RuntimeRefused("OWNER_CHANNEL_DENIED")
            process = None
            try:
                deadline = deadline_after(timeout)
                if type(native_child_handle) is not int or native_child_handle <= 0:
                    raise RuntimeRefused("PEER_UNVERIFIED")
                supplied = _observation(self.api, OwnedHandle(self.api, native_child_handle))
                process = self.api.open_process(supplied.pid)
                observed = _observation(self.api, process)
                if (observed != supplied or self.api.parent_pid(observed.pid) != self.supervisor.identity.pid
                        or observed.creation_filetime < self.supervisor.identity.creation_filetime
                        or (observed.operator_sid, observed.logon_sid) !=
                           (self.registration.identity.operator_sid, self.registration.logon_sid)):
                    raise RuntimeRefused("PEER_MISMATCH")
                # Classification precedes untrusted channel input. A launched
                # owner whose hello fails must not regain operator fallback.
                from .ipc import _remember_worker
                _remember_worker(observed)
                raw = self.api.read_frame(self.server, deadline)
                target, session = decode_owner_hello(raw, supervisor=self.registration, observed=observed,
                                                     role=self.role, commands=self.commands)
                ack = hashlib.sha256(raw).digest()
                self.api.write_frame(self.server, ack, deadline)
                if not hmac.compare_digest(self.api.read_frame(self.server, deadline), hashlib.sha256(ack).digest()):
                    raise RuntimeRefused("OWNER_CHANNEL_ACK_DENIED")
                remote = object.__new__(RemoteRoleEndpoint)
                remote.supervisor = self.supervisor; remote.descriptor = PipeDescriptor(target)
                remote.allowed_commands = self.commands; remote.session = session; remote.sequence = 1
                remote.api = self.api; remote.handle = self.server; remote.process = process
                remote.closed = False; remote._lock = threading.RLock(); remote._workers = {}; remote._offers = []
                _REMOTES[remote] = True
                self.remote = remote; process = None
                return remote
            except BaseException:
                try:
                    if process is not None: process.close()
                finally: self.close()
                raise

    def close(self):
        with self._lock:
            if self.closed: return
            self.closed = True
            _close_all([r for r in (self.remote, self.server, self.client) if r is not None])


@contextmanager
def _remote_scope(endpoint):
    from .owners import _owner_scope
    if type(endpoint) is not RemoteRoleEndpoint or endpoint not in _REMOTES:
        raise RuntimeRefused("ENDPOINT_UNVERIFIED")
    with _owner_scope(endpoint.supervisor), endpoint._lock:
        if endpoint.closed: raise RuntimeRefused("ENDPOINT_UNVERIFIED")
        from ._pipes import verify_peer
        try:
            verify_peer(endpoint.descriptor.registration, _observation(endpoint.api, endpoint.process))
            yield
        except _OwnerReplyRefused:
            # Recovery can hold several nested owner scopes. A domain refusal
            # acknowledged on one channel must not retire those healthy peers.
            raise
        except BaseException:
            endpoint.close(); raise


class RemoteRoleEndpoint:
    """Native-bound private authority, unlike the public routing descriptor.

    The parent explicitly pumps one request. A successful exchange holds its
    owner scope until the remote owner confirms the public client's ACK. On
    timeout the channel closes, even if an effect-free receipt was already sent.
    """
    def __init__(self): raise RuntimeRefused("ENDPOINT_UNVERIFIED")
    def __repr__(self): return "<RemoteRoleEndpoint private>"
    def __getstate__(self): raise RuntimeRefused("PRIVATE_CAPABILITY")

    def close(self):
        with self._lock:
            if self.closed: return
            self.closed = True; _REMOTES.pop(self, None)
            _close_all([*self._offers, self.handle, self.process])

    def _enroll(self, offer, capability, process):
        from .ipc import _enroll_worker
        with _remote_scope(self):
            if offer.supervisor is not self.supervisor: raise RuntimeRefused("BOOTSTRAP_DENIED")
            return _enroll_worker(self, offer, capability, process)

    def authorize_once(self, *, timeout=5):
        from ._pipes import deadline_after, verify_peer
        with _remote_scope(self):
            deadline = deadline_after(timeout)
            observed, value, secret = decode_query(self.api.read_frame(self.handle, deadline),
                session=self.session, sequence=self.sequence, target=self.descriptor.registration)
            entry = self._workers.get((observed.pid, observed.creation_filetime))
            if entry is None or not entry.active: raise RuntimeRefused("CAPABILITY_DENIED")
            # Both the retained enrollment and a fresh native observation must
            # match what the authenticated owner observed on its public pipe.
            retained = _observation(self.api, entry.process)
            if retained != observed: raise RuntimeRefused("PEER_MISMATCH")
            verify_peer(entry.capability.registration, retained)
            cap = entry.capability; target = self.descriptor.registration
            decision = authorize_envelope(value, registration=cap.registration, observed=observed,
                target_project_id=target.project_id, target_role=target.identity.role,
                target_generation=target.generation, allowed_commands=self.allowed_commands,
                capability=cap, secret=secret)
            raw = encode_approval(self.session, self.sequence, cap.registration, cap.commands, decision)
            self.api.write_frame(self.handle, raw, deadline)
            if not hmac.compare_digest(self.api.read_frame(self.handle, deadline), hashlib.sha256(raw).digest()):
                raise RuntimeRefused("OWNER_CHANNEL_ACK_DENIED")
            self.sequence += 1
            return decision


def receive_owner_channel(handle_value, *, expected_supervisor, endpoint, timeout=5):
    from .owners import _owner_scope
    from .ipc import RoleEndpoint
    from ._pipes import NativePipeAPI, deadline_after, verify_peer
    from ._windows import OwnedHandle
    api = NativePipeAPI(); deadline = deadline_after(timeout)
    if type(handle_value) is not int or handle_value <= 0: raise RuntimeRefused("OWNER_CHANNEL_DENIED")
    handle = OwnedHandle(api, handle_value)
    try:
        if not isinstance(endpoint, RoleEndpoint): raise RuntimeRefused("ENDPOINT_UNVERIFIED")
        with _owner_scope(endpoint.lease) as guard, endpoint._lock:
            if (endpoint not in guard.resources or endpoint.closed or endpoint._owner_channel is not None
                    or endpoint._workers or endpoint._offers):
                raise RuntimeRefused("OWNER_CHANNEL_DENIED")
            if not api.handle_flags(handle) & 1: raise RuntimeRefused("OWNER_CHANNEL_DENIED")
            api.set_inheritable(handle, False)
            with api.peer(handle, server_side=False) as observed:
                verify_peer(expected_supervisor, observed)
                if api.parent_pid(os.getpid()) != expected_supervisor.identity.pid:
                    raise RuntimeRefused("PEER_MISMATCH")
                target = endpoint.descriptor.registration; session = secrets.token_hex(32)
                raw = encode_owner_hello(expected_supervisor, target, endpoint.allowed_commands, session)
                with api.open_process(os.getpid()) as own:
                    decode_owner_hello(raw, supervisor=expected_supervisor, observed=_observation(api, own),
                        role=endpoint.lease.identity.role, commands=endpoint.allowed_commands)
                channel = _OwnerChannel(endpoint, api, handle, session)
                endpoint._owner_channel = channel  # worker-only before publication of any approval
                api.write_frame(handle, raw, deadline)
                ack = api.read_frame(handle, deadline)
                if not hmac.compare_digest(ack, hashlib.sha256(raw).digest()):
                    raise RuntimeRefused("OWNER_CHANNEL_ACK_DENIED")
                api.write_frame(handle, hashlib.sha256(ack).digest(), deadline)
                return channel
    except BaseException:
        try: handle.close()
        finally:
            if isinstance(endpoint, RoleEndpoint): endpoint.close()
        raise


class _OwnerChannel:
    def __init__(self, endpoint, api, handle, session):
        self.endpoint = endpoint; self.api = api; self.handle = handle; self.session = session
        self.sequence = 1; self.closed = False; self.pending = None

    def __repr__(self): return "<OwnerChannel private>"
    def __getstate__(self): raise RuntimeRefused("PRIVATE_CAPABILITY")

    def close(self):
        if self.closed: return
        self.closed = True; self.pending = None
        _close_all([self.handle, self.endpoint])

    def authorize(self, value, observed, secret, deadline):
        if self.closed or self.pending is not None: raise RuntimeRefused("OWNER_CHANNEL_DENIED")
        if value["actor"]["kind"] != "worker" or secret is None: raise RuntimeRefused("ROLE_DENIED")
        target = self.endpoint.descriptor.registration
        self.api.write_frame(self.handle, encode_query(self.session, self.sequence, target, observed, value, secret), deadline)
        raw = self.api.read_frame(self.handle, deadline)
        decision = decode_approval(raw, session=self.session, sequence=self.sequence, target=target,
            allowed_commands=self.endpoint.allowed_commands, observed=observed, value=value, secret=secret)
        self.pending = hashlib.sha256(raw).digest()
        return decision

    def finish(self, deadline):
        if self.closed or self.pending is None: raise RuntimeRefused("OWNER_CHANNEL_DENIED")
        self.api.write_frame(self.handle, self.pending, deadline)
        self.pending = None; self.sequence += 1
