"""Foreground M0 supervisor/coordinator with an independent native watchdog."""
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import time
from uuid import uuid4,uuid5,NAMESPACE_URL
from .identity import resolve_project
from .owners import acquire_owner,release_owner,_metadata
from .ipc import start_role_pipe,PipeDescriptor,PeerRegistration
from .control import serve_control_once,durable_request,disconnected
from .managed import launch_owner,constrain_coordinator
from .owner_rpc import call_owner
from .errors import RuntimeRefused
from ._windows import WindowsAPI
from .jobs import available_physical_memory
from compertum.coordinator import Coordinator,CONTROL_ACTIONS
from compertum.foundation import FixtureController,fixture_spec
from compertum.persistence import open_store,checked_path
from compertum.storage import StorageManager,reserve_runtime_paths
from compertum.events import canonical,uuid

ACTIONS=CONTROL_ACTIONS|frozenset({'status','foundation.check','attach','ai.export','ai.import','baseline','final','final_audit','fake_operator','paper_read','paper_market_read','paper_presence','paper_intent'})


def discover(root):
    project=resolve_project(Path(root).absolute());api=WindowsAPI()
    raw=api.read_regular(project.root_path/'state/locks/supervisor.json')
    generation,identity=_metadata(raw,project,'supervisor')
    value=json.loads(raw)
    if value['endpoint'] is None: raise RuntimeRefused('SUPERVISOR_NOT_READY')
    return PipeDescriptor(PeerRegistration(identity,project.logon_sid,project.project_id,generation,'worker'))


def control(root,action,payload=None,*,request_id=None):
    route=discover(root)
    command={'schema_version':1,'request_id':request_id or str(uuid4()),'target_role':'supervisor',
             'target_generation':route.registration.generation,'action':action,'payload':payload or {},'actor':{'kind':'operator'}}
    return durable_request(route,command)


class Supervisor:
    def __init__(self,config,*,_partial_fixture=False):
        self.config=config;self.project=resolve_project(config.project_root);self.leases=[];self.jobs=[]
        self.partial_fixture=_partial_fixture
        if _partial_fixture and '.cache' not in config.project_root.parts: raise RuntimeRefused('FIXTURE_ROOT_DENIED')
        self.self_job=None;self.limits=None;self.health=None;self.last_poll=0;self.shutdown=False;self.fixtures=None;self.research=None;self.final=None;self.final_audit=None;self.paper_reads=None;self.paper_market_reads=None
        try:
            self.self_job,self.limits=constrain_coordinator()
            self.supervisor=acquire_owner(self.project,'supervisor');self.leases.append(self.supervisor)
            self.coordinator_lease=acquire_owner(self.project,'coordinator');self.leases.append(self.coordinator_lease)
            self.store=open_store(self.coordinator_lease,'coordinator')
            self.storage=StorageManager(self.coordinator_lease,config)
            self.coordinator=Coordinator(self.store,health=self.get_health,refresh_health=self.poll_health,halt=self.halt,checkpoint=self.checkpoint,stop_run=self.stop_run)
            self.fixtures=FixtureController(self.coordinator,self.storage)
            from compertum.research import ResearchController
            self.research=ResearchController(self.coordinator,self.storage,cooperative=True)
            with self.store.conn:
                self.store.conn.execute('CREATE TABLE IF NOT EXISTS operator_requests(request_id TEXT PRIMARY KEY,binding TEXT NOT NULL,result TEXT,error TEXT)')
                self.store.conn.execute('CREATE TABLE IF NOT EXISTS fixture_requests(request_id TEXT PRIMARY KEY,binding TEXT NOT NULL,task_id TEXT NOT NULL,result TEXT)')
            from compertum.ai.manual import ManualBridge
            self.manual=ManualBridge(self.storage)
            reserve_runtime_paths(self.storage)
            if not self.partial_fixture:
                from .recovery_adapter import RemoteStore
                self.recovery=acquire_owner(self.project,'recovery');self.leases.append(self.recovery)
                for role in ('evaluation','execution'):
                    child,remote=launch_owner(self.supervisor,role);self.jobs.append(child)
                    setattr(self,role,RemoteStore(remote,self.project.root_path))
                    call_owner(remote,'status',{})
                from compertum.final_controller import FinalController
                self.final=FinalController(self.coordinator,self.storage,self.evaluation.remote)
                from compertum.final_audit_controller import FinalAuditController
                self.final_audit=FinalAuditController(self.coordinator,self.storage)
            job,self.watchdog=launch_owner(self.supervisor,'watchdog',expect_execution=not self.partial_fixture);self.jobs.append(job)
            self.poll_health()
            self.endpoint=start_role_pipe(self.supervisor,ACTIONS)
        except BaseException:
            self.close();raise

    def get_health(self):
        if self.health is None: return {'status':'UNVERIFIED'}
        return dict(self.health)

    def poll_health(self):
        self.last_poll=time.monotonic()
        try:
            self.health=call_owner(self.watchdog,'status',{})
            self.health['owners']={}
            if not self.partial_fixture:
                for role in ('evaluation','execution'):
                    try:
                        owner=call_owner(getattr(self,role).remote,'status',{})
                        self.health['owners'][role]=owner
                        if owner.get('status')!='HEALTHY': raise RuntimeRefused('OWNER_UNHEALTHY')
                    except RuntimeRefused:
                        self.health['owners'][role]={'status':'UNVERIFIED'}
                        self.health['status']='RESEARCH_BLOCKED';self.health['reason']=role.upper()+'_OWNER_UNAVAILABLE'
            if not self.partial_fixture:
                execution=self.health['owners'].get('execution',{})
                if not execution.get('heartbeat') or not self.health.get('heartbeat'):raise RuntimeRefused('MUTUAL_HEALTH_UNVERIFIED')
                for remote,heartbeat in ((self.watchdog,execution['heartbeat']),(self.execution.remote,self.health['heartbeat'])):
                    ack=call_owner(remote,'owner_heartbeat',heartbeat)
                    if ack.get('verified') is not True or ack.get('reason') is not None:raise RuntimeRefused('MUTUAL_HEALTH_UNVERIFIED')
                    if remote is self.watchdog:self.health['mutual']=ack
                    else:execution['mutual']=ack
            if available_physical_memory()<6*1024**3: self.health['status']='RESEARCH_BLOCKED';self.health['reason']='AVAILABLE_RAM_FLOOR'
        except RuntimeRefused:
            self.health={'status':'RESEARCH_BLOCKED','reason':'WATCHDOG_UNAVAILABLE','observed_monotonic':time.monotonic()}
        if self.health['status']!='HEALTHY':
            self.halt('health')
            with self.store.conn: self.coordinator._state('research_state','PAUSED')

    def halt(self,reason):
        if self.fixtures is not None: self.fixtures.pause(reason)
        if self.research is not None:self.research.pause('HEALTH_HALT' if reason=='health' else 'OPERATOR_PAUSE')
        if self.final is not None:self.final.pause(reason,terminal=reason=='stop_research')
        if self.final_audit is not None:self.final_audit.pause(reason,terminal=reason=='stop_research')

    def stop_run(self,run_id):
        uuid(run_id)
        if self.final_audit is not None:
            if self.final_audit.active and self.final_audit.active[0]['task_id']!=run_id:raise RuntimeRefused('RUN_NOT_ACTIVE')
            if any(r['task_id']==run_id for r in self.final_audit.records()):
                return self.final_audit.control(dict(operation='stop',task_id=run_id))
        if self.final is not None:
            if self.final.active and self.final.active[0]['attempt']['evaluation_id']!=run_id:raise RuntimeRefused('RUN_NOT_ACTIVE')
            final=next((r for r in self.final.records() if r['evaluation_id']==run_id),None)
            if final is not None:
                if self.fixtures.active or self.research.busy:raise RuntimeRefused('RUN_NOT_ACTIVE')
                from compertum.data.errors import DataError
                try:self.final.control(final['seal_id'],'stop')
                except DataError as error:raise RuntimeRefused(error.code) from None
                return
        baseline=self.store.conn.execute('SELECT 1 FROM baseline_runs WHERE run_id=?',(run_id,)).fetchone()
        row=self.store.conn.execute('SELECT task_id,status FROM fixture_tasks WHERE run_id=?',(run_id,)).fetchone()
        if baseline is None and row is None:raise RuntimeRefused('RUN_UNKNOWN')
        if (self.fixtures.active and self.fixtures.active[1]!=run_id) or (self.research.active and self.research.active[0]!=run_id):
            raise RuntimeRefused('RUN_NOT_ACTIVE')
        if self.research.pending is not None and self.research.pending.run_id!=run_id:raise RuntimeRefused('RUN_NOT_ACTIVE')
        if baseline is not None:
            from compertum.data.errors import DataError
            if self.research.runs.summary(run_id)['state']=='STOPPED':return
            try:self.research.control(run_id,str(uuid4()),'stop')
            except DataError as error:raise RuntimeRefused(error.code) from None
            return
        if self.fixtures.active is not None and self.fixtures.active[1]!=run_id: raise RuntimeRefused('RUN_NOT_ACTIVE')
        if self.fixtures.active is not None: self.fixtures.pause('stop_research')

    def checkpoint(self):
        self.halt('checkpoint')
        from compertum.final_audit_runs import require_closed_audits
        from compertum.data.errors import DataError
        try:require_closed_audits(self.store,self.coordinator_lease.identity.process_instance_id)
        except DataError as error:raise RuntimeRefused(error.code) from None
        if not self.partial_fixture:
            from .recovery_adapter import RemoteReserve
            from compertum.recovery import collect_recovery_set
            grant=self.storage.reserve_bytes(str(uuid4()),'backups',64*1024**2)
            result=collect_recovery_set(self.project,[self.store,self.evaluation,self.execution],grant,
                recovery_lease=self.recovery,watchdog_lease=self.watchdog,reserve=RemoteReserve(self.execution))
            path=Path(result['manifest_path'])
            return [{'artifact_id':result['manifest']['recovery_set_id'],'path':path.relative_to(self.project.root_path).as_posix(),
                'size_bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}]
        task_id=str(uuid4());grant=self.storage.reserve_bytes(task_id,'backups',16*1024**2)
        record=self.storage.checkpoint(grant,self.store,str(uuid4()),f'backups/{task_id}/research.sqlite')
        return [{'artifact_id':record['checkpoint_id'],'path':record['path'].replace('\\','/'),
                 'size_bytes':record['size_bytes'],'sha256':record['sha256']}]

    def status(self):
        return {**self.coordinator.status(),'supervisor_generation':self.supervisor.generation,
                'recovery_scope':'PARTIAL_TEST_FIXTURE' if self.partial_fixture else 'COMPLETE_THREE_OWNER_BARRIER','coordinator_limits':self.limits,'active_job_pid':self.fixtures.active[-1].pid if self.fixtures.active else None,
                'state_owner_processes':{} if self.partial_fixture else {role:getattr(self,role).lease.identity.pid for role in ('evaluation','execution')},
                'watchdog':self.get_health(),'fixtures':self.fixtures.records(),'ai_dispatch':'DISABLED',
                'final_runs':self.final.records() if self.final is not None else [],
                'final_audits':self.final_audit.records() if self.final_audit is not None else [],
                'active_final_audit_pid':self.final_audit.active[-1].pid if self.final_audit is not None and self.final_audit.active else None,
                'active_final_pid':self.final.active[-1].pid if self.final is not None and self.final.active else None,
                'saved_runs':self.research.records(),'pending_research':self.research.pending_status(),'active_replay_pid':self.research.active[-1].pid if self.research.active else None}

    def fixture_control(self,decision,payload):
        if not isinstance(payload,dict) or payload.get('operation') not in {'submit','resume'}:
            raise RuntimeRefused('CONTROL_PAYLOAD_DENIED')
        operation=payload['operation']
        if self.research.busy or (self.final is not None and self.final.active is not None) or (self.final_audit is not None and self.final_audit.active is not None):raise RuntimeRefused('JOB_SLOT_BUSY')
        if set(payload)!=({'operation'} if operation=='submit' else {'operation','task_id'}): raise RuntimeRefused('CONTROL_PAYLOAD_DENIED')
        binding=canonical(asdict(decision)).decode()
        with self.store._live():
            old=self.store.conn.execute('SELECT binding,task_id,result FROM fixture_requests WHERE request_id=?',(decision.request_id,)).fetchone()
            if old:
                if old[0]!=binding: raise RuntimeRefused('REQUEST_CONFLICT')
                if old[2]: return json.loads(old[2])
                task_id=old[1]
                existing=next((r for r in self.fixtures.records() if r['task_id']==task_id),None)
                if existing is not None: return existing
            else:
                task_id=str(uuid5(NAMESPACE_URL,self.project.project_id+decision.request_id)) if operation=='submit' else payload['task_id']
                uuid(task_id)
                with self.store.conn: self.store.conn.execute('INSERT INTO fixture_requests VALUES(?,?,?,NULL)',(decision.request_id,binding,task_id))
            result=self.fixtures.submit(fixture_spec(self.project.root_path,task_id)) if operation=='submit' else self.fixtures.resume(task_id)
            with self.store.conn: self.store.conn.execute('UPDATE fixture_requests SET result=? WHERE request_id=?',(canonical(result).decode(),decision.request_id))
            return result

    def handle(self,decision,action,payload):
        binding=canonical({'decision':asdict(decision),'action':action,'payload':payload}).decode()
        read_only=(action=='paper_read' and isinstance(payload,dict) and payload.get('operation')=='account_status') or action in {'status','attach'} or (action in {'baseline','final','final_audit','fake_operator','paper_read'} and isinstance(payload,dict) and payload.get('operation')=='status') or (action=='fake_operator' and isinstance(payload,dict) and payload.get('operation') in {'inspect_plan','operation_status'})
        read_only=read_only or (action=='paper_market_read' and isinstance(payload,dict) and payload.get('operation') in {'status','compose','lineage_status'})
        read_only=read_only or (action in {'paper_presence','paper_intent'} and isinstance(payload,dict) and payload.get('operation')=='inspect')
        with self.store._live():
            old=self.store.conn.execute('SELECT binding,result,error FROM operator_requests WHERE request_id=?',(decision.request_id,)).fetchone()
            if old:
                if old[0]!=binding: raise RuntimeRefused('REQUEST_CONFLICT')
                if old[2] is not None: raise RuntimeRefused(old[2])
                if old[1] is not None: return json.loads(old[1])
            elif not read_only:
                if self.store.conn.execute('SELECT count(*) FROM operator_requests').fetchone()[0]>=10000: raise RuntimeRefused('REQUEST_BOUND_EXCEEDED')
                with self.store.conn: self.store.conn.execute('INSERT INTO operator_requests VALUES(?,?,NULL,NULL)',(decision.request_id,binding))
            try: result=self._dispatch(decision,action,payload)
            except RuntimeRefused as error:
                if not read_only:
                    with self.store.conn: self.store.conn.execute('UPDATE operator_requests SET error=? WHERE request_id=?',(error.code,decision.request_id))
                raise
            if not read_only:
                with self.store.conn: self.store.conn.execute('UPDATE operator_requests SET result=? WHERE request_id=?',(canonical(result).decode(),decision.request_id))
            return result

    def _dispatch(self,decision,action,payload):
        if action in {'status','attach'}:
            if payload: raise RuntimeRefused('CONTROL_PAYLOAD_DENIED')
            return self.status()
        if action=='paper_read':
            if self.partial_fixture:raise RuntimeRefused('EXECUTION_UNAVAILABLE')
            if self.paper_reads is None:
                from .paper_read_publication import PaperReadPublication
                self.paper_reads=PaperReadPublication(self.storage,self.execution.remote)
            return self.paper_reads.handle(decision.subject_key,payload)
        if action=='paper_market_read':
            if self.partial_fixture:raise RuntimeRefused('EXECUTION_UNAVAILABLE')
            if self.paper_market_reads is None:
                from .paper_market_publication import PaperMarketPublication
                self.paper_market_reads=PaperMarketPublication(self.storage,self.execution.remote)
            return self.paper_market_reads.handle(decision.subject_key,payload)
        if action=='fake_operator':
            if self.partial_fixture:raise RuntimeRefused('EXECUTION_UNAVAILABLE')
            # Native operator identity comes from serve_control_once, never payload.
            return call_owner(self.execution.remote,'fake_operator',dict(request_id=decision.request_id,subject_key=decision.subject_key,command=payload))
        if action in {'paper_presence','paper_intent'}:
            if self.partial_fixture:raise RuntimeRefused('EXECUTION_UNAVAILABLE')
            return call_owner(self.execution.remote,action,dict(request_id=decision.request_id,subject_key=decision.subject_key,command=payload))
        if action=='foundation.check': return self.fixture_control(decision,payload)
        if action=='final_audit':
            from compertum.data.errors import DataError
            if self.final_audit is None:raise RuntimeRefused('FINAL_AUDIT_UNAVAILABLE')
            if isinstance(payload,dict) and payload.get('operation') in {'step','resume'} and (self.fixtures.active or self.research.busy or (self.final is not None and self.final.active is not None)):raise RuntimeRefused('JOB_SLOT_BUSY')
            try:return self.final_audit.control(payload)
            except DataError as error:raise RuntimeRefused(error.code) from None
        if action=='final':
            from compertum.data.errors import DataError
            if self.final is None:raise RuntimeRefused('FINAL_UNAVAILABLE')
            if not isinstance(payload,dict) or set(payload)!={'seal_id','operation'} or payload['operation'] not in {'status','step','resume','pause','stop','recover'}:raise RuntimeRefused('CONTROL_PAYLOAD_DENIED')
            uuid(payload['seal_id'])
            if payload['operation'] in {'step','resume'} and (self.fixtures.active or self.research.busy or (self.final_audit is not None and self.final_audit.active is not None)):raise RuntimeRefused('JOB_SLOT_BUSY')
            try:return self.final.control(payload['seal_id'],payload['operation'])
            except DataError as error:raise RuntimeRefused(error.code) from None
        if action=='baseline':
            from compertum.data.errors import DataError
            if not isinstance(payload,dict) or set(payload)!={'run_id','operation'} or payload['operation'] not in {'status','resume','step','pause','stop'}:
                raise RuntimeRefused('CONTROL_PAYLOAD_DENIED')
            uuid(payload['run_id'])
            if payload['operation'] in {'resume','step'} and ((self.final is not None and self.final.active is not None) or (self.final_audit is not None and self.final_audit.active is not None)):raise RuntimeRefused('JOB_SLOT_BUSY')
            try:return self.research.control(payload['run_id'],decision.request_id,payload['operation'])
            except DataError as error:raise RuntimeRefused(error.code) from None
        if action=='ai.export':
            from compertum.ai.manual import export_fixture_packet
            if set(payload)!={'task_id','provider'} or payload['provider']!='subscription': raise RuntimeRefused('CONTROL_PAYLOAD_DENIED')
            artifact=export_fixture_packet(self.manual,payload['task_id'])
            return {'status':'WAITING_FOR_OPERATOR','artifact':artifact,'usage_status':'UNKNOWN','executed':False}
        if action=='ai.import':
            from compertum.ai.manual import sanitized,read_json
            if set(payload)!={'task_id','response'}: raise RuntimeRefused('CONTROL_PAYLOAD_DENIED')
            from compertum.domain import resolve_project_path
            path=resolve_project_path(payload['response'],self.project.root_path)
            if not path.is_relative_to(self.project.root_path/'artifacts/inbox'): raise RuntimeRefused('AI_BUNDLE_DENIED')
            sidecar=checked_path(self.project.root_path,path.with_name(path.name+'.metadata.json'))
            with sidecar.open('rb') as stream: raw=stream.read(8193)
            if len(raw)>8192: raise RuntimeRefused('AI_INPUT_BOUND')
            sanitized(raw);metadata=read_json(raw)
            return self.manual.import_proposal(payload['task_id'],path,metadata)
        result=self.coordinator.control(decision,action,payload)
        if action=='shutdown': self.shutdown=True
        return result

    def run(self,*,maximum_seconds=None):
        deadline=time.monotonic()+maximum_seconds if maximum_seconds is not None else float('inf')
        try:
            while not self.shutdown and time.monotonic()<deadline:
                if time.monotonic()-self.last_poll>=.8: self.poll_health()
                if self.health['status']=='HEALTHY':
                    self.fixtures.tick();self.research.tick()
                    if self.final is not None:self.final.tick()
                    if self.final_audit is not None:self.final_audit.tick()
                if self.paper_reads is not None:self.paper_reads.tick()
                if self.paper_market_reads is not None:self.paper_market_reads.tick()
                try: serve_control_once(self.endpoint,self.handle,timeout=.1)
                except RuntimeRefused as error:
                    if error.code not in {'PIPE_DEADLINE_EXCEEDED','PIPE_EOF','REPLY_ACK_DENIED'} and not disconnected(error): raise
        finally: self.close()

    def close(self):
        if self.fixtures is not None: self.halt('shutdown')
        for job in reversed(self.jobs): job.close()
        self.jobs=[]
        for lease in reversed(self.leases): release_owner(lease)
        self.leases=[]
        if self.self_job is not None: self.self_job.close();self.self_job=None




