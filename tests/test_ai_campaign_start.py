"""Explicit reviewed starts retain approval and duplicate-request protection."""
from compertum.coordinator import Coordinator
import hashlib
import json
from dataclasses import replace
from uuid import uuid4
import pytest
from test_ai_campaign_registration import setup, register
from test_prepared_campaign import prepared
from test_persistence import owned
from test_clean_pair import pair_inputs
from test_environment_manifest import environment
from compertum.events import canonical
from compertum.runtime.ipc import ProtocolDecision
from compertum.runtime.errors import RuntimeRefused


def test_start_operation_exists():
    assert callable(getattr(Coordinator, 'start_reviewed_campaign', None))


def ready(prepared):
    parts = setup(prepared)
    registered = register(parts)
    c, controller = parts[:2]
    controller.cooperative = True
    with c.store.conn:
        c._state('research_state', 'RUNNING')
    payload = dict(registration_request_id=registered['request_id'],
        run_id=parts[-1]['run_id'], approval='START_FIRST_RESEARCH_UNIT')
    return parts, payload


def decision(c, payload):
    value = dict(subject='a'*64, action='start_reviewed_campaign', payload=payload,
        target_role='coordinator', target_generation=c.store.lease.generation,
        project_id=c.store.lease.project_id)
    return ProtocolDecision(str(uuid4()), 'a'*64, hashlib.sha256(canonical(value)).hexdigest(), c.store.lease.generation)


def start(parts, payload, approval=None):
    return parts[0].start_reviewed_campaign(approval or decision(parts[0], payload), payload, controller=parts[1])


@pytest.mark.parametrize('gate', ['approval', 'binding', 'generation', 'paused', 'health', 'recovery', 'busy', 'capacity'])
def test_refusal_keeps_campaign_paused(prepared, monkeypatch, gate):
    parts, payload = ready(prepared)
    c, controller = parts[:2]
    approval = decision(c, payload)
    if gate == 'approval':
        payload = dict(payload, approval='REGISTER_PAUSED_CAMPAIGN')
    elif gate == 'binding':
        approval = replace(approval, payload_hash='b'*64)
    elif gate == 'generation':
        approval = replace(approval, target_generation=approval.target_generation+1)
    elif gate == 'paused':
        with c.store.conn: c._state('research_state', 'PAUSED')
    elif gate == 'health':
        c.health = lambda: dict(status='FAILED')
    elif gate == 'recovery':
        controller.last_operation_error = dict(recovery_required=True)
    elif gate == 'busy':
        controller.active = object()
    elif gate == 'capacity':
        monkeypatch.setattr(controller.storage, '_capacity', lambda *a: (_ for _ in ()).throw(RuntimeRefused('STORAGE_TEST_REFUSAL')))
    with pytest.raises(RuntimeRefused): start(parts, payload, approval)
    assert controller.runs.summary(payload['run_id'])['state'] == 'PAUSED'
    assert not controller.runs.summary(payload['run_id'])['attempts']
    assert c.store.conn.execute("SELECT count(*) FROM control_requests WHERE action='start_reviewed_campaign'").fetchone()[0] == 0


def test_pending_repeat_and_second_request_never_dispatch(prepared):
    parts, payload = ready(prepared)
    approval = decision(parts[0], payload)
    first = start(parts, payload, approval)
    pending = parts[1].pending
    assert first['state'] == 'PENDING'
    assert start(parts, payload, approval) == first
    assert parts[1].pending is pending and parts[1].active is None
    with pytest.raises(RuntimeRefused): start(parts, payload)
    parts[1].pause()
    stopped = start(parts, payload, approval)
    assert stopped['state'] == 'FAILED'
    assert parts[1].runs.summary(payload['run_id'])['state'] == 'PAUSED'
    assert parts[1].pending is None


@pytest.mark.parametrize('phase', ['VERIFYING', 'PREPARE', 'RESERVE', 'ALLOCATE', 'LAUNCH'])
def test_later_refusal_pauses_without_launch(prepared, monkeypatch, phase):
    parts, payload = ready(prepared)
    c, controller = parts[:2]
    approval = decision(c, payload)
    start(parts, payload, approval)
    for _ in range(30):
        if controller.pending.phase == phase: break
        controller.tick()
    assert controller.pending is not None and controller.pending.phase == phase
    c.health = lambda: dict(status='FAILED')
    controller.tick()
    assert controller.pending is None and controller.active is None
    assert controller.runs.summary(payload['run_id'])['state'] == 'PAUSED'
    assert not controller.runs.summary(payload['run_id'])['attempts']
    assert start(parts, payload, approval)['state'] == 'FAILED'


def test_changed_registration_link_stops_pending_start(prepared):
    parts, payload = ready(prepared)
    start(parts, payload)
    path = parts[2].storage.root/f"artifacts/runs/{parts[-1]['task_id']}/ai/campaign-link.json"
    path.write_bytes(b'{}')
    parts[1].tick()
    assert parts[1].pending is None and parts[1].active is None
    assert parts[1].runs.summary(payload['run_id'])['state'] == 'PAUSED'


def test_restart_does_not_requeue_consumed_start(prepared):
    from compertum.research import ResearchController
    parts, payload = ready(prepared)
    approval = decision(parts[0], payload)
    result = start(parts, payload, approval)
    # Lose only the transient operation. The saved request remains uncertain.
    parts[1].pending.close()
    parts[1].pending = None
    controller = ResearchController(parts[0], parts[1].storage, cooperative=True)
    restarted = (parts[0], controller, *parts[2:])
    assert start(restarted, payload, approval) == result
    assert controller.pending is None and controller.active is None
    assert controller.runs.summary(payload['run_id'])['state'] == 'PAUSED'


def test_simulated_launch_confirms_once_and_repeat_cannot_restart(prepared, monkeypatch):
    from compertum.campaign_operation import _CampaignOperation
    parts, payload = ready(prepared)
    c, controller = parts[:2]
    approval = decision(c, payload)
    launches = []
    original = _CampaignOperation.advance
    def simulated(operation):
        if operation.action == 'step' and operation.phase == 'LAUNCH':
            launches.append(operation.run_id)
            controller.active = (operation.run_id, None, object())
            return True
        return original(operation)
    monkeypatch.setattr(_CampaignOperation, 'advance', simulated)
    start(parts, payload, approval)
    for _ in range(30):
        if controller.pending is None: break
        controller.tick()
    assert controller.pending is None
    result = start(parts, payload, approval)
    assert result['state'] == 'CONFIRMED' and result['reason'] == 'FIRST_RESEARCH_UNIT_STARTED'
    controller.active = None
    assert start(parts, payload, approval) == result and launches == [payload['run_id']]
    assert controller.pending is None


def test_native_launch_refusal_preserves_pause_and_consumed_request(prepared, monkeypatch):
    import compertum.research as research
    parts, payload = ready(prepared)
    c, controller = parts[:2]
    approval = decision(c, payload)
    calls = []
    def refused(*args, **kwargs):
        calls.append(True)
        raise RuntimeRefused('NATIVE_IDENTITY_TEST_REFUSAL')
    monkeypatch.setattr(research, 'launch_bounded', refused)
    start(parts, payload, approval)
    for _ in range(30):
        if controller.pending is None: break
        controller.tick()
    assert calls == [True] and controller.active is None and controller.pending is None
    assert controller.runs.summary(payload['run_id'])['state'] == 'PAUSED'
    result = start(parts, payload, approval)
    assert result['state'] == 'FAILED' and calls == [True]


def test_receipt_failure_after_simulated_launch_latches_recovery(prepared, monkeypatch):
    from compertum.campaign_operation import _CampaignOperation
    parts, payload = ready(prepared)
    c, controller = parts[:2]
    approval = decision(c, payload)
    first = start(parts, payload, approval)
    operation = controller.pending
    original = _CampaignOperation.advance
    launches = []
    def simulated(inner):
        if inner.action == 'step' and inner.phase == 'LAUNCH':
            launches.append(inner.run_id)
            controller.active = (inner.run_id, None, object())
            return True
        return original(inner)
    monkeypatch.setattr(_CampaignOperation, 'advance', simulated)
    monkeypatch.setattr(operation, '_record', lambda **kw: (_ for _ in ()).throw(OSError('receipt write failed')))
    for _ in range(30):
        if controller.pending is None: break
        controller.tick()
    assert controller.pending is None and controller.active is not None
    assert controller.last_operation_error['recovery_required'] is True
    assert start(parts, payload, approval) == first and launches == [payload['run_id']]
    controller.active = None


@pytest.mark.parametrize('phase', ['ALLOCATE', 'LAUNCH'])
def test_cancel_after_reservation_closes_resources(prepared, phase):
    parts, payload = ready(prepared)
    c, controller = parts[:2]
    approval = decision(c, payload)
    start(parts, payload, approval)
    for _ in range(30):
        if controller.pending.phase == phase: break
        controller.tick()
    operation = controller.pending
    assert operation.phase == phase and operation.inner.grant is not None
    writer = operation.inner.writer
    controller.pause()
    assert controller.pending is None and controller.active is None
    assert writer is None or writer.closed
    assert controller.runs.summary(payload['run_id'])['state'] == 'PAUSED'
    assert start(parts, payload, approval)['state'] == 'FAILED'


def test_actual_owner_restart_after_resume_does_not_launch(tmp_path):
    import subprocess
    import sys
    from pathlib import Path
    helper = Path(__file__).parent/'helpers/review_start_restart.py'
    for stage in ('interrupt', 'recover'):
        result = subprocess.run([sys.executable, '-B', str(helper), str(tmp_path), stage],
            capture_output=True, text=True, timeout=30)
        assert result.returncode == 0, result.stderr[-4000:]
    result = json.loads((tmp_path/'start-restart-result.json').read_text())
    assert result['generation_after'] > result['generation_before']
    assert result['state'] == 'PAUSED' and result['attempts'] == [] and result['receipt_state'] == 'PENDING'
