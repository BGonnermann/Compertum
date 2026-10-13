"""Suspended, assigned Windows processes with no breakaway and bounded capture."""
import ctypes as C
from ctypes import wintypes as W
import msvcrt
import os
from pathlib import Path
import subprocess
import sys,jsonschema
import threading
import time
from . import win32 as w
from ..domain import ContractError,within

class BasicLimits(C.Structure):
    _fields_=[('process_time',C.c_int64),('job_time',C.c_int64),('flags',W.DWORD),('min_ws',C.c_size_t),('max_ws',C.c_size_t),('active_limit',W.DWORD),('affinity',C.c_size_t),('priority',W.DWORD),('scheduling',W.DWORD)]
class ExtendedLimits(C.Structure):
    _fields_=[('basic',BasicLimits),('io',C.c_uint64*6),('process_memory',C.c_size_t),('job_memory',C.c_size_t),('peak_process',C.c_size_t),('peak_job',C.c_size_t)]
class Accounting(C.Structure):
    _fields_=[('times',C.c_int64*4),('page_faults',W.DWORD),('total',W.DWORD),('active',W.DWORD),('terminated',W.DWORD)]
class StartupInfo(C.Structure):
    _fields_=[('cb',W.DWORD),('reserved',W.LPWSTR),('desktop',W.LPWSTR),('title',W.LPWSTR),('x',W.DWORD),('y',W.DWORD),('sx',W.DWORD),('sy',W.DWORD),('xc',W.DWORD),('yc',W.DWORD),('fill',W.DWORD),('flags',W.DWORD),('show',W.WORD),('reserved_bytes',W.WORD),('reserved_ptr',C.c_void_p),('stdin',W.HANDLE),('stdout',W.HANDLE),('stderr',W.HANDLE)]
class ProcessInfo(C.Structure):
    _fields_=[('process',W.HANDLE),('thread',W.HANDLE),('pid',W.DWORD),('tid',W.DWORD)]
CreateJob=w.bind(w.K,'CreateJobObjectW',[C.c_void_p,W.LPCWSTR],W.HANDLE)
SetJob=w.bind(w.K,'SetInformationJobObject',[W.HANDLE,C.c_int,C.c_void_p,W.DWORD],W.BOOL)
QueryJob=w.bind(w.K,'QueryInformationJobObject',[W.HANDLE,C.c_int,C.c_void_p,W.DWORD,C.c_void_p],W.BOOL)
Assign=w.bind(w.K,'AssignProcessToJobObject',[W.HANDLE,W.HANDLE],W.BOOL)
InJob=w.bind(w.K,'IsProcessInJob',[W.HANDLE,W.HANDLE,C.POINTER(W.BOOL)],W.BOOL)
TerminateJob=w.bind(w.K,'TerminateJobObject',[W.HANDLE,W.UINT],W.BOOL)
TerminateProcess=w.bind(w.K,'TerminateProcess',[W.HANDLE,W.UINT],W.BOOL)
CreateProcess=w.bind(w.K,'CreateProcessW',[W.LPCWSTR,W.LPWSTR,C.c_void_p,C.c_void_p,W.BOOL,W.DWORD,C.c_void_p,W.LPCWSTR,C.POINTER(StartupInfo),C.POINTER(ProcessInfo)],W.BOOL)
Resume=w.bind(w.K,'ResumeThread',[W.HANDLE],W.DWORD)
ExitCode=w.bind(w.K,'GetExitCodeProcess',[W.HANDLE,C.POINTER(W.DWORD)],W.BOOL)
GetPid=w.bind(w.K,'GetProcessId',[W.HANDLE],W.DWORD)

class ResourceSlot:
    def __init__(self,project):
        # Test/clean-run roots inside this workspace must share the same heavy slot.
        resource_root=project.root_path
        for ancestor in (project.root_path,*project.root_path.parents):
            if (ancestor/'pyproject.toml').is_file() and (ancestor/'.python-version').is_file():resource_root=ancestor;break
        path=within(resource_root,'state/locks/research-resource.lock');path.parent.mkdir(parents=True,exist_ok=True)
        self.handle=w.CreateFile(str(path),0xC0000000,0,None,4,0,None)
        if self.handle==w.INVALID:raise ContractError('RESOURCE_BUSY')
    def close(self):
        if self.handle is not None:w.CloseHandle(self.handle);self.handle=None
    def __enter__(self):return self
    def __exit__(self,*args):self.close()

class JobHandle:
    def __init__(self,job,process,slot,readers,budget):
        self.job=job;self.process=process;self.slot=slot;self.budget=budget;self.started=time.monotonic();self.buffers=[bytearray(),bytearray()];self.bytes=0;self.capture_limit=min(10*1024**2,budget.output_bytes);self.output_limit=False;self.lock=threading.Lock()
        self.threads=[]
        for i,fd in enumerate(readers):
            def drain(index=i,source=fd):
                try:
                    while True:
                        chunk=os.read(source,65536)
                        if not chunk:break
                        with self.lock:
                            if self.bytes+len(chunk)>self.capture_limit:
                                self.output_limit=True;TerminateJob(self.job,7);break
                            self.bytes+=len(chunk);self.buffers[index].extend(chunk)
                finally:os.close(source)
            t=threading.Thread(target=drain,daemon=True);t.start();self.threads.append(t)
    def wait(self):
        timeout=max(0,self.budget.wall_seconds-(time.monotonic()-self.started))
        timed=w.Wait(self.process,int(timeout*1000))==258
        if timed:TerminateJob(self.job,1460);w.Wait(self.process,5000)
        code=W.DWORD();ExitCode(self.process,C.byref(code))
        # Root redirectors can exit independently of descendants: terminate leftovers.
        acc=Accounting();verified=bool(QueryJob(self.job,1,C.byref(acc),C.sizeof(acc),None))
        if verified and acc.active:TerminateJob(self.job,0)
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            verified=bool(QueryJob(self.job,1,C.byref(acc),C.sizeof(acc),None))
            if verified and acc.active==0:break
            time.sleep(.02)
        for thread in self.threads:thread.join(5)
        result={'assigned_before_resume':True,'root_pid':GetPid(self.process),'exit_code':code.value,'timed_out':timed,'output_limit':self.output_limit,'active_processes':acc.active if verified else None,'stdout':self.buffers[0].decode('utf-8','replace'),'stderr':self.buffers[1].decode('utf-8','replace'),'elapsed_seconds':time.monotonic()-self.started}
        w.CloseHandle(self.process);w.CloseHandle(self.job);self.slot.close()
        return result

def launch_bounded(lease,task,argv):
    lease.verify()
    if lease.role!='coordinator' or task.kind!='OFFLINE_FIXTURE' or argv not in [['fixture'],['sleep'],['memory'],['breakaway'],['grow'],['tree'],['model_identity_hash']]:raise ContractError('UNREGISTERED_TEMPLATE')
    slot=ResourceSlot(lease.project);job=CreateJob(None,None)
    if not job:slot.close();raise w.error('JOB_UNAVAILABLE')
    limits=ExtendedLimits();limits.basic.flags=0x2000|0x100|0x200|0x10|0x20;limits.basic.affinity=(1<<min(4,task.budget.cpu_threads,os.cpu_count()))-1;limits.basic.priority=0x4000;limits.process_memory=task.budget.ram_bytes;limits.job_memory=task.budget.ram_bytes
    if not SetJob(job,9,C.byref(limits),C.sizeof(limits)):w.CloseHandle(job);slot.close();raise w.error('JOB_LIMIT_UNVERIFIED')
    fds=[os.pipe(),os.pipe()];writers=[msvcrt.get_osfhandle(p[1]) for p in fds]
    for h in writers:os.set_handle_inheritable(h,True)
    start=StartupInfo();start.cb=C.sizeof(start);start.flags=0x100;start.stdout=writers[0];start.stderr=writers[1];start.stdin=None
    info=ProcessInfo();temp=within(lease.project.root_path,'.cache/worker-temp/'+task.task_id);temp.mkdir(parents=True,exist_ok=True)
    env={'SystemRoot':os.environ.get('SystemRoot','C:'+chr(92)+'Windows'),'WINDIR':os.environ.get('WINDIR','C:'+chr(92)+'Windows'),'TEMP':str(temp),'TMP':str(temp),'OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1','MKL_NUM_THREADS':'1','NUMEXPR_NUM_THREADS':'1','PYTHONNOUSERSITE':'1'}
    environment=C.create_unicode_buffer('\0'.join(k+'='+v for k,v in sorted(env.items()))+'\0\0')
    # The Windows venv redirector may spawn outside the assigned nested job.
    # Use the SAME base interpreter with explicitly selected locked-environment
    # packages and this trusted source module; never execute task-supplied code.
    base=getattr(sys,'_base_executable',sys.executable)
    source=Path(__file__).resolve().parents[2]
    packages=Path(jsonschema.__file__).resolve().parents[1]
    bootstrap='import sys,runpy;sys.path[:0]='+repr([str(source),str(packages)])+';runpy.run_module("compertum.runtime.worker",run_name="__main__")'
    command=C.create_unicode_buffer(subprocess.list2cmdline([base,'-I','-B','-u','-c',bootstrap,argv[0]]))
    created=False
    try:
        if not CreateProcess(base,command,None,None,True,0x4|0x400|0x08000000,environment,str(lease.project.root_path),C.byref(start),C.byref(info)):raise w.error('PROCESS_CREATE_FAILED')
        created=True;inside=W.BOOL()
        if not Assign(job,info.process) or not InJob(info.process,job,C.byref(inside)) or not inside.value:raise w.error('JOB_ASSIGNMENT_UNVERIFIED')
        actual=ExtendedLimits()
        if not QueryJob(job,9,C.byref(actual),C.sizeof(actual),None) or actual.job_memory!=task.budget.ram_bytes:raise w.error('JOB_LIMIT_UNVERIFIED')
        if Resume(info.thread)==0xFFFFFFFF:raise w.error('PROCESS_RESUME_FAILED')
        w.CloseHandle(info.thread)
        for pair in fds:os.close(pair[1])
        return JobHandle(job,info.process,slot,[pair[0] for pair in fds],task.budget)
    except BaseException:
        if created:TerminateProcess(info.process,7);w.CloseHandle(info.thread);w.CloseHandle(info.process)
        w.CloseHandle(job);slot.close()
        for pair in fds:
            for fd in pair:
                try:os.close(fd)
                except OSError:pass
        raise
