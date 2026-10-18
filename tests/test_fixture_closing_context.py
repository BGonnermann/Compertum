"""Real owned proofs and stores. Clocks, source authority and reserve are simulated."""
from datetime import datetime,timedelta,timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4
import hashlib,json
import pytest
from compertum.data.encoding import canonical
from compertum.fake_attempt_guard import verify_attempt_guard
from compertum.native_attempt_records import sha
from compertum.paper_contracts import utc
from compertum.runtime.errors import RuntimeRefused
from compertum.runtime.identity import resolve_project
from test_fixture_order_private_factory import owner,original_owner
from test_paper_input_context import confirmed,inputs
from test_paper_market_owner_fresh import history,completed,pair,native_market,publication
from test_paper_account_binding import invented_paper_origin,call,confirm
from test_paper_read_publication import launch
from test_paper_activity_owner import activity,activity_publication,pub_start,finish
from test_paper_market_collection import pages
from test_paper_presence import acknowledge,advance
from test_native_intent_purposes import prepare_combined
from test_native_intent_cancel import confirm_intent
from test_fixture_order_origin import origin
from test_fixture_economics import example

def stamp(o):return utc(datetime.fromtimestamp(o.clock.utc,timezone.utc).isoformat())

def serviced(o,seconds):
 from test_execution_health import connect
 while seconds:
  step=min(10,seconds);seconds-=step
  o.clock.utc+=step;o.clock.mono+=step;o.c.utc+=step;o.c.mono+=step
  connect(o.e,o.w);o.a.tick()

@pytest.fixture
def seeded(owner,tmp_path,monkeypatch):
 import test_paper_market_owner_fresh as market_fixture
 import test_paper_read_owner as account_fixture
 from helpers.stateful_economic_fixture import ControlledEconomicSource
 from helpers.stateful_order_fixture import ControlledOrderSource
 o=owner;project=resolve_project(o.a.store.root);begin=origin();begin.update(project_id=project.project_id,created_at='2023-11-24T13:59:59Z')
 initial=[True]
 def clock():return begin['created_at'] if initial[0] else stamp(o)
 ledger=example()['ledger'];ledger.update(project_id=project.project_id,account_alias='fixture',asset_id=begin['asset_id'],symbol='MSFT',opening_cash='1000')
 economic=ControlledEconomicSource.create(tmp_path/'economic.jsonl',ledger,clock)
 begin.update(economic_producer_id=economic._producer,economic_genesis_sha256=economic._genesis)
 source=ControlledOrderSource.create(tmp_path/'orders.jsonl',begin,economic,clock,lambda:verify_attempt_guard(project),lambda:('89','90'))
 initial[0]=False;o.close_source=source;o.close_economic=economic;o.close_project=project
 old_bodies=market_fixture.bodies
 def bodies(ctx):
  rows=old_bodies(ctx);asset=json.loads(rows[0]);asset['id']=begin['asset_id'];return [canonical(asset),rows[1]]
 monkeypatch.setattr(market_fixture,'bodies',bodies)
 old_body=account_fixture.body
 def body(op):
  value=old_body(op)
  if op=='POSITIONS':return source.snapshot()['inventory']['positions']
  if op=='ORDERS':return source.snapshot()['inventory']['orders']
  if op=='ACCOUNT':return dict(value,cash=str(Decimal('1000')+Decimal(source.snapshot()['cash_delta'])))
  return value
 monkeypatch.setattr(account_fixture,'body',body)
 try:yield o
 finally:source.close();economic.close()

def refreshed(o,pub,monkeypatch,*,market=True):
 p=launch((o,pub,None))
 for _ in range(10):pub.tick()
 proposal=call(pub,p,'account_propose');confirm(pub,p,proposal)
 fresh=capture=None
 if market:
  from test_paper_market_publication import command
  from test_paper_market_lineage_publication import drive
  if o.a._market._fresh_job is not None:command(o,'cancel',job_id=o.a._market._fresh_job)
  fresh,_=completed(o);capture=str(uuid4())
  command(o,'publish_lineage',capture_id=capture,job_id=fresh['job_id'],grant_sha256=fresh['grant_sha256']);drive(o,capture,'DONE')
 activity.__wrapped__((o,pub,p),monkeypatch)
 ap=activity_publication.__wrapped__((o,p),monkeypatch)
 with pages([canonical(o.close_source.snapshot()['inventory']['fills'])]) as (port,seen):
  o.activity_port=port;aid=pub_start(ap);finish(o,aid)
  for _ in range(12):ap[2].tick()
  assert o.a._activities._read(aid['activity_id'])['state']=='PUBLISHED'
 _,presence=acknowledge((o,pub,p))
 if market:o.a.input_context(subject='a'*64,packet_id=p['packet_id'],fresh_job_id=fresh['job_id'],capture_id=capture)
 return SimpleNamespace(packet=p,fresh=fresh,capture=capture,activity=aid,presence=presence)

@pytest.fixture
def held(seeded,confirmed,monkeypatch):
 from compertum.runtime import paper_fixture_economics as economics,paper_fixture_orders as orders,paper_fixture_reconciliation as reconciliation
 from test_native_attempt_records import records
 from compertum.runtime._winhttp_order import _wire
 o=seeded;source=o.close_source;economic=o.close_economic
 def economic_snapshot():return economic.snapshot(opening_sha256='0'*64,history_sha256='0'*64,until=stamp(o))
 for _ in range(2):
  p,d=records(o.a.lease);p['request']['body']['symbol']='MSFT';at=stamp(o)
  p['created_at']=p['request']['created_at']=at;p['expires_at']=utc((datetime.fromisoformat(at.replace('Z','+00:00'))+timedelta(seconds=60)).isoformat())
  method,target,_=_wire(p['request']['operation'],p['request']['parameters'],p['request']['body']);p['request'].update(method=method,target=target)
  p['request_sha256']=sha(p['request']);d['intent_sha256']=sha(p)
  with o.a.db:o.a.db.execute('BEGIN IMMEDIATE');o.fixture_orders.journal.consume(p,d,now=at)
  advance(o,1);source.execute(client_id=p['client_order_id'],operation=p['request']['operation'],parameters=p['request']['parameters'],body=p['request']['body'])
  with o.a.db:o.a.db.execute('BEGIN IMMEDIATE');o.fixture_orders.journal._observe_source(source.path.read_bytes(),economic_heads=(economic._genesis,),now=stamp(o))
 def source_snapshot(owner,context,base,originals):
  value=economic_snapshot()['ledger'];value.update(opening_sha256=base['opening']['sha256'],history_sha256=base['journal'])
  raw=source.path.read_bytes()
  def check():
   if source.path.read_bytes()!=raw:raise RuntimeRefused('SIMULATED_ORIGINAL_SOURCE_CHANGED')
  values=dict(originals=originals,ledger=value,opening_sha256=value['opening_sha256'],history_sha256=value['history_sha256'],
   asset_id=value['asset_id'],symbol=value['symbol'],required_after=value['covered_after'],required_until=value['covered_until'])
  return values,hashlib.sha256(canonical(values)).hexdigest(),check
 monkeypatch.setattr(economics,'_source_snapshot',source_snapshot)
 peer={'scope':'SIMULATED_SOURCE_PEER'}
 def original(*args):return None,{'order_source':{'journal_sha256':source.snapshot()['journal_sha256']}},{'port':44100,'peer':peer},None,None
 monkeypatch.setattr(orders,'_account_original',original);monkeypatch.setattr(reconciliation,'_account_original',original)
 monkeypatch.setattr(orders,'native_source_peer',lambda *args:peer)
 monkeypatch.setattr(orders,'source_file',lambda *args:(economic_snapshot(),[1,'a'*32]))
 monkeypatch.setattr(orders,'order_source_file',lambda *args:(source.snapshot(),[1,'b'*32]))
 monkeypatch.setattr(reconciliation,'source_file',lambda *args:(economic_snapshot(),[1,'a'*32]))
 monkeypatch.setattr(reconciliation,'_reserved_source_file',lambda *args:(source.path.read_bytes(),[1,'b'*32]))
 pub=confirmed[-1];current=refreshed(o,pub,monkeypatch)
 combined=(o,current.packet,current.fresh,current.capture,pub)
 _,intent=prepare_combined(combined,'CLOSE_LONG',terms=dict(symbol='MSFT',quantity=2,children=[dict(maximum_quantity=1,notional_cap='2000')]*2))
 confirm_intent(o,intent)
 return o,pub,current,intent

def test_accepted_parent_continues_after_start_expiry_with_fresh_proofs(held,monkeypatch):
 from compertum.runtime.paper_fixture_closing import accept_fixture_close
 from compertum.runtime.paper_fixture_reconciliation import reconcile_fixture_orders
 o,pub,current,intent=held;initial_current=current
 parent=accept_fixture_close(o.a,subject='a'*64,intent_id=intent['intent_id'],activity_id=current.activity['activity_id'])
 ids=[]
 for index in range(2):
  if index:
   serviced(o,61);current=refreshed(o,pub,monkeypatch)
  p=parent.prepare_child(subject='a'*64,packet_id=current.packet['packet_id'],fresh_job_id=current.fresh['job_id'],capture_id=current.capture,
   activity_id=current.activity['activity_id'],presence_id=current.presence['presence_id'])
  p._prepare();p._state='PENDING';p._call.commit(now=p._now());p._call.identity();ids.append(p._p['intent_id'])
  request=p._p['request'];advance(o,1)
  o.close_source.execute(client_id=p._p['client_order_id'],operation=request['operation'],parameters=request['parameters'],body=request['body']);p.close()
  current=refreshed(o,pub,monkeypatch,market=False)
  reconcile_fixture_orders(o.a,subject='a'*64,packet_id=current.packet['packet_id'],activity_id=current.activity['activity_id'],presence_id=current.presence['presence_id'])
  if index==1:current=refreshed(o,pub,monkeypatch,market=False)
 result=parent.finish(subject='a'*64,packet_id=current.packet['packet_id'],activity_id=current.activity['activity_id'],presence_id=current.presence['presence_id'])
 assert len(set(ids))==2 and verify_attempt_guard(o.close_project)['sequence']==4
 assert result['status']=='COMPLETE' and result['fixture_flat'] is True and result['transport_authorized'] is False
 with pytest.raises(RuntimeRefused,match='FIXTURE_CLOSING_STATE_CHANGED'):child(parent,initial_current)

def accepted(fixture):
 from compertum.runtime.paper_fixture_closing import accept_fixture_close
 o,pub,current,intent=fixture
 return accept_fixture_close(o.a,subject='a'*64,intent_id=intent['intent_id'],activity_id=current.activity['activity_id'])

def child(parent,current):
 return parent.prepare_child(subject='a'*64,packet_id=current.packet['packet_id'],fresh_job_id=current.fresh['job_id'],capture_id=current.capture,
  activity_id=current.activity['activity_id'],presence_id=current.presence['presence_id'])

def test_observed_parent_state_loss_stays_refused_after_row_repair(held):
 o,pub,current,intent=held;parent=accepted(held);raw=parent._state.decode()
 with o.a.db:o.a.db.execute('DELETE FROM state WHERE key=?',(parent._key,))
 with pytest.raises(RuntimeRefused):parent._records()
 with o.a.db:o.a.db.execute('INSERT INTO state VALUES(?,?)',(parent._key,raw))
 with pytest.raises(RuntimeRefused):parent._records()

def test_closing_parent_closes_its_ready_local_child(held):
 o,pub,current,intent=held;parent=accepted(held);p=child(parent,current)
 parent.close();assert p._closed and o.fixture_orders.active is None
 assert verify_attempt_guard(o.close_project)['sequence']==2

def test_child_source_binding_must_match_its_original_economic_context(held,monkeypatch):
 from compertum.runtime import paper_fixture_economics as module
 o,pub,current,intent=held;parent=accepted(held);flag=[False]
 source=module._source_snapshot;prepare=module._FixtureEconomicContext._prepare_proof
 def prepared(self):
  proof=prepare(self);flag[0]=True;return proof
 def changed(*args):
  values,binding,check=source(*args)
  if flag[0]:flag[0]=False;binding='f'*64
  return values,binding,check
 monkeypatch.setattr(module._FixtureEconomicContext,'_prepare_proof',prepared)
 monkeypatch.setattr(module,'_source_snapshot',changed)
 with pytest.raises(RuntimeRefused):child(parent,current)
 assert verify_attempt_guard(o.close_project)['sequence']==2

@pytest.mark.parametrize('fault',['confirmation','revocation','owner','deadline','duplicate','closed'])
def test_parent_refuses_changed_authority_and_deadline(held,fault):
 o,pub,current,intent=held;parent=accepted(held)
 if fault=='confirmation':
  with o.a.db:o.a.db.execute('DELETE FROM paper_native_confirmations WHERE intent_id=?',(intent['intent_id'],))
 elif fault=='revocation':o.a._intents._invalidate(parent._root,'OPERATOR_REVOKED')
 elif fault=='owner':o.a._intents.instance=str(uuid4())
 elif fault=='deadline':serviced(o,600)
 elif fault=='closed':parent.close()
 with pytest.raises(RuntimeRefused):
  if fault=='deadline':parent._age()
  elif fault=='duplicate':accepted(held)
  else:parent._records()
 assert verify_attempt_guard(o.close_project)['sequence']==2

def test_unresolved_native_child_cannot_create_another_child(held):
 o,pub,current,intent=held;parent=accepted(held);p=child(parent,current)
 p._prepare();p._state='PENDING';p._call.commit(now=p._now());key=p._p['intent_id'];p.close()
 with pytest.raises(RuntimeRefused):child(parent,current)
 assert verify_attempt_guard(o.close_project)['sequence']==3
 assert o.fixture_orders.journal.read('fixture',key)['status']=='NATIVE_CONSUMED'

def test_sql_failure_rolls_back_parent_but_preserves_external_consumption(held,monkeypatch):
 from compertum.native_write_journal import _NativeWriteJournal
 o,pub,current,intent=held;parent=accepted(held);before=parent._state.decode();p=child(parent,current)
 p._prepare();p._state='PENDING';key=p._p['intent_id']
 def fail(*args):raise RuntimeRefused('SIMULATED_AFTER_GUARD_APPEND')
 monkeypatch.setattr(_NativeWriteJournal,'_insert',fail)
 with pytest.raises(RuntimeRefused):p._call.commit(now=p._now())
 assert verify_attempt_guard(o.close_project)['sequence']==3
 assert o.a.db.execute('SELECT value FROM state WHERE key=?',(parent._key,)).fetchone()==(before,)
 assert o.a.db.execute('SELECT 1 FROM fake_intents WHERE intent_id=?',(key,)).fetchone() is None
 with pytest.raises(RuntimeRefused):parent._records()

def test_late_health_callback_cannot_replace_closing_child_target(held,monkeypatch):
 from compertum.runtime import paper_fixture_send_commit as module
 o,pub,current,intent=held;parent=accepted(held);before=parent._state
 p=child(parent,current);p._prepare();p._state='PENDING';key=p._p['intent_id'];health=module._health_live
 def changed(*args,**kwargs):
  result=health(*args,**kwargs)
  p._child._target=canonical(dict(json.loads(p._child._target),active=None))
  return result
 monkeypatch.setattr(module,'_health_live',changed)
 with pytest.raises(RuntimeRefused):p._call.commit(now=p._now())
 assert verify_attempt_guard(o.close_project)['sequence']==2
 assert o.a.db.execute('SELECT value FROM state WHERE key=?',(parent._key,)).fetchone()==(before.decode(),)
 assert o.a.db.execute('SELECT 1 FROM fake_intents WHERE intent_id=?',(key,)).fetchone() is None
