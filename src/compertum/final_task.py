"""Exact per-attempt tasks within the consumed final transaction's total budget."""
from datetime import datetime,timedelta,timezone
import hashlib
from .data.encoding import canonical
from .data.errors import DataError
from .domain import TaskSpec
from .evaluation_protocol import identifier,digest
from .final_request import read_request

OUTPUT_CONTRACT=dict(schema='synthetic-campaign-review-frame-v3',kind='final',payload='generated-final-batch-v1',maximum_bytes=16*1024**2,authority='COMMITTED_OWNER_AND_NATIVE_RECEIPT_REQUIRED')
OUTPUT_SHA256=hashlib.sha256(canonical(OUTPUT_CONTRACT)).hexdigest()
ACCEPTANCE=['sealed plan and consumption match','native attempt and environment match','complete framed result hashes match']

def _check(ok):
    if not ok:raise DataError('FINAL_TASK_INVALID')

def build_task(root,raw,request_artifact,*,charged_ms,now):
    from .foundation import fixture_spec
    try:
        _check(type(charged_ms) is int and 0<=charged_ms<120000)
        # TaskSpec uses integer seconds. Round prior use up, never add time.
        remaining=(120000-charged_ms)//1000;_check(remaining>=1)
        _check(type(now) is datetime and now.tzinfo is not None and now.utcoffset()==timedelta(0))
        v=read_request(raw,expected_sha256=hashlib.sha256(raw).hexdigest());plan=v['plan'];eid=plan['evaluation_id'];source=v['source_artifact']
        a=request_artifact;_check(type(a) is dict and set(a)=={'artifact_id','task_id','path','size_bytes','sha256'})
        identifier(a['artifact_id']);_check(a['task_id']==eid and a['path']==f"artifacts/runs/{eid}/input/final/attempt-{v['number']:02}.json")
        _check(type(a['size_bytes']) is int and a['size_bytes']==len(raw) and digest(a['sha256'])==hashlib.sha256(raw).hexdigest())
        p=fixture_spec(root,eid).to_payload();_check(p['code_sha256']==plan['runtime']['package_sha256'] and p['lock_sha256']==plan['runtime']['lock_sha256'])
        p.update(parent_task_id=source['task_id'],campaign_id=source['task_id'],created_at=now.isoformat(),deadline_at=(now+timedelta(seconds=remaining)).isoformat(),input_hashes=[a['sha256'],source['sha256']],output_schema_sha256=OUTPUT_SHA256,acceptance_checks=list(ACCEPTANCE))
        p['permissions'].update(filesystem_bundle=[a['path'],source['path']],output_directory=f'artifacts/runs/{eid}/final')
        p['budget'].update(wall_seconds=remaining,cpu_threads=4,ram_bytes=4*1024**3,output_bytes=16*1024**2)
        return TaskSpec(p,project_root=root)
    except (ValueError,TypeError,KeyError,AttributeError,OverflowError,RecursionError):raise DataError('FINAL_TASK_INVALID') from None

def validate_task(root,payload,raw,request_artifact,*,charged_ms):
    try:
        TaskSpec(payload,project_root=root)
        expected=build_task(root,raw,request_artifact,charged_ms=charged_ms,now=datetime.fromisoformat(payload['created_at'])).to_payload()
        _check(canonical(payload)==canonical(expected));return expected
    except (ValueError,TypeError,KeyError,AttributeError,OverflowError,RecursionError):raise DataError('FINAL_TASK_INVALID') from None
