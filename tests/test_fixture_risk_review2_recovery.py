"""Additional cases from the same second review. No new review round is used."""
from uuid import uuid4
import pytest
from compertum.runtime.errors import RuntimeRefused
from test_native_write_journal import journal,paper,native,records,consume
from test_fixture_risk_review2 import (risk_inputs,context,simulated_source,confirmed,inputs,history,
 completed,pair,owner,native_market,publication,invented_paper_origin,activity,activity_publication,published_activity,account)

def test_native_recovery_cannot_run_an_unverified_fake_startup(journal):
 from compertum.native_write_journal import _NativeWriteJournal
 _,_,store,j=journal;p,d,_=consume(journal)
 j=_NativeWriteJournal(store,j.reserve);assert j.read('fixture',p['intent_id'])['status']=='NATIVE_UNKNOWN'
 older=str(uuid4())
 with store.conn:
  store.conn.execute('UPDATE fake_execution_session SET owner_instance=?',(older,))
  store.conn.execute("CREATE TRIGGER corrupt_native_at_fake_restart AFTER UPDATE ON fake_execution_session BEGIN UPDATE fake_intents SET state='NATIVE_ACKNOWLEDGED' WHERE state='NATIVE_UNKNOWN'; END")
 restored=_NativeWriteJournal(store,j.reserve)
 assert restored.read('fixture',p['intent_id'])['status']=='NATIVE_UNKNOWN'
 assert store.conn.execute('SELECT owner_instance FROM fake_execution_session').fetchone()==(older,)
 with pytest.raises(RuntimeRefused,match='NATIVE_EFFECT_UNCERTAIN'):consume((*journal[:3],restored))

@pytest.mark.parametrize('phase',['factory','prepared'])
@pytest.mark.parametrize('fault',['revoked-presence','input-owner'])
def test_post_health_revocation_and_input_owner_refuse(risk_inputs,monkeypatch,phase,fault):
 from compertum.runtime import paper_final_proof as module,paper_fixture_risk as risk_module
 o,intent,_,_=risk_inputs;presence=o.a._presence;inputs=o.a._input_context;captured_owner=inputs._owner
 p=o.a._intents._read(intent['intent_id']);proofs=context(risk_inputs)._prepare_proofs() if phase=='prepared' else None
 armed=[phase=='prepared'];join=risk_module._join
 def ready(*args):
  result=join(*args);armed[0]=True;return result
 monkeypatch.setattr(risk_module,'_join',ready);original=module._health_finish
 def replace(*args):
  original(*args)
  if armed[0]:
   if fault=='revoked-presence':presence._revoked[p['presence_id']]='REVIEW_LATE_REVOCATION'
   else:object.__setattr__(inputs,'_owner',object())
 monkeypatch.setattr(module,'_health_finish',replace)
 try:
  with pytest.raises(RuntimeRefused):
   if proofs is None:context(risk_inputs)
   else:module._verify_proofs(*proofs)
 finally:
  presence._revoked.pop(p['presence_id'],None);object.__setattr__(inputs,'_owner',captured_owner)
