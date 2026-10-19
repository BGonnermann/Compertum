"""Explicit proposal links retain synthetic campaign evidence without dispatch."""
from uuid import uuid4
import json
from types import SimpleNamespace
import pytest

from test_ai_manual import bridge
from test_ai_review_plan_storage import accepted
from helpers.saved_campaign_fixture import campaign_folds
from compertum.simulation.runs import SavedRuns
from compertum.ai.manual import ManualBridge
from compertum.runtime.errors import RuntimeRefused
from compertum.data.errors import DataError
from compertum.events import canonical
from test_persistence import owned
from test_storage import manager


def setup(bridge):
    b, root, task_id, receipt, selection = accepted(bridge)
    b.save_review_plan(task_id, selection)
    runs = SavedRuns(b.storage)
    run_id = str(uuid4())
    runs.create_campaign(run_id, campaign_folds())
    return b, root, task_id, runs, run_id


def test_link_pending_campaign_without_dispatch(bridge):
    b, root, task_id, runs, run_id = setup(bridge)
    link = b.link_review_campaign(task_id, run_id, runs=runs)
    before = b.store.conn.total_changes
    history = b.review_history(task_id, runs=runs)
    assert b.store.conn.total_changes == before
    assert history['link'] == link
    assert history['campaign']['run_id'] == run_id
    assert history['campaign']['state'] == 'PAUSED'
    assert len(history['trials']) == 12
    assert all(row['status'] == 'PENDING' for row in history['trials'])
    assert history['attempts'] == [] and history['results'] == []
    assert history['financial_accepted'] is False
    assert history['execution_authorized'] is False


def test_repeat_and_reconstructed_bridge_preserve_link(bridge):
    b, root, task_id, runs, run_id = setup(bridge)
    first = b.link_review_campaign(task_id, run_id, runs=runs)
    changes = b.store.conn.total_changes
    assert b.link_review_campaign(task_id, run_id, runs=runs) == first
    assert b.store.conn.total_changes == changes
    second = ManualBridge(b.storage)
    assert second.review_history(task_id, runs=runs) == b.review_history(task_id, runs=runs)


def test_conflicting_campaign_does_not_replace_link(bridge):
    b, root, task_id, runs, run_id = setup(bridge)
    first = b.link_review_campaign(task_id, run_id, runs=runs)
    before = (root/first['path']).read_bytes()
    other = str(uuid4())
    runs.create_campaign(other, campaign_folds())
    with pytest.raises(RuntimeRefused, match='AI_ARTIFACT_CONFLICT'):
        b.link_review_campaign(task_id, other, runs=runs)
    assert (root/first['path']).read_bytes() == before


@pytest.mark.parametrize('name', ['review-plan.json', 'review-selection.json', 'receipt.json', 'campaign-link.json'])
def test_changed_ai_evidence_is_rejected(bridge, name):
    b, root, task_id, runs, run_id = setup(bridge)
    b.link_review_campaign(task_id, run_id, runs=runs)
    (root/f'artifacts/runs/{task_id}/ai/{name}').write_bytes(b'{}')
    with pytest.raises(RuntimeRefused, match='AI_EVIDENCE_MISMATCH'):
        b.review_history(task_id, runs=runs)


@pytest.mark.parametrize('change', ['input', 'unpublished', 'history', 'plan_binding'])
def test_campaign_and_plan_bindings_are_required(bridge, change):
    b, root, task_id, runs, run_id = setup(bridge)
    b.link_review_campaign(task_id, run_id, runs=runs)
    artifact = runs.summary(run_id)['input_artifact']
    if change == 'input':
        (root/artifact['path']).write_bytes(b'{}')
    else:
        with b.store.conn:
            if change == 'unpublished':
                b.store.conn.execute("UPDATE reservations SET status='ABANDONED' WHERE path=?", (artifact['path'],))
            elif change == 'history':
                b.store.conn.execute("UPDATE baseline_history SET body='{}' WHERE run_id=?", (run_id,))
            else:
                b.store.conn.execute("UPDATE ai_tasks SET prompt_sha256=? WHERE task_id=?", ('f'*64, task_id))
    with pytest.raises((RuntimeRefused, DataError)):
        b.review_history(task_id, runs=runs)


def test_budget_failure_keeps_campaign_paused_and_link_missing(bridge):
    b, root, task_id, runs, run_id = setup(bridge)
    with b.store.conn:
        b.store.conn.execute('UPDATE ai_budgets SET maximum=1 WHERE task_id=?', (task_id,))
    with pytest.raises(RuntimeRefused, match='AI_OUTPUT_BUDGET'):
        b.link_review_campaign(task_id, run_id, runs=runs)
    assert runs.summary(run_id)['state'] == 'PAUSED'
    with pytest.raises(RuntimeRefused, match='AI_HISTORY_EVIDENCE_MISSING'):
        b.review_history(task_id, runs=runs)


def test_wrong_owner_is_rejected(bridge):
    b, root, task_id, runs, run_id = setup(bridge)
    with pytest.raises(RuntimeRefused, match='AI_HISTORY_OWNER_MISMATCH'):
        b.link_review_campaign(task_id, run_id, runs=SimpleNamespace(store=object()))


def test_failed_skipped_pending_and_stopped_results_remain_visible(bridge):
    b, root, task_id, runs, run_id = setup(bridge)
    b.link_review_campaign(task_id, run_id, runs=runs)
    runs.control(run_id, str(uuid4()), 'resume')
    for _ in range(4):
        runs.step(run_id)
    runs.control(run_id, str(uuid4()), 'stop')
    history = b.review_history(task_id, runs=runs)
    assert history['campaign']['state'] == 'STOPPED'
    assert {v['status'] for v in history['results']} == {'COMPLETED', 'FAILED', 'SKIPPED'}
    assert len(history['trials']) == 12
    assert any(v['status'] == 'PENDING' for v in history['trials'])
    assert any(v['status'] == 'FAILED' for v in history['attempts'])
    artifact = next(v['artifact'] for v in history['results'] if v['status'] == 'COMPLETED')
    (root/artifact['path']).write_bytes(b'corrupt')
    with pytest.raises(DataError, match='RUN_ARTIFACT_CORRUPT'):
        b.review_history(task_id, runs=runs)


def test_interrupted_attempt_is_not_hidden_or_restarted(bridge):
    b, root, task_id, runs, run_id = setup(bridge)
    b.link_review_campaign(task_id, run_id, runs=runs)
    runs.control(run_id, str(uuid4()), 'resume')
    runs.begin(run_id)
    runs.interrupt(run_id, 'OPERATOR_PAUSE')
    before = b.store.conn.total_changes
    history = b.review_history(task_id, runs=runs)
    assert history['attempts'][-1]['status'] == 'INTERRUPTED'
    assert history['results'] == []
    assert b.store.conn.total_changes == before


def test_history_does_not_require_current_execution_identity(bridge, monkeypatch):
    b, root, task_id, runs, run_id = setup(bridge)
    b.link_review_campaign(task_id, run_id, runs=runs)
    def forbidden():
        raise AssertionError('History cannot request execution identity.')
    monkeypatch.setattr('compertum.simulation.runs.runtime_identity', forbidden)
    assert b.review_history(task_id, runs=runs)['campaign']['run_id'] == run_id


def sealed_setup(owned):
    from compertum.storage import reserve_runtime_paths
    from compertum.persistence import open_store
    from compertum.evaluation_seals import EvaluationSeals
    from compertum.development_seals import create_campaign
    storage = manager(owned)
    reserve_runtime_paths(storage)
    b, root, task_id, receipt, selection = accepted((ManualBridge(storage), storage.root))
    b.save_review_plan(task_id, selection)
    runs = SavedRuns(storage)
    seals = EvaluationSeals(open_store(owned[1]['evaluation'], 'evaluation'))
    run_id, seal_id = str(uuid4()), str(uuid4())
    create_campaign(runs, run_id, campaign_folds(), seal_id=seal_id, evaluation=seals,
        data_manifest_sha256='a'*64, holdout_manifest_sha256='b'*64)
    b.link_review_campaign(task_id, run_id, runs=runs)
    return b, task_id, runs, run_id, seals, seal_id


def test_sealed_history_uses_recorded_identity_while_dispatch_refuses(owned, monkeypatch):
    from compertum.development_seals import check_campaign_seal
    b, task_id, runs, run_id, seals, seal_id = sealed_setup(owned)
    state = runs._load(run_id)
    changed = {**state['identity'], 'package_sha256': 'f'*64}
    monkeypatch.setattr('compertum.development_seals.runtime_identity', lambda: changed)
    before = b.store.conn.total_changes
    assert b.review_history(task_id, runs=runs)['campaign']['recorded_identity'] == state['identity']
    assert b.store.conn.total_changes == before
    with pytest.raises(DataError, match='SEAL_RUNTIME_CHANGED'):
        check_campaign_seal(runs.store, state)


@pytest.mark.parametrize('change', ['ticket', 'receipt', 'mirror', 'binding', 'recorded_identity'])
def test_sealed_history_retains_all_evidence_checks(owned, change):
    b, task_id, runs, run_id, seals, seal_id = sealed_setup(owned)
    if change == 'mirror':
        with seals.store.conn:
            seals.store.conn.execute('DELETE FROM evaluation_seal_events WHERE sequence=2')
    elif change in ('binding', 'recorded_identity'):
        state = runs._load(run_id)
        if change == 'binding': state.pop('protocol_seal')
        else: state['identity']['package_sha256'] = 'f'*64
        with runs.store.conn:
            runs._save(state, 'INJECTED_CORRUPTION')
    else:
        with runs.store.conn:
            if change == 'ticket':
                runs.store.conn.execute('DELETE FROM sealed_campaigns WHERE run_id=?', (run_id,))
            else:
                runs.store.conn.execute("UPDATE sealed_campaigns SET receipt='{}' WHERE run_id=?", (run_id,))
    with pytest.raises((DataError, RuntimeRefused)):
        b.review_history(task_id, runs=runs)
