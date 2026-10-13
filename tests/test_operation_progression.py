"""Execution-owned finite progression. Small native fixtures simulate reserve size."""
import json
from uuid import uuid4
import pytest
from test_execution_health import pair
from test_execution_authority import authority,packet,advance,session
from test_saved_plan_controls import ready,prepare,phase,inspect
from compertum.runtime.errors import RuntimeRefused


def started(a):
    saved=prepare(a);phase(a,'approve_plan',saved);phase(a,'start_plan',saved);return saved


def step(a,saved,**kw):return phase(a,'advance_plan',saved,**kw)


def broker(a):return a.plan_owner.observations.broker


def submissions(a):return [v for v in broker(a).snapshot()['calls'] if v['kind']=='SUBMIT']


def finish(a,result,qty=None):
    b=broker(a);order=next(v for v in b.snapshot()['orders'] if v['order_id']==result['order_id'])
    qty=order['quantity'] if qty is None else qty
    if qty:b.fill(order['order_id'],qty,'100')
    if qty<order['quantity']:
        cancel=a.handle(packet('prepare_plan',kind='CANCEL'));phase(a,'approve_plan',cancel);phase(a,'start_plan',cancel)
        step(a,cancel);b.finish_cancel(order['order_id']);step(a,cancel)


def test_native_owner_commits_selection_before_dispatch_and_exact_retry_is_inert(ready,monkeypatch):
    from compertum.fake_execution_driver import FakeExecutionDriver
    a=ready[0];saved=started(a);run=FakeExecutionDriver.dispatch;seen=[]
    def observed(self,intent,observation,**kwargs):
        assert not a.store.conn.in_transaction
        row=a.store.conn.execute('SELECT body FROM fake_plan_steps').fetchone();value=json.loads(row[0])
        receipt=json.loads(a.store.conn.execute('SELECT result FROM fake_operator_requests WHERE request_id=?',(value['request_id'],)).fetchone()[0])
        assert value['intent']==intent.to_payload() and receipt['status']=='PENDING_UNCONFIRMED'
        seen.append(value);return run(self,intent,observation,**kwargs)
    monkeypatch.setattr(FakeExecutionDriver,'dispatch',observed)
    p=packet('advance_plan',plan_id=saved['plan_id'],plan_sha256=saved['plan_sha256']);first=a.handle(p)
    assert first['status']=='PENDING' and first['intent_status']=='ACKNOWLEDGED' and first['quantity']==19 and not first['financial_accepted']
    assert a.handle(p)==first and len(submissions(a))==1 and len(seen)==1
    assert step(a,saved)['status']=='PENDING' and len(submissions(a))==1
    p['subject_key']='b'*64
    with pytest.raises(RuntimeRefused,match='REQUEST_CONFLICT'):a.handle(p)


def test_serial_full_close_requires_terminal_evidence_then_fresh_flat(ready):
    a=ready[0];saved=started(a)
    for quantity in (19,19,7):
        result=step(a,saved);assert result['quantity']==quantity and result['status']=='PENDING'
        finish(a,result);assert step(a,saved)['intent_status']=='FILLED'
    result=step(a,saved)
    assert result['status']=='COMPLETE' and result['remaining_positions']==[] and result['open_order_ids']==[]
    assert broker(a).snapshot()['cash']=='10000' and len(submissions(a))==3
    assert step(a,saved)['status']=='COMPLETE' and len(submissions(a))==3


def test_partial_terminal_fills_never_enlarge_remaining_children(ready):
    a=ready[0];saved=started(a)
    for maximum,filled in ((19,7),(19,19),(7,7)):
        result=step(a,saved);assert result['quantity']==maximum
        finish(a,result,filled);step(a,saved)
    result=step(a,saved)
    assert result['status']=='BLOCKED_RESIDUAL' and result['remaining_positions']==[{'symbol':'AAPL','quantity':12}]
    assert broker(a).snapshot()['cash']=='8800' and len(submissions(a))==3


@pytest.mark.parametrize('boundary',['before_driver','after_accept'])
def test_interrupted_pending_request_never_redispatches(ready,monkeypatch,boundary):
    from compertum.fake_execution_driver import FakeExecutionDriver
    a=ready[0];saved=started(a);dispatch=FakeExecutionDriver.dispatch
    def crash(self,*args,**kwargs):
        if boundary=='after_accept':dispatch(self,*args,**kwargs)
        raise RuntimeError('injected process boundary')
    monkeypatch.setattr(FakeExecutionDriver,'dispatch',crash)
    p=packet('advance_plan',plan_id=saved['plan_id'],plan_sha256=saved['plan_sha256'])
    with pytest.raises(RuntimeError,match='injected'):a.handle(p)
    assert a.handle(p)['status']=='PENDING_UNCONFIRMED'
    monkeypatch.setattr(FakeExecutionDriver,'dispatch',dispatch)
    result=step(a,saved)
    assert result['status']==('PENDING' if boundary=='after_accept' else 'PENDING_UNCONFIRMED')
    assert len(submissions(a))==(boundary=='after_accept')


def test_timeout_acceptance_keeps_one_id_and_blocks_all_children(ready,monkeypatch):
    from compertum.deterministic_broker import DeterministicBroker
    a=ready[0];saved=started(a);submit=DeterministicBroker.submit
    def timeout(self,intent,**kwargs):return submit(self,intent,outcome='TIMEOUT_AFTER_ACCEPT',invisible_lookups=6)
    monkeypatch.setattr(DeterministicBroker,'submit',timeout)
    first=step(a,saved);assert first['status']=='UNKNOWN'
    for seconds in (0,2,3,5,10,10):
        advance(*ready,seconds);assert step(a,saved)['status']=='UNKNOWN'
    assert len(submissions(a))==1
    assert broker(a).snapshot()['positions']=={'AAPL':45}


@pytest.mark.parametrize('event',['halt','session','expiry'])
def test_invalidated_started_operation_cannot_dispatch(ready,event):
    a=ready[0];saved=started(a)
    if event=='halt':a.handle(packet('halt'))
    elif event=='session':session(a)
    else:advance(*ready,301)
    a.handle(packet('supervise'))
    with pytest.raises(RuntimeRefused,match='PLAN_CONTEXT_CHANGED'):step(a,saved)
    assert submissions(a)==[]


def test_unknown_after_deadline_remains_unknown_and_accepted_order_is_not_canceled(ready):
    a=ready[0];saved=started(a);first=step(a,saved)
    advance(*ready,290);a.handle(packet('supervise'));advance(*ready,290);a.handle(packet('supervise'));advance(*ready,21)
    result=step(a,saved)
    assert result['status']=='PENDING' and result['order_id']==first['order_id'] and len(submissions(a))==1
    assert not [v for v in broker(a).snapshot()['calls'] if v['kind']=='CANCEL']


def test_deadline_blocks_unsubmitted_children_with_exact_remainder(ready):
    a=ready[0];saved=started(a)
    for seconds in (290,290,21):advance(*ready,seconds);a.handle(packet('supervise'))
    result=step(a,saved)
    assert result['status']=='BLOCKED_RESIDUAL' and result['reason']=='PLAN_EXPIRED' and result['remaining_positions']==[{'symbol':'AAPL','quantity':45}]
    assert not submissions(a)


@pytest.mark.parametrize('extra',[{'quantity':1},{'intent_id':str(uuid4())},{'outcome':'ACK'},{'now':'2023-10-17T13:35:10Z'}])
def test_public_progress_cannot_supply_economic_or_authority_inputs(ready,extra):
    a=ready[0];saved=started(a)
    with pytest.raises(RuntimeRefused,match='CONTROL_PAYLOAD_DENIED'):step(a,saved,**extra)
    assert submissions(a)==[]


@pytest.mark.parametrize('table',['fake_plan_steps','fake_plan_results'])
def test_ignored_evidence_write_never_claims_effect(ready,table):
    a=ready[0];saved=started(a)
    # First call initializes the operation schema before a forced failure.
    from compertum.execution_operation_owner import FakeOperationOwner
    owner=FakeOperationOwner(a.plan_owner);owner._schema()
    with a.store.conn:a.store.conn.execute(f'CREATE TRIGGER ignore_step BEFORE INSERT ON {table} BEGIN SELECT RAISE(IGNORE); END')
    p=packet('advance_plan',plan_id=saved['plan_id'],plan_sha256=saved['plan_sha256'])
    with pytest.raises(RuntimeRefused,match='OPERATION_WRITE_UNVERIFIED'):a.handle(p)
    assert len(submissions(a))==(table=='fake_plan_results')
    if table=='fake_plan_results':assert a.handle(p)['status']=='PENDING_UNCONFIRMED'


def test_prepared_evidence_cannot_be_removed_or_rehashed_to_new_quantity(ready):
    import hashlib
    from compertum.events import canonical
    a=ready[0];saved=started(a);step(a,saved)
    key,raw=a.store.conn.execute('SELECT request_id,body FROM fake_plan_steps').fetchone();value=json.loads(raw)
    value['intent']['quantity']=20;raw=canonical(value).decode()
    with a.store.conn:a.store.conn.execute('UPDATE fake_plan_steps SET body=?,sha256=? WHERE request_id=?',(raw,hashlib.sha256(raw.encode()).hexdigest(),key))
    with pytest.raises(RuntimeRefused,match='OPERATION_STATE_CORRUPT'):step(a,saved)
    assert len(submissions(a))==1
