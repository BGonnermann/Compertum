"""Exact actual exits around selected intent/attempt/acceptance/result commits."""
import json,os,subprocess,sys
from pathlib import Path
import pytest


@pytest.mark.parametrize('point',['prepared','attempted','accepted','completed'])
def test_actual_process_exit_never_reissues_selected_effect(tmp_path,point):
    helper=Path(__file__).parent/'helpers/operation_crash_fixture.py'
    env={k:v for k,v in os.environ.items() if k.upper() in {'SYSTEMROOT','WINDIR','PATH','PYTHONPATH','TEMP','TMP'}}
    env.update(PYTHONDONTWRITEBYTECODE='1',PYTHONNOUSERSITE='1')
    args=[sys.executable,'-B',str(helper),str(tmp_path)]
    crashed=subprocess.run(args+['crash',point],env=env,capture_output=True,text=True,timeout=25)
    assert crashed.returncode==23,crashed.stderr
    recovered=subprocess.run(args+['recover',point],env=env,capture_output=True,text=True,timeout=25)
    assert recovered.returncode==0,recovered.stderr
    value=json.loads(recovered.stdout);accepted=point in {'accepted','completed'}
    assert value['submissions']==value['acceptances']==int(accepted) and value['positions']=={'AAPL':45}
    assert value['result']['status']==('PENDING_UNCONFIRMED' if point=='prepared' else 'PENDING' if accepted else 'UNKNOWN')
    (tmp_path/'crash-receipt.json').write_text(json.dumps(value),encoding='utf-8')
