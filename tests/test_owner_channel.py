"""Portable remote-owner contracts, never evidence of native authentication."""
from dataclasses import replace
import json
import pytest
from compertum.runtime import owner_channel as channel
from compertum.runtime.errors import RuntimeRefused
from compertum.runtime.ipc import ScopedCapability, authorize_envelope
from test_worker_bootstrap import SUPERVISOR, TARGET, CHILD, CHILD_PEER
from test_ipc_protocol import PEER, envelope

SESSION = "a" * 64
COMMANDS = frozenset({"status"})


def worker_request():
    value = envelope()
    value["actor"] = {"kind": "worker", "role": CHILD.identity.role,
        "instance_id": CHILD.identity.process_instance_id, "generation": CHILD.generation}
    return value


def test_owner_registration_is_bound_to_the_retained_native_child_and_expected_scope():
    raw = channel.encode_owner_hello(SUPERVISOR, TARGET, COMMANDS, SESSION)
    target, session = channel.decode_owner_hello(raw, supervisor=SUPERVISOR,
        observed=PEER, role=TARGET.identity.role, commands=COMMANDS)
    assert target == TARGET and session == SESSION
    for observed in (replace(PEER, pid=999), replace(PEER, creation_filetime=999),
                     replace(PEER, logon_sid="S-1-5-5-9-9")):
        with pytest.raises(RuntimeRefused):
            channel.decode_owner_hello(raw, supervisor=SUPERVISOR, observed=observed,
                role=TARGET.identity.role, commands=COMMANDS)


@pytest.mark.parametrize("fault", ["project", "role", "commands", "schema", "extra", "duplicate", "oversize"])
def test_owner_hello_never_expands_the_launch_scope(fault):
    raw = channel.encode_owner_hello(SUPERVISOR, TARGET, COMMANDS, SESSION)
    obj = json.loads(raw)
    if fault == "project": obj["target"]["project_id"] = "b" * 64
    if fault == "role": obj["target"]["identity"]["role"] = "execution"
    if fault == "commands": obj["commands"].append("resume_research")
    if fault == "schema": obj["schema_version"] = True
    if fault == "extra": obj["extra"] = 1
    bad = json.dumps(obj).encode()
    if fault == "duplicate": bad = b'{"session":"a","session":"a"}'
    if fault == "oversize": bad = b"x" * 8193
    with pytest.raises(RuntimeRefused):
        channel.decode_owner_hello(bad, supervisor=SUPERVISOR, observed=PEER,
            role=TARGET.identity.role, commands=COMMANDS)


def test_query_requires_exact_session_sequence_generation_and_native_observation_shape():
    value = worker_request()
    raw = channel.encode_query(SESSION, 1, TARGET, CHILD_PEER, value, "b" * 64)
    observed, decoded, secret = channel.decode_query(raw, session=SESSION, sequence=1, target=TARGET)
    assert observed == CHILD_PEER and decoded == value and secret == "b" * 64
    for args in ({"session": "c" * 64}, {"sequence": 2}, {"target": replace(TARGET, generation=4)}):
        with pytest.raises(RuntimeRefused):
            channel.decode_query(raw, **{"session": SESSION, "sequence": 1, "target": TARGET, **args})
    for field, val in (("sequence", True), ("observed", {"pid": CHILD_PEER.pid}), ("extra", "x")):
        obj = json.loads(raw); obj[field] = val
        with pytest.raises(RuntimeRefused):
            channel.decode_query(json.dumps(obj).encode(), session=SESSION, sequence=1, target=TARGET)
    with pytest.raises(RuntimeRefused):
        channel.encode_query(SESSION, 1, TARGET, CHILD_PEER, envelope(), "b" * 64)


def test_private_query_frame_budget_includes_routing_and_native_observation_overhead():
    from compertum.runtime.bootstrap import encode_worker_frame
    value = worker_request(); value["payload"] = {"x": "x" * 64000}
    size = len(encode_worker_frame(value, "b" * 64))
    value["payload"]["x"] += "x" * (65536 - size)
    assert len(encode_worker_frame(value, "b" * 64)) == 65536
    with pytest.raises(RuntimeRefused, match="OWNER_CHANNEL_DENIED"):
        channel.encode_query(SESSION, 1, TARGET, CHILD_PEER, value, "b" * 64)


@pytest.mark.parametrize("fault", [None, "session", "sequence", "generation", "peer", "role", "request", "effect", "scope"])
def test_approval_is_request_bound_and_never_grants_dispatch(fault):
    value = worker_request(); cap = ScopedCapability(CHILD, COMMANDS)
    decision = authorize_envelope(value, registration=CHILD, observed=CHILD_PEER,
        target_project_id=TARGET.project_id, target_role=TARGET.identity.role,
        target_generation=TARGET.generation, allowed_commands=COMMANDS, capability=cap, secret=cap.secret)
    raw = channel.encode_approval(SESSION, 1, CHILD, COMMANDS, decision)
    # No capability may come back in a supervisor's inspection receipt.
    if cap.secret.encode() in raw: raise RuntimeRefused("FIXTURE_CAPABILITY_EXPOSURE")
    args = dict(session=SESSION, sequence=1, target=TARGET, allowed_commands=COMMANDS,
                observed=CHILD_PEER, value=value, secret=cap.secret)
    if fault == "session": args["session"] = "c" * 64
    if fault == "sequence": args["sequence"] = 2
    if fault == "generation": args["target"] = replace(TARGET, generation=4)
    if fault == "peer": args["observed"] = replace(CHILD_PEER, pid=999)
    if fault == "role": value["actor"]["role"] = "execution"
    if fault == "request": value["payload"] = {"different": True}
    if fault == "scope": args["allowed_commands"] = frozenset({"checkpoint"})
    if fault == "effect":
        obj = json.loads(raw); obj["decision"]["can_dispatch"] = True; raw = json.dumps(obj).encode()
    if fault:
        with pytest.raises(RuntimeRefused): channel.decode_approval(raw, **args)
    else:
        assert channel.decode_approval(raw, **args) == decision


def test_public_descriptor_and_constructed_objects_cannot_register_an_owner():
    from compertum.domain import OwnerLease
    from compertum.runtime.bootstrap import _target_scope
    from compertum.runtime.ipc import PipeDescriptor
    forged = OwnerLease(SUPERVISOR.project_id, 1, SUPERVISOR.identity, object())
    with pytest.raises(RuntimeRefused, match="OWNER_UNVERIFIED"):
        channel.prepare_owner_channel(forged, role="coordinator", allowed_commands=COMMANDS)
    with pytest.raises(RuntimeRefused, match="ENDPOINT_UNVERIFIED"): channel.RemoteRoleEndpoint()
    for endpoint in (PipeDescriptor(TARGET), object.__new__(channel.RemoteRoleEndpoint)):
        with pytest.raises(RuntimeRefused, match="ENDPOINT_UNVERIFIED"):
            with _target_scope(endpoint): pass


@pytest.mark.skipif(__import__("os").name == "nt", reason="cloud refusal test")
def test_cloud_numeric_handle_does_not_create_remote_owner_authority():
    with pytest.raises(RuntimeRefused, match="NATIVE_WINDOWS_UNAVAILABLE"):
        channel.receive_owner_channel(123, expected_supervisor=SUPERVISOR, endpoint=object())


def fake_handle(value):
    from types import SimpleNamespace
    handle = SimpleNamespace(closed=False, get=lambda: value)
    def close(): handle.closed = True
    handle.close = close
    return handle


@pytest.fixture
def remote(monkeypatch):
    """Injected native observations and lease scope, never native evidence."""
    from contextlib import contextmanager
    from types import SimpleNamespace
    import threading
    from compertum.runtime import owners
    from compertum.runtime.ipc import PipeDescriptor, _WorkerEnrollment
    active = []
    @contextmanager
    def scope(lease):
        active.append(lease)
        try: yield
        finally: active.pop()
    monkeypatch.setattr(owners, "_owner_scope", scope)
    item = object.__new__(channel.RemoteRoleEndpoint)
    item.supervisor = object(); item.descriptor = PipeDescriptor(TARGET); item.allowed_commands = COMMANDS
    item.closed = False; item._lock = threading.RLock(); item._offers = []
    item.session = SESSION; item.sequence = 1; item.handle = fake_handle(1); item.process = fake_handle(2)
    worker = fake_handle(3); cap = ScopedCapability(CHILD, COMMANDS)
    item._workers = {(CHILD_PEER.pid, CHILD_PEER.creation_filetime): _WorkerEnrollment(cap, worker, item.supervisor)}
    item.api = SimpleNamespace()
    monkeypatch.setattr(channel, "_observation", lambda api, h: PEER if h is item.process else CHILD_PEER)
    channel._REMOTES[item] = True
    try: yield item, cap, active
    finally: item.close()


def test_supervisor_scope_covers_the_entire_approval_including_remote_public_ack(remote):
    import hashlib
    item, cap, active = remote
    value = worker_request(); queries = [channel.encode_query(SESSION, 1, TARGET, CHILD_PEER, value, cap.secret)]
    sent = []
    def read(handle, deadline):
        assert active == [item.supervisor]
        return queries.pop() if queries else hashlib.sha256(sent[0]).digest()
    def write(handle, raw, deadline):
        assert active == [item.supervisor]
        sent.append(raw)
    item.api.read_frame = read; item.api.write_frame = write
    result = item.authorize_once()
    assert not result.can_dispatch and item.sequence == 2 and not active and not item.closed


@pytest.mark.parametrize("fault", ["operator", "unenrolled", "revoked", "wrong_secret", "sequence", "ack", "interrupt"])
def test_remote_approval_failure_permanently_retires_session(remote, fault):
    item, cap, _ = remote
    value = worker_request()
    query = channel.encode_query(SESSION, 2 if fault == "sequence" else 1, TARGET,
                                CHILD_PEER, value, "0" * 64 if fault == "wrong_secret" else cap.secret)
    if fault == "operator":
        obj = json.loads(query); obj["request"] = envelope(); query = json.dumps(obj).encode()
    if fault == "unenrolled": item._workers.clear()
    if fault == "revoked": next(iter(item._workers.values())).active = False
    queue = [query, b"incorrect acknowledgement"]
    def read(*args):
        if fault == "interrupt": raise KeyboardInterrupt()
        return queue.pop(0)
    item.api.read_frame = read; item.api.write_frame = lambda *args: None
    with pytest.raises(KeyboardInterrupt if fault == "interrupt" else RuntimeRefused): item.authorize_once()
    assert item.closed and item.handle.closed and item.process.closed
    with pytest.raises(RuntimeRefused, match="ENDPOINT_UNVERIFIED"): item.authorize_once()


def test_remote_owner_waits_for_public_ack_before_acknowledging_supervisor(monkeypatch):
    import hashlib
    from contextlib import contextmanager
    from types import SimpleNamespace
    from compertum.runtime import owners
    from compertum.runtime.ipc import RoleEndpoint, PipeDescriptor, encode_protocol_reply
    from compertum.runtime.bootstrap import encode_worker_frame
    lease = SimpleNamespace(project_id=TARGET.project_id, identity=TARGET.identity, generation=TARGET.generation)
    @contextmanager
    def scope(_): yield SimpleNamespace(project=SimpleNamespace(operator_sid=TARGET.identity.operator_sid, logon_sid=TARGET.logon_sid))
    @contextmanager
    def peer(*a, **kw): yield CHILD_PEER
    monkeypatch.setattr(owners, "_owner_scope", scope)
    monkeypatch.setattr(owners, "require_live_owner", lambda _: None)
    public = []; private = []; cap = ScopedCapability(CHILD, COMMANDS); value = worker_request()
    decision = authorize_envelope(value, registration=CHILD, observed=CHILD_PEER,
        target_project_id=TARGET.project_id, target_role=TARGET.identity.role, target_generation=TARGET.generation,
        allowed_commands=COMMANDS, capability=cap, secret=cap.secret)
    approval = channel.encode_approval(SESSION, 1, CHILD, COMMANDS, decision)
    acked = []
    def read_public(*args):
        if not public: return encode_worker_frame(value, cap.secret)
        assert len(private) == 1  # query only; no private approval ACK yet
        acked.append(True)
        return hashlib.sha256(encode_protocol_reply(decision)).digest()
    def write_private(handle, raw, deadline):
        if private: assert acked
        private.append(raw)
    api = SimpleNamespace(connect=lambda *a: None, disconnect=lambda *a: None, peer=peer,
                          read_frame=read_public, write_frame=lambda h, raw, d: public.append(raw))
    endpoint = RoleEndpoint(lease, PipeDescriptor(TARGET), COMMANDS, api, fake_handle(1))
    control = SimpleNamespace(write_frame=write_private, read_frame=lambda *a: approval)
    endpoint._owner_channel = channel._OwnerChannel(endpoint, control, fake_handle(2), SESSION)
    assert endpoint.inspect_once() == decision
    assert private[-1] == hashlib.sha256(approval).digest()
    endpoint.close()
    assert endpoint.closed and endpoint._owner_channel.closed


@pytest.mark.parametrize("failure_at", ["reset", "close"])
def test_owner_inheritance_finalization_failure_retires_whole_offer(monkeypatch, failure_at):
    from contextlib import contextmanager
    from types import SimpleNamespace
    from compertum.runtime import owners
    @contextmanager
    def scope(_): yield
    monkeypatch.setattr(owners, "_owner_scope", scope)
    server = fake_handle(1); client = fake_handle(2)
    def reset(h, flag):
        if not flag and failure_at == "reset": raise KeyboardInterrupt()
    if failure_at == "close":
        def close(): client.closed = True; raise KeyboardInterrupt()
        client.close = close
    item = channel.OwnerChannelOffer(object(), SUPERVISOR, "coordinator", COMMANDS,
                                     SimpleNamespace(set_inheritable=reset), server, client)
    with pytest.raises(KeyboardInterrupt):
        with item.inheritance(): pass
    assert item.closed and client.closed and server.closed


@pytest.mark.parametrize("fault", ["timeout", "malformed", "wrong_role", "bad_ack"])
def test_failed_owner_hello_keeps_identified_launched_child_out_of_operator_fallback(monkeypatch, fault):
    from contextlib import contextmanager
    from types import SimpleNamespace
    from compertum.runtime import ipc, owners
    from compertum.runtime.identity import PeerObservation
    from compertum.runtime.ipc import RoleEndpoint, PipeDescriptor
    @contextmanager
    def scope(_): yield
    monkeypatch.setattr(owners, "_owner_scope", scope)
    monkeypatch.setattr(ipc, "_WORKER_IDENTITIES", set())
    identity = replace(TARGET.identity, pid=999, creation_filetime=300)
    launched = replace(TARGET, identity=identity)
    observed = PeerObservation(999, 300, identity.operator_sid, TARGET.logon_sid)
    monkeypatch.setattr(channel, "_observation", lambda *args: observed)
    process = fake_handle(3); server = fake_handle(1); client = fake_handle(2); client.close()
    wrong = replace(launched, identity=replace(identity, role="execution")) if fault == "wrong_role" else launched
    raw = channel.encode_owner_hello(SUPERVISOR, wrong, COMMANDS, SESSION)
    if fault == "malformed": raw = b'{"wrong":"hello"}'
    queue = [raw, b"incorrect acknowledgement"]
    def read(*args):
        if fault == "timeout": raise RuntimeRefused("PIPE_DEADLINE_EXCEEDED")
        return queue.pop(0)
    api = SimpleNamespace(open_process=lambda _: process, parent_pid=lambda _: SUPERVISOR.identity.pid,
        read_frame=read, write_frame=lambda *args: None)
    lease = SimpleNamespace(identity=SUPERVISOR.identity)
    offer = channel.OwnerChannelOffer(lease, SUPERVISOR, TARGET.identity.role, COMMANDS, api, server, client)
    offer.launched = True
    with pytest.raises(RuntimeRefused): offer.accept(123)
    assert offer.closed and process.closed
    local_lease = SimpleNamespace(project_id=TARGET.project_id, identity=TARGET.identity, generation=TARGET.generation)
    local = RoleEndpoint(local_lease, PipeDescriptor(TARGET), COMMANDS, object(), object())
    with pytest.raises(RuntimeRefused, match="ROLE_DENIED"):
        local._authorize_peer(envelope(), observed, None)
