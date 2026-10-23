"""Authenticated cycle control; successful first launch is simulated here."""
from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
import hashlib
import importlib
import sqlite3
from uuid import uuid4

import pytest
from test_ai_campaign_start import ready, start, decision as start_decision
from test_prepared_campaign import prepared
from test_persistence import owned
from test_clean_pair import pair_inputs
from test_environment_manifest import environment
from compertum.events import canonical
from compertum.campaign_contract import UNITS
from compertum.runtime.errors import RuntimeRefused
from compertum.runtime.ipc import ProtocolDecision


def decision(c, payload, subject='a'*64):
    body = dict(subject=subject, action='control_research_cycle', payload=payload,
        target_role='coordinator', target_generation=c.store.lease.generation,
        project_id=c.store.lease.project_id)
    return ProtocolDecision(str(uuid4()), subject, hashlib.sha256(canonical(body)).hexdigest(), c.store.lease.generation)


def setup(prepared, monkeypatch):
    module = importlib.import_module('compertum.ai.cycle')
    from compertum.campaign_operation import _CampaignOperation
    from compertum.auditor import AuditorController
    from compertum.campaign_review import CampaignReviewController
    parts, first = ready(prepared)
    c, research = parts[:2]
    original = _CampaignOperation.advance
    def simulated(operation):
        if operation.action == 'step' and operation.phase == 'LAUNCH':
            research.active = (operation.run_id, None, object())
            return True
        return original(operation)
    monkeypatch.setattr(_CampaignOperation, 'advance', simulated)
    first_decision = start_decision(c, first)
    start(parts, first, first_decision)
    for _ in range(30):
        if research.pending is None:
            break
        research.tick()
    assert start(parts, first, first_decision)['confirmed']
    research.active = None
    monkeypatch.setattr(_CampaignOperation, 'advance', original)
    cycle = module.ResearchCycleController(c, research.storage, research=research,
        auditor=AuditorController(c, research.storage), reviews=CampaignReviewController(c, research.storage))
    payload = dict(operation='approve', approval='RUN_FIXED_SYNTHETIC_CYCLE',
        cycle_id=str(uuid4()), run_id=first['run_id'],
        registration_request_id=first['registration_request_id'], first_start_request_id=first_decision.request_id,
        prepared_sha256=parts[-1]['prepared_sha256'], plan_sha256=parts[-1]['plan_sha256'],
        seal_id=parts[-1]['seal_id'], maximum_bytes=parts[-1]['maximum_bytes'],
        schedule_sha256=hashlib.sha256(canonical([asdict(u) for u in UNITS])).hexdigest(),
        deadline=(datetime.now(timezone.utc)+timedelta(seconds=1800)).isoformat(),
        scorecard_task_id=str(uuid4()), aggregate_task_id=str(uuid4()))
    return c, cycle, payload


def apply(c, cycle, payload, approved=None):
    return c.control_research_cycle(approved or decision(c, payload), payload, cycle=cycle)


def test_duplicate_cycle_request_has_one_record(prepared, monkeypatch):
    c, cycle, payload = setup(prepared, monkeypatch)
    approved = decision(c, payload)
    first = apply(c, cycle, payload, approved)
    assert apply(c, cycle, payload, approved) == first
    assert c.store.conn.execute('SELECT count(*) FROM research_cycles').fetchone()[0] == 1
    assert cycle.status(payload['cycle_id'])['record']['state'] == 'APPROVED'
    assert cycle.research.active is None and cycle.research.pending is None
    assert c.store.get_state('active_research_cycle') == payload['cycle_id']


@pytest.mark.parametrize('fault', ['approval', 'operator', 'generation', 'fingerprint', 'input', 'plan', 'seal', 'schedule', 'allowance', 'first_start', 'deadline', 'long_deadline'])
def test_approval_refusal_has_no_cycle_effect(prepared, monkeypatch, fault):
    c, cycle, payload = setup(prepared, monkeypatch)
    assert_refusal(c, cycle, payload, fault)


def assert_refusal(c, cycle, original, fault):
    payload = dict(original)
    fields = {'input': 'prepared_sha256', 'plan': 'plan_sha256', 'seal': 'seal_id',
              'schedule': 'schedule_sha256', 'first_start': 'first_start_request_id'}
    if fault in fields:
        key = fields[fault]
        payload[key] = str(uuid4()) if key.endswith('_id') else 'f'*64
    elif fault == 'approval': payload['approval'] = 'START_FIRST_RESEARCH_UNIT'
    elif fault == 'allowance': payload['maximum_bytes'] += 1
    elif fault == 'deadline': payload['deadline'] = '2000-01-01T00:00:00+00:00'
    elif fault == 'long_deadline': payload['deadline'] = '2099-01-01T00:00:00+00:00'
    approved = decision(c, payload, subject='b'*64 if fault == 'operator' else 'a'*64)
    if fault == 'generation': approved = replace(approved, target_generation=approved.target_generation+1)
    if fault == 'fingerprint': approved = replace(approved, payload_hash='f'*64)
    with pytest.raises((RuntimeRefused, ValueError)):
        apply(c, cycle, payload, approved)
    assert c.store.conn.execute('SELECT count(*) FROM research_cycles').fetchone()[0] == 0
    assert c.store.get_state('active_research_cycle') is None
    assert cycle.research.active is None and cycle.research.pending is None


def test_all_approval_refusals_share_unchanged_fixture(prepared, monkeypatch):
    c, cycle, payload = setup(prepared, monkeypatch)
    for fault in ('approval', 'operator', 'generation', 'fingerprint', 'input', 'plan',
                  'seal', 'schedule', 'allowance', 'first_start', 'deadline', 'long_deadline'):
        assert_refusal(c, cycle, payload, fault)


def test_second_cycle_cannot_claim_run(prepared, monkeypatch):
    c, cycle, payload = setup(prepared, monkeypatch)
    apply(c, cycle, payload)
    with pytest.raises(RuntimeRefused):
        apply(c, cycle, dict(payload, cycle_id=str(uuid4())))
    assert c.store.conn.execute('SELECT count(*) FROM research_cycles').fetchone()[0] == 1


def test_cycle_claim_blocks_direct_dispatch(prepared, monkeypatch):
    c, cycle, payload = setup(prepared, monkeypatch)
    apply(c, cycle, payload)
    for dispatch in (
        lambda: cycle.research.step(payload['run_id']),
        lambda: cycle.research.control(payload['run_id'], str(uuid4()), 'resume'),
        lambda: cycle.auditor.step(str(uuid4())), lambda: cycle.reviews.step(str(uuid4()))):
        with pytest.raises(RuntimeRefused, match='CYCLE_DISPATCH_OWNED'):
            dispatch()
    assert cycle.research.active is None


def test_pause_resume_stop_keep_original_deadline(prepared, monkeypatch):
    c, cycle, payload = setup(prepared, monkeypatch)
    apply(c, cycle, payload)
    def control(operation, **extra):
        return apply(c, cycle, dict(operation=operation, cycle_id=payload['cycle_id'], **extra))
    control('pause')
    paused = cycle.status(payload['cycle_id'])
    assert paused['record']['state'] == 'PAUSED'
    with pytest.raises(RuntimeRefused):
        control('resume', expected_hash='f'*64)
    control('resume', expected_hash=paused['sha256'])
    assert cycle.status(payload['cycle_id'])['record']['deadline'] == payload['deadline']
    control('stop')
    assert cycle.status(payload['cycle_id'])['record']['state'] == 'STOPPED'
    assert c.store.get_state('active_research_cycle') is None
    assert cycle.research.active is None and cycle.research.pending is None


def test_foreign_operator_cannot_pause(prepared, monkeypatch):
    c, cycle, payload = setup(prepared, monkeypatch)
    apply(c, cycle, payload)
    command = dict(operation='pause', cycle_id=payload['cycle_id'])
    with pytest.raises(RuntimeRefused):
        apply(c, cycle, command, decision(c, command, subject='b'*64))
    assert cycle.status(payload['cycle_id'])['record']['state'] == 'APPROVED'


def test_stop_claim_failure_rolls_back_state(prepared, monkeypatch):
    c, cycle, payload = setup(prepared, monkeypatch)
    apply(c, cycle, payload)
    before = cycle.status(payload['cycle_id'])
    c.store.conn.execute("""CREATE TEMP TRIGGER reject_cycle_release BEFORE UPDATE ON state
        WHEN NEW.key='active_research_cycle' AND NEW.value='null'
        BEGIN SELECT RAISE(ABORT, 'simulated release failure'); END""")
    with pytest.raises(sqlite3.IntegrityError, match='simulated release failure'):
        apply(c, cycle, dict(operation='stop', cycle_id=payload['cycle_id']))
    assert cycle.status(payload['cycle_id']) == before
    assert c.store.get_state('active_research_cycle') == payload['cycle_id']
    c.store.conn.execute('DROP TRIGGER reject_cycle_release')
    assert apply(c, cycle, dict(operation='stop', cycle_id=payload['cycle_id']))['confirmed']
    assert c.store.get_state('active_research_cycle') is None


def test_pause_waiting_cycle_is_confirmed_idle(prepared, monkeypatch):
    c, cycle, payload = setup(prepared, monkeypatch)
    apply(c, cycle, payload)
    for state in ('RUNNING', 'CHECKING_RESULTS', 'WAITING_FOR_ASSESSMENT'):
        current = cycle.status(payload['cycle_id'])
        cycle.records.transition(payload['cycle_id'], current['sha256'], dict(state=state))
    before = cycle.status(payload['cycle_id'])
    assert apply(c, cycle, dict(operation='pause', cycle_id=payload['cycle_id']))['confirmed']
    assert cycle.status(payload['cycle_id']) == before


def test_failed_pause_latches_dispatch_across_restart(prepared, monkeypatch):
    from compertum.ai.cycle import ResearchCycleController
    from compertum.ai.cycle_ownership import dispatch_scope
    c, cycle, payload = setup(prepared, monkeypatch)
    apply(c, cycle, payload)
    original = cycle.research.pause
    def failed():
        raise RuntimeRefused('SIMULATED_CLEANUP_FAILURE')
    monkeypatch.setattr(cycle.research, 'pause', failed)
    command = dict(operation='pause', cycle_id=payload['cycle_id'])
    approved = decision(c, command)
    with pytest.raises(RuntimeRefused, match='SIMULATED_CLEANUP_FAILURE'):
        apply(c, cycle, command, approved)
    assert not apply(c, cycle, command, approved)['confirmed']
    with pytest.raises(RuntimeRefused, match='CYCLE_CONTROL_PENDING'):
        with dispatch_scope(cycle):
            pass
    monkeypatch.setattr(cycle.research, 'pause', original)
    c._research_cycle = None
    restarted = ResearchCycleController(c, cycle.storage, research=cycle.research,
        auditor=cycle.auditor, reviews=cycle.reviews)
    with pytest.raises(RuntimeRefused, match='CYCLE_CONTROL_PENDING'):
        with dispatch_scope(restarted):
            pass
    with pytest.raises(RuntimeRefused, match='CYCLE_CONTROL_PENDING'):
        apply(c, restarted, dict(operation='resume', cycle_id=payload['cycle_id'],
            expected_hash=restarted.status(payload['cycle_id'])['sha256']))
    assert apply(c, restarted, command)['confirmed']
    assert not apply(c, restarted, command, approved)['confirmed']


def test_waiting_control_preserves_unrelated_work(prepared, monkeypatch):
    c, cycle, payload = setup(prepared, monkeypatch)
    apply(c, cycle, payload)
    for state in ('RUNNING', 'CHECKING_RESULTS', 'WAITING_FOR_ASSESSMENT'):
        current = cycle.status(payload['cycle_id'])
        cycle.records.transition(payload['cycle_id'], current['sha256'], dict(state=state))
    with c.store.conn:
        c._state('active_research_cycle', None)
    def unrelated():
        pytest.fail('Waiting cycle touched unrelated work')
    monkeypatch.setattr(cycle, '_pause_children', unrelated)
    cycle.close()
    assert c._research_cycle is None
    c._research_cycle = cycle
    for operation in ('pause', 'stop'):
        assert apply(c, cycle, dict(operation=operation, cycle_id=payload['cycle_id']))['confirmed']
    assert cycle.status(payload['cycle_id'])['record']['state'] == 'STOPPED'
