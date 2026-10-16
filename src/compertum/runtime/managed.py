"""Trusted role launch with an explicit inherited handle list and native limits."""
import ctypes as c
from dataclasses import asdict
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from .jobs import JobAPI,JobHandle,ExtendedLimits,Startup,ProcessInfo,SIZE
from ._windows import HANDLE,DWORD,BOOL,OwnedHandle
from .owners import _owner_scope,require_live_owner
from .owner_channel import prepare_owner_channel
from .errors import RuntimeRefused
from .startup import StartupBinding

class StartupEx(c.Structure):
    _fields_=[('base',Startup),('attributes',HANDLE)]


def launch_owner(supervisor,role,*,expect_execution=True):
    require_live_owner(supervisor,'supervisor')
    if type(expect_execution) is not bool:raise RuntimeRefused('OWNER_LAUNCH_DENIED')
    if role not in {'watchdog','evaluation','execution'}: raise RuntimeRefused('OWNER_LAUNCH_DENIED')
    commands=frozenset({'status','checkpoint','synthetic_protocol'} if role=='evaluation' else {'status','checkpoint','owner_heartbeat','fake_operator','paper_read','paper_read_transfer','paper_market_read','paper_market_transfer','paper_presence','paper_intent'} if role=='execution' else {'status','checkpoint','owner_heartbeat'})
    with _owner_scope(supervisor) as guard:
        offer=prepare_owner_channel(supervisor,role=role,allowed_commands=commands)
        api=JobAPI();job=api._handle(api.CreateJobObjectW(None,None),'CreateJobObjectW')
        process=None;thread=None;startup_binding=None
        try:
            available=SIZE();system=SIZE()
            api.checked(api.GetProcessAffinityMask(HANDLE(-1),c.byref(available),c.byref(system)),'GetProcessAffinityMask')
            limits=ExtendedLimits();limits.basic.flags=0x2000|0x100|0x200|0x10|0x8|0x400
            limits.basic.affinity=available.value&-available.value;limits.basic.active_limit=1
            limits.process_memory=limits.job_memory=(128 if role=='watchdog' else 256 if role=='evaluation' else 512)*1024**2
            api.checked(api.SetInformationJobObject(job.get(),9,c.byref(limits),c.sizeof(limits)),'SetJobLimits')
            actual=api.limits(job)
            if (actual.basic.flags!=limits.basic.flags or actual.basic.affinity!=limits.basic.affinity
                    or actual.job_memory!=limits.job_memory or actual.basic.active_limit!=1):
                raise RuntimeRefused('JOB_LIMITS_UNVERIFIED')
            kernel=c.WinDLL('kernel32',use_last_error=True)
            init=kernel.InitializeProcThreadAttributeList;init.argtypes=[HANDLE,DWORD,DWORD,c.POINTER(SIZE)];init.restype=BOOL
            update=kernel.UpdateProcThreadAttribute;update.argtypes=[HANDLE,DWORD,SIZE,HANDLE,SIZE,HANDLE,HANDLE];update.restype=BOOL
            delete=kernel.DeleteProcThreadAttributeList;delete.argtypes=[HANDLE];delete.restype=None
            size=SIZE();init(None,1,0,c.byref(size));attributes=c.create_string_buffer(size.value)
            api.checked(init(attributes,1,0,c.byref(size)),'InitializeProcThreadAttributeList')
            try:
                with offer.inheritance() as inherited:
                    handles=(HANDLE*1)(inherited)
                    api.checked(update(attributes,0,0x20002,handles,c.sizeof(handles),None,None),'ExplicitHandleList')
                    startup=StartupEx();startup.base.size=c.sizeof(startup);startup.attributes=c.cast(attributes,HANDLE)
                    startup_binding=StartupBinding(api,guard.project.root_path)
                    env={k:v for k,v in os.environ.items() if k.upper() in {'SYSTEMROOT','WINDIR'}}
                    env.update(__PYVENV_LAUNCHER__=sys.executable,PYTHONDONTWRITEBYTECODE='1',PYTHONNOUSERSITE='1',
                        PYTHONPATH=str(Path(__file__).resolve().parents[2]))
                    startup_binding.apply(env)
                    for key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'): env[key]='1'
                    block=c.create_unicode_buffer('\0'.join(f'{k}={v}' for k,v in sorted(env.items()))+'\0\0')
                    public={'root':str(guard.project.root_path),'role':role,'supervisor':asdict(offer.registration),'expect_execution':expect_execution}
                    command=c.create_unicode_buffer(subprocess.list2cmdline([sys.executable,'-B','-m','compertum.runtime.managed_owner',str(inherited),json.dumps(public,separators=(',',':'))]))
                    info=ProcessInfo()
                    api.checked(api.CreateProcessW(str(startup_binding.application),command,None,None,True,0x4|0x400|0x08000000|0x80000,
                        block,str(guard.project.root_path),c.cast(c.byref(startup),c.POINTER(Startup)),c.byref(info)),'CreateManagedOwner')
                    process=OwnedHandle(api,info.process);thread=OwnedHandle(api,info.thread)
                    api.assign(job,process);require_live_owner(supervisor)
                    startup_evidence=startup_binding.before_resume(process)
                    if api.ResumeThread(thread.get())!=1: raise RuntimeRefused('RESUME_UNVERIFIED')
                    thread.close();thread=None
            finally: delete(attributes)
            handle=JobHandle(api,supervisor,job,process,info.pid,float('inf'),limits)
            handle.startup_evidence=startup_evidence;handle._startup_plan_raw=startup_binding.raw
            remote=offer.accept(process.get())
            from .owner_rpc import call_owner
            # First-time reserve creation includes a complete storage census.
            observed=call_owner(remote,'status',{},timeout=35).get('startup')
            expected={'schema':'observed-python-startup-v1','pid':info.pid,'plan_sha256':startup_evidence['plan_sha256']}
            from .startup_record import validate_proof
            from compertum.data.errors import DataError
            try:validate_proof(observed)
            except DataError:raise RuntimeRefused('STARTUP_PROOF_UNVERIFIED') from None
            if json.dumps(observed,sort_keys=True)!=json.dumps(expected,sort_keys=True):raise RuntimeRefused('STARTUP_PROOF_UNVERIFIED')
            startup_binding.close();startup_binding=None
            guard.resources.append(handle)
            return handle,remote
        except BaseException:
            if process is not None:
                api.TerminateProcess(process.get(),125);api.WaitForSingleObject(process.get(),3000);process.close()
            if thread is not None: thread.close()
            job.close();offer.close();raise
        finally:
            if startup_binding is not None:startup_binding.close()


def constrain_coordinator():
    """Cap this trusted foreground coordinator; every child gets its own Job.

    Silent breakaway belongs only to this trusted launcher Job. Managed owners
    and fixture Jobs themselves have no breakaway flag and are assigned before
    resume. This avoids imposing the coordinator's 256 MiB cap on research Jobs.
    """
    api=JobAPI();job=api._handle(api.CreateJobObjectW(None,None),'CreateCoordinatorJob')
    try:
        available=SIZE();system=SIZE()
        api.checked(api.GetProcessAffinityMask(HANDLE(-1),c.byref(available),c.byref(system)),'GetProcessAffinityMask')
        limits=ExtendedLimits();limits.basic.flags=0x100|0x1000|0x10|0x400
        limits.basic.affinity=sum([1<<n for n in range(64) if available.value&(1<<n)][:4])
        limits.process_memory=256*1024**2
        api.checked(api.SetInformationJobObject(job.get(),9,c.byref(limits),c.sizeof(limits)),'SetCoordinatorLimits')
        api.assign(job,OwnedHandle(api,-1))
        actual=api.limits(job)
        if actual.process_memory!=limits.process_memory or actual.basic.flags!=limits.basic.flags:
            raise RuntimeRefused('COORDINATOR_LIMIT_UNVERIFIED')
        return job,{'memory_limit':actual.process_memory,'affinity':actual.basic.affinity,'verified':True}
    except BaseException: job.close();raise


_AI_JOB=None
_AI_LIMITS=None

def constrain_ai_adapter():
    """A dedicated adapter caller keeps a one-thread, 256 MiB, no-child Job.

    The handle lives until process exit. This API must not be used by the
    supervisor: local inference is deliberately a separate, bounded caller.
    """
    global _AI_JOB,_AI_LIMITS
    if _AI_JOB is not None: return dict(_AI_LIMITS)
    api=JobAPI();job=api._handle(api.CreateJobObjectW(None,None),'CreateAdapterJob')
    try:
        available=SIZE();system=SIZE()
        api.checked(api.GetProcessAffinityMask(HANDLE(-1),c.byref(available),c.byref(system)),'GetProcessAffinityMask')
        limits=ExtendedLimits();limits.basic.flags=0x100|0x10|0x8|0x400
        limits.basic.affinity=available.value&-available.value;limits.basic.active_limit=1;limits.process_memory=256*1024**2
        api.checked(api.SetInformationJobObject(job.get(),9,c.byref(limits),c.sizeof(limits)),'SetAdapterLimits')
        api.assign(job,OwnedHandle(api,-1));actual=api.limits(job)
        if actual.process_memory!=limits.process_memory or actual.basic.affinity!=limits.basic.affinity or actual.basic.flags!=limits.basic.flags or actual.basic.active_limit!=1:
            raise RuntimeRefused('AI_LIMIT_UNVERIFIED')
        _AI_JOB=job;_AI_LIMITS={'verified':True,'memory_limit':actual.process_memory,'affinity':actual.basic.affinity,'active_process_limit':actual.basic.active_limit}
        return dict(_AI_LIMITS)
    except BaseException: job.close();raise
