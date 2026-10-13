"""Registered tiny offline fixtures. Never accepts source code or a shell."""
from .startup import require_entrypoint_startup
_STARTUP_PROOF=require_entrypoint_startup() if __name__=='__main__' else None

import json
import os
from pathlib import Path
import subprocess
import sys
import time


CANONICAL=b'compertum-offline-fixture-v1\n'


def canonical_sink():
    # The parent admitted and opened this exact sink. No filesystem path, code,
    # network destination or ledger capability is accepted by the template.
    import ctypes as c
    from ._windows import WindowsAPI,OwnedHandle,DWORD
    api=WindowsAPI();handle=OwnedHandle(api,int(sys.argv[2]))
    maximum=int(sys.argv[3]);offset=int(sys.argv[4])
    if not api.handle_flags(handle)&1 or not 0<=offset<=len(CANONICAL)<=maximum<=4096: return 3
    api.set_inheritable(handle,False)
    try:
        for index in range(offset,len(CANONICAL)):
            chunk=CANONICAL[index:index+1]
            if index+len(chunk)>maximum: return 3
            buffer=c.create_string_buffer(chunk);written=DWORD()
            api.checked(api.WriteFile(handle.get(),buffer,len(chunk),c.byref(written),None),'FixtureSinkWrite')
            if written.value!=len(chunk): return 3
            api.checked(api.FlushFileBuffers(handle.get()),'FixtureSinkFlush')
            time.sleep(.12)
        return 0
    finally: handle.close()


def main():
    if sys.argv[1]=='canonical': return canonical_sink()
    mode=sys.argv[1]; path=Path(sys.argv[2]); result={}
    if mode=='echo': result={'result':'OFFLINE_FIXTURE_OK','startup':_STARTUP_PROOF}
    elif mode=='sleep': time.sleep(10); return 0
    elif mode=='memory':
        try: value=bytearray(128*1024*1024)
        except MemoryError: result={'allocation':'DENIED'}
        else: result={'allocation':'ADMITTED'}; del value
    elif mode in {'tree','breakaway'}:
        try:
            child=subprocess.Popen([sys.executable,'-B','-m',__spec__.name,'sleep',str(path)],
                executable=sys._base_executable,env={**os.environ,'__PYVENV_LAUNCHER__':sys.executable},
                creationflags=0x01000000 if mode=='breakaway' else 0,close_fds=True)
        except OSError as error:
            if mode!='breakaway': raise
            result={'breakaway_winerror':error.winerror}
        else:
            result={'child_pid':child.pid}
            if mode=='breakaway': child.terminate(); child.wait(timeout=2)
    else: return 3
    raw=json.dumps(result,sort_keys=True).encode()
    if len(raw)>4096: return 3
    with path.open('xb') as stream: stream.write(raw); stream.flush(); os.fsync(stream.fileno())
    if mode=='tree': time.sleep(10)
    return 0


if __name__=='__main__': raise SystemExit(main())


