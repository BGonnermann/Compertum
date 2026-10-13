"""Independent audit of an already consumed Final through three readonly handles."""
import ctypes as c
import io,json,os
from ._windows import WindowsAPI,OwnedHandle,DWORD
from .inherited_input import read_input
from .startup import expected_auditor_environment
from .startup_record import validate_proof,expected_proof
from .auditor_environment import verify_input,validate_expected
from .campaign_environment import observed_from_native
from .identity_pins import runtime_identity
from compertum.data.encoding import canonical
from compertum.data.errors import DataError
from compertum.review_evidence import sha
from compertum.final_audit_request import read_request,MAXIMUM
from compertum.environment_manifest import read_manifest
from compertum.review_frame import result_binding,pack_review,verify_review

MIB=1024**2


def _check(ok):
    if not ok:raise DataError('FINAL_AUDIT_WORKER_INVALID')


def compute(raw,request_sha256,frame,manifest,*,startup,expected):
    v=read_request(raw,expected_sha256=request_sha256);old=v['original'];author=old['author'];a=v['manifest_artifact']
    validate_proof(startup);validate_expected(expected)
    _check(startup['pid']==os.getpid() and expected==v['auditor_environment'])
    _check(type(manifest) is bytes and len(manifest)==a['size_bytes'])
    observed=verify_input(manifest,a['sha256'],expected=expected)
    _check(observed=={**expected,'schema':'observed-final-auditor-environment-v1'})
    manifest_value=read_manifest(manifest,expected_sha256=a['sha256']);identity=runtime_identity()
    _check(canonical(identity)==canonical(v['auditor_runtime'])==canonical(manifest_value['runtime']))
    _check(type(frame) is bytes and len(frame)==old['frame']['size_bytes'] and sha(frame)==old['frame']['sha256'])
    original_binding=result_binding('final',old['evaluation_id'],old['source_artifact']['task_id'],old['request_artifact']['sha256'],old['plan']['runtime'],author['process']['pid'],startup=expected_proof(author),environment=observed_from_native(author))
    proof=verify_review(io.BytesIO(frame),original_binding)
    _check(proof['payload_sha256']==old['payload_sha256'] and proof['payload_bytes']==old['payload_bytes'])
    payload=frame.split(b'\n',1)[1]
    # Exact environment and original frame checks precede numerical imports.
    from compertum.audit_generated_final import audit_generated_final
    audited=audit_generated_final(canonical(old['plan']),payload,plan_sha256=old['plan_sha256'],payload_sha256=old['payload_sha256'])
    _check(type(audited.content) is bytes and 0<len(audited.content)<=MIB and sha(audited.content)==audited.sha256)
    audit=json.loads(audited.content);_check(canonical(audit)==audited.content)
    body=canonical(dict(schema='consumed-final-independent-report-v1',original_evidence_sha256=sha(canonical(old)),audit_sha256=audited.sha256,audit=audit,financial_accepted=False,full_M3=False))
    return pack_review(body,result_binding('final_audit',v['task_id'],old['evaluation_id'],request_sha256,identity,os.getpid(),startup=startup,auditor_environment=observed))


def main(args,*,startup):
    handles=[];code=6
    try:
        _check(len(args)==7)
        request,sink,size=int(args[0]),int(args[1]),int(args[2]);pin=args[3];frame,manifest,maximum=int(args[4]),int(args[5]),int(args[6])
        values=[request,sink,frame,manifest];_check(len(set(values))==4 and all(v>0 for v in values) and 0<size<=MAXIMUM and maximum==2*MIB)
        api=WindowsAPI();handles=[OwnedHandle(api,v) for v in values]
        for h in handles:_check(api.handle_flags(h)&1);api.set_inheritable(h,False)
        raw=read_input(api,handles[0],size);v=read_request(raw,expected_sha256=pin)
        frame_raw=read_input(api,handles[2],v['original']['frame']['size_bytes']);manifest_raw=read_input(api,handles[3],v['manifest_artifact']['size_bytes'])
        result=compute(raw,pin,frame_raw,manifest_raw,startup=startup,expected=expected_auditor_environment(startup));_check(len(result)<=maximum)
        for offset in range(0,len(result),MIB):
            chunk=result[offset:offset+MIB];buffer=c.create_string_buffer(chunk);written=DWORD()
            api.checked(api.WriteFile(handles[1].get(),buffer,len(chunk),c.byref(written),None),'FinalAuditWrite')
            if written.value!=len(chunk):raise OSError('FINAL_AUDIT_SHORT_WRITE')
        api.checked(api.FlushFileBuffers(handles[1].get()),'FinalAuditFlush');code=0
    except Exception as error:code=5 if isinstance(error,OSError) else 4 if isinstance(error,DataError) else 6
    finally:
        for h in handles:
            try:h.close()
            except Exception:code=6
    return code
