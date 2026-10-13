"""Owner-built audit requests retain original author and separate auditor pins."""
from copy import deepcopy
import json
from uuid import uuid4
import pytest
from test_completed_final_evidence import saved
from test_environment_manifest import environment
from compertum.data.encoding import canonical
from compertum.data.errors import DataError
from compertum.review_evidence import sha
from compertum.completed_final_evidence import completed_final
from compertum import final_audit_request as m


@pytest.fixture
def audit_packet(saved,environment):
 original=completed_final(saved.storage,saved.sid);task=str(uuid4());value=environment('wheel');record=m.read_manifest
 from compertum.environment_manifest import build_manifest
 manifest=build_manifest(value)
 a=dict(artifact_id=str(uuid4()),task_id=task,path=f'artifacts/runs/{task}/final_audit/input/environment.json',size_bytes=len(manifest.content),sha256=manifest.sha256)
 raw=m.build_request(task,1,original,a,manifest.content)
 return raw,manifest.content,saved.raw


def test_request_keeps_original_code_separate_from_auditor(audit_packet):
 raw,manifest,frame=audit_packet;v=m.read_request(raw,expected_sha256=sha(raw))
 assert v['original']['plan']['runtime']!=v['auditor_runtime'] and v['auditor_environment']['lane']=='wheel'
 assert v['original']['frame']['sha256']==sha(frame) and v['manifest_artifact']['sha256']==sha(manifest)
 assert len(raw)<=65536


@pytest.mark.parametrize('fault',['hash','canonical','oversize','extra','schema','attempt','boolean_attempt','financial','full','task','manifest_path','manifest_owner','manifest_hash','manifest_size','environment_task','environment_lane','author_role','author_code','author_task','author_task_hash','author_lane','author_source','original_extra','original_seal','original_evaluation','original_plan','original_request','original_frame','source_path','source_owner','payload_size','head_sequence','head_boolean','closure_hash'])
def test_rehashed_substitutions_are_refused(audit_packet,fault):
 raw,_,_=audit_packet;v=json.loads(raw);o=v['original'];a=o['author']
 if fault=='hash':
  with pytest.raises(DataError):m.read_request(raw,expected_sha256='9'*64)
  return
 if fault=='canonical':raw=b' '+raw
 elif fault=='oversize':raw=b' '*(65536+1)
 else:
  if fault=='extra':v['verified']=True
  elif fault=='schema':v['schema']='other'
  elif fault=='attempt':v['attempt']=3
  elif fault=='boolean_attempt':v['attempt']=True
  elif fault=='financial':v['financial_accepted']=True
  elif fault=='full':v['full_M3']=True
  elif fault=='task':v['task_id']=o['evaluation_id']
  elif fault=='manifest_path':v['manifest_artifact']['path']='arbitrary.json'
  elif fault=='manifest_owner':v['manifest_artifact']['task_id']=o['evaluation_id']
  elif fault=='manifest_hash':v['manifest_artifact']['sha256']='9'*64
  elif fault=='manifest_size':v['manifest_artifact']['size_bytes']=4*1024**2+1
  elif fault=='environment_task':v['auditor_environment']['task_id']=str(uuid4())
  elif fault=='environment_lane':v['auditor_environment']['lane']='other'
  elif fault=='author_role':a.update(role='experiment_auditor',entrypoint='compertum.runtime.audit_worker')
  elif fault=='author_code':a['code_sha256']='9'*64
  elif fault=='author_task':a['task_id']=str(uuid4())
  elif fault=='author_task_hash':a['task_sha256']='9'*64
  elif fault=='author_lane':a['clean_environment']['lane']='wheel'
  elif fault=='author_source':a['clean_environment']['run_id']=str(uuid4())
  elif fault=='original_extra':o['verified']=True
  elif fault=='original_seal':o['seal_id']=str(uuid4())
  elif fault=='original_evaluation':o['evaluation_id']=str(uuid4())
  elif fault=='original_plan':o['plan']['selected']=[];o['plan_sha256']=sha(canonical(o['plan']))
  elif fault=='original_request':o['request_artifact']['path']=o['request_artifact']['path'].replace('01.json','02.json')
  elif fault=='original_frame':o['frame']['task_id']=str(uuid4())
  elif fault=='source_path':o['source_artifact']['path']='arbitrary.json'
  elif fault=='source_owner':o['source_artifact']['task_id']=o['evaluation_id']
  elif fault=='payload_size':o['payload_bytes']=o['frame']['size_bytes']
  elif fault=='head_sequence':o['guard_head']['sequence']=257
  elif fault=='head_boolean':o['seal_head']['sequence']=True
  else:o['original_closure_sha256']='bad'
  raw=canonical(v)
 with pytest.raises(DataError):m.read_request(raw,expected_sha256=sha(raw))
