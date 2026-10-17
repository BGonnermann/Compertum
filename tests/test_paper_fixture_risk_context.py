"""Real owner stores with simulated clocks, reserve, account origin, and source."""
import hashlib,pickle
from uuid import uuid4
import pytest
from compertum.data.encoding import canonical
from compertum.runtime.errors import RuntimeRefused
from test_paper_input_context import inputs,confirmed
from test_paper_market_owner_fresh import history,completed,pair,owner,native_market,publication
from test_paper_account_binding import invented_paper_origin
from test_paper_activity_owner import activity,activity_publication
from test_paper_reconciliation_context import published_activity
from test_paper_fixture_economics import simulated_source
from test_fixture_economics import seal
from test_native_intent_purposes import prepare_combined
from test_native_intent_cancel import confirm_intent

@pytest.fixture
def account(confirmed):
 o,packet,_,_,publisher=confirmed
 return o,publisher,packet

@pytest.fixture
def risk_inputs(simulated_source,confirmed,monkeypatch):
 from compertum.runtime import paper_fixture_economics as module
 original=module._source_snapshot;o,packet,saved,_=simulated_source
 def same_asset(*args):
  values,_,check=original(*args);market=o.a._market._combined.to_payload()['diagnostic']
  values['ledger'].update(asset_id=market['asset']['asset_id'],symbol=market['symbol']);seal(values['ledger'])
  values.update(asset_id=market['asset']['asset_id'],symbol=market['symbol'])
  return values,hashlib.sha256(canonical(values)).hexdigest(),check
 monkeypatch.setattr(module,'_source_snapshot',same_asset)
 _,intent=prepare_combined(confirmed,'FIXTURE_BUY');confirm_intent(o,intent)
 return o,intent,saved,confirmed

def context(fixture,**changes):
 o,intent,saved,_=fixture
 values=dict(subject='a'*64,intent_id=intent['intent_id'],activity_id=saved['activity_id']);values.update(changes)
 return o.a.fixture_risk_context(**values)

def test_current_confirmed_originals_supply_only_local_risk(risk_inputs):
 value=context(risk_inputs);result=value.diagnostic()
 assert result['scope']=='ENGINEERING_FIXTURE_RISK' and result['risk_status']=='CURRENT_LOCAL_RISK_CHECKED'
 assert result['source_qualified'] and result['purpose']=='FIXTURE_BUY'
 assert result['financial_accepted'] is result['transport_authorized'] is False
 assert 'DURABLE_DISPATCH_UNVERIFIED' in result['unverified_requirements']
 assert '100000' not in repr(value) and '100000' not in str(result)

def test_context_is_private_and_close_preserves_borrowed_inputs(risk_inputs):
 value=context(risk_inputs);owner=risk_inputs[0].a;account=owner._account_context;inputs=owner._input_context
 with pytest.raises(RuntimeRefused):pickle.dumps(value)
 with pytest.raises(RuntimeRefused):type(value)()
 value.close();assert not account._closed and not inputs._closed
 with pytest.raises(RuntimeRefused):value.diagnostic()

def test_final_proofs_are_original_and_single_use(risk_inputs):
 from compertum.runtime.paper_final_proof import _verify_proofs
 value=context(risk_inputs);proofs=value._prepare_proofs()
 assert len(proofs)==2
 assert _verify_proofs(*proofs)[0]['risk_status']=='CURRENT_LOCAL_RISK_CHECKED'
 with pytest.raises(RuntimeRefused):_verify_proofs(*proofs)

@pytest.mark.parametrize('field',['subject','intent_id','activity_id'])
def test_foreign_original_reference_refuses(risk_inputs,field):
 with pytest.raises(RuntimeRefused):context(risk_inputs,**{field:'b'*64 if field=='subject' else str(uuid4())})

@pytest.mark.parametrize('fault',['input','account','presence','confirmation','opening','activity','health','credentials','expiry','clock'])
def test_changed_originals_permanently_refuse(risk_inputs,fault):
 o,intent,saved,_=risk_inputs;value=context(risk_inputs)
 if fault=='input':o.a._input_context.close()
 elif fault=='account':o.a._account_context.close()
 elif fault=='presence':o.a._presence.close()
 elif fault=='confirmation':
  with o.a.db:o.a.db.execute('DELETE FROM paper_native_confirmations WHERE intent_id=?',(intent['intent_id'],))
 elif fault=='opening':
  with o.a.db:o.a.db.execute("UPDATE state SET value='{}' WHERE key='paper_opening:fixture'")
 elif fault=='activity':
  with o.a.db:o.a.db.execute("UPDATE state SET value='{}' WHERE key=?",('paper_activity:'+saved['activity_id'],))
 elif fault=='health':o.e.halt('RISK_FIXTURE_HEALTH_LOST')
 elif fault=='credentials':
  from compertum.runtime.paper_credential_slot import SLOT_PATH
  (o.a.store.root/SLOT_PATH).write_bytes(b'changed')
 elif fault=='expiry':o.clock.utc+=61;o.clock.mono+=61
 else:o.clock.utc+=6
 with pytest.raises(RuntimeRefused):value.diagnostic()
 assert value._closed
 with pytest.raises(RuntimeRefused):value.diagnostic()

def test_pending_transaction_is_preserved_without_revocation(risk_inputs):
 o=risk_inputs[0];value=context(risk_inputs)
 o.a.db.execute("INSERT INTO state VALUES('risk-caller-uncommitted','true')")
 with pytest.raises(RuntimeRefused):value.diagnostic()
 assert o.a.db.in_transaction and not value._closed
 o.a.db.rollback();assert value.diagnostic()['risk_status']=='CURRENT_LOCAL_RISK_CHECKED'

def test_late_changed_confirmation_refuses_captured_proofs(risk_inputs):
 from compertum.runtime.paper_final_proof import _verify_proofs
 o,intent,_,_=risk_inputs;value=context(risk_inputs);proofs=value._prepare_proofs()
 with o.a.db:o.a.db.execute('DELETE FROM paper_native_confirmations WHERE intent_id=?',(intent['intent_id'],))
 with pytest.raises(RuntimeRefused):_verify_proofs(*proofs)
