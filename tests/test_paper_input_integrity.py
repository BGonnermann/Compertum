"""Native stores/DPAPI; simulated account origin, reserve capacity and clocks."""
import pytest
from compertum.runtime.errors import RuntimeRefused
from test_paper_input_context import inputs,confirmed,context
from test_paper_market_owner_fresh import history,completed,pair,owner,native_market,publication
from test_paper_account_binding import invented_paper_origin,call,confirm
from test_paper_read_publication import launch


@pytest.mark.parametrize('point',['result_scan','last_preflight_scan'])
def test_later_combined_packet_rechecks_first_opening_after_scans(confirmed,monkeypatch,point):
    import compertum.runtime.paper_input_context as module
    import compertum.runtime.paper_preflight as preflight
    o,first,fresh,capture,pub=confirmed
    manifest=pub._route(first['packet_id'])['publication']['manifest']
    path=o.manager.root/manifest['path'];original_bytes=path.read_bytes()
    later=launch((o,pub,None))
    for _ in range(10):pub.tick()
    proposal=call(pub,later,'account_propose');confirm(pub,later,proposal)
    ctx=context((o,later,fresh,capture,pub))
    assert ctx.diagnostic()['opening_status']=='CURRENT_CLEAN_OPENING'
    marked=[False];fired=[False];scan=module._reject_reflections;last=preflight._reject_reflections
    def corrupt():
        if not fired[0]:fired[0]=True;path.write_bytes(b'invented late first-opening corruption')
    def result_scan(*args):
        scan(*args);marked[0]=True
        if point=='result_scan':corrupt()
    def last_scan(*args):
        last(*args)
        if marked[0] and point=='last_preflight_scan':corrupt()
    monkeypatch.setattr(module,'_reject_reflections',result_scan)
    monkeypatch.setattr(preflight,'_reject_reflections',last_scan)
    with pytest.raises(RuntimeRefused):ctx.diagnostic()
    assert fired[0] and ctx._closed
    path.write_bytes(original_bytes)
    with pytest.raises(RuntimeRefused):ctx.diagnostic()


@pytest.mark.parametrize('fault',['bad_mirror','partial_schema'])
def test_unconfirmed_combined_context_refuses_corrupt_history(inputs,fault):
    o,*_=inputs
    with o.a.db:
        if fault=='bad_mirror':o.a.db.execute("UPDATE state SET value='{}' WHERE key='fake_attempt_guard_head'")
        else:o.a.db.execute('CREATE TABLE fake_intents(body TEXT,decision TEXT)')
    before=o.a.db.total_changes
    with pytest.raises(RuntimeRefused):context(inputs)
    assert o.a.db.total_changes==before


@pytest.mark.parametrize('fault',['current_account','first_opening','lineage','history','route','producer','combined','history_view'])
def test_final_lineage_exit_cannot_revoke_original_inputs(confirmed,monkeypatch,fault):
    from contextlib import contextmanager
    from compertum.runtime.paper_market_lineage_routes import PREFIX as ROUTE_PREFIX
    import compertum.runtime.paper_input_context as module
    o,first,fresh,capture,pub=confirmed
    first_manifest=pub._route(first['packet_id'])['publication']['manifest']
    later=launch((o,pub,None))
    for _ in range(10):pub.tick()
    proposal=call(pub,later,'account_propose');confirm(pub,later,proposal)
    ctx=context((o,later,fresh,capture,pub));market=o.a._market
    manifests=dict(current_account=pub._route(later['packet_id'])['publication']['manifest'],first_opening=first_manifest,
        lineage=market._lineage.records.read(capture)['manifest'],history=market.records.read(fresh['job_id'])['grant']['history']['manifest'])
    path=o.manager.root/manifests[fault]['path'] if fault in manifests else None
    before=path.read_bytes() if path is not None else None
    db=o.manager.store.conn;key=ROUTE_PREFIX+capture;route=db.execute('SELECT value FROM state WHERE key=?',(key,)).fetchone()[0]
    original=module.open_market_lineage;calls=[0];fired=[False]
    @contextmanager
    def revoked(*args,**kwargs):
        calls[0]+=1;number=calls[0]
        with original(*args,**kwargs) as opened:yield opened
        if number==2:
            fired[0]=True
            if path is not None:path.write_bytes(b'invented corruption after final lineage exit')
            elif fault=='route':
                with db:assert db.execute("UPDATE state SET value='{}' WHERE key=?",(key,)).rowcount==1
            elif fault=='producer':market._producer.close()
            elif fault=='combined':market._combined.close()
            else:market._opened.close()
    monkeypatch.setattr(module,'open_market_lineage',revoked)
    try:
        with pytest.raises(RuntimeRefused):ctx.diagnostic()
        assert fired[0] and ctx._closed
        if path is not None:path.write_bytes(before)
        if fault=='route':
            with db:db.execute('UPDATE state SET value=? WHERE key=?',(route,key))
        with pytest.raises(RuntimeRefused):ctx.diagnostic()
    finally:
        if fault=='route':
            (o.a.store.root/'injected-final-route.json').write_text(route)
            with db:db.execute('UPDATE state SET value=? WHERE key=?',(route,key))


@pytest.mark.parametrize('fault',['lineage_artifact','lineage_ledger','history_artifact','history_ledger','route','parent'])
def test_final_scan_cannot_hide_changed_market_originals(inputs,monkeypatch,fault):
    import compertum.runtime.paper_input_context as module
    import compertum.runtime.paper_preflight as preflight
    from compertum.runtime.paper_market_lineage_routes import PREFIX as ROUTE_PREFIX
    from compertum.data.encoding import canonical
    o,_,fresh,capture,_=inputs;market=o.a._market;ctx=context(inputs)
    saved=market._lineage.records.read(capture);db=o.manager.store.conn
    manifest=saved['manifest'] if not fault.startswith('history') else market.records.read(fresh['job_id'])['grant']['history']['manifest']
    path=o.manager.root/manifest['path'];original_bytes=path.read_bytes()
    if fault=='route':
        query='UPDATE state SET value=? WHERE key=?';identity=ROUTE_PREFIX+capture
        before=db.execute('SELECT value FROM state WHERE key=?',(identity,)).fetchone()[0];bad='{}'
    elif fault=='parent':
        query='UPDATE reservations SET status=? WHERE id=?';identity=saved['reservation_id']
        before=db.execute('SELECT status FROM reservations WHERE id=?',(identity,)).fetchone()[0];bad='RESERVED'
    else:
        query='UPDATE reservations SET manifest=? WHERE path=?';identity=manifest['path']
        before=db.execute('SELECT manifest FROM reservations WHERE path=?',(identity,)).fetchone()[0];bad='{}'
    marked=[False];fired=[False];scan=module._reject_reflections;last=preflight._reject_reflections
    def result_scan(*args):scan(*args);marked[0]=True
    def last_scan(*args):
        last(*args)
        if marked[0] and not fired[0]:
            fired[0]=True
            if fault.endswith('artifact'):path.write_bytes(b'invented late market corruption')
            else:
                with db:assert db.execute(query,(bad,identity)).rowcount==1
    def restore():
        if fault.endswith('artifact'):path.write_bytes(original_bytes)
        else:
            with db:assert db.execute(query,(before,identity)).rowcount==1
    monkeypatch.setattr(module,'_reject_reflections',result_scan)
    monkeypatch.setattr(preflight,'_reject_reflections',last_scan)
    try:
        with pytest.raises(RuntimeRefused):ctx.diagnostic()
        assert fired[0] and ctx._closed
        restore()
        with pytest.raises(RuntimeRefused):ctx.diagnostic()
    finally:
        # Preserve the injected fault even when restoring these invented rows is
        # needed for normal native fixture teardown. Never resume a runtime.
        (o.a.store.root/'injected-late-market-fault.json').write_bytes(canonical(dict(fault=fault,identity=identity,original=before,injected=bad,fired=fired[0])))
        restore()


@pytest.mark.parametrize('point',['result_scan','last_preflight_scan'])
def test_unconfirmed_combined_context_rechecks_current_artifact_after_scans(inputs,monkeypatch,point):
    import compertum.runtime.paper_input_context as module
    import compertum.runtime.paper_preflight as preflight
    o,packet,_,_,pub=inputs
    manifest=pub._route(packet['packet_id'])['publication']['manifest']
    path=o.manager.root/manifest['path'];original_bytes=path.read_bytes();ctx=context(inputs)
    marked=[False];fired=[False];scan=module._reject_reflections;last=preflight._reject_reflections
    def corrupt():
        if not fired[0]:fired[0]=True;path.write_bytes(b'invented late unconfirmed-account corruption')
    def result_scan(*args):
        scan(*args);marked[0]=True
        if point=='result_scan':corrupt()
    def last_scan(*args):
        last(*args)
        if marked[0] and point=='last_preflight_scan':corrupt()
    monkeypatch.setattr(module,'_reject_reflections',result_scan)
    monkeypatch.setattr(preflight,'_reject_reflections',last_scan)
    with pytest.raises(RuntimeRefused):ctx.diagnostic()
    assert fired[0] and ctx._closed
    path.write_bytes(original_bytes)
    with pytest.raises(RuntimeRefused):ctx.diagnostic()


@pytest.mark.parametrize('nonempty',[False,True])
def test_combined_context_accepts_verified_history_without_repair(inputs,nonempty):
    from compertum.fake_execution_journal import FakeIntentJournal
    from compertum.runtime.paper_account_binding import _history
    from test_fake_execution_journal import checked_records
    o,*_=inputs;journal=FakeIntentJournal(o.a.store)
    if nonempty:
        intent,decision=checked_records(o.a.lease);journal.record_checked(intent,decision)
    history=_history(o.a)
    assert history['status']=='VERIFIED_HISTORY' and history['empty'] is not nonempty
    before=o.a.db.total_changes;value=context(inputs).diagnostic()
    assert ('NONEMPTY_LOCAL_HISTORY_REQUIRES_RECONCILIATION' in value['deficiencies']) is nonempty
    assert value['status']=='BLOCKED' and not value['transport_authorized']
    assert o.a.db.total_changes==before


@pytest.mark.parametrize('fault',['account','lineage','history','producer','combined','history_view','credential_slot'])
def test_credential_scan_after_live_checks_cannot_change_final_inputs(inputs,monkeypatch,fault):
    import compertum.runtime.paper_input_context as module
    import compertum.runtime.paper_credential_slot as slot
    from compertum.runtime.paper_credentials import seal_paper_credentials
    o,packet,fresh,capture,pub=inputs;ctx=context(inputs);market=o.a._market
    manifests=dict(account=pub._route(packet['packet_id'])['publication']['manifest'],
        lineage=market._lineage.records.read(capture)['manifest'],history=market.records.read(fresh['job_id'])['grant']['history']['manifest'])
    path=o.manager.root/manifests[fault]['path'] if fault in manifests else o.manager.root/slot.SLOT_PATH
    before=path.read_bytes()
    replacement=slot._payload(seal_paper_credentials(o.e.lease,'fixture',bytearray(b'NEW_FIXTURE_KEY'),bytearray(b'NEW_FIXTURE_SECRET')))
    live=module._final_live;scan=slot._reject_reflections;armed=[False];fired=[False]
    def completed_live(*args):
        value=live(*args);armed[0]=True;return value
    def changed(*args):
        scan(*args)
        if armed[0] and not fired[0]:
            fired[0]=True
            if fault in manifests:path.write_bytes(b'invented corruption during final slot scan')
            elif fault=='credential_slot':path.write_bytes(replacement)
            elif fault=='producer':market._producer.close()
            elif fault=='combined':market._combined.close()
            else:market._opened.close()
    monkeypatch.setattr(module,'_final_live',completed_live)
    monkeypatch.setattr(slot,'_reject_reflections',changed)
    with pytest.raises(RuntimeRefused):ctx.diagnostic()
    assert fired[0] and ctx._closed
    path.write_bytes(before)
    with pytest.raises(RuntimeRefused):ctx.diagnostic()
