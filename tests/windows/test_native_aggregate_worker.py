"""Whole-campaign audit runs in a separate bounded native process."""
import hashlib,json,os
from uuid import uuid4
from test_native_seals import state
from test_native_aggregate_registration import evidence


def test_native_aggregate_reconciles_original_evidence_and_retains_failures(state,monkeypatch):
    controller,run,review,card=evidence(state);task=str(uuid4())
    import ctypes as c
    import compertum.runtime.jobs as jobs
    from compertum.runtime._windows import DWORD
    create=jobs.create_suspended;seen=[]
    def inspect(api,argv,env,cwd,inherited=()):
        if argv[3]=='compertum.runtime.audit_worker' and argv[4]=='aggregate':
            for h in inherited[1:]:
                count=DWORD();buf=c.create_string_buffer(b'X')
                assert not api.WriteFile(h,buf,1,c.byref(count),None) and c.get_last_error()==5
            seen.append(len(inherited)-1)
        return create(api,argv,env,cwd,inherited)
    monkeypatch.setattr(jobs,'create_suspended',inspect)
    try:
        review.runs.register(task,run,'aggregate');review.step(task)
        job=review.active[2];limits=job.api.limits(job.job)
        assert limits.basic.active_limit==1 and limits.process_memory==limits.job_memory==4*1024**3
        assert limits.basic.affinity.bit_count()==4
        receipt=job.wait();assert receipt['exit_code']==0
        review.tick();s=review.runs.completed(task);assert s['state']=='COMPLETED' and seen==[6]
        raw=(controller.storage.root/s['artifact']['path']).read_bytes();header,payload=raw.split(b'\n',1);result=json.loads(payload)
        assert result['status']=='VERIFIED_PASS' and result['financial_accepted'] is False and result['full_M3'] is False and result['shortlist']==[]
        assert result['required_unit_audits']==len(result['unit_audits'])==1
        assert result['history_audit']['status']=='VERIFIED_PASS'
        from compertum.campaign_comparison import compare_indices
        comparison=compare_indices(result['comparison_index'],result['comparison_index'])
        assert comparison['unit_counts']['COMPLETED']==1 and comparison['unit_counts']['FAILED']+comparison['unit_counts']['SKIPPED']==62
        assert result['scorecard_sha256']==review.runs.completed(card)['payload_sha256']
        assert s['payload_sha256']==hashlib.sha256(payload).hexdigest() and json.loads(header)['worker_pid']==receipt['pid']!=os.getpid()
        assert s['attempts'][-1]['native_execution']==receipt['execution_identity']
        source=controller.runs.status(run);assert source['completed_units']==1 and source['failed_units']+source['skipped_units']==62
        assert review.step(task)==s and review.active is None
    finally:review.pause();controller.pause()
