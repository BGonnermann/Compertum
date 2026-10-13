"""Retained cleanup support for the existing JobHandle's Final-auditor mode.

No process is launched here. The launcher registers the same JobHandle before
creation; only that handle owns process, thread, Job, startup and writer lifetime.
"""
from copy import deepcopy
from dataclasses import dataclass
import time
from ._windows import OwnedHandle
from .errors import RuntimeRefused


@dataclass
class AuditLifetime:
    prepared: dict
    writer: object
    startup: object=None
    thread: object=None
    child_created: bool=False
    assigned: bool=False
    identity_captured: bool=False
    durably_bound: bool=False
    resume_attempted: bool=False
    exit_verified: bool=False
    cleanup_uncertain: bool=False


def enable(job,prepared,writer,*,startup=None):
    if job.closed or getattr(job,'audit_lifetime',None) is not None or job.process is not None or job.pid is not None:
        raise RuntimeRefused('FINAL_AUDIT_LIFETIME_INVALID')
    job.audit_lifetime=AuditLifetime(deepcopy(prepared),writer,startup)
    return job


def adopt_child(job,info):
    state=job.audit_lifetime
    if job.closed or state.exit_verified or state.cleanup_uncertain or state.child_created or job.process is not None or state.thread is not None:
        raise RuntimeRefused('FINAL_AUDIT_LIFETIME_INVALID')
    # The caller does this immediately after CreateProcess, before fallible cleanup.
    job.process=OwnedHandle(job.api,info.process);state.thread=OwnedHandle(job.api,info.thread)
    job.pid=info.pid;state.child_created=True


def prove_exit(job):
    state=job.audit_lifetime
    if state.cleanup_uncertain:raise RuntimeRefused('FINAL_AUDIT_CLEANUP_UNVERIFIED')
    if state.exit_verified:return
    # Root termination also covers a suspended child whose assignment failed.
    if job.process is not None:
        observed=job.api.WaitForSingleObject(job.process.get(),0)
        if observed==258:job.api.checked(job.api.TerminateProcess(job.process.get(),125),'TerminateFailedAuditProcess')
        elif observed!=0:raise RuntimeRefused('JOB_EXIT_UNVERIFIED')
    if job.api.active(job.job):job.api.checked(job.api.TerminateJobObject(job.job.get(),125),'TerminateFailedAuditJob')
    deadline=time.monotonic()+3
    for handle in ([job.process] if job.process is not None else [])+list(job.children.values()):
        if job.api.WaitForSingleObject(handle.get(),max(0,int((deadline-time.monotonic())*1000)))!=0:raise RuntimeRefused('JOB_EXIT_UNVERIFIED')
    if job.api.active(job.job):raise RuntimeRefused('JOB_EXIT_UNVERIFIED')
    job._stop_monitor();state.exit_verified=True


def close(job):
    """No handle or writer disposal follows an uncertain exit. Close errors poison retry."""
    if job.closed:return
    state=job.audit_lifetime;prove_exit(job)
    handles=[state.thread,*job.children.values(),job.process,job.job]
    try:
        for handle in handles:
            if handle is not None and not handle.closed:handle.close()
        if state.startup is not None:state.startup.close();state.startup=None
    except BaseException:
        # OwnedHandle marks itself closed before checking CloseHandle. Do not
        # retry that numeric handle: its ownership is now indeterminate.
        state.cleanup_uncertain=True
        raise
    job._finish_budget()
    from .jobs import _ACTIVE
    if _ACTIVE.get(job.lease.project_id) is job:_ACTIVE.pop(job.lease.project_id)
    job.closed=True


def closed_unbound(job):
    """Private disposition: allows terminal blocking only, never acceptance/retry."""
    state=job.audit_lifetime
    if not job.closed or not state.exit_verified or state.cleanup_uncertain or state.durably_bound or state.resume_attempted:
        raise RuntimeRefused('FINAL_AUDIT_CLEANUP_UNVERIFIED')
    p=state.prepared
    return dict(schema='closed-unbound-final-audit-v1',task_id=p['task_id'],number=p['number'],reservation_id=p['reservation_id'],child_created=state.child_created,pid=job.pid if state.child_created else None,assigned=state.assigned,process_exit_observed=state.child_created,job_active_processes=0,result_usable=False,retry_allowed=False)


@dataclass
class AuditLaunch:
    prepared: dict
    writer: object
    job: object=None


class AuditLaunchFailed(RuntimeRefused):
    def __init__(self,launch):
        super().__init__('FINAL_AUDIT_LAUNCH_FAILED')
        self.launch=launch


def no_child_disposition(launch):
    if launch.job is not None:raise RuntimeRefused('FINAL_AUDIT_CLEANUP_UNVERIFIED')
    p=launch.prepared
    return dict(schema='closed-unbound-final-audit-v1',task_id=p['task_id'],number=p['number'],reservation_id=p['reservation_id'],child_created=False,pid=None,assigned=False,process_exit_observed=False,job_active_processes=0,result_usable=False,retry_allowed=False)
