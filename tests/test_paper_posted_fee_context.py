"""Original encrypted activity with simulated clocks, replies, and a 64 KiB reserve."""
import json,pickle
from uuid import uuid4
import pytest

from compertum.data.encoding import canonical
from compertum.runtime.errors import RuntimeRefused
from test_paper_reconciliation_context import (
    published_activity,pair,connect,owner,publication,invented_paper_origin,account,activity,activity_publication,
)
from test_paper_read_preparation import ACCOUNT,KEY,SECRET


def context(fixture,**changes):
    o,packet,saved,_=fixture
    values=dict(subject='a'*64,packet_id=packet['packet_id'],activity_id=saved['activity_id'])
    values.update(changes)
    return o.a.posted_fee_context(**values)


def published_fees(activity_publication,publication,monkeypatch,rows,cash):
    from test_paper_portfolio_context import fresh
    from test_paper_activity_owner import pages,pub_start,finish
    import test_paper_read_owner as reader
    o,_,pub,module,remote=activity_publication
    original=reader.body
    def body(operation):
        value=original(operation)
        return dict(value,cash=cash) if operation=='ACCOUNT' else value
    monkeypatch.setattr(reader,'body',body)
    o.clock.utc+=1;o.clock.mono+=1
    _,_,packet=fresh(publication)
    o.a.account_context(subject='a'*64,packet_id=packet['packet_id'])
    o.clock.utc+=1;o.clock.mono+=1
    with pages([canonical(rows)]) as (port,seen):
        o.activity_port=port;started=pub_start((o,packet,pub,module,remote));finish(o,started)
        for _ in range(12):pub.tick()
        saved=o.a._activities._read(started['activity_id'])
        assert saved['state']=='PUBLISHED'
    return o,packet,saved,seen


def test_empty_originals_are_private_read_only_and_never_fee_authority(published_activity):
    o,_,_,seen=published_activity;before=o.a.db.total_changes,len(seen)
    c=context(published_activity);v=c.diagnostic()
    assert v['record_type']=='PaperPostedFeeContextDiagnostic' and v['status']=='BLOCKED'
    assert v['posted_fee_count']==0 and v['cash_comparison']=='MATCHING_OBSERVED_CASH'
    assert v['actual_billed_fee'] is v['actual_flat'] is None
    assert v['financial_accepted'] is v['transport_authorized'] is False
    assert {'FEE_POSTING_INTERVAL_UNVERIFIED','FEE_LIABILITIES_UNVERIFIED','FEE_REVERSALS_UNVERIFIED'}<=set(v['unverified_requirements'])
    assert (o.a.db.total_changes,len(seen))==before
    assert all(s.encode() not in canonical(v) for s in (ACCOUNT,KEY,SECRET,'100000','expected_cash'))
    assert '100000' not in repr(c)
    with pytest.raises(RuntimeRefused):pickle.dumps(c)
    with pytest.raises(RuntimeRefused):type(c)()
    c.close();assert not c._context._closed


@pytest.mark.parametrize('kind',['backdated','after-cash-observation','credit','cancelling-pair','zero','negative-zero'])
def test_original_postings_preserve_both_cash_values_and_timing_uncertainty(activity_publication,publication,monkeypatch,kind):
    row=dict(id='original::fee-1',activity_type='FEE',date='2023-11-24',net_amount='-0.02',description='Invented posted cash activity')
    cash='99999.98';rows=[row]
    if kind=='backdated':row['date']='2023-11-23'
    elif kind=='credit':row['net_amount']='0.02';cash='100000.02'
    elif kind=='cancelling-pair':rows.append(dict(row,id='original::fee-2',net_amount='0.02'));cash='100000'
    elif kind in ('zero','negative-zero'):row['net_amount']='-0.00' if kind=='negative-zero' else '0';cash='100000'
    fixture=published_fees(activity_publication,publication,monkeypatch,rows,cash)
    o,packet,saved,_=fixture;c=context(fixture);v=c.diagnostic();private=json.loads(c._calculation)
    assert private['opening_cash']=='100000.00' and private['observed_cash']==cash
    assert private['calculation_matches'] and private['posted_fee_count']==len(rows)
    assert v['cash_comparison']=='MATCHING_OBSERVED_CASH'
    assert 'FEE_POSTING_INTERVAL_UNVERIFIED' in v['unverified_requirements']
    assert 'FEE_REVERSALS_UNVERIFIED' in v['unverified_requirements']
    assert 'Invented posted cash activity'.encode() not in canonical(v) and cash.encode() not in canonical(v)
    assert v['actual_billed_fee'] is None and v['financial_accepted'] is v['transport_authorized'] is False
    assert private['posted_fees']==rows
    if kind=='after-cash-observation':
        from compertum.runtime.paper_activity_evidence import open_activity_evidence
        from compertum.runtime.paper_read_packet import _nanoseconds
        records=[json.loads(raw) for _,raw in o.a.preflight(packet['packet_id'])._records]
        account_record=next(r for r in records if r['operation']=='ACCOUNT')
        with open_activity_evidence(o.e.lease,'fixture',saved['activity_id'],saved['manifest']) as opened:
            collected=opened.snapshot()['collection']['bindings']['started_at']
        assert _nanoseconds(collected)>_nanoseconds(account_record['received_at'])
    for factory in (o.a.reconciliation_context,o.a.position_cost_context):
        with pytest.raises(RuntimeRefused):factory(subject='a'*64,packet_id=packet['packet_id'],activity_id=saved['activity_id'])
    assert not o.a._account_context._closed


@pytest.mark.parametrize('fault',['subject','packet','activity'])
def test_foreign_posted_fee_references_refuse(published_activity,fault):
    values={'subject':'b'*64} if fault=='subject' else {fault+'_id':str(uuid4())}
    with pytest.raises(RuntimeRefused):context(published_activity,**values)


@pytest.mark.parametrize('case',[
    'missing_current_context_never_reopens_historical_freshness',
    'published_activity_without_live_context_cannot_supply_a_proof',
    'proof_is_single_use_and_closure_after_capture_refuses',
    'actual_replacement_context_never_revives_prior_wrapper',
    'same_alias_credential_substitution_refuses',
    'different_account_identity_refuses',
    'constructor_and_captured_proof_preserve_pending_transaction',
    'captured_database_controls_transaction_check_after_replacement',
    'activity_only_proof_failure_preserves_borrowed_account',
    'actual_account_failure_still_revokes_borrowed_account',
])
def test_existing_original_record_boundary_contract_applies(published_activity,monkeypatch,case):
    import test_paper_reconciliation_context as existing
    monkeypatch.setattr(existing,'context',context)
    getattr(existing,'test_'+case)(published_activity)


@pytest.mark.parametrize('fault',['record','artifact','opening','context','expiry','clock_gap'])
def test_original_changes_permanently_refuse(published_activity,monkeypatch,fault):
    import test_paper_reconciliation_context as existing
    monkeypatch.setattr(existing,'context',context)
    existing.test_changed_originals_permanently_invalidate_wrapper(published_activity,fault)


@pytest.mark.parametrize('fault',['wrapper','owner','database'])
def test_closed_resources_refuse(published_activity,monkeypatch,fault):
    import test_paper_reconciliation_context as existing
    monkeypatch.setattr(existing,'context',context)
    existing.test_closed_resources_cannot_supply_a_proof(published_activity,fault)


@pytest.mark.parametrize('state',['EVIDENCE_READY','ABORTED','INTERRUPTED'])
def test_unpublished_activity_never_supplies_posted_fee_observations(published_activity,monkeypatch,state):
    import test_paper_reconciliation_context as existing
    monkeypatch.setattr(existing,'context',context)
    existing.test_unpublished_activity_cannot_supply_matching_observations(published_activity,state)


@pytest.mark.parametrize('stage',['calculation','secrecy'])
def test_late_callbacks_cannot_change_original_activity(published_activity,monkeypatch,stage):
    from compertum.runtime import paper_posted_fee_context as module
    o,_,saved,_=published_activity;c=context(published_activity)
    name='calculate_posted_fees' if stage=='calculation' else '_reject_reflections';original=getattr(module,name)
    def changed(*args,**kw):
        value=original(*args,**kw)
        with o.a.db:o.a.db.execute('UPDATE state SET value=? WHERE key=?',
            (canonical(dict(saved,subject='b'*64)).decode(),'paper_activity:'+saved['activity_id']))
        return value
    monkeypatch.setattr(module,name,changed)
    with pytest.raises(RuntimeRefused):c.diagnostic()
    assert c._closed and not c._context._closed


def test_changed_calculation_content_is_refused(published_activity,monkeypatch):
    from compertum.runtime import paper_posted_fee_context as module
    original=module.calculate_posted_fees
    def changed(**values):
        result=original(**values)
        object.__setattr__(result,'content',canonical(dict(json.loads(result.content),financial_accepted=True)))
        return result
    monkeypatch.setattr(module,'calculate_posted_fees',changed)
    with pytest.raises(RuntimeRefused):context(published_activity)


def test_diagnostic_runs_the_actual_credential_reflection_check(published_activity,monkeypatch):
    from compertum.runtime import paper_posted_fee_context as module
    seen=[]
    def reject(raw,secrets):
        assert json.loads(raw)['record_type']=='PaperPostedFeeContextDiagnostic'
        assert KEY in secrets and SECRET in secrets;seen.append(True)
        raise RuntimeRefused('SIMULATED_DIAGNOSTIC_SECRET_REFLECTION')
    monkeypatch.setattr(module,'_reject_reflections',reject)
    with pytest.raises(RuntimeRefused):context(published_activity)
    assert seen


@pytest.mark.parametrize('route',['captured','diagnostic'])
def test_final_health_clock_cannot_change_original_fee_identity(published_activity,monkeypatch,route):
    from types import SimpleNamespace
    from compertum.runtime import execution_health
    c=context(published_activity);proof=c._prepare_proof() if route=='captured' else None
    clocks=execution_health.time
    def changed():
        result=clocks.monotonic();object.__setattr__(c,'_activity_id',str(uuid4()));return result
    monkeypatch.setattr(execution_health,'time',SimpleNamespace(monotonic=changed,time=clocks.time))
    with pytest.raises(RuntimeRefused):proof._verify() if proof else c.diagnostic()
    assert c._closed and not c._context._closed
    if proof:assert proof._used and proof._final_identity is None


def test_grouped_account_and_posted_fee_proofs_are_single_use(published_activity):
    from compertum.runtime.paper_final_proof import _verify_proofs
    c=context(published_activity);account_proof=c._context._prepare_proof();posted=c._prepare_proof()
    values=_verify_proofs(account_proof,posted)
    assert [v['record_type'] for v in values]==['PaperAccountInputDiagnostic','PaperPostedFeeContextDiagnostic']
    assert account_proof._final_identity is posted._final_identity is None
    with pytest.raises(RuntimeRefused):posted._verify()
