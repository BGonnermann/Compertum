"""Durable reservations, bounded sinks and separately measured volume use."""
from dataclasses import dataclass
import ctypes as C
from ctypes import wintypes as W
import json,os,shutil,time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from .domain import ContractError,GIB,within,new_id,now,file_hash,atomic_json
from .runtime import win32 as w

CAPS={'data':15*GIB,'models':5*GIB,'scratch':5*GIB,'records':5*GIB,'backups':20*GIB}
class StandardInfo(C.Structure):
    _fields_=[('allocation',C.c_int64),('end',C.c_int64),('links',W.DWORD),('delete_pending',C.c_ubyte),('directory',C.c_ubyte)]
FileEx=w.bind(w.K,'GetFileInformationByHandleEx',[W.HANDLE,C.c_int,C.c_void_p,W.DWORD],W.BOOL)

def allocated_size(path):
    h=w.CreateFile(str(path),0,7,None,3,0,None)
    if h==w.INVALID:raise w.error('ALLOCATION_UNVERIFIED')
    try:
        info=StandardInfo()
        if not FileEx(h,1,C.byref(info),C.sizeof(info)):raise w.error('ALLOCATION_UNVERIFIED')
        return max(info.allocation,info.end)
    finally:w.CloseHandle(h)

def category(path):
    parts=Path(path).parts
    if parts and parts[0]=='.cache':return 'scratch'
    if parts and parts[0]=='data':return 'data'
    if parts and parts[0]=='backups':return 'backups'
    if len(parts)>1 and parts[:2]==('artifacts','models'):return 'models'
    return 'records'

def sample_storage(root):
    root=Path(root).resolve();used={k:0 for k in CAPS};unexpected=[]
    reads=[]
    def collect(directory,parts=()):
        with os.scandir(directory) as entries:
            for entry in entries:
                st=entry.stat(follow_symlinks=False);relative=Path(*parts,entry.name)
                attrs=getattr(st,'st_file_attributes',0)
                if attrs&0x400:
                    known=(relative.parts[:2]==('.cache','uv') or (relative.parts[:2]==('.cache','test-runs') and entry.name.endswith('current'))) and Path(entry.path).resolve().is_relative_to(root)
                    if not known:unexpected.append(str(relative))
                    continue
                if attrs&0x10:collect(entry.path,(*parts,entry.name))
                elif relative.parts[:2]==('state','locks') and st.st_size==0:used[category(relative)]+=4096
                else:reads.append((relative,entry.path))
    collect(root)
    def measure(item):
        relative,path=item
        try:return category(relative),allocated_size(path)
        except OSError as exc:raise OSError(exc.errno,'ALLOCATION_UNVERIFIED:'+str(relative)) from None
    # Bounded native I/O concurrency; all allocations still measured, not mocked.
    with ThreadPoolExecutor(max_workers=4) as pool:
        for name,size in pool.map(measure,reads,buffersize=64):used[name]+=size
    return {'at':now(),'monotonic':time.monotonic(),'used':used,'total':sum(used.values()),'free_bytes':shutil.disk_usage(root).free,'unexpected_reparse':unexpected}

@dataclass(frozen=True)
class StorageGrant:
    grant_id:str
    task_id:str
    category:str
    maximum:int

class StorageManager:
    def __init__(self,store,free_floor=50*GIB,category_caps=None):
        self.store=store;self.root=store.lease.project.root_path;self.free_floor=free_floor;self.caps={**CAPS,**(category_caps or {})}
        if any(k not in CAPS or v<=0 or v>CAPS[k] for k,v in self.caps.items()):raise ContractError('STORAGE_CAP_INVALID')
        with store.transaction():store.db.execute('CREATE TABLE IF NOT EXISTS storage_grants(grant_id TEXT PRIMARY KEY,task_id TEXT,category TEXT,maximum INTEGER,reserved INTEGER,written INTEGER,state TEXT,path TEXT)')
    def reservations(self):
        with self.store.lock:
            rows=self.store.db.execute('SELECT grant_id,task_id,category,maximum,reserved,written,state,path FROM storage_grants ORDER BY rowid').fetchall()
        keys=('grant_id','task_id','category','maximum','reserved','written','state','path')
        return [dict(zip(keys,r)) for r in rows]
    def check_storage(self):
        observation=sample_storage(self.root);pending={k:0 for k in CAPS}
        for grant in self.reservations():
            if grant['state']!='PUBLISHED':pending[grant['category']]+=max(0,grant['reserved']-((grant['written']+4095)//4096)*4096)
        admitted=not observation['unexpected_reparse'] and observation['free_bytes']>=self.free_floor and all(observation['used'][k]+pending[k]<=self.caps[k] for k in CAPS) and observation['total']+sum(pending.values())<=50*GIB
        return {'admitted':admitted,'reason':'READY' if admitted else 'STORAGE_LIMIT','observation':observation,'pending':pending}
    def reserve_bytes(self,task_id,category_name,maximum):
        if category_name not in CAPS or type(maximum) is not int or not 0<maximum<=2*GIB:raise ContractError('RESERVATION_INVALID')
        amount=((maximum+4095)//4096)*4096
        with self.store.transaction():
            status=self.check_storage()
            if not status['admitted'] or status['observation']['used'][category_name]+status['pending'][category_name]+amount>self.caps[category_name] or status['observation']['total']+sum(status['pending'].values())+amount>50*GIB:raise ContractError('STORAGE_LIMIT')
            grant=StorageGrant(new_id(),task_id,category_name,maximum)
            self.store.db.execute('INSERT INTO storage_grants VALUES(?,?,?,?,?,0,?,NULL)',(grant.grant_id,task_id,category_name,maximum,amount,'RESERVED'))
            return grant
    def open_artifact(self,grant,relative_path):return BoundedWriter(self,grant,relative_path)

class BoundedWriter:
    def __init__(self,manager,grant,relative):
        self.manager=manager;self.grant=grant;self.target=within(manager.root,relative)
        if category(relative)!=grant.category:raise ContractError('GRANT_CATEGORY_MISMATCH')
        self.staging=self.target.with_name(self.target.name+'.part-'+grant.grant_id)
        with manager.store.transaction():
            row=manager.store.db.execute('SELECT state,maximum FROM storage_grants WHERE grant_id=?',(grant.grant_id,)).fetchone()
            if row!=('RESERVED',grant.maximum) or self.target.exists():raise ContractError('GRANT_OR_TARGET_INVALID')
            self.target.parent.mkdir(parents=True,exist_ok=True)
            self.file=self.staging.open('xb')
            manager.store.db.execute('UPDATE storage_grants SET state=?,path=? WHERE grant_id=?',('OPEN',str(self.staging.relative_to(manager.root)),grant.grant_id))
        self.closed=False;self.published=False;self.failed=False
    def write(self,chunk):
        if not isinstance(chunk,bytes) or len(chunk)>8*1024**2 or self.closed:raise ContractError('WRITE_CAPACITY')
        with self.manager.store.transaction():
            if not self.manager.check_storage()['admitted']:raise ContractError('WRITE_CAPACITY')
            row=self.manager.store.db.execute('SELECT maximum,written,state FROM storage_grants WHERE grant_id=?',(self.grant.grant_id,)).fetchone()
            if row[2]!='OPEN' or row[1]+len(chunk)>row[0] or shutil.disk_usage(self.manager.root).free<self.manager.free_floor:raise ContractError('WRITE_CAPACITY')
            try:self.file.write(chunk);self.file.flush();os.fsync(self.file.fileno())
            except OSError:
                self.failed=True;raise
            self.manager.store.db.execute('UPDATE storage_grants SET written=written+? WHERE grant_id=?',(len(chunk),self.grant.grant_id))
        return len(chunk)
    def close(self):
        if not self.closed:self.file.close();self.closed=True
    def publish(self):
        if self.failed:raise ContractError('ARTIFACT_UNFLUSHED')
        if self.published:raise ContractError('ALREADY_PUBLISHED')
        self.close()
        with self.manager.store.transaction():
            if self.target.exists():raise ContractError('TARGET_EXISTS')
            os.replace(self.staging,self.target)
            self.manager.store.db.execute('UPDATE storage_grants SET state=?,path=? WHERE grant_id=?',('PUBLISHED',str(self.target.relative_to(self.manager.root)),self.grant.grant_id))
        self.published=True
        return {'schema_version':1,'artifact_id':self.grant.grant_id,'task_id':self.grant.task_id,'path':str(self.target.relative_to(self.manager.root)),'sha256':file_hash(self.target),'bytes':self.target.stat().st_size,'at':now()}

def create_journal_reserve(lease,bytes=GIB):
    lease.verify()
    if lease.role!='execution' or not 0<bytes<=GIB:raise ContractError('RESERVE_OWNER_OR_SIZE')
    path=within(lease.project.root_path,'state/execution-reserve.bin')
    if path.exists():
        if path.stat().st_size!=bytes:raise ContractError('RESERVE_SIZE_MISMATCH')
    else:
        if shutil.disk_usage(path.parent).free<50*GIB+bytes:raise ContractError('RESERVE_SPACE_UNAVAILABLE')
        if sample_storage(lease.project.root_path)['used']['records']+bytes>CAPS['records']:raise ContractError('RESERVE_CATEGORY_LIMIT')
        with path.open('xb') as f:
            chunk=b'\0'*(8*1024**2);remaining=bytes
            while remaining:f.write(chunk[:min(len(chunk),remaining)]);remaining-=min(len(chunk),remaining)
            f.flush();os.fsync(f.fileno())
    if getattr(path.stat(),'st_file_attributes',0)&0x200 or allocated_size(path)<bytes:raise ContractError('RESERVE_ALLOCATION_UNVERIFIED')
    r={'bytes':bytes,'allocated_bytes':allocated_size(path),'verified':True,'synthetic_scaled':bytes!=GIB}
    atomic_json(path.with_suffix('.json'),r);return r

def release_journal_reserve(lease,bytes,incident_id):
    lease.verify()
    if lease.role!='execution' or bytes!=64*1024**2 or not incident_id:raise ContractError('RESERVE_RELEASE_DENIED')
    path=lease.project.root_path/'state/execution-reserve.bin';size=path.stat().st_size
    if size-bytes<256*1024**2:raise ContractError('JOURNAL_CAPACITY_UNAVAILABLE')
    with path.open('r+b') as f:f.truncate(size-bytes);f.flush();os.fsync(f.fileno())
    r={'bytes':size-bytes,'allocated_bytes':allocated_size(path),'verified':True,'incident_id':incident_id}
    atomic_json(path.with_suffix('.json'),r);return r

def refill_journal_reserve(lease,target_bytes=GIB):
    lease.verify()
    if lease.role!='execution' or not 256*1024**2<=target_bytes<=GIB:raise ContractError('RESERVE_OWNER_OR_SIZE')
    path=lease.project.root_path/'state/execution-reserve.bin';size=path.stat().st_size
    if size>target_bytes or shutil.disk_usage(path.parent).free<50*GIB+target_bytes-size:raise ContractError('RESERVE_REFILL_CAPACITY')
    if sample_storage(lease.project.root_path)['used']['records']+target_bytes-size>CAPS['records']:raise ContractError('RESERVE_CATEGORY_LIMIT')
    with path.open('ab') as f:
        chunk=b'\0'*(8*1024**2);remaining=target_bytes-size
        while remaining:
            amount=min(len(chunk),remaining);f.write(chunk[:amount]);remaining-=amount
        f.flush();os.fsync(f.fileno())
    result={'bytes':target_bytes,'allocated_bytes':allocated_size(path),'verified':allocated_size(path)>=target_bytes,'synthetic_scaled':target_bytes!=GIB}
    if not result['verified']:raise ContractError('RESERVE_ALLOCATION_UNVERIFIED')
    atomic_json(path.with_suffix('.json'),result);return result
