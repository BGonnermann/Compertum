"""Closed request for auditing an existing consumed Final; no admission authority."""
import json
from .data.encoding import canonical
from .data.errors import DataError
from .evaluation_protocol import identifier,digest,identity
from .final_plan import read_plan
from .review_evidence import sha
from .runtime.job_identity import validate_execution_identity
from .runtime.auditor_environment import validate_expected,expected_from_manifest
from .environment_manifest import read_manifest

MAXIMUM=64*1024
ORIGINAL_FIELDS=set('schema seal_id evaluation_id plan plan_sha256 consumption_sha256 seal_head guard_head dispatch_sha256 request_artifact task_artifact source_artifact frame payload_sha256 payload_bytes author original_exit_sha256 original_closure_sha256 original_result_sha256'.split())
FIELDS={'schema','task_id','attempt','original','manifest_artifact','auditor_environment','auditor_runtime','financial_accepted','full_M3'}


def _check(ok):
    if not ok:raise DataError('FINAL_AUDIT_REQUEST_INVALID')


def artifact(value,maximum):
    _check(type(value) is dict and set(value)=={'artifact_id','task_id','path','size_bytes','sha256'})
    identifier(value['artifact_id']);identifier(value['task_id']);digest(value['sha256'])
    _check(type(value['size_bytes']) is int and 0<value['size_bytes']<=maximum)
    _check(type(value['path']) is str and len(value['path'])<=1024)
    return value


def original_evidence(value):
    _check(type(value) is dict and set(value)==ORIGINAL_FIELDS and value['schema']=='completed-final-evidence-v1')
    p,_=read_plan(canonical(value['plan']),digest(value['plan_sha256']));eid=p['evaluation_id']
    _check(value['seal_id']==p['seal_id'] and value['evaluation_id']==eid)
    for k in ('consumption_sha256','dispatch_sha256','payload_sha256','original_exit_sha256','original_closure_sha256','original_result_sha256'):digest(value[k])
    for name in ('seal_head','guard_head'):
        head=value[name];_check(type(head) is dict and set(head)=={'sequence','sha256'} and type(head['sequence']) is int and 1<=head['sequence']<=256);digest(head['sha256'])
    req=artifact(value['request_artifact'],32768);task=artifact(value['task_artifact'],64*1024);frame=artifact(value['frame'],16*1024**2);source=artifact(value['source_artifact'],20*1024**2)
    _check(all(a['task_id']==eid for a in (req,task,frame)) and source['task_id']!=eid and source['path']==f"artifacts/runs/{source['task_id']}/baseline/inputs.json")
    numbers=[n for n in (1,2) if req['path']==f'artifacts/runs/{eid}/input/final/attempt-{n:02}.json' and task['path']==f'artifacts/runs/{eid}/input/final/task-attempt-{n:02}.json' and frame['path']==f'artifacts/runs/{eid}/final/attempt-{n:02}.final']
    _check(len(numbers)==1 and type(value['payload_bytes']) is int and 0<value['payload_bytes']<frame['size_bytes'])
    n=value['author'];validate_execution_identity(n)
    _check(n['schema']=='native-template-execution-v3' and n['role']=='experiment_runner' and n['task_id']==eid and n['task_sha256']==task['sha256'])
    _check(n['code_sha256']==p['runtime']['package_sha256'] and n['lock_sha256']==p['runtime']['lock_sha256'] and n['clean_environment']['lane']=='source' and n['clean_environment']['run_id']==source['task_id'])
    return value


def read_request(raw,*,expected_sha256):
    try:
        _check(type(raw) is bytes and 0<len(raw)<=MAXIMUM and sha(raw)==digest(expected_sha256))
        v=json.loads(raw);_check(type(v) is dict and set(v)==FIELDS and canonical(v)==raw and v['schema']=='consumed-final-audit-request-v1')
        task=identifier(v['task_id']);_check(type(v['attempt']) is int and 1<=v['attempt']<=2 and v['financial_accepted'] is False and v['full_M3'] is False)
        old=original_evidence(v['original']);_check(task not in (old['evaluation_id'],old['source_artifact']['task_id']))
        manifest=artifact(v['manifest_artifact'],4*1024**2)
        _check(manifest['task_id']==task and manifest['path']==f'artifacts/runs/{task}/final_audit/input/environment.json')
        expected=validate_expected(v['auditor_environment']);_check(expected['task_id']==task and expected['manifest_sha256']==manifest['sha256'])
        identity(v['auditor_runtime']);return v
    except (ValueError,TypeError,KeyError,AttributeError,OverflowError,RecursionError):raise DataError('FINAL_AUDIT_REQUEST_INVALID') from None


def build_request(task_id,attempt,original,manifest_artifact,manifest_raw):
    value=read_manifest(manifest_raw,expected_sha256=manifest_artifact['sha256'])
    _check(len(manifest_raw)==manifest_artifact['size_bytes'])
    result=dict(schema='consumed-final-audit-request-v1',task_id=task_id,attempt=attempt,original=original,manifest_artifact=manifest_artifact,
        auditor_environment=expected_from_manifest(manifest_raw,manifest_artifact['sha256'],task_id),auditor_runtime=value['runtime'],financial_accepted=False,full_M3=False)
    raw=canonical(result);read_request(raw,expected_sha256=sha(raw));return raw
