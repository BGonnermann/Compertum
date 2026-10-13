"""Actual coordinator process exits at explicit synthetic-review boundaries."""
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
import json,os,sys
sys.path.insert(0,str(Path(__file__).parents[1]))
from compertum.config import load_config
from compertum.runtime.identity import resolve_project
from compertum.runtime.owners import acquire_owner,release_owner
from compertum.storage import StorageManager,reserve_runtime_paths
from compertum.research import ResearchController
from compertum.campaign_review import CampaignReviewController

root=Path(sys.argv[1]).resolve();run,task,action=sys.argv[2:5];project=resolve_project(root)
lease=acquire_owner(project,'coordinator');storage=StorageManager(lease,load_config(root/'config.toml',root))
coordinator=SimpleNamespace(status=lambda:{'research_state':'RUNNING'},require_health=lambda:None)
audit=None;author=None;supervisor=None;managed=None
try:
    if action in ('create','create_aggregate','create_aggregate_ready'):
        from compertum.runtime.managed import launch_owner
        from compertum.development_seals import create_campaign
        from helpers.saved_campaign_fixture import campaign_folds
        reserve_runtime_paths(storage);supervisor=acquire_owner(project,'supervisor');managed,remote=launch_owner(supervisor,'evaluation')
        author=ResearchController(coordinator,storage)
        create_campaign(author.runs,run,campaign_folds(),seal_id=str(uuid4()),evaluation=remote,data_manifest_sha256='a'*64,holdout_manifest_sha256='b'*64)
        author.control(run,str(uuid4()),'resume');author.step(run);assert author.active[2].wait()['exit_code']==0;author.tick()
        from compertum.simulation.campaign_runs import interrupt
        while author.runs.summary(run)['state']!='COMPLETED':
            author.runs.begin_campaign(run,author.runs.prepare_campaign(run));interrupt(author.runs,run,'MISSING_REFERENCE',terminal=True)
        assert author.runs.status(run)['completed_units']==1
        audit=CampaignReviewController(coordinator,storage)
        if action.startswith('create_aggregate'):
            from compertum.auditor import AuditorController
            units=AuditorController(coordinator,storage);unit_task=str(uuid4());units.runs.register(unit_task,run,0)
            try:
                units.step(unit_task);assert units.active[2].wait()['exit_code']==0;units.tick();assert units.runs.status(unit_task)['state']=='COMPLETED'
            finally:units.pause()
            card=str(uuid4());audit.runs.register(card,run,'scorecard');audit.step(card);assert audit.active[2].wait()['exit_code']==0;audit.tick();assert audit.runs.status(card)['state']=='COMPLETED'
            result=audit.runs.register(task,run,'aggregate') if action=='create_aggregate_ready' else {'state':'EVIDENCE_READY'}
        else:result=audit.runs.register(task,run,'scorecard')
    elif action.startswith('registration_crash_'):
        audit=CampaignReviewController(coordinator,storage)
        if action=='registration_crash_unrecorded':
            publish=audit.runs._publish
            def crash(task,path,raw):
                result=publish(task,path,raw)
                if path.endswith('/unit-audits-0.json'):os._exit(81)
                return result
            audit.runs._publish=crash
        else:
            save=audit.runs._save;boundary='EXPORT_PUBLISHED' if action=='registration_crash_recorded' else 'BUNDLE_BOUND'
            def crash(s,transition):
                save(s,transition)
                if transition==boundary:
                    # Exercise death after the intended durable boundary.
                    audit.runs.store.conn.commit()
                    os._exit(82 if boundary=='EXPORT_PUBLISHED' else 83)
            audit.runs._save=crash
        audit.runs.register(task,run,'aggregate');raise AssertionError('CRASH_NOT_REACHED')
    else:
        audit=CampaignReviewController(coordinator,storage);result=audit.runs.status(task)
        if action!='status':
            if result['state']=='INTERRUPTED':audit.runs.resume(task)
            if action=='crash_before_resume':
                begin=audit.runs.begin
                def crash(*args,**kwargs):begin(*args,**kwargs);os._exit(77)
                audit.runs.begin=crash
            elif action=='crash_after_publish':
                open_artifact=storage.open_artifact
                def wrap(*args,**kwargs):
                    writer=open_artifact(*args,**kwargs);publish=writer.publish
                    if not writer.destination.name.startswith(('scorecard-attempt-','aggregate-attempt-')):return writer
                    def crash():publish();os._exit(78)
                    writer.publish=crash;return writer
                storage.open_artifact=wrap
            elif action=='crash_after_commit':
                accept=audit.runs.accept
                def crash(*args,**kwargs):accept(*args,**kwargs);os._exit(79)
                audit.runs.accept=crash
            elif action=='crash_after_rejection':
                import compertum.runtime.jobs as jobs
                create=jobs.create_suspended
                def changed(api,argv,*args,**kwargs):
                    argv=list(argv);argv[7 if argv[3]=='compertum.runtime.audit_worker' and argv[4]!='aggregate' else 8]='0'*64
                    return create(api,argv,*args,**kwargs)
                jobs.create_suspended=changed
            elif action!='finish':raise ValueError('UNKNOWN_ACTION')
            audit.step(task)
            if audit.active:
                receipt=audit.active[2].wait()
                if action=='crash_after_rejection':
                    assert receipt['exit_code']==6;audit.runs.record_exit(task,receipt);os._exit(80)
                assert receipt['exit_code']==0;audit.tick()
            result=audit.runs.status(task)
    print(json.dumps({'generation':lease.generation,'result':result}),flush=True)
finally:
    if audit:audit.pause()
    if author:author.pause()
    if managed:managed.close()
    if supervisor:release_owner(supervisor)
    release_owner(lease)
