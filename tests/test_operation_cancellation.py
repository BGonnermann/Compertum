"""Independent fake fills and cancellation races through the native plan owner."""
from uuid import uuid4
import pytest
from test_execution_health import pair
from test_execution_authority import authority,packet,advance
from test_saved_plan_controls import ready,prepare,phase
from test_operation_progression import step,broker,submissions
from test_execution_risk import intent,observation
from compertum.domain import ExecutionIntent
from compertum.runtime.errors import RuntimeRefused


def seed(a):
    # Create the pre-existing order through the same journaled owner path.
    saved=prepare(a);phase(a,'approve_plan',saved);phase(a,'start_plan',saved)
    return step(a,saved)


def plan(a,kind):
    saved=a.handle(packet('prepare_plan',kind=kind));phase(a,'approve_plan',saved);phase(a,'start_plan',saved);return saved


def test_cancel_ack_stays_pending_and_completion_does_not_claim_flat(ready):
    a=ready[0];order=seed(a);saved=plan(a,'CANCEL');first=step(a,saved)
    assert first['status']=='PENDING' and first['quantity']==0
    assert step(a,saved)['status']=='PENDING'
    broker(a).fill(order['order_id'],2,'100');broker(a).finish_cancel(order['order_id'])
    assert step(a,saved)['intent_status']=='CANCELED'
    done=step(a,saved)
    assert done['status']=='CANCEL_COMPLETE' and done['remaining_positions']==[{'symbol':'AAPL','quantity':43}]
    assert len([v for v in broker(a).snapshot()['calls'] if v['kind']=='CANCEL'])==1


def test_late_cancel_fill_requires_new_close_plan_without_enlarging_children(ready):
    a=ready[0];order=seed(a);saved=plan(a,'CLOSE_LONG');assert step(a,saved)['status']=='PENDING'
    broker(a).fill(order['order_id'],2,'100');broker(a).finish_cancel(order['order_id']);step(a,saved)
    result=step(a,saved)
    assert result['status']=='BLOCKED_RESIDUAL' and result['reason']=='PLAN_QUANTITY_CHANGED'
    assert result['remaining_positions']==[{'symbol':'AAPL','quantity':43}] and len(submissions(a))==1


def test_cancel_then_close_keeps_original_finite_children(ready):
    a=ready[0];order=seed(a);saved=plan(a,'CLOSE_LONG');step(a,saved);broker(a).finish_cancel(order['order_id']);step(a,saved)
    result=step(a,saved)
    assert result['quantity']==19 and result['status']=='PENDING' and len(submissions(a))==2


def test_changed_quantity_refuses_next_effect(ready):
    a=ready[0];saved=plan(a,'CLOSE_LONG')
    with broker(a).db:broker(a).db.execute("UPDATE positions SET quantity=44 WHERE symbol='AAPL'")
    with pytest.raises(RuntimeRefused,match='FAKE_ECONOMIC_RECONCILIATION'):step(a,saved)
    assert submissions(a)==[]


def test_start_is_required_and_higher_price_cannot_lift_child_cap(ready,monkeypatch):
    from compertum.domain import ExecutionObservation
    a=ready[0];saved=prepare(a)
    with pytest.raises(RuntimeRefused,match='PLAN_START_REQUIRED'):step(a,saved)
    phase(a,'approve_plan',saved);phase(a,'start_plan',saved)
    owner=a.plan_owner.observations;read=owner.read
    def higher():
        record,context=read();o=record.to_payload();o['quotes'][0].update(bid='3000',ask='3000');return ExecutionObservation(o),context
    monkeypatch.setattr(owner,'read',higher)
    result=step(a,saved)
    assert result['status']=='BLOCKED_RESIDUAL' and result['reason']=='CHILD_ENVELOPE_EXCEEDED' and submissions(a)==[]
