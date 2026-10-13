"""Exact120-second task for one independent audit attempt; no Final consumption."""
from datetime import datetime,timedelta
from .data.encoding import canonical
from .data.errors import DataError
from .domain import TaskSpec
from .review_evidence import sha
from .final_audit_request import read_request,artifact

OUTPUT_CONTRACT=dict(schema='consumed-final-audit-frame-v1',kind='final_audit',payload='consumed-final-independent-report-v1',maximum_bytes=2*1024**2,authority='COMMITTED_OWNER_AND_NATIVE_RECEIPT_REQUIRED')
OUTPUT_SHA256=sha(canonical(OUTPUT_CONTRACT))
ACCEPTANCE=['original completed Final remains unchanged','independent native auditor and manifest match','source fit predictions accounting policy qualification reconstructed']


def _check(ok):
    if not ok:raise DataError('FINAL_AUDIT_TASK_INVALID')


def build_task(root,raw,request_artifact,*,now):
    from .foundation import fixture_spec
    try:
        _check(type(now) is datetime and now.tzinfo is not None and now.utcoffset()==timedelta(0))
        v=read_request(raw,expected_sha256=sha(raw));task=v['task_id'];original=v['original'];frame=original['frame'];manifest=v['manifest_artifact'];a=artifact(request_artifact,64*1024)
        _check(a['task_id']==task and a['path']==f"artifacts/runs/{task}/final_audit/input/attempt-{v['attempt']:02}.json" and a['size_bytes']==len(raw) and a['sha256']==sha(raw))
        p=fixture_spec(root,task).to_payload();_check(p['code_sha256']==v['auditor_runtime']['package_sha256'] and p['lock_sha256']==v['auditor_runtime']['lock_sha256'])
        p.update(role='experiment_auditor',parent_task_id=original['evaluation_id'],campaign_id=original['evaluation_id'],created_at=now.isoformat(),deadline_at=(now+timedelta(seconds=120)).isoformat(),input_hashes=[a['sha256'],frame['sha256'],manifest['sha256']],output_schema_sha256=OUTPUT_SHA256,acceptance_checks=list(ACCEPTANCE))
        p['permissions'].update(filesystem_bundle=[a['path'],frame['path'],manifest['path']],output_directory=f'artifacts/runs/{task}/final_audit')
        p['budget'].update(wall_seconds=120,cpu_threads=4,ram_bytes=4*1024**3,output_bytes=2*1024**2)
        return TaskSpec(p,project_root=root)
    except (ValueError,TypeError,KeyError,AttributeError,OverflowError,RecursionError):raise DataError('FINAL_AUDIT_TASK_INVALID') from None


def validate_task(root,payload,raw,request_artifact):
    try:
        TaskSpec(payload,project_root=root)
        expected=build_task(root,raw,request_artifact,now=datetime.fromisoformat(payload['created_at'])).to_payload()
        _check(canonical(payload)==canonical(expected));return expected
    except (ValueError,TypeError,KeyError,AttributeError,OverflowError,RecursionError):raise DataError('FINAL_AUDIT_TASK_INVALID') from None


def inspect_recorded_task(root,payload,raw,request_artifact):
    """Read-only v1 contract check under recorded pins; never grants launch authority."""
    try:
        TaskSpec(payload,project_root=root);v=read_request(raw,expected_sha256=sha(raw));task=v['task_id'];a=artifact(request_artifact,65536)
        _check(a['task_id']==task and a['path']==f"artifacts/runs/{task}/final_audit/input/attempt-{v['attempt']:02}.json" and a['size_bytes']==len(raw) and a['sha256']==sha(raw))
        now=datetime.fromisoformat(payload['created_at']);_check(now.tzinfo is not None and now.utcoffset()==timedelta(0));frame=v['original']['frame'];manifest=v['manifest_artifact'];eid=v['original']['evaluation_id']
        expected=dict(schema_version='1',record_type='TaskSpec',task_id=task,parent_task_id=eid,campaign_id=eid,role='experiment_auditor',kind='OFFLINE_FIXTURE',created_at=now.isoformat(),deadline_at=(now+timedelta(seconds=120)).isoformat(),
            input_hashes=[a['sha256'],frame['sha256'],manifest['sha256']],code_sha256=v['auditor_runtime']['package_sha256'],lock_sha256=v['auditor_runtime']['lock_sha256'],output_schema_sha256=OUTPUT_SHA256,model_identity=None,acceptance_checks=list(ACCEPTANCE),
            permissions=dict(tools=['trusted_fixture'],filesystem_bundle=[a['path'],frame['path'],manifest['path']],output_directory=f'artifacts/runs/{task}/final_audit',network_destinations=[],protected_data=False,broker=False,shell=False),
            budget=dict(cpu_threads=4,ram_bytes=4*1024**3,output_bytes=2*1024**2,wall_seconds=120,max_attempts=2,ai_requests=0,gpu_training=False,input_tokens=0,output_tokens=0,request_deadline_seconds=0),
            clock=dict(state='REGISTERED',active_elapsed_seconds=0,active_started_at=None,manual_wait_started_at=None,manual_deadline_at=None,process_lease_id=None,cpu_reserved=False))
        _check(canonical(payload)==canonical(expected));return expected
    except (ValueError,TypeError,KeyError,AttributeError,OverflowError,RecursionError):raise DataError('FINAL_AUDIT_TASK_INVALID') from None
