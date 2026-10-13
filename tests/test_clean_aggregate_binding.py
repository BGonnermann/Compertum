"""Pure native evidence consistency; constructed packets grant no authority."""
from dataclasses import asdict
from copy import deepcopy
import hashlib
from uuid import uuid4
import pytest
from compertum.data.encoding import canonical
from compertum.data.errors import DataError
from compertum.campaign_contract import UNITS
from compertum.aggregate_evidence import expected_unit_request,bind_unit_audit
from compertum.runtime.identity import PeerObservation
from compertum.runtime.job_identity import capture_execution_identity
from test_clean_native_record import pins,native


def sha(value):return hashlib.sha256(canonical(value)).hexdigest()

def receipt(n):return dict(pid=n['process']['pid'],exit_code=0,timed_out=False,active_processes=0,assigned_before_resume=True,affinity=15,memory_limit=4*1024**3,peak_job_memory=1024**2,observed_child_pids=[],observed_children_exited=True,execution_identity=n)

def artifact(task,path):return dict(artifact_id=str(uuid4()),task_id=task,path=path,size_bytes=100,sha256='1'*64)


def evidence():
 expected=pins();run=expected['run_id'];author=native(expected);task=str(uuid4())
 source=dict(run_id=run,state='COMPLETED',identity=dict(package_sha256='c'*64,lock_sha256='d'*64,python='3.14.7',distributions=[['a','1']]),clean_environment=expected,
  input_artifact=artifact(run,f'artifacts/runs/{run}/baseline/inputs.json'),protocol_seal=dict(seal_id=str(uuid4()),protocol_sha256='2'*64,ticket_sha256='3'*64,admission_event_sha256='4'*64),
  attempts=[dict(unit=0,status='COMPLETED',native_execution=author,job_receipt=receipt(author))],
  outcomes={UNITS[0].key:dict(unit=0,identity=asdict(UNITS[0]),status='COMPLETED',artifact=artifact(run,f'artifacts/runs/{run}/baseline/unit-00-attempt-1.campaign'),payload_sha256='5'*64,dependency_sha256=None)})
 request=expected_unit_request(source,0);inputs=[request['input_artifact'],request['result']['artifact']]
 payload=dict(task_id=task,role='experiment_auditor',parent_task_id=run,campaign_id=run,code_sha256='c'*64,lock_sha256='d'*64,
  input_hashes=[a['sha256'] for a in inputs],permissions=dict(filesystem_bundle=[a['path'] for a in inputs],output_directory=f'artifacts/runs/{task}/audit'),budget=dict(wall_seconds=120,cpu_threads=4,ram_bytes=4*1024**3,output_bytes=16*1024**2,max_attempts=2))
 auditor=capture_execution_identity(PeerObservation(456,987654321,'S-1-5-21-1-2-3-1001','S-1-5-5-100-200'),payload,'compertum.runtime.audit_worker',startup=author['startup'],clean_environment=expected)
 path=f'artifacts/runs/{task}/audit/attempt-1.json'
 attempt=dict(number=1,status='COMPLETED',output_path=path,reservation_id=str(uuid4()),task=payload,native_execution=auditor,job_receipt=receipt(auditor))
 audit=dict(task_id=task,request=request,request_sha256=sha(request),state='COMPLETED',owner='fixture',attempts=[attempt],artifact=artifact(task,path),audit_sha256='6'*64,financial_accepted=False,last_transition='COMPLETED',updated_at='2026-10-10T12:00:00+00:00')
 return source,audit


@pytest.mark.parametrize('fault',['strip','lane','prior_attempt'])
def test_aggregate_cannot_downgrade_or_relabel_auditor_environment(fault):
 source,audit=evidence();assert bind_unit_audit(audit,source)['index']==0
 if fault=='prior_attempt':
  old=deepcopy(audit['attempts'][0]);old.update(status='INTERRUPTED',reason='WORKER_FAILED');old['job_receipt']['exit_code']=5
  audit['attempts'][0]['number']=2;audit['attempts'][0]['output_path']=audit['artifact']['path']=audit['attempts'][0]['output_path'].replace('attempt-1','attempt-2')
  audit['attempts'].insert(0,old);target=old
 else:target=audit['attempts'][-1]
 n=target['native_execution']
 if fault=='lane':n['clean_environment']={**n['clean_environment'],'lane':'wheel'}
 else:n.pop('clean_environment');n['schema']='native-template-execution-v2'
 target['job_receipt']['execution_identity']=n
 with pytest.raises(DataError):bind_unit_audit(audit,source)
