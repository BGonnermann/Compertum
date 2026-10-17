"""Real private risk proofs; source readers, clocks, reserve, and endpoint are simulated."""
import json
import pytest
from compertum.data.encoding import canonical
from compertum.native_attempt_records import native_client_id,sha
from compertum.fake_attempt_guard import verify_attempt_guard
from compertum.runtime.errors import RuntimeRefused
from compertum.runtime.identity import resolve_project
from test_paper_fixture_risk_context import risk_inputs,account,confirmed,inputs,history,completed,pair,native_market,publication,invented_paper_origin,activity,activity_publication,published_activity,simulated_source
from test_paper_read_owner import owner as original_owner

@pytest.fixture
def owner(original_owner,monkeypatch):
 from compertum.runtime.paper_fixture_orders import install_fixture_orders
 monkeypatch.setattr('compertum.native_write_journal.execution_durable',lambda *args:None)
 original_owner.fixture_orders=install_fixture_orders(original_owner.a)
 return original_owner

@pytest.fixture
def prepared(risk_inputs,monkeypatch):
 from compertum.runtime import paper_fixture_orders as module
 o,intent,saved,_=risk_inputs
 monkeypatch.setattr('compertum.native_write_journal.execution_durable',lambda *args:None)
 component=o.fixture_orders
 peer={'scope':'SIMULATED_SOURCE_PEER'}
 monkeypatch.setattr(module,'_account_original',lambda *args:(None,{'order_source':{'journal_sha256':'e'*64}},{'port':44100,'peer':peer},None,None))
 monkeypatch.setattr(module,'native_source_peer',lambda *args:peer)
 monkeypatch.setattr(module,'source_file',lambda *args:({'ledger':{'ledger_head_sha256':'d'*64}},[1,'a'*32]))
 monkeypatch.setattr(module,'order_source_file',lambda *args:({'journal_sha256':'e'*64},[1,'b'*32]))
 p=component.prepare(subject='a'*64,intent_id=intent['intent_id'],activity_id=saved['activity_id'])
 try:yield o,intent,component,p
 finally:p.close();component.close()

def test_factory_joins_exact_original_risk_and_native_consumption(prepared):
 o,intent,component,p=prepared;p._prepare();p._state='PENDING'
 root=o.a._intents._read(intent['intent_id']);confirmation=o.a._intents._confirmation(root)
 assert p._p['evidence_sha256']['intent']==sha(root) and p._p['evidence_sha256']['confirmation']==sha(confirmation)
 assert p._p['client_order_id']==native_client_id(o.e.lease.project_id,'fixture',root['intent_id'])
 assert p._pending.to_payload()['body']['client_order_id']==p._p['client_order_id']
 p._call.commit(now=p._now());p._call.identity()
 assert verify_attempt_guard(resolve_project(o.a.store.root))['sequence']==1
 assert component.journal.read('fixture',root['intent_id'])['status']=='NATIVE_CONSUMED'

def test_changed_original_confirmation_prevents_consumption(prepared):
 o,intent,component,p=prepared;p._prepare();p._state='PENDING'
 with o.a.db:o.a.db.execute('DELETE FROM paper_native_confirmations WHERE intent_id=?',(intent['intent_id'],))
 with pytest.raises(RuntimeRefused):p._call.commit(now=p._now())
 assert o.a.db.execute('SELECT count(*) FROM fake_intents').fetchone()==(0,)
