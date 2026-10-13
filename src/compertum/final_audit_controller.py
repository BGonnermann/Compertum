"""Foreground independent Final audit controls; uncertainty retains owned resources."""
from datetime import datetime,timezone
import json
from .data.errors import DataError
from .evaluation_protocol import identifier
from .final_audit_runs import FinalAuditRuns,summary
from .runtime.errors import RuntimeRefused
from .runtime.jobs import launch_bounded,preflight_campaign,job_slot_busy
from .runtime.audit_job_lifetime import AuditLaunchFailed,prove_exit,closed_unbound,no_child_disposition
from .storage import adopt_fixture_bytes


class FinalAuditController:
    def __init__(self,coordinator,storage):
        self.coordinator=coordinator;self.storage=storage;self.runs=FinalAuditRuns(storage);self.active=None;self.error=None

    def records(self):return self.runs.records()

    def _uncertain(self,task):
        s=self.runs.status(task)
        if s['state'] in ('PREPARED','RUNNING') and s['attempts'][-1]['job_receipt'] is None:self.runs.uncertain(task,'LAUNCH_FAILED')

    def _dispose(self):
        prepared,writer,job=self.active
        # close must prove process exit and finish all handle/budget cleanup first.
        job.close();writer.close();self.active=None

    def _failed_launch(self,launch):
        prepared=launch.prepared;writer=launch.writer;job=launch.job;task=prepared['task_id']
        if job is None:
            self.runs.record_unbound(prepared,no_child_disposition(launch));writer.close();return
        self.active=(prepared,writer,job)
        try:
            s=self.runs.status(task)
            if s['attempts'][-1]['native_execution'] is None:
                job.close();self.runs.record_unbound(prepared,closed_unbound(job));writer.close();self.active=None
            else:
                prove_exit(job);self.runs.record_exit(task,job.wait())
                self.runs.interrupt(task,'LAUNCH_FAILED');self._dispose()
        except Exception:
            self._uncertain(task);raise

    def _admit(self):
        if self.coordinator.status()['research_state']!='RUNNING':raise RuntimeRefused('RESEARCH_PAUSED')
        self.coordinator.require_health()
        if self.active is not None or job_slot_busy(self.storage.lease):raise RuntimeRefused('JOB_SLOT_BUSY')
        preflight_campaign(self.storage.lease)

    def step(self,task):
        identifier(task);self._admit();return self._step(task)

    def _step(self,task):
        s=self.runs.status(task)
        if s['state']=='COMPLETED':return summary(self.runs.completed(task))
        prepared,spec,writer=self.runs.prepare(task,now=datetime.now(timezone.utc))
        try:
            job=launch_bounded(self.storage.lease,spec,['fixture','final_audit',str(writer.destination)],writer=writer,final_audit_request=prepared,before_resume=lambda identity:self.coordinator.require_health())
        except AuditLaunchFailed as error:
            self._failed_launch(error.launch);raise
        self.active=(prepared,writer,job);self.error=None
        return summary(self.runs.status(task))

    def _finish(self,*,cause=None,terminal=False):
        prepared,writer,job=self.active;task=prepared['task_id']
        try:
            receipt=job.wait();self.runs.record_exit(task,receipt);prove_exit(job)
            adopt_fixture_bytes(writer,job)
            if terminal:self.runs.interrupt(task,'OPERATOR_STOP',stop=True)
            elif receipt['timed_out']:self.runs.interrupt(task,'JOB_TIMEOUT')
            elif receipt['exit_code']==5:self.runs.interrupt(task,'WORKER_IO_FAILURE')
            elif receipt['exit_code'] not in (0,125):self.runs.interrupt(task,'AUDIT_INTEGRITY_FAILURE')
            elif cause is not None:self.runs.interrupt(task,'OPERATOR_STOP' if terminal else cause,stop=terminal)
            elif receipt['exit_code']!=0:self.runs.interrupt(task,'AUDIT_INTEGRITY_FAILURE')
            else:
                self.coordinator.require_health();s=self.runs.status(task);self.runs.current(s)
                with writer.path.open('rb') as stream:raw=stream.read(2*1024**2+1)
                self.runs.inspect_output(s,raw)
                artifact=writer.publish();self.runs.accept(task,artifact)
        except Exception as error:
            self.error=getattr(error,'code','FINAL_AUDIT_BOOKKEEPING_FAILED')
            s=self.runs.status(task)
            if s['state'] in ('PREPARED','RUNNING','EXIT_UNVERIFIED'):
                if s['attempts'][-1]['job_receipt'] is None:
                    self._uncertain(task);raise
                # A fully indexed successful artifact can finish bookkeeping on recover.
                if writer.manifest is None:self.runs.interrupt(task,'BOOKKEEPING_FAILED')
            raise
        finally:
            # An observed receipt permits disposal; an uncertain exit never does.
            s=self.runs.status(task)
            if s['attempts'][-1]['job_receipt'] is not None:self._dispose()

    def tick(self):
        if self.active is None:return
        prepared,writer,job=self.active
        if job.audit_lifetime.cleanup_uncertain:return
        if job.api.active(job.job):return
        try:
            if self.runs.status(prepared['task_id'])['state']=='RUNNING':self._finish()
        except Exception as error:self.error=getattr(error,'code','FINAL_AUDIT_BOOKKEEPING_FAILED')

    def pause(self,reason='OPERATOR_PAUSE',*,terminal=False):
        if self.active is None:return
        prepared,writer,job=self.active;task=prepared['task_id']
        s=self.runs.status(task)
        if s['attempts'][-1]['job_receipt'] is not None and s['state'] not in ('RUNNING','EXIT_UNVERIFIED'):
            self._dispose();return
        if s['attempts'][-1]['native_execution'] is None:
            from .runtime.audit_job_lifetime import AuditLaunch
            self._failed_launch(AuditLaunch(prepared,writer,job));return
        try:prove_exit(job);self._finish(cause='OPERATOR_PAUSE',terminal=terminal)
        except Exception as error:
            self.error=getattr(error,'code','FINAL_AUDIT_CLEANUP_UNVERIFIED');self._uncertain(task);raise

    def recover(self,task):
        if self.active is not None:
            if self.active[0]['task_id']!=task:raise RuntimeRefused('JOB_SLOT_BUSY')
            self.pause();return summary(self.runs.status(task))
        s=self.runs.status(task)
        if s['state']=='EXIT_UNVERIFIED':return summary(self.runs.recover_exit(task))
        if s['state']=='COMPLETED':return summary(self.runs.completed(task))
        if s['state']=='RUNNING' and s['attempts'][-1]['job_receipt'] is not None:
            a=s['attempts'][-1]
            row=self.storage.store.conn.execute("SELECT manifest FROM reservations WHERE id=? AND status='PUBLISHED'",(a['reservation_id'],)).fetchone()
            if row is None:self.runs.interrupt(task,'PUBLICATION_FAILED')
            else:
                self.coordinator.require_health();self.runs.accept(task,json.loads(row[0]))
            return summary(self.runs.status(task))
        return summary(s)

    def control(self,payload):
        if type(payload) is not dict or type(payload.get('operation')) is not str:raise RuntimeRefused('CONTROL_PAYLOAD_DENIED')
        operation=payload['operation']
        fields={'operation','task_id','seal_id','manifest_reference'} if operation=='register' else {'operation','task_id'}
        if set(payload)!=fields or operation not in ('register','status','step','resume','pause','stop','recover'):raise RuntimeRefused('CONTROL_PAYLOAD_DENIED')
        task=payload['task_id'];identifier(task)
        if operation=='register':return summary(self.runs.register(task,payload['seal_id'],payload['manifest_reference']))
        if operation=='status':return summary(self.runs.status(task))
        if operation=='step':return self.step(task)
        if operation=='resume':
            self._admit();s=self.runs.status(task)
            if s['state']=='INTERRUPTED':self.runs.resume(task)
            elif not (s['state']=='READY' and len(s['attempts'])==1 and s['attempts'][0]['status']=='INTERRUPTED'):raise RuntimeRefused('FINAL_AUDIT_NOT_RESUMABLE')
            return self._step(task)
        if operation=='recover':return self.recover(task)
        if self.active is not None and self.active[0]['task_id']!=task:raise RuntimeRefused('RUN_NOT_ACTIVE')
        if self.active is not None:self.pause(terminal=operation=='stop')
        elif operation=='stop':return summary(self.runs.stop_idle(task))
        return summary(self.runs.status(task))
