"""Actual owner exits around fit publication/commit and evaluation admission."""
from pathlib import Path
from uuid import uuid4
import hashlib,json,os,subprocess,sys
import pytest
from compertum.runtime._windows import WindowsAPI
from compertum.runtime.errors import RuntimeRefused
from compertum.modeling.campaign import UNITS
ROOT=Path(__file__).parents[2]


def child(root,run,action,expected=0):
    env={k:v for k,v in os.environ.items() if k.upper() in {'SYSTEMROOT','WINDIR','TEMP','TMP','PYTHONPATH'}}
    env.update(__PYVENV_LAUNCHER__=sys.executable,PYTHONNOUSERSITE='1',PYTHONDONTWRITEBYTECODE='1',
        OMP_NUM_THREADS='4',OPENBLAS_NUM_THREADS='4',MKL_NUM_THREADS='4',NUMEXPR_NUM_THREADS='4')
    args=[sys.executable,'-B',str(ROOT/'tests/helpers/campaign_native_child.py'),str(root),run,action]
    result=subprocess.run(args,executable=sys._base_executable,env=env,capture_output=True,timeout=110,creationflags=0x08000000)
    index=len(list(root.glob('process-*.json')))
    (root/f'process-{index:02}.json').write_text(json.dumps({'argv':args,'exit_code':result.returncode,'stdout':result.stdout.decode(),'stderr':result.stderr.decode()},indent=2),encoding='utf-8')
    assert result.returncode==expected,result.stderr.decode()
    return json.loads(result.stdout) if expected==0 else None


def prepare(root):
    root.mkdir(exist_ok=True);(root/'config.toml').write_bytes((ROOT/'config/default.toml').read_bytes())


@pytest.mark.parametrize('action,code',[('crash_before_fit',74),('crash_after_publish',73),('crash_after_commit',76),('crash_during_evaluation',74)])
def test_native_campaign_owner_crash_preserves_fit_boundary(tmp_path,action,code):
    prepare(tmp_path);run=str(uuid4());created=child(tmp_path,run,'create')
    target=4 if action=='crash_during_evaluation' else 3
    child(tmp_path,run,f'batch:{target}');child(tmp_path,run,action,code)
    pid=json.loads((tmp_path/'native-pids.jsonl').read_text().splitlines()[-1])['pid'];api=WindowsAPI()
    try:handle=api.open_process(pid)
    except RuntimeRefused:assert pid not in api.process_snapshot()
    else:
        try:assert api.WaitForSingleObject(handle.get(),3000)==0
        finally:handle.close()
    if action=='crash_during_evaluation':
        assert json.loads((tmp_path/'evaluation-entered.json').read_text())=={'unit':4,'phase':'evaluate','fit_supplied':True}
    recovered=child(tmp_path,run,'status');state=recovered['result']
    assert recovered['generation']>created['generation']
    assert state['state']==('PAUSED' if action=='crash_after_commit' else 'INTERRUPTED')
    assert state['completed_units']==(4 if action in ('crash_after_commit','crash_during_evaluation') else 3)
    baseline=tmp_path/f'artifacts/runs/{run}/baseline'
    retained={str(p.relative_to(tmp_path)):hashlib.sha256(p.read_bytes()).hexdigest() for p in baseline.glob('unit-*')}
    if action=='crash_after_publish':assert (baseline/'unit-03-attempt-1.campaign').is_file()
    done=child(tmp_path,run,'batch:5')['result']
    assert done['completed_units']==5 and done['resolved_units']==5
    fits=[a for a in done['attempts'] if a['unit']==3]
    assert len(fits)==(1 if action in ('crash_after_commit','crash_during_evaluation') else 2)
    assert len([a for a in done['attempts'] if a['unit']==4])==(2 if action=='crash_during_evaluation' else 1)
    assert all(hashlib.sha256((tmp_path/p).read_bytes()).hexdigest()==pin for p,pin in retained.items())
    fit=done['outcomes'][UNITS[3].key];evaluation=done['outcomes'][UNITS[4].key]
    from compertum.runtime.campaign_worker import compute
    expected=compute((tmp_path/done['input_artifact']['path']).read_bytes(),done['request_sha256'],4,
        dependency_raw=(tmp_path/fit['artifact']['path']).read_bytes(),dependency_digest=fit['artifact']['sha256'],dependency_payload_sha256=fit['payload_sha256'])
    assert (tmp_path/evaluation['artifact']['path']).read_bytes()==expected
    assert child(tmp_path,run,'status')['result']['state']=='PAUSED'
    stopped=child(tmp_path,run,'stop')['result'];restored=child(tmp_path,run,'status')['result']
    assert all(restored[k]==v for k,v in stopped.items()) and restored['state']=='STOPPED'
    assert restored['attempts']==done['attempts'] and restored['outcomes']==done['outcomes']
