"""Original private risk proofs with simulated source authority and clocks."""
import pytest
from compertum.fake_attempt_guard import verify_attempt_guard
from compertum.runtime.identity import resolve_project
from compertum.runtime.errors import RuntimeRefused
from test_fixture_order_private_factory import prepared,owner,original_owner,risk_inputs,account,confirmed,inputs,history,completed,pair,native_market,publication,invented_paper_origin,activity,activity_publication,published_activity,simulated_source

def test_sql_consumption_cannot_change_original_source_before_send(prepared,monkeypatch):
 from compertum.fake_execution_journal import FakeIntentJournal
 o,intent,component,p=prepared;p._prepare();p._state='PENDING'
 source=p._source;event=FakeIntentJournal._event;changed=[False]
 monkeypatch.setattr(p,'_source',lambda:source() if not changed[0] else b'changed original source')
 def alter(*args):event(*args);changed[0]=True
 monkeypatch.setattr(FakeIntentJournal,'_event',alter)
 with pytest.raises(RuntimeRefused):p._call.commit(now=p._now())
 assert verify_attempt_guard(resolve_project(o.a.store.root))['sequence']==1
 assert o.a.db.execute('SELECT count(*) FROM fake_intents').fetchone()==(0,)

def test_producer_rejects_a_replaced_consumption_call(prepared):
 from compertum.runtime.paper_final_proof import _final_proof
 from compertum.runtime.paper_fixture_send_commit import _ConsumeCall
 o,intent,component,p=prepared;p._prepare();p._state='PENDING';original=p._call
 proofs=tuple(_final_proof(o.a,lambda:None,lambda:None,lambda reason:None,{'unqualified':i}) for i in range(2))
 replacement=_ConsumeCall(o.a,component.journal,p._p,p._d,proofs)
 try:
  p._call=replacement
  with pytest.raises(RuntimeRefused):p._pure()
 finally:p._call=original;replacement.close()
 assert verify_attempt_guard(resolve_project(o.a.store.root))['sequence']==0
