"""Independent role entry point; only an inherited supervisor channel admits it."""
from .startup import require_entrypoint_startup
_STARTUP_PROOF=require_entrypoint_startup() if __name__=='__main__' else None

import json
from pathlib import Path
import shutil
import sqlite3
import sys
import time
from .bootstrap import _registration
from .identity import resolve_project
from .owners import acquire_owner,release_owner,_owner_scope
from .ipc import start_role_pipe
from .owner_channel import receive_owner_channel
from .owner_rpc import serve_owner_once
from .errors import RuntimeRefused
from .execution_health import MutualHealth,disarm_execution,execution_durable
from compertum.events import canonical
from compertum.persistence import open_store,checked_path,_active_store_path
from compertum.storage import iter_storage,GIB,INVENTORY_MAX_AGE,open_journal_reserve,create_journal_reserve
from compertum.watchdog import check_storage


class StorageMonitor:
    def __init__(self,lease,project,*,expect_execution=True):
        self.lease=lease;self.project=project;self.previous=None;self.observation=None
        self.last_volume=0;self.last_scan=0;self.parent_heartbeat=time.monotonic();self.reason=None
        self.last_scan_started=0;self.last_volume_measured=0
        self.scan=None
        halt=checked_path(project.root_path,project.root_path/'state/watchdog/halt.json')
        if halt.exists(): self.reason='RETAINED_WATCHDOG_HALT'
        self.mutual=MutualHealth(lease,self.trip,required=expect_execution)

    def trip(self,reason):
        if self.reason is not None: return
        self.reason=reason
        with _owner_scope(self.lease) as guard:
            path=checked_path(self.project.root_path,self.project.root_path/'state/watchdog/halt.json')
            path.parent.mkdir(exist_ok=True)
            guard.api.publish_metadata(path,canonical({'reason':reason,'generation':self.lease.generation,'observed_monotonic':time.monotonic(),'order_admission':'DISARMED'}))

    def volume(self):
        now=time.monotonic()
        if now-self.last_volume>=.9:
            self.last_volume=now
            if shutil.disk_usage(self.project.root_path).free<50*GIB: self.trip('FREE_SPACE_FLOOR')
            self.last_volume_measured=time.monotonic()

    def tick(self):
        self.mutual.tick()
        now=time.monotonic()
        if now-self.parent_heartbeat>15: self.trip('SUPERVISOR_HEARTBEAT_STALE')
        self.volume()
        # Yield between batches so pipe replies, volume checks and peer health
        # keep their own deadlines even when a complete inventory takes longer.
        if self.scan is None and now-self.last_scan>=2.5:
            self.last_scan=now;self.last_scan_started=now
            self.scan=iter_storage(self.project,volume_probe=self.volume)
        if self.scan is not None:
            until=time.monotonic()+.05
            try:
                while True:
                    next(self.scan)
                    if time.monotonic()>=until:return
            except StopIteration as completed:
                observed=completed.value;self.scan=None
            except BaseException:
                self.close();raise
            path=_active_store_path(self.project.root_path,self.project.project_id,'coordinator')
            # Admission commits the grant before any bytes are created. Read the
            # ledger after the scan so a concurrent admitted publication cannot
            # appear to be unreserved merely because the old ledger was sampled.
            db=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=.2)
            try:
                rows=db.execute('SELECT path,maximum FROM reservations WHERE path IS NOT NULL LIMIT 1025').fetchall()
                if len(rows)>1024: raise RuntimeRefused('RESERVATION_BOUND_EXCEEDED')
            finally: db.close()
            reservations=[{'path':p,'maximum':n} for p,n in rows]
            result=check_storage(observed,reservations,previous=self.previous)
            if result['status']=='RESEARCH_BLOCKED': self.trip(result['reason'])
            self.previous=observed;self.observation=observed

    def close(self):
        scan,self.scan=self.scan,None
        if scan is not None:scan.close()

    def storage_reason(self):
        if self.reason:return self.reason
        if self.observation is None:return 'STORAGE_SCAN_PENDING'
        if not 0<=time.monotonic()-self.observation['completed_monotonic']<=INVENTORY_MAX_AGE:
            return 'STORAGE_STALE'
        return None

    def handle(self,action,payload):
        if action=='owner_heartbeat':return self.mutual.receive(payload)
        if action=='checkpoint' and set(payload)=={'barrier_id'}:
            from compertum.events import uuid
            uuid(payload['barrier_id']);self.tick()
            if self.storage_reason(): raise RuntimeRefused('WATCHDOG_BLOCKED')
            return {'barrier_id':payload['barrier_id'],'generation':self.lease.generation,'process_instance_id':self.lease.identity.process_instance_id}
        if action!='status' or payload!={}: raise RuntimeRefused('COMMAND_DENIED')
        self.parent_heartbeat=time.monotonic()
        self.tick()
        reason=self.storage_reason()
        return {'status':'RESEARCH_BLOCKED' if reason else 'HEALTHY','reason':reason,
                'observed_monotonic':time.monotonic(),
                'storage_observed_monotonic':self.observation['completed_monotonic'] if self.observation else None,
                'volume_observed_monotonic':self.last_volume_measured,'scan_seconds':self.observation['scan_seconds'] if self.observation else None,
                'generation':self.lease.generation,'order_admission':'DISARMED','startup':_STARTUP_PROOF,
                'mutual':self.mutual.status(),'heartbeat':self.mutual.receipt(healthy=self.reason is None)}


def main():
    if len(sys.argv)!=3 or len(sys.argv[2])>8192: raise RuntimeRefused('OWNER_LAUNCH_DENIED')
    public=json.loads(sys.argv[2]);project=resolve_project(Path(public['root']));role=public['role']
    if role not in {'watchdog','evaluation','execution'}: raise RuntimeRefused('OWNER_LAUNCH_DENIED')
    lease=acquire_owner(project,role);monitor=None;mutual=None;authority=None;paper_reads=None
    try:
        endpoint=start_role_pipe(lease,frozenset({'status','checkpoint','synthetic_protocol'} if role=='evaluation' else {'status','checkpoint','owner_heartbeat','fake_operator','paper_read','paper_read_transfer','paper_market_read','paper_market_transfer','paper_presence','paper_intent','paper_activity','paper_activity_transfer'} if role=='execution' else {'status','checkpoint','owner_heartbeat'}))
        channel=receive_owner_channel(int(sys.argv[1]),expected_supervisor=_registration(public['supervisor']),endpoint=endpoint)
        if role=='watchdog':
            expected=public.get('expect_execution',True)
            if type(expected) is not bool:raise RuntimeRefused('OWNER_LAUNCH_DENIED')
            monitor=StorageMonitor(lease,project,expect_execution=expected);handler=monitor.handle
        else:
            store=open_store(lease,role)
            reserve=None
            if role=='execution':
                reserve=open_journal_reserve(lease) if (project.root_path/'state/execution-reserve.bin').exists() else create_journal_reserve(lease)
                disarm_execution(store,'PROCESS_START')
                mutual=MutualHealth(lease,lambda reason:disarm_execution(store,reason),required=True)
            barrier=None
            seals=None
            def handler(action,payload):
                nonlocal barrier,seals,authority,paper_reads
                if action=='owner_heartbeat' and role=='execution':return mutual.receive(payload)
                if action=='status' and payload=={}:
                    if mutual is not None:
                        try:capacity=execution_durable(store,reserve)
                        except RuntimeRefused as error:mutual.halt(error.code);capacity=None
                        state=mutual.status()
                        return {'status':'HEALTHY' if mutual.reason is None else 'RESEARCH_BLOCKED','reason':mutual.reason,'generation':lease.generation,'role':role,'reserve':capacity,'startup':_STARTUP_PROOF,'mutual':state,'heartbeat':mutual.receipt(healthy=capacity is not None)}
                    return {'status':'HEALTHY','generation':lease.generation,'role':role,'reserve':None,'startup':_STARTUP_PROOF}
                if action in {'paper_read','paper_read_transfer','paper_market_read','paper_market_transfer','paper_presence','paper_intent','paper_activity','paper_activity_transfer'} and role=='execution':
                    if barrier is not None:raise RuntimeRefused('BARRIER_HELD')
                    if paper_reads is None:
                        from .paper_read_owner import PaperReadOwner
                        paper_reads=PaperReadOwner(store,reserve,mutual)
                    handlers={'paper_read':paper_reads.handle,'paper_read_transfer':paper_reads.transfer,
                              'paper_market_read':paper_reads.market_handle,'paper_market_transfer':paper_reads.market_transfer,
                              'paper_presence':paper_reads.presence_handle,'paper_intent':paper_reads.intent_handle,
                              'paper_activity':paper_reads.activity_handle,'paper_activity_transfer':paper_reads.activity_transfer}
                    return handlers[action](payload)
                if action=='fake_operator' and role=='execution':
                    if barrier is not None:raise RuntimeRefused('BARRIER_HELD')
                    if authority is None:
                        from compertum.execution_authority import ExecutionAuthority
                        authority=ExecutionAuthority(store,reserve,mutual)
                    return authority.handle(payload)
                if action=='synthetic_protocol' and role=='evaluation':
                    if barrier is not None:raise RuntimeRefused('BARRIER_HELD')
                    if seals is None:
                        from compertum.evaluation_seals import EvaluationSeals
                        seals=EvaluationSeals(store)
                    return seals.handle(payload)
                if action=='checkpoint':
                    from compertum.events import uuid
                    from compertum.domain import resolve_project_path
                    uuid(payload.get('barrier_id'))
                    if payload.get('operation')=='end' and set(payload)=={'operation','barrier_id'}:
                        if barrier!=payload['barrier_id']: raise RuntimeRefused('BARRIER_MISMATCH')
                        barrier=None;return {'status':'BARRIER_RELEASED'}
                    if (payload.get('operation')!='snapshot' or set(payload)!={'operation','barrier_id','destination','maximum_bytes'}
                            or barrier is not None or not payload['destination'].startswith('backups/')):
                        raise RuntimeRefused('BARRIER_DENIED')
                    if paper_reads is not None:paper_reads.require_checkpoint()
                    destination=resolve_project_path(payload['destination'],project.root_path)
                    barrier=payload['barrier_id']
                    return store.checkpoint(barrier,destination,maximum_bytes=payload['maximum_bytes'])
                raise RuntimeRefused('COMMAND_DENIED')
        while True:
            if monitor is not None: monitor.tick()
            if mutual is not None:mutual.tick()
            if authority is not None and barrier is None:authority.tick()
            if paper_reads is not None and barrier is None:paper_reads.tick()
            try: serve_owner_once(channel,handler,timeout=.01 if monitor is not None and monitor.scan is not None else .1)
            except RuntimeRefused as error:
                if error.code=='PIPE_DEADLINE_EXCEEDED': continue
                raise
    except (RuntimeRefused,OSError,sqlite3.Error) as error:
        if monitor is not None: monitor.trip(error.code if isinstance(error,RuntimeRefused) else 'OWNER_CHANNEL_LOST')
        if mutual is not None:mutual.halt(error.code if isinstance(error,RuntimeRefused) else 'OWNER_CHANNEL_LOST')
        return 3
    finally:
        try:
            if monitor is not None:monitor.close()
        finally:release_owner(lease)

if __name__=='__main__': raise SystemExit(main())




