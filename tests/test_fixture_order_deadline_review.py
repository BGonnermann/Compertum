"""Preparing an exchange must consume its original ten-second request budget."""
from types import SimpleNamespace
import time
import pytest
from compertum.fake_attempt_guard import verify_attempt_guard
from compertum.runtime.identity import resolve_project
from compertum.runtime.errors import RuntimeRefused
from test_fixture_order_private_factory import prepared as private_prepared,owner,original_owner,risk_inputs,account,confirmed,inputs,history,completed,pair,native_market,publication,invented_paper_origin,activity,activity_publication,published_activity,simulated_source

@pytest.mark.parametrize('delay',[10,10.1])
def test_preparation_cannot_extend_the_request_deadline(private_prepared,monkeypatch,delay):
 from compertum.runtime import paper_fixture_orders as module
 from compertum.runtime import _winhttp_get as backend
 o,intent,component,p=private_prepared;clock=[time.monotonic()];native_setup=[];prepare=module.prepare_order_exchange
 monkeypatch.setattr(module,'time',SimpleNamespace(monotonic=lambda:clock[0],monotonic_ns=lambda:int(clock[0]*10**9)))
 def delayed(*args,**kwargs):
  result=prepare(*args,**kwargs);clock[0]+=delay;return result
 def api():native_setup.append(True);raise RuntimeRefused('TEST_NATIVE_REACHED')
 monkeypatch.setattr(module,'prepare_order_exchange',delayed);monkeypatch.setattr(backend,'_API',api)
 with pytest.raises(RuntimeRefused):p.dispatch()
 assert native_setup==[] and verify_attempt_guard(resolve_project(o.a.store.root))['sequence']==0
