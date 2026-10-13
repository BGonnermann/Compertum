"""Registered non-financial M0 diagnostics, never arbitrary candidate code."""
import ctypes as C
from ctypes import wintypes as W
import json,os,subprocess,sys,time
from . import win32 as w
from .jobs import InJob

def main():
    kind=sys.argv[1]
    if kind=='fixture':
        inside=W.BOOL();assert InJob(w.GetCurrentProcess(),None,C.byref(inside))
        mask=C.c_size_t();system=C.c_size_t()
        get=w.bind(w.K,'GetProcessAffinityMask',[W.HANDLE,C.POINTER(C.c_size_t),C.POINTER(C.c_size_t)],W.BOOL)
        assert get(w.GetCurrentProcess(),C.byref(mask),C.byref(system))
        print(json.dumps({'sum':14,'pid':os.getpid(),'in_job':bool(inside.value),'cpu_mask':mask.value}),flush=True)
    elif kind=='sleep':time.sleep(10)
    elif kind=='memory':data=bytearray(512*1024**2);print(len(data))
    elif kind=='grow':
        while True:sys.stdout.write('x'*65536);sys.stdout.flush()
    elif kind=='tree':
        child=subprocess.Popen([sys.executable,'-I','-c','import time;time.sleep(10)'],creationflags=0x08000000)
        print(json.dumps({'child_redirector_pid':child.pid}),flush=True);time.sleep(10)
    elif kind=='breakaway':
        try:
            p=subprocess.Popen([sys.executable,'-I','-c','pass'],creationflags=0x01000000|0x08000000);p.wait(timeout=5);print(json.dumps({'breakaway_denied':False}))
        except OSError:print(json.dumps({'breakaway_denied':True}))
    elif kind=='model_identity_hash':
        from ..ai.qualification import identity_files
        print(json.dumps(identity_files()),flush=True)
    else:raise ValueError('UNREGISTERED_TEMPLATE')

if __name__=='__main__':main()
