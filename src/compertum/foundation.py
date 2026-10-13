"""Deterministic, restartable M0 fixture using an admitted inherited sink."""
from datetime import datetime,timedelta,timezone
import hashlib
import json
from pathlib import Path
import sysconfig
import time
from uuid import uuid4
from .domain import TaskSpec
from .events import canonical,uuid
from .persistence import checked_path
from .runtime.errors import RuntimeRefused
from .runtime.jobs import launch_bounded
from .runtime.fixture_worker import CANONICAL
from .storage import adopt_fixture_bytes


def fixture_spec(root,task_id=None):
    from .recovery import _package_hash
    task_id=task_id or str(uuid4());now=datetime.now(timezone.utc)
    lock=Path(__file__).parents[2]/'uv.lock'
    if not lock.is_file(): lock=Path(sysconfig.get_path('data'))/'share/compertum/uv.lock'
    if not lock.is_file(): raise RuntimeRefused('LOCK_IDENTITY_UNAVAILABLE')
    digest=hashlib.sha256(CANONICAL).hexdigest()
    value={'schema_version':'1','record_type':'TaskSpec','task_id':task_id,'parent_task_id':None,'campaign_id':None,
        'role':'experiment_runner','kind':'OFFLINE_FIXTURE','created_at':now.isoformat(),'deadline_at':(now+timedelta(seconds=30)).isoformat(),
        'input_hashes':[digest],'code_sha256':_package_hash(),'lock_sha256':hashlib.sha256(lock.read_bytes()).hexdigest(),
        'output_schema_sha256':digest,'model_identity':None,'acceptance_checks':['canonical fixture bytes agree'],
        'permissions':{'tools':['trusted_fixture'],'filesystem_bundle':[],
            'output_directory':f'artifacts/runs/{task_id}/output','network_destinations':[],'protected_data':False,'broker':False,'shell':False},
        'budget':{'cpu_threads':1,'ram_bytes':128*1024**2,'output_bytes':4096,'wall_seconds':30,'max_attempts':2,'ai_requests':0,
            'gpu_training':False,'input_tokens':0,'output_tokens':0,'request_deadline_seconds':0},
        'clock':{'state':'REGISTERED','active_elapsed_seconds':0,'active_started_at':None,'manual_wait_started_at':None,
            'manual_deadline_at':None,'process_lease_id':None,'cpu_reserved':False}}
    return TaskSpec(value,project_root=root)


class FixtureController:
    def __init__(self,coordinator,storage):
        self.coordinator=coordinator;self.store=coordinator.store;self.storage=storage;self.active=None
        with self.store._live(),self.store.conn:
            self.store.conn.execute('''CREATE TABLE IF NOT EXISTS fixture_tasks(
                task_id TEXT PRIMARY KEY,run_id TEXT NOT NULL,spec TEXT NOT NULL,status TEXT NOT NULL,
                attempt INTEGER NOT NULL,checkpoint TEXT,artifact TEXT,lease_deadline REAL)''')
            self.store.conn.execute("UPDATE fixture_tasks SET status='INTERRUPTED',lease_deadline=NULL WHERE status='RUNNING'")

    def records(self):
        with self.store._live():
            rows=self.store.conn.execute('SELECT task_id,run_id,status,attempt,checkpoint,artifact FROM fixture_tasks ORDER BY task_id LIMIT 129').fetchall()
            if len(rows)>128: raise RuntimeRefused('FIXTURE_LEDGER_FULL')
            return [dict(task_id=r[0],run_id=r[1],status=r[2],attempt=r[3],checkpoint=json.loads(r[4]) if r[4] else None,
                artifact=json.loads(r[5]) if r[5] else None) for r in rows]

    def submit(self,spec):
        if not isinstance(spec,TaskSpec) or spec.to_payload()['kind']!='OFFLINE_FIXTURE': raise RuntimeRefused('FIXTURE_DENIED')
        p=spec.to_payload();task_id=p['task_id']
        if self.coordinator.status()['research_state']!='RUNNING': raise RuntimeRefused('RESEARCH_PAUSED')
        self.coordinator.require_health()
        with self.store._live():
            old=self.store.conn.execute('SELECT spec FROM fixture_tasks WHERE task_id=?',(task_id,)).fetchone()
            if old:
                if old[0]!=canonical(p).decode(): raise RuntimeRefused('TASK_CONFLICT')
                return next(r for r in self.records() if r['task_id']==task_id)
            if len(self.records())>=128 or self.active is not None: raise RuntimeRefused('JOB_SLOT_BUSY')
            run_id=str(uuid4())
            with self.store.conn: self.store.conn.execute("INSERT INTO fixture_tasks VALUES(?,?,?,'REGISTERED',0,NULL,NULL,NULL)",(task_id,run_id,canonical(p).decode()))
            return self._launch(task_id)

    def _launch(self,task_id):
        from .recovery import _package_hash
        self.coordinator.require_health()
        if self.active is not None: raise RuntimeRefused('JOB_SLOT_BUSY')
        row=self.store.conn.execute('SELECT run_id,spec,attempt,checkpoint,status FROM fixture_tasks WHERE task_id=?',(task_id,)).fetchone()
        if not row or row[4] not in {'REGISTERED','PAUSED','INTERRUPTED'}: raise RuntimeRefused('RESUME_DENIED')
        run_id,raw,previous,checkpoint,_=row;p=json.loads(raw);attempt=previous+1
        if attempt>p['budget']['max_attempts']: raise RuntimeRefused('ATTEMPT_BUDGET_EXHAUSTED')
        if p['code_sha256']!=_package_hash() or p['input_hashes']!=[hashlib.sha256(CANONICAL).hexdigest()]:
            raise RuntimeRefused('CHECKPOINT_IDENTITY_MISMATCH')
        prefix=b''
        if checkpoint:
            cp=json.loads(checkpoint);path=checked_path(self.store.root,self.store.root/cp['path'])
            with path.open('rb') as stream: prefix=stream.read(4097)
            if (len(prefix)!=cp['size_bytes'] or hashlib.sha256(prefix).hexdigest()!=cp['sha256'] or not CANONICAL.startswith(prefix)
                    or cp['code_sha256']!=p['code_sha256'] or cp['input_hashes']!=p['input_hashes']):
                raise RuntimeRefused('CHECKPOINT_IDENTITY_MISMATCH')
        grant=self.storage.reserve_bytes(task_id,'records',p['budget']['output_bytes'])
        writer=self.storage.open_artifact(grant,f'artifacts/runs/{task_id}/output/attempt-{attempt:03d}/fixture.bin')
        if prefix: writer.write(prefix)
        lineage={'code_sha256':p['code_sha256'],'input_hashes':p['input_hashes'],'checkpoint':json.loads(checkpoint) if checkpoint else None}
        self.store.record_attempt(run_id,task_id,attempt,'RUNNING',lineage)
        with self.store.conn: self.store.conn.execute("UPDATE fixture_tasks SET status='RUNNING',attempt=?,lease_deadline=? WHERE task_id=?",(attempt,time.time()+30,task_id))
        try: job=launch_bounded(self.store.lease,TaskSpec(p,project_root=self.store.root),['fixture','canonical',str(writer.destination)],writer=writer,offset=len(prefix))
        except BaseException:
            writer.close();self.store.record_attempt(run_id,task_id,attempt,'FAILED',lineage)
            with self.store.conn: self.store.conn.execute("UPDATE fixture_tasks SET status='FAILED' WHERE task_id=?",(task_id,))
            raise
        self.active=(task_id,run_id,attempt,lineage,writer,job)
        return next(r for r in self.records() if r['task_id']==task_id)

    def resume(self,task_id):
        uuid(task_id)
        if self.coordinator.status()['research_state']!='RUNNING': raise RuntimeRefused('RESEARCH_PAUSED')
        return self._launch(task_id)

    def tick(self):
        if self.active is None: return
        task_id,run_id,attempt,lineage,writer,job=self.active
        self.coordinator.require_health()
        if time.monotonic()>=job.deadline:
            self.pause('timeout');return
        if job.api.active(job.job):
            with self.store.conn: self.store.conn.execute('UPDATE fixture_tasks SET lease_deadline=? WHERE task_id=?',(time.time()+30,task_id))
            return
        receipt=job.wait();adopt_fixture_bytes(writer,job)
        with writer.path.open('rb') as stream: result=stream.read(4097)
        if receipt['exit_code']!=0 or result!=CANONICAL:
            self.pause('failure');raise RuntimeRefused('FIXTURE_FAILED')
        artifact=writer.publish();job.close();self.active=None
        self.store.record_attempt(run_id,task_id,attempt,'COMPLETED',lineage)
        with self.store.conn: self.store.conn.execute("UPDATE fixture_tasks SET status='COMPLETED',artifact=?,lease_deadline=NULL WHERE task_id=?",(canonical(artifact).decode(),task_id))

    def pause(self,reason):
        if self.active is None: return
        task_id,run_id,attempt,lineage,writer,job=self.active
        job.api.checked(job.api.TerminateJobObject(job.job.get(),125),'PauseFixtureJob')
        job.wait();adopt_fixture_bytes(writer,job)
        with writer.path.open('rb') as stream: prefix=stream.read(4097)
        if not CANONICAL.startswith(prefix):
            writer.close();job.close();self.active=None;raise RuntimeRefused('CHECKPOINT_IDENTITY_MISMATCH')
        artifact=writer.publish();job.close();self.active=None
        checkpoint={**artifact,'checkpoint_id':str(uuid4()),'code_sha256':lineage['code_sha256'],'input_hashes':lineage['input_hashes']}
        status='TIMED_OUT' if reason=='timeout' else 'FAILED' if reason in {'failure','stop_research'} else 'PAUSED'
        self.store.record_attempt(run_id,task_id,attempt,status,lineage)
        with self.store.conn:
            self.store.conn.execute('UPDATE fixture_tasks SET status=?,checkpoint=?,lease_deadline=NULL WHERE task_id=?',(status,canonical(checkpoint).decode(),task_id))




def run_foundation_suite(config,offline=True):
    """Bounded foreground offline run with a complete recovery checkpoint."""
    if offline is not True: raise RuntimeRefused('CAPABILITY_UNAVAILABLE')
    from .runtime.supervisor import Supervisor
    from .runtime.ipc import ProtocolDecision
    from .runtime.control import serve_control_once
    supervisor=Supervisor(config)
    try:
        decision=ProtocolDecision(str(uuid4()),hashlib.sha256(b'local operator control').hexdigest(),hashlib.sha256(b'offline foundation').hexdigest(),supervisor.supervisor.generation)
        supervisor.coordinator.control(decision,'resume_research',{})
        task=supervisor.fixtures.submit(fixture_spec(supervisor.project.root_path))
        deadline=time.monotonic()+30
        while supervisor.fixtures.active and time.monotonic()<deadline:
            if time.monotonic()-supervisor.last_poll>=.8: supervisor.poll_health()
            supervisor.fixtures.tick()
            try: serve_control_once(supervisor.endpoint,supervisor.handle,timeout=.05)
            except RuntimeRefused as error:
                if error.code!='PIPE_DEADLINE_EXCEEDED': raise
        result=next(r for r in supervisor.fixtures.records() if r['task_id']==task['task_id'])
        if result['status']!='COMPLETED': raise RuntimeRefused('FOUNDATION_UNVERIFIED')
        snapshots=supervisor.checkpoint()
        receipt={'status':'FOUNDATION_VERIFIED','strategy_state':'NOT_EVALUATED','paper':'DISABLED',
                 'task_id':task['task_id'],'artifact':result['artifact'],'recovery_manifests':snapshots,
                 'watchdog':supervisor.get_health(),'ai_requests':0}
        from .recovery import _write
        grant=supervisor.storage.reserve_bytes(task['task_id'],'records',8192)
        writer=supervisor.storage.open_artifact(grant,f"artifacts/runs/{task['task_id']}/foundation.json")
        try: writer.write(canonical(receipt));receipt['receipt_artifact']=writer.publish()
        finally: writer.close()
        return receipt
    finally: supervisor.close()
