"""Review regressions: retain reconciliation capacity and recover without dispatch."""
import json
import pytest
from uuid import uuid4
from test_execution_health import pair
from test_execution_authority import authority,packet,advance,session
from test_saved_plan_controls import ready,prepare,phase
from test_operation_progression import started,step,broker,submissions,finish
from compertum.runtime.errors import RuntimeRefused


def test_dispatch_requires_broker_reconciliation_headroom(ready):
    a=ready[0];saved=started(a);b=broker(a)
    for _ in range(511):b.lookup('absent')
    result=step(a,saved)
    assert result['status']=='BLOCKED_RESIDUAL' and result['reason']=='RECONCILIATION_CAPACITY_REQUIRED'
    assert submissions(a)==[]


def test_dispatch_requires_step_reconciliation_headroom(ready,monkeypatch):
    import compertum.execution_operation_owner as module
    a=ready[0];saved=started(a)
    # A reduced test cap represents exactly one remaining slot without writing
    # 63 unrelated requests. Production MAX_STEPS remains 64.
    monkeypatch.setattr(module,'MAX_STEPS',1)
    result=step(a,saved)
    assert result['status']=='BLOCKED_RESIDUAL' and result['reason']=='RECONCILIATION_CAPACITY_REQUIRED' and submissions(a)==[]


@pytest.mark.parametrize('event',['halt','session'])
def test_invalidated_operation_can_reconcile_only_existing_intent(ready,event):
    a=ready[0];saved=started(a);first=step(a,saved)
    if event=='halt':a.handle(packet('halt'))
    else:session(a)
    a.handle(packet('supervise'));finish(a,first)
    result=phase(a,'reconcile_plan',saved)
    assert result['intent_status']=='FILLED' and len(submissions(a))==1
    with pytest.raises(RuntimeRefused,match='PLAN_CONTEXT_CHANGED'):step(a,saved)
    assert phase(a,'reconcile_plan',saved)['status']=='RECONCILED' and len(submissions(a))==1


def test_status_remains_read_only_when_step_capacity_is_exhausted(ready,monkeypatch):
    import compertum.execution_operation_owner as module
    a=ready[0];saved=started(a);first=step(a,saved);monkeypatch.setattr(module,'MAX_STEPS',1)
    before=a.store.conn.total_changes
    result=a.handle(packet('operation_status',plan_id=saved['plan_id']))
    assert result['intents'][0]['status']=='ACKNOWLEDGED' and result['fresh_reconciliation'] is False
    assert a.store.conn.total_changes==before and len(submissions(a))==1


def test_dispatch_requires_journal_event_headroom(ready):
    a=ready[0];saved=started(a);db=a.store.conn
    count=db.execute('SELECT count(*) FROM fake_intent_events').fetchone()[0]
    with db:
        db.executemany('INSERT INTO fake_intent_events(account,intent_id,kind,body) VALUES(?,?,?,?)',[(('fake-account',str(uuid4()),'TEST_PRIOR_EVIDENCE','{}')) for _ in range(510-count)])
    result=step(a,saved)
    assert result['status']=='BLOCKED_RESIDUAL' and result['reason']=='RECONCILIATION_CAPACITY_REQUIRED' and submissions(a)==[]


def test_result_and_pending_evidence_cannot_disappear_silently(ready):
    a=ready[0];saved=started(a);first=step(a,saved)
    with a.store.conn:a.store.conn.execute('DELETE FROM fake_plan_results WHERE request_id=?',(first['request_id'],))
    with pytest.raises(RuntimeRefused,match='OPERATION_STATE_CORRUPT'):step(a,saved)
    assert len(submissions(a))==1
