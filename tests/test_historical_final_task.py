"""An old completed task can be inspected without relaxing current launch pins."""
from copy import deepcopy
from datetime import datetime,timezone
import pytest
from test_final_task import request
from compertum.data.errors import DataError
from compertum.final_task import build_task,validate_task
from compertum.historical_final_task import validate_historical_task


def saved(root):
 raw,a=request();p=build_task(root,raw,a,charged_ms=34567,now=datetime(2026,1,1,tzinfo=timezone.utc)).to_payload()
 return raw,a,p


def test_new_auditor_inspects_old_task_without_launch_authority(tmp_path,monkeypatch):
 from compertum import recovery
 raw,a,p=saved(tmp_path)
 monkeypatch.setattr(recovery,'_package_hash',lambda:'9'*64)
 with pytest.raises(DataError):validate_task(tmp_path,p,raw,a,charged_ms=34567)
 assert validate_historical_task(tmp_path,p,raw,a,charged_ms=34567)==p
 with pytest.raises(DataError):build_task(tmp_path,raw,a,charged_ms=34567,now=datetime(2026,1,1,tzinfo=timezone.utc))


@pytest.mark.parametrize('fault',['code','lock','role','parent','campaign','hash','source','output','broker','network','clock','deadline','wall','threads','memory','attempts','acceptance','schema','charge','request','float'])
def test_rehashed_historical_task_changes_are_rejected(tmp_path,fault):
 raw,a,p=saved(tmp_path);charge=34567
 if fault=='code':p['code_sha256']='9'*64
 elif fault=='lock':p['lock_sha256']='9'*64
 elif fault=='role':p['role']='experiment_auditor'
 elif fault=='parent':p['parent_task_id']=None
 elif fault=='campaign':p['campaign_id']=None
 elif fault=='hash':p['input_hashes'][0]='9'*64
 elif fault=='source':p['permissions']['filesystem_bundle'][1]='artifacts/other.json'
 elif fault=='output':p['permissions']['output_directory']+='/other'
 elif fault=='broker':p['permissions']['broker']=True
 elif fault=='network':p['permissions']['network_destinations']=['example.invalid']
 elif fault=='clock':p['clock']['active_elapsed_seconds']=1
 elif fault=='deadline':p['deadline_at']='2026-01-01T00:02:00+00:00'
 elif fault=='wall':p['budget']['wall_seconds']=120
 elif fault=='threads':p['budget']['cpu_threads']=5
 elif fault=='memory':p['budget']['ram_bytes']=5*1024**3
 elif fault=='attempts':p['budget']['max_attempts']=3
 elif fault=='acceptance':p['acceptance_checks']=[]
 elif fault=='schema':p['output_schema_sha256']='9'*64
 elif fault=='charge':charge=0
 elif fault=='request':a['sha256']='9'*64
 else:p['budget']['cpu_threads']=4.0
 with pytest.raises((DataError,ValueError)):validate_historical_task(tmp_path,p,raw,a,charged_ms=charge)
