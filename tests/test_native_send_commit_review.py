"""Keep the final native health requirement and transaction state fixed."""
import pytest
from compertum.fake_attempt_guard import verify_attempt_guard
from compertum.runtime.errors import RuntimeRefused
from test_native_send_commit import call,journal,paper,native,records,AT,prepared

@pytest.mark.parametrize('field,value',[('required',False),('peer_role','evaluation'),('lease',None),('peer',None)])
def test_health_contract_cannot_change_after_final_clock_check(call,monkeypatch,field,value):
 from compertum.runtime import paper_fixture_send_commit as module
 current=prepared(call);original=module._health_finish
 def changed(*args):original(*args);setattr(call.owner.health,field,value)
 monkeypatch.setattr(module,'_health_finish',changed)
 with pytest.raises(RuntimeRefused):current.commit(now=AT)
 assert verify_attempt_guard(call.project)['sequence']==1
 current.close()

@pytest.mark.parametrize('phase',['health','identity'])
def test_final_callback_transaction_is_refused_and_preserved(call,monkeypatch,phase):
 from compertum.runtime import paper_fixture_send_commit as module
 def pending():call.owner.db.execute("INSERT INTO state VALUES('late-caller-write','true')")
 if phase=='health':
  original=module._health_finish
  def changed(*args):original(*args);pending()
  monkeypatch.setattr(module,'_health_finish',changed)
 else:call.proofs[-1]._final_identity=pending
 current=prepared(call)
 with pytest.raises(RuntimeRefused):current.commit(now=AT)
 assert call.owner.db.in_transaction and verify_attempt_guard(call.project)['sequence']==1
 assert call.owner.db.execute('SELECT state FROM fake_intents').fetchone()==('NATIVE_CONSUMED',)
 call.owner.db.rollback();current.close()
