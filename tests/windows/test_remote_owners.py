"""Actual separate supervisor/owner/worker processes. Skips stay UNVERIFIED."""
from dataclasses import asdict
import json
import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4
import pytest
from fixture_processes import python_process
from test_bootstrap import launch as launch_worker, finish
from test_ipc import launch as launch_operator
from fixture_files import publish_gate

pytestmark = pytest.mark.skipif(os.name != "nt", reason="NATIVE_WINDOWS_UNAVAILABLE")
ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def supervisor():
    from compertum.runtime.identity import resolve_project
    from compertum.runtime.owners import acquire_owner, release_owner, _LEASES
    root = ROOT / ".cache/test-runs" / ("native-remote-" + str(uuid4())); root.mkdir(parents=True)
    project = resolve_project(root); lease = acquire_owner(project, "supervisor")
    children = []
    try: yield root, project, lease, children
    finally:
        if lease in _LEASES: release_owner(lease)
        for proc in children:
            if proc.poll() is None: proc.terminate()
            proc.communicate(timeout=3)


def launch_owner(state, role="coordinator", claimed_role=None, operator_target=None):
    from compertum.runtime.owner_channel import prepare_owner_channel
    root, _, lease, children = state
    offer = prepare_owner_channel(lease, role=role, allowed_commands=frozenset({"status", "resume_research"}))
    gate = root / (str(uuid4()) + ".go"); config = root / (str(uuid4()) + ".json")
    values = {"root": str(root), "role": claimed_role or role,
        "commands": sorted(offer.commands), "supervisor": asdict(offer.registration), "gate": str(gate)}
    if operator_target is not None: values["operator_target"] = asdict(operator_target)
    config.write_text(json.dumps(values))
    env = {k: v for k, v in os.environ.items() if k.upper() in {"SYSTEMROOT", "WINDIR"}}
    env["PYTHONPATH"] = str(ROOT / "src"); env["PYTHONDONTWRITEBYTECODE"] = "1"
    with offer.inheritance() as handle:
        assert offer.api.handle_flags(offer.client) & 1 and not offer.api.handle_flags(offer.server) & 1
        startup = subprocess.STARTUPINFO(); startup.lpAttributeList = {"handle_list": [handle]}
        proc = python_process(["-B", str(ROOT / "tests/helpers/owner_child.py"), str(handle), str(config)],
            cwd=ROOT, env=env, close_fds=True, startupinfo=startup, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    children.append(proc)
    remote = offer.accept(int(proc._handle))
    assert remote.descriptor.registration.identity.pid == proc.pid != os.getpid()
    return proc, remote, gate


def worker(state, remote, mode="normal"):
    root, project, lease, children = state
    proc, offer, gate = launch_worker((root, project, lease, None, remote), mode)
    children.append(proc)
    assert proc.pid not in {os.getpid(), remote.descriptor.registration.identity.pid}
    return proc, offer, gate


def test_separate_native_owner_and_worker_receive_only_scoped_inspection(supervisor):
    owner, remote, owner_gate = launch_owner(supervisor)
    child, _, worker_gate = worker(supervisor, remote)
    publish_gate(owner_gate, {}); publish_gate(worker_gate, {})
    decision = remote.authorize_once()
    code, received = finish(child); owner_code, owner_result = finish(owner)
    assert code == owner_code == 0
    assert received["request_id"] == owner_result["request_id"] == decision.request_id
    assert not decision.can_dispatch and remote.sequence == 2


def test_unknown_operator_is_denied_at_remote_owner_without_classification_fallback(supervisor):
    owner, remote, gate = launch_owner(supervisor)
    child = launch_operator(supervisor[0], remote.descriptor, action="resume_research", raw=True)
    supervisor[-1].append(child); publish_gate(gate, {})
    assert finish(owner) == (3, {"status": "ROLE_DENIED", "can_dispatch": False})
    assert finish(child)[0] == 3


def test_worker_cannot_claim_operator_at_another_native_owner(supervisor):
    first, first_remote, _ = launch_owner(supervisor)
    second, second_remote, second_gate = launch_owner(supervisor, "execution")
    child, _, gate = worker(supervisor, first_remote, "operator")
    publish_gate(second_gate, {}); publish_gate(gate, {"target": asdict(second_remote.descriptor.registration)})
    assert finish(second) == (3, {"status": "ROLE_DENIED", "can_dispatch": False})
    assert finish(child)[0] == 3
    first.terminate(); first.communicate(timeout=3)


def test_live_supervisor_process_loses_remote_authority_when_its_lease_is_released(supervisor):
    from compertum.runtime.owners import release_owner
    from compertum.runtime.errors import RuntimeRefused
    owner, remote, gate = launch_owner(supervisor)
    child, offer, child_gate = worker(supervisor, remote)
    release_owner(supervisor[2])
    assert remote.closed and offer.closed and not offer.enrollment.active
    publish_gate(gate, {}); publish_gate(child_gate, {})
    with pytest.raises(RuntimeRefused): remote.authorize_once()
    assert finish(owner)[0] == finish(child)[0] == 3


def test_target_release_closes_private_channel_and_rejects_old_worker(supervisor):
    from compertum.runtime.errors import RuntimeRefused
    owner, remote, gate = launch_owner(supervisor)
    child, _, child_gate = worker(supervisor, remote)
    publish_gate(gate, {"action": "release"})
    assert finish(owner) == (0, {"status": "RELEASED", "endpoint_closed": True, "can_dispatch": False})
    publish_gate(child_gate, {})
    with pytest.raises(RuntimeRefused): remote.authorize_once()
    assert remote.closed and finish(child)[0] == 3


@pytest.mark.parametrize("action", ["stale_session", "stale_sequence"])
def test_old_session_or_sequence_cannot_authorize_a_worker(supervisor, action):
    from compertum.runtime.errors import RuntimeRefused
    owner, remote, gate = launch_owner(supervisor)
    child, _, child_gate = worker(supervisor, remote)
    publish_gate(gate, {"action": action}); publish_gate(child_gate, {})
    with pytest.raises(RuntimeRefused, match="OWNER_CHANNEL_DENIED"): remote.authorize_once()
    assert remote.closed and finish(owner)[0] == finish(child)[0] == 3


def test_owner_registration_cannot_change_the_role_allowed_by_the_supervisor(supervisor):
    from compertum.runtime.errors import RuntimeRefused
    with pytest.raises(RuntimeRefused, match="OWNER_CHANNEL_DENIED"):
        launch_owner(supervisor, "coordinator", claimed_role="execution")
    assert finish(supervisor[-1][-1])[0] == 3


def test_wrong_public_ack_also_retires_supervisor_approval(supervisor):
    from compertum.runtime.errors import RuntimeRefused
    owner, remote, gate = launch_owner(supervisor)
    child, _, child_gate = worker(supervisor, remote, "bad_ack")
    publish_gate(gate, {}); publish_gate(child_gate, {})
    with pytest.raises(RuntimeRefused): remote.authorize_once()
    assert remote.closed and finish(owner)[0] == finish(child)[0] == 3


def test_replacement_owner_rejects_the_previous_generation_worker_capability(supervisor):
    from compertum.runtime.errors import RuntimeRefused
    first, old, first_gate = launch_owner(supervisor)
    child, offer, child_gate = worker(supervisor, old, "raw")
    publish_gate(first_gate, {"action": "release"})
    assert finish(first)[0] == 0
    old.close(); first._handle.Close()  # release every parent reference to the old process object
    assert offer.closed and not offer.enrollment.active
    second, new, second_gate = launch_owner(supervisor)
    assert new.descriptor.registration.generation == old.descriptor.registration.generation + 1
    publish_gate(second_gate, {})
    publish_gate(child_gate, {"target": asdict(new.descriptor.registration)})
    with pytest.raises(RuntimeRefused, match="CAPABILITY_DENIED"): new.authorize_once()
    assert new.closed and finish(second)[0] == finish(child)[0] == 3


def test_failed_owner_registration_cannot_fall_back_to_colocated_operator_rights(supervisor):
    from compertum.runtime.ipc import start_role_pipe
    from compertum.runtime.errors import RuntimeRefused
    local = start_role_pipe(supervisor[2], frozenset({"resume_research"}))
    with pytest.raises(RuntimeRefused, match="OWNER_CHANNEL_DENIED"):
        launch_owner(supervisor, claimed_role="execution", operator_target=local.descriptor.registration)
    with pytest.raises(RuntimeRefused, match="ROLE_DENIED"): local.inspect_once()
    assert finish(supervisor[-1][-1])[0] == 3
