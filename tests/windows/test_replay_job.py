import hashlib,json,time
import pytest
from test_persistence import owned
from test_saved_runs import setup_run,control
from compertum.foundation import fixture_spec
from compertum.domain import TaskSpec
from compertum.runtime.jobs import launch_bounded
from compertum.runtime.errors import RuntimeRefused
from compertum.storage import adopt_fixture_bytes
from compertum.simulation import replay
from helpers.simulation_fixture import SECTORS


def specification(root,run,artifact):
    value=fixture_spec(root,run).to_payload()
    value['input_hashes']=[artifact['sha256']]
    value['permissions']['filesystem_bundle']=[artifact['path']]
    value['permissions']['output_directory']=f'artifacts/runs/{run}/baseline'
    value['budget'].update(cpu_threads=4,ram_bytes=4*1024**3,output_bytes=16*1024**2)
    return TaskSpec(value,project_root=root)


def test_native_replay_job_exact_bytes_and_limits(owned):
    storage,runs,run,(chunks,start,end),created=setup_run(owned)
    control(runs,run,'resume');admitted=runs.begin(run)
    grant=storage.reserve_bytes(run,'records',16*1024**2)
    writer=storage.open_artifact(grant,f'artifacts/runs/{run}/baseline/unit-00-attempt-1.replay')
    job=None
    try:
        task=specification(storage.root,run,admitted['input_artifact'])
        job=launch_bounded(storage.lease,task,['fixture','replay',str(writer.destination)],writer=writer,
            input_artifact=admitted['input_artifact'],unit=0)
        receipt=job.wait()
        assert receipt['exit_code']==0 and receipt['assigned_before_resume'] and receipt['active_processes']==0
        assert receipt['memory_limit']==4*1024**3 and receipt['affinity'].bit_count()<=4
        adopt_fixture_bytes(writer,job);artifact=writer.publish()
        from compertum.simulation.worker_record import verify_result
        assert verify_result((storage.root/artifact['path']).read_bytes(),admitted['request_sha256'],1,10)==replay(chunks,SECTORS,start,end,1).content
        assert runs.accept(run,artifact)['completed_units']==1
        (storage.root/'job-receipt.json').write_text(json.dumps(receipt))
    finally:
        if job:job.close()
        writer.close()


def test_replay_sink_cannot_exceed_task_output_budget(owned):
    storage,runs,run,args,created=setup_run(owned)
    grant=storage.reserve_bytes(run,'records',16*1024**2)
    writer=storage.open_artifact(grant,f'artifacts/runs/{run}/baseline/test.replay')
    payload=specification(storage.root,run,created['input_artifact']).to_payload();payload['budget']['output_bytes']=4096
    job=None
    try:
        with pytest.raises(RuntimeRefused,match='REPLAY_INPUT_DENIED'):
            job=launch_bounded(storage.lease,TaskSpec(payload,project_root=storage.root),['fixture','replay',str(writer.destination)],
                writer=writer,input_artifact=created['input_artifact'],unit=0)
    finally:
        if job:job.close()
        writer.close()


def test_worker_refuses_changed_input_without_output(owned):
    storage,runs,run,args,created=setup_run(owned)
    artifact={**created['input_artifact'],'sha256':'f'*64}
    writer=storage.open_artifact(storage.reserve_bytes(run,'records',16*1024**2),f'artifacts/runs/{run}/baseline/corrupt.replay')
    job=None
    try:
        job=launch_bounded(storage.lease,specification(storage.root,run,artifact),['fixture','replay',str(writer.destination)],
            writer=writer,input_artifact=artifact,unit=0)
        assert job.wait()['exit_code']==4
        assert adopt_fixture_bytes(writer,job)==0
    finally:
        if job:job.close()
        writer.close()


@pytest.mark.parametrize('outcome',['timely','timeout','timeout_exit_race'])
def test_late_supervisor_tick_uses_native_exit_evidence(owned,monkeypatch,outcome):
    from types import SimpleNamespace
    from compertum.research import ResearchController
    storage,runs,run,args,created=setup_run(owned)
    controller=ResearchController(SimpleNamespace(status=lambda:{'research_state':'RUNNING'},require_health=lambda:None),storage)
    control(controller.runs,run,'resume')
    controller.step(run)
    job=controller.active[2]
    try:
        if outcome=='timeout':job.deadline=time.monotonic()-.001
        assert job.api.WaitForSingleObject(job.process.get(),10000)==0
        until=time.monotonic()+1
        while job.ended is None and time.monotonic()<until:time.sleep(.01)
        assert job.ended is not None and job.timed_out==(outcome=='timeout')
        if outcome=='timeout_exit_race':
            receipt=job.wait();assert receipt['exit_code']==0
            monkeypatch.setattr(job,'wait',lambda:{**receipt,'timed_out':True})
        # Model returning from a slow control RPC after an on-time native exit.
        job.deadline=time.monotonic()-.001
        controller.tick()
        state=controller.runs.summary(run)
        if outcome=='timely':
            assert state['state']=='READY' and state['completed_units']==1
            assert state['attempts'][0]['job_receipt']['timed_out'] is False
        else:
            assert state['state']=='FAILED' and state['completed_units']==0
            assert state['attempts'][0]['reason']=='JOB_TIMEOUT'
            assert state['attempts'][0]['job_receipt']['timed_out'] is True
    finally:
        controller.pause()
