import hashlib
import json

import pytest

from test_ai_manual import bridge, packet
from compertum.events import canonical
from compertum.runtime.errors import RuntimeRefused
from compertum.ai.manual import MAX_PACKET
from compertum.persistence import checked_path
from pathlib import Path


def accepted(bridge):
    b, root, task, path, response, meta = packet(bridge)
    task_id = task.to_payload()['task_id']
    receipt = b.import_proposal(task_id, path, meta)
    selection = canonical(dict(schema_version='1', proposal_sha256=receipt['original']['sha256'],
                              candidate_ids=['ridge-h05-a010']))
    return b, root, task_id, receipt, selection


def test_save_and_repeat_preserve_plan_and_reservations(bridge):
    b, root, task_id, receipt, selection = accepted(bridge)
    result = b.save_review_plan(task_id, selection)
    raw = (root/result['path']).read_bytes()
    plan = json.loads(raw)
    assert plan['authority'] == 'REVIEW_ONLY' and plan['executed'] is False
    assert plan['proposal_sha256'] == receipt['original']['sha256']
    assert len(plan['definition']['registered_family']) == 12
    assert plan['selection_sha256'] == hashlib.sha256(selection).hexdigest()
    before = b.store.conn.execute('SELECT count(*) FROM reservations').fetchone()
    assert b.save_review_plan(task_id, selection) == result
    assert b.store.conn.execute('SELECT count(*) FROM reservations').fetchone() == before
    assert (root/result['path']).read_bytes() == raw


@pytest.mark.parametrize('change', ['original', 'receipt', 'plan', 'binding', 'status', 'selection', 'budget'])
def test_refuse_changed_evidence_and_limits(bridge, change):
    b, root, task_id, receipt, selection = accepted(bridge)
    if change == 'plan':
        artifact = b.save_review_plan(task_id, selection)
        (root/artifact['path']).write_bytes(b'{}')
    elif change in ('original', 'receipt'):
        key = 'original' if change == 'original' else 'receipt_artifact'
        (root/receipt[key]['path']).write_bytes(b'{}')
    elif change == 'selection':
        b.save_review_plan(task_id, selection)
        value = json.loads(selection); value['candidate_ids'] = ['momentum-h05']
        selection = canonical(value)
    else:
        with b.store.conn:
            if change == 'binding':
                b.store.conn.execute("UPDATE ai_tasks SET prompt_sha256=?", ('f'*64,))
            elif change == 'status':
                b.store.conn.execute("UPDATE ai_tasks SET status='WAITING_FOR_OPERATOR'")
            else:
                b.store.conn.execute('UPDATE ai_budgets SET maximum=1')
    with pytest.raises(RuntimeRefused):
        b.save_review_plan(task_id, selection)


def test_waiting_proposal_cannot_save(bridge):
    b, root, task, path, response, meta = packet(bridge)
    with pytest.raises(RuntimeRefused, match='AI_PROPOSAL_NOT_ACCEPTED'):
        b.save_review_plan(task.to_payload()['task_id'], b'{}')


@pytest.mark.parametrize('name', ['review-selection.json', 'review-plan.json'])
def test_repeat_read_is_bounded_for_oversized_saved_file(bridge, name, monkeypatch):
    b, root, task_id, receipt, selection = accepted(bridge)
    b.save_review_plan(task_id, selection)
    target = checked_path(b.store.root, root/f'artifacts/runs/{task_id}/ai/{name}')
    target.write_bytes(b'x'*(MAX_PACKET+2))
    original_open = Path.open
    reads = []

    class BoundedRead:
        def __init__(self, stream): self.stream = stream
        def __enter__(self): return self
        def __exit__(self, *args): self.stream.close()
        def read(self, size=-1):
            assert size == MAX_PACKET+1
            reads.append(size)
            return self.stream.read(size)

    def checked_open(path, *args, **kwargs):
        stream = original_open(path, *args, **kwargs)
        return BoundedRead(stream) if path == target else stream

    monkeypatch.setattr(Path, 'open', checked_open)
    with pytest.raises(RuntimeRefused, match='AI_ARTIFACT_CONFLICT'):
        b.save_review_plan(task_id, selection)
    assert reads == [MAX_PACKET+1]


@pytest.mark.parametrize('key', ['original', 'receipt_artifact'])
@pytest.mark.parametrize('change', ['missing', 'unpublished'])
def test_published_reservations_are_required(bridge, key, change):
    b, root, task_id, receipt, selection = accepted(bridge)
    with b.store.conn:
        if change == 'missing':
            b.store.conn.execute('DELETE FROM reservations WHERE path=?', (receipt[key]['path'],))
        else:
            b.store.conn.execute("UPDATE reservations SET status='ABANDONED' WHERE path=?", (receipt[key]['path'],))
    with pytest.raises(RuntimeRefused, match='AI_EVIDENCE_MISMATCH'):
        b.save_review_plan(task_id, selection)


def test_database_receipt_must_match_retained_bytes(bridge):
    b, root, task_id, receipt, selection = accepted(bridge)
    receipt['proposal']['summary'] = 'Changed after acceptance.'
    with b.store.conn:
        b.store.conn.execute('UPDATE ai_tasks SET response=?', (canonical(receipt).decode(),))
    with pytest.raises(RuntimeRefused, match='AI_EVIDENCE_MISMATCH'):
        b.save_review_plan(task_id, selection)


def test_repeat_after_interrupted_plan_write_reuses_selection(bridge, monkeypatch):
    b, root, task_id, receipt, selection = accepted(bridge)
    retain = b._retain
    def interrupted(task, name, raw):
        if name == 'review-plan.json':
            raise RuntimeRefused('TEST_INTERRUPTION')
        return retain(task, name, raw)
    monkeypatch.setattr(b, '_retain', interrupted)
    with pytest.raises(RuntimeRefused, match='TEST_INTERRUPTION'):
        b.save_review_plan(task_id, selection)
    before = b.store.conn.execute('SELECT count(*) FROM reservations').fetchone()[0]
    monkeypatch.setattr(b, '_retain', retain)
    result = b.save_review_plan(task_id, selection)
    assert b.store.conn.execute('SELECT count(*) FROM reservations').fetchone()[0] == before+1
    assert json.loads((root/result['path']).read_bytes())['executed'] is False
