"""Private supervisor-owned adapters for acknowledged cross-process barriers."""
from contextlib import contextmanager
from dataclasses import dataclass
import sqlite3
from pathlib import Path
from .owner_channel import _remote_scope
from .owner_rpc import call_owner
from .errors import RuntimeRefused

@dataclass(frozen=True)
class RemoteLease:
    project_id:str
    generation:int
    identity:object

class RemoteStore:
    def __init__(self,remote,root):
        with _remote_scope(remote):
            registration=remote.descriptor.registration
            if registration.identity.role not in {'evaluation','execution'}: raise RuntimeRefused('RECOVERY_OWNERS_REQUIRED')
            self.remote=remote;self.role=registration.identity.role;self.root=root;self.conn=None;self.barrier=None
            self.lease=RemoteLease(registration.project_id,registration.generation,registration.identity)

    @contextmanager
    def _live(self):
        with _remote_scope(self.remote):
            try: yield
            finally:
                if self.barrier is not None:
                    try: call_owner(self.remote,'checkpoint',{'operation':'end','barrier_id':self.barrier})
                    finally: self.barrier=None
                if self.conn is not None: self.conn.close();self.conn=None

    def checkpoint(self,barrier_id,destination,*,maximum_bytes):
        result=call_owner(self.remote,'checkpoint',{'operation':'snapshot','barrier_id':barrier_id,
            'destination':Path(destination).relative_to(self.root).as_posix(),'maximum_bytes':maximum_bytes})
        if (result.get('barrier_id')!=barrier_id or result.get('role')!=self.role or result.get('project_id')!=self.lease.project_id
                or result.get('generation')!=self.lease.generation): raise RuntimeRefused('RECOVERY_OWNER_MISMATCH')
        self.barrier=barrier_id
        self.conn=sqlite3.connect(Path(destination).as_uri()+'?mode=ro',uri=True)
        return result

class RemoteReserve:
    def __init__(self,store): self.store=store;self.lease=store.lease
    def receipt(self):
        result=call_owner(self.store.remote,'status',{})
        if result.get('role')!='execution' or result.get('generation')!=self.lease.generation:
            raise RuntimeRefused('RESERVE_UNVERIFIED')
        return result['reserve']
