"""Original WinHTTP results are required even with simulated producer authority."""
from datetime import datetime
from types import SimpleNamespace
import json
import pytest
from compertum.fake_attempt_guard import verify_attempt_guard
from compertum.runtime.errors import RuntimeRefused
from test_fixture_order_native_dispatch import producer,pending,call,journal,paper,native,records,AT
from test_winhttp_order import service
from test_winhttp_get import finish
from test_paper_responses import order

@pytest.mark.parametrize('fault',['none','replacement','foreign-result','cleanup'])
def test_only_the_original_completed_native_reply_can_be_retained(producer,monkeypatch,fault):
 from compertum.runtime import paper_fixture_orders as module
 from compertum.runtime._winhttp_get import _HTTPResult
 call,p,q,clock=producer;retained=[]
 p._component=SimpleNamespace(active=p,_retain=lambda *args:retained.append(True));p._result=None;p._risk=None;p._intent_id=call.p['intent_id']
 monkeypatch.setattr(module,'_utc_now',lambda:datetime.fromisoformat('2023-11-24T14:35:01+00:00'))
 body=json.dumps(order(qty='1',client_order_id=call.p['client_order_id'])).encode()
 with service(body=body) as (port,_,seen):
  permit=pending(producer,port);native=module._FixtureOrderHTTP(p,_permit=permit);raw=finish(native)
  if fault=='replacement':p._native=SimpleNamespace(poll=lambda:raw,close=lambda:None)
  elif fault=='foreign-result':monkeypatch.setattr(native,'poll',lambda:_HTTPResult(raw.status_code,raw.body))
  elif fault=='cleanup':native.native_closed=False
  try:
   if fault=='none':assert p.poll()['effect_status']=='UNRECONCILED' and retained==[True]
   else:
    with pytest.raises(RuntimeRefused):p.poll()
    assert retained==[]
   assert verify_attempt_guard(call.project)['sequence']==1
   assert call.owner.db.execute('SELECT state FROM fake_intents').fetchone()==('NATIVE_CONSUMED',)
  finally:native.native_closed=True;native.close()
