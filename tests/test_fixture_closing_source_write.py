"""Real file mutation during SQL. Source authority and clocks stay simulated."""
import pytest
from compertum.fake_attempt_guard import verify_attempt_guard
from compertum.runtime.errors import RuntimeRefused
from test_fixture_closing_context import held,seeded,owner,original_owner,confirmed,inputs,history,completed,pair,native_market,publication,invented_paper_origin,accepted,child,refreshed,advance,prepare_combined,confirm_intent

@pytest.mark.parametrize('phase',['accept','complete'])
def test_original_source_change_during_parent_sql_refuses_and_rolls_back(held,monkeypatch,phase):
 from compertum.runtime.paper_fixture_reconciliation import reconcile_fixture_orders
 o,pub,current,intent=held
 if phase=='complete':
  _,intent=prepare_combined((o,current.packet,current.fresh,current.capture,pub),'CLOSE_LONG',
   terms=dict(symbol='MSFT',quantity=2,children=[dict(maximum_quantity=2,notional_cap='2000')]))
  confirm_intent(o,intent);parent=accepted((o,pub,current,intent));p=child(parent,current)
  p._prepare();p._state='PENDING';p._call.commit(now=p._now());request=p._p['request'];advance(o,1)
  o.close_source.execute(client_id=p._p['client_order_id'],operation=request['operation'],parameters=request['parameters'],body=request['body']);p.close()
  current=refreshed(o,pub,monkeypatch,market=False)
  reconcile_fixture_orders(o.a,subject='a'*64,packet_id=current.packet['packet_id'],activity_id=current.activity['activity_id'],presence_id=current.presence['presence_id'])
  current=refreshed(o,pub,monkeypatch,market=False)
 key='fixture_closing_parent:'+intent['intent_id'];path=o.close_source.path;raw=path.read_bytes()
 before=o.a.db.execute('SELECT value FROM state WHERE key=?',(key,)).fetchone();guard=verify_attempt_guard(o.close_project)
 def change():path.write_bytes(raw+b' ');return 1
 o.a.db.create_function('change_parent_original_source',0,change)
 event='INSERT' if phase=='accept' else 'UPDATE'
 with o.a.db:
  o.a.db.execute("CREATE TRIGGER parent_original_changes AFTER "+event+" ON state WHEN new.key='"+key+"' BEGIN SELECT change_parent_original_source(); END")
 with pytest.raises(RuntimeRefused):
  if phase=='accept':accepted(held)
  else:parent.finish(subject='a'*64,packet_id=current.packet['packet_id'],activity_id=current.activity['activity_id'],presence_id=current.presence['presence_id'])
 assert path.read_bytes()==raw+b' '
 assert o.a.db.execute('SELECT value FROM state WHERE key=?',(key,)).fetchone()==before
 assert verify_attempt_guard(o.close_project)==guard
