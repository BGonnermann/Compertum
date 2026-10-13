"""Registered pure replay over exactly two inherited file handles; no state store."""
from .startup import require_entrypoint_startup
_STARTUP_PROOF=require_entrypoint_startup() if __name__=='__main__' else None

import ctypes as c
import hashlib,json,sys
from ._windows import WindowsAPI,OwnedHandle,DWORD
from compertum.data.errors import DataError
from compertum.data.snapshot import canonical,validate_snapshot
from compertum.simulation.runs import unit_schedule,runtime_identity,compute_unit
from compertum.simulation.engine import replay
from compertum.simulation.worker_record import pack_result


def compute(raw,digest,unit):
    if hashlib.sha256(raw).hexdigest()!=digest:raise DataError('RUN_ARTIFACT_CORRUPT')
    bundle=json.loads(raw)
    if bundle['identity']!=json.loads(canonical(runtime_identity())):raise DataError('RUN_IDENTITY_CHANGED')
    units=unit_schedule(bundle)
    if bundle['units']!=[list(v) for v in units] or type(unit) is not int or not 0<=unit<len(units):raise DataError('RUN_STATE_CORRUPT')
    result=compute_unit(bundle,unit)
    return pack_result(result.content,digest)


def main():
    api=WindowsAPI();source=OwnedHandle(api,int(sys.argv[1]));sink=OwnedHandle(api,int(sys.argv[2]))
    size=int(sys.argv[3]);digest=sys.argv[4];unit=int(sys.argv[5]);maximum=int(sys.argv[6])
    if not 0<size<=20*1024**2 or not 0<maximum<=16*1024**2:return 4
    for handle in (source,sink):
        if not api.handle_flags(handle)&1:return 4
        api.set_inheritable(handle,False)
    try:
        raw=bytearray()
        while len(raw)<size:
            count=min(1024**2,size-len(raw));buffer=c.create_string_buffer(count);read=DWORD()
            api.checked(api.ReadFile(source.get(),buffer,count,c.byref(read),None),'ReplayRead')
            if not read.value:return 4
            raw.extend(buffer.raw[:read.value])
        result=compute(bytes(raw),digest,unit)
        if len(result)>maximum:return 4
        written_total=0
        for offset in range(0,len(result),8*1024**2):
            chunk=result[offset:offset+8*1024**2]
            if written_total+len(chunk)>maximum:return 4
            buffer=c.create_string_buffer(chunk);written=DWORD()
            api.checked(api.WriteFile(sink.get(),buffer,len(chunk),c.byref(written),None),'ReplayWrite')
            if written.value!=len(chunk):return 5
            written_total+=written.value
        api.checked(api.FlushFileBuffers(sink.get()),'ReplayFlush')
        return 0
    except OSError:return 5
    except Exception:return 4
    finally:source.close();sink.close()


if __name__=='__main__':raise SystemExit(main())
