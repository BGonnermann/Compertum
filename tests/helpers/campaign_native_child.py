"""Short-lived native campaign coordinator fixture. Synthetic data only."""
from pathlib import Path
import json,os,sys,time
from types import SimpleNamespace
from uuid import uuid4
sys.path.insert(0,str(Path(__file__).parents[1]))
from helpers.saved_campaign_fixture import campaign_folds
from compertum.config import load_config
from compertum.runtime.identity import resolve_project
from compertum.runtime.owners import acquire_owner,release_owner
from compertum.storage import StorageManager
from compertum.research import ResearchController

root=Path(sys.argv[1]).resolve();run=sys.argv[2];action=sys.argv[3]
lease=acquire_owner(resolve_project(root),'coordinator');controller=None
try:
    storage=StorageManager(lease,load_config(root/'config.toml',root))
    controller=ResearchController(SimpleNamespace(status=lambda:{'research_state':'RUNNING'},require_health=lambda:None),storage)
    runs=controller.runs
    if action=='create':result=runs.create_campaign(run,campaign_folds(True))
    elif action=='status':result=runs.status(run)
    elif action=='stop':result=controller.control(run,str(uuid4()),'stop')
    elif action=='verify':
        from compertum.simulation.campaign_runs import history
        state=history(runs,run);runs.status(run)
        for a in state['attempts']:
            if a['status']=='COMPLETED':
                r=a['job_receipt'];assert r['assigned_before_resume'] and r['active_processes']==0 and r['observed_children_exited'] and r['exit_code']==0 and not r['timed_out']
                assert r['memory_limit']==4*1024**3 and r['affinity'].bit_count()<=4
        card=runs.campaign_scorecard(run)
        (root/'scorecard.json').write_bytes(card.content)
        result=runs.summary(run)
        result['daily_budget']=storage.store.conn.execute('SELECT day,sum(charged) FROM job_budget GROUP BY day').fetchall()
        result['reserved_records_bytes']=storage.store.conn.execute("SELECT sum(CASE WHEN status='PUBLISHED' THEN written ELSE maximum END) FROM reservations WHERE task=? AND status!='SPLIT'",(run,)).fetchone()[0]
        result['state_bytes']=len(json.dumps(state).encode())
    elif action.startswith('batch:') or action.startswith('crash_'):
        controller.control(run,str(uuid4()),'resume')
        import compertum.runtime.jobs as jobs
        create=jobs.create_suspended
        def capture(api,*args,**kwargs):
            if action=='crash_during_evaluation':
                command,environment,cwd,inherited=args
                command=list(command);command[3]='helpers.campaign_crash_worker'
                environment=dict(environment);environment['PYTHONPATH']+=os.pathsep+str(Path(__file__).parents[1])
                environment['COMPERTUM_FIXTURE_EVALUATION_MARKER']=str(root/'evaluation-entered.json')
                args=(command,environment,cwd,inherited)
            info=create(api,*args,**kwargs)
            with (root/'native-pids.jsonl').open('a') as f:f.write(json.dumps({'pid':info.pid,'action':action})+'\n')
            return info
        jobs.create_suspended=capture
        if action=='crash_before_fit':
            begin=runs.begin_campaign
            def crash(*args,**kwargs):begin(*args,**kwargs);os._exit(74)
            runs.begin_campaign=crash
        elif action=='crash_after_publish':
            open_artifact=storage.open_artifact
            def wrap(*args,**kwargs):
                writer=open_artifact(*args,**kwargs);publish=writer.publish
                def crash():publish();os._exit(73)
                writer.publish=crash;return writer
            storage.open_artifact=wrap
        elif action=='crash_after_commit':
            accept=runs.accept
            def crash(*args,**kwargs):accept(*args,**kwargs);os._exit(76)
            runs.accept=crash
        target=int(action.split(':')[1]) if action.startswith('batch:') else 63
        assert 1<=target<=63
        for _ in range(8):
            result=runs.summary(run)
            if result['resolved_units']>=target:break
            controller.step(run)
            if action=='crash_during_evaluation':
                until=time.monotonic()+30
                while not (root/'evaluation-entered.json').exists() and time.monotonic()<until:time.sleep(.01)
                assert (root/'evaluation-entered.json').is_file()
                os._exit(74)
            receipt=controller.active[2].wait();controller.tick()
            result=runs.summary(run)
            assert receipt['exit_code']==0 and not receipt['timed_out'],receipt
            assert result['state'] in ('READY','COMPLETED'),result['state']
        assert result['resolved_units']==target
    else:raise RuntimeError('UNKNOWN_CAMPAIGN_FIXTURE_ACTION')
    print(json.dumps({'generation':lease.generation,'result':result}),flush=True)
finally:
    if controller:controller.pause()
    release_owner(lease)
