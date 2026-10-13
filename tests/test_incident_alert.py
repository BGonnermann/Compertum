"""Durable operator warnings use existing incident evidence, never new effects."""
import hashlib,json,sys
from pathlib import Path
sys.path.insert(0,str(Path.cwd()/'tests'))
import pytest
from test_execution_health import pair
from test_execution_authority import authority,packet,advance
from test_saved_plan_controls import ready,phase
from test_operation_progression import started,step,broker
from test_operation_late_recovery import expired
from compertum.events import canonical
from compertum.runtime.errors import RuntimeRefused

def status(a,saved):return a.handle(packet('operation_status',plan_id=saved['plan_id']))['intents'][0]
def request(saved):return packet('advance_plan',plan_id=saved['plan_id'],plan_sha256=saved['plan_sha256'])

def test_warning_starts_at_limit_and_status_is_read_only(ready,monkeypatch):
    from compertum.deterministic_broker import DeterministicBroker
    a=ready[0];saved=started(a);submit=DeterministicBroker.submit
    monkeypatch.setattr(DeterministicBroker,'submit',lambda self,intent,**kw:submit(self,intent,outcome='TIMEOUT_BEFORE_ACCEPT'))
    first=step(a,saved);assert first['reason'] is None
    advance(*ready,119);early=step(a,saved)
    assert early['reason'] is None and not status(a,saved).get('operator_action_required',False)
    calls=broker(a).snapshot()['calls'];advance(*ready,1);p=request(saved);warning=a.handle(p)
    assert warning['status']=='UNKNOWN' and warning['reason']=='UNRESOLVED_LIMIT' and warning['operator_action_required'] is True
    before=a.store.conn.total_changes;visible=status(a,saved)
    assert visible['reason']==warning['reason'] and visible['incident_started_at']==warning['incident_started_at']
    assert a.store.conn.total_changes==before and a.handle(p)==warning
    assert broker(a).snapshot()['calls']==calls

@pytest.mark.parametrize('accepted',[False,True])
def test_warning_replay_and_late_resolution_preserve_history(ready,monkeypatch,accepted):
    a,saved,first=expired(ready,monkeypatch,accepted=accepted);p=request(saved);warning=a.handle(p)
    assert warning['operator_action_required'] is True
    calls=broker(a).snapshot()['calls'];result=phase(a,'reconcile_plan',saved)
    if accepted:
        assert result['intent_status']=='ACKNOWLEDGED' and result['reason'] is None
        assert not status(a,saved).get('operator_action_required',False)
        advance(*ready,1)
        a.plan_owner.observations.journal.uncertain('fake-account',first['intent_id'],reason='DISCONNECT',now=a.observation_context()['market_at'])
        assert not status(a,saved).get('operator_action_required',False)
    else:
        assert result['reason']=='UNRESOLVED_LIMIT' and status(a,saved)['operator_action_required'] is True
    assert a.handle(p)==warning and broker(a).snapshot()['calls']==calls

@pytest.mark.parametrize('failure',['ignore','abort'])
def test_failed_result_write_keeps_warning_visible_without_retry(ready,monkeypatch,failure):
    a,saved,first=expired(ready,monkeypatch,accepted=False);calls=broker(a).snapshot()['calls'];p=request(saved)
    sql='RAISE(IGNORE)' if failure=='ignore' else "RAISE(ABORT,'injected result failure')"
    with a.store.conn:a.store.conn.execute(f'CREATE TRIGGER stop_result BEFORE INSERT ON fake_plan_results BEGIN SELECT {sql}; END')
    import sqlite3
    with pytest.raises((RuntimeRefused,sqlite3.IntegrityError)):a.handle(p)
    with a.store.conn:a.store.conn.execute('DROP TRIGGER stop_result')
    assert a.handle(p)['status']=='PENDING_UNCONFIRMED'
    visible=status(a,saved);assert visible['reason']=='UNRESOLVED_LIMIT' and visible['operator_action_required'] is True
    assert phase(a,'reconcile_plan',saved)['reason']=='UNRESOLVED_LIMIT' and broker(a).snapshot()['calls']==calls

@pytest.mark.parametrize('change',['false_action','invented_start','missing_action','numeric_action'])
def test_rehashed_warning_mirrors_need_incident_evidence(ready,monkeypatch,change):
    a,saved,first=expired(ready,monkeypatch,accepted=False);p=request(saved);warning=a.handle(p);calls=broker(a).snapshot()['calls']
    assert warning['reason']=='UNRESOLVED_LIMIT';forged=dict(warning)
    if change=='false_action':forged['operator_action_required']=False
    elif change=='numeric_action':forged['operator_action_required']=1
    elif change=='invented_start':forged['incident_started_at']='2023-10-17T13:00:00Z'
    else:forged.pop('operator_action_required')
    raw=canonical(forged).decode()
    with a.store.conn:
        a.store.conn.execute('UPDATE fake_plan_results SET sha256=?,body=? WHERE request_id=?',(hashlib.sha256(raw.encode()).hexdigest(),raw,p['request_id']))
        a.store.conn.execute('UPDATE fake_operator_requests SET result=? WHERE request_id=?',(raw,p['request_id']))
    with pytest.raises(RuntimeRefused,match='OPERATION_STATE_CORRUPT'):a.handle(p)
    assert broker(a).snapshot()['calls']==calls
