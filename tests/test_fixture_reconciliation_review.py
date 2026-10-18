"""Private proofs and real native registry. Source readers remain simulated."""
from types import SimpleNamespace
import pytest
from compertum.runtime.errors import RuntimeRefused
from test_fixture_order_reconciliation_context import observed,dispatch_inputs,owner,original_owner,risk_inputs,account,confirmed,inputs,history,completed,pair,native_market,publication,invented_paper_origin,activity,activity_publication,published_activity,simulated_source,reconcile

def test_same_lease_native_transport_blocks_reconciliation_without_closing_it(observed):
 from test_winhttp_get import server,start
 from compertum.runtime._winhttp_get import _PENDING
 o,*_=observed
 with server(stall=True) as (port,arrived,seen):
  native=start(o.a.lease,port)
  try:
   assert arrived.wait(1)
   before=o.a.db.total_changes
   with pytest.raises(RuntimeRefused):reconcile(observed)
   assert id(native) in _PENDING and not native.native_closed and o.a.db.total_changes==before
  finally:native.close()

def test_later_presence_callback_cannot_replace_frozen_source_bytes(observed,monkeypatch):
 from compertum.runtime.paper_presence import _PresenceOwner
 o,intent,component,root,module=observed
 reader=module._reserved_source_file;raw,identity=reader();saved=[raw]
 monkeypatch.setattr(module,'_reserved_source_file',lambda *args:(saved[0],identity))
 original=_PresenceOwner._prepare_proof
 def prepare(self,**kwargs):
  proof=original(self,**kwargs);check=proof._check
  def changed():check();saved[0]=raw+b' '
  proof._check=changed;return proof
 monkeypatch.setattr(_PresenceOwner,'_prepare_proof',prepare)
 with pytest.raises(RuntimeRefused):reconcile(observed)
