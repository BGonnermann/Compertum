"""Original-history integration with explicitly simulated native file and peer readers."""
from contextlib import contextmanager
from copy import deepcopy
from types import SimpleNamespace
import hashlib,json
import pytest
from compertum.data.encoding import canonical
from compertum.fixture_source_journal import decode_source_journal
from compertum.runtime.errors import RuntimeRefused
from test_fixture_order_source import source,record,execute

def test_native_file_reader_accepts_verified_future_transactions(source,monkeypatch):
 from compertum.runtime import fixture_source_binding as module
 execute(source,record(source));project=source.orders.snapshot()['origin']['project_id']
 @contextmanager
 def scope(lease):yield SimpleNamespace(project=SimpleNamespace(project_id=project))
 monkeypatch.setattr(module,'_owner_scope',scope)
 monkeypatch.setattr(module,'_reserved_source_file',lambda *args:(source.orders.path.read_bytes(),[1,'1'*32]))
 monkeypatch.setattr(module,'source_file',lambda *args:(decode_source_journal(source.economic.path.read_bytes()),[1,'0'*32]))
 value,identity=module.order_source_file(object())
 assert value['transaction_count']==1 and value['inventory']['positions'][0]['qty']=='1' and identity==[1,'1'*32]

def prepared(source,monkeypatch):
 from compertum.runtime import paper_fixture_economics as module
 source.clock.value='2026-10-17T19:00:00.000002Z'
 first=source.economic.snapshot(opening_sha256='0'*64,history_sha256='0'*64,until=source.clock())
 initial=source.orders.snapshot();native=record(source);execute(source,native)
 observed=source.orders.observations();current=source.economic.snapshot(opening_sha256='0'*64,history_sha256='0'*64,until=source.clock())
 orders=source.orders.snapshot();journal=decode_source_journal(source.economic.path.read_bytes())
 descriptor=lambda value:{key:value[key] for key in ('producer_id','genesis_sha256','journal_sha256')}
 peer=dict(scope='SIMULATED_TEST_PEER');file_id=[1,'0'*32];order_id=[1,'1'*32]
 def embedded(snapshot,order):
  return dict(version=1,producer_id=snapshot['producer_id'],genesis_sha256=snapshot['genesis_sha256'],ledger=snapshot['ledger'],
   order_source=descriptor(order),served_by=peer)
 first=embedded(first,initial);current=embedded(current,orders)
 def witness(snapshot,key):
  return dict(request_sha256=key,peer=peer,port=44100,source_file_identity=file_id,order_source_file_identity=order_id,order_source=snapshot['order_source'])
 one=witness(first,'f'*64);two=witness(current,'e'*64)
 rows={'first':(dict(request=dict(created_at='2026-10-17T19:00:00.000001Z')),first,one,canonical(one).decode(),dict(first=True)),
  'current':(dict(request=dict(created_at='2026-10-17T19:00:01Z'),parsed=dict(received_at='2026-10-17T19:00:02.000001Z')),
   current,two,canonical(two).decode(),dict(current=True))}
 class DB:
  in_transaction=False
  def execute(self,query,parameters):
   assert query=='SELECT body FROM fixture_source_witnesses WHERE request_sha256=?'
   result=next((row[3] for row in rows.values() if row[2]['request_sha256']==parameters[0]),None)
   return SimpleNamespace(fetchone=lambda:(result,) if result is not None else None)
 owner=SimpleNamespace(db=DB(),lease=object());context=SimpleNamespace(_packet='current')
 base=dict(opening=dict(sha256='a'*64,reference=dict(first_packet_id='first')),journal='b'*64)
 originals=dict(project_id=orders['origin']['project_id'],account_alias='fixture',opening_cash='1000',current_cash=observed['cash'],
  attempts=tuple(source.saved['records']),orders=tuple(observed['orders']),positions=tuple(observed['positions']),activities=tuple(observed['activities']))
 monkeypatch.setattr(module,'_account_original',lambda owner,alias,packet:rows[packet])
 monkeypatch.setattr(module,'source_file',lambda lease:(journal,file_id))
 monkeypatch.setattr(module,'order_source_file',lambda lease:(orders,order_id))
 monkeypatch.setattr(module,'native_source_peer',lambda *args:peer)
 return module,owner,context,base,originals,rows,orders

def test_original_empty_descriptor_is_a_verified_prefix_of_current_history(source,monkeypatch):
 module,owner,context,base,originals,rows,orders=prepared(source,monkeypatch)
 values,pin,check=module._source_snapshot(owner,context,base,originals);check()
 assert values['originals']==originals and len(pin)==64
 assert rows['first'][1]['order_source']['journal_sha256'] in orders['prefix_sha256']

@pytest.mark.parametrize('fault',['first-prefix','foreign-attempt','orders','positions','fills','current-head'])
def test_history_extension_cannot_hide_changed_originals(source,monkeypatch,fault):
 module,owner,context,base,originals,rows,orders=prepared(source,monkeypatch)
 if fault=='first-prefix':rows['first'][1]['order_source']['journal_sha256']='e'*64
 elif fault=='foreign-attempt':originals['attempts']=()
 elif fault=='orders':originals['orders']=()
 elif fault=='positions':originals['positions']=()
 elif fault=='fills':originals['activities']=()
 else:rows['current'][1]['order_source']['journal_sha256']='e'*64
 with pytest.raises(RuntimeRefused):module._source_snapshot(owner,context,base,originals)
