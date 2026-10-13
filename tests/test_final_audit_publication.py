"""Simulated publication faults: successful exit alone cannot accept an audit."""
from uuid import uuid4

import pytest

from test_final_audit_controller import controller, owner, saved, environment
from compertum import final_audit_controller as m
from compertum.data.encoding import canonical
from compertum.data.errors import DataError
from compertum.runtime.errors import RuntimeRefused


def original_evidence(o):
    s = o.saved
    return (
        canonical(s.evidence), canonical(s.guard), canonical(s.status),
        (s.storage.root / s.frame['path']).read_bytes(),
        tuple(s.db.execute('SELECT * FROM final_dispatches ORDER BY attempt_id')),
        tuple(s.db.execute('SELECT * FROM final_exits ORDER BY attempt_id')),
        tuple(s.db.execute('SELECT * FROM final_closures ORDER BY attempt_id')),
    )


def refuses_replacement(c, o, before):
    assert c.recover(o.task)['state'] == 'BLOCKED'
    assert c.runs.status(o.task) == before
    with pytest.raises((DataError, RuntimeRefused)):
        c.control(dict(operation='resume', task_id=o.task))
    with pytest.raises((DataError, RuntimeRefused)):
        c.step(o.task)
    assert c.runs.status(o.task) == before


@pytest.mark.parametrize('renamed_before_failure', [False, True])
def test_publish_failure_blocks_without_acceptance_or_retry(controller, monkeypatch, renamed_before_failure):
    o, c = controller
    original = original_evidence(o)
    c.step(o.task)
    prepared, writer, job = c.active
    calls = []

    def fail_publication():
        calls.append(True)
        if renamed_before_failure:
            writer.stream.close()
            writer.path.rename(writer.destination)
        raise OSError('injected failure before publication ledger commit')

    monkeypatch.setattr(writer, 'publish', fail_publication)
    c.tick()
    state = c.runs.status(o.task)
    assert calls == [True]
    assert state['state'] == 'BLOCKED'
    assert state['attempts'][0]['reason'] == 'BOOKKEEPING_FAILED'
    assert state['attempts'][0]['job_receipt'] == job.result
    assert job.result['exit_code'] == 0 and not job.result['timed_out']
    assert len(state['attempts']) == 1
    assert state['artifact'] is None and state['audit_sha256'] is None
    assert c.active is None and job.closed and writer.closed
    assert writer.destination.exists() == renamed_before_failure
    assert o.db.execute('SELECT status, manifest FROM reservations WHERE id=?', (prepared['reservation_id'],)).fetchone() == ('ABANDONED', None)
    monkeypatch.setattr(m, 'launch_bounded', lambda *a, **kw: pytest.fail('unexpected redispatch'))
    refuses_replacement(c, o, state)
    assert original_evidence(o) == original


@pytest.mark.parametrize('reservation_state', ['OPEN', 'ABANDONED'])
def test_restart_after_successful_exit_without_publication_blocks(controller, monkeypatch, reservation_state):
    o, c = controller
    original = original_evidence(o)
    c.step(o.task)
    prepared, writer, job = c.active
    c.runs.record_exit(o.task, job.wait())
    assert c.runs.status(o.task)['state'] == 'RUNNING'
    job.close()
    if reservation_state == 'ABANDONED':
        writer.close()
    else:
        # Simulate process loss after the exit receipt but before ledger cleanup.
        writer.stream.close()
        writer.closed = True
    c.active = None
    assert not writer.destination.exists()
    assert o.db.execute('SELECT status, manifest FROM reservations WHERE id=?', (prepared['reservation_id'],)).fetchone() == (reservation_state, None)
    o.storage.lease.identity.process_instance_id = str(uuid4())
    monkeypatch.setattr(m, 'FinalAuditRuns', type(o.runs))
    monkeypatch.setattr(m, 'launch_bounded', lambda *a, **kw: pytest.fail('unexpected redispatch'))
    restarted = m.FinalAuditController(c.coordinator, o.storage)
    assert restarted.runs.status(o.task)['state'] == 'RUNNING'
    assert restarted.recover(o.task)['state'] == 'BLOCKED'
    state = restarted.runs.status(o.task)
    assert state['attempts'][0]['reason'] == 'PUBLICATION_FAILED'
    assert state['attempts'][0]['job_receipt'] == job.result
    assert job.result['exit_code'] == 0 and not job.result['timed_out']
    assert len(state['attempts']) == 1
    assert state['artifact'] is None and state['audit_sha256'] is None
    refuses_replacement(restarted, o, state)
    assert original_evidence(o) == original
