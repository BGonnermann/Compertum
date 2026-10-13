"""Exact v1 historical Final task inspection; never grants launch authority.

Only the completed-Final evidence reader may use this contract. New dispatches
continue through final_task.build_task/validate_task and current runtime pins.
"""
from datetime import datetime,timedelta
import hashlib
from .data.encoding import canonical
from .data.errors import DataError
from .domain import TaskSpec
from .evaluation_protocol import identifier,digest
from .final_request import read_request
from .final_task import OUTPUT_SHA256,ACCEPTANCE


def _check(ok):
    if not ok:raise DataError('HISTORICAL_FINAL_TASK_INVALID')


def validate_historical_task(root,payload,raw,request_artifact,*,charged_ms):
    """Validate declared old bytes only; owner must prove completed publication."""
    try:
        TaskSpec(payload,project_root=root)
        _check(type(charged_ms) is int and 0<=charged_ms<120000)
        remaining=(120000-charged_ms)//1000;_check(remaining>=1)
        now=datetime.fromisoformat(payload['created_at'])
        _check(now.tzinfo is not None and now.utcoffset()==timedelta(0))
        v=read_request(raw,expected_sha256=hashlib.sha256(raw).hexdigest());p=v['plan'];eid=p['evaluation_id'];source=v['source_artifact']
        a=request_artifact;_check(type(a) is dict and set(a)=={'artifact_id','task_id','path','size_bytes','sha256'})
        identifier(a['artifact_id']);_check(a['task_id']==eid and a['path']==f"artifacts/runs/{eid}/input/final/attempt-{v['number']:02}.json")
        _check(type(a['size_bytes']) is int and a['size_bytes']==len(raw) and digest(a['sha256'])==hashlib.sha256(raw).hexdigest())
        # Retained contract reconstruction deliberately observes no current code pin.
        expected=dict(schema_version='1',record_type='TaskSpec',task_id=eid,parent_task_id=source['task_id'],campaign_id=source['task_id'],
            role='experiment_runner',kind='OFFLINE_FIXTURE',created_at=now.isoformat(),deadline_at=(now+timedelta(seconds=remaining)).isoformat(),
            input_hashes=[a['sha256'],source['sha256']],code_sha256=p['runtime']['package_sha256'],lock_sha256=p['runtime']['lock_sha256'],
            output_schema_sha256=OUTPUT_SHA256,model_identity=None,acceptance_checks=list(ACCEPTANCE),
            permissions=dict(tools=['trusted_fixture'],filesystem_bundle=[a['path'],source['path']],output_directory=f'artifacts/runs/{eid}/final',network_destinations=[],protected_data=False,broker=False,shell=False),
            budget=dict(cpu_threads=4,ram_bytes=4*1024**3,output_bytes=16*1024**2,wall_seconds=remaining,max_attempts=2,ai_requests=0,gpu_training=False,input_tokens=0,output_tokens=0,request_deadline_seconds=0),
            clock=dict(state='REGISTERED',active_elapsed_seconds=0,active_started_at=None,manual_wait_started_at=None,manual_deadline_at=None,process_lease_id=None,cpu_reserved=False))
        _check(canonical(payload)==canonical(expected));return expected
    except (ValueError,TypeError,KeyError,AttributeError,OverflowError,RecursionError):raise DataError('HISTORICAL_FINAL_TASK_INVALID') from None
