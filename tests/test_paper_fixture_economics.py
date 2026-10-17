"""Private lifecycle checks with an explicitly simulated source resolver."""
import copy,hashlib,json,pickle
from datetime import datetime,timedelta,timezone
import pytest
from compertum.data.encoding import canonical
from compertum.runtime.errors import RuntimeRefused
from test_paper_reconciliation_context import published_activity,pair,connect,owner,publication,invented_paper_origin,account,activity,activity_publication
from test_fixture_economics import example,seal

def context(fixture,**changes):
    o,packet,saved,_=fixture
    values=dict(subject='a'*64,packet_id=packet['packet_id'],activity_id=saved['activity_id']);values.update(changes)
    return o.a.fixture_economic_context(**values)

@pytest.fixture
def simulated_source(published_activity,monkeypatch):
    from compertum.runtime import paper_fixture_economics as module
    o,_,_,_=published_activity
    now=datetime.fromtimestamp(o.clock.utc,timezone.utc)
    start=(now-timedelta(seconds=10)).isoformat().replace('+00:00','Z');until=now.isoformat().replace('+00:00','Z')
    def source(owner,account,base,originals):
        ledger=example()['ledger']
        ledger.update(project_id=originals['project_id'],account_alias=originals['account_alias'],opening_cash=originals['opening_cash'],
            opening_sha256=base['opening']['sha256'],history_sha256=base['journal'],covered_after=start,covered_until=until,events=[])
        seal(ledger)
        values=dict(originals=originals,ledger=ledger,opening_sha256=base['opening']['sha256'],history_sha256=base['journal'],
                    asset_id=ledger['asset_id'],symbol=ledger['symbol'],required_after=start,required_until=until)
        return values,hashlib.sha256(canonical(values)).hexdigest(),lambda:None
    monkeypatch.setattr(module,'_source_snapshot',source)
    return published_activity

def test_missing_original_native_source_refuses_without_changing_account(published_activity):
    o,_,_,_=published_activity
    with pytest.raises(RuntimeRefused):context(published_activity)
    assert not o.a._account_context._closed

def test_simulated_source_join_preserves_private_lifecycle_and_actual_refusals(simulated_source):
    c=context(simulated_source);result=c.diagnostic()
    assert result['scope']=='ENGINEERING_FIXTURE_ECONOMICS' and result['source_qualified']
    assert result['financial_accepted'] is result['transport_authorized'] is False
    assert 'ACTUAL_BILLING_UNVERIFIED' in result['unverified_requirements']
    assert '100000' not in repr(c) and '100000' not in json.dumps(result)
    with pytest.raises(RuntimeRefused):pickle.dumps(c)
    with pytest.raises(RuntimeRefused):type(c)()
    c.close();assert not c._context._closed

@pytest.mark.parametrize('fault',['subject','packet','activity'])
def test_foreign_original_reference_refuses(simulated_source,fault):
    from uuid import uuid4
    values={'subject':'b'*64} if fault=='subject' else {fault+'_id':str(uuid4())}
    with pytest.raises(RuntimeRefused):context(simulated_source,**values)

@pytest.mark.parametrize('case',[
 'missing_current_context_never_reopens_historical_freshness','published_activity_without_live_context_cannot_supply_a_proof',
 'proof_is_single_use_and_closure_after_capture_refuses','actual_replacement_context_never_revives_prior_wrapper',
 'same_alias_credential_substitution_refuses','different_account_identity_refuses',
 'constructor_and_captured_proof_preserve_pending_transaction','captured_database_controls_transaction_check_after_replacement',
 'activity_only_proof_failure_preserves_borrowed_account','actual_account_failure_still_revokes_borrowed_account'])
def test_existing_original_record_contract_applies(simulated_source,monkeypatch,case):
    import test_paper_reconciliation_context as existing
    monkeypatch.setattr(existing,'context',context)
    getattr(existing,'test_'+case)(simulated_source)

@pytest.mark.parametrize('fault',['record','artifact','opening','context','expiry','clock_gap'])
def test_changed_originals_refuse(simulated_source,monkeypatch,fault):
    import test_paper_reconciliation_context as existing
    monkeypatch.setattr(existing,'context',context)
    existing.test_changed_originals_permanently_invalidate_wrapper(simulated_source,fault)

@pytest.mark.parametrize('fault',['wrapper','owner','database'])
def test_closed_resources_refuse(simulated_source,monkeypatch,fault):
    import test_paper_reconciliation_context as existing
    monkeypatch.setattr(existing,'context',context)
    existing.test_closed_resources_cannot_supply_a_proof(simulated_source,fault)
