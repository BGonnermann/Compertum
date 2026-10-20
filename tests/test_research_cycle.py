"""Durable cycle records retain exact bindings and reject stale transitions."""
import importlib
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from test_ai_manual import bridge
from compertum.events import canonical
from compertum.runtime.errors import RuntimeRefused


def record():
    now = datetime.now(timezone.utc)
    return dict(schema_version='1', record_type='ResearchCycle',
        cycle_id=str(uuid4()), run_id=str(uuid4()),
        approval_request_id=str(uuid4()), registration_request_id=str(uuid4()),
        first_start_request_id=str(uuid4()), operator='a'*64, generation=1,
        prepared_sha256='b'*64, plan_sha256='c'*64, seal_id=str(uuid4()),
        schedule_sha256='d'*64, maximum_bytes=128*1024**2,
        deadline=(now+timedelta(seconds=1800)).isoformat(),
        scorecard_task_id=str(uuid4()), aggregate_task_id=str(uuid4()),
        state='APPROVED', sequence=0, dispatch=None, reason='OWNER_APPROVED',
        updated_at=now.isoformat(), financial_acceptance=False, execute_next=False)


def records(bridge):
    return importlib.import_module('compertum.ai.cycle_record').CycleRecords(bridge[0].storage)


def test_cycle_records_interface_exists():
    module = importlib.import_module('compertum.ai.cycle_record')
    assert callable(module.CycleRecords)
    assert callable(module.CycleRecords.status)
    assert callable(module.CycleRecords.transition)


def test_duplicate_record_is_idempotent_and_detached(bridge):
    rows = records(bridge)
    value = record()
    first = rows.create(value)
    assert rows.create(value) == first
    first['record']['state'] = 'BLOCKED'
    assert rows.status(value['cycle_id'])['record'] == value


def test_second_cycle_cannot_claim_same_run(bridge):
    rows = records(bridge)
    value = record()
    rows.create(value)
    with pytest.raises(RuntimeRefused, match='CYCLE_RUN_ALREADY_CLAIMED'):
        rows.create(dict(value, cycle_id=str(uuid4())))


@pytest.mark.parametrize('field,value', [
    ('run_id', str(uuid4())), ('operator', 'e'*64), ('generation', 2),
    ('prepared_sha256', 'e'*64), ('deadline', '2099-01-01T00:00:00+00:00'),
    ('maximum_bytes', 256*1024**2), ('sequence', 30), ('execute_next', True)])
def test_transition_cannot_change_approval_bindings(bridge, field, value):
    rows = records(bridge)
    original = record()
    saved = rows.create(original)
    with pytest.raises(RuntimeRefused):
        rows.transition(original['cycle_id'], saved['sha256'], {field: value})
    assert rows.status(original['cycle_id']) == saved


def test_stale_transition_never_overwrites_new_state(bridge):
    rows = records(bridge)
    value = record()
    saved = rows.create(value)
    paused = rows.transition(value['cycle_id'], saved['sha256'], dict(state='PAUSED', reason='OWNER_PAUSED'))
    with pytest.raises(RuntimeRefused, match='CYCLE_STATE_CHANGED'):
        rows.transition(value['cycle_id'], saved['sha256'], dict(state='RUNNING', reason='START'))
    assert rows.status(value['cycle_id']) == paused
    assert paused['record']['sequence'] == 1


def test_expired_record_refuses_creation(bridge):
    rows = records(bridge)
    value = record()
    value['deadline'] = '2000-01-01T00:00:00+00:00'
    with pytest.raises(RuntimeRefused, match='CYCLE_DEADLINE'):
        rows.create(value)


def test_uncertain_dispatch_cannot_resume(bridge):
    rows = records(bridge)
    value = record()
    saved = rows.create(value)
    dispatch = dict(task_id=str(uuid4()), kind='RESEARCH', unit=0, history_sha256='f'*64)
    running = rows.transition(value['cycle_id'], saved['sha256'], dict(state='RUNNING', dispatch=dispatch, reason='DISPATCH_INTENT'))
    paused = rows.transition(value['cycle_id'], running['sha256'], dict(state='PAUSED', reason='INTERRUPTED'))
    with pytest.raises(RuntimeRefused, match='CYCLE_DISPATCH_UNCERTAIN'):
        rows.transition(value['cycle_id'], paused['sha256'], dict(state='RUNNING', reason='RESUME'))


def test_restart_preserves_bindings_and_blocks_uncertain_dispatch(bridge):
    rows = records(bridge)
    value = record()
    saved = rows.create(value)
    dispatch = dict(task_id=str(uuid4()), kind='RESEARCH', unit=0, history_sha256='f'*64)
    rows.transition(value['cycle_id'], saved['sha256'], dict(state='RUNNING', dispatch=dispatch, reason='DISPATCH_INTENT'))
    restarted = records(bridge)
    restarted.recover()
    state = restarted.status(value['cycle_id'])['record']
    assert state['state'] == 'BLOCKED' and state['dispatch'] == dispatch
    assert state['deadline'] == value['deadline']
    assert state['operator'] == value['operator'] and state['generation'] == value['generation']


def test_record_count_is_bounded(bridge):
    rows = records(bridge)
    for _ in range(32):
        rows.create(record())
    with pytest.raises(RuntimeRefused, match='CYCLE_LEDGER_FULL'):
        rows.create(record())


def test_large_reason_refused_without_saved_change(bridge):
    rows = records(bridge)
    value = record()
    saved = rows.create(value)
    with pytest.raises((RuntimeRefused, ValueError)):
        rows.transition(value['cycle_id'], saved['sha256'], dict(reason='x'*65536))
    assert rows.status(value['cycle_id']) == saved


def test_capacity_refusal_creates_no_cycle_table(bridge, monkeypatch):
    storage = bridge[0].storage
    def refuse(*args):
        raise RuntimeRefused('STORAGE_TEST_REFUSAL')
    monkeypatch.setattr(storage, '_capacity', refuse)
    with pytest.raises(RuntimeRefused, match='STORAGE_TEST_REFUSAL'):
        records(bridge)
    assert storage.store.conn.execute("SELECT count(*) FROM sqlite_master WHERE name='research_cycles'").fetchone()[0] == 0


@pytest.mark.parametrize('operation', ['create', 'transition'])
def test_later_capacity_loss_refuses_mutation(bridge, monkeypatch, operation):
    rows = records(bridge)
    original = record()
    saved = rows.create(original)
    def refuse(*args):
        raise RuntimeRefused('STORAGE_TEST_REFUSAL')
    monkeypatch.setattr(rows.storage, '_capacity', refuse)
    with pytest.raises(RuntimeRefused, match='STORAGE_TEST_REFUSAL'):
        if operation == 'create':
            rows.create(record())
        else:
            rows.transition(original['cycle_id'], saved['sha256'], dict(state='RUNNING', reason='START'))
    assert rows.status(original['cycle_id']) == saved


def test_sequence_limit_preserves_pause_and_stop(bridge):
    rows = records(bridge)
    value = record()
    rows.create(value)
    # Construct the valid boundary directly; avoid ten thousand fixture writes.
    value.update(state='RUNNING', sequence=9999)
    with rows.store.conn:
        rows.store.conn.execute('UPDATE research_cycles SET record=? WHERE cycle_id=?',
                               (canonical(value).decode(), value['cycle_id']))
    saved = rows.status(value['cycle_id'])
    with pytest.raises(RuntimeRefused, match='CYCLE_SEQUENCE_BOUND'):
        rows.transition(value['cycle_id'], saved['sha256'], dict(state='RUNNING', reason='CONTINUE'))
    paused = rows.transition(value['cycle_id'], saved['sha256'], dict(state='PAUSED', reason='OWNER_PAUSED'))
    stopped = rows.transition(value['cycle_id'], paused['sha256'], dict(state='STOPPED', reason='OWNER_STOPPED'))
    assert stopped['record']['sequence'] == 10001
