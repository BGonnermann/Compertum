"""Native owners and clocks; reserve capacity is explicitly simulated by fixture."""
from types import SimpleNamespace
from uuid import uuid4
import pytest
from test_execution_authority import authority,packet,profile,session,advance
from test_execution_health import pair
from compertum.runtime.errors import RuntimeRefused
from compertum.domain import ContractError
from compertum.execution_contracts import instant
from compertum.execution_plans import build_plan
from compertum.deterministic_broker import DeterministicBroker
from compertum.fake_economic_opening import provision_opening
from compertum.fake_execution_journal import FakeIntentJournal


def observed_owner(authority):
    from compertum.execution_observations import FakeObservationOwner
    a,e,w,c=authority;session(a);a.handle(packet('supervise'))
    FakeIntentJournal(a.store)
    broker=DeterministicBroker(a.store.root/'state/fake-broker',cash='5500',positions={'AAPL':45})
    try:provision_opening(a.store,broker,cash='5500',positions={'AAPL':45})
    finally:broker.close()
    return FakeObservationOwner(a)


def test_owner_reads_independent_balances_and_builds_control_only_observation(authority):
    owner=observed_owner(authority);record,context=owner.read();o=record.to_payload()
    assert o['account']['broker_cash']==o['account']['sleeve_cash']=='5500'
    assert o['positions']==[{'symbol':'AAPL','quantity':'45','owned_quantity':45}]
    assert not o['authority']['strategy_admitted'] and not o['authority']['armed'] and o['authority']['halted']
    assert o['account']['prior_close_nav']==o['account']['prior_peak_nav']=='0'
    assert o['feed']=='fixture' and o['scope']=='DETERMINISTIC_FAKE'
    assert context['session_id']==authority[0].status()['session_id']
    plan=build_plan(record,kind='CLOSE_LONG',now=o['observed_at'],calendar=context['calendar'])
    assert [x['maximum_quantity'] for x in plan.to_payload()['children']]==[19,19,7]


def test_native_peer_and_supervision_ages_are_not_reset_when_observed(authority):
    owner=observed_owner(authority);a,e,w,c=authority;first,_=owner.read();start=first.to_payload()['observed_at']
    advance(a,e,w,c,20);c.mono+=2;c.utc+=2
    later,_=owner.read();o=later.to_payload()
    assert (instant(o['observed_at'])-instant(start)).total_seconds()==22
    assert o['health']['supervision_at']==start
    assert (instant(o['observed_at'])-instant(o['health']['watchdog_at'])).total_seconds()==2


@pytest.mark.parametrize('failure',['halt','health','supervision'])
def test_lost_native_authority_refuses_observation(authority,failure):
    owner=observed_owner(authority);a,e,w,c=authority
    if failure=='halt':a.handle(packet('halt'))
    elif failure=='health':e.halt('PEER_UNAVAILABLE')
    else:advance(a,e,w,c,301)
    with pytest.raises(RuntimeRefused):owner.read()


def test_changed_session_does_not_reset_independent_broker(authority):
    owner=observed_owner(authority);before,old=owner.read();a,e,w,c=authority
    session(a);a.handle(packet('supervise'));after,new=owner.read()
    assert old['session_id']!=new['session_id']
    assert after.to_payload()['account']['broker_cash']==before.to_payload()['account']['broker_cash']
    assert after.to_payload()['positions']==before.to_payload()['positions']


def test_changed_account_cannot_relabel_existing_broker(authority):
    owner=observed_owner(authority);owner.read();a,e,w,c=authority;p=profile();p['account_alias']='fake-other'
    a.handle(packet('open_session',session_id=str(uuid4()),profile=p));a.handle(packet('supervise'))
    with pytest.raises((RuntimeRefused,ContractError)):owner.read()


def test_uncertain_preserved_attempt_blocks_new_control_plan(authority):
    from test_fake_execution_journal import checked_records,arguments
    from test_execution_risk import NOW
    owner=observed_owner(authority);owner.read();a=authority[0];i,d=checked_records(a.store.lease)
    owner.journal.record_checked(i,d);owner.journal.begin_attempt(*arguments(i),now=NOW)
    record,context=owner.read();o=record.to_payload()
    assert o['authority']['unknown_intents'] and o['account']['submissions']==1
    with pytest.raises(ContractError,match='UNKNOWN_INTENT'):
        build_plan(record,kind='CLOSE_LONG',now=o['observed_at'],calendar=context['calendar'])


def test_missing_guard_is_not_replaced_by_new_observation(authority):
    owner=observed_owner(authority);owner.read();a=authority[0];path=a.store.root/'state/fake-execution-attempts/head.json'
    path.rename(path.with_name('preserved-head.json'))
    with pytest.raises(RuntimeRefused,match='EXECUTION_COMPROMISED'):owner.read()
    assert not path.exists()


def test_observation_cannot_commit_an_unfinished_owner_transaction(authority):
    owner=observed_owner(authority);owner.read();a=authority[0]
    a.store.conn.execute("INSERT INTO state VALUES('fixture.pending','true')")
    try:
        with pytest.raises(RuntimeRefused,match='OBSERVATION_TRANSACTION_OPEN'):owner.read()
        assert a.store.conn.in_transaction
    finally:a.store.conn.rollback()
    assert a.store.get_state('fixture.pending') is None


def test_caller_shaped_authority_is_not_accepted(authority):
    from compertum.execution_observations import FakeObservationOwner
    with pytest.raises(RuntimeRefused,match='WRONG_OWNER_ROLE'):FakeObservationOwner(SimpleNamespace(store=authority[0].store))

def test_broker_link_cannot_escape_project_or_create_external_files(authority,tmp_path):
    owner=observed_owner(authority);path=owner.store.root/'state/fake-broker'
    path.rename(path.with_name('preserved-broker'))
    outside=tmp_path.parent/('outside-'+str(uuid4()));outside.mkdir()
    path.symlink_to(outside,target_is_directory=True)
    with pytest.raises(RuntimeRefused,match='PATH_DENIED|REPARSE_DENIED'):owner.read()
    assert list(outside.iterdir())==[]


def test_missing_broker_after_terminal_fill_cannot_reset_account(authority):
    from compertum.execution_observations import FakeObservationOwner
    from compertum.fake_execution_journal import FakeIntentJournal
    from test_fake_execution_journal import checked_records,arguments,observed
    from test_execution_risk import NOW
    owner=observed_owner(authority);store=owner.store;j=FakeIntentJournal(store)
    i,d=checked_records(store.lease);j.record_checked(i,d);j.begin_attempt(*arguments(i),now=NOW)
    path=store.root/'state/fake-broker';b=DeterministicBroker(path)
    try:
        ack=b.submit(i);n=i.to_payload()['quantity'];b.fill(ack['order_id'],n,'100')
        j.observe(*arguments(i),observed(i,store.lease,filled=n,status='FILLED',order_id=ack['order_id']),event_id=str(uuid4()))
        assert j.read(*arguments(i))['status']=='FILLED'
    finally:b.close()
    path.rename(path.with_name('preserved-broker'))
    with pytest.raises(RuntimeRefused,match='FAKE_BROKER_MISSING'):FakeObservationOwner(authority[0]).read()
    assert not path.exists()


def test_observation_never_initializes_a_missing_fixture_account(authority):
    from compertum.execution_observations import FakeObservationOwner
    a=authority[0];session(a);a.handle(packet('supervise'));path=a.store.root/'state/fake-broker'
    with pytest.raises(RuntimeRefused,match='FAKE_BROKER_MISSING'):FakeObservationOwner(a).read()
    assert not path.exists()


@pytest.mark.parametrize('key,value',[('fake_attempt_conflict','true'),('execution_status','"EXECUTION_COMPROMISED"')])
def test_preserved_compromise_latch_refuses_before_broker_open(authority,key,value):
    owner=observed_owner(authority);path=owner.store.root/'state/fake-broker';before={p.name:p.read_bytes() for p in path.iterdir()}
    with owner.store.conn:owner.store.conn.execute('INSERT INTO state VALUES(?,?)',(key,value))
    with pytest.raises(RuntimeRefused,match='EXECUTION_COMPROMISED'):owner.read()
    assert owner.broker is None and {p.name:p.read_bytes() for p in path.iterdir()}==before


def test_missing_broker_account_row_cannot_be_recreated(authority):
    import sqlite3
    owner=observed_owner(authority);path=owner.store.root/'state/fake-broker/deterministic-broker.sqlite'
    db=sqlite3.connect(path)
    with db:db.execute('DELETE FROM account')
    db.close()
    with pytest.raises(ContractError,match='FAKE_STORE_IDENTITY'):owner.read()
    db=sqlite3.connect(path)
    try:assert db.execute('SELECT count(*) FROM account').fetchone()==(0,)
    finally:db.close()


def test_open_observer_pins_broker_directory_and_closes_with_owner(authority):
    owner=observed_owner(authority);owner.read();path=owner.store.root/'state/fake-broker'
    with pytest.raises(OSError):path.rename(path.with_name('replacement'))
    owner.close();owner.close()
    with pytest.raises(RuntimeRefused,match='OBSERVATION_OWNER_CLOSED'):owner.read()
    path.rename(path.with_name('preserved-broker'))


@pytest.mark.parametrize('key,value',[
    ('execution_status','"UNVERIFIED"'),('execution_status','null'),('execution_status','false'),
    ('execution_status','"'+('x'*100000)+'"'),('fake_attempt_conflict','[]'),
    ('fake_attempt_conflict','0'),('fake_attempt_conflict','null'),('fake_attempt_conflict','{}')],ids=['unknown','null-status','false-status','oversized','list-conflict','zero-conflict','null-conflict','object-conflict'])
def test_malformed_compromise_state_never_means_trusted(authority,key,value):
    owner=observed_owner(authority)
    with owner.store.conn:owner.store.conn.execute('INSERT INTO state VALUES(?,?)',(key,value))
    with pytest.raises(RuntimeRefused,match='EXECUTION_COMPROMISED'):owner.read()
    assert owner.broker is None


def test_pin_close_failure_still_releases_other_native_pins(authority,monkeypatch):
    owner=observed_owner(authority);owner.read();directory,database=owner.pins;original=type(database).close
    def close(handle):
        was_open=not handle.closed;original(handle)
        if handle is database and was_open:raise RuntimeRefused('CLOSE_FIXTURE_FAILURE')
    monkeypatch.setattr(type(database),'close',close)
    with pytest.raises(RuntimeRefused,match='CLOSE_FIXTURE_FAILURE'):owner.close()
    try:assert directory.closed and database.closed
    finally:original(directory);original(database)
    path=owner.store.root/'state/fake-broker';path.rename(path.with_name('preserved-broker'))
    owner.close()


def test_failed_broker_open_closes_all_pins_even_after_close_error(authority,monkeypatch):
    import compertum.execution_observations as module
    from compertum.runtime._windows import OwnedHandle
    owner=observed_owner(authority);original=OwnedHandle.close;captured={}
    with owner.store._live() as guard:api=guard.api
    opening=api.open_file
    def opened(path,*args,**kwargs):
        handle=opening(path,*args,**kwargs)
        if path.name in ('fake-broker','deterministic-broker.sqlite'):captured[path.name]=handle
        return handle
    def close(handle):
        was_open=not handle.closed;original(handle)
        if handle is captured.get('deterministic-broker.sqlite') and was_open:raise RuntimeRefused('CLOSE_FIXTURE_FAILURE')
    def fail(*args,**kwargs):raise RuntimeRefused('OPEN_FIXTURE_FAILURE')
    monkeypatch.setattr(api,'open_file',opened);monkeypatch.setattr(OwnedHandle,'close',close);monkeypatch.setattr(module,'DeterministicBroker',fail)
    try:
        with pytest.raises(RuntimeRefused,match='OPEN_FIXTURE_FAILURE'):owner.read()
        assert set(captured)=={'fake-broker','deterministic-broker.sqlite'} and all(h.closed for h in captured.values())
        path=owner.store.root/'state/fake-broker';path.rename(path.with_name('preserved-broker'))
    finally:
        for handle in captured.values():original(handle)
