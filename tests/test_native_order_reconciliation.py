"""Backend accounting with real Windows stores and an explicitly unqualified local source."""
from datetime import datetime,timedelta
from types import SimpleNamespace
import sqlite3
import pytest
from compertum.data.encoding import canonical
from compertum.fake_attempt_guard import verify_attempt_guard
from compertum.runtime.errors import RuntimeRefused
from test_native_write_journal import journal,paper,native,records,AT,consume
from test_fixture_economics import example
from test_fixture_order_origin import origin
from test_fixture_order_journal import sha,changed

@pytest.fixture
def original(journal,tmp_path):
 from helpers.stateful_economic_fixture import ControlledEconomicSource
 from helpers.stateful_order_fixture import ControlledOrderSource
 project,lease,store,j=journal
 class Clock:
  value='2023-11-24T14:34:59Z'
  def __call__(self):return self.value
 clock=Clock();begin=origin();begin.update(project_id=project.project_id,created_at=clock())
 header=example()['ledger'];header.update(project_id=project.project_id,account_alias='fixture',asset_id=begin['asset_id'],symbol=begin['symbol'])
 economic=ControlledEconomicSource.create(tmp_path/'economic.jsonl',header,clock)
 begin.update(economic_producer_id=economic._producer,economic_genesis_sha256=economic._genesis)
 source=ControlledOrderSource.create(tmp_path/'orders.jsonl',begin,economic,clock,lambda:verify_attempt_guard(project),lambda:('99','100'))
 f=SimpleNamespace(project=project,lease=lease,store=store,j=j,source=source,economic=economic,clock=clock)
 try:yield f
 finally:source.close();economic.close()

def submitted(f,*,resting=False,cancel=None):
 p,d=records(f.lease,operation='SUBMIT_ORDER' if cancel is None else 'CANCEL_ORDER')
 if cancel is None:
  p['request']['body']['symbol']='MSFT'
  if resting:p['purpose']='FIXTURE_RESTING_BUY';p['request']['body'].update(type='limit',limit_price='80')
 else:p['request']['parameters']['order_id']=cancel
 from compertum.runtime._winhttp_order import _wire
 at=max(AT,f.clock());p['created_at']=p['request']['created_at']=at
 p['expires_at']=(datetime.fromisoformat(at.replace('Z','+00:00'))+timedelta(seconds=60)).isoformat().replace('+00:00','Z')
 method,target,_=_wire(p['request']['operation'],p['request']['parameters'],p['request']['body']);p['request'].update(method=method,target=target)
 p['request_sha256']=sha(p['request']);d['intent_sha256']=sha(p)
 with f.store.conn:
  f.store.conn.execute('BEGIN IMMEDIATE');assert f.j.consume(p,d,now=at)['first_consumption']
 f.clock.value=(datetime.fromisoformat(at.replace('Z','+00:00'))+timedelta(seconds=1)).isoformat().replace('+00:00','Z')
 return p,d

def execute(f,p):
 r=p['request'];return f.source.execute(client_id=p['client_order_id'],operation=r['operation'],parameters=r['parameters'],body=r['body'])

def observe(f,raw=None):
 raw=f.source.path.read_bytes() if raw is None else raw
 with f.store.conn:
  f.store.conn.execute('BEGIN IMMEDIATE')
  return f.j._observe_source(raw,economic_heads=(f.economic._genesis,),now=f.clock())

def test_complete_original_fill_resolves_consumption_without_another_send(original):
 f=original;p,d=submitted(f);execute(f,p);before=f.source.path.read_bytes();result=observe(f)
 row=f.j.read('fixture',p['intent_id']);assert row['status']=='NATIVE_FILLED' and row['filled_quantity']==1 and row['filled_notional']=='100'
 assert result['unresolved_count']==0 and result['financial_accepted'] is result['transport_authorized'] is False
 assert f.source.path.read_bytes()==before and verify_attempt_guard(f.project)['sequence']==1
 with f.store.conn:
  f.store.conn.execute('BEGIN IMMEDIATE');assert not f.j.consume(p,d,now=AT)['first_consumption']

def test_missing_order_never_establishes_absence_or_a_new_send(original):
 f=original;p,d=submitted(f);assert observe(f)['unresolved_count']==1
 assert f.j.read('fixture',p['intent_id'])['status']=='NATIVE_UNKNOWN'
 with pytest.raises(RuntimeRefused):submitted(f)
 assert verify_attempt_guard(f.project)['sequence']==1

def test_explicit_future_rejection_resolves_uncertainty_at_its_actual_time(original):
 f=original;p,d=submitted(f);observe(f);f.clock.value='2023-11-24T14:37:00Z'
 f.source.reject_unseen(client_id=p['client_order_id'],expected_heads=(f.economic._head,f.source.snapshot()['journal_sha256']))
 assert observe(f)['unresolved_count']==0 and f.j.read('fixture',p['intent_id'])['status']=='NATIVE_REJECTED'
 assert verify_attempt_guard(f.project)['sequence']==1

def test_cancel_reconciles_both_original_order_and_distinct_cancel_attempt(original):
 import json
 f=original;p,_=submitted(f,resting=True);_,raw=execute(f,p);target=json.loads(raw)['id'];observe(f)
 cancel,_=submitted(f,cancel=target);execute(f,cancel);assert observe(f)['unresolved_count']==0
 assert f.j.read('fixture',p['intent_id'])['status']=='NATIVE_CANCELED'
 assert f.j.read('fixture',cancel['intent_id'])['status']=='NATIVE_CANCELED'
 assert verify_attempt_guard(f.project)['sequence']==2

def test_older_database_recovery_still_requires_original_source_resolution(original,tmp_path):
 from compertum.native_write_journal import _NativeWriteJournal
 f=original;older=sqlite3.connect(tmp_path/'older.sqlite')
 try:
  f.store.conn.backup(older);p,d=submitted(f);execute(f,p);observe(f);older.backup(f.store.conn)
  f.j=_NativeWriteJournal(f.store,f.j.reserve);assert f.j.read('fixture',p['intent_id'])['status']=='NATIVE_UNKNOWN'
  assert observe(f)['unresolved_count']==0 and f.j.read('fixture',p['intent_id'])['status']=='NATIVE_FILLED'
  assert verify_attempt_guard(f.project)['sequence']==1
 finally:older.close()

@pytest.mark.parametrize('fault',['partial','foreign-record','future'])
def test_unverified_history_cannot_resolve_a_consumed_attempt(original,fault):
 f=original;p,d=submitted(f);execute(f,p);raw=f.source.path.read_bytes()
 if fault=='partial':raw=raw[:-1]
 elif fault=='future':f.clock.value=AT
 else:
  def change(tx):
   tx['attempt']['intent']['evidence_sha256']['risk']='f'*64
   tx['attempt']['decision']['intent_sha256']=sha(tx['attempt']['intent'])
  raw=changed(raw,change)
 with pytest.raises(RuntimeRefused):observe(f,raw)
 assert f.j.read('fixture',p['intent_id'])['status']=='NATIVE_CONSUMED'

def test_reconciliation_refuses_unrelated_trigger_changes(original):
 f=original;p,d=submitted(f);execute(f,p)
 with f.store.conn:f.store.conn.execute("CREATE TRIGGER change_around_native AFTER UPDATE ON fake_intents BEGIN INSERT INTO state VALUES('unrelated-change','true'); END")
 with pytest.raises(RuntimeRefused):observe(f)
 assert f.j.read('fixture',p['intent_id'])['status']=='NATIVE_CONSUMED'
 assert f.store.conn.execute("SELECT value FROM state WHERE key='unrelated-change'").fetchone() is None

def test_observed_source_history_cannot_be_replaced_with_a_rejection(original):
 f=original;p,d=submitted(f,resting=True);execute(f,p);observe(f)
 def replacement(tx):
  row=dict(tx['events'][0]['order'],status='rejected')
  tx['events']=[dict(tx['events'][0],kind='ORDER_REJECTED',order=row)]
 with pytest.raises(RuntimeRefused):observe(f,changed(f.source.path.read_bytes(),replacement))
 assert f.j.read('fixture',p['intent_id'])['status']=='NATIVE_ACKNOWLEDGED'

def test_observation_rechecks_external_guard_after_sql_events(original,monkeypatch):
 from compertum.fake_execution_journal import FakeIntentJournal
 f=original;p,d=submitted(f);execute(f,p);event=FakeIntentJournal._event
 def corrupt(journal,*args):
  event(journal,*args)
  (f.project.root_path/'state/fake-execution-attempts/head.json').write_bytes(b'{}')
 monkeypatch.setattr(FakeIntentJournal,'_event',corrupt)
 with pytest.raises(RuntimeRefused):observe(f)
 assert f.store.conn.execute('SELECT state FROM fake_intents WHERE intent_id=?',(p['intent_id'],)).fetchone()==('NATIVE_CONSUMED',)
