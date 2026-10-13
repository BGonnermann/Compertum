"""Upgrade compatibility and failure boundaries for independent alert witnesses."""
import sys,json,hashlib
from pathlib import Path
sys.path.insert(0,str(Path.cwd()/'tests'))
import pytest
from test_execution_health import pair
from test_execution_authority import authority,packet,advance
from test_saved_plan_controls import ready,phase
from test_operation_progression import started,step,broker
from test_operation_late_recovery import expired
from test_incident_alert_review import holder
from compertum.runtime.errors import RuntimeRefused
from compertum.events import canonical

def timeout(ready,monkeypatch):
    from compertum.deterministic_broker import DeterministicBroker
    a=ready[0];saved=started(a);submit=DeterministicBroker.submit
    monkeypatch.setattr(DeterministicBroker,'submit',lambda self,intent,**kw:submit(self,intent,outcome='TIMEOUT_BEFORE_ACCEPT'))
    return a,saved

def test_legacy_unmarked_result_remains_inert_after_upgrade(ready,monkeypatch):
    import json
    from compertum.execution_operation_owner import FakeOperationOwner
    from compertum import fake_incident_evidence as incidents
    a,saved=timeout(ready,monkeypatch);prepare=FakeOperationOwner._prepare
    def old_prepare(self,packet,binding,value):
        value=dict(value);value.pop('result_contract');return prepare(self,packet,binding,value)
    p=packet('advance_plan',plan_id=saved['plan_id'],plan_sha256=saved['plan_sha256'])
    with monkeypatch.context() as legacy:
        legacy.setattr(FakeOperationOwner,'_prepare',old_prepare);legacy.setattr(incidents,'record_result',lambda *args:{})
        original=a.handle(p)
    assert original['reason'] is None
    value=json.loads(a.store.conn.execute('SELECT body FROM fake_plan_steps WHERE request_id=?',(p['request_id'],)).fetchone()[0]);assert 'result_contract' not in value
    assert a.store.conn.execute('SELECT count(*) FROM fake_intent_events WHERE kind=?',(incidents.KIND,)).fetchone()==(0,)
    calls=broker(a).snapshot()['calls'];advance(*ready,120);warning=phase(a,'reconcile_plan',saved)
    assert warning['reason']=='UNRESOLVED_LIMIT' and a.handle(p)==original and broker(a).snapshot()['calls']==calls

def test_reconcile_after_limit_warns_without_spending_lookup(ready,monkeypatch):
    a,saved=timeout(ready,monkeypatch);step(a,saved);calls=broker(a).snapshot()['calls'];advance(*ready,120)
    result=phase(a,'reconcile_plan',saved)
    assert result['reason']=='UNRESOLVED_LIMIT' and result['operator_action_required'] is True
    visible=a.handle(packet('operation_status',plan_id=saved['plan_id']))['intents'][0]
    assert visible['reason']=='UNRESOLVED_LIMIT' and broker(a).snapshot()['calls']==calls

@pytest.mark.parametrize('table',['fake_incidents','fake_intent_events'])
def test_ignored_incident_witness_write_cannot_complete_result(ready,monkeypatch,table):
    a,saved,first=expired(ready,monkeypatch,accepted=False);calls=broker(a).snapshot()['calls'];p=packet('advance_plan',plan_id=saved['plan_id'],plan_sha256=saved['plan_sha256'])
    operation='UPDATE' if table=='fake_incidents' else 'INSERT'
    with a.store.conn:a.store.conn.execute(f'CREATE TRIGGER ignore_witness BEFORE {operation} ON {table} BEGIN SELECT RAISE(IGNORE); END')
    with pytest.raises(RuntimeRefused):a.handle(p)
    with a.store.conn:a.store.conn.execute('DROP TRIGGER ignore_witness')
    assert a.handle(p)['status']=='PENDING_UNCONFIRMED'
    assert a.handle(packet('operation_status',plan_id=saved['plan_id']))['intents'][0]['reason']=='UNRESOLVED_LIMIT'
    assert broker(a).snapshot()['calls']==calls

def test_interrupted_submission_without_incident_remains_visible():
    o,i,started=holder()
    try:
        o.db.execute('DELETE FROM fake_incidents');o.db.commit()
        assert o._warning(i,'SUBMITTING')=={}
    finally:o.db.close()


def test_new_witness_cannot_be_downgraded_to_legacy_format(ready,monkeypatch):
    a,saved,first=expired(ready,monkeypatch,accepted=False)
    p=packet('advance_plan',plan_id=saved['plan_id'],plan_sha256=saved['plan_sha256']);warning=a.handle(p);key=p['request_id'];calls=broker(a).snapshot()['calls']
    selected=json.loads(a.store.conn.execute('SELECT body FROM fake_plan_steps WHERE request_id=?',(key,)).fetchone()[0]);selected.pop('result_contract');raw_step=canonical(selected).decode();step_sha=hashlib.sha256(raw_step.encode()).hexdigest()
    value=dict(warning,reason=None,selection_sha256=step_sha);value.pop('operator_action_required');value.pop('incident_started_at');raw_result=canonical(value).decode()
    with a.store.conn:
        a.store.conn.execute('UPDATE fake_plan_steps SET body=?,sha256=? WHERE request_id=?',(raw_step,step_sha,key))
        a.store.conn.execute('UPDATE fake_plan_results SET sha256=?,body=? WHERE request_id=?',(hashlib.sha256(raw_result.encode()).hexdigest(),raw_result,key))
        a.store.conn.execute('UPDATE fake_operator_requests SET result=? WHERE request_id=?',(raw_result,key))
    with pytest.raises(RuntimeRefused,match='OPERATION_STATE_CORRUPT'):a.handle(p)
    assert broker(a).snapshot()['calls']==calls

@pytest.mark.parametrize('existing_events',[486,488])
def test_near_full_journal_refuses_before_dispatch_or_preserves_late_resolution(ready,monkeypatch,existing_events):
    from uuid import uuid4
    from compertum.deterministic_broker import DeterministicBroker
    a=ready[0];saved=started(a);journal=a.plan_owner.observations.journal
    with journal._transaction():
        for _ in range(existing_events):journal._event('prior-fake-account',str(uuid4()),'CHECKED',{'historical_fixture':True})
    submit=DeterministicBroker.submit
    monkeypatch.setattr(DeterministicBroker,'submit',lambda self,intent,**kw:submit(self,intent,outcome='TIMEOUT_AFTER_ACCEPT',invisible_lookups=6))
    initial=step(a,saved);b=broker(a)
    if initial['status']=='BLOCKED_RESIDUAL':
        assert initial['reason']=='RECONCILIATION_CAPACITY_REQUIRED' and not b.snapshot()['calls']
        assert existing_events==488
        return
    assert initial['status']=='UNKNOWN'
    prior=0
    for seconds in (0,2,5,10,20,30,120):
        advance(*ready,seconds-prior);prior=seconds;warning=step(a,saved)
        assert warning['status']=='UNKNOWN'
    assert warning['operator_action_required'] is True
    calls=b.snapshot()['calls'];assert len(calls)==7
    order=b.snapshot()['orders'][0];b.fill(order['order_id'],19,'100')
    assert phase(a,'reconcile_plan',saved)['intent_status']=='FILLED'
    assert phase(a,'reconcile_plan',saved)['status']=='RECONCILED'
    assert b.snapshot()['calls']==calls
    assert a.store.conn.execute('SELECT count(*) FROM fake_intent_events').fetchone()[0]==existing_events+26
    assert a.store.conn.execute('SELECT count(*) FROM fake_plan_steps').fetchone()[0]==10


def test_new_dispatch_requires_all_ten_remaining_operation_slots(ready):
    from compertum.execution_operation_owner import FakeOperationOwner
    a=ready[0];started(a);owner=FakeOperationOwner(a.plan_owner)
    assert owner._headroom([None]*54)
    assert not owner._headroom([None]*55)
