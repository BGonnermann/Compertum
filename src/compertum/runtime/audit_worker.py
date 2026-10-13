"""Deterministic independent audit worker over readonly inherited evidence handles.

This output requires a coordinator-held native receipt before it has authority.
"""
from .startup import require_entrypoint_startup,expected_clean_environment
_STARTUP_PROOF=require_entrypoint_startup() if __name__=='__main__' else None

import ctypes as c
import hashlib,json,os,sys
from uuid import UUID
from ._windows import WindowsAPI,OwnedHandle,DWORD
from .inherited_input import read_input as _read
from .campaign_environment import verify_input
from .identity_pins import runtime_identity
from compertum.data.encoding import canonical
from compertum.data.errors import DataError
from compertum.campaign_contract import UNITS
from compertum.simulation.campaign_record import verify_result

MIB=1024**2


def _check(condition):
    if not condition:raise DataError('AUDITOR_INPUT_INVALID')


def compute(raw,digest,unit,result_raw,result_sha,*,audit_id,fit_raw=None,fit_sha=None,fit_payload_sha=None):
    try:
        from compertum.data.snapshot import validate_snapshot
        from compertum.modeling.campaign import read_campaign
        from compertum.modeling.candidate import CandidateResult
        from compertum.audit_execution import audit_execution
        _check(type(unit) is int and 0<=unit<63 and UNITS[unit].phase=='evaluate')
        _check(type(audit_id) is str and str(UUID(audit_id))==audit_id)
        identity=runtime_identity();bundle=read_campaign(raw,expected_sha256=digest,identity=identity);u=UNITS[unit]
        _check(type(result_raw) is bytes and 0<len(result_raw)<=16*MIB and hashlib.sha256(result_raw).hexdigest()==result_sha)
        parent=None
        if u.fit_unit is None:_check(fit_raw is None and fit_sha is None and fit_payload_sha is None)
        else:
            _check(type(fit_raw) is bytes and 0<len(fit_raw)<=16*MIB and hashlib.sha256(fit_raw).hexdigest()==fit_sha)
            payload=verify_result(fit_raw,digest,u.fit_unit);_check(hashlib.sha256(payload).hexdigest()==fit_payload_sha);parent=json.loads(payload)
            fields={'schema','status','financial_accepted','candidate_id','year','training_start','training_end','source_market_sha256','dataset_assembly','fit_rows','fit_rows_sha256','fit_manifest','fit_manifest_sha256','model','model_sha256'}
            _check(set(parent)==fields and parent['fit_rows_sha256']==hashlib.sha256(canonical(parent['fit_rows'])).hexdigest())
        body=verify_result(result_raw,digest,unit,fit_payload_sha);value=json.loads(body)
        if parent is not None:_check(all(value[k]==parent[k] for k in ('dataset_assembly','fit_rows','fit_manifest','fit_manifest_sha256','model','model_sha256')))
        fold=bundle['folds'][(2021,2022,2023).index(u.year)]
        if parent is not None:_check(parent['source_market_sha256']==fold['market_sha256'] and all(parent[k]==fold[k] for k in ('training_start','training_end')))
        chunks=tuple(validate_snapshot(canonical(s)) for s in fold['snapshots'])
        result=CandidateResult(body,hashlib.sha256(body).hexdigest())
        audit=audit_execution(chunks,fold['sectors'],result,candidate_id=u.candidate_id,year=u.year,training_start=fold['training_start'],training_end=fold['training_end'],start=fold['start'],end=fold['end'],scoring_as_of=fold['scoring_as_of'])
        report={'schema':'synthetic-native-unit-audit-v1','task_id':audit_id,'role':'experiment_auditor','worker_pid':os.getpid(),'unit':unit,'candidate_id':u.candidate_id,'year':u.year,'input_sha256':digest,'result_frame_sha256':result_sha,'result_payload_sha256':result.sha256,'fit_frame_sha256':fit_sha,'fit_payload_sha256':fit_payload_sha,'runtime_identity':identity,'audit_sha256':audit.sha256,'audit':json.loads(audit.content),'native_authority':'AWAITING_COORDINATOR_RECEIPT','financial_accepted':False}
        output=canonical(report);_check(len(output)<=16*MIB);return output
    except (ValueError,TypeError,KeyError,AttributeError,IndexError,OverflowError,RecursionError) as exc:
        if isinstance(exc,DataError):raise
        raise DataError('AUDITOR_INPUT_INVALID') from None


def exit_code_for_error(error):
    if isinstance(error,OSError):return 5
    if isinstance(error,DataError) and error.code.startswith('AUDIT_'):return 4
    return 6


def main():
    if len(sys.argv)>1 and sys.argv[1]=='final_audit':
        from .final_audit_worker import main as final_audit_main
        return final_audit_main(sys.argv[2:],startup=_STARTUP_PROOF)
    if len(sys.argv)>1 and sys.argv[1] in ('aggregate','pair_compare'):
        from .campaign_review_worker import main as review_main
        return review_main(sys.argv[1],sys.argv[2:],startup=_STARTUP_PROOF)
    handles=[];code=6
    try:
        if len(sys.argv)!=15:raise DataError('AUDITOR_HANDLES_INVALID')
        source,sink,size=int(sys.argv[1]),int(sys.argv[2]),int(sys.argv[3]);digest=sys.argv[4];unit=int(sys.argv[5]);maximum=int(sys.argv[6])
        result_handle,result_size,result_digest=int(sys.argv[7]),int(sys.argv[8]),sys.argv[9]
        fit_handle,fit_size,fit_digest,fit_payload_sha=int(sys.argv[10]),int(sys.argv[11]),sys.argv[12],sys.argv[13];audit_id=sys.argv[14]
        _check(0<size<=20*MIB and 0<maximum<=16*MIB and 0<result_size<=16*MIB)
        values=[source,sink,result_handle]+([fit_handle] if fit_handle else [])
        _check(len(set(values))==len(values) and all(v>0 for v in values))
        api=WindowsAPI();handles=[OwnedHandle(api,v) for v in values]
        for handle in handles:
            _check(api.handle_flags(handle)&1);api.set_inheritable(handle,False)
        raw=_read(api,handles[0],size);environment=verify_input(raw,digest,expected=expected_clean_environment(_STARTUP_PROOF));result_raw=_read(api,handles[2],result_size);kwargs={}
        if fit_handle:
            _check(0<fit_size<=16*MIB);kwargs=dict(fit_raw=_read(api,handles[3],fit_size),fit_sha=fit_digest,fit_payload_sha=fit_payload_sha)
        else:_check(fit_size==0 and fit_digest=='-' and fit_payload_sha=='-')
        result=compute(raw,digest,unit,result_raw,result_digest,audit_id=audit_id,**kwargs)
        report=json.loads(result);report.update(schema='synthetic-native-unit-audit-v2',startup=_STARTUP_PROOF)
        if environment is not None:report.update(schema='synthetic-native-unit-audit-v3',environment=environment)
        result=canonical(report)
        _check(len(result)<=maximum)
        for offset in range(0,len(result),8*MIB):
            chunk=result[offset:offset+8*MIB];buffer=c.create_string_buffer(chunk);written=DWORD()
            api.checked(api.WriteFile(handles[1].get(),buffer,len(chunk),c.byref(written),None),'AuditWrite')
            if written.value!=len(chunk):raise OSError('AUDIT_SHORT_WRITE')
        api.checked(api.FlushFileBuffers(handles[1].get()),'AuditFlush');code=0
    except Exception as error:code=exit_code_for_error(error)
    finally:
        for handle in handles:
            try:handle.close()
            except Exception:code=6
    return code


if __name__=='__main__':raise SystemExit(main())
