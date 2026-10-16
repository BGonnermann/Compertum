"""Retained native attempts survive an older, empty fixture database."""
import sqlite3
import pytest
from compertum.data.encoding import canonical
from compertum.runtime.errors import RuntimeRefused
from compertum.fake_attempt_guard import append_record
from compertum.runtime.paper_portfolio_context import _journal_snapshot
from test_native_attempt_records import records,attempt
from test_paper_portfolio_context import (
    pair,connect,owner,publication,launch,invented_paper_origin,account,
    context,portfolio,fresh,journal_fixture,
)


def retained_after_restore(account):
    o,_,_=account
    fixture=journal_fixture(account,'empty')
    old=sqlite3.connect(':memory:')
    try:
        o.a.db.backup(old)
        p,d=records(o.a.lease)
        with o.a.db:append_record(o.a.store,attempt(p,d))
        old.backup(o.a.db)
    finally:old.close()
    return o,p,d,fresh(fixture)


def test_restored_empty_database_reports_retained_attempt_without_authority(account):
    o,p,d,fixture=retained_after_restore(account)
    opening=o.a.db.execute("SELECT value FROM state WHERE key='paper_opening:fixture'").fetchone()[0]
    before=o.a.db.total_changes
    value=portfolio(context(fixture)).diagnostic()
    assert value['history_classification']=='NONEMPTY_LOCAL_HISTORY'
    assert value['observation_status']==value['status']=='BLOCKED'
    assert value['retained_attempts']==1
    assert not any(value['journal_counts'].values())
    assert value['financial_accepted'] is value['transport_authorized'] is False
    assert value['actual_flat'] is None
    assert o.a.db.total_changes==before
    assert o.a.db.execute("SELECT value FROM state WHERE key='paper_opening:fixture'").fetchone()[0]==opening
    raw=canonical(value)
    assert all(s.encode() not in raw for s in (p['intent_id'],p['client_order_id'],p['request_sha256'],d['intent_sha256']))


def test_external_attempt_changes_digest_with_identical_database(account):
    o,_,_=account;journal_fixture(account,'empty')
    before=_journal_snapshot(o.a)
    old=sqlite3.connect(':memory:')
    try:
        o.a.db.backup(old);p,d=records(o.a.lease)
        with o.a.db:append_record(o.a.store,attempt(p,d))
        old.backup(o.a.db)
    finally:old.close()
    after=_journal_snapshot(o.a)
    assert before['counts']==after['counts'] and before['retained_sequence']==after['retained_sequence']==0
    assert before['sha256']!=after['sha256']
    assert before['retained_attempts']==0 and after['retained_attempts']==1


def test_external_change_after_proof_capture_permanently_refuses(account):
    o,_,_=account;r=portfolio(context(journal_fixture(account,'empty')));proof=r._prepare_proof()
    old=sqlite3.connect(':memory:')
    try:
        o.a.db.backup(old);p,d=records(o.a.lease)
        with o.a.db:append_record(o.a.store,attempt(p,d))
        old.backup(o.a.db)
    finally:old.close()
    with pytest.raises(RuntimeRefused):proof._verify()
    assert r._closed and r._context._closed
    with pytest.raises(RuntimeRefused):r.diagnostic()


@pytest.mark.parametrize('damage',['missing','corrupt'])
def test_unverified_external_history_refuses_without_writes(account,damage):
    o,_,_,_=retained_after_restore(account)
    folder=o.a.store.root/'state/fake-execution-attempts'
    path=folder/'00000001.json'
    if damage=='missing':path.rename(folder/'retained-damaged-entry.json')
    else:path.write_bytes(b'invented corrupt fixture record')
    before=o.a.db.total_changes
    with pytest.raises(RuntimeRefused):_journal_snapshot(o.a)
    assert o.a.db.total_changes==before


@pytest.mark.parametrize('schema',[False,True])
def test_genuine_empty_history_remains_read_only(account,schema):
    o,_,_=account;fixture=journal_fixture(account,'empty') if schema else account
    before=o.a.db.total_changes;v=portfolio(context(fixture)).diagnostic()
    assert v['history_classification']=='VERIFIED_EMPTY_LOCAL_HISTORY'
    assert v['observation_status']=='CLEAN_ZERO_OPENING_OBSERVED' and v['retained_attempts']==0
    assert o.a.db.total_changes==before
