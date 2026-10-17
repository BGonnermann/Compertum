"""Native files and leases; remote transport and GiB reserve are simulated."""
from contextlib import contextmanager
from pathlib import Path
import sqlite3
from uuid import uuid4
import pytest
from test_persistence import owned

@pytest.mark.parametrize('roles',[('evaluation','execution'),('evaluation',),('execution',)])
def test_remote_snapshots_open_before_lineage_and_sharing_precedes_coordinator_snapshot(owned,monkeypatch,roles):
 import test_recovery_snapshot_closure as closure
 from compertum.runtime import recovery_adapter
 from compertum.storage import owner_of_grant
 from compertum.recovery import validate_recovery_set
 original=closure.collect_recovery_set;adapters=[]
 class SnapshotAdapter:
  def __init__(self,store):
   self.store=store;self.role=store.role;self.root=store.root;self.lease=store.lease;self.conn=None
  @contextmanager
  def _live(self):
   with self.store._live():
    try:yield
    finally:
     if self.conn is not None:self.conn.close();self.conn=None
  def checkpoint(self,barrier_id,destination,*,maximum_bytes):
   assert self.conn is None
   result=self.store.checkpoint(barrier_id,destination,maximum_bytes=maximum_bytes)
   self.conn=sqlite3.connect(Path(destination).as_uri()+'?mode=ro',uri=True)
   return result
 monkeypatch.setattr(recovery_adapter,'RemoteStore',SnapshotAdapter)
 def collect(project,stores,grant,**kwargs):
  manager=owner_of_grant(grant);wrapped=[]
  for store in stores:
   if store.role in roles:
    store=SnapshotAdapter(store);adapters.append(store)
   wrapped.append(store)
  larger=manager.reserve_bytes(str(uuid4()),'backups',40*1024**2)
  return original(project,wrapped,larger,**kwargs)
 monkeypatch.setattr(closure,'collect_recovery_set',collect)
 seals,_,artifact,collected=closure.prepared(owned)
 assert adapters and all(a.conn is None for a in adapters)
 root=owned[0].root_path;manifest=collected['manifest']
 assert validate_recovery_set(Path(collected['manifest_path']),project_root=root)['status']=='VERIFIED'
 shared=next(a for a in manifest['artifacts'] if a['artifact_id']==artifact['artifact_id'])
 coordinator=next(s for s in manifest['snapshots'] if s['owner_role']=='coordinator')
 with sqlite3.connect((root/coordinator['path']).as_uri()+'?mode=ro',uri=True) as db:
  assert db.execute('SELECT status FROM reservations WHERE path=?',(shared['path'],)).fetchone()==('PUBLISHED',)
