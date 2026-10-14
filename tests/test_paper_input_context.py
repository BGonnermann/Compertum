"""Native stores/DPAPI with local market replies and simulated account/clock data.

The confirmed fixture injects PAPER_TLS; it never establishes real account access.
"""
from datetime import datetime,timezone
from uuid import uuid4
import json,pickle
import pytest
from compertum.data.encoding import canonical
from compertum.runtime.errors import RuntimeRefused
from compertum.runtime.service_budget import queue_for
from test_paper_market_owner_fresh import history,completed,pair,owner,native_market,publication
from test_paper_market_publication import command
from test_paper_market_lineage_publication import drive,status
from test_paper_read_publication import publication as _account_publication,launch
from test_paper_read_preparation import ACCOUNT,KEY,SECRET
from test_paper_account_binding import invented_paper_origin,call,confirm


@pytest.fixture
def inputs(history,monkeypatch):
    import test_paper_read_owner as account_fixture
    original=account_fixture.body;o=history
    def at_current_clock(operation):
        value=original(operation)
        if operation=='CLOCK':
            value=dict(value,timestamp=datetime.fromtimestamp(o.clock.utc,timezone.utc).isoformat())
        return value
    monkeypatch.setattr(account_fixture,'body',at_current_clock)
    account=_account_publication.__wrapped__(o,monkeypatch)
    packet=launch(account);account_pub=account[1]
    for _ in range(10):account_pub.tick()
    assert account_pub.handle('a'*64,dict(operation='status',packet_id=packet['packet_id']))['state']=='PUBLISHED'
    fresh,_=completed(o);registration=o.remote.descriptor.registration
    registration.generation=o.e.lease.generation;registration.identity.process_instance_id=o.e.lease.identity.process_instance_id
    capture=str(uuid4())
    command(o,'publish_lineage',capture_id=capture,job_id=fresh['job_id'],grant_sha256=fresh['grant_sha256'])
    drive(o,capture,'DONE')
    return o,packet,fresh,capture,account_pub


def context(fixture,**changes):
    o,packet,fresh,capture,_=fixture
    values=dict(subject='a'*64,packet_id=packet['packet_id'],fresh_job_id=fresh['job_id'],capture_id=capture)
    values.update(changes)
    return o.a.input_context(**values)


def test_combines_original_inputs_without_new_requests_writes_or_authority(inputs):
    o,packet,fresh,capture,_=inputs
    requests=len(o.calls);quota=queue_for(o.e.lease).status()
    changes=(o.a.db.total_changes,o.pub.db.total_changes);held=o.a._market._opened
    c=context(inputs);v=c.diagnostic()
    assert v['packet_id']==packet['packet_id'] and v['fresh_job_id']==fresh['job_id'] and v['capture_id']==capture
    assert v['lineage_sha256']==status(o,capture)['lineage_sha256']
    assert v['status']=='BLOCKED' and v['actual_flat'] is None
    assert v['financial_accepted'] is v['transport_authorized'] is False
    assert {'SUPERVISION_UNVERIFIED','EXACT_PLAN_GRANT_REQUIRED','OWNERSHIP_UNVERIFIED','ECONOMIC_RECONCILIATION_UNVERIFIED',
            'FEE_EVIDENCE_UNVERIFIED','FEED_ENTITLEMENT_UNVERIFIED','ACCOUNT_CONFIRMATION_UNVERIFIED'}<=set(v['deficiencies'])
    raw=canonical(v)
    assert len(raw)<=16384 and all(secret.encode() not in raw for secret in (ACCOUNT,KEY,SECRET,'body_utf8'))
    assert (o.a.db.total_changes,o.pub.db.total_changes)==changes and len(o.calls)==requests and queue_for(o.e.lease).status()==quota
    c.close();assert held.snapshot()['collection']['mode']=='HISTORY'
    assert command(o,'compose',job_id=fresh['job_id'])['composition']['quote_valid']
    with pytest.raises(RuntimeRefused):c.diagnostic()


@pytest.mark.parametrize('field',['subject','packet_id','fresh_job_id','capture_id'])
def test_original_identity_substitution_refused(inputs,field):
    with pytest.raises(RuntimeRefused):context(inputs,**{field:'b'*64 if field=='subject' else str(uuid4())})


def test_historical_capture_does_not_freeze_the_current_observation_clock(inputs):
    o,_,_,capture,_=inputs;c=context(inputs);first=c.diagnostic();prior=status(o,capture)
    o.clock.utc+=10;o.clock.mono+=10
    second=c.diagnostic()
    assert second['checked_at']!=first['checked_at'] and second['lineage_sha256']==first['lineage_sha256']
    assert status(o,capture)==prior and second['status']=='BLOCKED'
    o.clock.utc+=21;o.clock.mono+=21
    with pytest.raises(RuntimeRefused):c.diagnostic()


@pytest.mark.parametrize('fault',['closed','replacement','cancel','restart','health','clock'])
def test_context_cannot_survive_invalidated_originals(inputs,fault):
    o,_,fresh,_,_=inputs;c=context(inputs)
    if fault=='closed':c.close()
    elif fault=='replacement':context(inputs)
    elif fault=='cancel':command(o,'cancel',job_id=fresh['job_id'])
    elif fault=='restart':o.a.close();o.a=o.module.PaperReadOwner(o.a.store,o.a.reserve,o.e)
    elif fault=='health':o.e.halt('FIXTURE_HEALTH_LOST')
    else:o.clock.mono+=6
    with pytest.raises(RuntimeRefused):c.diagnostic()


def test_context_is_private_and_cannot_be_passed_through_public_read_routing(inputs):
    o,packet,_,_,pub=inputs;c=context(inputs)
    assert ACCOUNT not in repr(c) and KEY not in repr(c) and SECRET not in repr(c)
    with pytest.raises(RuntimeRefused):pickle.dumps(c)
    with pytest.raises(RuntimeRefused):pub.handle('a'*64,dict(operation='input_context',packet_id=packet['packet_id']))


@pytest.fixture
def confirmed(invented_paper_origin,inputs):
    o,p,_,_,pub=inputs;r=call(pub,p,'account_propose');confirm(pub,p,r)
    return inputs


def test_unconfirmed_proposal_and_unverified_origin_remain_blocked(inputs):
    o,p,_,_,pub=inputs;r=call(pub,p,'account_propose')
    with pytest.raises(RuntimeRefused,match='NATIVE_ORIGIN'):confirm(pub,p,r)
    v=context(inputs).diagnostic()
    assert v['confirmation_status']=='UNCONFIRMED' and v['opening_status']=='UNVERIFIED'
    assert 'ACCOUNT_CONFIRMATION_UNVERIFIED' in v['deficiencies']


def test_current_confirmation_opening_does_not_clear_unrelated_blockers(confirmed):
    o,p,_,_,pub=confirmed;before=o.a.db.total_changes
    v=context(confirmed).diagnostic()
    assert v['confirmation_status']=='CONFIRMED_CURRENT_CONTEXT' and v['opening_status']=='CURRENT_CLEAN_OPENING'
    assert v['opening_reference_sha256']==o.a.opening_history('fixture')['opening_reference_sha256']
    assert 'ACCOUNT_CONFIRMATION_UNVERIFIED' not in v['deficiencies']
    assert {'HALT_EVIDENCE_UNVERIFIED','ACTION_EVIDENCE_UNVERIFIED','FEE_EVIDENCE_UNVERIFIED','EXACT_PLAN_GRANT_REQUIRED'}<=set(v['deficiencies'])
    assert v['status']=='BLOCKED' and not v['transport_authorized'] and v['actual_flat'] is None
    assert o.a.db.total_changes==before


@pytest.mark.parametrize('cash',['100000.01','100000.02','-1'])
def test_later_account_packet_uses_its_manifest_and_original_opening(confirmed,monkeypatch,cash):
    import test_paper_read_owner as fixture
    from compertum.runtime.paper_account_binding import _state
    o,p,f,capture,pub=confirmed;prior=_state(o.a,'paper_opening:fixture');old=context(confirmed)
    original=fixture.body
    monkeypatch.setattr(fixture,'body',lambda op:dict(original(op),cash=cash) if op=='ACCOUNT' else original(op))
    packet=launch((o,pub,None))
    for _ in range(10):pub.tick()
    proposal=call(pub,packet,'account_propose');confirm(pub,packet,proposal)
    with pytest.raises(RuntimeRefused):old.diagnostic()
    result=context((o,packet,f,capture,pub)).diagnostic()
    assert result['packet_id']==packet['packet_id']!=p['packet_id']
    assert _state(o.a,'paper_opening:fixture')==prior
    assert result['opening_status']==('CURRENT_CLEAN_OPENING' if cash=='100000.01' else 'BLOCKED')
    if cash!='100000.01':assert ('NEGATIVE_ACCOUNT_CASH' if cash=='-1' else 'UNEXPLAINED_CASH_CHANGE') in result['deficiencies']


def test_missing_opening_is_blocking_and_never_recreated(confirmed):
    o,*_=confirmed
    with o.a.db:o.a.db.execute("DELETE FROM state WHERE key='paper_opening:fixture'")
    before=o.a.db.total_changes;v=context(confirmed).diagnostic()
    assert v['opening_status']=='UNRECORDED' and 'PAPER_OPENING_UNRECORDED' in v['deficiencies']
    assert o.a.db.total_changes==before


@pytest.mark.parametrize('fault',['confirmation','opening','alias','account_artifact','account_ledger','lineage_artifact','lineage_ledger','consumption','capture'])
def test_corrupted_originals_never_become_missing_evidence(confirmed,fault):
    o,p,f,c,pub=confirmed;ctx=context(confirmed);calls=len(o.calls)
    restore=None
    if fault in ('confirmation','opening','alias','consumption','capture'):
        key={'confirmation':'paper_account_proposal:'+p['packet_id'],'opening':'paper_opening:fixture',
             'alias':'paper_account_alias:fixture','consumption':'paper_market_consumption:'+f['job_id'],
             'capture':'paper_market_lineage_capture:'+c}[fault]
        if fault=='capture':restore=(key,o.a.db.execute('SELECT value FROM state WHERE key=?',(key,)).fetchone()[0])
        with o.a.db:
            cursor=o.a.db.execute("UPDATE state SET value='{}' WHERE key=?",(key,));assert cursor.rowcount==1
    else:
        manifest=pub._route(p['packet_id'])['publication']['manifest'] if fault.startswith('account') else status(o,c)['manifest']
        if fault.endswith('artifact'):(o.manager.root/manifest['path']).write_bytes(b'corrupt invented encrypted evidence')
        else:
            with o.manager.store.conn:o.manager.store.conn.execute("UPDATE reservations SET manifest='{}' WHERE path=?",(manifest['path'],))
    try:
        with pytest.raises(RuntimeRefused):ctx.diagnostic()
        assert len(o.calls)==calls
    finally:
        if restore is not None:
            # Retain the injected bytes; restore only this invented test fault so
            # ordinary fixture teardown can close handles. No runtime is resumed.
            (o.a.store.root/'injected-capture-corruption.json').write_bytes(canonical(dict(key=restore[0],injected='{}',original=restore[1])))
            with o.a.db:o.a.db.execute('UPDATE state SET value=? WHERE key=?',(restore[1],restore[0]))


@pytest.mark.parametrize('point',['lineage','opening','scan'])
def test_final_recheck_rejects_expiry_during_verification(confirmed,monkeypatch,point):
    from contextlib import contextmanager
    import compertum.runtime.paper_input_context as module
    from compertum.runtime import paper_opening
    o,*_=confirmed;ctx=context(confirmed)
    def expire():o.clock.utc+=31;o.clock.mono+=31
    if point=='scan':
        original=module._reject_reflections
        def scan(*a,**kw):original(*a,**kw);expire()
        monkeypatch.setattr(module,'_reject_reflections',scan)
    else:
        target=module if point=='lineage' else paper_opening
        name='open_market_lineage' if point=='lineage' else 'open_read_evidence';original=getattr(target,name)
        @contextmanager
        def slow(*a,**kw):
            with original(*a,**kw) as value:yield value
            expire()
        monkeypatch.setattr(target,name,slow)
    with pytest.raises(RuntimeRefused):ctx.diagnostic()


def test_stale_market_remains_blocked_with_a_new_current_account_packet(inputs):
    o,p,f,c,pub=inputs;o.clock.utc+=31;o.clock.mono+=31
    packet=launch((o,pub,None))
    for _ in range(10):pub.tick()
    v=context((o,packet,f,c,pub)).diagnostic()
    assert not v['quote_valid'] and v['status']=='BLOCKED' and not v['transport_authorized']


def test_account_expiry_does_not_close_valid_borrowed_market(inputs,monkeypatch):
    from types import SimpleNamespace
    o,*_=inputs;ctx=context(inputs);held=o.a._market._opened
    monkeypatch.setattr(o.module,'time',SimpleNamespace(time=lambda:o.clock.utc+31,monotonic=lambda:o.clock.mono+31))
    with pytest.raises(RuntimeRefused,match='PREFLIGHT_STALE'):ctx.diagnostic()
    assert held.snapshot()['collection']['mode']=='HISTORY'


def test_rotated_credentials_and_direct_construction_refuse(inputs,monkeypatch):
    import compertum.runtime.paper_preflight as module
    from compertum.runtime.paper_credentials import seal_paper_credentials
    from compertum.runtime.paper_input_context import _PaperInputContext
    o,*_=inputs;ctx=context(inputs)
    with pytest.raises(RuntimeRefused):_PaperInputContext()
    changed=seal_paper_credentials(o.e.lease,'fixture',bytearray(b'NEW_FIXTURE_KEY'),bytearray(b'NEW_FIXTURE_SECRET'))
    monkeypatch.setattr(module,'load_paper_slot',lambda *a:changed)
    with pytest.raises(RuntimeRefused):ctx.diagnostic()


def test_existing_capture_from_another_fresh_job_is_not_adopted(inputs):
    o,p,f,c,pub=inputs;command(o,'cancel',job_id=f['job_id']);second,_=completed(o)
    with pytest.raises(RuntimeRefused):context((o,p,second,c,pub))
    assert command(o,'compose',job_id=second['job_id'])['composition']['quote_valid']


@pytest.mark.parametrize('fault',['expiry','health','credentials'])
def test_late_durable_read_cannot_outlive_the_last_live_check(confirmed,monkeypatch,fault):
    import compertum.runtime.paper_input_context as module
    from compertum.runtime.paper_credentials import seal_paper_credentials
    o,*_=confirmed;ctx=context(confirmed);held=o.a._market._opened;original=module._account_manifest;calls=[0]
    replacement=seal_paper_credentials(o.e.lease,'fixture',bytearray(b'NEW_FIXTURE_KEY'),bytearray(b'NEW_FIXTURE_SECRET'))
    def delayed(*a):
        result=original(*a);calls[0]+=1
        if calls[0]==2:
            if fault=='expiry':o.clock.utc+=31;o.clock.mono+=31
            elif fault=='health':o.e.halt('LATE_FIXTURE_HEALTH_LOST')
            else:monkeypatch.setattr(module,'load_paper_slot',lambda *a:replacement)
        return result
    monkeypatch.setattr(module,'_account_manifest',delayed)
    with pytest.raises(RuntimeRefused):ctx.diagnostic()
    assert calls[0]>=2 and held.snapshot()['collection']['mode']=='HISTORY'


@pytest.mark.parametrize('fault',['alias','history','proposal'])
def test_late_account_dependency_change_refuses_current_confirmation(confirmed,monkeypatch,fault):
    from contextlib import contextmanager
    import compertum.runtime.paper_input_context as module
    o,*_=confirmed;ctx=context(confirmed);held=o.a._market._opened;original=module.open_market_lineage
    @contextmanager
    def changed(*a,**kw):
        with original(*a,**kw) as opened:yield opened
        if fault=='proposal':o.a._account_proposal.close()
        else:
            key='paper_account_alias:fixture' if fault=='alias' else 'fake_attempt_guard_head'
            with o.a.db:o.a.db.execute("UPDATE state SET value='{}' WHERE key=?",(key,))
    monkeypatch.setattr(module,'open_market_lineage',changed)
    with pytest.raises(RuntimeRefused):ctx.diagnostic()
    assert held.snapshot()['collection']['mode']=='HISTORY'


@pytest.mark.parametrize('fault',['close','replace'])
def test_context_revoked_during_scan_cannot_return_a_result(inputs,monkeypatch,fault):
    import compertum.runtime.paper_input_context as module
    o,*_=inputs;ctx=context(inputs);held=o.a._market._opened;original=module._reject_reflections;called=[False]
    def revoke(*a,**kw):
        original(*a,**kw)
        if not called[0]:
            called[0]=True
            if fault=='close':ctx.close()
            else:context(inputs)
    monkeypatch.setattr(module,'_reject_reflections',revoke)
    with pytest.raises(RuntimeRefused):ctx.diagnostic()
    assert called[0] and held.snapshot()['collection']['mode']=='HISTORY'


def test_blocked_first_opening_is_preserved_after_a_clean_later_packet(invented_paper_origin,inputs):
    from compertum.runtime.paper_account_binding import _state
    o,p,f,c,pub=inputs;(o.a.store.root/'state/generations').mkdir()
    proposal=call(pub,p,'account_propose');confirm(pub,p,proposal);before=_state(o.a,'paper_opening:fixture')
    first=context(inputs).diagnostic();assert first['opening_status']=='BLOCKED' and 'RESTORE_HISTORY_PRESENT' in first['deficiencies']
    packet=launch((o,pub,None))
    for _ in range(10):pub.tick()
    proposal=call(pub,packet,'account_propose');confirm(pub,packet,proposal)
    second=context((o,packet,f,c,pub)).diagnostic()
    assert second['opening_status']=='BLOCKED' and second['opening_reference_sha256']==first['opening_reference_sha256']
    assert _state(o.a,'paper_opening:fixture')==before


@pytest.mark.parametrize('fault',['gap','expiry'])
def test_refused_context_never_revives_when_account_clock_is_restored(inputs,monkeypatch,fault):
    from types import SimpleNamespace
    o,_,fresh,_,_=inputs;ctx=context(inputs);held=o.a._market._opened
    with monkeypatch.context() as changed:
        delta=31 if fault=='expiry' else 0
        changed.setattr(o.module,'time',SimpleNamespace(time=lambda:o.clock.utc+delta,monotonic=lambda:o.clock.mono+(31 if fault=='expiry' else 6)))
        with pytest.raises(RuntimeRefused):ctx.diagnostic()
    with pytest.raises(RuntimeRefused):ctx.diagnostic()
    assert held.snapshot()['collection']['mode']=='HISTORY'
    assert command(o,'compose',job_id=fresh['job_id'])['composition']['quote_valid']
    assert context(inputs).diagnostic()['status']=='BLOCKED'
