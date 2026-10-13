"""Native owner/store saved controls; only reserve capacity is simulated."""
import json
from uuid import uuid4
import pytest
from test_execution_authority import authority,packet,session,advance
from test_execution_health import pair
from test_execution_observations import observed_owner
from compertum.runtime.errors import RuntimeRefused
from compertum.execution_contracts import instant


@pytest.fixture
def ready(authority):
    observed_owner(authority)
    return authority


def prepare(a,**kw):return a.handle(packet('prepare_plan',kind='CLOSE_LONG',**kw))
def phase(a,operation,saved,**kw):return a.handle(packet(operation,plan_id=saved['plan_id'],plan_sha256=saved['plan_sha256'],**kw))
def inspect(a,saved):return a.handle(packet('inspect_plan',plan_id=saved['plan_id']))


def test_saved_original_plan_fresh_approval_and_start_have_no_effects(ready):
    a,e,w,c=ready;saved=prepare(a);view=inspect(a,saved)
    assert [v['maximum_quantity'] for v in view['plan']['children']]==[19,19,7]
    original=a.store.conn.execute('SELECT body FROM fake_saved_plans WHERE plan_id=?',(saved['plan_id'],)).fetchone()[0]
    advance(a,e,w,c,30);approved=phase(a,'approve_plan',saved)
    advance(a,e,w,c,29);started=phase(a,'start_plan',saved)
    assert (saved['status'],approved['status'],started['status'])==('PREPARED','APPROVED','STARTED_NO_DISPATCH')
    assert all(v['receipt_only'] and not v['effects_enabled'] and not v['financial_accepted'] for v in (saved,approved,started))
    assert a.store.conn.execute('SELECT body FROM fake_saved_plans WHERE plan_id=?',(saved['plan_id'],)).fetchone()[0]==original
    rows=dict(a.store.conn.execute('SELECT phase,body FROM fake_saved_plan_phases WHERE plan_id=?',(saved['plan_id'],)))
    assert set(rows)=={'APPROVAL','START'}
    assert (instant(json.loads(rows['APPROVAL'])['record']['authorized_at'])-instant(view['plan']['created_at'])).total_seconds()==30
    assert (instant(json.loads(rows['START'])['record']['started_at'])-instant(view['plan']['created_at'])).total_seconds()==59
    assert a.plan_owner.observations.broker.snapshot()['calls']==[]
    assert a.store.conn.execute('SELECT count(*) FROM fake_intents').fetchone()==(0,)


def test_exact_request_retry_keeps_receipt_and_never_extends_plan(ready):
    a,e,w,c=ready;p=packet('prepare_plan',kind='CLOSE_LONG');first=a.handle(p);advance(a,e,w,c,61)
    assert a.handle(p)==first and a.store.conn.execute('SELECT count(*) FROM fake_saved_plans').fetchone()==(1,)
    with pytest.raises(RuntimeRefused,match='PLAN_EXPIRED'):phase(a,'approve_plan',first)
    p['subject_key']='b'*64
    with pytest.raises(RuntimeRefused,match='REQUEST_CONFLICT'):a.handle(p)


def test_plan_and_authority_commands_share_request_identity(ready):
    a=ready[0];p=packet('prepare_plan',kind='CLOSE_LONG');a.handle(p)
    changed=dict(p,command={'operation':'halt'})
    with pytest.raises(RuntimeRefused,match='REQUEST_CONFLICT'):a.handle(changed)
    assert a.status()['supervised']


@pytest.mark.parametrize('operation,extra',[('prepare_plan',{'observation':{}}),('prepare_plan',{'now':'2023-01-01T00:00:00Z'}),('approve_plan',{'health':True}),('start_plan',{'intent':{}}),('inspect_plan',{'generation':1})])
def test_public_saved_controls_reject_injected_inputs(ready,operation,extra):
    a=ready[0];saved=prepare(a);command={'operation':operation,**extra}
    if operation=='prepare_plan':command['kind']='CLOSE_LONG'
    else:command['plan_id']=saved['plan_id']
    if operation in ('approve_plan','start_plan'):command['plan_sha256']=saved['plan_sha256']
    with pytest.raises(RuntimeRefused,match='CONTROL_PAYLOAD_DENIED'):a.handle(packet(**command))


@pytest.mark.parametrize('operation',['approve_plan','start_plan'])
def test_operator_must_name_exact_reviewed_plan_digest(ready,operation):
    a=ready[0];saved=prepare(a)
    with pytest.raises(RuntimeRefused,match='PLAN_DIGEST_CHANGED'):
        a.handle(packet(operation,plan_id=saved['plan_id'],plan_sha256='0'*64))


def test_start_requires_saved_approval_and_both_phases_are_one_time(ready):
    a=ready[0];saved=prepare(a)
    with pytest.raises(RuntimeRefused,match='PLAN_APPROVAL_REQUIRED'):phase(a,'start_plan',saved)
    phase(a,'approve_plan',saved)
    with pytest.raises(RuntimeRefused,match='PLAN_ALREADY_APPROVED'):phase(a,'approve_plan',saved)
    p=packet('start_plan',plan_id=saved['plan_id'],plan_sha256=saved['plan_sha256']);first=a.handle(p)
    assert a.handle(p)==first
    with pytest.raises(RuntimeRefused,match='PLAN_ALREADY_STARTED'):phase(a,'start_plan',saved)


@pytest.mark.parametrize('event',['halt','supervision_expiry','session'])
def test_invalidated_plan_does_not_revive_with_renewed_supervision(ready,event):
    a,e,w,c=ready
    if event=='supervision_expiry':advance(a,e,w,c,290)
    saved=prepare(a);phase(a,'approve_plan',saved)
    if event=='halt':a.handle(packet('halt'))
    elif event=='supervision_expiry':advance(a,e,w,c,11)
    else:session(a)
    a.handle(packet('supervise'))
    assert inspect(a,saved)['plan_id']==saved['plan_id']
    with pytest.raises(RuntimeRefused,match='PLAN_CONTEXT_CHANGED'):phase(a,'start_plan',saved)


def test_ordinary_supervision_renewal_keeps_same_plan_context(ready):
    a,e,w,c=ready;saved=prepare(a);advance(a,e,w,c,20);a.handle(packet('supervise'))
    phase(a,'approve_plan',saved);phase(a,'start_plan',saved)


def test_changed_broker_economics_refuse_approval_without_replacing_plan(ready):
    from test_operation_progression import started,step
    a=ready[0];seed=started(a);ack=step(a,seed)
    saved=prepare(a);before=inspect(a,saved)
    phases=a.store.conn.execute('SELECT * FROM fake_saved_plan_phases ORDER BY plan_id,phase').fetchall()
    b=a.plan_owner.observations.broker;b.fill(ack['order_id'],3,'100')
    with pytest.raises(RuntimeRefused,match='PLAN_SNAPSHOT_CHANGED'):phase(a,'approve_plan',saved)
    assert inspect(a,saved)==before and a.store.conn.execute('SELECT * FROM fake_saved_plan_phases ORDER BY plan_id,phase').fetchall()==phases


@pytest.mark.parametrize('table',['fake_saved_plans','fake_saved_plan_phases','fake_operator_requests'])
def test_ignored_durable_write_cannot_acknowledge_or_partially_save(ready,table):
    a=ready[0];saved=prepare(a);before=tuple(a.store.conn.execute('SELECT count(*) FROM '+t).fetchone()[0] for t in ('fake_saved_plans','fake_saved_plan_phases','fake_operator_requests'))
    with a.store.conn:a.store.conn.execute('CREATE TRIGGER fixture_ignore BEFORE INSERT ON '+table+' BEGIN SELECT RAISE(IGNORE); END')
    with pytest.raises(RuntimeRefused,match='WRITE_UNVERIFIED'):
        prepare(a) if table=='fake_saved_plans' else phase(a,'approve_plan',saved)
    after=tuple(a.store.conn.execute('SELECT count(*) FROM '+t).fetchone()[0] for t in ('fake_saved_plans','fake_saved_plan_phases','fake_operator_requests'))
    assert after==before


def test_operator_cannot_commit_an_unfinished_plan_transaction(ready):
    a=ready[0];a.store.conn.execute("INSERT INTO state VALUES('fixture.pending','true')")
    try:
        with pytest.raises(RuntimeRefused,match='OPERATOR_TRANSACTION_OPEN'):prepare(a)
        assert a.store.conn.in_transaction
    finally:a.store.conn.rollback()
    assert a.store.get_state('fixture.pending') is None


def test_partial_or_corrupt_saved_state_is_never_reinitialized(ready):
    a=ready[0];saved=prepare(a)
    with a.store.conn:a.store.conn.execute('DROP TABLE fake_saved_plan_phases')
    with pytest.raises(RuntimeRefused,match='PLAN_STATE_CORRUPT'):inspect(a,saved)
    assert a.store.conn.execute("SELECT name FROM sqlite_master WHERE name='fake_saved_plan_phases'").fetchall()==[]


def test_changed_immutable_record_is_refused(ready):
    a=ready[0];saved=prepare(a)
    with a.store.conn:a.store.conn.execute("UPDATE fake_saved_plans SET body='{}'")
    with pytest.raises(RuntimeRefused,match='PLAN_STATE_CORRUPT'):inspect(a,saved)


def test_saved_plan_bound_leaves_request_and_broker_unchanged(ready):
    a=ready[0]
    for _ in range(32):prepare(a)
    before=a.store.conn.execute('SELECT count(*) FROM fake_operator_requests').fetchone()
    with pytest.raises(RuntimeRefused,match='SAVED_PLAN_BOUND'):prepare(a)
    assert a.store.conn.execute('SELECT count(*) FROM fake_operator_requests').fetchone()==before
    assert a.plan_owner.observations.broker.snapshot()['calls']==[]


@pytest.mark.parametrize('damage',['authorization_snapshot','approval_observation'])
def test_rehashed_inconsistent_approval_cannot_start(ready,damage):
    import hashlib
    from compertum.events import canonical
    a=ready[0];saved=prepare(a);phase(a,'approve_plan',saved)
    raw=a.store.conn.execute("SELECT body FROM fake_saved_plan_phases WHERE phase='APPROVAL'").fetchone()[0];value=json.loads(raw)
    if damage=='authorization_snapshot':value['record']['snapshot_sha256']='f'*64
    else:value['observation']['account']['broker_cash']='4999'
    changed=canonical(value)
    with a.store.conn:a.store.conn.execute("UPDATE fake_saved_plan_phases SET body=?,sha256=? WHERE phase='APPROVAL'",(changed.decode(),hashlib.sha256(changed).hexdigest()))
    with pytest.raises(RuntimeRefused,match='PLAN_STATE_CORRUPT'):phase(a,'start_plan',saved)
    assert a.store.conn.execute("SELECT count(*) FROM fake_saved_plan_phases WHERE phase='START'").fetchone()==(0,)


@pytest.mark.parametrize('lost',['APPROVAL','START'])
def test_lost_phase_with_retained_receipt_never_grants_a_second_phase(ready,lost):
    a=ready[0];saved=prepare(a);approved=phase(a,'approve_plan',saved)
    request=packet('start_plan',plan_id=saved['plan_id'],plan_sha256=saved['plan_sha256']);started=a.handle(request)
    with a.store.conn:a.store.conn.execute('DELETE FROM fake_saved_plan_phases WHERE phase=?',(lost,))
    assert a.handle(request)==started
    with pytest.raises(RuntimeRefused,match='PLAN_STATE_CORRUPT'):
        phase(a,'approve_plan' if lost=='APPROVAL' else 'start_plan',saved)


def test_rehashed_core_conflicts_with_its_original_receipt(ready):
    import hashlib
    from compertum.events import canonical
    a=ready[0];saved=prepare(a)
    value=json.loads(a.store.conn.execute('SELECT body FROM fake_saved_plans').fetchone()[0]);value['context']['epoch']+=1;raw=canonical(value)
    with a.store.conn:a.store.conn.execute('UPDATE fake_saved_plans SET body=?,sha256=?',(raw.decode(),hashlib.sha256(raw).hexdigest()))
    with pytest.raises(RuntimeRefused,match='PLAN_STATE_CORRUPT'):inspect(a,saved)
