"""Local Windows named pipes. Kernel peers, scoped roles and duplicate receipts."""
from dataclasses import dataclass
import ctypes as C
from ctypes import wintypes as W
import json
import os
import secrets
import threading
import time
from . import win32 as w
from ..domain import canonical,digest,receipt,new_id

class SecurityAttributes(C.Structure):
    _fields_=[('length',W.DWORD),('descriptor',C.c_void_p),('inherit',W.BOOL)]
Security=w.bind(w.A,'ConvertStringSecurityDescriptorToSecurityDescriptorW',[W.LPCWSTR,W.DWORD,C.POINTER(C.c_void_p),C.POINTER(W.DWORD)],W.BOOL)
CreatePipe=w.bind(w.K,'CreateNamedPipeW',[W.LPCWSTR,W.DWORD,W.DWORD,W.DWORD,W.DWORD,W.DWORD,W.DWORD,C.POINTER(SecurityAttributes)],W.HANDLE)
Connect=w.bind(w.K,'ConnectNamedPipe',[W.HANDLE,C.c_void_p],W.BOOL)
Disconnect=w.bind(w.K,'DisconnectNamedPipe',[W.HANDLE],W.BOOL)
Read=w.bind(w.K,'ReadFile',[W.HANDLE,C.c_void_p,W.DWORD,C.POINTER(W.DWORD),C.c_void_p],W.BOOL)
Write=w.bind(w.K,'WriteFile',[W.HANDLE,C.c_void_p,W.DWORD,C.POINTER(W.DWORD),C.c_void_p],W.BOOL)
ClientPid=w.bind(w.K,'GetNamedPipeClientProcessId',[W.HANDLE,C.POINTER(W.ULONG)],W.BOOL)
ServerPid=w.bind(w.K,'GetNamedPipeServerProcessId',[W.HANDLE,C.POINTER(W.ULONG)],W.BOOL)
Flush=w.bind(w.K,'FlushFileBuffers',[W.HANDLE],W.BOOL)
OpenThread=w.bind(w.K,'OpenThread',[W.DWORD,W.BOOL,W.DWORD],W.HANDLE)
CancelSync=w.bind(w.K,'CancelSynchronousIo',[W.HANDLE],W.BOOL)
ThreadId=w.bind(w.K,'GetCurrentThreadId',[],W.DWORD)

def bounded_io(call,seconds=5):
    target=OpenThread(1,False,ThreadId())
    if not target:raise RuntimeError('IPC_DEADLINE_UNVERIFIED')
    timer=threading.Timer(seconds,lambda:CancelSync(target));timer.daemon=True;timer.start()
    try:return call()
    finally:timer.cancel();timer.join();w.CloseHandle(target)

@dataclass(frozen=True)
class RoleEndpoint:
    name:str
    generation:str
    process:dict
    role:str

def _send(handle,value):
    payload=canonical(value)
    if len(payload)>65536: raise ValueError('IPC_CAPACITY')
    done=W.DWORD()
    if not bounded_io(lambda:Write(handle,payload,len(payload),C.byref(done),None)) or done.value!=len(payload): raise w.error('IPC_WRITE_FAILED')
def _read(handle):
    buf=C.create_string_buffer(65536); done=W.DWORD()
    if not bounded_io(lambda:Read(handle,buf,len(buf),C.byref(done),None)): raise w.error('IPC_READ_FAILED')
    return json.loads(buf.raw[:done.value])

class RoleServer:
    def __init__(self,lease,allowed,handler,store=None):
        self.lease=lease; self.allowed=allowed; self.handler=handler; self.stop=threading.Event(); self.ready=threading.Event(); self.error=None
        self.store=store
        prefix=chr(92)*2+'.'+chr(92)+'pipe'+chr(92)+'cmp-'
        self.records={}; self.peers={}; self.endpoint=RoleEndpoint(prefix+lease.project.project_id[:16]+'-'+lease.generation,lease.generation,lease.process,lease.role)
        self.thread=threading.Thread(target=self._loop,daemon=True); self.thread.start()
        if not self.ready.wait(5) or self.error: raise RuntimeError('PIPE_START_UNVERIFIED')
    def register_peer(self,process,role,actions):
        token=secrets.token_hex(32)
        self.peers[token]={'process':process,'role':role,'actions':frozenset(actions)}
        return token
    def _authorize(self,handle,command):
        pid=W.ULONG()
        if not ClientPid(handle,C.byref(pid)): raise PermissionError('PEER_UNVERIFIED')
        peer=w.identity(pid.value)
        if peer['sid']!=self.lease.project.operator_sid: raise PermissionError('PEER_SID')
        if command.get('pid',pid.value)!=pid.value or command.get('generation')!=self.lease.generation: raise PermissionError('PEER_GENERATION')
        role=command.get('role','operator')
        if role=='operator':
            if command.get('capability'): raise PermissionError('WRITER_CAPABILITY_DENIED')
            return peer['sid'],self.allowed
        admitted=self.peers.get(command.get('capability',''))
        if not admitted or role!=admitted['role'] or peer!=admitted['process']: raise PermissionError('ROLE_UNVERIFIED')
        return digest({'peer':peer,'role':role}),admitted['actions']
    def _loop(self):
        descriptor=C.c_void_p(); size=W.DWORD()
        # Read/write data, attributes and EA; omit FILE_CREATE_PIPE_INSTANCE (4).
        sddl='D:P(A;;0x0012019b;;;'+self.lease.project.operator_sid+')(A;;GA;;;SY)'
        if not Security(sddl,1,C.byref(descriptor),C.byref(size)):
            self.error='DACL_UNVERIFIED'; self.ready.set(); return
        attrs=SecurityAttributes(C.sizeof(SecurityAttributes),descriptor,False)
        try:
            while not self.stop.is_set():
                handle=CreatePipe(self.endpoint.name,0x3|0x00080000,0x4|0x2|0x8,1,65536,65536,1000,C.byref(attrs))
                if handle==w.INVALID: self.error='PIPE_OWNER_UNVERIFIED'; self.ready.set(); return
                self.ready.set()
                try:
                    if not Connect(handle,None) and C.get_last_error()!=535: raise w.error('PIPE_CONNECT_FAILED')
                    if self.stop.is_set(): continue
                    command=_read(handle)
                    try:
                        self.lease.verify(); subject,allowed=self._authorize(handle,command)
                        action=command.get('action')
                        if action not in allowed: raise PermissionError('ACTION_DENIED')
                        rid=command.get('request_id') or new_id(); ph=digest({k:v for k,v in command.items() if k not in {'capability','pid','role','generation','request_id'}})
                        old=self.records.get(rid)
                        if old:
                            if old[:2]!=(subject,ph): raise PermissionError('REQUEST_ID_REUSE')
                            result=old[2]
                        else:
                            result=receipt(action,request_id=rid,generation=self.lease.generation)
                            callback=lambda:self.handler(command) if self.handler else {}
                            result['result']=self.store.request_once(rid,subject,self.lease.generation,{'hash':ph},callback) if self.store else callback()
                            self.records[rid]=(subject,ph,result)
                    except (PermissionError,ValueError) as exc:
                        result=receipt('denied','FAILED',3,type(exc).__name__,generation=self.lease.generation)
                    _send(handle,result); bounded_io(lambda:Flush(handle))
                except (OSError,ValueError) as exc:
                    self.error=type(exc).__name__
                finally: Disconnect(handle); w.CloseHandle(handle)
        finally: w.LocalFree(descriptor)
    def close(self):
        self.stop.set()
        try:
            handle=w.CreateFile(self.endpoint.name,0x00120003,0,None,3,0,None)
            if handle!=w.INVALID: w.CloseHandle(handle)
        except OSError: pass
        self.thread.join(5)
        if self.thread.is_alive(): raise RuntimeError('PIPE_SHUTDOWN_UNVERIFIED')

def start_role_pipe(lease,allowed_commands,handler=None,store=None): return RoleServer(lease,allowed_commands,handler,store)

def request(endpoint,command):
    deadline=time.monotonic()+5; handle=w.INVALID
    while time.monotonic()<deadline:
        handle=w.CreateFile(endpoint.name,0x00120003,0,None,3,0,None)
        if handle!=w.INVALID: break
        time.sleep(.02)
    if handle==w.INVALID: raise RuntimeError('PIPE_UNAVAILABLE')
    try:
        pid=W.ULONG()
        if not ServerPid(handle,C.byref(pid)) or w.identity(pid.value)!=endpoint.process: raise PermissionError('SERVER_IDENTITY_UNVERIFIED')
        _send(handle,{'generation':endpoint.generation,'role':'operator','pid':os.getpid(),**command})
        response=_read(handle)
        if response['generation']!=endpoint.generation: raise PermissionError('SERVER_GENERATION')
        return response
    finally: w.CloseHandle(handle)
