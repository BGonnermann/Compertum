"""Closed final calculation through inherited inputs and a bounded output handle."""
import ctypes as c
import hashlib,json,os
from ._windows import WindowsAPI,OwnedHandle,DWORD
from .inherited_input import read_input
from .campaign_environment import verify_input,validate_expected
from .identity_pins import runtime_identity
from .startup_record import validate_proof
from .startup import expected_clean_environment
from compertum.data.encoding import canonical
from compertum.data.errors import DataError
from compertum.final_request import read_request,MAXIMUM
from compertum.review_frame import result_binding,pack_review

MIB=1024**2

def _check(ok):
    if not ok:raise DataError('FINAL_WORKER_INVALID')

def compute(raw,request_sha256,source,*,startup,expected):
    v=read_request(raw,expected_sha256=request_sha256);a=v['source_artifact'];plan=v['plan']
    validate_proof(startup);validate_expected(expected)
    _check(startup['pid']==os.getpid() and expected['lane']=='source' and expected['run_id']==a['task_id'])
    _check(type(source) is bytes and len(source)==a['size_bytes'] and hashlib.sha256(source).hexdigest()==a['sha256'])
    observed=verify_input(source,a['sha256'],expected=expected)
    _check(observed=={**expected,'schema':'observed-clean-environment-v1'})
    # verify_input has already proved the exact canonical source envelope.
    pair=json.loads(source)['clean_pair']['record']
    _check(plan['project_id']==pair['project_id'] and plan['seal_id']==pair['source']['seal_id']
        and plan['inputs']['input_sha256']==pair['holdout_manifest_sha256'])
    identity=runtime_identity();_check(canonical(identity)==canonical(plan['runtime']))
    # No numerical/calendar imports or generated prices precede these gates.
    from compertum.modeling.generated_final import evaluate_generated_final
    result=evaluate_generated_final(canonical(plan),expected_sha256=v['plan_sha256'])
    _check(hashlib.sha256(result.content).hexdigest()==result.sha256)
    return pack_review(result.content,result_binding('final',plan['evaluation_id'],a['task_id'],request_sha256,identity,os.getpid(),startup=startup,environment=observed))

def main(args,*,startup):
    handles=[];code=6
    try:
        _check(len(args)==6);request,sink,size=int(args[0]),int(args[1]),int(args[2]);pin=args[3];source=int(args[4]);maximum=int(args[5])
        values=[request,sink,source];_check(len(set(values))==3 and all(v>0 for v in values) and 0<size<=MAXIMUM and maximum==16*MIB)
        api=WindowsAPI();handles=[OwnedHandle(api,v) for v in values]
        for h in handles:_check(api.handle_flags(h)&1);api.set_inheritable(h,False)
        raw=read_input(api,handles[0],size);v=read_request(raw,expected_sha256=pin)
        source_raw=read_input(api,handles[2],v['source_artifact']['size_bytes'])
        result=compute(raw,pin,source_raw,startup=startup,expected=expected_clean_environment(startup))
        _check(len(result)<=maximum)
        for offset in range(0,len(result),8*MIB):
            chunk=result[offset:offset+8*MIB];buffer=c.create_string_buffer(chunk);written=DWORD()
            api.checked(api.WriteFile(handles[1].get(),buffer,len(chunk),c.byref(written),None),'FinalWrite')
            if written.value!=len(chunk):raise OSError('FINAL_SHORT_WRITE')
        api.checked(api.FlushFileBuffers(handles[1].get()),'FinalFlush');code=0
    except Exception as error:code=5 if isinstance(error,OSError) else 4 if isinstance(error,DataError) else 6
    finally:
        for h in handles:
            try:h.close()
            except Exception:code=6
    return code
