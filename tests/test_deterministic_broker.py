"""Independent fixture accepts/fills/cancel races persist across reopen."""
import pytest
from compertum.domain import ExecutionIntent,ContractError
from compertum.deterministic_broker import DeterministicBroker,SimulatedTimeout
from compertum.execution_risk import client_order_id,snapshot_sha256
from compertum.domain import ExecutionObservation
from test_execution_risk import observation,intent


def request():
 o=observation();p=intent(o);p['snapshot_sha256']=snapshot_sha256(ExecutionObservation(o));return ExecutionIntent(p)


def test_accepted_lost_reply_and_delayed_lookup_survive_reopen(tmp_path):
 i=request();b=DeterministicBroker(tmp_path)
 with pytest.raises(SimulatedTimeout):b.submit(i,outcome='TIMEOUT_AFTER_ACCEPT',invisible_lookups=2)
 b.close();b=DeterministicBroker(tmp_path)
 try:
  assert b.lookup(client_order_id(i)) is None and b.lookup(client_order_id(i)) is None
  assert b.lookup(client_order_id(i))['status']=='ACKNOWLEDGED'
  s=b.snapshot();assert len(s['orders'])==1 and sum(v['kind']=='SUBMIT' for v in s['calls'])==1 and s['cash']=='10000' and s['positions']=={}
 finally:b.close()


def test_cancel_acceptance_does_not_cancel_and_intervening_fill_is_retained(tmp_path):
 b=DeterministicBroker(tmp_path)
 try:
  accepted=b.submit(request());identity=accepted['order_id'];b.fill(identity,4,'100')
  assert b.request_cancel(identity)['status']==204
  assert b.snapshot()['orders'][0]['status']=='PARTIALLY_FILLED'
  b.fill(identity,3,'101');closed=b.finish_cancel(identity)
  assert closed['status']=='CANCELED' and closed['filled_quantity']==7 and closed['filled_notional']=='703'
  s=b.snapshot();assert s['cash']=='9297' and s['positions']=={'AAPL':7}
  assert b.request_cancel(identity)['status']==422
  with pytest.raises(ContractError):b.fill(identity,1,'100')
 finally:b.close()


def test_fixture_identity_and_cash_never_change_on_duplicate_submit(tmp_path):
 b=DeterministicBroker(tmp_path);i=request()
 try:
  first=b.submit(i);assert b.submit(i)==first
  assert len(b.snapshot()['orders'])==1 and sum(c['kind']=='SUBMIT' for c in b.snapshot()['calls'])==2
  p=i.to_payload();p['quantity']=1
  with pytest.raises(ContractError,match='FAKE_CLIENT_ID_CONFLICT'):b.submit(ExecutionIntent(p))
  assert b.snapshot()['cash']=='10000'
 finally:b.close()


def test_realized_price_gap_is_evidence_and_not_clamped_to_pretrade_cap(tmp_path):
 b=DeterministicBroker(tmp_path,cash='5500',positions={'AAPL':45});i=request().to_payload();i['side']='sell'
 try:
  accepted=b.submit(ExecutionIntent(i));b.fill(accepted['order_id'],19,'110');s=b.snapshot()
  assert s['positions']=={'AAPL':26} and s['cash']=='7590' and s['orders'][0]['filled_notional']=='2090'
 finally:b.close()


def test_unknown_existing_database_is_preserved_before_any_schema_write(tmp_path):
 import sqlite3
 path=tmp_path/'deterministic-broker.sqlite'
 with sqlite3.connect(path) as db:db.execute('CREATE TABLE valuable(value TEXT)');db.execute("INSERT INTO valuable VALUES('preserve')")
 before=path.read_bytes()
 with pytest.raises(ContractError,match='FAKE_STORE_IDENTITY'):DeterministicBroker(tmp_path)
 assert path.read_bytes()==before


def test_wrong_account_and_nondecimal_input_are_refused(tmp_path):
 b=DeterministicBroker(tmp_path);b.close()
 with pytest.raises(ContractError,match='FAKE_STORE_IDENTITY'):DeterministicBroker(tmp_path,account='fake-other')
 with pytest.raises(ContractError,match='INVALID_FIXTURE_CASH'):DeterministicBroker(tmp_path/'invalid',cash=10000.0)
 assert not (tmp_path/'invalid').exists()


def test_invalid_fill_rolls_back_every_economic_effect(tmp_path):
 b=DeterministicBroker(tmp_path)
 try:
  accepted=b.submit(request());before=b.snapshot()
  with pytest.raises(ContractError):b.fill(accepted['order_id'],20,'100')
  assert b.snapshot()==before
  with pytest.raises(ContractError):b.fill(accepted['order_id'],1,100.0)
  assert b.snapshot()==before
 finally:b.close()


def test_attempt_that_was_never_accepted_stays_observable(tmp_path):
 b=DeterministicBroker(tmp_path);i=request()
 try:
  with pytest.raises(SimulatedTimeout):b.submit(i,outcome='TIMEOUT_BEFORE_ACCEPT')
  assert b.lookup(client_order_id(i)) is None
  s=b.snapshot();assert s['orders']==[] and sum(v['kind']=='SUBMIT' for v in s['calls'])==1
 finally:b.close()


def test_concurrent_fill_cannot_read_modify_write_from_stale_order(tmp_path):
 import sqlite3
 a=DeterministicBroker(tmp_path);b=DeterministicBroker(tmp_path)
 try:
  accepted=a.submit(request());identity=accepted['order_id'];original=a._order
  def interleave(order_id):
   value=original(order_id)
   with pytest.raises(sqlite3.OperationalError,match='locked'):b.fill(identity,4,'100')
   return value
  a._order=interleave;a.fill(identity,3,'100');a._order=original;b.fill(identity,4,'100')
  s=a.snapshot();assert s['cash']=='9300' and s['positions']=={'AAPL':7} and s['orders'][0]['filled_quantity']==7 and s['orders'][0]['filled_notional']=='700'
 finally:a.close();b.close()


def test_read_snapshot_cannot_mix_old_cash_with_new_positions(tmp_path):
 a=DeterministicBroker(tmp_path);b=DeterministicBroker(tmp_path)
 try:
  identity=a.submit(request())['order_id'];fired=[]
  def during_read(sql):
   if sql.startswith('SELECT symbol,quantity') and not fired:
    fired.append(True);b.fill(identity,4,'100')
  a.db.set_trace_callback(during_read);before=a.snapshot();a.db.set_trace_callback(None)
  assert fired and before['cash']=='10000' and before['positions']=={} and before['orders'][0]['filled_quantity']==0
  after=a.snapshot();assert after['cash']=='9600' and after['positions']=={'AAPL':4} and after['orders'][0]['filled_quantity']==4
 finally:a.close();b.close()


def test_existing_only_open_never_creates_missing_fixture(tmp_path):
    path=tmp_path/'missing'
    with pytest.raises(ContractError,match='FAKE_BROKER_MISSING'):DeterministicBroker(path,create=False)
    assert not path.exists()


def test_existing_only_open_preserves_account_and_effects(tmp_path):
    b=DeterministicBroker(tmp_path);i=request();accepted=b.submit(i);b.fill(accepted['order_id'],3,'100');before=b.snapshot();b.close()
    b=DeterministicBroker(tmp_path,create=False)
    try:assert b.snapshot()==before
    finally:b.close()


def test_existing_only_open_does_not_recreate_missing_broker_table(tmp_path):
    import sqlite3
    b=DeterministicBroker(tmp_path);b.close();path=tmp_path/'deterministic-broker.sqlite';db=sqlite3.connect(path)
    with db:db.execute('DROP TABLE orders')
    db.close()
    with pytest.raises(ContractError,match='FAKE_STORE_IDENTITY'):DeterministicBroker(tmp_path,create=False)
    db=sqlite3.connect(path)
    try:assert db.execute("SELECT name FROM sqlite_master WHERE name='orders'").fetchall()==[]
    finally:db.close()
