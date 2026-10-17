"""Original fee observations with invented clocks and a labelled 64 KiB reserve."""
import json,pickle
from uuid import uuid4
import pytest

from compertum.runtime.errors import RuntimeRefused
from test_paper_reconciliation_context import (
    published_activity, pair, connect, owner, publication, invented_paper_origin,
    account, activity, activity_publication,
)
from compertum.data.encoding import canonical
from test_paper_fee_declarations import declared
from test_paper_fees import schedule
from test_paper_read_preparation import ACCOUNT,KEY,SECRET


def test_unpublished_fee_reference_refuses(published_activity):
    o, packet, saved, _ = published_activity
    with pytest.raises(RuntimeRefused):
        o.a.fee_context(subject='a'*64, packet_id=packet['packet_id'],
            activity_id=saved['activity_id'], declaration_id=str(uuid4()), manifest={})
    assert not o.a._account_context._closed


@pytest.mark.parametrize('fault,route',[
    ('schedule','construction'),('schedule','recapture'),
    ('source','construction'),('source','recapture'),
])
def test_valid_in_memory_declaration_change_refuses(fee_fixture,monkeypatch,fault,route):
    import compertum.runtime.paper_fee_context as module
    c=context(fee_fixture) if route=='recapture' else None
    original=module.calculate_fees
    def changed(batch,schedules):
        s=schedules[0];value=json.loads(s.content)
        if fault=='schedule':value['rules'][0]['rate']='0.01'
        else:
            object.__setattr__(s.sources[0],'raw',b'Changed invented source')
            value['source_sha256']=[s.sources[0].sha256]
        object.__setattr__(s,'content',canonical(value))
        return original(batch,schedules)
    monkeypatch.setattr(module,'calculate_fees',changed)
    with pytest.raises(RuntimeRefused):
        context(fee_fixture) if c is None else c.diagnostic()
    assert not fee_fixture[0][0].a._account_context._closed
    if c is not None:assert c._closed


@pytest.mark.parametrize('direction',['declaration_changes_activity','activity_changes_declaration'])
def test_late_publication_callback_cannot_change_other_originals(fee_fixture,monkeypatch,direction):
    import compertum.runtime.paper_fee_declarations as declared_module
    import compertum.runtime.paper_reconciliation_context as activity_module
    o,_,saved,_=fee_fixture[0];c=context(fee_fixture);proof=c._prepare_proof();called=[]
    module=declared_module if direction=='declaration_changes_activity' else activity_module
    original=module._published
    def changed(*args):
        value=original(*args);called.append(True)
        if direction=='declaration_changes_activity':
            with o.a.db:o.a.db.execute('UPDATE state SET value=? WHERE key=?',
                (canonical(dict(saved,subject='b'*64)).decode(),'paper_activity:'+saved['activity_id']))
        else:(o.manager.root/fee_fixture[2]['path']).write_bytes(b'{}')
        return value
    monkeypatch.setattr(module,'_published',changed)
    with pytest.raises(RuntimeRefused):proof._verify()
    assert called and proof._used and c._closed and not c._context._closed


@pytest.fixture
def fee_fixture(published_activity):
    o,_,_,_=published_activity
    identity,_,manifest,_=declared(o,(schedule(declared_from='2020-01-01',declared_until='2030-01-01'),))
    return published_activity,identity,manifest


def context(fixture,**changes):
    observed,identity,manifest=fixture;o,packet,saved,_=observed
    values=dict(subject='a'*64,packet_id=packet['packet_id'],activity_id=saved['activity_id'],
        declaration_id=identity,manifest=manifest)
    values.update(changes)
    return o.a.fee_context(**values)


def test_current_empty_declaration_stays_private_and_unqualified(fee_fixture):
    o,_,_,seen=fee_fixture[0];before=o.a.db.total_changes,len(seen)
    c=context(fee_fixture);value=c.diagnostic()
    assert value['record_type']=='PaperFeeContextDiagnostic' and value['status']=='BLOCKED'
    assert value['declaration_status']=='DECLARED_BATCH_CALCULATED'
    assert value['declared_execution_count']==value['declared_day_count']==0
    assert value['calculation_batch_count']==1 and value['actual_billed_fee'] is None
    assert value['financial_accepted'] is value['transport_authorized'] is False and value['actual_flat'] is None
    assert {'FEE_LIABILITIES_UNVERIFIED','FEE_SOURCE_INTERPRETATION_UNVERIFIED',
        'FEE_ACCOUNT_APPLICABILITY_UNVERIFIED','FEE_BILLING_UNVERIFIED',
        'ACTION_EVIDENCE_UNVERIFIED','RISK_UNVERIFIED','DURABLE_CONSUMPTION_UNVERIFIED'}<=set(value['unverified_requirements'])
    assert (o.a.db.total_changes,len(seen))==before
    assert all(s.encode() not in canonical(value) for s in (ACCOUNT,KEY,SECRET,'Invented fee source','100000'))
    assert 'Invented fee source' not in repr(c)
    with pytest.raises(RuntimeRefused):pickle.dumps(c)
    with pytest.raises(RuntimeRefused):type(c)()
    c.close();assert not o.a._account_context._closed


@pytest.mark.parametrize('kind',['missing','overlap'])
def test_missing_or_ambiguous_rules_stay_incomplete_without_actual_fee_claim(published_activity,kind):
    o,_,_,_=published_activity
    ss=() if kind=='missing' else (schedule(declared_from='2020-01-01',declared_until='2030-01-01'),
        schedule(schedule_id=str(uuid4()),declared_from='2020-01-01',declared_until='2030-01-01'))
    identity,_,manifest,_=declared(o,ss)
    c=context((published_activity,identity,manifest));value=c.diagnostic()
    assert value['declaration_status']=='INCOMPLETE_DECLARATIONS' and value['actual_billed_fee'] is None
    assert 'FEE_LIABILITIES_UNVERIFIED' in value['unverified_requirements']


@pytest.mark.parametrize('fault',['subject','packet','activity','declaration','manifest'])
def test_foreign_original_fee_references_refuse(fee_fixture,fault):
    values={'subject':'b'*64} if fault=='subject' else {'manifest':{}} if fault=='manifest' else {fault+'_id':str(uuid4())}
    with pytest.raises(RuntimeRefused):context(fee_fixture,**values)
    assert not fee_fixture[0][0].a._account_context._closed


@pytest.mark.parametrize('fault',['expiry','clock_gap','opening','record'])
def test_changed_current_originals_permanently_refuse(fee_fixture,fault):
    o,_,saved,_=fee_fixture[0];c=context(fee_fixture)
    if fault=='expiry':o.clock.utc+=31;o.clock.mono+=31
    elif fault=='clock_gap':o.clock.utc+=6
    elif fault=='opening':
        with o.a.db:o.a.db.execute("UPDATE state SET value='{}' WHERE key='paper_opening:fixture'")
    else:
        with o.a.db:o.a.db.execute('UPDATE state SET value=? WHERE key=?',
            (canonical(dict(saved,subject='b'*64)).decode(),'paper_activity:'+saved['activity_id']))
    with pytest.raises(RuntimeRefused):c.diagnostic()
    assert c._closed
    with pytest.raises(RuntimeRefused):c.diagnostic()


@pytest.mark.parametrize('fault',['wrapper','owner','database'])
def test_closed_resources_cannot_supply_a_fee_proof(fee_fixture,fault):
    o,_,_,_=fee_fixture[0];c=context(fee_fixture)
    if fault=='wrapper':c.close()
    elif fault=='owner':o.a.close()
    else:o.a.db.close()
    with pytest.raises(RuntimeRefused):c._prepare_proof()
    assert c._closed


def test_pending_caller_work_and_unused_proof_survive_refusal(fee_fixture):
    o,_,_,_=fee_fixture[0]
    o.a.db.execute("INSERT INTO state VALUES('caller-uncommitted','true')")
    with pytest.raises(RuntimeRefused):context(fee_fixture)
    assert o.a.db.in_transaction and not o.a._account_context._closed
    o.a.db.rollback();c=context(fee_fixture);proof=c._prepare_proof()
    o.a.db.execute("INSERT INTO state VALUES('caller-uncommitted','true')")
    with pytest.raises(RuntimeRefused):proof._verify()
    assert not proof._used and not c._closed and o.a.db.in_transaction
    o.a.db.rollback();assert proof._verify()['status']=='BLOCKED'


@pytest.mark.parametrize('stage',['calculation','secrecy'])
def test_callback_cannot_replace_retained_declaration(fee_fixture,monkeypatch,stage):
    import compertum.runtime.paper_fee_context as module
    o,_,_,_=fee_fixture[0];c=context(fee_fixture);path=o.manager.root/fee_fixture[2]['path']
    original=getattr(module,'calculate_fees' if stage=='calculation' else '_reject_reflections')
    def changed(*args,**kw):
        value=original(*args,**kw);path.write_bytes(b'{}');return value
    monkeypatch.setattr(module,'calculate_fees' if stage=='calculation' else '_reject_reflections',changed)
    with pytest.raises(RuntimeRefused):c.diagnostic()
    assert c._closed and not o.a._account_context._closed


@pytest.mark.parametrize('route',['captured','diagnostic'])
def test_final_health_clock_cannot_change_fee_binding(fee_fixture,monkeypatch,route):
    from types import SimpleNamespace
    from compertum.runtime import execution_health
    o,_,_,_=fee_fixture[0];c=context(fee_fixture);proof=c._prepare_proof() if route=='captured' else None
    clocks=execution_health.time
    def changed():
        result=clocks.monotonic();object.__setattr__(c,'_declaration_id',str(uuid4()));return result
    monkeypatch.setattr(execution_health,'time',SimpleNamespace(monotonic=changed,time=clocks.time))
    with pytest.raises(RuntimeRefused):proof._verify() if proof else c.diagnostic()
    assert c._closed and not o.a._account_context._closed
    if proof:assert proof._used and proof._final_identity is None


def test_grouped_fee_and_account_proofs_are_single_use_and_clear_hooks(fee_fixture):
    from compertum.runtime.paper_final_proof import _verify_proofs
    c=context(fee_fixture);account=c._context._prepare_proof();fee=c._prepare_proof()
    values=_verify_proofs(account,fee)
    assert [v['record_type'] for v in values]==['PaperAccountInputDiagnostic','PaperFeeContextDiagnostic']
    assert account._final_identity is fee._final_identity is None
    with pytest.raises(RuntimeRefused):fee._verify()
    c.close();assert not c._context._closed


def test_changed_calculation_object_is_not_accepted(fee_fixture,monkeypatch):
    import compertum.runtime.paper_fee_context as module
    c=context(fee_fixture);original=module.calculate_fees
    def changed(*args):
        value=original(*args);object.__setattr__(value,'content',canonical(dict(json.loads(value.content),actual_billed_fee='0')))
        return value
    monkeypatch.setattr(module,'calculate_fees',changed)
    with pytest.raises(RuntimeRefused):c.diagnostic()
    assert c._closed and not c._context._closed


def test_actual_account_failure_retains_existing_revocation(fee_fixture,monkeypatch):
    import test_paper_reconciliation_context as old
    monkeypatch.setattr(old,'context',lambda fixture:context((fixture,fee_fixture[1],fee_fixture[2])))
    old.test_actual_account_failure_still_revokes_borrowed_account(fee_fixture[0])


def test_nonfill_activity_is_preserved_as_unknown_and_never_a_paid_fee(activity_publication):
    from test_paper_activity_owner import pages,pub_start,finish
    o,packet,pub,module,remote=activity_publication
    with pages([canonical([dict(id='original::unknown-charge',activity_type='FEE',net_amount='-1')])]) as (port,seen):
        o.activity_port=port;started=pub_start(activity_publication);finish(o,started)
        for _ in range(12):pub.tick()
        saved=o.a._activities._read(started['activity_id'])
        identity,_,manifest,_=declared(o,(schedule(declared_from='2020-01-01',declared_until='2030-01-01'),))
        c=context(((o,packet,saved,seen),identity,manifest));value=c.diagnostic()
        assert value['declared_execution_count']==0 and value['unsupported_activity_count']==1
        assert value['actual_billed_fee'] is None and 'UNSUPPORTED_ACTIVITY' in value['unverified_requirements']
        with pytest.raises(RuntimeRefused):o.a.reconciliation_context(subject='a'*64,packet_id=packet['packet_id'],activity_id=saved['activity_id'])


def original_fill_fixture(activity_publication,publication,monkeypatch,kind):
    from compertum.fake_execution_journal import FakeIntentJournal
    from compertum.fake_attempt_guard import append_record
    from compertum.native_attempt_records import sha
    from test_native_attempt_records import records,attempt
    from test_paper_portfolio import order,position
    from test_paper_portfolio_context import fresh
    from test_paper_activity_owner import pages,pub_start,finish
    import test_paper_read_owner as reader
    o,_,pub,module,remote=activity_publication;FakeIntentJournal(o.a.store)
    p,d=records(o.e.lease);p['created_at']='2023-11-24T14:30:00.100000Z';p['expires_at']='2023-11-24T14:31:00.100000Z'
    p['request']['created_at']=p['created_at'];p['request_sha256']=sha(p['request']);d['intent_sha256']=sha(p)
    with o.a.db:append_record(o.a.store,dict(attempt(p,d),attempted_at=p['created_at']))
    observed=order(client_order_id=p['client_order_id'],qty='1',filled_qty='1',filled_avg_price='150',status='filled',submitted_at='2023-11-24T14:30:00.200000Z')
    original=reader.body
    def body(operation):
        if operation=='POSITIONS':return [position()]
        if operation=='ORDERS':return [observed]
        value=original(operation)
        return dict(value,cash='99849.98') if operation=='ACCOUNT' else value
    monkeypatch.setattr(reader,'body',body);o.clock.utc+=1;o.clock.mono+=1
    _,_,packet=fresh(publication);o.a.account_context(subject='a'*64,packet_id=packet['packet_id'])
    fill=dict(activity_type='FILL',id='original::owned-fill',order_id=observed['id'],symbol='AAPL',side='buy',qty='1',cum_qty='1',leaves_qty='0',price='150',transaction_time='2023-11-24T14:30:00.300000Z',type='fill')
    if kind=='foreign':fill['order_id']=str(uuid4())
    o.clock.utc+=1;o.clock.mono+=1
    with pages([canonical([] if kind=='missing' else [fill])]) as (port,seen):
        o.activity_port=port;started=pub_start((o,packet,pub,module,remote));finish(o,started)
        for _ in range(12):pub.tick()
        saved=o.a._activities._read(started['activity_id'])
    identity,_,manifest,_=declared(o,(schedule(declared_from='2020-01-01',declared_until='2030-01-01'),))
    return (o,packet,saved,seen),identity,manifest


@pytest.mark.parametrize('kind',['valid','foreign','missing'])
def test_original_cash_difference_stays_unchanged_and_foreign_fills_refuse(activity_publication,publication,monkeypatch,kind):
    import compertum.runtime.paper_fee_context as module
    fixture=original_fill_fixture(activity_publication,publication,monkeypatch,kind)
    o,packet,saved,_=fixture[0];seen=[];validate=module.validate_fill_history
    def checked(**values):seen.append(values['current_cash']);return validate(**values)
    monkeypatch.setattr(module,'validate_fill_history',checked)
    if kind!='valid':
        with pytest.raises(RuntimeRefused):context(fixture)
        assert not o.a._account_context._closed
        return
    c=context(fixture);value=c.diagnostic()
    assert seen and set(seen)=={'99849.98'}
    assert value['declared_execution_count']==value['declared_day_count']==1
    assert value['actual_billed_fee'] is None and 'FEE_LIABILITIES_UNVERIFIED' in value['unverified_requirements']
    for factory in (o.a.reconciliation_context,o.a.position_cost_context):
        with pytest.raises(RuntimeRefused):factory(subject='a'*64,packet_id=packet['packet_id'],activity_id=saved['activity_id'])
    assert not o.a._account_context._closed
