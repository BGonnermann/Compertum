"""Actual crash/restart then authenticated public warning with allocated1GiBreserve."""
import json,os,shutil,subprocess,sys,time
from pathlib import Path
import compertum
from test_fake_operator_control import ROOT,launch,stop,call

def test_native_incident_warning_survives_crash_and_public_restart(tmp_path):
    shutil.copyfile(ROOT/'config/default.toml',tmp_path/'config.toml')
    helper=ROOT/'tests/helpers/incident_alert_fixture.py'
    env={k:v for k,v in os.environ.items() if k.upper() in {'SYSTEMROOT','WINDIR','PATH','PYTHONPATH','TEMP','TMP'}}
    env.update(PYTHONDONTWRITEBYTECODE='1',PYTHONNOUSERSITE='1')
    args=[sys.executable,'-B',str(helper),str(tmp_path)]
    crashed=subprocess.run(args+['create'],env=env,capture_output=True,text=True,timeout=40)
    assert crashed.returncode==23,crashed.stderr
    recovered=subprocess.run(args+['recover'],env=env,capture_output=True,text=True,timeout=25)
    assert recovered.returncode==0,recovered.stderr
    proof=json.loads((tmp_path/'incident-fixture.json').read_text(encoding='utf-8'));recovery=json.loads(recovered.stdout)
    assert proof['package_origin']==recovery['package_origin']==str(Path(compertum.__file__).resolve())
    p,status=launch(tmp_path,'normal')
    try:
        reserve=status['watchdog']['owners']['execution']['reserve']
        assert reserve['capacity_bytes']==1024**3 and reserve['allocated_bytes']>=1024**3 and not reserve['sparse']
        began=time.monotonic();visible=call(tmp_path,'operation_status',plan_id=proof['args']['plan_id']);elapsed=time.monotonic()-began
        assert elapsed<5 and visible['intents'][0]['reason']=='UNRESOLVED_LIMIT' and visible['intents'][0]['operator_action_required'] is True
        assert visible['intents'][0]['incident_started_at']==proof['warning']['incident_started_at']
        current=call(tmp_path,'status');assert current['halted'] and not current['armed'] and not current['supervised']
        receipt=stop(tmp_path,p)
        assert Path(receipt['execution_origin']['package_root']).resolve()==Path(compertum.__file__).resolve().parent
        from compertum.deterministic_broker import DeterministicBroker
        b=DeterministicBroker(tmp_path/'state/fake-broker',create=False)
        try:assert b.snapshot()['calls']==proof['calls'] and b.snapshot()['orders']==[]
        finally:b.close()
        (tmp_path/'incident-alert-receipt.json').write_text(json.dumps(dict(actual_reserve=reserve,actual_crash=True,actual_restart=True,public_pipe=True,exact_owner_replay=True,operator_warning=visible['intents'][0],calls_unchanged=True,execution_origin=receipt['execution_origin'],seed_origin=proof['package_origin'],recovery_origin=recovery['package_origin'],status_seconds=elapsed,accelerated_fixture_clock=True,financial_accepted=False)),encoding='utf-8')
    finally:
        if p.poll() is None:p.kill();p.communicate(timeout=5)
