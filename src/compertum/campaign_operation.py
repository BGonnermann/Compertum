"""One cooperative campaign operation; all effects stay with its coordinator."""
from datetime import datetime,timedelta,timezone
import time
from compertum.data.errors import DataError
from compertum.domain import TaskSpec
from compertum.events import uuid
from compertum.runtime.errors import RuntimeRefused
from compertum.simulation.campaign_verification import _Verification
from compertum.simulation import campaign_runs as campaign
from compertum.storage import adopt_fixture_bytes

MIB=1024**2


class _CampaignOperation:
    def __init__(self,controller,run_id,action,*,created_at=None,request_id=None):
        self.controller=controller;self.runs=controller.runs;self.run_id=run_id;self.action=action;self.request_id=request_id
        self.created_at=created_at or datetime.now(timezone.utc)
        self.deadline=time.monotonic()+120-(datetime.now(timezone.utc)-self.created_at).total_seconds()
        self.proof=None;self.grant=None;self.writer=None;self.job=None;self.prepared=None;self.artifact=None;self.receipt_recorded=False
        self.initial=self.runs._load(run_id)
        if action=='complete':
            self.phase='EXIT_RECEIPT';_,self.writer,self.job=controller.active
        else:
            self.phase='VERIFYING';self.proof=_Verification(self.runs,run_id)

    def view(self):
        return {'run_id':self.run_id,'operation':self.action,'phase':self.phase,
            'verified_artifacts':self.proof.position if self.proof is not None else 0,
            'total_artifacts':len(self.proof.records) if self.proof is not None else 0}

    def advance(self):
        from compertum import research as module
        c=self.controller
        with self.runs.store._live():
            c.coordinator.require_health()
            if time.monotonic()>=self.deadline:raise RuntimeRefused('TASK_DEADLINE_EXCEEDED')
            if self.action=='step' and c.coordinator.status()['research_state']!='RUNNING':raise RuntimeRefused('RESEARCH_PAUSED')
            if self.phase=='VERIFYING':
                if self.proof.advance():self.phase={'resume':'RESUME','step':'PREPARE','complete':'ACCEPT'}[self.action]
            elif self.phase=='RESUME':
                campaign.control(self.runs,self.run_id,self.request_id,'resume',self.runs._load(self.run_id),_verification=self.proof)
                return True
            elif self.phase=='PREPARE':
                self.prepared=self.runs.prepare_campaign(self.run_id,_verification=self.proof)
                payload=module.fixture_spec(c.storage.root,self.run_id).to_payload()
                payload.update(created_at=self.created_at.isoformat(),deadline_at=(self.created_at+timedelta(seconds=120)).isoformat())
                artifact=self.prepared['input_artifact'];dependency=self.prepared['dependency_artifact']
                artifacts=[artifact]+([dependency] if dependency else [])
                payload['input_hashes']=[a['sha256'] for a in artifacts]
                payload['permissions']['filesystem_bundle']=[a['path'] for a in artifacts]
                payload['permissions']['output_directory']=f'artifacts/runs/{self.run_id}/baseline'
                payload['budget'].update(cpu_threads=4,ram_bytes=4*1024**3,output_bytes=16*MIB,wall_seconds=120)
                self.task=TaskSpec(payload,project_root=c.storage.root);self.phase='RESERVE'
            elif self.phase=='RESERVE':
                self.proof.check(self.runs,self.runs._load(self.run_id))
                self.grant=c.storage.reserve_bytes(self.run_id,'records',16*MIB);self.phase='ALLOCATE'
            elif self.phase=='ALLOCATE':
                self.proof.check(self.runs,self.runs._load(self.run_id))
                self.writer=c.storage.open_artifact(self.grant,self.prepared['output_path']);self.phase='LAUNCH'
            elif self.phase=='LAUNCH':
                module.preflight_campaign(c.storage.lease)
                self.proof.check(self.runs,self.runs._load(self.run_id))
                prepared=self.prepared
                def commit(execution_identity):
                    c.coordinator.require_health()
                    self.runs.begin_campaign(self.run_id,prepared,reservation_id=self.grant.grant_id,_verification=self.proof)
                    campaign.bind_native_execution(self.runs,self.run_id,prepared['unit'],execution_identity)
                self.job=module.launch_bounded(c.storage.lease,self.task,['fixture','campaign',str(self.writer.destination)],writer=self.writer,
                    input_artifact=prepared['input_artifact'],unit=prepared['unit'],dependency_artifact=prepared['dependency_artifact'],
                    dependency_sha256=prepared['dependency_sha256'],before_resume=commit)
                c.active=(self.run_id,self.writer,self.job)
                return True
            elif self.phase=='EXIT_RECEIPT':
                receipt=self.job.wait();c._receipt(self.run_id,receipt);self.receipt_recorded=True
                adopt_fixture_bytes(self.writer,self.job)
                if receipt['timed_out']:
                    self.runs.interrupt(self.run_id,'JOB_TIMEOUT',terminal=True);return True
                if receipt['exit_code'] not in (0,4,5):
                    c._campaign_interrupt(self.run_id,'UNIT_INTEGRITY_FAILURE');return True
                if receipt['exit_code']!=0:
                    self.runs.interrupt(self.run_id,'WORKER_FAILED',terminal=receipt['exit_code']!=5);return True
                self.phase='PUBLISH'
            elif self.phase=='PUBLISH':
                self.artifact=self.writer.publish();self.proof=_Verification(self.runs,self.run_id);self.phase='VERIFYING'
            elif self.phase=='ACCEPT':
                self.runs.accept(self.run_id,self.artifact,_verification=self.proof)
                return True
            else:raise DataError('CAMPAIGN_OPERATION_INVALID')
            return False

    def fail(self,error):
        state=self.runs._load(self.run_id);c=self.controller
        if self.action=='complete' and state['state']=='RUNNING':
            c._campaign_interrupt(self.run_id,'WORKER_FAILED' if isinstance(error,OSError) else 'UNIT_INTEGRITY_FAILURE')
        elif (self.action=='step' and self.grant is not None and state['state']=='RUNNING' and state['attempts']
                and state['attempts'][-1].get('reservation_id')==self.grant.grant_id):
            self.runs.interrupt(self.run_id,'LAUNCH_FAILED',terminal=True)

    def cancel(self,reason,terminal=False):
        try:
            if self.action=='complete' and self.runs._load(self.run_id)['state']=='RUNNING':
                # The real exit receipt remains authoritative even if its acceptance is cancelled.
                receipt=self.job.wait()
                if not self.receipt_recorded:self.controller._receipt(self.run_id,receipt)
                if self.writer.manifest is None and not self.writer.closed:adopt_fixture_bytes(self.writer,self.job)
                self.runs.interrupt(self.run_id,reason,terminal=terminal)
        finally:self.close()

    def close(self):
        try:
            if self.proof is not None:self.proof.close()
        finally:
            if self.action=='complete':
                try:self.job.close()
                finally:
                    try:self.writer.close()
                    finally:self.controller.active=None
            elif self.job is None and self.writer is not None:self.writer.close()


def queue_resume(controller,run_id,request_id):
    runs=controller.runs;uuid(run_id);uuid(request_id)
    with runs.store._live():
        old=runs.store.conn.execute('SELECT action,receipt FROM baseline_controls WHERE run_id=? AND request_id=?',(run_id,request_id)).fetchone()
        if old:
            if old[0]!='resume':raise DataError('CONTROL_CONFLICT')
            import json
            return json.loads(old[1])
        if controller.pending is not None and controller.pending.run_id==run_id and controller.pending.request_id==request_id:
            return dict(controller.pending.reply)
        if controller.busy:raise RuntimeRefused('JOB_SLOT_BUSY')
        state=runs._load(run_id)
        if state['state'] in {'COMPLETED','FAILED','STOPPED'}:raise DataError('RUN_TERMINAL')
        if state['state'] in {'RUNNING','PREPARING'}:raise DataError('RUN_BUSY')
        if runs.store.conn.execute('SELECT count(*) FROM baseline_controls WHERE run_id=?',(run_id,)).fetchone()[0]>=128:raise DataError('CONTROL_BOUND')
        controller.coordinator.require_health()
        operation=_CampaignOperation(controller,run_id,'resume',request_id=request_id)
        try:
            receipt={**campaign.view(state,compact=True),'pending_operation':operation.view()}
            operation.reply=receipt
            controller.pending=operation
            return receipt
        except BaseException:operation.close();raise
