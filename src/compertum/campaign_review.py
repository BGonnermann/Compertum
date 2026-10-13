"""Foreground native campaign reviews with coordinator-owned streamed acceptance."""
from datetime import datetime,timedelta,timezone
from .review_runs import ReviewRuns,MIB
from .domain import TaskSpec
from .foundation import fixture_spec
from .runtime.errors import RuntimeRefused
from .runtime.jobs import launch_bounded,preflight_campaign,job_slot_busy
from .storage import adopt_fixture_bytes


class CampaignReviewController:
    def __init__(self,coordinator,storage):
        self.coordinator=coordinator;self.storage=storage;self.runs=ReviewRuns(storage);self.active=None

    def step(self,task_id):
        if self.coordinator.status()['research_state']!='RUNNING':raise RuntimeRefused('RESEARCH_PAUSED')
        self.coordinator.require_health()
        if self.active or job_slot_busy(self.storage.lease):raise RuntimeRefused('JOB_SLOT_BUSY')
        old=self.runs.status(task_id)
        if old['state']=='COMPLETED':return self.runs.completed(task_id)
        now=datetime.now(timezone.utc);preflight_campaign(self.storage.lease);prepared=self.runs.prepare(task_id)
        writer=None;job=None
        try:
            s=self.runs.status(task_id);header,_=self.runs.bundle(s);artifacts=[s['request_artifact']]+[r['artifact'] for r in header['records']]
            payload=fixture_spec(self.storage.root,task_id).to_payload()
            payload.update(role='experiment_runner' if s['kind']=='scorecard' else 'experiment_auditor',parent_task_id=s['source_run_id'],campaign_id=s['source_run_id'],created_at=now.isoformat(),deadline_at=(now+timedelta(seconds=120)).isoformat())
            payload['input_hashes']=[a['sha256'] for a in artifacts];payload['permissions']['filesystem_bundle']=[a['path'] for a in artifacts]
            payload['permissions']['output_directory']=f'artifacts/runs/{task_id}/review'
            payload['budget'].update(cpu_threads=4,ram_bytes=4*1024**3,output_bytes=16*MIB,wall_seconds=120)
            task=TaskSpec(payload,project_root=self.storage.root);self.runs.bind_task(prepared,payload)
            grant=self.storage.reserve_bytes(task_id,'records',16*MIB);writer=self.storage.open_artifact(grant,prepared['output_path'])
            def commit(identity):
                self.coordinator.require_health(refresh=True);self.runs.begin(prepared,payload,grant.grant_id,identity)
            job=launch_bounded(self.storage.lease,task,['fixture',s['kind'],str(writer.destination)],writer=writer,review_request=prepared,before_resume=commit,before_execute=self.coordinator.require_health)
            self.active=(task_id,writer,job);return self.runs.status(task_id)
        except Exception as error:
            if job is not None:job.close()
            if writer is not None:writer.close()
            retry=isinstance(error,OSError) or isinstance(error,RuntimeRefused) and error.code in {'STORAGE_CAPACITY','AVAILABLE_RAM_FLOOR','JOB_SLOT_BUSY','LOCAL_AI_SLOT_BUSY'}
            if self.runs.status(task_id)['state'] in ('PREPARING','RUNNING'):self.runs.interrupt(task_id,'LAUNCH_RETRYABLE' if retry else 'LAUNCH_FAILED',retry=retry)
            raise

    def tick(self):
        if self.active is None:return
        task,writer,job=self.active
        if job.api.active(job.job):return
        try:
            receipt=job.wait();self.runs.record_exit(task,receipt);adopt_fixture_bytes(writer,job)
            if receipt['timed_out']:self.runs.interrupt(task,'JOB_TIMEOUT',retry=True);return
            if receipt['exit_code']!=0:
                self.runs.interrupt(task,'WORKER_FAILED' if receipt['exit_code']==5 else 'REVIEW_REJECTED',retry=receipt['exit_code']==5);return
            self.coordinator.require_health();artifact=writer.publish();self.runs.accept(task,artifact)
        except Exception as error:
            if self.runs.status(task)['state']=='RUNNING':self.runs.interrupt(task,'REVIEW_ACCEPTANCE_IO_FAILURE' if isinstance(error,OSError) else 'REVIEW_ACCEPTANCE_FAILED',retry=isinstance(error,OSError))
        finally:job.close();writer.close();self.active=None

    def pause(self):
        if self.active is None:return
        task,writer,job=self.active
        try:
            job.api.checked(job.api.TerminateJobObject(job.job.get(),125),'PauseReviewJob')
            receipt=job.wait();self.runs.record_exit(task,receipt);adopt_fixture_bytes(writer,job)
            if receipt['timed_out']:self.runs.interrupt(task,'JOB_TIMEOUT',retry=True)
            elif receipt['exit_code']==5:self.runs.interrupt(task,'WORKER_FAILED',retry=True)
            elif receipt['exit_code'] not in (0,125):self.runs.interrupt(task,'REVIEW_REJECTED',retry=False)
            else:self.runs.interrupt(task,'OPERATOR_PAUSE',retry=True)
        except Exception as error:
            if self.runs.status(task)['state']=='RUNNING':self.runs.interrupt(task,'PAUSE_IO_FAILURE' if isinstance(error,OSError) else 'PAUSE_BOOKKEEPING_FAILURE',retry=isinstance(error,OSError))
            raise
        finally:job.close();writer.close();self.active=None
