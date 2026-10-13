"""Native ledger admission for bounded deterministic fake files; no real effects."""
import sqlite3
import pytest
from compertum.runtime.errors import RuntimeRefused
from test_persistence import owned
from test_storage import manager,module


def test_runtime_reservations_use_one_capacity_scan_and_repeat_exactly(owned,monkeypatch):
    storage=manager(owned);calls=[];original=storage._capacity
    def counted(*args,**kwargs):
        calls.append((args,kwargs));return original(*args,**kwargs)
    monkeypatch.setattr(storage,'_capacity',counted)
    paths=module().reserve_runtime_paths(storage)
    assert len(calls)==1
    assert len(paths)==289
    assert paths['state/paper-credentials.bin']==16384
    assert paths['state/fake-economic-opening.json']==8192
    assert paths['state/fake-broker/deterministic-broker.sqlite']==2*1024**2
    assert paths['state/fake-broker/deterministic-broker.sqlite-wal']==8*1024**2
    assert paths['state/fake-broker/deterministic-broker.sqlite-shm']==65536
    assert paths['state/fake-execution-attempts/00000001.json']==65536
    assert paths['state/fake-execution-attempts/00000256.json']==65536
    before=storage.reservations()
    assert module().reserve_runtime_paths(storage)==paths
    assert storage.reservations()==before and len(calls)==2


def test_first_guard_and_fake_broker_writes_are_accounted(owned):
    from compertum.persistence import open_store
    from compertum.fake_execution_journal import FakeIntentJournal
    from compertum.deterministic_broker import DeterministicBroker
    from compertum.watchdog import check_storage
    from test_fake_execution_journal import checked_records,arguments
    from test_execution_risk import NOW
    project,leases=owned;storage=manager(owned)
    module().reserve_runtime_paths(storage);before=storage.observation()
    journal=FakeIntentJournal(open_store(leases['execution'],'execution'))
    intent,decision=checked_records(leases['execution']);journal.record_checked(intent,decision)
    assert journal.begin_attempt(*arguments(intent),now=NOW)['simulate_once']
    broker=DeterministicBroker(project.root_path/'state/fake-broker')
    try:
        broker.submit(intent)
        observed=storage.observation()
        assert check_storage(observed,storage.reservations(),previous=before)['status']=='STORAGE_OBSERVED'
        assert len(broker.snapshot()['orders'])==1
    finally:broker.close()


def test_batch_capacity_refusal_leaves_no_partial_reservations(owned,monkeypatch):
    storage=manager(owned);original=storage.observation
    def almost_full():
        observed=original();observed['categories']['records']=4*1024**3-105*1024**2
        observed['total_bytes']=sum(observed['categories'].values());return observed
    monkeypatch.setattr(storage,'observation',almost_full)
    with pytest.raises(RuntimeRefused,match='STORAGE_CAPACITY'):module().reserve_runtime_paths(storage)
    assert storage.reservations()==[]


@pytest.mark.parametrize('failure',['ABORT','IGNORE'])
def test_batch_write_failure_never_leaves_partial_admission(owned,failure):
    storage=manager(owned)
    action="RAISE(ABORT,'fixture')" if failure=='ABORT' else 'RAISE(IGNORE)'
    storage.store.conn.execute("CREATE TRIGGER refuse_runtime BEFORE INSERT ON reservations WHEN NEW.path='state/watchdog/halt.json' BEGIN SELECT "+action+"; END")
    with pytest.raises((RuntimeRefused,sqlite3.IntegrityError)):module().reserve_runtime_paths(storage)
    assert storage.reservations()==[]


@pytest.mark.parametrize('damage',['maximum','duplicate','status'])
def test_existing_runtime_admission_mismatch_refuses_without_growth(owned,damage):
    storage=manager(owned);module().reserve_runtime_paths(storage)
    with storage.store.conn:
        if damage=='maximum':storage.store.conn.execute("UPDATE reservations SET maximum=maximum+1 WHERE path='state/watchdog/halt.json'")
        elif damage=='status':storage.store.conn.execute("UPDATE reservations SET status='OPEN' WHERE path='state/watchdog/halt.json'")
        else:storage.store.conn.execute("INSERT INTO reservations SELECT 'duplicate',task,category,maximum,written,status,path,manifest FROM reservations WHERE path='state/watchdog/halt.json'")
    before=storage.reservations()
    with pytest.raises(RuntimeRefused,match='RUNTIME_RESERVATION_MISMATCH'):module().reserve_runtime_paths(storage)
    assert storage.reservations()==before