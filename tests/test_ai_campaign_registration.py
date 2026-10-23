"""Reviewed registration remains paused and separate from execution."""
import hashlib
import json
import time
from dataclasses import replace
from uuid import uuid4
import pytest

from test_prepared_campaign import prepared
from test_persistence import owned
from test_clean_pair import pair_inputs
from test_environment_manifest import environment
from test_ai_review_plan_storage import accepted
from compertum.ai.manual import ManualBridge
from compertum.coordinator import Coordinator
from compertum.research import ResearchController
from compertum.runtime.ipc import ProtocolDecision
from compertum.runtime.errors import RuntimeRefused
from compertum.data.errors import DataError
from compertum.events import canonical


def test_registration_operation_exists():
    from compertum.coordinator import Coordinator
    assert callable(getattr(Coordinator, 'register_reviewed_campaign', None))


def setup(prepared):
    module, runs, seals, pair, args, campaign, raw = prepared
    module.register_pair(runs, pair)
    bridge = ManualBridge(runs.storage)
    b, root, task_id, receipt, selection = accepted((bridge, runs.storage.root))
    artifact = b.save_review_plan(task_id, selection)
    coordinator = Coordinator(runs.store, health=lambda: dict(status='HEALTHY', observed_monotonic=time.monotonic()))
    controller = ResearchController(coordinator, runs.storage)
    value = json.loads(pair.content)
    payload = dict(task_id=task_id, plan_sha256=artifact['sha256'], run_id=value['source']['run_id'],
        prepared_sha256=hashlib.sha256(raw).hexdigest(), seal_id=value['source']['seal_id'],
        maximum_bytes=json.loads(raw)['maximum_bytes'], approval='REGISTER_PAUSED_CAMPAIGN')
    return coordinator, controller, bridge, seals, raw, payload


def decision(coordinator, payload, **changes):
    subject = 'a'*64
    fingerprint = dict(subject=subject, action='register_reviewed_campaign', payload=payload,
        target_role='coordinator', target_generation=coordinator.store.lease.generation,
        project_id=coordinator.store.lease.project_id)
    value = ProtocolDecision(str(uuid4()), subject, hashlib.sha256(canonical(fingerprint)).hexdigest(),
        coordinator.store.lease.generation)
    return replace(value, **changes)


def register(parts, approval=None, payload=None):
    coordinator, controller, bridge, seals, raw, original = parts
    payload = original if payload is None else payload
    return coordinator.register_reviewed_campaign(approval or decision(coordinator, payload), payload,
        controller=controller, bridge=bridge, prepared_raw=raw, evaluation=seals)


def test_register_repeat_and_fixed_family(prepared):
    parts = setup(prepared)
    c, controller, bridge, seals, raw, payload = parts
    approval = decision(c, payload)
    result = register(parts, approval)
    assert result['state'] == 'CONFIRMED'
    assert result['reason'] == 'CAMPAIGN_REGISTERED_PAUSED'
    assert register(parts, approval) == result
    history = bridge.review_history(payload['task_id'], runs=controller.runs)
    assert len(history['trials']) == 12
    assert history['attempts'] == [] and history['results'] == []
    assert history['execution_authorized'] is False
    assert controller.runs.summary(payload['run_id'])['state'] == 'PAUSED'
    assert controller.runs.summary(payload['run_id'])['total_units'] == 63
    assert c.status()['research_state'] == 'PAUSED'
    assert c.store.conn.execute('SELECT count(*) FROM baseline_runs').fetchone()[0] == 1
    with pytest.raises(RuntimeRefused, match='RESEARCH_PAUSED'):
        controller.step(payload['run_id'])


@pytest.mark.parametrize('field', ['plan_sha256','prepared_sha256','run_id','seal_id','maximum_bytes','approval'])
def test_changed_approved_inputs_have_no_effect(prepared, field):
    parts = setup(prepared)
    c, controller, b, seals, raw, payload = parts
    approval = decision(c, payload)
    changed = dict(payload)
    changed[field] = 1 if field == 'maximum_bytes' else str(uuid4()) if field in ('run_id','seal_id') else '0'*64
    with pytest.raises((RuntimeRefused, DataError)):
        register(parts, approval, changed)
    assert c.store.conn.execute('SELECT count(*) FROM baseline_runs').fetchone()[0] == 0


@pytest.mark.parametrize('field', ['subject_key','target_generation','payload_hash'])
def test_changed_decision_is_refused(prepared, field):
    parts = setup(prepared)
    c = parts[0]
    approval = decision(c, parts[-1])
    changed = replace(approval, **{field: approval.target_generation+1 if field == 'target_generation' else 'b'*64})
    with pytest.raises(RuntimeRefused):
        register(parts, changed)
    assert c.store.conn.execute('SELECT count(*) FROM baseline_runs').fetchone()[0] == 0


@pytest.mark.parametrize('boundary', ['before_create','after_create','after_link'])
def test_interrupted_registration_recovers_same_campaign(prepared, monkeypatch, boundary):
    import compertum.development_seals as producer
    parts = setup(prepared)
    c, controller, bridge, seals, raw, payload = parts
    approval = decision(c, payload)
    original = producer.create_prepared_campaign
    link = bridge.link_review_campaign
    def interrupted(*args, **kwargs):
        if boundary == 'after_create':
            original(*args, **kwargs)
        raise OSError('synthetic interruption')
    def interrupted_link(*args, **kwargs):
        link(*args, **kwargs)
        raise OSError('synthetic interruption')
    with monkeypatch.context() as patch:
        if boundary == 'after_link':
            patch.setattr(bridge, 'link_review_campaign', interrupted_link)
        else:
            patch.setattr(producer, 'create_prepared_campaign', interrupted)
        with pytest.raises(OSError, match='synthetic interruption'):
            register(parts, approval)
    if boundary != 'before_create':
        with pytest.raises(RuntimeRefused, match='REGISTRATION_INCOMPLETE'):
            controller.runs.control(payload['run_id'], str(uuid4()), 'resume')
        def never_create(*args, **kwargs):
            raise AssertionError('recovery must only complete the link')
        monkeypatch.setattr(producer, 'create_prepared_campaign', never_create)
    restarted = ResearchController(c, controller.storage)
    parts = (c, restarted, ManualBridge(controller.storage), seals, raw, payload)
    result = register(parts, approval)
    assert result['state'] == 'CONFIRMED'
    assert c.store.conn.execute('SELECT count(*) FROM baseline_runs').fetchone()[0] == 1
    assert restarted.runs.summary(payload['run_id'])['attempts'] == []
    assert restarted.runs.summary(payload['run_id'])['state'] == 'PAUSED'


def test_second_request_cannot_claim_same_campaign(prepared):
    parts = setup(prepared)
    register(parts)
    with pytest.raises(RuntimeRefused, match='REGISTRATION_CONFLICT'):
        register(parts)
    assert parts[0].store.conn.execute('SELECT count(*) FROM baseline_runs').fetchone()[0] == 1


@pytest.mark.parametrize('gate', ['health','recovery','busy'])
def test_registration_keeps_admission_gates(prepared, gate):
    parts = setup(prepared)
    c, controller = parts[:2]
    if gate == 'health':
        c.health = lambda: dict(status='FAILED', observed_monotonic=time.monotonic())
    elif gate == 'recovery':
        controller.last_operation_error = dict(recovery_required=True)
    else:
        controller.active = object()
    with pytest.raises(RuntimeRefused):
        register(parts)
    assert c.store.conn.execute('SELECT count(*) FROM baseline_runs').fetchone()[0] == 0


def test_capacity_failure_keeps_pending_request(prepared, monkeypatch):
    parts = setup(prepared)
    c, controller, bridge, seals, raw, payload = parts
    approval = decision(c, payload)
    def refused(*args, **kwargs):
        raise RuntimeRefused('STORAGE_TEST_REFUSAL')
    monkeypatch.setattr(controller.storage, 'reserve_bytes', refused)
    with pytest.raises((RuntimeRefused, DataError)):
        register(parts, approval)
    row = c.store.conn.execute('SELECT receipt FROM control_requests WHERE request_id=?', (approval.request_id,)).fetchone()
    assert row and json.loads(row[0])['state'] == 'PENDING'
    assert controller.active is None and controller.pending is None


def test_changed_plan_after_interruption_blocks_recovery(prepared, monkeypatch):
    parts = setup(prepared)
    c, controller, bridge, seals, raw, payload = parts
    approval = decision(c, payload)
    with monkeypatch.context() as patch:
        patch.setattr(bridge, 'link_review_campaign', lambda *a, **k: (_ for _ in ()).throw(OSError('link failed')))
        with pytest.raises(OSError):
            register(parts, approval)
    (bridge.storage.root/f"artifacts/runs/{payload['task_id']}/ai/review-plan.json").write_bytes(b'{}')
    with pytest.raises(RuntimeRefused):
        register(parts, approval)
    with pytest.raises(RuntimeRefused, match='REGISTRATION_INCOMPLETE'):
        controller.runs.control(payload['run_id'], str(uuid4()), 'resume')
    assert controller.runs.summary(payload['run_id'])['attempts'] == []


def test_unapproved_registration_is_refused(prepared):
    parts = setup(prepared)
    c, controller, bridge, seals, raw, payload = parts
    with pytest.raises(RuntimeRefused):
        c.register_reviewed_campaign(None, payload, controller=controller, bridge=bridge,
            prepared_raw=raw, evaluation=seals)
    assert c.store.conn.execute('SELECT count(*) FROM baseline_runs').fetchone()[0] == 0


@pytest.mark.parametrize('name', ['review-plan.json', 'campaign-link.json'])
@pytest.mark.parametrize('operation', ['resume', 'prepare'])
def test_changed_confirmed_evidence_blocks_dispatch(prepared, name, operation):
    parts = setup(prepared)
    register(parts)
    c, controller, bridge, seals, raw, payload = parts
    if operation == 'prepare':
        controller.runs.control(payload['run_id'], str(uuid4()), 'resume')
    path = bridge.storage.root/f"artifacts/runs/{payload['task_id']}/ai/{name}"
    path.write_bytes(b'{}')
    with pytest.raises(RuntimeRefused):
        if operation == 'resume':
            controller.control(payload['run_id'], str(uuid4()), 'resume')
        else:
            controller.runs.prepare_campaign(payload['run_id'])
    assert controller.runs.summary(payload['run_id'])['attempts'] == []


def test_actual_owner_restart_preserves_approval_and_recovers(tmp_path):
    import subprocess
    import sys
    from pathlib import Path
    helper = Path(__file__).parent/'helpers/review_registration_restart.py'
    for stage in ('interrupt', 'recover'):
        result = subprocess.run([sys.executable, '-B', str(helper), str(tmp_path), stage],
            capture_output=True, text=True, timeout=30)
        assert result.returncode == 0, result.stderr[-4000:]
    result = json.loads((tmp_path/'restart-result.json').read_text())
    assert result['generation_after'] > result['generation_before']
    assert result['campaigns'] == 1 and result['attempts'] == [] and result['state'] == 'PAUSED'
    assert result['original_approval_preserved'] is True


def test_dispatch_gate_does_not_walk_campaign_results(prepared, monkeypatch):
    from compertum.ai.registration import require_complete
    import compertum.ai.registration as registration
    import compertum.ai.history as history
    parts = setup(prepared)
    register(parts)
    def forbidden(*args, **kwargs):
        raise AssertionError('dispatch must retain cooperative campaign verification')
    monkeypatch.setattr(history, 'read_history', forbidden)
    monkeypatch.setattr(history, '_campaign', forbidden)
    monkeypatch.setattr(registration, '_campaign', forbidden)
    require_complete(parts[1].runs, parts[-1]['run_id'])

