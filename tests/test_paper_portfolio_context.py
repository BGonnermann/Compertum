"""Native stores/DPAPI; invented replies/origin, simulated clocks and reserves."""
import json,pickle
from decimal import localcontext
import pytest
from compertum.data.encoding import canonical
from compertum.runtime.errors import RuntimeRefused
from test_execution_health import pair,connect
from test_paper_read_owner import owner
from test_paper_read_publication import publication,launch
from test_paper_account_binding import invented_paper_origin,propose,confirm,call
from test_paper_presence import account,advance,acknowledge
from test_paper_account_context import context
from test_paper_read_preparation import ACCOUNT,KEY,SECRET


def portfolio(c):
    from compertum.runtime.paper_portfolio_context import _portfolio_context
    return _portfolio_context(c)


def fresh(account):
    o,pub,_=account;p=launch((o,pub,None))
    for _ in range(10):pub.tick()
    confirm(pub,p,call(pub,p,'account_propose'))
    return o,pub,p


def journal_fixture(account,kind):
    from compertum.fake_execution_journal import FakeIntentJournal
    from test_fake_execution_journal import checked_records
    o,_,_=account;j=FakeIntentJournal(o.a.store)
    if kind=='empty':
        with o.a.db:o.a.db.execute('DELETE FROM fake_execution_session')
    elif kind in ('checked','unknown'):
        intent,decision=checked_records(o.a.lease);j.record_checked(intent,decision)
        if kind=='unknown':
            with o.a.db:o.a.db.execute("UPDATE fake_intents SET body='{}',decision='{}'")
    return fresh(account)


def test_foreign_context_is_rejected_without_methods():
    class Foreign:
        def _prepare_proof(self):raise AssertionError('Unqualified callback')
    with pytest.raises(RuntimeRefused):portfolio(Foreign())


def test_clean_observation_is_private_read_only_and_never_authority(account):
    from compertum.runtime.service_budget import queue_for
    o,pub,p=account;c=context(account)
    before=(o.a.db.total_changes,pub.db.total_changes,len(o.calls),queue_for(o.e.lease).status())
    r=portfolio(c);v=r.diagnostic()
    assert r._context is c and o.a._account_context is c
    assert v['observation_status']=='CLEAN_ZERO_OPENING_OBSERVED'
    assert v['history_classification']=='VERIFIED_EMPTY_LOCAL_HISTORY'
    assert v['cash_observation']=='MATCHES_IMMUTABLE_OPENING'
    assert v['status']=='BLOCKED' and v['actual_flat'] is None
    assert v['financial_accepted'] is v['transport_authorized'] is False
    assert {'OWNERSHIP_UNVERIFIED','ECONOMIC_COVERAGE_UNVERIFIED','FEE_ACTION_EVIDENCE_UNVERIFIED',
            'RISK_UNVERIFIED','DURABLE_CONSUMPTION_UNVERIFIED'}<=set(v['unverified_requirements'])
    raw=canonical(v);assert len(raw)<=16384
    assert all(s.encode() not in raw for s in (ACCOUNT,KEY,SECRET,'100000','body_utf8'))
    assert before==(o.a.db.total_changes,pub.db.total_changes,len(o.calls),queue_for(o.e.lease).status())
    assert o.a.db.execute("SELECT name FROM sqlite_master WHERE name='fake_intents'").fetchone() is None
    with pytest.raises(RuntimeRefused):pickle.dumps(r)
    with pytest.raises(RuntimeRefused):type(r)()
    with pytest.raises(RuntimeRefused):pub.handle('a'*64,dict(operation='portfolio_context',packet_id=p['packet_id']))
    r.close();assert not c._closed and c.diagnostic()['packet_id']==p['packet_id']
    with pytest.raises(RuntimeRefused):r.diagnostic()


@pytest.mark.parametrize('kind',['empty','session','checked','unknown'])
def test_complete_local_history_is_observed_without_ownership_claim(account,kind):
    o,_,_=account;first=o.a.db.execute("SELECT value FROM state WHERE key='paper_opening:fixture'").fetchone()[0]
    fixture=journal_fixture(account,kind);c=context(fixture);before=o.a.db.total_changes
    v=portfolio(c).diagnostic()
    assert v['history_classification']==('VERIFIED_EMPTY_LOCAL_HISTORY' if kind=='empty' else 'NONEMPTY_LOCAL_HISTORY')
    assert v['observation_status']==('CLEAN_ZERO_OPENING_OBSERVED' if kind=='empty' else 'BLOCKED')
    assert v['journal_counts']['fake_execution_session']==(0 if kind=='empty' else 1)
    assert v['record_classes']['unknown']==(1 if kind=='unknown' else 0)
    assert v['record_classes']['fake']==(1 if kind=='checked' else 0)
    assert not v['transport_authorized'] and v['actual_flat'] is None
    assert before==o.a.db.total_changes
    assert first==o.a.db.execute("SELECT value FROM state WHERE key='paper_opening:fixture'").fetchone()[0]


def test_schema_created_after_capture_does_not_refresh_borrowed_context(account):
    from compertum.fake_execution_journal import FakeIntentJournal
    o,_,_=account;c=context(account)
    FakeIntentJournal(o.a.store)
    with pytest.raises(RuntimeRefused):portfolio(c)
    assert c._closed


@pytest.mark.parametrize('fault',['row','session','schema','head'])
def test_late_complete_journal_changes_refuse_and_never_revive(account,fault):
    o,_,_=account;fixture=journal_fixture(account,'checked');r=portfolio(context(fixture));p=r._prepare_proof()
    head=o.a.db.execute("SELECT value FROM state WHERE key='fake_attempt_guard_head'").fetchone()[0]
    with o.a.db:
        if fault=='row':o.a.db.execute("UPDATE fake_intents SET body='{}',decision='{}'")
        elif fault=='session':o.a.db.execute("UPDATE fake_execution_session SET state='INVENTED_CHANGE'")
        elif fault=='schema':o.a.db.execute('CREATE INDEX invented_reader_index ON fake_intents(state)')
        else:o.a.db.execute("UPDATE state SET value='{}' WHERE key='fake_attempt_guard_head'")
    if fault!='head':assert head==o.a.db.execute("SELECT value FROM state WHERE key='fake_attempt_guard_head'").fetchone()[0]
    with pytest.raises(RuntimeRefused):p._verify()
    assert r._closed
    with pytest.raises(RuntimeRefused):r.diagnostic()


def test_decorates_original_single_use_proof_and_groups_with_presence(account,monkeypatch):
    from compertum.runtime.paper_final_proof import _verify_proofs
    o,_,_=account;_,presence=acknowledge(account);c=context(account);r=portfolio(c)
    original=type(c)._prepare_proof;captured=[]
    def prepared(self):
        p=original(self);captured.append((p,p._owner,p._db,p._lease,p._health,p._peer));return p
    monkeypatch.setattr(type(c),'_prepare_proof',prepared)
    p=r._prepare_proof();row=captured[-1]
    assert p is row[0] and (p._owner,p._db,p._lease,p._health,p._peer)==row[1:] and not p._used
    with pytest.raises(RuntimeRefused,match='DUPLICATE'):_verify_proofs(p,p)
    assert not p._used
    pp=o.a._presence._prepare_proof(subject='a'*64,presence_id=presence['presence_id'])
    assert _verify_proofs(p,pp)[0]['status']=='BLOCKED'
    assert p._used
    with pytest.raises(RuntimeRefused,match='CONSUMED'):p._verify()


@pytest.mark.parametrize('point',['before','after','replaced_db'])
def test_pending_captured_transaction_stays_open_and_proof_unused(account,point):
    o,_,_=account;c=context(account);r=portfolio(c);db=o.a.db
    p=None if point=='before' else r._prepare_proof()
    db.execute('BEGIN');db.execute("INSERT INTO state VALUES('invented_pending_portfolio','true')")
    if point=='replaced_db':o.a.db=object()
    try:
        with pytest.raises(RuntimeRefused,match='TRANSACTION'):
            if p is None:r._prepare_proof()
            else:p._verify()
        assert db.in_transaction and db.execute("SELECT value FROM state WHERE key='invented_pending_portfolio'").fetchone()==('true',)
        if p is not None:assert not p._used
        assert not c._closed and not r._closed
    finally:o.a.db=db;db.rollback()


@pytest.mark.parametrize('seconds',[29.999,30,30.001])
def test_original_age_is_preserved(account,seconds):
    o,_,_=account;r=portfolio(context(account));p=r._prepare_proof();advance(o,seconds)
    if seconds<=30:assert p._verify()['status']=='BLOCKED'
    else:
        with pytest.raises(RuntimeRefused):p._verify()
        assert r._closed


@pytest.mark.parametrize('fault',['closed','replacement','health','artifact'])
def test_original_lifetime_and_artifact_failures_are_permanent(account,fault):
    o,pub,packet=account;c=context(account);r=portfolio(c);p=r._prepare_proof();restore=lambda:None
    if fault=='closed':c.close()
    elif fault=='replacement':context(account)
    elif fault=='health':o.e.halt('INVENTED_PORTFOLIO_HALT')
    else:
        path=o.manager.root/pub._route(packet['packet_id'])['publication']['manifest']['path']
        raw=path.read_bytes();path.write_bytes(b'invented late portfolio artifact');restore=lambda:path.write_bytes(raw)
    try:
        with pytest.raises(RuntimeRefused):p._verify()
        assert r._closed
    finally:restore()
    with pytest.raises(RuntimeRefused):r.diagnostic()


def test_finish_has_no_durable_reads_or_callbacks_after_original_clocks(account,monkeypatch):
    import compertum.runtime.paper_portfolio_context as module
    import compertum.runtime.paper_account_context as ac
    c=context(account);r=portfolio(c);p=r._prepare_proof()
    def forbidden(*args,**kwargs):raise AssertionError('Callback after preparation')
    for m in (module,ac):
        for name in ('original_opening','load_paper_slot','open_paper_credentials','_reject_reflections'):
            monkeypatch.setattr(m,name,forbidden)
    finish=p._finish;seen=[];read=module._journal_snapshot
    def checked_read(*args):
        assert not seen,'Durable read after final clocks'
        return read(*args)
    monkeypatch.setattr(module,'_journal_snapshot',checked_read)
    def last():finish();seen.append(True)
    p._finish=last
    p._verify();assert seen==[True]


def test_expiry_during_last_journal_read_refuses(account,monkeypatch):
    import compertum.runtime.paper_portfolio_context as module
    o,_,_=account;r=portfolio(context(account));p=r._prepare_proof();read=module._journal_snapshot;fired=[]
    def delayed(*args):
        value=read(*args);advance(o,31);fired.append(True);return value
    monkeypatch.setattr(module,'_journal_snapshot',delayed)
    with pytest.raises(RuntimeRefused):p._verify()
    assert fired and r._closed


@pytest.mark.parametrize('damage',['event_body','extra_column','partial_schema'])
def test_unsupported_or_oversized_journal_refuses_without_writes(account,damage):
    o,_,_=account;fixture=journal_fixture(account,'empty');c=context(fixture)
    with o.a.db:
        if damage=='event_body':o.a.db.execute("INSERT INTO fake_intent_events(account,intent_id,kind,body) VALUES('fixture','invented','INVENTED',?)",('x'*65537,))
        elif damage=='extra_column':o.a.db.execute('ALTER TABLE fake_execution_session ADD COLUMN unexpected TEXT')
        else:o.a.db.execute('DROP TABLE fake_incidents')
    before=o.a.db.total_changes
    with pytest.raises(RuntimeRefused):portfolio(c)
    assert o.a.db.total_changes==before


def test_inert_paper_preparation_remains_unowned_and_is_fully_pinned(account,monkeypatch):
    from compertum.paper_intent_journal import PaperIntentJournal
    from compertum.runtime.identity import resolve_project
    from test_paper_intent_journal import prepared
    o,_,_=account
    monkeypatch.setattr('compertum.paper_intent_journal.execution_durable',lambda *args:None)
    j=PaperIntentJournal(o.a.store,o.a.reserve)
    prepared((resolve_project(o.a.store.root),o.a.lease,o.a.store,j,o.protected))
    fixture=fresh(account);r=portfolio(context(fixture));v=r.diagnostic()
    assert v['record_classes']['preparation']==1 and v['history_classification']=='NONEMPTY_LOCAL_HISTORY'
    p=r._prepare_proof();head=o.a.db.execute("SELECT value FROM state WHERE key='fake_attempt_guard_head'").fetchone()[0]
    with o.a.db:o.a.db.execute("UPDATE fake_intents SET state='PAPER_SKIPPED_RESTART'")
    assert head==o.a.db.execute("SELECT value FROM state WHERE key='fake_attempt_guard_head'").fetchone()[0]
    with pytest.raises(RuntimeRefused):p._verify()


@pytest.mark.parametrize('delta',['0.01','-0.01','0.02','-0.02'])
def test_cash_uses_original_opening_and_fixed_decimal_context(account,monkeypatch,delta):
    import test_paper_read_owner as fixture_module
    from decimal import Decimal
    o,_,_=account;body=fixture_module.body
    def changed(operation):
        value=body(operation)
        if operation=='ACCOUNT':value=dict(value,cash=str(Decimal(value['cash'])+Decimal(delta)))
        return value
    monkeypatch.setattr(fixture_module,'body',changed)
    later=fresh(account);c=context(later)
    with localcontext() as arithmetic:
        arithmetic.prec=2;v=portfolio(c).diagnostic()
    matches=delta in ('0.01','-0.01')
    assert v['cash_observation']==('MATCHES_IMMUTABLE_OPENING' if matches else 'UNEXPLAINED_CASH_CHANGE')
    assert v['observation_status']==('CLEAN_ZERO_OPENING_OBSERVED' if matches else 'BLOCKED')
    assert v['status']=='BLOCKED' and v['actual_flat'] is None
