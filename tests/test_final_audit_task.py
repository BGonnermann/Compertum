"""Task bounds/path grants only; these fixtures do not admit an environment."""
from datetime import datetime,timezone
import json
from uuid import uuid4
import pytest
from test_final_audit_request import audit_packet,saved,environment
from compertum.data.encoding import canonical
from compertum.data.errors import DataError
from compertum.domain import ContractError,TaskSpec
from compertum.review_evidence import sha
from compertum.runtime.identity_pins import runtime_identity
from compertum import final_audit_task as m


@pytest.fixture
def task_packet(audit_packet,tmp_path):
 raw,_,_=audit_packet;v=json.loads(raw);v['auditor_runtime']=runtime_identity();raw=canonical(v);task=v['task_id']
 a=dict(artifact_id=str(uuid4()),task_id=task,path=f'artifacts/runs/{task}/final_audit/input/attempt-01.json',size_bytes=len(raw),sha256=sha(raw))
 p=m.build_task(tmp_path,raw,a,now=datetime(2026,10,12,tzinfo=timezone.utc)).to_payload()
 return raw,a,p,tmp_path


def test_exact_three_input_read_and_bounded_auditor_task(task_packet):
 raw,a,p,root=task_packet;v=json.loads(raw)
 assert p['role']=='experiment_auditor' and p['parent_task_id']==v['original']['evaluation_id']
 assert p['permissions']['filesystem_bundle']==[a['path'],v['original']['frame']['path'],v['manifest_artifact']['path']]
 assert p['budget']['wall_seconds']==120 and p['budget']['output_bytes']==2*1024**2 and p['budget']['cpu_threads']==4
 assert not any(p['permissions'][k] for k in ('broker','shell','protected_data','network_destinations'))
 assert m.validate_task(root,p,raw,a)==p


@pytest.mark.parametrize('fault',['role','parent','campaign','source','source_extra','manifest','request','output','broker','network','code','lock','hashes','wall','threads','memory','bytes','clock','deadline','schema','acceptance','float'])
def test_changed_task_cannot_preserve_audit_admission(task_packet,fault):
 raw,a,p,root=task_packet
 if fault=='role':p['role']='experiment_runner'
 elif fault=='parent':p['parent_task_id']=str(uuid4())
 elif fault=='campaign':p['campaign_id']=str(uuid4())
 elif fault=='source':p['permissions']['filesystem_bundle'][1]=f'artifacts/runs/{uuid4()}/final/attempt-01.final'
 elif fault=='source_extra':p['permissions']['filesystem_bundle'].append('artifacts/fixture-input')
 elif fault=='manifest':p['permissions']['filesystem_bundle'][2]+='.other'
 elif fault=='request':p['permissions']['filesystem_bundle'][0]=p['permissions']['filesystem_bundle'][0].replace('01.json','02.json')
 elif fault=='output':p['permissions']['output_directory']+='/other'
 elif fault=='broker':p['permissions']['broker']=True
 elif fault=='network':p['permissions']['network_destinations']=['example.invalid']
 elif fault=='code':p['code_sha256']='9'*64
 elif fault=='lock':p['lock_sha256']='9'*64
 elif fault=='hashes':p['input_hashes'][1]='9'*64
 elif fault=='wall':p['budget']['wall_seconds']=119
 elif fault=='threads':p['budget']['cpu_threads']=3
 elif fault=='memory':p['budget']['ram_bytes']=3*1024**3
 elif fault=='bytes':p['budget']['output_bytes']=3*1024**2
 elif fault=='clock':p['clock']['active_elapsed_seconds']=1
 elif fault=='deadline':p['deadline_at']='2026-10-12T00:02:01+00:00'
 elif fault=='schema':p['output_schema_sha256']='9'*64
 elif fault=='acceptance':p['acceptance_checks']=[]
 else:p['budget']['cpu_threads']=4.0
 with pytest.raises((DataError,ContractError)):m.validate_task(root,p,raw,a)


def test_older_auditor_code_cannot_launch_new_task(task_packet,monkeypatch):
 from compertum import recovery
 raw,a,p,root=task_packet;monkeypatch.setattr(recovery,'_package_hash',lambda:'9'*64)
 with pytest.raises(DataError):m.build_task(root,raw,a,now=datetime(2026,10,12,tzinfo=timezone.utc))


@pytest.mark.parametrize('fault',['source_attempt','request_attempt','count','role','output'])
def test_foreign_frame_permission_is_narrow_even_before_dispatch(task_packet,fault):
 raw,a,p,root=task_packet
 if fault=='source_attempt':p['permissions']['filesystem_bundle'][1]=p['permissions']['filesystem_bundle'][1].replace('01.final','03.final')
 elif fault=='request_attempt':p['permissions']['filesystem_bundle'][0]=p['permissions']['filesystem_bundle'][0].replace('01.json','03.json')
 elif fault=='count':p['permissions']['filesystem_bundle'].pop()
 elif fault=='role':p['role']='experiment_runner'
 else:p['permissions']['output_directory']=f"artifacts/runs/{p['task_id']}/output"
 with pytest.raises(ContractError):TaskSpec(p,project_root=root)
