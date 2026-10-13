from dataclasses import dataclass
import json
import os
from .identity import resolve_project,ProjectIdentity
from . import win32 as w
from ..domain import atomic_json,new_id,now,within

class OwnerError(RuntimeError): pass

def verify_prior_exit(previous):
    try:
        actual=w.identity(previous['pid'])
    except OSError as exc:
        if exc.errno==87 and w.process_absent(previous['pid']): return {'kind':'VERIFIED_ABSENT','verified':True}
        raise OwnerError('OWNER_UNVERIFIED') from None
    if actual['creation_time']!=previous['creation_time']: return {'kind':'PID_REUSED','verified':True}
    if actual['exited']: return {'kind':'SIGNALED','verified':True}
    raise OwnerError('OWNER_BUSY_LIVE_INSTANCE')

@dataclass
class OwnerLease:
    project:ProjectIdentity
    role:str
    generation:str
    process_instance_id:str
    process:dict
    handle:int
    closed:bool=False
    def verify(self):
        if self.closed: raise OwnerError('OWNER_LEASE_CLOSED')
        if w.identity(os.getpid())!=self.process:raise OwnerError('OWNER_PROCESS_MISMATCH')
        info=w.FileInfo()
        if not w.GetFileInfo(self.handle,w.C.byref(info)):raise OwnerError('OWNER_HANDLE_UNVERIFIED')
        pathbuf=w.C.create_unicode_buffer(32768)
        if not w.GetPath(self.handle,pathbuf,len(pathbuf),0):raise OwnerError('OWNER_HANDLE_UNVERIFIED')
        final=pathbuf.value.removeprefix(chr(92)*2+'?'+chr(92))
        expected=str(self.project.root_path/'state/locks'/(self.role+'.lock'))
        if final.casefold()!=expected.casefold():raise OwnerError('OWNER_HANDLE_ROLE_MISMATCH')
        path=self.project.root_path/'state/runtime'/(self.role+'.json')
        data=json.loads(path.read_text())
        if data['generation']!=self.generation or data['process_instance_id']!=self.process_instance_id: raise OwnerError('OWNER_GENERATION_MISMATCH')
    def close(self):
        if not self.closed: w.CloseHandle(self.handle); self.closed=True
    def __enter__(self): self.verify(); return self
    def __exit__(self,*args): self.close()

def acquire_owner(project,role):
    if role not in {'supervisor','coordinator','evaluation','execution','watchdog','recovery'}: raise OwnerError('UNKNOWN_OWNER_ROLE')
    path=within(project.root_path,'state/locks/'+role+'.lock'); path.parent.mkdir(parents=True,exist_ok=True)
    handle=w.CreateFile(str(path),0xC0000000,0,None,4,0,None)
    if handle==w.INVALID: raise OwnerError('OWNER_BUSY_OR_UNVERIFIED')
    meta=within(project.root_path,'state/runtime/'+role+'.json')
    try:
        if meta.exists():
            previous=json.loads(meta.read_text())
            if previous['project_id']!=project.project_id: raise OwnerError('ROOT_IDENTITY_MISMATCH')
            verify_prior_exit(previous)
        process=w.identity(os.getpid()); instance=new_id(); generation=new_id()
        data={**process,'project_id':project.project_id,'role':role,'process_instance_id':instance,'generation':generation,'at':now()}
        atomic_json(meta,data)
        return OwnerLease(project,role,generation,instance,process,handle)
    except BaseException:
        w.CloseHandle(handle); raise
