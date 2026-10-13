"""Late independent evidence must resolve ambiguity without another broker call."""
import pytest
from test_execution_health import pair
from test_execution_authority import authority,packet,advance
from test_saved_plan_controls import ready,phase
from test_operation_progression import started,step,broker,submissions
from compertum.runtime.errors import RuntimeRefused


def expired(ready,monkeypatch,*,accepted=True):
    from compertum.deterministic_broker import DeterministicBroker
    a=ready[0];saved=started(a);submit=DeterministicBroker.submit
    def timeout(self,intent,**kwargs):return submit(self,intent,outcome='TIMEOUT_AFTER_ACCEPT' if accepted else 'TIMEOUT_BEFORE_ACCEPT',invisible_lookups=6)
    monkeypatch.setattr(DeterministicBroker,'submit',timeout)
    first=step(a,saved);assert first['status']=='UNKNOWN'
    prior=0
    for seconds in (0,2,5,10,20,30,120):
        advance(*ready,seconds-prior);prior=seconds
        assert step(a,saved)['status']=='UNKNOWN'
    calls=broker(a).snapshot()['calls']
    assert sum(v['kind']=='SUBMIT' for v in calls)==1 and sum(v['kind']=='LOOKUP' for v in calls)==6
    return a,saved,first


def incident(a):return a.store.conn.execute('SELECT started_at,next_index,last_elapsed,active FROM fake_incidents ORDER BY rowid DESC LIMIT 1').fetchone()


@pytest.mark.parametrize('state',['ACKNOWLEDGED','FILLED','CANCELED'])
def test_explicit_late_positive_evidence_resolves_without_lookup_or_resubmit(ready,monkeypatch,state):
    if state=='CANCELED':
        from compertum.deterministic_broker import DeterministicBroker
        from test_operation_cancellation import seed,plan
        a=ready[0];first=seed(a);saved=plan(a,'CANCEL');b=broker(a)
        cancel=DeterministicBroker.request_cancel
        def timeout(self,order_id,**kwargs):
            with self.db:self.db.execute('UPDATE orders SET hidden=6')
            return cancel(self,order_id,outcome='TIMEOUT_AFTER_REQUEST')
        monkeypatch.setattr(DeterministicBroker,'request_cancel',timeout)
        assert step(a,saved)['status']=='UNKNOWN'
        prior=0
        for seconds in (0,2,5,10,20,30,120):
            advance(*ready,seconds-prior);prior=seconds
            assert step(a,saved)['status']=='UNKNOWN'
        assert sum(v['kind']=='LOOKUP' for v in b.snapshot()['calls'])==6
    else:a,saved,first=expired(ready,monkeypatch);b=broker(a)
    order=b.snapshot()['orders'][0]
    if state=='FILLED':b.fill(order['order_id'],19,'100')
    elif state=='CANCELED':b.finish_cancel(order['order_id'])
    before=incident(a);calls=b.snapshot()['calls'];a.handle(packet('supervise'))
    request=packet('reconcile_plan',plan_id=saved['plan_id'],plan_sha256=saved['plan_sha256']);result=a.handle(request)
    assert result['intent_status']==state and result['order_id']==order['order_id']
    assert result['filled_quantity']==(19 if state=='FILLED' else 0)
    assert incident(a)==(*before[:3],0) and b.snapshot()['calls']==calls
    assert a.handle(request)==result and b.snapshot()['calls']==calls


def test_absent_late_evidence_keeps_unknown_and_incident_budget(ready,monkeypatch):
    a,saved,first=expired(ready,monkeypatch,accepted=False);before=incident(a);calls=broker(a).snapshot()['calls']
    assert phase(a,'reconcile_plan',saved)['status']=='UNKNOWN'
    assert incident(a)==before and broker(a).snapshot()['calls']==calls


def test_late_positive_evidence_cannot_clear_sticky_conflict(ready,monkeypatch):
    a,saved,first=expired(ready,monkeypatch);j=a.plan_owner.observations.journal
    j.uncertain('fake-account',first['intent_id'],reason='CONFLICTING_OBSERVATION',now=a.require_supervised()['market_at'])
    before=incident(a);calls=broker(a).snapshot()['calls']
    assert phase(a,'reconcile_plan',saved)['status']=='UNKNOWN'
    assert incident(a)==before and broker(a).snapshot()['calls']==calls


def test_late_reconciliation_refuses_backward_incident_time(ready,monkeypatch):
    a,saved,first=expired(ready,monkeypatch);calls=broker(a).snapshot()['calls']
    with a.store.conn:a.store.conn.execute('UPDATE fake_incidents SET last_elapsed=121')
    with pytest.raises(RuntimeRefused,match='INCIDENT_CLOCK_REVERSED'):phase(a,'reconcile_plan',saved)
    assert broker(a).snapshot()['calls']==calls

@pytest.mark.parametrize('fault',['binding','io'])
def test_new_reconciliation_failure_is_durable_unknown(ready,monkeypatch,fault):
    import json,sqlite3
    from compertum.deterministic_broker import DeterministicBroker
    a=ready[0];saved=started(a);first=step(a,saved);b=broker(a);snapshot=b.snapshot
    reads=[]
    def failing():
        reads.append(True)
        if len(reads)==2 and fault=='io':raise sqlite3.OperationalError('independent snapshot unavailable')
        value=snapshot()
        # Initial owner observation qualifies; the later independent driver read
        # must latch a newly observed conflict without another effect.
        if len(reads)==2 and fault=='binding':value['orders'][0]['quantity']=18
        return value
    monkeypatch.setattr(b,'snapshot',failing)
    calls=snapshot()['calls'];result=phase(a,'reconcile_plan',saved)
    assert result['status']=='UNKNOWN'
    row=a.plan_owner.observations.journal.read('fake-account',first['intent_id'])
    assert row['status']=='UNKNOWN' and row['conflicting_observation']==(fault=='binding')
    assert a.plan_owner.observations.read()[0].to_payload()['authority']['unknown_intents']
    assert snapshot()['calls']==calls
