"""Actual NTFS allocation may exceed EOF while an extending handle remains open."""
from uuid import uuid4
import pytest
from test_persistence import owned
from test_storage import manager
from compertum.runtime.errors import RuntimeRefused
from compertum.storage import reserve_runtime_paths
from compertum.watchdog import check_storage


def test_chunk_extension_stays_within_committed_physical_allowance(owned):
 store=manager(owned);reserve_runtime_paths(store);task=str(uuid4());maximum=10558162
 grant=store.reserve_bytes(task,'records',maximum);writer=store.open_artifact(grant,f'artifacts/runs/{task}/prepared.json')
 try:
  previous=store.observation();assert writer.path.stat().st_size==0
  for n in (8*1024**2,maximum-8*1024**2):
   writer.write(b'x'*n);observed=store.observation();value=observed['files'][writer.path.relative_to(store.root).as_posix()]
   assert value['allocated']<=((maximum+4095)//4096)*4096,value
   assert check_storage(observed,store.reservations(),previous=previous)['status']=='STORAGE_OBSERVED'
   previous=observed
  with pytest.raises(RuntimeRefused,match='OUTPUT_BOUND_EXCEEDED'):writer.write(b'x')
  result=writer.publish();assert result['size_bytes']==maximum
  assert (store.root/result['path']).read_bytes()==b'x'*maximum
 finally:writer.close()

def test_allocation_path_is_committed_before_disk_space_changes(owned,monkeypatch):
 import sqlite3
 from compertum.storage import BoundedWriter
 store=manager(owned);task=str(uuid4());grant=store.reserve_bytes(task,'records',8192);original=BoundedWriter._allocate;seen=[]
 def observed(writer):
  with sqlite3.connect((store.root/'state/research.sqlite').as_uri()+'?mode=ro',uri=True) as db:
   row=db.execute('SELECT status,path FROM reservations WHERE id=?',(grant.grant_id,)).fetchone()
  assert row==('OPEN',str(writer.path.relative_to(store.root)))
  seen.append(row);original(writer)
 monkeypatch.setattr(BoundedWriter,'_allocate',observed)
 writer=store.open_artifact(grant,f'artifacts/runs/{task}/committed.bin')
 try:assert len(seen)==1 and writer.path.stat().st_size==0
 finally:writer.close()


def test_failed_allocation_preserves_accounted_artifact_and_closes_handle(owned,monkeypatch):
 from compertum.storage import BoundedWriter
 from compertum.runtime._windows import WindowsAPI
 store=manager(owned);task=str(uuid4());grant=store.reserve_bytes(task,'records',8192);original=BoundedWriter._allocate;writers=[]
 def fail(writer):
  writers.append(writer);original(writer);raise RuntimeRefused('INJECTED_ALLOCATION_FAILURE')
 monkeypatch.setattr(BoundedWriter,'_allocate',fail)
 with pytest.raises(RuntimeRefused,match='INJECTED_ALLOCATION_FAILURE'):store.open_artifact(grant,f'artifacts/runs/{task}/failed.bin')
 writer=writers[0];assert writer.closed and writer.stream.closed and writer.path.exists()
 row=next(v for v in store.reservations() if v['id']==grant.grant_id)
 assert row['status']=='ABANDONED' and row['maximum']==8192 and row['written']==0
 with WindowsAPI().open_file(writer.path,0x40000000,0):pass


def test_preallocated_space_is_not_counted_twice_at_first_write(owned):
 from dataclasses import replace
 store=manager(owned);task=str(uuid4());maximum=1024**2;grant=store.reserve_bytes(task,'records',maximum)
 writer=store.open_artifact(grant,f'artifacts/runs/{task}/capacity.bin')
 try:
  current=store.observation()['categories']['records']
  store.config=replace(store.config,storage_categories={**store.config.storage_categories,'records':1024**3+current+maximum//2})
  writer.write(b'x');assert writer.written==1
 finally:writer.close()


def test_allocation_rechecks_free_space_after_the_grant_was_reserved(owned,monkeypatch):
 store=manager(owned);task=str(uuid4());grant=store.reserve_bytes(task,'records',8192);original=store.observation
 monkeypatch.setattr(store,'observation',lambda:{**original(),'free_bytes':50*1024**3+4096})
 with pytest.raises(RuntimeRefused,match='STORAGE_CAPACITY'):store.open_artifact(grant,f'artifacts/runs/{task}/late.bin')


def test_open_ledger_failure_closes_and_accounts_created_file(owned,monkeypatch):
 import sqlite3
 from compertum.storage import BoundedWriter
 store=manager(owned);task=str(uuid4());grant=store.reserve_bytes(task,'records',8192);original=BoundedWriter.__init__;writers=[]
 def capture(writer,*args):original(writer,*args);writers.append(writer)
 monkeypatch.setattr(BoundedWriter,'__init__',capture)
 with store.store.conn:
  store.store.conn.execute("CREATE TRIGGER refuse_open BEFORE UPDATE ON reservations WHEN NEW.status='OPEN' BEGIN SELECT RAISE(ABORT,'INJECTED_OPEN_FAILURE'); END")
 with pytest.raises(sqlite3.IntegrityError,match='INJECTED_OPEN_FAILURE'):store.open_artifact(grant,f'artifacts/runs/{task}/ledger-failure.bin')
 writer=writers[0];assert writer.closed and writer.stream.closed and all(h.closed for h in writer.directories)
 row=next(v for v in store.reservations() if v['id']==grant.grant_id)
 assert row['status']=='ABANDONED' and row['path']==str(writer.path.relative_to(store.root))
