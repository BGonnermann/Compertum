"""Section 19 sandbox: one Windows AppContainer and one Job Object for each Engineer job.

The AppContainer is the operating-system boundary. The process can read and write only the
folder this module grants to its own container identity. Windows gives every container
read access to Program Files, so the system interpreter runs without a grant.
Each job creates the container profile and deletes it when the job ends, so no file or registry
value in the container's own package storage survives from one job to the next. The profile name
is fixed, and Windows derives the container identity (SID) from the name, so the identity is the
same for every job. A firewall rule for that identity therefore covers every job. Because the
identity is the same, the grant on the job folder is revoked when the job ends, so a later job
cannot reach an earlier job folder.

The Job Object keeps the section 6 limits: process and job memory, one process, one CPU,
and the deadline. The environment holds three Windows variables and nothing else.

Before Engineer code runs, verify_sandbox runs a fixed probe in a fresh job and checks every
control. The owner authorized the AppContainer sandbox on 22 October 2026. This module
creates no firewall rule and makes no other security change.
"""
import ctypes as c
from dataclasses import dataclass
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
from uuid import uuid4
from ._windows import BOOL,DWORD,HANDLE,OwnedHandle
from .errors import RuntimeRefused
from .jobs import ExtendedLimits,JobAPI,ProcessInfo,SIZE,Startup,available_physical_memory

PROFILE_PREFIX='Compertum.Engine.Sandbox'
PROFILE_NAME=PROFILE_PREFIX
ENVIRONMENT=('SYSTEMROOT','WINDIR','LOCALAPPDATA')
OUTPUT_BYTES=65536
MIN_SECONDS,MAX_SECONDS=1,3600
MIN_MEMORY,MAX_MEMORY=64*1024**2,8*1024**3
MAX_DISK=1024**3
FILE_MODIFY=0x1301BF  # generic read, write, execute and delete; no WRITE_DAC or WRITE_OWNER
REPARSE_POINT=0x400
OUT_OF_MEMORY_EXITS=(0xC0000017,0xC000012D)
CONTROLS=('appcontainer_token','low_integrity','external_network_denied',
          'outside_read_denied','outside_write_denied','outside_file_absent','previous_job_read_denied','inside_write_allowed',
          'child_process_denied','memory_limit_enforced','fixed_targets_read_denied','pipe_open_denied')
MAX_FIXED_TARGETS=16
# Loopback is observed, not gated. On this host (Windows 11 10.0.26300) a capability-less AppContainer reaches a loopback listener.
# The owner accepted this as a documented limitation on 23 October 2026 (option 1 in docs/ENGINE_PLAN.md, "Loopback finding").
# The engine records the observation with every verification; stage E3 adds the compensating connection check.
OBSERVATIONS=('loopback_connected','loopback_seen_by_listener')


class TRUSTEE(c.Structure):
    _fields_=[('multiple',HANDLE),('operation',c.c_int),('form',c.c_int),('type',c.c_int),('name',HANDLE)]
class EXPLICIT_ACCESS(c.Structure):
    _fields_=[('permissions',DWORD),('mode',c.c_int),('inheritance',DWORD),('trustee',TRUSTEE)]
class SECURITY_CAPABILITIES(c.Structure):
    _fields_=[('sid',HANDLE),('capabilities',HANDLE),('count',DWORD),('reserved',DWORD)]
class StartupEx(c.Structure):
    _fields_=[('base',Startup),('attributes',HANDLE)]


class SandboxAPI(JobAPI):
    def __init__(self):
        super().__init__()
        userenv=c.WinDLL('userenv',use_last_error=True);advapi=c.WinDLL('advapi32',use_last_error=True);kernel=c.WinDLL('kernel32',use_last_error=True)
        def bind(dll,name,result,*args):
            fn=getattr(dll,name);fn.restype=result;fn.argtypes=list(args);setattr(self,name,fn)
        bind(userenv,'CreateAppContainerProfile',c.c_long,c.c_wchar_p,c.c_wchar_p,c.c_wchar_p,HANDLE,DWORD,c.POINTER(HANDLE))
        bind(userenv,'DeleteAppContainerProfile',c.c_long,c.c_wchar_p)
        bind(advapi,'FreeSid',HANDLE,HANDLE)
        bind(advapi,'GetNamedSecurityInfoW',DWORD,c.c_wchar_p,c.c_int,DWORD,c.POINTER(HANDLE),c.POINTER(HANDLE),c.POINTER(HANDLE),c.POINTER(HANDLE),c.POINTER(HANDLE))
        bind(advapi,'SetNamedSecurityInfoW',DWORD,c.c_wchar_p,c.c_int,DWORD,HANDLE,HANDLE,HANDLE,HANDLE)
        bind(advapi,'SetEntriesInAclW',DWORD,c.c_ulong,c.POINTER(EXPLICIT_ACCESS),HANDLE,c.POINTER(HANDLE))
        bind(advapi,'GetEffectiveRightsFromAclW',DWORD,HANDLE,c.POINTER(TRUSTEE),c.POINTER(DWORD))
        bind(kernel,'InitializeProcThreadAttributeList',BOOL,HANDLE,DWORD,DWORD,c.POINTER(SIZE))
        bind(kernel,'UpdateProcThreadAttribute',BOOL,HANDLE,DWORD,SIZE,HANDLE,SIZE,HANDLE,HANDLE)
        bind(kernel,'DeleteProcThreadAttributeList',None,HANDLE)

    def status(self,error,operation):
        if error: raise RuntimeRefused(f'NATIVE_CALL_FAILED:{operation}:{error}')


class Profile:
    """One AppContainer identity. It exists only between __init__ and close()."""
    def __init__(self,api,name):
        if type(name) is not str or not name.startswith(PROFILE_PREFIX) or not 1<=len(name)<=64 or not name.replace('.','').replace('-','').isalnum():
            raise RuntimeRefused('SANDBOX_PROFILE_NAME_DENIED')
        self.api=api;self.name=name;self.sid=None;self.folder=packages_folder()/name
        if self.folder.exists(): raise RuntimeRefused('SANDBOX_PROFILE_EXISTS')
        sid=HANDLE();result=api.CreateAppContainerProfile(name,name,'Compertum section 19 sandbox job',None,0,c.byref(sid))
        if result&0xFFFFFFFF==0x800700B7: raise RuntimeRefused('SANDBOX_PROFILE_EXISTS')
        if result<0 or not sid.value: raise RuntimeRefused(f'NATIVE_CALL_FAILED:CreateAppContainerProfile:{result&0xFFFFFFFF:08x}')
        self.sid=sid.value
        try: self.sid_string=api._sid_string(self.sid)
        except BaseException:
            self.close();raise

    def _apply(self,folder,permissions,mode):
        api=self.api;old=HANDLE();descriptor=HANDLE()
        api.status(api.GetNamedSecurityInfoW(str(folder),1,4,None,None,c.byref(old),None,c.byref(descriptor)),'GetNamedSecurityInfoW')
        try:
            access=EXPLICIT_ACCESS(permissions,mode,3,TRUSTEE(None,0,0,0,self.sid));new=HANDLE()
            api.status(api.SetEntriesInAclW(1,c.byref(access),old,c.byref(new)),'SetEntriesInAclW')
            try:
                api.status(api.SetNamedSecurityInfoW(str(folder),1,4,None,None,new,None),'SetNamedSecurityInfoW')
                rights=DWORD();api.status(api.GetEffectiveRightsFromAclW(new,c.byref(access.trustee),c.byref(rights)),'GetEffectiveRightsFromAclW')
                return rights.value
            finally: api.LocalFree(new)
        finally: api.LocalFree(descriptor)

    def grant(self,folder,permissions=FILE_MODIFY):
        """Add one inheritable allow entry for this container to folder, keeping the existing entries."""
        if self._apply(folder,permissions,1)&permissions!=permissions: raise RuntimeRefused('SANDBOX_GRANT_UNVERIFIED')

    def revoke(self,folder):
        """Remove every entry for this container from folder. The identity is shared by all jobs, so this must hold."""
        if self._apply(folder,0,4)!=0: raise RuntimeRefused('SANDBOX_REVOKE_UNVERIFIED')

    def close(self):
        """Delete the profile and its package folder. A retained folder is refused, never ignored."""
        if self.sid is not None: self.api.FreeSid(self.sid);self.sid=None
        result=self.api.DeleteAppContainerProfile(self.name)
        if result<0 or self.folder.exists(): raise RuntimeRefused('SANDBOX_PROFILE_RETAINED')


def packages_folder():
    local=os.environ.get('LOCALAPPDATA')
    if not local: raise RuntimeRefused('SANDBOX_ENVIRONMENT_UNAVAILABLE')
    return Path(local)/'Packages'


def stale_profiles():
    """Lowercase names of sandbox profiles left behind by an interrupted job. Removal is a separate, recorded step.

    Windows stores the package folder under the lowercase profile name.
    """
    folder=packages_folder();prefix=PROFILE_PREFIX.lower()
    return sorted(p.name.lower() for p in folder.iterdir() if p.is_dir() and p.name.lower().startswith(prefix)) if folder.is_dir() else []


def remove_stale_profile(api,name):
    """Remove one stale profile by name. The fixed name is always allowed, because a registry entry can outlive its folder."""
    if type(name) is not str or (name.lower() not in stale_profiles() and name.lower()!=PROFILE_NAME.lower()): raise RuntimeRefused('SANDBOX_PROFILE_UNKNOWN')
    had_folder=(packages_folder()/name).exists()
    result=api.DeleteAppContainerProfile(name)
    if result<0 and not had_folder: raise RuntimeRefused('SANDBOX_PROFILE_UNKNOWN')
    if result<0 or (packages_folder()/name).exists(): raise RuntimeRefused('SANDBOX_PROFILE_RETAINED')


def folder_bytes(folder,limit=MAX_DISK):
    """Sum regular file sizes below folder without following any reparse point. The folder may be hostile."""
    total=0;pending=[Path(folder)]
    while pending:
        current=pending.pop()
        try: entries=list(os.scandir(current))
        except OSError: continue
        for entry in entries:
            try:
                info=entry.stat(follow_symlinks=False)
                if getattr(info,'st_file_attributes',0)&REPARSE_POINT or entry.is_symlink(): continue
                if entry.is_dir(follow_symlinks=False): pending.append(Path(entry.path))
                elif entry.is_file(follow_symlinks=False): total+=info.st_size
            except OSError: continue
            if total>limit: return total
    return total


def read_head(path,limit=OUTPUT_BYTES):
    try:
        with open(path,'rb') as stream: return stream.read(limit)
    except OSError: return b''


@dataclass(frozen=True)
class SandboxResult:
    job_id:str
    sid:str
    pid:int
    exit_code:int
    timed_out:bool
    elapsed_seconds:float
    peak_process_bytes:int
    job_folder_bytes:int
    package_folder_bytes:int
    disk_overrun:bool
    stdout:bytes
    stderr:bytes

    def record(self):
        return {'job_id':self.job_id,'sid':self.sid,'pid':self.pid,'exit_code':self.exit_code,'timed_out':self.timed_out,
                'elapsed_seconds':round(self.elapsed_seconds,3),'peak_process_bytes':self.peak_process_bytes,'job_folder_bytes':self.job_folder_bytes,
                'package_folder_bytes':self.package_folder_bytes,'disk_overrun':self.disk_overrun,'stdout_bytes':len(self.stdout),'stderr_bytes':len(self.stderr)}


def _job_folder(root,job_dir):
    try: root=Path(root).resolve(strict=True);job=Path(job_dir).resolve(strict=True)
    except OSError: raise RuntimeRefused('SANDBOX_FOLDER_DENIED') from None
    try: relative=job.relative_to(root)
    except ValueError: raise RuntimeRefused('SANDBOX_FOLDER_DENIED') from None
    info=job.lstat()
    if len(relative.parts)!=1 or not job.is_dir() or job.is_symlink() or getattr(info,'st_file_attributes',0)&REPARSE_POINT: raise RuntimeRefused('SANDBOX_FOLDER_DENIED')
    return job


def _argv(job,argv):
    """The first argument names one .py file in the job folder. No argument is absolute or climbs out."""
    if (type(argv) is not list or not 1<=len(argv)<=64 or any(type(a) is not str or not 1<=len(a)<=1024 or '\0' in a for a in argv)
            or any(Path(a).is_absolute() or '..' in Path(a).parts for a in argv)): raise RuntimeRefused('SANDBOX_ARGV_DENIED')
    script=Path(argv[0])
    if len(script.parts)!=1 or script.suffix!='.py' or not (job/script).is_file() or (job/script).is_symlink(): raise RuntimeRefused('SANDBOX_ARGV_DENIED')
    return list(argv)


def _bounded(value,low,high,code):
    if type(value) is not int or not low<=value<=high: raise RuntimeRefused(code)
    return value


class TcpRow4(c.Structure):
    _fields_=[('state',DWORD),('local_addr',DWORD),('local_port',DWORD),('remote_addr',DWORD),('remote_port',DWORD),('pid',DWORD)]


class TcpRow6(c.Structure):
    _fields_=[('local_addr',c.c_ubyte*16),('local_scope',DWORD),('local_port',DWORD),('remote_addr',c.c_ubyte*16),('remote_scope',DWORD),
              ('remote_port',DWORD),('state',DWORD),('pid',DWORD)]


class LoopbackWatcher:
    """Sample the Windows TCP table while a sandbox process runs and keep every row that the process owns.

    This is the compensating control for loopback reach (docs/ENGINE_PLAN.md, "Loopback finding"). A connection shorter than one
    sample interval can be missed, so a clean record is evidence, not proof. A failed sample makes the watcher unverified.
    """
    def __init__(self,interval=.025):
        self.interval=_bounded(int(interval*1000),1,1000,'SANDBOX_WATCHER_DENIED')/1000
        self.pid=None;self.samples=0;self.error=None;self.connections={};self._stop=threading.Event();self._thread=None
        self._iphlpapi=c.WinDLL('iphlpapi',use_last_error=True)
        self._iphlpapi.GetExtendedTcpTable.argtypes=[c.c_void_p,c.POINTER(DWORD),BOOL,c.c_ulong,c.c_int,c.c_ulong]
        self._iphlpapi.GetExtendedTcpTable.restype=DWORD

    def _table(self,family,row_type):
        size=DWORD(0)
        for _ in range(4):
            buffer=c.create_string_buffer(max(size.value,4))
            status=self._iphlpapi.GetExtendedTcpTable(buffer,c.byref(size),False,family,5,0)  # TCP_TABLE_OWNER_PID_ALL
            if status==0:
                count=DWORD.from_buffer(buffer).value
                return (row_type*count).from_buffer(buffer,4)
            if status!=122: raise OSError(status,'GetExtendedTcpTable')  # ERROR_INSUFFICIENT_BUFFER
        raise OSError(122,'GetExtendedTcpTable')

    def sample(self):
        rows=[]
        for row in self._table(2,TcpRow4):
            if row.pid==self.pid:
                rows.append(('ipv4',socket.inet_ntoa(row.local_addr.to_bytes(4,'little')),socket.ntohs(row.local_port&0xFFFF),
                             socket.inet_ntoa(row.remote_addr.to_bytes(4,'little')),socket.ntohs(row.remote_port&0xFFFF),row.state))
        for row in self._table(23,TcpRow6):
            if row.pid==self.pid:
                rows.append(('ipv6',socket.inet_ntop(socket.AF_INET6,bytes(row.local_addr)),socket.ntohs(row.local_port&0xFFFF),
                             socket.inet_ntop(socket.AF_INET6,bytes(row.remote_addr)),socket.ntohs(row.remote_port&0xFFFF),row.state))
        self.samples+=1
        for family,local,lport,remote,rport,state in rows:
            key=(family,local,lport,remote,rport);entry=self.connections.get(key)
            if entry is None: self.connections[key]={'family':family,'local_address':local,'local_port':lport,'remote_address':remote,'remote_port':rport,'states':[state]}
            elif state not in entry['states']: entry['states'].append(state)

    def _run(self):
        try:
            while not self._stop.is_set():
                self.sample();self._stop.wait(self.interval)
            self.sample()
        except BaseException as error: self.error=repr(error)[:200]

    def start(self,pid):
        if self._thread is not None or type(pid) is not int or pid<=0: raise RuntimeRefused('SANDBOX_WATCHER_DENIED')
        self.pid=pid;self._thread=threading.Thread(target=self._run,daemon=True);self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=3)
            if self._thread.is_alive(): self.error=self.error or 'watcher thread did not stop'

    def loopback_connections(self):
        """Rows with a loopback remote address that were not just listening or closed."""
        return [dict(v) for v in self.connections.values()
                if v['states'] and any(s not in (1,2) for s in v['states'])  # 1 CLOSED, 2 LISTEN
                and (v['remote_address'].startswith('127.') or v['remote_address']=='::1' or v['remote_address'].startswith('::ffff:127.'))]

    def record(self):
        return {'pid':self.pid,'samples':self.samples,'interval_seconds':self.interval,'error':self.error,
                'connections':[dict(v) for v in self.connections.values()],'loopback_connections':self.loopback_connections(),
                'verified':self.error is None and self.samples>=1}


def run_sandboxed(root,job_dir,argv,*,seconds,memory_bytes,disk_bytes=MAX_DISK,memory_floor_bytes,available_memory=available_physical_memory,api=None,watcher=None):
    """Run the system Python in a fresh AppContainer inside job_dir. Return a SandboxResult after the process ends.

    argv names a .py file in job_dir and its arguments; the interpreter runs with -I -B. Any refusal happens before the process exists.
    The caller holds the one heavy-job slot. This function does not check the slot.
    watcher: an optional LoopbackWatcher. It starts when the process resumes and stops when the process has ended.
    """
    if watcher is not None and not isinstance(watcher,LoopbackWatcher): raise RuntimeRefused('SANDBOX_WATCHER_DENIED')
    job=_job_folder(root,job_dir);argv=_argv(job,argv)
    seconds=_bounded(seconds,MIN_SECONDS,MAX_SECONDS,'SANDBOX_DEADLINE_DENIED');memory_bytes=_bounded(memory_bytes,MIN_MEMORY,MAX_MEMORY,'SANDBOX_MEMORY_DENIED')
    disk_bytes=_bounded(disk_bytes,1,MAX_DISK,'SANDBOX_DISK_DENIED');_bounded(memory_floor_bytes,1,2**62,'SANDBOX_FLOOR_DENIED')
    environment={}
    for key in ENVIRONMENT:
        value=os.environ.get(key)
        if not value: raise RuntimeRefused('SANDBOX_ENVIRONMENT_UNAVAILABLE')
        environment[key]=value
    runtime=getattr(sys,'_base_executable',None)
    if not runtime or not Path(runtime).is_file(): raise RuntimeRefused('RUNTIME_UNAVAILABLE')
    available=available_memory()
    if type(available) is not int or available<memory_floor_bytes: raise RuntimeRefused('AVAILABLE_RAM_FLOOR')
    api=api or SandboxAPI();job_id=str(uuid4())
    profile=process=thread=None;job_object=api._handle(api.CreateJobObjectW(None,None),'CreateSandboxJob')
    stdout_path=job/'stdout.txt';stderr_path=job/'stderr.txt'
    try:
        profile=Profile(api,PROFILE_NAME)
        # The entry is on disk before grant() verifies it, so the finally block revokes whenever the profile exists.
        profile.grant(job)
        affinity=SIZE();system=SIZE();api.checked(api.GetProcessAffinityMask(HANDLE(-1),c.byref(affinity),c.byref(system)),'GetProcessAffinityMask')
        limits=ExtendedLimits();limits.basic.flags=0x2000|0x100|0x200|0x10|0x8|0x400
        limits.basic.affinity=affinity.value&-affinity.value;limits.basic.active_limit=1;limits.process_memory=limits.job_memory=memory_bytes
        api.checked(api.SetInformationJobObject(job_object.get(),9,c.byref(limits),c.sizeof(limits)),'SetSandboxLimits')
        actual=api.limits(job_object)
        if (actual.basic.flags!=limits.basic.flags or actual.basic.affinity!=limits.basic.affinity or actual.basic.active_limit!=1
                or actual.process_memory!=memory_bytes or actual.job_memory!=memory_bytes): raise RuntimeRefused('JOB_LIMITS_UNVERIFIED')
        environment.update(TEMP=str(job),TMP=str(job),PYTHONDONTWRITEBYTECODE='1',PYTHONNOUSERSITE='1',PYTHONIOENCODING='utf-8')
        block=c.create_unicode_buffer('\0'.join(f'{k}={v}' for k,v in sorted(environment.items()))+'\0\0')
        command=c.create_unicode_buffer(subprocess.list2cmdline([runtime,'-I','-B',*argv]))
        size=SIZE();api.InitializeProcThreadAttributeList(None,2,0,c.byref(size));attributes=c.create_string_buffer(size.value)
        api.checked(api.InitializeProcThreadAttributeList(attributes,2,0,c.byref(size)),'InitializeProcThreadAttributeList')
        import msvcrt
        from .bootstrap import _INHERIT_LOCK
        started=time.monotonic()
        with open(stdout_path,'wb') as out,open(stderr_path,'wb') as err,_INHERIT_LOCK:
            borrowed=[OwnedHandle(api,msvcrt.get_osfhandle(stream.fileno())) for stream in (out,err)]
            try:
                for handle in borrowed: api.set_inheritable(handle,True)
                handles=(HANDLE*2)(*(h.value for h in borrowed))
                api.checked(api.UpdateProcThreadAttribute(attributes,0,0x20002,handles,c.sizeof(handles),None,None),'ExplicitHandleList')
                capabilities=SECURITY_CAPABILITIES(profile.sid,None,0,0)
                api.checked(api.UpdateProcThreadAttribute(attributes,0,0x20009,c.byref(capabilities),c.sizeof(capabilities),None,None),'SecurityCapabilities')
                startup=StartupEx();startup.base.size=c.sizeof(startup);startup.attributes=c.cast(attributes,HANDLE)
                startup.base.flags=0x100;startup.base.stdout=borrowed[0].value;startup.base.stderr=borrowed[1].value
                info=ProcessInfo()
                api.checked(api.CreateProcessW(runtime,command,None,None,True,0x4|0x400|0x08000000|0x80000,block,str(job),
                    c.cast(c.byref(startup),c.POINTER(Startup)),c.byref(info)),'CreateSandboxProcess')
                process=OwnedHandle(api,info.process);thread=OwnedHandle(api,info.thread)
            finally:
                api.DeleteProcThreadAttributeList(attributes)
                for handle in borrowed: api.set_inheritable(handle,False)
            api.assign(job_object,process)
            if watcher is not None: watcher.start(info.pid)
            try:
                if api.ResumeThread(thread.get())!=1: raise RuntimeRefused('RESUME_UNVERIFIED')
                thread.close();thread=None
                timed_out=api.WaitForSingleObject(process.get(),seconds*1000)!=0
                if timed_out:
                    api.checked(api.TerminateJobObject(job_object.get(),124),'DeadlineTerminateJob')
                    if api.WaitForSingleObject(process.get(),3000)!=0: raise RuntimeRefused('JOB_EXIT_UNVERIFIED')
                elapsed=time.monotonic()-started
                deadline=time.monotonic()+3
                while api.active(job_object):
                    if time.monotonic()>=deadline: raise RuntimeRefused('JOB_EXIT_UNVERIFIED')
                    time.sleep(.01)
            finally:
                if watcher is not None: watcher.stop()
            code=DWORD();api.checked(api.GetExitCodeProcess(process.get(),c.byref(code)),'GetExitCodeProcess')
            peak=api.limits(job_object).peak_process_memory
        job_total=folder_bytes(job,disk_bytes);package_total=folder_bytes(profile.folder,disk_bytes)
        return SandboxResult(job_id,profile.sid_string,info.pid,code.value,timed_out,elapsed,peak,job_total,package_total,
                             job_total+package_total>disk_bytes,read_head(stdout_path),read_head(stderr_path))
    except BaseException:
        if process is not None:
            api.TerminateProcess(process.get(),125);api.WaitForSingleObject(process.get(),3000)
        raise
    finally:
        errors=[]
        for handle in (thread,process,job_object):
            if handle is not None:
                try: handle.close()
                except BaseException as error: errors.append(error)
        if profile is not None:
            try: profile.revoke(job)
            except BaseException as error: errors.append(error)
            try: profile.close()
            except BaseException as error: errors.append(error)
        if errors:
            active=sys.exc_info()[1]
            if active is None: raise errors[0]
            for error in errors: active.add_note(f'sandbox cleanup also failed: {error!r}')


PROBE=r'''
import ctypes as c, json, os, socket, subprocess, sys
with open('targets.json', encoding='utf-8') as stream: targets = json.load(stream)
port, outside_read, outside_write, previous, megabytes = targets['port'], targets['outside_read'], targets['outside_write'], targets['previous'], targets['megabytes']
fixed_reads, pipe = targets['fixed_reads'], targets['pipe']
out = {}
def attempt(name, fn):
    try: out[name] = {'ok': True, 'value': fn()}
    except BaseException as error: out[name] = {'ok': False, 'error': type(error).__name__, 'detail': str(error)[:200]}
    with open('probe.json', 'w', encoding='utf-8') as stream: json.dump(out, stream)
def token():
    advapi = c.WinDLL('advapi32', use_last_error=True); handle = c.c_void_p(); count = c.c_uint32()
    if not advapi.OpenProcessToken(c.c_void_p(-1), 8, c.byref(handle)): raise OSError(c.get_last_error())
    flag = c.c_uint32()
    if not advapi.GetTokenInformation(handle, 29, c.byref(flag), 4, c.byref(count)): raise OSError(c.get_last_error())
    label = c.create_string_buffer(64)
    if not advapi.GetTokenInformation(handle, 25, label, 64, c.byref(count)): raise OSError(c.get_last_error())
    sid = c.c_void_p.from_buffer(label).value
    advapi.GetSidSubAuthorityCount.restype = c.POINTER(c.c_ubyte); advapi.GetSidSubAuthority.restype = c.POINTER(c.c_uint32)
    n = advapi.GetSidSubAuthorityCount(c.c_void_p(sid)).contents.value
    return {'is_appcontainer': flag.value, 'integrity_level': advapi.GetSidSubAuthority(c.c_void_p(sid), n - 1).contents.value}
def connect(host, port):
    s = socket.socket(); s.settimeout(3)
    try: s.connect((host, port)); return 'CONNECTED'
    finally: s.close()
attempt('token', token)
attempt('external_connect', lambda: connect('1.1.1.1', 53))
attempt('loopback_connect', lambda: connect('127.0.0.1', port))
attempt('outside_read', lambda: open(outside_read, encoding='utf-8').read())
attempt('outside_write', lambda: open(outside_write, 'w', encoding='utf-8').write('escaped'))
attempt('previous_read', lambda: open(previous, encoding='utf-8').read())
for index, target in enumerate(fixed_reads):
    attempt('fixed_read_%d' % index, lambda target=target: len(open(target, 'rb').read(16)))
if pipe is not None:
    attempt('pipe_open', lambda: len(open(pipe, 'rb').read(1)))
attempt('inside_write', lambda: open('inside.txt', 'w', encoding='utf-8').write('ok'))
attempt('child_process', lambda: subprocess.run([sys.executable, '-I', '-c', 'pass'], timeout=10).returncode)
attempt('allocate', lambda: len(bytearray(megabytes * 1024 * 1024)))
'''


def controls_from(report,result,*,escape_exists,inside_written,fixed_count,pipe_given):
    """Compute the twelve controls. Each denial must carry the exact error the boundary produces; any other failure is not a pass.

    fixed_count is the number of real fixed-part files the probe tried to read; zero proves nothing and fails the control.
    pipe_given says whether a named pipe server was offered; without one the pipe control fails.
    """
    def refused(name,error,detail=''):
        entry=report.get(name)
        return type(entry) is dict and entry.get('ok') is False and entry.get('error')==error and detail in str(entry.get('detail',''))
    token=report.get('token',{}).get('value') or {}
    return {'appcontainer_token':token.get('is_appcontainer')==1,'low_integrity':token.get('integrity_level')==4096,
            'external_network_denied':refused('external_connect','PermissionError'),
            'outside_read_denied':refused('outside_read','PermissionError'),'outside_write_denied':refused('outside_write','PermissionError'),
            'outside_file_absent':not escape_exists,'previous_job_read_denied':refused('previous_read','PermissionError'),
            'inside_write_allowed':report.get('inside_write',{}).get('ok') is True and inside_written,
            'child_process_denied':refused('child_process','OSError','1816'),
            'fixed_targets_read_denied':type(fixed_count) is int and fixed_count>=1 and all(refused(f'fixed_read_{i}','PermissionError') for i in range(fixed_count)),
            'pipe_open_denied':pipe_given is True and refused('pipe_open','PermissionError'),
            'memory_limit_enforced':refused('allocate','MemoryError') or ('allocate' not in report and 'child_process' in report
                                                                          and not result.timed_out and result.exit_code in OUT_OF_MEMORY_EXITS)}


def observations_from(report,*,listener_saw_connection):
    """Record what the probe saw on loopback. These are facts for the ledger, not controls; see OBSERVATIONS."""
    entry=report.get('loopback_connect')
    return {'loopback_connected':type(entry) is dict and entry.get('ok') is True,'loopback_seen_by_listener':bool(listener_saw_connection)}


def fixed_target_paths(targets):
    """Admit at most 16 existing, absolute, regular files that the probe must fail to read. These are the real fixed parts."""
    if not isinstance(targets,(list,tuple)) or len(targets)>MAX_FIXED_TARGETS: raise RuntimeRefused('SANDBOX_TARGETS_DENIED')
    paths=[]
    for target in targets:
        if not isinstance(target,(str,Path)): raise RuntimeRefused('SANDBOX_TARGETS_DENIED')
        path=Path(target)
        if not path.is_absolute() or not path.is_file() or path.is_symlink(): raise RuntimeRefused('SANDBOX_TARGETS_DENIED')
        paths.append(str(path))
    if len(set(paths))!=len(paths): raise RuntimeRefused('SANDBOX_TARGETS_DENIED')
    return paths


def verify_sandbox(root,*,memory_floor_bytes,seconds=60,memory_bytes=256*1024**2,api=None,fixed_targets=(),pipe=None):
    """Run a first job, then the fixed probe in a second job, and return a verification dict. The caller uses require_verified.

    fixed_targets: real fixed-part files (ledger, rules, config) that the probe must fail to read. pipe: a named pipe path
    with a live server that the probe must fail to open. Without targets or without a pipe the two controls fail.
    The external probe target is 1.1.1.1:53. A packet leaves the host only if the boundary has already failed.
    """
    root=Path(root).resolve(strict=True);token=str(uuid4())[:8];fixed=fixed_target_paths(fixed_targets)
    if pipe is not None and (not isinstance(pipe,str) or not pipe.startswith('\\\\.\\pipe\\') or not 10<len(pipe)<=256): raise RuntimeRefused('SANDBOX_TARGETS_DENIED')
    previous=root/f'previous-{token}';previous.mkdir()
    (previous/'main.py').write_text("open('inside.txt','w',encoding='utf-8').write('earlier job')\n",encoding='utf-8')
    first=run_sandboxed(root,previous,['main.py'],seconds=seconds,memory_bytes=memory_bytes,memory_floor_bytes=memory_floor_bytes,api=api)
    if first.exit_code!=0 or not (previous/'inside.txt').is_file(): raise RuntimeRefused('SANDBOX_UNVERIFIED:previous_job_failed')
    job=root/f'probe-{token}';job.mkdir()
    (job/'probe.py').write_text(PROBE,encoding='utf-8')
    canary=root/f'canary-{token}.txt';canary.write_text('outside the sandbox',encoding='utf-8');escape=root/f'escape-{token}.txt'
    listener=socket.socket();listener.bind(('127.0.0.1',0));listener.listen(1);listener.settimeout(seconds+5);seen=[]
    def accept():
        try: connection,_=listener.accept();seen.append(True);connection.close()
        except OSError: pass
    waiter=threading.Thread(target=accept,daemon=True);waiter.start()
    (job/'targets.json').write_text(json.dumps({'port':listener.getsockname()[1],'outside_read':str(canary),'outside_write':str(escape),
                                                'previous':str(previous/'inside.txt'),'megabytes':memory_bytes//1024**2+256,
                                                'fixed_reads':fixed,'pipe':pipe}),encoding='utf-8')
    try:
        result=run_sandboxed(root,job,['probe.py'],seconds=seconds,memory_bytes=memory_bytes,memory_floor_bytes=memory_floor_bytes,api=api)
    finally:
        listener.close();waiter.join(timeout=2)
    report=json.loads(read_head(job/'probe.json')) if (job/'probe.json').is_file() else {}
    controls=controls_from(report,result,escape_exists=escape.exists(),inside_written=(job/'inside.txt').is_file(),fixed_count=len(fixed),pipe_given=pipe is not None)
    observations=observations_from(report,listener_saw_connection=bool(seen))
    assert set(controls)==set(CONTROLS) and set(observations)==set(OBSERVATIONS)
    return {'controls':controls,'failed':sorted(k for k,v in controls.items() if not v),'observations':observations,'report':report,
            'result':result.record(),'previous_result':first.record(),'job_folder':str(job),'fixed_targets':fixed,'pipe':pipe}


def require_verified(verification):
    """Refuse unless every control held. The engine calls this before the first Engineer job of a run.

    Observations never pass or fail this check. The engine must still record them with the run.
    """
    if (type(verification) is not dict or type(verification.get('failed')) is not list or type(verification.get('controls')) is not dict
            or set(verification['controls'])!=set(CONTROLS)): raise RuntimeRefused('SANDBOX_UNVERIFIED')
    failed=sorted(set(verification['failed'])|{k for k,v in verification['controls'].items() if v is not True})
    if failed: raise RuntimeRefused('SANDBOX_UNVERIFIED:'+','.join(failed))
    return True
