"""Actual native owners; small reserve simulated. Candidate only."""
import json,sys,hashlib
from pathlib import Path
from uuid import uuid4
sys.path.insert(0,str(Path.cwd()/'tests'))
import pytest
from test_execution_authority import authority
from test_execution_health import pair
from test_fake_execution_journal import checked_records,arguments
from test_execution_risk import NOW
from compertum.fake_execution_journal import FakeIntentJournal
from compertum.deterministic_broker import DeterministicBroker
from compertum.runtime.errors import RuntimeRefused
from compertum.fake_economic_opening import provision_opening,require_opening

@pytest.fixture
def opened(authority):
 store=authority[0].store;FakeIntentJournal(store)
 broker=DeterministicBroker(store.root/'state/fake-broker',cash='5500',positions={'AAPL':45})
 try:yield store,broker
 finally:broker.close()

def declare(store,broker):return provision_opening(store,broker,cash='5500',positions={'AAPL':45})

def test_declared_economics_are_fixed_before_effects(opened):
 store,b=opened;value=declare(store,b)
 assert require_opening(store,b)=={'account_alias':'fake-account','cash':'5500','positions':{'AAPL':45}}
 assert value['sha256']==hashlib.sha256((store.root/'state/fake-economic-opening.json').read_bytes()).hexdigest()
 with b.db:b.db.execute("UPDATE account SET cash='5500.02'")
 assert require_opening(store,b)['cash']=='5500'

@pytest.mark.parametrize('reason',['mismatch','call','order','attempt'])
def test_initial_declaration_refuses_changed_or_used_broker(opened,reason):
 store,b=opened;j=FakeIntentJournal(store);i,d=checked_records(store.lease)
 if reason=='mismatch':
  with b.db:b.db.execute("UPDATE account SET cash='5500.02'")
 elif reason=='call':b.lookup('unused-client')
 elif reason=='order':b.submit(i)
 else:j.record_checked(i,d);j.begin_attempt(*arguments(i),now=NOW)
 with pytest.raises(RuntimeRefused,match='FAKE_OPENING_UNVERIFIED'):declare(store,b)
 assert not (store.root/'state/fake-economic-opening.json').exists()
 assert store.get_state('fake_economic_opening') is None

def test_observation_does_not_initialize_missing_opening(opened):
 store,b=opened
 with pytest.raises(RuntimeRefused,match='FAKE_OPENING_UNVERIFIED'):require_opening(store,b)
 assert not (store.root/'state/fake-economic-opening.json').exists()

@pytest.mark.parametrize('change',['file','mirror','broker','missing_file','missing_mirror'])
def test_corrupt_or_missing_independent_pin_refuses(opened,change):
 store,b=opened;declare(store,b);path=store.root/'state/fake-economic-opening.json'
 if change=='file':path.write_text(path.read_text().replace('5500','5501'))
 elif change=='mirror':
  with store.conn:store.conn.execute("UPDATE state SET value=? WHERE key='fake_economic_opening'",(json.dumps({'sha256':'b'*64}),))
 elif change=='broker':
  with b.db:b.db.execute("UPDATE fixture_identity SET value=? WHERE key='opening_sha256'",('b'*64,))
 elif change=='missing_file':path.rename(path.with_name('preserved-opening.json'))
 else:
  with store.conn:store.conn.execute("DELETE FROM state WHERE key='fake_economic_opening'")
 with pytest.raises(RuntimeRefused,match='FAKE_OPENING_UNVERIFIED'):require_opening(store,b)

def test_exact_repeat_is_read_only_and_changed_declaration_refuses(opened):
 store,b=opened;first=declare(store,b);path=store.root/'state/fake-economic-opening.json';before=path.read_bytes()
 assert declare(store,b)==first and path.read_bytes()==before
 with pytest.raises(RuntimeRefused,match='FAKE_OPENING_UNVERIFIED'):provision_opening(store,b,cash='5501',positions={'AAPL':45})

def test_partial_provisioning_never_synthesizes_missing_pin(opened):
 store,b=opened;declare(store,b)
 with store.conn:store.conn.execute("DELETE FROM state WHERE key='fake_economic_opening'")
 with pytest.raises(RuntimeRefused,match='FAKE_OPENING_UNVERIFIED'):declare(store,b)
 assert store.get_state('fake_economic_opening') is None

def test_unfinished_caller_transaction_is_not_committed(opened):
 store,b=opened;store.conn.execute("INSERT INTO state VALUES('caller_pending','true')")
 try:
  with pytest.raises(RuntimeRefused,match='FAKE_OPENING_UNVERIFIED'):declare(store,b)
  assert store.conn.in_transaction
 finally:store.conn.rollback()
 assert store.get_state('caller_pending') is None

@pytest.mark.parametrize('spelling',['5500.00','5500.00000000'])
def test_equivalent_cash_spellings_have_one_canonical_opening(opened,spelling):
 store,b=opened
 first=provision_opening(store,b,cash=spelling,positions={'AAPL':45})
 assert require_opening(store,b)['cash']=='5500'
 assert provision_opening(store,b,cash='5500',positions={'AAPL':45})==first
 with pytest.raises(RuntimeRefused,match='FAKE_OPENING_UNVERIFIED'):provision_opening(store,b,cash='5500.01',positions={'AAPL':45})

@pytest.mark.parametrize('change',['large_cash','large_symbol','too_many_positions'])
def test_oversized_broker_rows_cannot_write_opening(opened,change):
 store,b=opened
 with b.db:
  if change=='large_cash':b.db.execute('UPDATE account SET cash=?',('9'*65536,))
  elif change=='large_symbol':b.db.execute('INSERT INTO positions VALUES(?,?)',('X'*65536,1))
  else:
   for a in 'ABCD':
    for z in 'ABCDEFGHIJKLMNOPQ':b.db.execute('INSERT INTO positions VALUES(?,?)',(a+z,1))
 with pytest.raises(RuntimeRefused,match='FAKE_OPENING_UNVERIFIED'):declare(store,b)
 assert not (store.root/'state/fake-economic-opening.json').exists()


@pytest.mark.parametrize('positive',[{}, {'MSFT':3}])
def test_zero_holdings_have_the_same_canonical_opening_as_absence(authority,positive):
 store=authority[0].store;FakeIntentJournal(store)
 b=DeterministicBroker(store.root/'state/fake-broker',cash='5500',positions={'AAPL':0,**positive})
 try:
  first=provision_opening(store,b,cash='5500',positions={'AAPL':0,**positive})
  assert require_opening(store,b)=={'account_alias':'fake-account','cash':'5500','positions':positive}
  assert provision_opening(store,b,cash='5500',positions=positive)==first
 finally:b.close()


def test_read_only_recovery_verification_closes_its_real_sqlite_connection(opened,monkeypatch):
 import sqlite3
 from compertum import fake_economic_opening as module
 from compertum.runtime.identity import resolve_project
 store,b=opened;declare(store,b);connections=[];connect=sqlite3.connect
 def tracked(*args,**kwargs):
  conn=connect(*args,**kwargs);connections.append(conn);return conn
 monkeypatch.setattr(module.sqlite3,'connect',tracked)
 try:
  assert module.verify_opening(resolve_project(store.root))['status']=='VERIFIED'
  assert len(connections)==1
  with pytest.raises(sqlite3.ProgrammingError):connections[0].execute('SELECT 1')
 finally:
  for conn in connections:conn.close()
