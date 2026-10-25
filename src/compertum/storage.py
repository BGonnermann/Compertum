"""Native allocation inventory, serialized grants and bounded artifact writers."""
import ctypes as c
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import time
from uuid import uuid4
from ._native_storage import Directory
from .config import _DEFAULTS
from .events import uuid,canonical
from .persistence import checked_path,open_store
from .runtime._windows import WindowsAPI,HANDLE,DWORD,BOOL
from .runtime.errors import RuntimeRefused
from .runtime.owners import _owner_scope,require_live_owner

GIB=1024**3
_GRANT_OWNERS={}
CAPS={key:_DEFAULTS['storage'][key+'_bytes'] for key in ('data','models','scratch','records','backups')}
TOTAL_CAP=_DEFAULTS['storage']['total_bytes']  # the project total; the 50 GiB free-space floor below is a separate rule
SCAN_SECONDS=_DEFAULTS['resources']['storage_scan_seconds']
INVENTORY_MAX_AGE=_DEFAULTS['resources']['project_monitor_seconds']

class IOStatus(c.Structure):
    _fields_=[('status',c.c_void_p),('information',c.c_size_t)]
class StandardInfo(c.Structure):
    _fields_=[('allocation',c.c_int64),('size',c.c_int64),('links',DWORD),('delete_pending',c.c_ubyte),('directory',c.c_ubyte)]


def category(path):
    part=Path(path).parts[0].lower()
    return {'data':'data','models':'models','.cache':'scratch','.venv':'scratch','.venv-repro':'scratch','backups':'backups'}.get(part,'records')


def _directory_rows(data):
    """Parse bounded FILE_FULL_DIR_INFORMATION rows before releasing path locks."""
    rows=[];offset=0
    while offset<len(data):
        if len(data)-offset<68:raise RuntimeRefused('STORAGE_SCAN_UNVERIFIED')
        row=struct.unpack_from('<IIqqqqqqIII',data,offset)
        step,_,_,_,_,_,length,allocated,attributes,name_length,_=row
        end=offset+68+name_length
        if (length<0 or allocated<0 or not name_length or name_length%2 or end>len(data)
                or step and (step%8 or step<68+name_length or offset+step>=len(data))
                or not step and len(data)-end>=8):raise RuntimeRefused('STORAGE_SCAN_UNVERIFIED')
        try:name=data[offset+68:end].decode('utf-16-le')
        except UnicodeError:raise RuntimeRefused('STORAGE_SCAN_UNVERIFIED') from None
        if name not in ('.','..'):rows.append((name,length,allocated,attributes))
        if not step:break
        offset+=step
    return rows


def iter_storage(project,*,volume_probe=None):
    """Complete native inventory in caller-thread batches; close to cancel."""
    started=time.monotonic();root=project.root_path;resolved_root=root.resolve()
    files={};totals=dict.fromkeys(CAPS,0);reparse=[]
    tasks=[(str(root),'',None)];buffer=c.create_string_buffer(65536)
    def deadline():
        if time.monotonic()-started>SCAN_SECONDS:raise RuntimeRefused('STORAGE_SCAN_DEADLINE')
    def probe():
        deadline()
        if volume_probe is not None:volume_probe()
        deadline()
    while tasks:
        probe()
        directory,prefix,inherited_category=tasks.pop()
        with Directory(directory,buffer) as handle:
            while True:
                probe();data=handle.read();deadline()
                if data is None:break
                for name,length,allocated,attributes in _directory_rows(data):
                    relative=prefix+name;file_category=inherited_category or category(name)
                    if attributes&0x400:
                        path=Path(directory)/name;target=path.resolve()
                        if not target.is_relative_to(resolved_root):raise RuntimeRefused('STORAGE_REPARSE_ESCAPE')
                        reparse.append(relative)
                    elif attributes&0x10:
                        tasks.append((os.path.join(directory,name),relative+'/',file_category));continue
                    charged=max(length,allocated)
                    files[relative]={'size':length,'allocated':allocated,'charged':charged}
                    totals[file_category]+=charged
                # All rows and linked targets are checked before yielding. The
                # directory remains locked until its final batch is consumed.
                yield None
        # Checked native closure is part of the complete scan deadline.
        probe()
        yield None
    free_bytes=shutil.disk_usage(root).free
    completed=time.monotonic()
    if completed-started>SCAN_SECONDS:raise RuntimeRefused('STORAGE_SCAN_DEADLINE')
    return {'project_id':project.project_id,'categories':totals,'total_bytes':sum(totals.values()),
            'free_bytes':free_bytes,'files':files,'reparse_paths':reparse,
            'started_monotonic':started,'completed_monotonic':completed,'scan_seconds':completed-started}


def sample_storage(project,*,volume_probe=None):
    """Drive the same complete inventory synchronously for fresh admission."""
    scan=iter_storage(project,volume_probe=volume_probe)
    try:
        while True:
            try:next(scan)
            except StopIteration as completed:return completed.value
    finally:scan.close()


@dataclass(frozen=True)
class StorageGrant:
    grant_id:str
    task_id:str
    category:str
    maximum:int


class StorageManager:
    def __init__(self,lease,config):
        require_live_owner(lease,'coordinator'); self.lease=lease; self.config=config; self._grants={};self.health_probe=None
        with _owner_scope(lease) as guard:
            self.project=guard.project; self.root=guard.project.root_path
            from .runtime.identity import resolve_project
            if resolve_project(config.project_root).project_id!=lease.project_id or any(config.storage_categories[k]>v for k,v in CAPS.items()) or config.storage_total_bytes>TOTAL_CAP:
                raise RuntimeRefused('STORAGE_POLICY_DENIED')
            self.store=open_store(lease,'coordinator')
            with self.store.conn:
                self.store.conn.execute('CREATE TABLE IF NOT EXISTS reservations(id TEXT PRIMARY KEY,task TEXT NOT NULL,category TEXT NOT NULL,maximum INTEGER NOT NULL,written INTEGER NOT NULL,status TEXT NOT NULL,path TEXT,manifest TEXT)')
                self.store.conn.execute("UPDATE reservations SET status='ABANDONED' WHERE status='OPEN'")
            self.observation()

    def observation(self):
        with _owner_scope(self.lease): return sample_storage(self.project,volume_probe=self.health_probe)

    def reservations(self):
        with self.store._live():
            return [dict(zip(('id','task','category','maximum','written','status','path','manifest'),row)) for row in self.store.conn.execute('SELECT * FROM reservations ORDER BY id')]

    def _capacity(self,category_name,amount,*,physical_bytes=None):
        observation=self.observation(); pending=dict.fromkeys(CAPS,0)
        rows=self.reservations()
        # Inventory already charges preallocated bytes. Credit each exact file
        # once, while retaining the unused allowance of every live/abandoned grant.
        physical={path.replace('\\','/'):value['charged'] for path,value in observation['files'].items()}
        for row in rows:
            if row['status']=='PUBLISHED' and row['path']:
                physical.pop(row['path'].replace('\\','/'),None)
        for row in rows:
            if row['status']=='PUBLISHED': continue
            remaining=max(0,row['maximum']-row['written']) if row['status']=='SPLIT' else row['maximum']
            allowance=((remaining+4095)//4096)*4096
            path=row['path'].replace('\\','/') if row['path'] else None
            credit=min(allowance,physical.pop(path,0)) if path else 0
            pending[row['category']]+=allowance-credit
        # Hold journal headroom even before its physical allocation.
        reserve=observation['files'].get('state/execution-reserve.bin',{}).get('charged',0)
        pending['records']+=max(0,GIB-reserve)
        pending[category_name]+=amount
        growth=amount if physical_bytes is None else physical_bytes
        if (observation['free_bytes']-growth<50*GIB or sum(observation['categories'].values())+sum(pending.values())>self.config.storage_total_bytes
                or any(observation['categories'][key]+pending[key]>self.config.storage_categories[key] for key in CAPS)):
            raise RuntimeRefused('STORAGE_CAPACITY')

    def reserve_bytes(self,task_id,category_name,maximum):
        uuid(task_id)
        if category_name not in CAPS or type(maximum) is not int or not 0<maximum<=2*GIB: raise RuntimeRefused('STORAGE_CAPACITY')
        with self.store._live(),self.store.conn:
            self._capacity(category_name,((maximum+4095)//4096)*4096)
            grant=StorageGrant(str(uuid4()),task_id,category_name,maximum)
            self.store.conn.execute('INSERT INTO reservations VALUES(?,?,?,?,0,\'RESERVED\',NULL,NULL)',(grant.grant_id,task_id,category_name,maximum))
            self._grants[grant.grant_id]=grant
            _GRANT_OWNERS[id(grant)]=(grant,self)
            return grant

    def split_grant(self,parent,maximum):
        with self.store._live(),self.store.conn:
            if not isinstance(parent,StorageGrant) or self._grants.get(parent.grant_id) is not parent:
                raise RuntimeRefused('GRANT_DENIED')
            row=self.store.conn.execute('SELECT maximum,written,status FROM reservations WHERE id=?',(parent.grant_id,)).fetchone()
            if not row or row[2] not in {'RESERVED','SPLIT'} or type(maximum) is not int or not 0<maximum<=row[0]-row[1]:
                raise RuntimeRefused('GRANT_BOUND_EXCEEDED')
            # A split may add a separately allocated file even when logical bytes fit.
            self._capacity(parent.category,4096)
            grant=StorageGrant(str(uuid4()),parent.task_id,parent.category,maximum)
            self.store.conn.execute("UPDATE reservations SET written=written+?,status='SPLIT' WHERE id=?",(maximum,parent.grant_id))
            self.store.conn.execute("INSERT INTO reservations VALUES(?,?,?,?,0,'RESERVED',NULL,NULL)",(grant.grant_id,grant.task_id,grant.category,maximum))
            self._grants[grant.grant_id]=grant;_GRANT_OWNERS[id(grant)]=(grant,self)
            return grant

    def checkpoint(self,grant,source,barrier_id,relative_path):
        with self.store._live(),self.store.conn:
            if self._grants.get(grant.grant_id) is not grant or grant.category!='backups' or source.lease.project_id!=self.lease.project_id:
                raise RuntimeRefused('GRANT_DENIED')
            row=self.store.conn.execute('SELECT status FROM reservations WHERE id=?',(grant.grant_id,)).fetchone()
            path=checked_path(self.root,self.root/relative_path)
            if not row or row[0]!='RESERVED' or not path.is_relative_to(self.root/'backups'/grant.task_id):
                raise RuntimeRefused('GRANT_DENIED')
            self._capacity('backups',0)
            self.store.conn.execute("UPDATE reservations SET status='OPEN',path=? WHERE id=?",(relative_path,grant.grant_id))
        # No SQLite transaction remains open while its backup API executes.
        receipt=source.checkpoint(barrier_id,path,maximum_bytes=grant.maximum)
        with self.store._live(),self.store.conn:
            self.store.conn.execute("UPDATE reservations SET status='PUBLISHED',written=?,manifest=? WHERE id=?",(receipt['size_bytes'],canonical(receipt).decode(),grant.grant_id))
        return receipt

    def open_artifact(self,grant,relative_path):
        with self.store._live():
            writer=None
            try:
                with self.store.conn:
                    if not isinstance(grant,StorageGrant) or self._grants.get(grant.grant_id) is not grant: raise RuntimeRefused('GRANT_DENIED')
                    row=self.store.conn.execute('SELECT status FROM reservations WHERE id=?',(grant.grant_id,)).fetchone()
                    if not row or row[0]!='RESERVED': raise RuntimeRefused('GRANT_DENIED')
                    path=checked_path(self.root,self.root/relative_path)
                    relative=path.relative_to(self.root).as_posix()
                    if category(relative)!=grant.category or grant.task_id not in path.parts or not relative.startswith(('artifacts/runs/','.cache/','backups/')):
                        raise RuntimeRefused('OUTPUT_DENIED')
                    if path.exists(): raise RuntimeRefused('OUTPUT_EXISTS')
                    writer=BoundedWriter(self,grant,path)
                    self.store.conn.execute("UPDATE reservations SET status='OPEN',path=? WHERE id=?",(str(writer.path.relative_to(self.root)),grant.grant_id))
                # Commit the path before native allocation becomes visible to
                # the independent monitor. Allocation leaves EOF at zero.
                writer._allocate();return writer
            except BaseException:
                if writer is not None: writer.close()
                raise


class BoundedWriter:
    def __init__(self,manager,grant,destination):
        self.manager=manager; self.grant=grant; self.destination=destination; self.written=0; self.manifest=None; self.closed=False
        destination.parent.mkdir(parents=True,exist_ok=True)
        checked_path(manager.root,destination)
        self.directories=[]
        with _owner_scope(manager.lease) as guard:
            current=manager.root
            try:
                for component in destination.parent.relative_to(current).parts:
                    current=current/component; self.directories.append(guard.api.open_directory(current))
                self.path=destination.with_name(destination.name+'.partial-'+grant.grant_id)
                self.stream=self.path.open('xb',buffering=0)
                guard.resources.append(self)
            except BaseException:
                for handle in reversed(self.directories): handle.close()
                raise

    def _allocate(self):
        import msvcrt
        with self.manager.store._live() as guard:
            self.manager._capacity(self.grant.category,0,physical_bytes=((self.grant.maximum+4095)//4096)*4096)
            handle=HANDLE(msvcrt.get_osfhandle(self.stream.fileno()));amount=c.c_int64(self.grant.maximum)
            guard.api.checked(guard.api.SetFileInformationByHandle(handle,5,c.byref(amount),c.sizeof(amount)),'ArtifactAllocation')
            value=StandardInfo()
            guard.api.checked(guard.api.GetFileInformationByHandleEx(handle,1,c.byref(value),c.sizeof(value)),'ArtifactAllocationRead')
            if value.size!=0 or not self.grant.maximum<=value.allocation<=((self.grant.maximum+4095)//4096)*4096:
                raise RuntimeRefused('ARTIFACT_ALLOCATION_UNVERIFIED')

    def write(self,chunk):
        with self.manager.store._live(),self.manager.store.conn:
            if self.closed or not isinstance(chunk,bytes) or len(chunk)>8*1024*1024 or self.written+len(chunk)>self.grant.maximum:
                raise RuntimeRefused('OUTPUT_BOUND_EXCEEDED')
            self.manager._capacity(self.grant.category,0)
            n=self.stream.write(chunk)
            if n!=len(chunk): raise RuntimeRefused('OUTPUT_WRITE_UNVERIFIED')
            self.stream.flush(); os.fsync(self.stream.fileno()); self.written+=n
            self.manager.store.conn.execute('UPDATE reservations SET written=? WHERE id=?',(self.written,self.grant.grant_id))
            return n

    def publish(self,*,before_publish=None):
        job=getattr(self,'_final_audit_job',None)
        if job is not None and not job.audit_lifetime.exit_verified:raise RuntimeRefused('JOB_EXIT_UNVERIFIED')
        if self.manifest is not None: return dict(self.manifest)
        with self.manager.store._live(),self.manager.store.conn:
            if self.closed: raise RuntimeRefused('WRITER_CLOSED')
            self.stream.flush(); os.fsync(self.stream.fileno()); self.stream.close()
            with self.path.open('rb') as stream: digest=hashlib.file_digest(stream,'sha256').hexdigest()
            if before_publish is not None:before_publish()
            self.path.rename(self.destination)
            self.manifest={'artifact_id':str(uuid4()),'path':self.destination.relative_to(self.manager.root).as_posix(),'size_bytes':self.written,'sha256':digest,'task_id':self.grant.task_id}
            self.manager.store.conn.execute("UPDATE reservations SET status='PUBLISHED',path=?,manifest=? WHERE id=?",(self.manifest['path'],canonical(self.manifest).decode(),self.grant.grant_id))
            self.closed=True
            for handle in reversed(self.directories): handle.close()
            return dict(self.manifest)

    def close(self):
        job=getattr(self,'_final_audit_job',None)
        if job is not None and not job.closed:raise RuntimeRefused('FINAL_AUDIT_CLEANUP_UNVERIFIED')
        if not self.closed:
            self.closed=True
            try: self.stream.close()
            finally:
                for handle in reversed(self.directories): handle.close()
            if not self.manager.store.closed:
                try:
                    with self.manager.store._live(),self.manager.store.conn:
                        self.manager.store.conn.execute("UPDATE reservations SET status='ABANDONED',path=COALESCE(path,?) WHERE id=?",(str(self.path.relative_to(self.manager.root)),self.grant.grant_id))
                except RuntimeRefused as error:
                    # Owner release revokes authority before resource disposal.
                    # The next owner recounts retained OPEN files as abandoned.
                    if error.code!='OWNER_UNVERIFIED': raise


class JournalReserve:
    def __init__(self,lease,api,handle,capacity):
        self.lease=lease;self.api=api;self.handle=handle;self.capacity=capacity;self.closed=False

    def receipt(self):
        require_live_owner(self.lease,'execution')
        value=StandardInfo()
        self.api.checked(self.api.GetFileInformationByHandleEx(self.handle.get(),1,c.byref(value),c.sizeof(value)),'ReserveAllocation')
        attributes=self.api.file_info(self.handle).attributes
        if attributes&(0x200|0x800) or value.allocation<value.size: raise RuntimeRefused('RESERVE_UNVERIFIED')
        return {'capacity_bytes':self.capacity,'unused_bytes':value.size,'allocated_bytes':value.allocation,'sparse':False}

    def release(self,amount,incident_id):
        unit=min(64*1024**2,self.capacity//16)
        if type(amount) is not int or amount!=unit: raise RuntimeRefused('RESERVE_RELEASE_DENIED')
        return self._resize('RELEASE',amount,incident_id)

    def refill(self,incident_id):
        return self._resize('REFILL',0,incident_id)

    def _resize(self,kind,amount,incident_id):
        uuid(incident_id)
        with _owner_scope(self.lease) as guard:
            require_live_owner(self.lease,'execution');store=open_store(self.lease,'execution')
            with store.conn:
                store.conn.execute('CREATE TABLE IF NOT EXISTS reserve_operations(id TEXT PRIMARY KEY,kind TEXT NOT NULL,amount INTEGER NOT NULL,before_bytes INTEGER NOT NULL,after_bytes INTEGER NOT NULL,status TEXT NOT NULL)')
            old=store.conn.execute('SELECT kind,amount,before_bytes,after_bytes,status FROM reserve_operations WHERE id=?',(incident_id,)).fetchone()
            unused=self.receipt()['unused_bytes']
            if old:
                if old[:2]!=(kind,amount): raise RuntimeRefused('RESERVE_OPERATION_CONFLICT')
                if old[4]=='APPLIED': return self.receipt()
                before,target=old[2:4]
            else:
                if store.conn.execute("SELECT 1 FROM reserve_operations WHERE status='PENDING'").fetchone():
                    raise RuntimeRefused('RESERVE_RECOVERY_REQUIRED')
                before=unused;target=unused-amount if kind=='RELEASE' else self.capacity
                if not 0<=target<=self.capacity: raise RuntimeRefused('RESERVE_RELEASE_DENIED')
                with store.conn:
                    store.conn.execute("INSERT INTO reserve_operations VALUES(?,?,?,?,?,'PENDING')",(incident_id,kind,amount,before,target))
            if kind=='RELEASE' and unused not in {before,target}: raise RuntimeRefused('RESERVE_RECOVERY_REQUIRED')
            if kind=='REFILL' and not before<=unused<=target: raise RuntimeRefused('RESERVE_RECOVERY_REQUIRED')
            kernel=c.WinDLL('kernel32',use_last_error=True)
            seek=kernel.SetFilePointerEx;seek.argtypes=[HANDLE,c.c_int64,c.POINTER(c.c_int64),DWORD];seek.restype=BOOL
            if kind=='RELEASE':
                end=kernel.SetEndOfFile;end.argtypes=[HANDLE];end.restype=BOOL
                self.api.checked(seek(self.handle.get(),target,None,0),'ReserveSeek')
                self.api.checked(end(self.handle.get()),'ReserveTruncate')
            else:
                observed=sample_storage(guard.project);growth=target-unused
                if (observed['free_bytes']-growth<50*GIB or observed['categories']['records']+growth>5*GIB
                        or observed['total_bytes']+growth>TOTAL_CAP): raise RuntimeRefused('STORAGE_CAPACITY')
                self.api.checked(seek(self.handle.get(),unused,None,0),'ReserveSeek')
                chunk=c.create_string_buffer(min(max(growth,1),8*1024**2))
                while growth:
                    count=min(growth,len(chunk));written=DWORD()
                    self.api.checked(self.api.WriteFile(self.handle.get(),chunk,count,c.byref(written),None),'ReserveRefill')
                    if written.value!=count: raise RuntimeRefused('RESERVE_UNVERIFIED')
                    growth-=count
            self.api.checked(self.api.FlushFileBuffers(self.handle.get()),'ReserveFlush')
            receipt=self.receipt()
            if receipt['unused_bytes']!=target: raise RuntimeRefused('RESERVE_UNVERIFIED')
            with store.conn: store.conn.execute("UPDATE reserve_operations SET status='APPLIED' WHERE id=?",(incident_id,))
            return receipt
    def close(self):
        if not self.closed: self.closed=True;self.handle.close()


def create_journal_reserve(lease,bytes=GIB):
    require_live_owner(lease,'execution')
    if type(bytes) is not int or not 65536<=bytes<=GIB: raise RuntimeRefused('RESERVE_SIZE_DENIED')
    with _owner_scope(lease) as guard:
        if shutil.disk_usage(guard.project.root_path).free-bytes<50*GIB: raise RuntimeRefused('STORAGE_CAPACITY')
        observed=sample_storage(guard.project)
        if observed['categories']['records']+bytes>5*GIB or observed['total_bytes']+bytes>TOTAL_CAP: raise RuntimeRefused('STORAGE_CAPACITY')
        path=checked_path(guard.project.root_path,guard.project.root_path/'state/execution-reserve.bin')
        handle=guard.api.open_file(path,0xC0000000,0,disposition=1)
        try:
            chunk=c.create_string_buffer(min(bytes,8*1024**2)); remaining=bytes
            while remaining:
                count=min(remaining,len(chunk)); written=DWORD()
                guard.api.checked(guard.api.WriteFile(handle.get(),chunk,count,c.byref(written),None),'ReserveWrite')
                if written.value!=count: raise RuntimeRefused('RESERVE_UNVERIFIED')
                remaining-=count
            guard.api.checked(guard.api.FlushFileBuffers(handle.get()),'ReserveFlush')
            reserve=JournalReserve(lease,guard.api,handle,bytes);reserve.receipt();guard.resources.append(reserve)
            return reserve
        except BaseException: handle.close();raise


def owner_of_grant(grant):
    pair=_GRANT_OWNERS.get(id(grant))
    if pair is None or pair[0] is not grant: raise RuntimeRefused('GRANT_DENIED')
    require_live_owner(pair[1].lease,'coordinator')
    return pair[1]


def open_journal_reserve(lease):
    require_live_owner(lease,'execution')
    with _owner_scope(lease) as guard:
        path=checked_path(guard.project.root_path,guard.project.root_path/'state/execution-reserve.bin')
        handle=guard.api.open_file(path,0xC0000000,0)
        try:
            reserve=JournalReserve(lease,guard.api,handle,GIB)
            if reserve.receipt()['unused_bytes']>GIB: raise RuntimeRefused('RESERVE_UNVERIFIED')
            guard.resources.append(reserve)
            return reserve
        except BaseException: handle.close();raise

def reserve_runtime_paths(manager):
    """Reserve bounded metadata/database growth before managed owners start."""
    task_id=str(uuid4())
    paths={}
    from .persistence import _active_store_path
    for role in ('coordinator','evaluation','execution'):
        name=_active_store_path(manager.root,manager.lease.project_id,role).relative_to(manager.root).as_posix()
        paths[name]=16*1024**2
        paths[name+'-wal']=16*1024**2
        paths[name+'-shm']=65536
    for role in ('supervisor','coordinator','evaluation','execution','watchdog','recovery'):
        paths[f'state/locks/{role}.json']=16384
        paths[f'state/locks/{role}.lock']=4096
    paths['state/watchdog/halt.json']=16384
    paths['state/evaluation-consumption/identity.json']=16384
    paths['state/evaluation-consumption/head.json']=16384
    paths['state/evaluation-seals/identity.json']=16384
    paths['state/evaluation-seals/head.json']=16384
    # Credential ciphertext is runtime-only: never a published backup artifact.
    paths['state/paper-credentials.bin']=16384  # target plus one <=8KiB staging file
    paths['state/fake-economic-opening.json']=8192
    paths['state/fake-broker/deterministic-broker.sqlite']=2*1024**2
    paths['state/fake-broker/deterministic-broker.sqlite-wal']=8*1024**2
    paths['state/fake-broker/deterministic-broker.sqlite-shm']=65536
    paths['state/fake-execution-attempts/identity.json']=16384
    paths['state/fake-execution-attempts/head.json']=16384
    for sequence in range(1,257):
        paths[f'state/fake-execution-attempts/{sequence:08d}.json']=65536
    # One owner lock, capacity observation and transaction admit the whole set.
    # No file producer starts until every exact path has a retained reservation.
    with manager.store._live(),manager.store.conn:
        missing=[]
        for path,maximum in paths.items():
            old=manager.store.conn.execute('SELECT maximum,status,category FROM reservations WHERE path=? LIMIT 2',(path,)).fetchall()
            if old:
                if old!=[(maximum,'RUNTIME','records')]:raise RuntimeRefused('RUNTIME_RESERVATION_MISMATCH')
            else:missing.append((path,maximum))
        manager._capacity('records',sum(((maximum+4095)//4096)*4096 for _,maximum in missing))
        for path,maximum in missing:
            row=(str(uuid4()),task_id,'records',maximum,0,'RUNTIME',path,None)
            changed=manager.store.conn.execute('INSERT INTO reservations VALUES(?,?,?,?,?,?,?,?)',row)
            actual=manager.store.conn.execute('SELECT * FROM reservations WHERE id=?', (row[0],)).fetchone()
            if changed.rowcount!=1 or actual!=row:raise RuntimeRefused('RUNTIME_RESERVATION_WRITE_UNVERIFIED')
    return paths



def adopt_fixture_bytes(writer,job):
    """Reconcile an admitted inherited sink only after its entire Job exits."""
    with writer.manager.store._live(),writer.manager.store.conn:
        if job.api.WaitForSingleObject(job.process.get(),0)!=0 or job.api.active(job.job):
            raise RuntimeRefused('JOB_EXIT_UNVERIFIED')
        size=writer.path.stat().st_size
        if size>writer.grant.maximum: raise RuntimeRefused('OUTPUT_BOUND_EXCEEDED')
        writer.written=size
        writer.manager.store.conn.execute('UPDATE reservations SET written=? WHERE id=?',(size,writer.grant.grant_id))
        return size


