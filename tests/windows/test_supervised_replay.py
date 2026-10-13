import json,time,shutil,sqlite3
from pathlib import Path
from uuid import uuid4
import pytest
from test_m0_lifecycle import launch,stopped
from test_saved_run_restart import child as saved_child
from compertum.runtime.supervisor import control
from compertum.runtime.errors import RuntimeRefused

ROOT=Path(__file__).parents[2]

def baseline(root,run,operation):return control(root,'baseline',{'run_id':run,'operation':operation})

def test_native_terminal_pause_resume_stop_restart(tmp_path):
    shutil.copyfile(ROOT/'config/default.toml',tmp_path/'config.toml');run=str(uuid4())
    saved_child(tmp_path,run,'create')
    process,status=launch(tmp_path);measurements={}
    try:
        assert status['research_state']=='PAUSED'
        with pytest.raises(RuntimeRefused,match='RESEARCH_PAUSED'):baseline(tmp_path,run,'step')
        control(tmp_path,'resume_research');baseline(tmp_path,run,'resume')
        admitted=baseline(tmp_path,run,'step');assert admitted['state']=='RUNNING'
        began=time.monotonic();observed=control(tmp_path,'status');measurements['status_seconds']=time.monotonic()-began
        assert measurements['status_seconds']<5 and observed['watchdog']['status']=='HEALTHY'
        began=time.monotonic();paused=baseline(tmp_path,run,'pause');measurements['pause_seconds']=time.monotonic()-began
        assert measurements['pause_seconds']<5 and paused['state']=='PAUSED'
        assert control(tmp_path,'status')['active_replay_pid'] is None
        baseline(tmp_path,run,'resume');baseline(tmp_path,run,'step')
        deadline=time.monotonic()+15
        while time.monotonic()<deadline:
            state=baseline(tmp_path,run,'status')
            if state['state']!='RUNNING':break
            time.sleep(.1)
        assert state['completed_units']==1 and state['state']=='READY',state
        assert len(state['attempts'])==2
        receipt=state['attempts'][-1]['job_receipt']
        assert receipt['active_processes']==0 and receipt['memory_limit']==4*1024**3
        control(tmp_path,'shutdown');stopped(process)
        process,status=launch(tmp_path)
        restored=baseline(tmp_path,run,'status')
        assert restored['completed_units']==1 and restored['state']=='PAUSED'
        assert status['research_state']=='PAUSED' and status['active_replay_pid'] is None
        control(tmp_path,'resume_research');baseline(tmp_path,run,'resume');baseline(tmp_path,run,'step')
        began=time.monotonic();control(tmp_path,'stop_research',{'run_id':run});measurements['stop_seconds']=time.monotonic()-began
        assert measurements['stop_seconds']<5 and baseline(tmp_path,run,'status')['state']=='STOPPED'
        control(tmp_path,'shutdown');stopped(process)
        process,status=launch(tmp_path)
        assert baseline(tmp_path,run,'status')['state']=='STOPPED'
        control(tmp_path,'shutdown');stopped(process)
        (tmp_path/'measurements.json').write_text(json.dumps(measurements))
    finally:
        if process.poll() is None:process.kill();process.wait(timeout=5)


def test_native_explicit_steps_match_outputs_and_share_slot(tmp_path):
    shutil.copyfile(ROOT/'config/default.toml',tmp_path/'config.toml');run=str(uuid4());other=str(uuid4())
    saved_child(tmp_path,run,'create');saved_child(tmp_path,other,'create')
    process,status=launch(tmp_path)
    try:
        control(tmp_path,'resume_research');baseline(tmp_path,run,'resume')
        fixture=control(tmp_path,'foundation.check',{'operation':'submit'})
        with pytest.raises(RuntimeRefused,match='RUN_NOT_ACTIVE'):control(tmp_path,'stop_research',{'run_id':other})
        with pytest.raises(RuntimeRefused,match='JOB_SLOT_BUSY'):baseline(tmp_path,run,'step')
        assert baseline(tmp_path,run,'status')['attempts']==[]
        control(tmp_path,'pause_research');control(tmp_path,'resume_research')
        for unit in range(6):
            request=str(uuid4());payload={'run_id':run,'operation':'step'}
            admitted=control(tmp_path,'baseline',payload,request_id=request)
            if unit==0:
                with pytest.raises(RuntimeRefused,match='RUN_NOT_ACTIVE'):control(tmp_path,'stop_research',{'run_id':other})
            deadline=time.monotonic()+12
            while time.monotonic()<deadline:
                state=baseline(tmp_path,run,'status')
                if state['state']!='RUNNING':break
                time.sleep(.05)
            assert state['completed_units']==unit+1,state
            assert control(tmp_path,'baseline',payload,request_id=request)==admitted
            assert len(baseline(tmp_path,run,'status')['attempts'])==unit+1
        assert state['state']=='COMPLETED'
        baseline(tmp_path,other,'stop')
        assert control(tmp_path,'stop_research',{'run_id':other})['confirmed']
        with sqlite3.connect((tmp_path/'state/research.sqlite').as_uri()+'?mode=ro',uri=True) as db:
            before=db.execute('SELECT count(*) FROM operator_requests').fetchone()[0]
        for _ in range(4):baseline(tmp_path,run,'status')
        with sqlite3.connect((tmp_path/'state/research.sqlite').as_uri()+'?mode=ro',uri=True) as db:
            assert db.execute('SELECT count(*) FROM operator_requests').fetchone()[0]==before
        control(tmp_path,'shutdown');stopped(process)
        from helpers.simulation_fixture import fixture as inputs,SECTORS
        from compertum.simulation import replay
        from compertum.simulation.worker_record import verify_result
        chunks,start,end,_=inputs(scored=8)
        for result in state['results']:
            content=verify_result((tmp_path/result['artifact']['path']).read_bytes(),state['request_sha256'],result['horizon'],result['cost_bps'])
            assert content==replay(chunks,SECTORS,start,end,result['horizon'],cost_bps=result['cost_bps']).content
        (tmp_path/'final-run.json').write_text(json.dumps(state))
    finally:
        if process.poll() is None:process.kill();process.wait(timeout=5)


def test_supervisor_crash_kills_worker_and_restart_preserves_attempt(tmp_path):
    from compertum.runtime._windows import WindowsAPI
    shutil.copyfile(ROOT/'config/default.toml',tmp_path/'config.toml');run=str(uuid4())
    saved_child(tmp_path,run,'create');process,status=launch(tmp_path);worker=None
    try:
        control(tmp_path,'resume_research');baseline(tmp_path,run,'resume');baseline(tmp_path,run,'step')
        status=control(tmp_path,'status');api=WindowsAPI();worker=api.open_process(status['active_replay_pid'])
        process.kill();process.communicate(timeout=5)
        assert api.WaitForSingleObject(worker.get(),3000)==0
        process,status=launch(tmp_path);state=baseline(tmp_path,run,'status')
        assert status['research_state']=='PAUSED' and state['state']=='INTERRUPTED'
        assert len(state['attempts'])==1 and state['completed_units']==0
        control(tmp_path,'resume_research');baseline(tmp_path,run,'resume');baseline(tmp_path,run,'step')
        deadline=time.monotonic()+12
        while time.monotonic()<deadline:
            state=baseline(tmp_path,run,'status')
            if state['state']!='RUNNING':break
            time.sleep(.05)
        assert state['completed_units']==1 and len(state['attempts'])==2,state
        control(tmp_path,'shutdown');stopped(process)
        (tmp_path/'crash-receipt.json').write_text(json.dumps({'worker_exit_verified':True,'run':state}))
    finally:
        if worker:worker.close()
        if process.poll() is None:process.kill();process.wait(timeout=5)
