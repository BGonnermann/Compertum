"""Bounded synthetic recovery driver; no financial transport or protected reader."""
import json
from pathlib import Path
import sqlite3
import sys
from uuid import uuid4
from compertum.config import load_config
from compertum.consumption import consume_once,verify_consumption_guard
from compertum.events import canonical
from compertum.persistence import open_store,STORE_NAMES
from compertum.recovery import collect_recovery_set,restore_recovery_set,validate_recovery_set
from compertum.runtime.identity import resolve_project
from compertum.runtime.owners import acquire_owner,release_owner
from compertum.runtime.errors import RuntimeRefused
from compertum.storage import StorageManager,create_journal_reserve,open_journal_reserve

INPUTS={key:'a'*64 for key in ('input_sha256','protocol_sha256','shortlist_sha256')}


def main():
    root=Path(sys.argv[1]).resolve();request=json.loads(Path(sys.argv[2]).read_bytes());project=resolve_project(root)
    if request['action']=='package_origin':return {'status':'VERIFIED'}
    if request['action']=='inspect_paper':
        from paper_consumption_support import inspect
        return inspect(root,project)
    if request['action']=='reconcile_operation':
        from operation_recovery_support import reconcile
        return reconcile(root,project)
    if request['action']=='managed_verification':
        from compertum.runtime.supervisor import Supervisor
        from compertum.runtime.ipc import ProtocolDecision
        from compertum.foundation import fixture_spec
        import time
        supervisor=Supervisor(load_config(root/'config.toml',root))
        try:
            supervisor.coordinator.control(ProtocolDecision(str(uuid4()),'a'*64,'b'*64,supervisor.supervisor.generation),'resume_research',{})
            task=supervisor.fixtures.submit(fixture_spec(root));time.sleep(.3)
            checkpoint=supervisor.checkpoint()[0]
            validation=validate_recovery_set(root/checkpoint['path'],project_root=root)
            assert validation['status']=='VERIFIED'
            instances=validation['manifest']['writers']
            assert len({w['process_instance_id'] for w in instances})==4
            supervisor.jobs[0].api.TerminateJobObject(supervisor.jobs[0].job.get(),125)
            receipt=supervisor.jobs[0].wait();started=time.monotonic();supervisor.poll_health()
            health=supervisor.get_health()
            assert health['status']=='RESEARCH_BLOCKED' and health['reason']=='EVALUATION_OWNER_UNAVAILABLE'
            try: supervisor.fixtures.submit(fixture_spec(root))
            except RuntimeRefused: pass
            else: raise RuntimeRefused('DEAD_OWNER_ADMITTED')
            return {'status':'VERIFIED','manifest':checkpoint,'writers':instances,'health':health,'dead_process_exit':receipt['exit_code'],'detection_seconds':time.monotonic()-started}
        finally: supervisor.close()
    if request['action']=='recovery_state':
        pointer=json.loads((root/'state/active-generation.json').read_bytes())
        path=root/'state/generations'/pointer['generation']/'evaluation.sqlite'
        with sqlite3.connect(path.as_uri()+'?mode=ro',uri=True) as conn:
            row=conn.execute("SELECT value FROM state WHERE key='evaluation_status'").fetchone()
            return {'status':json.loads(row[0]) if row else 'VERIFIED'}
    if request['action']=='interrupt_restore':
        import os
        from compertum.runtime._windows import WindowsAPI
        original=WindowsAPI.publish_metadata
        def interrupt(api,path,raw):
            original(api,path,raw)
            if Path(path).name=='restore-operation.json' and json.loads(raw)['status']=='STAGING_EVALUATION': os._exit(17)
        WindowsAPI.publish_metadata=interrupt
        restore_recovery_set(Path(request['manifest']),verify_consumption_guard(project),project.root_path/'state/generations'/str(uuid4()),project=project)
        raise RuntimeRefused('INTERRUPTION_NOT_REACHED')
    if request['action']=='probe_blocked':
        lease=acquire_owner(project,'coordinator')
        try:
            try: open_store(lease,'coordinator')
            except RuntimeRefused as error: return {'status':error.code}
            raise RuntimeRefused('MIXED_GENERATION_ADMITTED')
        finally: release_owner(lease)
    if request['action']=='recover_interruption':
        from compertum.recovery import recover_interrupted_restore
        return recover_interrupted_restore(project)
    if request['action']=='restore_known_guard':
        # Repeated qualification is an explicit restore into another generation,
        # preserving the prior (including compromised) fixture state and receipts.
        phase=json.loads((root/'state/restore-operation.json').read_bytes())
        import hashlib
        source=next(path for path in (root/'backups').rglob('manifest.json') if hashlib.sha256(path.read_bytes()).hexdigest()==phase['manifest_sha256'])
        return restore_recovery_set(source,verify_consumption_guard(project),project.root_path/'state/generations'/str(uuid4()),project=project)
    if request['action']=='attempt_consume':
        lease=acquire_owner(project,'evaluation')
        try:
            open_store(lease,'evaluation')
            try: consume_once(lease,request['seal_id'],str(uuid4()),INPUTS)
            except RuntimeRefused as error:
                if error.code not in {'SEAL_ALREADY_CONSUMED','EVALUATION_COMPROMISED'}: raise
                return {'status':'DENIED','reason':error.code}
            raise RuntimeRefused('REPEAT_CONSUMPTION_ADMITTED')
        finally: release_owner(lease)
    if request['action']=='old_guard_restore':
        import shutil
        directory=root/'state/evaluation-consumption'
        retained=root/'state'/('retained-guard-'+str(uuid4()))
        directory.rename(retained)
        try:
            shutil.copytree(request['guard_before'],directory)
            result=restore_recovery_set(Path(request['manifest']),verify_consumption_guard(project),root/'state/generations'/str(uuid4()),project=project)
            return result
        finally:
            directory.rename(root/'state'/('rolled-back-guard-'+str(uuid4())))
            retained.rename(directory)
    if request['action']=='prepare':
        leases={};stores={}
        try:
            for role in (*STORE_NAMES,'watchdog','recovery'): leases[role]=acquire_owner(project,role)
            for role in STORE_NAMES: stores[role]=open_store(leases[role],role)
            source=Path(__file__).parents[2]/'config/default.toml';config=root/'config.toml'
            if not config.exists(): config.write_bytes(source.read_bytes())
            elif config.read_bytes()!=source.read_bytes(): raise RuntimeRefused('FIXTURE_CONFIG_MISMATCH')
            manager=StorageManager(leases['coordinator'],load_config(config,root))
            reserve=open_journal_reserve(leases['execution']) if (root/'state/execution-reserve.bin').exists() else create_journal_reserve(leases['execution'])
            task_id=str(uuid4());writer=manager.open_artifact(manager.reserve_bytes(task_id,'records',128),f'artifacts/runs/{task_id}/fixture.bin')
            writer.write(b'compertum-offline-fixture-v1\n');artifact=writer.publish()
            artifact={key:artifact[key] for key in ('artifact_id','path','size_bytes','sha256')}|{'parent_artifact_ids':[]}
            def send(kind='FIXTURE_TRANSITION',target='evaluation'):
                item={'event_id':str(uuid4()),'kind':kind,'target_role':target,'payload':{'key':'fixture','value':task_id}}
                stores['coordinator'].commit_event(item);return item['event_id']
            ack_event=send();message=next(m for m in stores['coordinator'].pending() if m['event_id']==ack_event)
            ack=stores['evaluation'].accept_message(message);stores['coordinator'].acknowledge(ack_event,ack)
            pending=send();send('BROKER_SIDE_EFFECT','execution')
            def collect():
                grant=manager.reserve_bytes(str(uuid4()),'backups',8*1024**2)
                return collect_recovery_set(project,list(stores.values()),grant,recovery_lease=leases['recovery'],watchdog_lease=leases['watchdog'],reserve=reserve,artifacts=[artifact])
            from compertum.ai.manual import ManualBridge,export_fixture_packet
            from datetime import datetime,timezone
            bridge=ManualBridge(manager);ai_id=str(uuid4());packet=export_fixture_packet(bridge,ai_id)
            packet_value=json.loads((root/packet['path']).read_bytes())
            sys.path.insert(0,str(Path(__file__).parent))
            from ai_fixture import proposal
            from compertum.domain import TaskSpec
            task=TaskSpec(json.loads(bridge.store.conn.execute('SELECT task FROM ai_tasks WHERE task_id=?',(ai_id,)).fetchone()[0]),project_root=root)
            response=proposal(task,packet_value['prompt_sha256']);response['provider']['model_label']='synthetic-model'
            inbox=root/'artifacts/inbox';inbox.mkdir(exist_ok=True);response_path=inbox/(ai_id+'.json');response_path.write_bytes(canonical(response))
            imported=bridge.import_proposal(ai_id,response_path,{'provider':'manual_subscription','model_label':'synthetic-model','received_at':datetime.now(timezone.utc).isoformat(),'provenance':'SYNTHETIC_FIXTURE'})
            operation=None
            if request.get('fake_operation'):
                from operation_recovery_support import prepare
                operation,before=prepare(root,leases,stores,reserve,collect)
            elif request.get('paper_preparation'):
                from paper_consumption_support import prepare
                operation,before=prepare(root,leases,stores,reserve,collect)
            else:before=collect()
            seal,evaluation=str(uuid4()),str(uuid4())
            import shutil
            guard_before=root/'state'/('guard-before-'+str(uuid4()))
            shutil.copytree(root/'state/evaluation-consumption',guard_before)
            consume_once(leases['evaluation'],seal,evaluation,INPUTS)
            after=collect()
            return {'fake_operation':operation,'actual_reserve':reserve.receipt(),'ai_packet':packet,'ai_response':imported['original'],'guard_before':str(guard_before),'before':before['manifest_path'],'after':after['manifest_path'],'seal_id':seal,'evaluation_id':evaluation,'pending_event':pending,'ack_event':ack_event}
        finally:
            for lease in reversed(list(leases.values())): release_owner(lease)
    if request['action']=='restore':
        evidence=verify_consumption_guard(project)
        if request.get('uncertain_guard'): evidence={**evidence,'status':'EVALUATION_COMPROMISED'}
        destination=project.root_path/'state/generations'/str(uuid4())
        result=restore_recovery_set(Path(request['manifest']),evidence,destination,project=project)
        # Inspect with read-only SQLite after the restoring owner handles close.
        with sqlite3.connect((destination/'evaluation.sqlite').as_uri()+'?mode=ro',uri=True) as conn:
            row=conn.execute('SELECT body FROM consumption WHERE seal_id=?',(request['seal_id'],)).fetchone()
            status=json.loads(conn.execute("SELECT value FROM state WHERE key='evaluation_status'").fetchone()[0])
            result['new_evaluation_denied']=status=='EVALUATION_COMPROMISED' or (row is not None and json.loads(row[0])['evaluation_id']==request['evaluation_id'])
            event_ids={row['event_id'] for row in validate_recovery_set(Path(request['manifest']),project_root=root)['manifest']['messages']['pending'] if row['receiver_role']=='evaluation'}
            result['safe_delivery_count']=conn.execute('SELECT count(*) FROM inbox WHERE event_id=?',(request['pending_event'],)).fetchone()[0]
        with sqlite3.connect((destination/'research.sqlite').as_uri()+'?mode=ro',uri=True) as conn:
            result['broker_pending']=sum(json.loads(row[0])['kind']=='BROKER_SIDE_EFFECT' for row in conn.execute('SELECT body FROM events JOIN outbox USING(event_id) WHERE ack IS NULL'))
        return result
    if request['action']=='corrupt_copy':
        value=json.loads(Path(request['manifest']).read_bytes())
        value['artifacts'][0]['sha256']='0'*64
        altered=root/('corrupt-'+str(uuid4())+'.json');altered.write_bytes(canonical(value))
        pointer=root/'state/active-generation.json';before=pointer.read_bytes()
        result=validate_recovery_set(altered,project_root=root)
        try: restore_recovery_set(altered,verify_consumption_guard(project),project.root_path/'state/generations'/str(uuid4()),project=project)
        except RuntimeRefused: pass
        else: raise RuntimeRefused('INVALID_RECOVERY_PUBLISHED')
        return {**result,'active_generation_unchanged':pointer.read_bytes()==before}
    raise RuntimeRefused('FIXTURE_ACTION_DENIED')


if __name__=='__main__':
    try:
        import compertum
        result=main();result['package_origin']=str(Path(compertum.__file__).resolve());print(json.dumps(result,sort_keys=True))
    except RuntimeRefused as error: print(json.dumps({'status':error.code}));raise SystemExit(3)
