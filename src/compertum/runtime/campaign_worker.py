"""Fixed campaign unit over explicit inherited handles; no model path discovery."""
from .startup import require_entrypoint_startup,expected_clean_environment
_STARTUP_PROOF=require_entrypoint_startup() if __name__=='__main__' else None

import ctypes as c
import hashlib,sys
from ._windows import WindowsAPI,OwnedHandle,DWORD
from compertum.data.errors import DataError
from compertum.campaign_contract import UNITS,DETERMINISTIC
from .inherited_input import read_input as _read
from .campaign_environment import verify_input
from .identity_pins import runtime_identity
from compertum.simulation.campaign_record import pack_result,verify_result

MIB=1024**2


def compute(raw,digest,unit,*,dependency_raw=None,dependency_digest=None,dependency_payload_sha256=None):
    if not isinstance(raw,bytes) or not 0<len(raw)<=20*MIB or hashlib.sha256(raw).hexdigest()!=digest:raise DataError('RUN_ARTIFACT_CORRUPT')
    if type(unit) is not int or not 0<=unit<len(UNITS):raise DataError('CAMPAIGN_UNIT_INVALID')
    from compertum.modeling.campaign import CampaignInput,compute_campaign_unit
    from compertum.modeling.checkpoints import FitCheckpoint
    parent=UNITS[unit].fit_unit;checkpoint=None
    if parent is None:
        if any(v is not None for v in (dependency_raw,dependency_digest,dependency_payload_sha256)):raise DataError('CAMPAIGN_DEPENDENCY_INVALID')
    else:
        if not isinstance(dependency_raw,bytes) or not 0<len(dependency_raw)<=16*MIB or hashlib.sha256(dependency_raw).hexdigest()!=dependency_digest:raise DataError('CAMPAIGN_DEPENDENCY_INVALID')
        body=verify_result(dependency_raw,digest,parent)
        if hashlib.sha256(body).hexdigest()!=dependency_payload_sha256:raise DataError('CAMPAIGN_DEPENDENCY_INVALID')
        checkpoint=FitCheckpoint(body,dependency_payload_sha256)
    result=compute_campaign_unit(CampaignInput(raw,digest),unit,identity=runtime_identity(),fit_checkpoint=checkpoint,expected_fit_sha256=dependency_payload_sha256)
    return pack_result(result.content,digest,unit,dependency_payload_sha256)


def exit_code_for_error(error):
    if isinstance(error,OSError):return 5
    if isinstance(error,DataError) and error.code in DETERMINISTIC:return 4
    return 6


def main():
    if len(sys.argv)>1 and sys.argv[1]=='final':
        from .final_worker import main as final_main
        return final_main(sys.argv[2:],startup=_STARTUP_PROOF)
    if len(sys.argv)>1 and sys.argv[1]=='scorecard':
        from .campaign_review_worker import main as review_main
        return review_main('scorecard',sys.argv[2:],startup=_STARTUP_PROOF)
    handles=[];code=6
    try:
        if len(sys.argv)!=11:raise DataError('CAMPAIGN_HANDLES_INVALID')
        source_value,sink_value,size=int(sys.argv[1]),int(sys.argv[2]),int(sys.argv[3])
        digest=sys.argv[4];unit=int(sys.argv[5]);maximum=int(sys.argv[6]);dependency_value=int(sys.argv[7]);dependency_size=int(sys.argv[8])
        dependency_digest=sys.argv[9];dependency_payload_sha256=sys.argv[10]
        if not 0<size<=20*MIB or not 0<maximum<=16*MIB:raise DataError('CAMPAIGN_HANDLES_INVALID')
        values=[source_value,sink_value]+([dependency_value] if dependency_value else [])
        if len(set(values))!=len(values) or any(v<=0 for v in values):raise DataError('CAMPAIGN_HANDLES_INVALID')
        api=WindowsAPI();handles=[OwnedHandle(api,v) for v in values]
        for handle in handles:
            if not api.handle_flags(handle)&1:raise DataError('CAMPAIGN_HANDLES_INVALID')
            api.set_inheritable(handle,False)
        raw=_read(api,handles[0],size);environment=verify_input(raw,digest,expected=expected_clean_environment(_STARTUP_PROOF));kwargs={}
        if dependency_value:
            if not 0<dependency_size<=16*MIB:raise DataError('CAMPAIGN_HANDLES_INVALID')
            kwargs=dict(dependency_raw=_read(api,handles[2],dependency_size),dependency_digest=dependency_digest,dependency_payload_sha256=dependency_payload_sha256)
        elif dependency_size!=0 or dependency_digest!='-' or dependency_payload_sha256!='-':raise DataError('CAMPAIGN_HANDLES_INVALID')
        result=compute(raw,digest,unit,**kwargs)
        result=pack_result(result.split(b'\n',1)[1],digest,unit,dependency_payload_sha256 if dependency_value else None,startup=_STARTUP_PROOF,environment=environment)
        if len(result)>maximum:raise DataError('OUTPUT_BOUND')
        for offset in range(0,len(result),8*MIB):
            chunk=result[offset:offset+8*MIB];buffer=c.create_string_buffer(chunk);written=DWORD()
            api.checked(api.WriteFile(handles[1].get(),buffer,len(chunk),c.byref(written),None),'CampaignWrite')
            if written.value!=len(chunk):raise OSError('CAMPAIGN_SHORT_WRITE')
        api.checked(api.FlushFileBuffers(handles[1].get()),'CampaignFlush')
        code=0
    except Exception as error:code=exit_code_for_error(error)
    finally:
        for handle in handles:
            try:handle.close()
            except Exception:code=6
    return code


if __name__=='__main__':raise SystemExit(main())
