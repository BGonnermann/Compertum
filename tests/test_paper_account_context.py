"""Native stores/DPAPI; account origin, reserve capacity and clocks are simulated."""
from uuid import uuid4
import json,pickle
import pytest
from compertum.data.encoding import canonical
from compertum.runtime.errors import RuntimeRefused
from compertum.runtime.service_budget import queue_for
from test_execution_health import pair,connect
from test_paper_read_owner import owner
from test_paper_read_publication import publication,launch
from test_paper_account_binding import invented_paper_origin,propose,confirm,call
from test_paper_presence import account,advance
from test_paper_read_preparation import ACCOUNT,KEY,SECRET


def context(fixture,**changes):
    o,_,p=fixture;args=dict(subject='a'*64,packet_id=p['packet_id']);args.update(changes)
    return o.a.account_context(**args)


def test_confirmed_account_context_needs_no_market_and_has_no_side_effects(account):
    o,pub,p=account;assert o.a._market is None
    before=(o.a.db.total_changes,pub.db.total_changes,len(o.calls),queue_for(o.e.lease).status())
    c=context(account);v=c.diagnostic()
    assert v['record_type']=='PaperAccountInputDiagnostic' and v['scope']=='CURRENT_ACCOUNT_OBSERVATIONS_ONLY'
    assert v['packet_id']==p['packet_id'] and v['confirmation_status']=='CONFIRMED_CURRENT_CONTEXT'
    assert v['opening_status']=='CURRENT_CLEAN_OPENING'
    assert {'OWNERSHIP_UNVERIFIED','ECONOMIC_RECONCILIATION_UNVERIFIED','SUPERVISION_UNVERIFIED',
            'EXACT_PLAN_GRANT_REQUIRED','TARGET_RECONCILIATION_UNVERIFIED'}<=set(v['unverified_requirements'])
    assert not {'QUOTE_EVIDENCE_UNVERIFIED','FEED_ENTITLEMENT_UNVERIFIED','LIQUIDITY_UNVERIFIED',
                'ELIGIBILITY_UNVERIFIED','ACCOUNT_CONFIRMATION_UNVERIFIED'}&set(v['unverified_requirements'])
    assert v['status']=='BLOCKED' and v['actual_flat'] is None
    assert v['financial_accepted'] is v['transport_authorized'] is v['research_eligible'] is False
    raw=canonical(v);assert len(raw)<=16384 and all(s.encode() not in raw for s in (ACCOUNT,KEY,SECRET,'body_utf8'))
    assert before==(o.a.db.total_changes,pub.db.total_changes,len(o.calls),queue_for(o.e.lease).status())
    assert o.a._market is None
    c.close();assert o.a.preflight(p['packet_id']).diagnostic()['packet_id']==p['packet_id']
    with pytest.raises(RuntimeRefused):c.diagnostic()


@pytest.mark.parametrize('point',['result_scan','last_preflight_scan'])
def test_later_packet_rechecks_original_opening_artifact_after_final_scan(account,monkeypatch,point):
    import compertum.runtime.paper_account_context as module
    import compertum.runtime.paper_preflight as preflight
    o,pub,first=account;manifest=pub._route(first['packet_id'])['publication']['manifest']
    path=o.manager.root/manifest['path'];original_bytes=path.read_bytes()
    later=launch((o,pub,None))
    for _ in range(10):pub.tick()
    proposal=call(pub,later,'account_propose');confirm(pub,later,proposal)
    c=context((o,pub,later));assert c.diagnostic()['opening_status']=='CURRENT_CLEAN_OPENING'
    marked=[False];fired=[False];scan=module._reject_reflections;last=preflight._reject_reflections
    def corrupt():
        if not fired[0]:fired[0]=True;path.write_bytes(b'late invented first-opening corruption')
    def result_scan(*args):
        scan(*args);marked[0]=True
        if point=='result_scan':corrupt()
    def last_scan(*args):
        last(*args)
        if marked[0] and point=='last_preflight_scan':corrupt()
    monkeypatch.setattr(module,'_reject_reflections',result_scan);monkeypatch.setattr(preflight,'_reject_reflections',last_scan)
    with pytest.raises(RuntimeRefused):c.diagnostic()
    assert fired[0] and c._closed
    path.write_bytes(original_bytes)
    with pytest.raises(RuntimeRefused):c.diagnostic()


@pytest.mark.parametrize('fault',['bad_mirror','partial_schema'])
def test_initial_unconfirmed_context_refuses_corrupt_original_history(publication,fault):
    o,pub,_=publication;p=launch(publication)
    for _ in range(10):pub.tick()
    with o.a.db:
        if fault=='bad_mirror':o.a.db.execute("UPDATE state SET value='{}' WHERE key='fake_attempt_guard_head'")
        else:o.a.db.execute('CREATE TABLE fake_intents(body TEXT,decision TEXT)')
    before=o.a.db.total_changes
    with pytest.raises(RuntimeRefused):context((o,pub,p))
    assert o.a.db.total_changes==before


@pytest.mark.parametrize('nonempty',[False,True])
def test_verified_history_is_read_without_repair_or_empty_history_requirement(publication,nonempty):
    from compertum.fake_execution_journal import FakeIntentJournal
    from compertum.runtime.paper_account_binding import _history
    from test_fake_execution_journal import checked_records
    o,pub,_=publication;journal=FakeIntentJournal(o.a.store)
    if nonempty:
        intent,decision=checked_records(o.a.lease);journal.record_checked(intent,decision)
    history=_history(o.a);assert history['status']=='VERIFIED_HISTORY' and history['empty'] is not nonempty
    p=launch(publication)
    for _ in range(10):pub.tick()
    before=o.a.db.total_changes;value=context((o,pub,p)).diagnostic()
    assert ('NONEMPTY_LOCAL_HISTORY_REQUIRES_RECONCILIATION' in value['observed_deficiencies']) is nonempty
    assert value['status']=='BLOCKED' and not value['transport_authorized'] and o.a.db.total_changes==before


@pytest.mark.parametrize('field',['subject','packet_id'])
def test_account_context_rejects_identity_substitution(account,field):
    with pytest.raises(RuntimeRefused):context(account,**{field:'b'*64 if field=='subject' else str(uuid4())})


@pytest.mark.parametrize('proposed',[False,True])
def test_unconfirmed_observation_preserves_missing_confirmation(publication,proposed):
    o,pub,_=publication
    if proposed:o,pub,p,_=propose(publication)
    else:
        p=launch(publication)
        for _ in range(10):pub.tick()
    before=o.a.db.total_changes;v=context((o,pub,p)).diagnostic()
    assert v['confirmation_status']=='UNCONFIRMED' and 'ACCOUNT_CONFIRMATION_UNVERIFIED' in v['unverified_requirements']
    assert v['account_transport_provenance']!='PAPER_TLS' and not v['transport_authorized']
    assert o.a.db.total_changes==before


def test_account_context_is_private_and_cannot_be_injected_through_public_routing(account):
    o,pub,p=account;c=context(account)
    assert all(s not in repr(c) for s in (ACCOUNT,KEY,SECRET))
    with pytest.raises(RuntimeRefused):pickle.dumps(c)
    with pytest.raises(RuntimeRefused):type(c)()
    with pytest.raises(RuntimeRefused):pub.handle('a'*64,dict(operation='account_context',packet_id=p['packet_id']))


@pytest.mark.parametrize('seconds',[29.999,30,30.001])
def test_original_account_age_is_not_renewed(account,seconds):
    o,_,_=account;c=context(account);first=c.diagnostic();advance(o,seconds)
    if seconds<=30:
        v=c.diagnostic();assert v['checked_at']!=first['checked_at']
        assert v['account_manifest_sha256']==first['account_manifest_sha256']
    else:
        with pytest.raises(RuntimeRefused,match='STALE'):c.diagnostic()


@pytest.mark.parametrize('fault',['closed','replacement','preflight','proposal','owner','health','reverse','drift'])
def test_account_context_lifetime_fault_never_revives(account,fault):
    o,_,_=account;c=context(account);utc,mono=o.clock.utc,o.clock.mono
    if fault=='closed':c.close()
    elif fault=='replacement':context(account)
    elif fault=='preflight':o.a._preflight.close()
    elif fault=='proposal':o.a._account_proposal.close()
    elif fault=='owner':o.a.close();o.a=o.module.PaperReadOwner(o.a.store,o.a.reserve,o.e)
    elif fault=='health':o.e.halt('ACCOUNT_CONTEXT_FIXTURE_HALT')
    elif fault=='reverse':o.clock.utc-=1;o.clock.mono-=1
    else:o.clock.mono+=6
    with pytest.raises(RuntimeRefused):c.diagnostic()
    o.clock.utc,o.clock.mono=utc,mono
    with pytest.raises(RuntimeRefused):c.diagnostic()


@pytest.mark.parametrize('fault',['confirmation','alias','opening','history','packet','manifest','artifact'])
def test_account_context_rejects_changed_originals_and_never_revives(account,fault):
    o,pub,p=account;c=context(account);restore=None
    if fault in ('confirmation','alias','opening','history'):
        key={'confirmation':'paper_account_proposal:'+p['packet_id'],'alias':'paper_account_alias:fixture',
             'opening':'paper_opening:fixture','history':'fake_attempt_guard_head'}[fault]
        raw=o.a.db.execute('SELECT value FROM state WHERE key=?',(key,)).fetchone()[0]
        with o.a.db:o.a.db.execute("UPDATE state SET value='{}' WHERE key=?",(key,))
        restore=lambda:o.a.db.execute('UPDATE state SET value=? WHERE key=?',(raw,key))
    elif fault=='packet':
        raw=o.a.db.execute('SELECT body FROM paper_read_packets WHERE packet_id=?',(p['packet_id'],)).fetchone()[0]
        with o.a.db:o.a.db.execute("UPDATE paper_read_packets SET body='{}' WHERE packet_id=?",(p['packet_id'],))
        restore=lambda:o.a.db.execute('UPDATE paper_read_packets SET body=? WHERE packet_id=?',(raw,p['packet_id']))
    else:
        manifest=pub._route(p['packet_id'])['publication']['manifest']
        if fault=='artifact':
            path=o.manager.root/manifest['path'];raw=path.read_bytes();path.write_bytes(b'invented corrupt ciphertext')
            restore=lambda:path.write_bytes(raw)
        else:
            db=o.manager.store.conn;raw=db.execute('SELECT manifest FROM reservations WHERE path=?',(manifest['path'],)).fetchone()[0]
            with db:db.execute("UPDATE reservations SET manifest='{}' WHERE path=?",(manifest['path'],))
            restore=lambda:db.execute('UPDATE reservations SET manifest=? WHERE path=?',(raw,manifest['path']))
    with pytest.raises(RuntimeRefused):c.diagnostic()
    # Restore only an invented fault to demonstrate nonrevival; never resume a runtime.
    with o.a.db,o.manager.store.conn:restore()
    with pytest.raises(RuntimeRefused):c.diagnostic()


@pytest.mark.parametrize('missing',['confirmation','alias','opening'])
def test_account_context_distinguishes_absent_originals_from_corruption(account,missing):
    o,_,p=account;c=context(account)
    key={'confirmation':'paper_account_proposal:'+p['packet_id'],'alias':'paper_account_alias:fixture','opening':'paper_opening:fixture'}[missing]
    with o.a.db:o.a.db.execute('DELETE FROM state WHERE key=?',(key,))
    before=o.a.db.total_changes
    with pytest.raises(RuntimeRefused):c.diagnostic()
    if missing=='opening':
        v=context(account).diagnostic();assert v['opening_status']=='UNRECORDED'
        assert 'PAPER_OPENING_UNRECORDED' in v['observed_deficiencies']
    else:
        with pytest.raises(RuntimeRefused):context(account)
    assert o.a.db.total_changes==before


@pytest.mark.parametrize('kind',['positions','orders','negative_cash','market_closed','strategy_halted'])
def test_account_observations_do_not_require_clean_opening_or_strategy_window(publication,invented_paper_origin,monkeypatch,kind):
    import test_paper_read_owner as fixture
    from test_paper_portfolio import position,order
    original=fixture.body;o,pub,_=publication
    if kind=='market_closed':o.clock.utc-=60
    def changed(op):
        value=original(op)
        if kind=='positions' and op=='POSITIONS':return [position()]
        if kind=='orders' and op=='ORDERS':return [order(client_order_id='foreign-order')]
        if kind=='negative_cash' and op=='ACCOUNT':return dict(value,cash='-1')
        if kind=='market_closed' and op=='CLOCK':return dict(value,timestamp='2023-11-24T14:29:00Z',is_open=False,next_open='2023-11-24T14:30:00Z')
        return value
    monkeypatch.setattr(fixture,'body',changed)
    if kind=='strategy_halted':
        from compertum.runtime.execution_health import disarm_execution
        disarm_execution(o.a.store,'ACCOUNT_CONTEXT_STRATEGY_FIXTURE')
    o,pub,p,r=propose(publication);confirm(pub,p,r);v=context((o,pub,p)).diagnostic()
    assert v['confirmation_status']=='CONFIRMED_CURRENT_CONTEXT' and v['status']=='BLOCKED'
    assert not {'MARKET_NOT_OPEN','QUOTE_EVIDENCE_UNVERIFIED','NEGATIVE_ACCOUNT_CASH'}&set(v['unverified_requirements'])
    if kind=='negative_cash':assert 'NEGATIVE_ACCOUNT_CASH' in v['observed_deficiencies']
    if kind=='market_closed':assert 'MARKET_NOT_OPEN' in v['observed_deficiencies']
    assert o.a._market is None and not v['transport_authorized']


@pytest.mark.parametrize('point',['result_scan','last_preflight_scan'])
@pytest.mark.parametrize('fault',['expiry','health','health_persisted','preflight_closed','proposal_closed','context_closed','context_replaced','alias','confirmation','artifact','credentials'])
def test_late_callback_cannot_return_invalid_account_context(account,monkeypatch,point,fault):
    from types import SimpleNamespace
    import compertum.runtime.paper_account_context as module
    import compertum.runtime.paper_preflight as preflight
    o,_,p=account;c=context(account);marked=[False];fired=[False]
    if fault=='health_persisted':
        from compertum.runtime.execution_health import disarm_execution
        o.e.on_halt=lambda reason:disarm_execution(o.a.store,reason)
    result_scan=module._reject_reflections;preflight_scan=preflight._reject_reflections
    def mutate():
        if fired[0]:return
        fired[0]=True
        if fault=='expiry':o.clock.utc+=31;o.clock.mono+=31
        elif fault in ('health','health_persisted'):o.e.halt('LATE_ACCOUNT_CONTEXT_HEALTH')
        elif fault=='preflight_closed':o.a._preflight.close()
        elif fault=='proposal_closed':o.a._account_proposal.close()
        elif fault=='context_closed':c.close()
        elif fault=='context_replaced':o.a._account_context=None
        elif fault=='credentials':monkeypatch.setattr(module,'load_paper_slot',lambda *a:SimpleNamespace(ciphertext=b'changed ciphertext'))
        elif fault=='artifact':
            manifest=account[1]._route(p['packet_id'])['publication']['manifest']
            (o.manager.root/manifest['path']).write_bytes(b'late invented corrupt ciphertext')
        else:
            key='paper_account_alias:fixture' if fault=='alias' else 'paper_account_proposal:'+p['packet_id']
            with o.a.db:o.a.db.execute("UPDATE state SET value='{}' WHERE key=?",(key,))
    def scan(*args):
        result_scan(*args);marked[0]=True
        if point=='result_scan':mutate()
    def last_scan(*args):
        preflight_scan(*args)
        if marked[0] and point=='last_preflight_scan':mutate()
    monkeypatch.setattr(module,'_reject_reflections',scan);monkeypatch.setattr(preflight,'_reject_reflections',last_scan)
    with pytest.raises(RuntimeRefused):c.diagnostic()
    assert fired[0] and c._closed
    if fault=='health_persisted':assert json.loads(o.a.db.execute("SELECT value FROM state WHERE key='admission'").fetchone()[0])=='HALTED'
    with pytest.raises(RuntimeRefused):c.diagnostic()
