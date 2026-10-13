import hashlib,json,time,shutil
from pathlib import Path
from uuid import uuid4
import pytest
from test_m0_lifecycle import launch,stopped
from test_saved_run_restart import child as saved_child
from test_supervised_replay import baseline
from compertum.runtime.supervisor import control
from compertum.runtime._windows import WindowsAPI

ROOT=Path(__file__).parents[2]

@pytest.mark.parametrize('crash',[False,True,'pause'])
def test_nine_unit_native_completion_and_prediction_restart(tmp_path,crash):
    shutil.copyfile(ROOT/'config/default.toml',tmp_path/'config.toml');run=str(uuid4())
    saved_child(tmp_path,run,'create_prediction');process,status=launch(tmp_path);observed=None
    try:
        control(tmp_path,'resume_research');baseline(tmp_path,run,'resume')
        for unit in range(9):
            previous=baseline(tmp_path,run,'status');baseline(tmp_path,run,'step')
            if crash and unit==6:
                hashes={r['artifact']['path']:r['artifact']['sha256'] for r in previous['results']}
                assert len(hashes)==6
                api=WindowsAPI();observed=api.open_process(control(tmp_path,'status')['active_replay_pid'])
                if crash is True:
                    process.kill();process.communicate(timeout=5)
                    process,status=launch(tmp_path)
                else:
                    assert baseline(tmp_path,run,'pause')['state']=='PAUSED'
                assert api.WaitForSingleObject(observed.get(),3000)==0
                interrupted=baseline(tmp_path,run,'status')
                assert interrupted['state']==('INTERRUPTED' if crash is True else 'PAUSED') and interrupted['completed_units']==6
                assert all(hashlib.sha256((tmp_path/p).read_bytes()).hexdigest()==h for p,h in hashes.items())
                control(tmp_path,'resume_research');baseline(tmp_path,run,'resume');baseline(tmp_path,run,'step')
            deadline=time.monotonic()+12
            while time.monotonic()<deadline:
                state=baseline(tmp_path,run,'status')
                if state['state']!='RUNNING':break
                time.sleep(.05)
            assert state['completed_units']==unit+1,state
        assert state['state']=='COMPLETED' and state['total_units']==9
        assert len(state['attempts'])==9+int(bool(crash))
        assert len([r for r in state['results'] if r['cost_bps'] is None])==3
        control(tmp_path,'shutdown');stopped(process)
        from helpers.simulation_fixture import fixture,SECTORS
        from compertum.simulation import replay
        from compertum.simulation.prediction import score_predictions
        from compertum.simulation.worker_record import verify_result
        chunks,start,end,_=fixture(scored=26)
        for row in state['results']:
            raw=(tmp_path/row['artifact']['path']).read_bytes()
            body=verify_result(raw,state['request_sha256'],row['horizon'],row['cost_bps'],scoring_as_of=state['scoring_as_of'])
            expected=(score_predictions(chunks,SECTORS,start,end,row['horizon'],scoring_as_of=state['scoring_as_of'])
                if row['cost_bps'] is None else replay(chunks,SECTORS,start,end,row['horizon'],cost_bps=row['cost_bps']))
            assert body==expected.content
            assert row['artifact']['path'].endswith('.prediction' if row['cost_bps'] is None else '.replay')
        (tmp_path/'final-nine.json').write_text(json.dumps({'crash_during_prediction':crash is True,'transition':'pause' if crash=='pause' else 'crash' if crash else 'none','run':state}))
    finally:
        if observed:observed.close()
        if process.poll() is None:process.kill();process.wait(timeout=5)
