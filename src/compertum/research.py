"""Foreground, nonblocking controller for one saved synthetic replay at a time."""
from datetime import datetime,timedelta,timezone
import json,time
from uuid import uuid4
from .domain import TaskSpec
from .foundation import fixture_spec
from .simulation.runs import SavedRuns,MIB,unit_schedule,attempt_seconds
from .data.errors import DataError
from .runtime.errors import RuntimeRefused
from .runtime.jobs import launch_bounded,job_slot_busy,preflight_campaign
from .storage import adopt_fixture_bytes


class ResearchController:
    def __init__(self,coordinator,storage,*,cooperative=False):
        self.coordinator=coordinator;self.storage=storage;self.runs=SavedRuns(storage);self.store=storage.store;self.active=None
        self.cooperative=cooperative;self.pending=None;self.last_operation_error=None
        with self.store._live(),self.store.conn:
            for (run_id,) in self.store.conn.execute('SELECT run_id FROM baseline_runs').fetchall():
                state=self.runs._load(run_id)
                if state['state']=='READY':
                    state['state']='PAUSED';self.runs._save(state,'SUPERVISOR_START_PAUSED')

    def records(self):
        with self.store._live():
            return [{k:v for k,v in self.runs.summary(row[0]).items() if k in ('run_id','state','completed_units','total_units')}
                for row in self.store.conn.execute('SELECT run_id FROM baseline_runs ORDER BY run_id LIMIT 128').fetchall()]

    def _receipt(self,run_id,receipt):
        with self.store._live(),self.store.conn:
            state=self.runs._load(run_id)
            if state.get('input_kind')=='synthetic-campaign':
                from .simulation.campaign_runs import validate_receipt
                validate_receipt(receipt)
                if state['state']!='RUNNING' or state['active_owner']!=self.runs.owner or state['attempts'][-1].get('native_execution')!=receipt.get('execution_identity') or 'execution_identity' not in receipt:raise DataError('CAMPAIGN_EXECUTION_UNVERIFIED')
            state['attempts'][-1]['job_receipt']=receipt
            self.runs._save(state,'JOB_EXIT_VERIFIED')

    def step(self,run_id):
        from .ai.cycle_ownership import require_dispatch_owner
        require_dispatch_owner(self)
        self._require_recovery_clear()
        if self.coordinator.status()['research_state']!='RUNNING':raise RuntimeRefused('RESEARCH_PAUSED')
        self.coordinator.require_health()
        if self.busy or job_slot_busy(self.storage.lease):raise RuntimeRefused('JOB_SLOT_BUSY')
        if self.runs._load(run_id).get('input_kind')=='synthetic-campaign':return self._campaign_step(run_id)
        admission=self.runs.begin(run_id);writer=None;job=None
        try:
            state=self.runs._load(run_id)
            used=self.store.conn.execute("SELECT COALESCE(sum(CASE WHEN status='PUBLISHED' THEN written ELSE maximum END),0) FROM reservations WHERE task=? AND category='records' AND status!='SPLIT'",(run_id,)).fetchone()[0]
            maximum=16*MIB
            if used+maximum>state['maximum_bytes']:raise DataError('RUN_BUDGET')
            artifact=admission['input_artifact'];payload=fixture_spec(self.storage.root,run_id).to_payload()
            seconds=attempt_seconds(state)
            now=datetime.now(timezone.utc);payload.update(created_at=now.isoformat(),deadline_at=(now+timedelta(seconds=seconds)).isoformat())
            payload['input_hashes']=[artifact['sha256']]
            payload['permissions']['filesystem_bundle']=[artifact['path']]
            payload['permissions']['output_directory']=f'artifacts/runs/{run_id}/baseline'
            payload['budget'].update(cpu_threads=4,ram_bytes=4*1024**3,output_bytes=maximum,wall_seconds=seconds)
            task=TaskSpec(payload,project_root=self.storage.root)
            grant=self.storage.reserve_bytes(run_id,'records',maximum)
            suffix='prediction' if unit_schedule(state)[admission['unit']][1] is None else 'replay'
            name=f"unit-{admission['unit']:02}-attempt-{admission['attempt']}.{suffix}"
            writer=self.storage.open_artifact(grant,f'artifacts/runs/{run_id}/baseline/{name}')
            job=launch_bounded(self.storage.lease,task,['fixture','replay',str(writer.destination)],writer=writer,
                input_artifact=artifact,unit=admission['unit'])
            self.active=(run_id,writer,job)
            return self.runs.summary(run_id)
        except Exception:
            if job is not None:job.close()
            if writer is not None:writer.close()
            self.runs.interrupt(run_id,'LAUNCH_FAILED',terminal=True)
            raise

    @property
    def busy(self):return self.active is not None or self.pending is not None or bool(self.last_operation_error and self.last_operation_error.get('recovery_required'))

    def _require_recovery_clear(self):
        if self.last_operation_error and self.last_operation_error.get('recovery_required'):
            raise RuntimeRefused('CAMPAIGN_RECOVERY_REQUIRED')

    def pending_status(self):return self.pending.view() if self.pending is not None else None

    def _operation_error(self,operation,error,cleanup=None):
        if self.last_operation_error and self.last_operation_error.get('recovery_required'):return
        self.last_operation_error={'run_id':operation.run_id,'operation':operation.action,'phase':operation.phase,
            'reason':getattr(error,'code','CAMPAIGN_PREPARATION_FAILED')}
        if cleanup is not None:
            self.last_operation_error.update(recovery_required=True,cleanup_reason=getattr(cleanup,'code','CAMPAIGN_CLEANUP_FAILED'))

    def _advance_pending(self,*,propagate=False):
        operation=self.pending
        if operation is None:return
        error=None;cleanup=None
        try:
            if not operation.advance():return
        except Exception as failure:
            error=failure
            try:operation.fail(error)
            except Exception as failure:cleanup=failure
        # Never retain a finished operation even when resource closure fails.
        self.pending=None
        try:operation.close()
        except Exception as failure:cleanup=failure
        if error is not None or cleanup is not None:
            self._operation_error(operation,error or cleanup,cleanup)
            if propagate:
                if error is not None:raise error
                raise RuntimeRefused('CAMPAIGN_RECOVERY_REQUIRED') from cleanup
        elif not (self.last_operation_error and self.last_operation_error.get('recovery_required')):self.last_operation_error=None

    def _campaign_step(self,run_id):
        from .campaign_operation import _CampaignOperation
        now=datetime.now(timezone.utc);preflight_campaign(self.storage.lease)
        if self.runs._load(run_id)['state']!='READY':raise DataError('RUN_NOT_READY')
        self.pending=_CampaignOperation(self,run_id,'step',created_at=now)
        if not self.cooperative:
            while self.pending is not None:self._advance_pending(propagate=True)
        result=self.runs.summary(run_id)
        if self.pending is not None:result['pending_operation']=self.pending_status()
        return result

    def _campaign_interrupt(self,run_id,reason,*,terminal=False):
        from .simulation.campaign_runs import interrupt
        return interrupt(self.runs,run_id,reason,terminal=terminal)

    def tick(self):
        if self.pending is not None or self.active is not None:
            from .ai.cycle_ownership import require_dispatch_owner
            require_dispatch_owner(self)
        if self.pending is not None:
            self._advance_pending();return
        if self.active is None:return
        run_id,writer,job=self.active
        campaign=self.runs._load(run_id).get('input_kind')=='synthetic-campaign'
        if job.api.active(job.job):return
        if campaign:
            from .campaign_operation import _CampaignOperation
            self.pending=_CampaignOperation(self,run_id,'complete')
            self._advance_pending()
            if not self.cooperative:
                while self.pending is not None:self._advance_pending()
            return
        try:
            receipt=job.wait();self._receipt(run_id,receipt);adopt_fixture_bytes(writer,job)
            if receipt['timed_out']:
                self.runs.interrupt(run_id,'JOB_TIMEOUT',terminal=True);return
            if campaign and receipt['exit_code'] not in (0,4,5):
                self._campaign_interrupt(run_id,'UNIT_INTEGRITY_FAILURE');return
            if receipt['exit_code']!=0:
                self.runs.interrupt(run_id,'WORKER_FAILED',terminal=receipt['exit_code']!=5);return
            artifact=writer.publish();self.runs.accept(run_id,artifact)
        except (DataError,RuntimeRefused,OSError) as error:
            if self.runs.summary(run_id)['state']=='RUNNING':
                if campaign:self._campaign_interrupt(run_id,'WORKER_FAILED' if isinstance(error,OSError) else 'UNIT_INTEGRITY_FAILURE')
                else:self.runs.interrupt(run_id,'WORKER_FAILED',terminal=True)
        except Exception:
            if not campaign:raise
            if self.runs.summary(run_id)['state']=='RUNNING':self._campaign_interrupt(run_id,'UNIT_INTEGRITY_FAILURE')
        finally:
            job.close();writer.close();self.active=None

    def pause(self,reason='OPERATOR_PAUSE',*,terminal=False):
        if self.pending is not None:
            operation=self.pending;self.pending=None
            try:operation.cancel(reason,terminal)
            except Exception as error:
                self._operation_error(operation,error,error)
                raise RuntimeRefused('CAMPAIGN_RECOVERY_REQUIRED') from error
        if self.active is None:return
        run_id,writer,job=self.active
        try:
            job.api.checked(job.api.TerminateJobObject(job.job.get(),125),'PauseReplayJob')
            receipt=job.wait();self._receipt(run_id,receipt);adopt_fixture_bytes(writer,job)
            self.runs.interrupt(run_id,reason,terminal=terminal)
        finally:
            job.close();writer.close();self.active=None

    def control(self,run_id,request_id,operation):
        if operation=='status':
            result=self.runs.summary(run_id)
            if self.pending is not None and self.pending.run_id==run_id:result['pending_operation']=self.pending_status()
            if self.last_operation_error is not None and self.last_operation_error['run_id']==run_id:result['last_operation_error']=self.last_operation_error
            return result
        if operation in {'step','resume'}:
            from .ai.cycle_ownership import require_dispatch_owner
            require_dispatch_owner(self)
            self._require_recovery_clear()
            from .ai.registration import require_complete
            require_complete(self.runs,run_id)
        if operation=='step':return self.step(run_id)
        if operation not in {'resume','pause','stop'}:raise RuntimeRefused('CONTROL_PAYLOAD_DENIED')
        if self.pending is not None and self.pending.run_id==run_id and operation in {'pause','stop'}:self.pause()
        if self.active and self.active[0]==run_id and operation in {'pause','stop'}:self.pause()
        if operation=='resume' and self.cooperative and self.runs._load(run_id).get('input_kind')=='synthetic-campaign':
            from .campaign_operation import queue_resume
            return queue_resume(self,run_id,request_id)
        return self.runs.control(run_id,request_id,operation)
