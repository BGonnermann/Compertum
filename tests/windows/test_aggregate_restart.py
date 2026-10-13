"""Actual aggregate coordinator process deaths preserve fixed evidence/attempts."""
from pathlib import Path
from uuid import uuid4
import shutil
import pytest
from test_review_restart import child


def prepare(root):
    shutil.copyfile(Path(__file__).parents[2]/'config/default.toml',root/'config.toml')
    run,task=str(uuid4()),str(uuid4());assert child(root,run,task,'create_aggregate_ready')['state']=='READY';return run,task


@pytest.mark.parametrize('boundary,code',[('crash_before_resume',77),('crash_after_publish',78),('crash_after_commit',79)])
def test_actual_aggregate_crash_preserves_the_acceptance_boundary(tmp_path,boundary,code):
    run,task=prepare(tmp_path);child(tmp_path,run,task,boundary,code)
    recovered=child(tmp_path,run,task,'status');result=child(tmp_path,run,task,'finish')
    assert result['state']=='COMPLETED' and result['financial_accepted'] is False
    assert result['request_sha256']==recovered['request_sha256'] and result['preparation_artifacts']==recovered['preparation_artifacts']
    if boundary=='crash_after_commit':assert recovered==result and len(result['attempts'])==1
    else:
        assert recovered['state']=='INTERRUPTED' and recovered['artifact'] is None and len(result['attempts'])==2
        path=tmp_path/result['attempts'][0]['output_path']
        assert path.exists() if boundary=='crash_after_publish' else list(path.parent.glob(path.name+'.partial-*'))
    assert result['attempts'][-1]['job_receipt']['active_processes']==0


def test_aggregate_owner_deaths_exhaust_two_attempts(tmp_path):
    run,task=prepare(tmp_path);child(tmp_path,run,task,'crash_before_resume',77)
    assert child(tmp_path,run,task,'status')['state']=='INTERRUPTED'
    child(tmp_path,run,task,'crash_before_resume',77);result=child(tmp_path,run,task,'status')
    assert result['state']=='FAILED' and len(result['attempts'])==2
    assert len(list((tmp_path/f'artifacts/runs/{task}/review').glob('*.partial-*')))==2


def test_aggregate_rejection_survives_owner_death(tmp_path):
    run,task=prepare(tmp_path);child(tmp_path,run,task,'crash_after_rejection',80)
    result=child(tmp_path,run,task,'status')
    assert result['state']=='BLOCKED' and result['attempts'][-1]['job_receipt']['exit_code']==6
    assert result==child(tmp_path,run,task,'status')
