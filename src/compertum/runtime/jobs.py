"""Suspended, owner-bound native Jobs for registered offline fixtures only."""
import ctypes as c
from datetime import datetime, timezone
import math
import json,re
from uuid import uuid4
import os
from pathlib import Path
import subprocess
import sys
import time
import threading
from ._windows import WindowsAPI, DWORD, BOOL, HANDLE, OwnedHandle
from .errors import RuntimeRefused
from .startup import StartupBinding
from .owners import _owner_scope, require_live_owner
from compertum.domain import TaskSpec
from compertum.persistence import checked_path, open_store

SIZE=c.c_size_t
_ACTIVE={}

class MemoryStatus(c.Structure):
    _fields_=[('length',DWORD),('load',DWORD)]+[(name,c.c_uint64) for name in ('total','available','page_total','page_available','virtual_total','virtual_available','extended')]


def available_physical_memory():
    kernel=c.WinDLL('kernel32',use_last_error=True)
    query=kernel.GlobalMemoryStatusEx;query.argtypes=[c.POINTER(MemoryStatus)];query.restype=BOOL
    value=MemoryStatus();value.length=c.sizeof(value)
    if not query(c.byref(value)): raise RuntimeRefused('AVAILABLE_RAM_UNVERIFIED')
    return value.available

class BasicLimits(c.Structure):
    _fields_=[('process_time',c.c_int64),('job_time',c.c_int64),('flags',DWORD),('min_ws',SIZE),('max_ws',SIZE),('active_limit',DWORD),('affinity',SIZE),('priority',DWORD),('scheduling',DWORD)]
class IOCounters(c.Structure):
    _fields_=[(name,c.c_uint64) for name in ('reads','writes','other','read_bytes','write_bytes','other_bytes')]
class ExtendedLimits(c.Structure):
    _fields_=[('basic',BasicLimits),('io',IOCounters),('process_memory',SIZE),('job_memory',SIZE),('peak_process_memory',SIZE),('peak_job_memory',SIZE)]
class Accounting(c.Structure):
    _fields_=[('user',c.c_int64),('kernel',c.c_int64),('period_user',c.c_int64),('period_kernel',c.c_int64),('faults',DWORD),('total',DWORD),('active',DWORD),('terminated',DWORD)]
class ProcessList(c.Structure):
    _fields_=[('assigned',DWORD),('count',DWORD),('pids',SIZE*4)]
class Startup(c.Structure):
    _fields_=[('size',DWORD),('reserved',c.c_wchar_p),('desktop',c.c_wchar_p),('title',c.c_wchar_p),('x',DWORD),('y',DWORD),('width',DWORD),('height',DWORD),('chars_x',DWORD),('chars_y',DWORD),('fill',DWORD),('flags',DWORD),('show',c.c_uint16),('reserved_size',c.c_uint16),('reserved_data',HANDLE),('stdin',HANDLE),('stdout',HANDLE),('stderr',HANDLE)]
class ProcessInfo(c.Structure):
    _fields_=[('process',HANDLE),('thread',HANDLE),('pid',DWORD),('tid',DWORD)]


class JobAPI(WindowsAPI):
    def __init__(self):
        super().__init__(); kernel=c.WinDLL('kernel32',use_last_error=True)
        def bind(name,result,*args):
            fn=getattr(kernel,name); fn.restype=result; fn.argtypes=list(args); setattr(self,name,fn)
        bind('CreateJobObjectW',HANDLE,HANDLE,c.c_wchar_p)
        bind('SetInformationJobObject',BOOL,HANDLE,c.c_int,HANDLE,DWORD)
        bind('QueryInformationJobObject',BOOL,HANDLE,c.c_int,HANDLE,DWORD,c.POINTER(DWORD))
        bind('AssignProcessToJobObject',BOOL,HANDLE,HANDLE)
        bind('IsProcessInJob',BOOL,HANDLE,HANDLE,c.POINTER(BOOL))
        bind('TerminateJobObject',BOOL,HANDLE,DWORD)
        bind('TerminateProcess',BOOL,HANDLE,DWORD)
        bind('GetExitCodeProcess',BOOL,HANDLE,c.POINTER(DWORD))
        bind('GetProcessAffinityMask',BOOL,HANDLE,c.POINTER(SIZE),c.POINTER(SIZE))
        bind('CreateProcessW',BOOL,c.c_wchar_p,c.c_wchar_p,HANDLE,HANDLE,BOOL,DWORD,HANDLE,c.c_wchar_p,c.POINTER(Startup),c.POINTER(ProcessInfo))
        bind('ResumeThread',DWORD,HANDLE)

    def assign(self,job,process):
        self.checked(self.AssignProcessToJobObject(job.get(),process.get()),'AssignProcessToJobObject')
        member=BOOL()
        self.checked(self.IsProcessInJob(process.get(),job.get(),c.byref(member)),'IsProcessInJob')
        if not member.value: raise RuntimeRefused('ASSIGNMENT_UNVERIFIED')

    def limits(self,job):
        result=ExtendedLimits()
        self.checked(self.QueryInformationJobObject(job.get(),9,c.byref(result),c.sizeof(result),None),'QueryJobLimits')
        return result

    def active(self,job):
        result=Accounting()
        self.checked(self.QueryInformationJobObject(job.get(),1,c.byref(result),c.sizeof(result),None),'QueryJobAccounting')
        return result.active


class JobHandle:
    def __init__(self,api,lease,job,process,pid,deadline,limits):
        self.api=api; self.lease=lease; self.job=job; self.process=process; self.pid=pid
        self.deadline=deadline; self.expected=limits; self.closed=False; self.receipt=None; self.children={}
        self.started=time.monotonic();self.budget_store=None;self.budget_id=None;self.budget_finished=False
        self.startup_evidence=None;self._startup_plan_raw=None
        self.timed_out=False;self.ended=None;self.deadline_error=None;self._execution_identity_raw=None
        self._monitor_stop=threading.Event();self._monitor=None

    @property
    def startup_plan(self):
        return json.loads(self._startup_plan_raw) if self._startup_plan_raw is not None else None

    @property
    def execution_identity(self):
        return json.loads(self._execution_identity_raw) if self._execution_identity_raw is not None else None

    def start_monitor(self):
        # No SQLite or role capability is used by this thread. It owns only the
        # native deadline observation until close joins it before closing handles.
        self._monitor=threading.Thread(target=self._monitor_deadline,name='compertum-job-deadline',daemon=True)
        try:self._monitor.start()
        except BaseException:
            self._monitor=None
            raise

    def _monitor_deadline(self):
        try:
            while not self._monitor_stop.is_set():
                if not self.api.active(self.job):
                    self.ended=time.monotonic();return
                if time.monotonic()>=self.deadline and not self.timed_out:
                    self.timed_out=True
                    self.api.checked(self.api.TerminateJobObject(self.job.get(),124),'DeadlineTerminateJob')
                self._monitor_stop.wait(.01)
        except BaseException as error:
            self.deadline_error=error
            self.api.TerminateJobObject(self.job.get(),125)

    def _stop_monitor(self):
        self._monitor_stop.set()
        if self._monitor is not None:
            self._monitor.join(timeout=1)
            if self._monitor.is_alive():raise RuntimeRefused('JOB_MONITOR_UNVERIFIED')

    def _finish_budget(self):
        if not self.budget_finished and self.budget_store is not None:
            try:
                with self.budget_store._live(),self.budget_store.conn:
                    self.budget_store.conn.execute("UPDATE job_budget SET charged=?,status='FINISHED' WHERE id=?",(math.ceil((self.ended or time.monotonic())-self.started),self.budget_id))
            except RuntimeRefused as error:
                if error.code!='OWNER_UNVERIFIED': raise
            self.budget_finished=True
        if getattr(self,'audit_lifetime',None) is None and _ACTIVE.get(self.lease.project_id) is self: _ACTIVE.pop(self.lease.project_id,None)

    def _observe_children(self):
        data=ProcessList()
        self.api.checked(self.api.QueryInformationJobObject(self.job.get(),3,c.byref(data),c.sizeof(data),None),'QueryJobProcesses')
        if data.count>4: raise RuntimeRefused('JOB_PROCESS_UNVERIFIED')
        for pid in data.pids[:data.count]:
            if pid==self.pid or pid in self.children: continue
            try: handle=self.api.open_process(pid)
            except RuntimeRefused:
                if pid not in self.api.process_snapshot(): continue
                raise
            member=BOOL()
            self.api.checked(self.api.IsProcessInJob(handle.get(),self.job.get(),c.byref(member)),'IsChildInJob')
            if not member.value:
                handle.close();raise RuntimeRefused('JOB_PROCESS_UNVERIFIED')
            self.children[pid]=handle

    def _wait_handles(self):
        deadline=time.monotonic()+3
        for handle in (self.process,*self.children.values()):
            if self.api.WaitForSingleObject(handle.get(),max(0,int((deadline-time.monotonic())*1000)))!=0:
                raise RuntimeRefused('JOB_EXIT_UNVERIFIED')

    def wait(self):
        if self.receipt is not None: return dict(self.receipt)
        require_live_owner(self.lease)
        timed_out=False
        if self.deadline_error is not None:raise RuntimeRefused('JOB_MONITOR_UNVERIFIED') from self.deadline_error
        while self.api.active(self.job):
            self._observe_children()
            if time.monotonic()>=self.deadline:
                timed_out=True; self.api.checked(self.api.TerminateJobObject(self.job.get(),124),'TerminateJobObject'); break
            time.sleep(.01)
        end=time.monotonic()+3
        while self.api.active(self.job) and time.monotonic()<end: time.sleep(.01)
        if self.api.active(self.job) or self.api.WaitForSingleObject(self.process.get(),3000)!=0:
            raise RuntimeRefused('JOB_EXIT_UNVERIFIED')
        self._wait_handles()
        code=DWORD(); self.api.checked(self.api.GetExitCodeProcess(self.process.get(),c.byref(code)),'GetExitCodeProcess')
        limits=self.api.limits(self.job)
        self.receipt={'pid':self.pid,'exit_code':code.value,'timed_out':timed_out or self.timed_out,'active_processes':0,
                      'assigned_before_resume':True,'affinity':limits.basic.affinity,'memory_limit':limits.job_memory,
                      'peak_job_memory':limits.peak_job_memory,'observed_child_pids':sorted(self.children),'observed_children_exited':True}
        if self.execution_identity is not None:self.receipt['execution_identity']=self.execution_identity
        self.ended=self.ended or time.monotonic()
        self._finish_budget()
        return dict(self.receipt)

    def close(self):
        if getattr(self,'audit_lifetime',None) is not None:
            from .audit_job_lifetime import close
            return close(self)
        if not self.closed:
            self.closed=True
            try:
                self._observe_children()
                self.api.checked(self.api.TerminateJobObject(self.job.get(),125),'TerminateJobObject')
                end=time.monotonic()+3
                while self.api.active(self.job) and time.monotonic()<end: time.sleep(.01)
                if self.api.active(self.job): raise RuntimeRefused('JOB_EXIT_UNVERIFIED')
                self._wait_handles()
                self._finish_budget()
            finally:
                self._stop_monitor()
                for handle in self.children.values(): handle.close()
                self.process.close(); self.job.close()

    def __enter__(self): return self
    def __exit__(self,*args): self.close()


def job_slot_busy(lease):
    require_live_owner(lease,'coordinator')
    return lease.project_id in _ACTIVE


def preflight_campaign(lease):
    """Read current admission gates before reserving a campaign output."""
    require_live_owner(lease,'coordinator')
    with _owner_scope(lease):
        if lease.project_id in _ACTIVE:raise RuntimeRefused('JOB_SLOT_BUSY')
        if available_physical_memory()<8*1024**3:raise RuntimeRefused('AVAILABLE_RAM_FLOOR')
        store=open_store(lease,'coordinator')
        from compertum.final_audit_runs import require_closed_audits
        require_closed_audits(store,lease.identity.process_instance_id)
        if store.conn.execute("SELECT 1 FROM sqlite_master WHERE name='local_ai_state'").fetchone():
            ai=store.conn.execute("SELECT value FROM local_ai_state WHERE key='dispatch'").fetchone()
            if ai and ai[0]!='IDLE':raise RuntimeRefused('LOCAL_AI_SLOT_BUSY')


def _campaign_inputs(lease,payload,writer,unit,primary,dependency,dependency_sha256,before_resume):
    from compertum.campaign_contract import UNITS
    budget=payload['budget'];run=payload['task_id'];base=f'artifacts/runs/{run}/baseline/'
    if (payload['role']!='experiment_runner' or type(unit) is not int or not 0<=unit<len(UNITS) or not callable(before_resume)
            or budget['wall_seconds']!=120 or budget['cpu_threads']!=4 or budget['ram_bytes']!=4*1024**3
            or writer.grant.maximum!=16*1024**2 or budget['output_bytes']!=writer.grant.maximum
            or not re.fullmatch(r'unit-'+f'{unit:02}'+r'-attempt-[12]\.campaign',writer.destination.name)):
        raise RuntimeRefused('CAMPAIGN_INPUT_DENIED')
    parent=UNITS[unit].fit_unit
    artifacts=[primary];paths=[base+'inputs.json'];maxima=[20*1024**2]
    if parent is None:
        if dependency is not None or dependency_sha256 is not None:raise RuntimeRefused('CAMPAIGN_INPUT_DENIED')
    else:
        if (not isinstance(dependency,dict) or not isinstance(dependency_sha256,str)
                or not re.fullmatch('[0-9a-f]{64}',dependency_sha256)
                or dependency.get('path') not in [base+f'unit-{parent:02}-attempt-{n}.campaign' for n in (1,2)]):
            raise RuntimeRefused('CAMPAIGN_INPUT_DENIED')
        artifacts.append(dependency);paths.append(dependency['path']);maxima.append(16*1024**2)
    store=open_store(lease,'coordinator')
    for artifact,path,maximum in zip(artifacts,paths,maxima):
        if (not isinstance(artifact,dict) or artifact.get('path')!=path or artifact.get('task_id')!=run
                or type(artifact.get('size_bytes')) is not int or not 0<artifact['size_bytes']<=maximum
                or not isinstance(artifact.get('sha256'),str) or not re.fullmatch('[0-9a-f]{64}',artifact['sha256'])):
            raise RuntimeRefused('CAMPAIGN_INPUT_DENIED')
        row=store.conn.execute("SELECT manifest FROM reservations WHERE task=? AND path=? AND status='PUBLISHED'",(run,path)).fetchone()
        if row is None or json.loads(row[0])!=artifact:raise RuntimeRefused('CAMPAIGN_INPUT_DENIED')
    if (payload['permissions']['filesystem_bundle']!=paths or payload['input_hashes']!=[a['sha256'] for a in artifacts]
            or payload['permissions']['output_directory']!=base.rstrip('/')
            or writer.destination.relative_to(writer.manager.root).as_posix()!=base+writer.destination.name):
        raise RuntimeRefused('CAMPAIGN_INPUT_DENIED')


def launch_bounded(lease,task,argv,*,writer=None,offset=0,input_artifact=None,unit=None,dependency_artifact=None,dependency_sha256=None,before_resume=None,before_execute=None,fit_artifact=None,audit_request=None,review_request=None,final_request=None,final_audit_request=None):
    # Capture ownership before CreateProcess can return.
    from .audit_job_lifetime import AuditLaunch,AuditLaunchFailed
    tracker=AuditLaunch(final_audit_request,writer) if final_audit_request is not None else None
    try:
        return _launch_bounded(lease,task,argv,writer=writer,offset=offset,input_artifact=input_artifact,unit=unit,dependency_artifact=dependency_artifact,dependency_sha256=dependency_sha256,before_resume=before_resume,before_execute=before_execute,fit_artifact=fit_artifact,audit_request=audit_request,review_request=review_request,final_request=final_request,final_audit_request=final_audit_request,_audit_launch=tracker)
    except BaseException as error:
        if tracker is not None:raise AuditLaunchFailed(tracker) from error
        raise


def _launch_bounded(lease,task,argv,*,writer=None,offset=0,input_artifact=None,unit=None,dependency_artifact=None,dependency_sha256=None,before_resume=None,before_execute=None,fit_artifact=None,audit_request=None,review_request=None,final_request=None,final_audit_request=None,_audit_launch=None):
    require_live_owner(lease)
    if lease.identity.role!='coordinator' or not isinstance(task,TaskSpec): raise RuntimeRefused('JOB_ADMISSION_DENIED')
    payload=task.to_payload(); budget=payload['budget']
    if payload['kind']!='OFFLINE_FIXTURE' or len(argv)!=3 or argv[0]!='fixture' or argv[1] not in {'echo','tree','memory','breakaway','sleep','canonical','replay','campaign','audit','scorecard','aggregate','pair_compare','final','final_audit'}:
        raise RuntimeRefused('UNREGISTERED_COMMAND')
    if argv[1] not in {'replay','campaign','audit'} and (input_artifact is not None or unit is not None):raise RuntimeRefused('REPLAY_INPUT_DENIED')
    if argv[1] not in {'campaign','audit','scorecard','aggregate','pair_compare','final','final_audit'} and any(v is not None for v in (dependency_artifact,dependency_sha256,before_resume)):raise RuntimeRefused('CAMPAIGN_INPUT_DENIED')
    if argv[1]!='audit' and (fit_artifact is not None or audit_request is not None):raise RuntimeRefused('AUDITOR_INPUT_DENIED')
    if argv[1] not in {'scorecard','aggregate','pair_compare'} and review_request is not None:raise RuntimeRefused('REVIEW_INPUT_DENIED')
    if argv[1] not in {'scorecard','aggregate','pair_compare'} and before_execute is not None:raise RuntimeRefused('REVIEW_INPUT_DENIED')
    if argv[1] in {'scorecard','aggregate','pair_compare'} and not callable(before_execute):raise RuntimeRefused('REVIEW_INPUT_DENIED')
    if argv[1] in {'scorecard','aggregate','pair_compare'} and any(v is not None for v in (input_artifact,unit,dependency_artifact,dependency_sha256,fit_artifact,audit_request)):raise RuntimeRefused('REVIEW_INPUT_DENIED')
    if argv[1]!='final' and final_request is not None:raise RuntimeRefused('FINAL_INPUT_DENIED')
    if argv[1]=='final' and (not callable(before_resume) or type(final_request) is not dict or any(v is not None for v in (input_artifact,unit,dependency_artifact,dependency_sha256,fit_artifact,audit_request,review_request))):raise RuntimeRefused('FINAL_INPUT_DENIED')
    if argv[1]!='final_audit' and final_audit_request is not None:raise RuntimeRefused('FINAL_AUDIT_INPUT_DENIED')
    if argv[1]=='final_audit' and (type(final_audit_request) is not dict or not callable(before_resume) or any(v is not None for v in (input_artifact,unit,dependency_artifact,dependency_sha256,fit_artifact,audit_request,review_request,final_request))):raise RuntimeRefused('FINAL_AUDIT_INPUT_DENIED')
    with _owner_scope(lease) as guard:
        if lease.project_id in _ACTIVE: raise RuntimeRefused('JOB_SLOT_BUSY')
        if available_physical_memory()<8*1024**3: raise RuntimeRefused('AVAILABLE_RAM_FLOOR')
        remaining=(datetime.fromisoformat(payload['deadline_at'].replace('Z','+00:00'))-datetime.now(timezone.utc)).total_seconds()
        if remaining<=0: raise RuntimeRefused('TASK_DEADLINE_EXCEEDED')
        deadline=time.monotonic()+min(remaining,budget['wall_seconds'])
        if argv[1] in {'campaign','audit','scorecard','aggregate','pair_compare','final','final_audit'}:
            elapsed=(datetime.now(timezone.utc)-datetime.fromisoformat(payload['created_at'].replace('Z','+00:00'))).total_seconds()
            campaign_started=time.monotonic()-max(0,elapsed)
            deadline=min(deadline,campaign_started+(budget['wall_seconds'] if argv[1]=='final' else 120))
            if time.monotonic()>=deadline:raise RuntimeRefused('TASK_DEADLINE_EXCEEDED')
        output=checked_path(guard.project.root_path,Path(argv[2]))
        namespace=guard.project.root_path/payload['permissions']['output_directory']
        if not output.is_relative_to(namespace) or output.exists(): raise RuntimeRefused('OUTPUT_DENIED')
        if argv[1] in {'canonical','replay','campaign','audit','scorecard','aggregate','pair_compare','final','final_audit'}:
            from compertum.storage import BoundedWriter
            from .fixture_worker import CANONICAL
            if (not isinstance(writer,BoundedWriter) or writer.manager.lease is not lease
                    or writer.grant.task_id!=payload['task_id'] or writer.destination!=output
                    or writer.grant.maximum<len(CANONICAL) or writer.written!=offset
                    or type(offset) is not int or not 0<=offset<=len(CANONICAL)):
                raise RuntimeRefused('FIXTURE_SINK_DENIED')
            if argv[1]=='replay':
                expected=f"artifacts/runs/{payload['task_id']}/baseline/inputs.json"
                if (not isinstance(input_artifact,dict) or input_artifact.get('path')!=expected
                        or payload['permissions']['filesystem_bundle']!=[expected]
                        or payload['input_hashes']!=[input_artifact.get('sha256')]
                        or type(input_artifact.get('size_bytes')) is not int or not 0<input_artifact['size_bytes']<=20*1024**2
                        or type(unit) is not int or not 0<=unit<9 or offset!=0
                        or writer.grant.maximum>min(16*1024**2,budget['output_bytes'])):raise RuntimeRefused('REPLAY_INPUT_DENIED')
            if argv[1]=='campaign':
                if offset!=0:raise RuntimeRefused('CAMPAIGN_INPUT_DENIED')
                _campaign_inputs(lease,payload,writer,unit,input_artifact,dependency_artifact,dependency_sha256,before_resume)
                from compertum.simulation.campaign_runs import verify_native_admission
                verify_native_admission(writer.manager.store,lease.identity.process_instance_id,payload['task_id'],unit,input_artifact,
                    dependency_artifact,dependency_sha256,output.relative_to(guard.project.root_path).as_posix(),writer.grant.grant_id,started=False)
            if argv[1]=='final':
                if offset!=0:raise RuntimeRefused('FINAL_INPUT_DENIED')
                from compertum.final_dispatch import FinalRuns
                from compertum.review_evidence import published
                final_runs=FinalRuns(writer.manager)
                final_dispatch=final_runs.verify_launch(final_request,payload,writer.grant.grant_id)
                final_value=json.loads(published(writer.manager,final_dispatch['request_artifact'],32768,read=True))
                final_artifacts=[final_dispatch['request_artifact'],final_value['source_artifact']]
                if output.relative_to(guard.project.root_path).as_posix()!=final_dispatch['attempt']['output_path']:raise RuntimeRefused('FINAL_INPUT_DENIED')
            if argv[1] in {'scorecard','aggregate','pair_compare'}:
                if offset!=0 or not callable(before_resume) or not isinstance(review_request,dict):raise RuntimeRefused('REVIEW_INPUT_DENIED')
                from compertum.review_runs import ReviewRuns
                reviews=ReviewRuns(writer.manager)
                review_state,review_artifacts=reviews.verify_launch(review_request,payload,writer.grant.grant_id)
                if review_state['kind']!=argv[1] or output.relative_to(guard.project.root_path).as_posix()!=review_request['output_path']:raise RuntimeRefused('REVIEW_INPUT_DENIED')
            if argv[1]=='final_audit':
                from compertum.final_audit_runs import FinalAuditRuns
                if offset!=0:raise RuntimeRefused('FINAL_AUDIT_INPUT_DENIED')
                final_audits=FinalAuditRuns(writer.manager)
                final_audit_state,final_audit_artifacts=final_audits.verify_launch(final_audit_request,payload,writer.grant.grant_id)
                if output.relative_to(guard.project.root_path).as_posix()!=final_audit_request['output_path']:raise RuntimeRefused('FINAL_AUDIT_INPUT_DENIED')
            if argv[1]=='audit':
                if offset!=0 or not callable(before_resume):raise RuntimeRefused('AUDITOR_INPUT_DENIED')
                from compertum.audit_runs import AuditRuns
                audits=AuditRuns(writer.manager)
                if not isinstance(audit_request,dict):raise RuntimeRefused('AUDITOR_INPUT_DENIED')
                audits.verify_launch(audit_request,payload,writer.grant.grant_id)
                request=audit_request['request']
                if (type(unit) is not int or unit!=request['unit'] or input_artifact!=request['input_artifact'] or dependency_artifact!=request['result']['artifact']
                        or fit_artifact!=(request['fit']['artifact'] if request['fit'] else None) or dependency_sha256!=(request['fit']['payload_sha256'] if request['fit'] else None)
                        or output.relative_to(guard.project.root_path).as_posix()!=audit_request['output_path']):raise RuntimeRefused('AUDITOR_INPUT_DENIED')
        elif writer is not None or offset!=0: raise RuntimeRefused('FIXTURE_SINK_DENIED')
        clean_expectation=None
        if argv[1] in {'campaign','audit','scorecard','aggregate','pair_compare','final'}:
            from compertum.development_seals import expected_environment
            source_run=final_value['source_artifact']['task_id'] if argv[1]=='final' else payload['task_id'] if argv[1]=='campaign' else request['source_run_id'] if argv[1]=='audit' else review_state['source_run_id']
            clean_expectation=expected_environment(writer.manager.store,source_run)
        output.parent.mkdir(parents=True,exist_ok=True)
        budget_store=open_store(lease,'coordinator');budget_id=str(uuid4());day=datetime.now().astimezone().date().isoformat()
        from compertum.final_audit_runs import require_closed_audits
        require_closed_audits(budget_store,lease.identity.process_instance_id,final_audit_request)
        if budget_store.conn.execute("SELECT 1 FROM sqlite_master WHERE name='local_ai_state'").fetchone():
            active_ai=budget_store.conn.execute("SELECT value FROM local_ai_state WHERE key='dispatch'").fetchone()
            if active_ai and active_ai[0]!='IDLE': raise RuntimeRefused('LOCAL_AI_SLOT_BUSY')
        with budget_store.conn:
            budget_store.conn.execute('CREATE TABLE IF NOT EXISTS job_budget(id TEXT PRIMARY KEY,day TEXT NOT NULL,charged INTEGER NOT NULL,status TEXT NOT NULL)')
            # Record elapsed usage without imposing a daily runtime cap.
            budget_store.conn.execute("INSERT INTO job_budget VALUES(?,?,?,'RESERVED')",(budget_id,day,budget['wall_seconds']+6))
        api=JobAPI(); job=api._handle(api.CreateJobObjectW(None,None),'CreateJobObjectW')
        process=None; thread=None;startup_binding=None
        if argv[1]=='final_audit':
            from .audit_job_lifetime import enable,adopt_child
            handle=enable(JobHandle(api,lease,job,None,None,deadline,None),final_audit_request,writer)
            handle.started=campaign_started;handle.budget_store=budget_store;handle.budget_id=budget_id
            _audit_launch.job=handle;writer._final_audit_job=handle
            _ACTIVE[lease.project_id]=handle;guard.resources.append(handle)
        try:
            available=SIZE(); system=SIZE()
            api.checked(api.GetProcessAffinityMask(HANDLE(-1),c.byref(available),c.byref(system)),'GetProcessAffinityMask')
            bits=[1<<n for n in range(64) if available.value&(1<<n)][:budget['cpu_threads']]
            if not bits: raise RuntimeRefused('CPU_AFFINITY_UNAVAILABLE')
            limits=ExtendedLimits(); limits.basic.flags=0x2000|0x100|0x200|0x10|0x8|0x400
            limits.basic.affinity=sum(bits); limits.basic.active_limit=1 if argv[1] in {'audit','scorecard','aggregate','pair_compare','final','final_audit'} else 4
            limits.process_memory=budget['ram_bytes']; limits.job_memory=budget['ram_bytes']
            api.checked(api.SetInformationJobObject(job.get(),9,c.byref(limits),c.sizeof(limits)),'SetJobLimits')
            actual=api.limits(job)
            if (actual.basic.flags!=limits.basic.flags or actual.basic.affinity!=limits.basic.affinity
                    or actual.process_memory!=limits.process_memory or actual.job_memory!=limits.job_memory or actual.basic.active_limit!=limits.basic.active_limit):
                raise RuntimeRefused('JOB_LIMITS_UNVERIFIED')
            runtime=getattr(sys,'_base_executable',None)
            if not runtime or not Path(runtime).is_file(): raise RuntimeRefused('RUNTIME_UNAVAILABLE')
            auditor_expectation=final_audit_state['auditor_environment'] if argv[1]=='final_audit' else None
            startup_binding=StartupBinding(api,output.parent,clean_environment=clean_expectation,auditor_environment=auditor_expectation)
            if argv[1]=='final_audit':handle.expected=limits;handle.audit_lifetime.startup=startup_binding
            env={k:v for k,v in os.environ.items() if k.upper() in {'SYSTEMROOT','WINDIR'}}
            env.update(__PYVENV_LAUNCHER__=sys.executable,PYTHONDONTWRITEBYTECODE='1',PYTHONNOUSERSITE='1',
                       PYTHONPATH=str(Path(__file__).resolve().parents[2]),TEMP=str(output.parent),TMP=str(output.parent))
            startup_binding.apply(env)
            for key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'): env[key]=str(budget['cpu_threads'])
            command=[sys.executable,'-B','-m','compertum.runtime.fixture_worker',argv[1],str(output)]
            if argv[1] in {'canonical','replay','campaign','audit','scorecard','aggregate','pair_compare','final','final_audit'}:
                import msvcrt
                from .bootstrap import _INHERIT_LOCK
                with _INHERIT_LOCK:
                    native=msvcrt.get_osfhandle(writer.stream.fileno())
                    borrowed=OwnedHandle(api,native)
                    api.set_inheritable(borrowed,True)
                    input_stream=None;input_handle=None;dependency_stream=None;dependency_handle=None;fit_stream=None;fit_handle=None;review_streams=[];review_handles=[]
                    try:
                        inherited=(native,)
                        if argv[1]=='final_audit':
                            for artifact in final_audit_artifacts:
                                path=checked_path(guard.project.root_path,guard.project.root_path/artifact['path'])
                                stream=path.open('rb');review_streams.append(stream)
                                native_input=OwnedHandle(api,msvcrt.get_osfhandle(stream.fileno()));review_handles.append(native_input)
                                if os.fstat(stream.fileno()).st_size!=artifact['size_bytes']:raise RuntimeRefused('FINAL_AUDIT_INPUT_DENIED')
                                api.set_inheritable(native_input,True);inherited+=(native_input.value,)
                            command=[sys.executable,'-B','-m','compertum.runtime.audit_worker','final_audit',str(review_handles[0].value),str(native),str(final_audit_artifacts[0]['size_bytes']),final_audit_artifacts[0]['sha256'],str(review_handles[1].value),str(review_handles[2].value),str(writer.grant.maximum)]
                        elif argv[1]=='final':
                            for artifact in final_artifacts:
                                path=checked_path(guard.project.root_path,guard.project.root_path/artifact['path'])
                                stream=path.open('rb');review_streams.append(stream)
                                native_input=OwnedHandle(api,msvcrt.get_osfhandle(stream.fileno()));review_handles.append(native_input)
                                if os.fstat(stream.fileno()).st_size!=artifact['size_bytes']:raise RuntimeRefused('FINAL_INPUT_DENIED')
                                api.set_inheritable(native_input,True);inherited+=(native_input.value,)
                            command=[sys.executable,'-B','-m','compertum.runtime.campaign_worker','final',str(review_handles[0].value),str(native),str(final_artifacts[0]['size_bytes']),final_artifacts[0]['sha256'],str(review_handles[1].value),str(writer.grant.maximum)]
                        elif argv[1] in {'scorecard','aggregate','pair_compare'}:
                            for artifact in review_artifacts:
                                path=checked_path(guard.project.root_path,guard.project.root_path/artifact['path'])
                                stream=path.open('rb');review_streams.append(stream)
                                native_input=OwnedHandle(api,msvcrt.get_osfhandle(stream.fileno()));review_handles.append(native_input)
                                if os.fstat(stream.fileno()).st_size!=artifact['size_bytes']:raise RuntimeRefused('REVIEW_INPUT_DENIED')
                                api.set_inheritable(native_input,True);inherited+=(native_input.value,)
                            entrypoint='compertum.runtime.campaign_worker' if argv[1]=='scorecard' else 'compertum.runtime.audit_worker'
                            command=[sys.executable,'-B','-m',entrypoint,argv[1],str(review_handles[0].value),str(native),
                                str(review_artifacts[0]['size_bytes']),review_state['request_sha256'],payload['task_id'],review_state['source_run_id'],str(writer.grant.maximum),','.join(str(h.value) for h in review_handles[1:])]
                        elif argv[1] in {'replay','campaign','audit'}:
                            input_path=checked_path(guard.project.root_path,guard.project.root_path/input_artifact['path'])
                            input_stream=input_path.open('rb');input_handle=OwnedHandle(api,msvcrt.get_osfhandle(input_stream.fileno()))
                            if os.fstat(input_stream.fileno()).st_size!=input_artifact['size_bytes']:raise RuntimeRefused('REPLAY_INPUT_DENIED')
                            api.set_inheritable(input_handle,True);inherited+=(input_handle.value,)
                            command=[sys.executable,'-B','-m','compertum.runtime.replay_worker',str(input_handle.value),str(native),
                                str(input_artifact['size_bytes']),input_artifact['sha256'],str(unit),str(writer.grant.maximum)]
                            if argv[1] in {'campaign','audit'}:
                                if dependency_artifact is not None:
                                    dependency_path=checked_path(guard.project.root_path,guard.project.root_path/dependency_artifact['path'])
                                    dependency_stream=dependency_path.open('rb');dependency_handle=OwnedHandle(api,msvcrt.get_osfhandle(dependency_stream.fileno()))
                                    if os.fstat(dependency_stream.fileno()).st_size!=dependency_artifact['size_bytes']:raise RuntimeRefused('CAMPAIGN_INPUT_DENIED')
                                    api.set_inheritable(dependency_handle,True);inherited+=(dependency_handle.value,)
                                command[3]='compertum.runtime.campaign_worker'
                                command.extend([str(dependency_handle.value if dependency_handle else 0),str(dependency_artifact['size_bytes'] if dependency_artifact else 0),
                                    dependency_artifact['sha256'] if dependency_artifact else '-',dependency_sha256 or '-'])
                                if argv[1]=='audit':
                                    if fit_artifact is not None:
                                        fit_path=checked_path(guard.project.root_path,guard.project.root_path/fit_artifact['path'])
                                        fit_stream=fit_path.open('rb');fit_handle=OwnedHandle(api,msvcrt.get_osfhandle(fit_stream.fileno()))
                                        if os.fstat(fit_stream.fileno()).st_size!=fit_artifact['size_bytes']:raise RuntimeRefused('AUDITOR_INPUT_DENIED')
                                        api.set_inheritable(fit_handle,True);inherited+=(fit_handle.value,)
                                    command[3]='compertum.runtime.audit_worker';command.pop()
                                    command.extend([str(fit_handle.value if fit_handle else 0),str(fit_artifact['size_bytes'] if fit_artifact else 0),fit_artifact['sha256'] if fit_artifact else '-',dependency_sha256 or '-',payload['task_id']])
                        else:command=[*command[:-1],str(native),str(writer.grant.maximum),str(offset)]
                        if argv[1]=='final_audit':info=create_suspended(api,command,env,output.parent,inherited,on_created=lambda info:adopt_child(handle,info))
                        else:info=create_suspended(api,command,env,output.parent,inherited)
                        # Final auditor ownership predates attribute/inheritance cleanup.
                        if argv[1]=='final_audit':process=handle.process;thread=handle.audit_lifetime.thread
                        else:process=OwnedHandle(api,info.process);thread=OwnedHandle(api,info.thread)
                    finally:
                        cleanup_errors=[]
                        for borrowed_handle in (borrowed,input_handle,dependency_handle,fit_handle,*review_handles):
                            if borrowed_handle is not None:
                                try:api.set_inheritable(borrowed_handle,False)
                                except BaseException as error:cleanup_errors.append(error)
                        for stream in (input_stream,dependency_stream,fit_stream,*review_streams):
                            if stream is not None:
                                try:stream.close()
                                except BaseException as error:cleanup_errors.append(error)
                        if cleanup_errors:raise cleanup_errors[0]
            else:
                info=create_suspended(api,command,env,output.parent)
                process=OwnedHandle(api,info.process);thread=OwnedHandle(api,info.thread)
            api.assign(job,process)
            if argv[1]=='final_audit':handle.audit_lifetime.assigned=True
            from .ipc import _remember_worker
            from .bootstrap import _observation
            observation=_observation(api,process);_remember_worker(observation)
            require_live_owner(lease)
            if time.monotonic()>=deadline:raise RuntimeRefused('TASK_DEADLINE_EXCEEDED')
            if argv[1]!='final_audit':handle=JobHandle(api,lease,job,process,info.pid,deadline,limits)
            if argv[1] in {'campaign','audit','scorecard','aggregate','pair_compare','final','final_audit'}:
                from .job_identity import capture_execution_identity
                handle._execution_identity_raw=json.dumps(capture_execution_identity(observation,payload,'compertum.runtime.campaign_worker' if argv[1] in {'campaign','scorecard','final'} else 'compertum.runtime.audit_worker',startup=startup_binding.observe(process),clean_environment=clean_expectation,auditor_environment=auditor_expectation),sort_keys=True)
                handle.started=campaign_started
            if argv[1]=='final_audit':
                handle.audit_lifetime.identity_captured=True
                final_audits.bind_native(final_audit_request,handle.execution_identity)
                handle.audit_lifetime.durably_bound=True
            handle.startup_evidence=startup_binding.observe(process);handle._startup_plan_raw=startup_binding.raw
            handle.start_monitor()
            if argv[1]=='campaign':
                before_resume(handle.execution_identity)
                require_live_owner(lease)
                from compertum.simulation.campaign_runs import verify_native_admission
                verify_native_admission(budget_store,lease.identity.process_instance_id,payload['task_id'],unit,input_artifact,
                    dependency_artifact,dependency_sha256,output.relative_to(guard.project.root_path).as_posix(),writer.grant.grant_id,execution_identity=handle.execution_identity)
                if time.monotonic()>=deadline:raise RuntimeRefused('TASK_DEADLINE_EXCEEDED')
            if argv[1]=='audit':
                before_resume(handle.execution_identity);require_live_owner(lease)
                audits.verify_launch(audit_request,payload,writer.grant.grant_id,execution_identity=handle.execution_identity)
                if time.monotonic()>=deadline:raise RuntimeRefused('TASK_DEADLINE_EXCEEDED')
            if argv[1] in {'scorecard','aggregate','pair_compare'}:
                before_resume(handle.execution_identity);require_live_owner(lease)
                # Refresh before the final seal/input check so refresh cannot open a revocation gap.
                before_execute(refresh=True)
                reviews.verify_launch(review_request,payload,writer.grant.grant_id,execution_identity=handle.execution_identity)
                if time.monotonic()>=deadline:raise RuntimeRefused('TASK_DEADLINE_EXCEEDED')
            if argv[1]=='final':
                before_resume(handle.execution_identity);require_live_owner(lease)
                final_runs.verify_launch(final_request,payload,writer.grant.grant_id,execution_identity=handle.execution_identity)
                if time.monotonic()>=deadline:raise RuntimeRefused('TASK_DEADLINE_EXCEEDED')
            if argv[1]=='final_audit':
                before_resume(handle.execution_identity);require_live_owner(lease)
                final_audits.verify_launch(final_audit_request,payload,writer.grant.grant_id,execution_identity=handle.execution_identity)
            if startup_binding.before_resume(process)!=handle.startup_evidence:raise RuntimeRefused('STARTUP_IMAGE_UNVERIFIED')
            if argv[1] in {'scorecard','aggregate','pair_compare'}:
                before_execute();require_live_owner(lease)
            if time.monotonic()>=deadline:raise RuntimeRefused('TASK_DEADLINE_EXCEEDED')
            if argv[1]=='final_audit':handle.audit_lifetime.resume_attempted=True
            if api.ResumeThread(thread.get())!=1: raise RuntimeRefused('RESUME_UNVERIFIED')
            if argv[1]=='final_audit':return handle
            thread.close(); thread=None
            startup_binding.close();startup_binding=None
            handle.budget_store=budget_store;handle.budget_id=budget_id;_ACTIVE[lease.project_id]=handle
            guard.resources.append(handle)
            return handle
        except BaseException:
            if argv[1]=='final_audit':raise
            cleanup_errors=[]
            if process is not None:
                try:
                    api.TerminateProcess(process.get(),125)
                    if api.WaitForSingleObject(process.get(),3000)!=0:raise RuntimeRefused('JOB_EXIT_UNVERIFIED')
                except BaseException as error:cleanup_errors.append(error)
            if 'handle' in locals():
                try:handle._stop_monitor()
                except BaseException as error:cleanup_errors.append(error)
            for owned_handle in (process,thread,job):
                if owned_handle is not None:
                    try:owned_handle.close()
                    except BaseException as error:cleanup_errors.append(error)
            if cleanup_errors:raise cleanup_errors[0]
            raise
        finally:
            if startup_binding is not None and argv[1]!='final_audit':startup_binding.close()


def create_suspended(api,argv,env,cwd,inherited=(),*,on_created=None):
    """Create a child with only explicitly supplied handles, before any code runs."""
    class ExtendedStartup(c.Structure):
        _fields_=[('base',Startup),('attributes',HANDLE)]
    block=c.create_unicode_buffer('\0'.join(f'{k}={v}' for k,v in sorted(env.items()))+'\0\0')
    command=c.create_unicode_buffer(subprocess.list2cmdline(argv));info=ProcessInfo()
    application=json.loads(env['COMPERTUM_STARTUP'])['base_executable'] if 'COMPERTUM_STARTUP' in env else sys._base_executable
    if not inherited:
        startup=Startup();startup.size=c.sizeof(startup)
        api.checked(api.CreateProcessW(application,command,None,None,False,0x4|0x400|0x08000000,
            block,str(cwd),c.byref(startup),c.byref(info)),'CreateProcessW')
        if on_created is not None:on_created(info)
        return info
    kernel=c.WinDLL('kernel32',use_last_error=True)
    init=kernel.InitializeProcThreadAttributeList;init.argtypes=[HANDLE,DWORD,DWORD,c.POINTER(SIZE)];init.restype=BOOL
    update=kernel.UpdateProcThreadAttribute;update.argtypes=[HANDLE,DWORD,SIZE,HANDLE,SIZE,HANDLE,HANDLE];update.restype=BOOL
    delete=kernel.DeleteProcThreadAttributeList;delete.argtypes=[HANDLE];delete.restype=None
    size=SIZE();init(None,1,0,c.byref(size));attributes=c.create_string_buffer(size.value)
    api.checked(init(attributes,1,0,c.byref(size)),'InitializeProcThreadAttributeList')
    try:
        handles=(HANDLE*len(inherited))(*inherited)
        api.checked(update(attributes,0,0x20002,handles,c.sizeof(handles),None,None),'ExplicitHandleList')
        startup=ExtendedStartup();startup.base.size=c.sizeof(startup);startup.attributes=c.cast(attributes,HANDLE)
        api.checked(api.CreateProcessW(application,command,None,None,True,0x4|0x400|0x08000000|0x80000,
            block,str(cwd),c.cast(c.byref(startup),c.POINTER(Startup)),c.byref(info)),'CreateProcessW')
        if on_created is not None:on_created(info)
        return info
    finally: delete(attributes)


