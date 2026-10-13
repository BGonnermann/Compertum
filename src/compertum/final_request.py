"""Bounded final request bytes. Structural agreement is not owner admission."""
import hashlib,json
from uuid import UUID,uuid5
from .data.encoding import canonical
from .data.errors import DataError
from .evaluation_protocol import identifier,digest
from .final_plan import read_plan

MAXIMUM=32768
FIELDS={'schema','plan','plan_sha256','consumption_sha256','number','attempt_id','source_artifact','financial_accepted'}

def _check(ok):
    if not ok:raise DataError('FINAL_REQUEST_INVALID')

def read_request(raw,*,expected_sha256):
    try:
        _check(type(raw) is bytes and 0<len(raw)<=MAXIMUM and hashlib.sha256(raw).hexdigest()==digest(expected_sha256))
        v=json.loads(raw);_check(type(v) is dict and set(v)==FIELDS and canonical(v)==raw)
        _check(v['schema']=='synthetic-final-request-v1' and v['financial_accepted'] is False)
        plan,_=read_plan(canonical(v['plan']),digest(v['plan_sha256']));digest(v['consumption_sha256'])
        _check(type(v['number']) is int and v['number'] in (1,2))
        _check(identifier(v['attempt_id'])==str(uuid5(UUID(plan['evaluation_id']),f"synthetic-final-attempt-{v['number']}")))
        a=v['source_artifact'];_check(type(a) is dict and set(a)=={'artifact_id','task_id','path','size_bytes','sha256'})
        identifier(a['artifact_id']);identifier(a['task_id']);digest(a['sha256'])
        _check(a['task_id']!=plan['evaluation_id'] and a['path']==f"artifacts/runs/{a['task_id']}/baseline/inputs.json")
        _check(type(a['size_bytes']) is int and 0<a['size_bytes']<=20*1024**2)
        return v
    except (ValueError,TypeError,KeyError,AttributeError,RecursionError,OverflowError):raise DataError('FINAL_REQUEST_INVALID') from None

def build_request(plan,*,plan_sha256,consumption_sha256,number,source_artifact):
    try:
        raw=canonical(dict(schema='synthetic-final-request-v1',plan=plan,plan_sha256=plan_sha256,consumption_sha256=consumption_sha256,number=number,attempt_id=str(uuid5(UUID(plan['evaluation_id']),f'synthetic-final-attempt-{number}')),source_artifact=source_artifact,financial_accepted=False))
        read_request(raw,expected_sha256=hashlib.sha256(raw).hexdigest());return raw
    except (ValueError,TypeError,KeyError,AttributeError,RecursionError,OverflowError):raise DataError('FINAL_REQUEST_INVALID') from None
