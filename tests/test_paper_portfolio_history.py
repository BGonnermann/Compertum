"""Native local stores; invented replies, account origins, clocks and reserves."""
import pytest
from compertum.runtime.errors import RuntimeRefused
from test_paper_portfolio_context import (pair,connect,owner,publication,invented_paper_origin,
    account,context,portfolio,journal_fixture,fresh,advance,acknowledge)

MUTATIONS={
    'events':"INSERT INTO fake_intent_events(account,intent_id,kind,body) VALUES('other','other','UNKNOWN','{}')",
    'broker':"INSERT INTO fake_broker_events VALUES('other','other','unverified')",
    'applications':"INSERT INTO fake_event_applications VALUES('other','other','other')",
    'incidents':"INSERT INTO fake_incidents VALUES('other','other',0,0,NULL,1)",
    'trigger':"CREATE TRIGGER invented_history_trigger AFTER INSERT ON fake_intent_events BEGIN SELECT 1; END",
    'deleted':"DELETE FROM fake_execution_session",
}


@pytest.mark.parametrize('change',MUTATIONS)
def test_complete_history_change_invalidates_original_proof(account,change):
    fixture=journal_fixture(account,'session');o,_,_=fixture;r=portfolio(context(fixture));p=r._prepare_proof()
    head=o.a.db.execute("SELECT value FROM state WHERE key='fake_attempt_guard_head'").fetchone()
    with o.a.db:o.a.db.execute(MUTATIONS[change])
    assert head==o.a.db.execute("SELECT value FROM state WHERE key='fake_attempt_guard_head'").fetchone()
    with pytest.raises(RuntimeRefused):p._verify()
    assert r._closed


def test_deleted_events_leave_nonempty_sequence_evidence(account):
    fixture=journal_fixture(account,'empty');o,_,_=fixture
    with o.a.db:
        o.a.db.execute(MUTATIONS['events']);o.a.db.execute('DELETE FROM fake_intent_events')
    fixture=fresh(fixture);v=portfolio(context(fixture)).diagnostic()
    assert v['history_classification']=='NONEMPTY_LOCAL_HISTORY'
    assert v['observation_status']=='BLOCKED' and v['transport_authorized'] is False


def test_sequence_change_after_capture_invalidates_proof(account):
    fixture=journal_fixture(account,'empty');o,_,_=fixture;r=portfolio(context(fixture));p=r._prepare_proof()
    with o.a.db:o.a.db.execute("INSERT INTO sqlite_sequence(name,seq) VALUES('fake_intent_events',4)")
    with pytest.raises(RuntimeRefused):p._verify()
    assert r._closed


@pytest.mark.parametrize('table,column',[
    ('fake_intents','client_id'),('fake_intent_events','kind'),('fake_broker_events','event_id'),
    ('fake_event_applications','event_id'),('fake_incidents','intent_id'),('fake_execution_session','owner_instance')])
def test_oversized_history_field_refuses_before_materializing(account,table,column):
    fixture=journal_fixture(account,'checked');o,_,_=fixture
    with o.a.db:
        for key in ('events','broker','applications','incidents'):o.a.db.execute(MUTATIONS[key])
        o.a.db.execute('UPDATE '+table+' SET '+column+'=?',('x'*65537,))
    from compertum.runtime.paper_portfolio_context import _journal_snapshot
    before=o.a.db.total_changes
    with pytest.raises(RuntimeRefused):_journal_snapshot(o.a)
    assert before==o.a.db.total_changes


def test_history_row_limit_refuses(account):
    fixture=journal_fixture(account,'empty');o,_,_=fixture
    with o.a.db:o.a.db.executemany("INSERT INTO fake_broker_events VALUES('other',?,'unknown')",[(str(i),) for i in range(513)])
    from compertum.runtime.paper_portfolio_context import _journal_snapshot
    with pytest.raises(RuntimeRefused):_journal_snapshot(o.a)


@pytest.mark.parametrize('reverse',[False,True])
def test_grouped_proof_rechecks_age_after_other_durable_reads(account,reverse):
    from compertum.runtime.paper_final_proof import _verify_proofs
    o,_,_=account;_,presence=acknowledge(account);r=portfolio(context(account));p=r._prepare_proof()
    other=o.a._presence._prepare_proof(subject='a'*64,presence_id=presence['presence_id']);check=other._check
    def delayed():check();advance(o,31)
    other._check=delayed
    with pytest.raises(RuntimeRefused):_verify_proofs(*( (other,p) if reverse else (p,other)))
    assert r._closed


@pytest.mark.parametrize('kind',['positions','orders','blocked'])
def test_current_nonempty_or_blocked_account_never_observes_clean_opening(account,monkeypatch,kind):
    import test_paper_read_owner as fixture_module
    from test_paper_portfolio import position,order
    original=fixture_module.body
    def changed(operation):
        value=original(operation)
        if kind=='positions' and operation=='POSITIONS':return [position()]
        if kind=='orders' and operation=='ORDERS':return [order(client_order_id='foreign-order')]
        if kind=='blocked' and operation=='ACCOUNT':return dict(value,trading_blocked=True)
        return value
    monkeypatch.setattr(fixture_module,'body',changed)
    v=portfolio(context(fresh(account))).diagnostic()
    assert v['observation_status']=='BLOCKED' and v['actual_flat'] is None


def test_missing_confirmation_and_opening_stay_unverified(publication,invented_paper_origin):
    from test_paper_read_publication import launch
    o,pub,_=publication;p=launch(publication)
    for _ in range(10):pub.tick()
    v=portfolio(context((o,pub,p))).diagnostic()
    assert v['observation_status']=='BLOCKED' and v['cash_observation']=='OPENING_UNVERIFIED'
    assert 'ACCOUNT_CONFIRMATION_UNVERIFIED' in v['unverified_requirements']


def test_journal_named_view_cannot_appear_to_be_empty_history(account):
    o,_,_=account
    with o.a.db:o.a.db.execute("CREATE VIEW fake_intents AS SELECT 'retained' AS evidence")
    from compertum.runtime.paper_portfolio_context import _journal_snapshot
    with pytest.raises(RuntimeRefused):_journal_snapshot(o.a)


def test_generated_column_cannot_escape_complete_schema_check(account):
    fixture=journal_fixture(account,'empty');o,_,_=fixture
    with o.a.db:o.a.db.execute("ALTER TABLE fake_intents ADD COLUMN hidden TEXT GENERATED ALWAYS AS ('retained') VIRTUAL")
    from compertum.runtime.paper_portfolio_context import _journal_snapshot
    with pytest.raises(RuntimeRefused):_journal_snapshot(o.a)


@pytest.mark.parametrize('when',['creation','existing'])
def test_closed_captured_connection_refuses_permanently(account,when):
    o,_,_=account;c=context(account);r=portfolio(c) if when=='existing' else None
    o.a.db.close()
    with pytest.raises(RuntimeRefused):
        if r is None:portfolio(c)
        else:r._prepare_proof()
    assert c._closed
    if r is not None:assert r._closed
