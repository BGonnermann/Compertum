"""Native owners and loopback activity; invented opening, clocks and 64 KiB reserve."""
import json
import pickle
from uuid import uuid4

import pytest

from compertum.data.encoding import canonical
from compertum.runtime.errors import RuntimeRefused
from test_execution_health import pair, connect
from test_paper_read_owner import owner
from test_paper_read_publication import publication
from test_paper_account_binding import invented_paper_origin
from test_paper_presence import account
from test_paper_activity_owner import activity, activity_publication, pub_start, finish
from test_paper_market_collection import pages
from test_paper_read_preparation import ACCOUNT, KEY, SECRET


@pytest.fixture
def published_activity(activity_publication):
    o,packet,pub,_,_=activity_publication
    with pages([b'[]']) as (port,seen):
        o.activity_port=port;p=pub_start(activity_publication);finish(o,p)
        for _ in range(12):pub.tick()
        saved=o.a._activities._read(p['activity_id'])
        assert saved['state']=='PUBLISHED'
        yield o,packet,saved,seen


def context(fixture,**changes):
    o,p,saved,_=fixture
    values=dict(subject='a'*64,packet_id=p['packet_id'],activity_id=saved['activity_id'])
    values.update(changes)
    return o.a.reconciliation_context(**values)


def test_original_empty_records_reconcile_privately_without_authority(published_activity):
    o,p,saved,seen=published_activity;before=(o.a.db.total_changes,len(seen))
    c=context(published_activity);v=c.diagnostic()
    assert v['status']=='BLOCKED' and v['observation_status']=='MATCHING_LOOPBACK_OBSERVATIONS'
    assert v['order_count']==v['fill_count']==v['position_count']==0
    assert v['transport_authorized'] is v['financial_accepted'] is False and v['actual_flat'] is None
    assert {'FEE_LIABILITIES_UNVERIFIED','ACTION_EVIDENCE_UNVERIFIED','RISK_UNVERIFIED',
            'DURABLE_CONSUMPTION_UNVERIFIED'}<=set(v['unverified_requirements'])
    assert before==(o.a.db.total_changes,len(seen))
    assert all(value.encode() not in canonical(v) for value in (ACCOUNT,KEY,SECRET,'100000','expected_cash'))
    with pytest.raises(RuntimeRefused):pickle.dumps(c)
    with pytest.raises(RuntimeRefused):type(c)()
    account=c._context;c.close();assert not account._closed
    with pytest.raises(RuntimeRefused):c.diagnostic()


@pytest.mark.parametrize('fault',['subject','packet','activity'])
def test_foreign_original_identifiers_refuse(published_activity,fault):
    changes={'subject':'b'*64} if fault=='subject' else {fault+'_id':str(uuid4())}
    with pytest.raises(RuntimeRefused):context(published_activity,**changes)


def test_missing_current_context_never_reopens_historical_freshness(published_activity):
    o,_,_,_=published_activity;o.a._account_context.close();o.a._account_context=None
    with pytest.raises(RuntimeRefused):context(published_activity)


@pytest.mark.parametrize('fault',['record','artifact','opening','context','expiry','clock_gap'])
def test_changed_originals_permanently_invalidate_wrapper(published_activity,fault):
    o,_,saved,_=published_activity;c=context(published_activity)
    if fault=='record':
        damaged=dict(saved,subject='b'*64)
        with o.a.db:o.a.db.execute('UPDATE state SET value=? WHERE key=?',
            (canonical(damaged).decode(),'paper_activity:'+saved['activity_id']))
    elif fault=='artifact':
        path=o.manager.root/saved['manifest']['path'];path.write_bytes(b'changed')
    elif fault=='opening':
        with o.a.db:o.a.db.execute("UPDATE state SET value='{}' WHERE key='paper_opening:fixture'")
    elif fault=='context':o.a._account_context=None
    else:
        o.clock.utc+=31 if fault=='expiry' else 6
        o.clock.mono+=31 if fault=='expiry' else 0
    with pytest.raises(RuntimeRefused):c.diagnostic()
    assert c._closed
    with pytest.raises(RuntimeRefused):c.diagnostic()


def test_caller_transaction_is_preserved_without_context_revocation(published_activity):
    o,_,_,_=published_activity;c=context(published_activity)
    o.a.db.execute("INSERT INTO state VALUES('caller-uncommitted','true')")
    with pytest.raises(RuntimeRefused):c.diagnostic()
    assert o.a.db.in_transaction and not c._closed and not c._context._closed
    assert o.a.db.execute("SELECT value FROM state WHERE key='caller-uncommitted'").fetchone()==('true',)
    o.a.db.rollback();assert c.diagnostic()['status']=='BLOCKED'


def test_constructor_refuses_closed_database_before_portfolio_callbacks(published_activity,monkeypatch):
    from compertum.runtime import paper_reconciliation_context as module
    o,_,_,_=published_activity
    def unexpected_callback(*args,**kwargs):
        raise AssertionError('Portfolio callback after closed database')
    monkeypatch.setattr(module,'_portfolio_context',unexpected_callback)
    o.a.db.close()
    with pytest.raises(RuntimeRefused) as refused:context(published_activity)
    assert refused.value.code=='PAPER_RECONCILIATION_DATABASE_CLOSED'


def test_published_activity_without_live_context_cannot_supply_a_proof(published_activity):
    o,_,_,_=published_activity;c=context(published_activity)
    c._context.close()
    with pytest.raises(RuntimeRefused):c._prepare_proof()


def test_proof_is_single_use_and_closure_after_capture_refuses(published_activity):
    c=context(published_activity);proof=c._prepare_proof()
    assert proof._verify()['status']=='BLOCKED'
    with pytest.raises(RuntimeRefused):proof._verify()
    second=c._prepare_proof();c.close()
    with pytest.raises(RuntimeRefused):second._verify()
    assert not c._context._closed
    assert c._context.diagnostic()['confirmation_status']=='CONFIRMED_CURRENT_CONTEXT'


@pytest.mark.parametrize('state',['EVIDENCE_READY','ABORTED','INTERRUPTED'])
def test_unpublished_activity_cannot_supply_matching_observations(published_activity,state):
    o,_,saved,_=published_activity;damaged=dict(saved,state=state)
    with o.a.db:o.a.db.execute('UPDATE state SET value=? WHERE key=?',
        (canonical(damaged).decode(),'paper_activity:'+saved['activity_id']))
    with pytest.raises(RuntimeRefused):context(published_activity)


def test_actual_replacement_context_never_revives_prior_wrapper(published_activity):
    o,p,_,_=published_activity;c=context(published_activity)
    replacement=o.a.account_context(subject='a'*64,packet_id=p['packet_id'])
    assert replacement is not c._context
    with pytest.raises(RuntimeRefused):c.diagnostic()
    with pytest.raises(RuntimeRefused):c.diagnostic()


def test_same_alias_credential_substitution_refuses(published_activity):
    from compertum.runtime.paper_credentials import seal_paper_credentials
    from compertum.runtime.paper_credential_slot import _payload
    o,_,_,_=published_activity;c=context(published_activity)
    changed=seal_paper_credentials(o.e.lease,'fixture',bytearray(b'REPLACEMENT_TEST_KEY'),bytearray(b'REPLACEMENT_TEST_SECRET'))
    (o.a.store.root/'state/paper-credentials.bin').write_bytes(_payload(changed))
    with pytest.raises(RuntimeRefused):c.diagnostic()
    assert c._closed


def test_different_account_identity_refuses(published_activity):
    o,_,_,_=published_activity;c=context(published_activity)
    object.__setattr__(o.a._preflight,'_account_id',str(uuid4()))
    with pytest.raises(RuntimeRefused):c.diagnostic()


def test_constructor_and_captured_proof_preserve_pending_transaction(published_activity):
    o,_,_,_=published_activity
    o.a.db.execute("INSERT INTO state VALUES('caller-uncommitted','true')")
    with pytest.raises(RuntimeRefused):context(published_activity)
    assert o.a.db.in_transaction and not o.a._account_context._closed
    o.a.db.rollback();c=context(published_activity);proof=c._prepare_proof()
    o.a.db.execute("INSERT INTO state VALUES('caller-uncommitted','true')")
    with pytest.raises(RuntimeRefused):proof._verify()
    assert not proof._used and not c._closed and o.a.db.in_transaction
    o.a.db.rollback();assert proof._verify()['status']=='BLOCKED'


def test_captured_database_controls_transaction_check_after_replacement(published_activity):
    import sqlite3
    o,_,_,_=published_activity;c=context(published_activity);proof=c._prepare_proof()
    original=o.a.db;replacement=sqlite3.connect(':memory:')
    try:
        original.execute("INSERT INTO state VALUES('caller-uncommitted','true')")
        o.a.db=replacement
        with pytest.raises(RuntimeRefused):proof._verify()
        assert original.in_transaction and not proof._used and not c._closed
        original.rollback();o.a.db=original
        assert proof._verify()['status']=='BLOCKED'
    finally:o.a.db=original;replacement.close()


@pytest.mark.parametrize('fault',['wrapper','owner','database'])
def test_closed_resources_cannot_supply_a_proof(published_activity,fault):
    o,_,_,_=published_activity;c=context(published_activity)
    if fault=='wrapper':c.close()
    elif fault=='owner':o.a.close()
    else:o.a.db.close()
    with pytest.raises(RuntimeRefused):c.diagnostic()
    assert c._closed


def test_changed_record_during_decryption_refuses(published_activity,monkeypatch):
    from contextlib import contextmanager
    from compertum.runtime import paper_reconciliation_context as module
    o,_,saved,_=published_activity;c=context(published_activity);original=module.open_activity_evidence
    @contextmanager
    def changed(*args,**kw):
        with original(*args,**kw) as opened:yield opened
        with o.a.db:o.a.db.execute('UPDATE state SET value=? WHERE key=?',
            (canonical(dict(saved,subject='b'*64)).decode(),'paper_activity:'+saved['activity_id']))
    monkeypatch.setattr(module,'open_activity_evidence',changed)
    with pytest.raises(RuntimeRefused):c.diagnostic()
    assert c._closed


def test_final_durable_read_cannot_hide_expired_original_clock(published_activity,monkeypatch):
    from compertum.runtime import paper_reconciliation_context as module
    o,_,_,_=published_activity;c=context(published_activity);proof=c._prepare_proof();original=module._published
    def delayed(*args):
        result=original(*args);o.clock.utc+=31;o.clock.mono+=31;return result
    monkeypatch.setattr(module,'_published',delayed)
    with pytest.raises(RuntimeRefused):proof._verify()
    assert c._closed


@pytest.mark.parametrize('mode',['complete','missing_fill','older_database','outside_interval'])
def test_native_retained_buy_and_original_nonempty_observations(activity_publication,publication,monkeypatch,mode):
    from compertum.fake_execution_journal import FakeIntentJournal
    from compertum.fake_attempt_guard import append_record
    from compertum.native_attempt_records import sha
    from test_native_attempt_records import records,attempt
    from test_paper_portfolio import order,position
    from test_paper_portfolio_context import fresh
    import test_paper_read_owner as reader
    import sqlite3
    o,_,pub,module,remote=activity_publication
    FakeIntentJournal(o.a.store)
    old=sqlite3.connect(':memory:');o.a.db.backup(old)
    try:
        p,d=records(o.e.lease);p['created_at']='2023-11-24T14:30:00.100000Z';p['expires_at']='2023-11-24T14:31:00.100000Z'
        p['request']['created_at']=p['created_at'];p['request_sha256']=sha(p['request']);d['intent_sha256']=sha(p)
        a=attempt(p,d);a['attempted_at']=p['created_at']
        with o.a.db:append_record(o.a.store,a)
        if mode=='older_database':old.backup(o.a.db)
    finally:old.close()
    observed=order(client_order_id=p['client_order_id'],qty='1',filled_qty='1',filled_avg_price='150',status='filled',
                   submitted_at='2023-11-24T14:30:00.200000Z')
    original=reader.body
    def body(operation):
        if operation=='POSITIONS':return [position()]
        if operation=='ORDERS':return [observed]
        value=original(operation)
        if operation=='ACCOUNT':value=dict(value,cash='99850')
        return value
    monkeypatch.setattr(reader,'body',body)
    o.clock.utc+=1;o.clock.mono+=1
    _,read_pub,new_packet=fresh(publication)
    o.a.account_context(subject='a'*64,packet_id=new_packet['packet_id'])
    fill=dict(activity_type='FILL',id='20231124::owned-1',order_id=observed['id'],symbol='AAPL',side='buy',
              qty='1',cum_qty='1',leaves_qty='0',price='150',transaction_time='2023-11-24T14:30:00.300000Z',type='fill')
    if mode=='outside_interval':
        from datetime import datetime,timezone
        fill['transaction_time']=datetime.fromtimestamp(o.clock.utc+60,timezone.utc).isoformat()
    o.clock.utc+=1;o.clock.mono+=1
    with pages([canonical([] if mode=='missing_fill' else [fill])]) as (port,seen):
        o.activity_port=port;s=pub_start((o,new_packet,pub,module,remote));finish(o,s)
        for _ in range(12):pub.tick()
        saved=o.a._activities._read(s['activity_id']);fixture=(o,new_packet,saved,seen)
        if mode=='outside_interval':
            assert 'ACTIVITY_TIME_OUTSIDE_QUERY_INTERVAL' in saved['summary']['deficiencies']
        if mode in {'missing_fill','outside_interval'}:
            with pytest.raises(RuntimeRefused):context(fixture)
        else:
            c=context(fixture);value=c.diagnostic()
            assert value['order_count']==value['fill_count']==value['position_count']==1
            assert json.loads(c._calculation)['expected_cash']=='99850'
            assert value['transport_authorized'] is False
            if mode=='older_database':
                proof=c._prepare_proof();prior=sqlite3.connect(':memory:');o.a.db.backup(prior)
                try:
                    cancel,decision=records(o.e.lease,operation='CANCEL_ORDER')
                    cancel['request']['parameters']['order_id']=observed['id']
                    cancel['request']['target']='/v2/orders/'+observed['id']
                    cancel['request_sha256']=sha(cancel['request']);decision['intent_sha256']=sha(cancel)
                    with o.a.db:append_record(o.a.store,attempt(cancel,decision))
                    prior.backup(o.a.db)
                finally:prior.close()
                with pytest.raises(RuntimeRefused):proof._verify()
                assert c._closed


def test_published_unsupported_activity_is_not_economic_coverage(activity_publication):
    o,packet,pub,_,_=activity_publication
    with pages([canonical([dict(id='activity::fee',activity_type='DIV',amount='1')])]) as (port,seen):
        o.activity_port=port;s=pub_start(activity_publication);finish(o,s)
        for _ in range(12):pub.tick()
        saved=o.a._activities._read(s['activity_id'])
        assert saved['state']=='PUBLISHED'
        with pytest.raises(RuntimeRefused):context((o,packet,saved,seen))


def test_generated_diagnostic_runs_secret_reflection_check(published_activity,monkeypatch):
    from compertum.runtime import paper_reconciliation_context as module
    def reject(raw,secrets):
        assert json.loads(raw)['record_type']=='PaperReconciliationDiagnostic'
        assert KEY in secrets and SECRET in secrets
        raise RuntimeRefused('SIMULATED_DIAGNOSTIC_SECRET_REFLECTION')
    monkeypatch.setattr(module,'_reject_reflections',reject,raising=False)
    with pytest.raises(RuntimeRefused):context(published_activity)


def test_activity_only_proof_failure_preserves_borrowed_account(published_activity):
    o,_,saved,_=published_activity;c=context(published_activity);proof=c._prepare_proof()
    (o.manager.root/saved['manifest']['path']).write_bytes(b'changed activity only')
    with pytest.raises(RuntimeRefused):proof._verify()
    assert c._closed and not c._context._closed
    assert c._context.diagnostic()['confirmation_status']=='CONFIRMED_CURRENT_CONTEXT'


def test_actual_account_failure_still_revokes_borrowed_account(published_activity):
    o,_,_,_=published_activity;c=context(published_activity);proof=c._prepare_proof()
    with o.a.db:o.a.db.execute("UPDATE state SET value='{}' WHERE key='paper_opening:fixture'")
    with pytest.raises(RuntimeRefused):proof._verify()
    assert c._closed and c._context._closed
