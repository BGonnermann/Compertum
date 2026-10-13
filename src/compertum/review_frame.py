"""Bounded streamed review outputs; coordinator launch receipts supply authority."""
import hashlib,json,re
from uuid import UUID
from compertum.data.encoding import canonical
from compertum.data.errors import DataError
from compertum.evaluation_protocol import identity as _identity
from compertum.runtime.startup_record import validate_proof
from compertum.runtime.campaign_environment import validate_observed

MAXIMUM=16*1024**2
HEADER_MAXIMUM=64*1024
CHUNK=1024**2
KINDS={'scorecard':'experiment_runner','aggregate':'experiment_auditor','pair_compare':'experiment_auditor','final':'experiment_runner','final_audit':'experiment_auditor'}


def _check(value):
    if not value:raise DataError('REVIEW_FRAME_INVALID')


def _sha(value):
    return type(value) is str and re.fullmatch('[0-9a-f]{64}',value) is not None


def result_binding(kind,task_id,source_run_id,request_sha256,runtime_identity,worker_pid,*,startup=None,environment=None,auditor_environment=None):
    try:
        _check(type(kind) is str and kind in KINDS)
        _check(all(type(v) is str and str(UUID(v))==v for v in (task_id,source_run_id)))
        _check(task_id!=source_run_id and _sha(request_sha256))
        _check(type(worker_pid) is int and 0<worker_pid<2**32)
        value={'kind':kind,'task_id':task_id,'source_run_id':source_run_id,'request_sha256':request_sha256,
            'runtime_identity':_identity(runtime_identity),'worker_pid':worker_pid,'role':KINDS[kind],
            'native_authority':'AWAITING_COORDINATOR_RECEIPT','financial_accepted':False,'full_M3':False}
        _check((kind=='final_audit')==(auditor_environment is not None))
        if startup is not None:
            value['startup']=validate_proof(startup);_check(startup['pid']==worker_pid)
        if environment is not None:
            _check(startup is not None);value['environment']=validate_observed(environment)
        if auditor_environment is not None:
            from .runtime.auditor_environment import validate_observed as validate_auditor
            _check(startup is not None and environment is None)
            value['auditor_environment']=validate_auditor(auditor_environment)
            _check(auditor_environment['task_id']==task_id)
        return value
    except (ValueError,TypeError,AttributeError):raise DataError('REVIEW_FRAME_INVALID') from None


def _binding(value):
    _check(type(value) is dict)
    try:expected=result_binding(*(value[k] for k in ('kind','task_id','source_run_id','request_sha256','runtime_identity','worker_pid')),startup=value.get('startup'),environment=value.get('environment'),auditor_environment=value.get('auditor_environment'))
    except KeyError:raise DataError('REVIEW_FRAME_INVALID') from None
    _check(set(value)==set(expected) and canonical(value)==canonical(expected))
    return expected


def _schema(binding):
    if binding['kind']=='final_audit':return 'consumed-final-audit-frame-v1'
    return 'synthetic-campaign-review-frame-v3' if 'environment' in binding else 'synthetic-campaign-review-frame-v2' if 'startup' in binding else 'synthetic-campaign-review-frame-v1'


def pack_review(payload,binding):
    binding=_binding(binding)
    limit=2*1024**2 if binding['kind']=='final_audit' else MAXIMUM
    _check(type(payload) is bytes and 0<len(payload)<limit)
    header=canonical(dict(binding,schema=_schema(binding),payload_bytes=len(payload),payload_sha256=hashlib.sha256(payload).hexdigest()))
    _check(len(header)+1<=HEADER_MAXIMUM and len(header)+1+len(payload)<=limit)
    return header+b'\n'+payload


def verify_review(stream,expected_binding,*,maximum=MAXIMUM):
    """Verify exact framing and hashes without decoding or retaining the payload."""
    expected=_binding(expected_binding)
    _check(type(maximum) is int and 0<maximum<=MAXIMUM)
    if expected['kind']=='final_audit':maximum=min(maximum,2*1024**2)
    line=stream.readline(HEADER_MAXIMUM+1)
    _check(type(line) is bytes and 0<len(line)<=HEADER_MAXIMUM and line.endswith(b'\n'))
    try:header=json.loads(line[:-1])
    except (ValueError,UnicodeError,RecursionError):raise DataError('REVIEW_FRAME_INVALID') from None
    _check(type(header) is dict and set(header)==set(expected)|{'schema','payload_bytes','payload_sha256'})
    _check(canonical(header)+b'\n'==line and header['schema']==(_schema(expected)))
    _check(canonical({k:header[k] for k in expected})==canonical(expected))
    size=header['payload_bytes']
    _check(type(size) is int and 0<size<=maximum-len(line) and _sha(header['payload_sha256']))
    payload_hash=hashlib.sha256();frame_hash=hashlib.sha256(line);remaining=size
    while remaining:
        chunk=stream.read(min(CHUNK,remaining))
        _check(type(chunk) is bytes and 0<len(chunk)<=remaining)
        payload_hash.update(chunk);frame_hash.update(chunk);remaining-=len(chunk)
    _check(stream.read(1)==b'' and payload_hash.hexdigest()==header['payload_sha256'])
    return {'header':header,'payload_sha256':payload_hash.hexdigest(),'payload_bytes':size,
        'sha256':frame_hash.hexdigest(),'size_bytes':len(line)+size}
