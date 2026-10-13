"""Real process deaths, retained orphans and attempt exhaustion."""
import json,os,shutil,subprocess,sys
from pathlib import Path
from uuid import uuid4
import pytest
from fixture_processes import python_process


def child(root,run,task,action,code=0):
    p=python_process(['-B',str(Path(__file__).parents[1]/'helpers/audit_native_child.py'),str(root),run,task,action],env={k:v for k,v in os.environ.items() if k.upper() in {'SYSTEMROOT','WINDIR','PYTHONPATH','PYTHONDONTWRITEBYTECODE','PYTHONNOUSERSITE','OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'}},stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    out,err=p.communicate(timeout=60)
    assert p.returncode==code,(out,err)
    return json.loads(out)['result'] if code==0 else None


def prepare(root):
    shutil.copyfile(Path(__file__).parents[2]/'config/default.toml',root/'config.toml')
    run,task=str(uuid4()),str(uuid4());assert child(root,run,task,'create')['state']=='READY';return run,task


def test_second_attempt_owner_death_records_exhaustion(tmp_path):
    run,task=prepare(tmp_path)
    child(tmp_path,run,task,'crash_before_resume',77)
    assert child(tmp_path,run,task,'status')['state']=='INTERRUPTED'
    child(tmp_path,run,task,'crash_before_resume',77)
    result=child(tmp_path,run,task,'status')
    assert result['state']=='FAILED' and len(result['attempts'])==2
    assert result['attempts'][-1]['reason']=='TRANSIENT_ATTEMPTS_EXHAUSTED'
    assert len(list((tmp_path/f'artifacts/runs/{task}/audit').glob('*.partial-*')))==2


@pytest.mark.parametrize('boundary,code',[('crash_before_resume',77),('crash_after_publish',78),('crash_after_commit',79)])
def test_native_crash_preserves_commit_boundary_and_does_not_adopt_orphans(tmp_path,boundary,code):
    run,task=prepare(tmp_path);child(tmp_path,run,task,boundary,code)
    recovered=child(tmp_path,run,task,'status');result=child(tmp_path,run,task,'finish')
    assert result['state']=='COMPLETED'
    if boundary=='crash_after_commit':
        assert recovered==result and len(result['attempts'])==1
    else:
        assert recovered['state']=='INTERRUPTED' and recovered['artifact'] is None and len(result['attempts'])==2
        path=tmp_path/result['attempts'][0]['output_path']
        assert path.exists() if boundary=='crash_after_publish' else list(path.parent.glob(path.name+'.partial-*'))
    assert result['attempts'][-1]['job_receipt']['active_processes']==0
