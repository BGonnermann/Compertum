"""M0 native services. No execution or evaluator service is activated."""
import ctypes as C
from ctypes import wintypes as W
import json,os,subprocess,sys,time,jsonschema,msvcrt
from pathlib import Path
from .identity import resolve_project
from .owners import acquire_owner
from . import jobs,win32 as w
from ..domain import atomic_json,now

def constrain_service(memory,cpu_threads=4):
    job=jobs.CreateJob(None,None);limits=jobs.ExtendedLimits()
    if not 1<=cpu_threads<=4:raise ValueError('SERVICE_CPU_LIMIT')
    limits.basic.flags=0x2000|0x100|0x200|0x10|0x20;limits.basic.affinity=(1<<cpu_threads)-1;limits.basic.priority=0x20
    limits.process_memory=memory;limits.job_memory=memory
    if not job or not jobs.SetJob(job,9,C.byref(limits),C.sizeof(limits)) or not jobs.Assign(job,w.GetCurrentProcess()):
        if job:w.CloseHandle(job)
        raise RuntimeError('SERVICE_JOB_UNVERIFIED')
    return job

def spawn_service(root,role,peer_server=None):
    if role not in {'supervisor','watchdog'}:raise ValueError('UNREGISTERED_SERVICE')
    source=Path(__file__).resolve().parents[2];packages=Path(jsonschema.__file__).resolve().parents[1]
    code='import sys;sys.path[:0]='+repr([str(source),str(packages)])+';from compertum.runtime.supervisor import main;main()'
    temp=Path(root)/'.cache/service-temp';temp.mkdir(parents=True,exist_ok=True)
    env={'SystemRoot':os.environ.get('SystemRoot','C:'+chr(92)+'Windows'),'WINDIR':os.environ.get('WINDIR','C:'+chr(92)+'Windows'),'TEMP':str(temp),'TMP':str(temp),'OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1','MKL_NUM_THREADS':'1'}
    args=[sys._base_executable,'-I','-B','-u','-c',code,str(root),role];startup=None;fds=None
    if peer_server:
        if role!='watchdog':raise ValueError('BOOTSTRAP_ROLE_DENIED')
        fds=os.pipe();handle=msvcrt.get_osfhandle(fds[0]);os.set_handle_inheritable(handle,True)
        startup=subprocess.STARTUPINFO();startup.lpAttributeList={'handle_list':[handle]};args.append(str(handle))
    try:
        child=subprocess.Popen(args,env=env,cwd=root,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=0x08000000,close_fds=True,startupinfo=startup)
        if peer_server:
            from dataclasses import asdict
            token=peer_server.register_peer(w.identity(child.pid),'watchdog',{'watchdog-health'})
            os.write(fds[1],json.dumps({'endpoint':asdict(peer_server.endpoint),'capability':token}).encode())
        return child
    finally:
        if fds:
            for fd in fds:os.close(fd)

def main():
    root=Path(sys.argv[1]);role=sys.argv[2]
    job=constrain_service((128 if role=='watchdog' else 256)*1024**2)
    try:
        p=resolve_project(root)
        if role=='supervisor':
            from ..coordinator import serve
            with acquire_owner(p,'supervisor') as lease:serve(p,lease)
        else:
            from ..watchdog import StorageWatchdog
            bootstrap=None
            if len(sys.argv)>3:
                fd=msvcrt.open_osfhandle(int(sys.argv[3]),os.O_RDONLY)
                with os.fdopen(fd,'rb') as source:
                    raw=source.read(65537)
                if len(raw)>65536:raise RuntimeError('BOOTSTRAP_CAPACITY')
                bootstrap=json.loads(raw)
            with acquire_owner(p,'watchdog') as lease:
                wd=StorageWatchdog(lease,root/'state/watchdog/heartbeat.json')
                last_sent=0
                try:
                    while True:
                        meta=json.loads((root/'state/runtime/supervisor.json').read_text())
                        actual=w.identity(meta['pid'])
                        if actual['creation_time']!=meta['creation_time'] or actual['exited']:break
                        if (root/'state/runtime/shutdown.json').exists():break
                        if bootstrap and time.monotonic()-last_sent>=5:
                            from .ipc import RoleEndpoint,request
                            observed=json.loads((root/'state/watchdog/heartbeat.json').read_text()) if (root/'state/watchdog/heartbeat.json').exists() else {'storage_healthy':False}
                            result=request(RoleEndpoint(**bootstrap['endpoint']),{'action':'watchdog-health','role':'watchdog','capability':bootstrap['capability'],'storage_healthy':observed['storage_healthy']})
                            if result['exit_code']:raise RuntimeError('BOOTSTRAP_ROLE_UNVERIFIED')
                            last_sent=time.monotonic()
                        time.sleep(.5)
                finally:wd.close()
    except Exception as exc:
        atomic_json(root/'state/runtime'/(role+'-failure.json'),{'at':now(),'reason':type(exc).__name__})
    finally:w.CloseHandle(job)
