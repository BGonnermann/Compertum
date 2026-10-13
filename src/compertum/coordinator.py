"""Single-writer fixture lifecycle, budgets and restrictive admission."""
import json,time,threading
from dataclasses import asdict
from pathlib import Path
from .domain import TaskSpec,Budget,ContractError,atomic_json,canonical,digest,file_hash,new_id,now,within
from .persistence import open_store
from .runtime.owners import acquire_owner
from .runtime.ipc import start_role_pipe
from .runtime.jobs import launch_bounded
from .runtime.supervisor import spawn_service
from .storage import StorageManager
from .recovery import restore_admission

FIXTURE={'answer':14,'fixture':'m0-v1'}
def fixture_code_hash():return file_hash(Path(__file__).with_name('coordinator.py'))

class Coordinator:
    def __init__(self,store):
        self.store=store;self.root=store.lease.project.root_path;self.manager=StorageManager(store);self.quit=threading.Event()
        for task in self.tasks():
            if task['state']=='RUNNING':
                task['state']='INTERRUPTED';task['attempt_history'].append({'state':'INTERRUPTED','at':now()});self.save(task)
        self.store.set('paused',True) # Every start is conservatively paused.
    def tasks(self):
        with self.store.lock:return [json.loads(r[0]) for r in self.store.db.execute("SELECT value FROM kv WHERE key LIKE 'task:%'")]
    def save(self,task):self.store.set('task:'+task['task_id'],task)
    def health(self):
        try:
            wd=json.loads((self.root/'state/watchdog/heartbeat.json').read_text())
            if time.monotonic()-wd['monotonic']>15 or not wd['storage_healthy']:return False
            peer=self.store.get('watchdog-role-health',{})
            if time.monotonic()-peer.get('monotonic',0)>15 or peer.get('storage_healthy') is not True:return False
            return restore_admission(self.root)
        except (OSError,ValueError,KeyError):return False
    def status(self):return {'broker':'NOT_CONFIGURED','strategy':'STRATEGY_NOT_EVALUATED','paper':'PAPER_DISABLED','order_admission':'DISARMED','research_paused':self.store.get('paused',True),'storage_healthy':self.health(),'ai_dispatch':'MANUAL_OR_UNQUALIFIED','execution_active':False,'tasks':self.tasks(),'generation':self.store.lease.generation}
    def handle(self,command):
        action=command['action']
        if action=='status':return self.status()
        if action=='watchdog-health':
            if type(command.get('storage_healthy')) is not bool:raise ContractError('WATCHDOG_HEALTH_SCHEMA')
            self.store.set('watchdog-role-health',{'monotonic':time.monotonic(),'at':now(),'storage_healthy':command['storage_healthy']});return {'state':'AUTHENTICATED'}
        if action in {'ai-export','ai-import','ai-export-existing','ai-import-inbox'}:
            from .ai.manual import export_subscription_task,import_proposal,import_inbox_proposal
            if not self.health():raise ContractError('ADMISSION_UNHEALTHY')
            if action=='ai-export-existing':
                waiting=self.store.get('ai:'+command['task_id'])
                if not waiting:raise ContractError('AI_TASK_UNKNOWN')
                return waiting['packet']
            if action=='ai-import-inbox':return import_inbox_proposal(self.store,command['task_id'],command['response_path'])
            if action=='ai-export':
                task=TaskSpec(kind='AI_PROPOSAL',role='proposer',expected_schema='ai_proposal',permissions=('model_proposal',))
                return export_subscription_task(self.store,task,{'question':command['question'],'fixture':True})
            return import_proposal(self.store,command['task_id'],command['response_path'],command['metadata'])
        if action=='pause':
            self.store.set('paused',True)
            for t in self.tasks():
                if t['state']=='RUNNING':t['state']='PAUSED';self.save(t)
            return {'state':'PAUSED','checkpointed':True}
        if action=='resume':
            if not self.health():raise ContractError('ADMISSION_UNHEALTHY')
            for t in self.tasks():
                if t['state'] in {'PAUSED','INTERRUPTED'}:
                    if t['code_hash']!=fixture_code_hash() or t['inputs_hash']!=digest(FIXTURE):raise ContractError('CHECKPOINT_HASH_MISMATCH')
                    if t['attempts']>=2:raise ContractError('ATTEMPTS_EXHAUSTED')
                    t['attempts']+=1;t['state']='RUNNING';self.save(t)
            self.store.set('paused',False);return {'state':'RUNNING'}
        if action=='fixture':
            if self.store.get('paused',True) or not self.health():raise ContractError('ADMISSION_UNHEALTHY')
            if any(t['state']=='RUNNING' for t in self.tasks()):raise ContractError('RESOURCE_BUSY')
            day=now()[:10];reserved=self.store.get('cpu:'+day,0)
            if reserved+10>7200:raise ContractError('DAILY_CPU_LIMIT')
            self.store.set('cpu:'+day,reserved+10) # Reserve full trusted fixture deadline; crash never refunds.
            task={'task_id':new_id(),'kind':'OFFLINE_FIXTURE','state':'RUNNING','step':0,'attempts':1,'attempt_history':[],'code_hash':fixture_code_hash(),'inputs_hash':digest(FIXTURE),'lease_until_monotonic':time.monotonic()+30,'created_at':now()}
            self.save(task);return task
        if action=='stop':
            task=self.store.get('task:'+command.get('run_id',''))
            if not task:raise ContractError('RUN_UNKNOWN')
            task['state']='STOPPED';self.save(task);return task
        if action=='shutdown':
            self.handle({'action':'pause'});self.quit.set();return {'state':'CHECKPOINTED'}
        raise ContractError('CAPABILITY_UNAVAILABLE')
    def tick(self):
        if self.store.get('paused',True) or not self.health():return
        with self.store.transaction():
            for t in self.tasks():
                if t['state']!='RUNNING':continue
                if time.monotonic()>t['lease_until_monotonic']:
                    t['state']='INTERRUPTED';t['attempt_history'].append({'state':'INTERRUPTED','reason':'LEASE_GAP','at':now()});self.save(t);self.store.set('paused',True);continue
                if t['code_hash']!=fixture_code_hash() or t['inputs_hash']!=digest(FIXTURE):
                    t['state']='FAILED_HASH';self.save(t);continue
                t['lease_until_monotonic']=time.monotonic()+30
                if t['step']<10:t['step']+=1;self.save(t);continue
                spec=TaskSpec(task_id=t['task_id'],budget=Budget(ram_bytes=128*1024**2,wall_seconds=10,output_bytes=1024**2))
                grant=self.manager.reserve_bytes(t['task_id'],'records',1024)
                result=launch_bounded(self.store.lease,spec,['fixture']).wait()
                if result['exit_code'] or result['active_processes']!=0:raise ContractError('FIXTURE_PROCESS_FAILED')
                if json.loads(result['stdout'])['sum']!=14:raise ContractError('FIXTURE_RESULT_INVALID')
                writer=self.manager.open_artifact(grant,'artifacts/foundation/'+t['task_id']+'.json')
                try:writer.write(canonical(FIXTURE));manifest=writer.publish()
                finally:writer.close()
                t.update(state='COMPLETE',artifact=manifest,process=result,completed_at=now());self.save(t)
                self.store.commit_event({'event_id':t['task_id'],'kind':'ARTIFACT_REGISTERED','payload':manifest})

def serve(project,supervisor_lease):
    shutdown=project.root_path/'state/runtime/shutdown.json'
    if shutdown.exists():shutdown.unlink() # Own prior transient stop marker only.
    with acquire_owner(project,'coordinator') as lease:
        store=open_store(lease,'coordinator');coordinator=Coordinator(store);pipe=start_role_pipe(lease,{'status','pause','resume','stop','shutdown','fixture','ai-export','ai-import','ai-export-existing','ai-import-inbox'},coordinator.handle,store)
        atomic_json(project.root_path/'state/runtime/endpoint.json',asdict(pipe.endpoint));watchdog=spawn_service(project.root_path,'watchdog',peer_server=pipe)
        try:
            while not coordinator.quit.wait(.2):
                atomic_json(project.root_path/'state/runtime/heartbeat.json',{'at':now(),'monotonic':time.monotonic(),'generation':lease.generation})
                try:coordinator.tick()
                except Exception as exc:
                    store.set('paused',True);store.set('incident',{'at':now(),'reason':type(exc).__name__})
        finally:
            atomic_json(shutdown,{'at':now(),'generation':lease.generation});pipe.close();store.close()
            try:watchdog.wait(timeout=15)
            except Exception:pass # Refuse takeover while old watchdog remains alive.
