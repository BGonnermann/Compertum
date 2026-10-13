"""Aggregate native refusal at the child and current-authority boundaries."""
from uuid import uuid4
import pytest
from test_native_seals import state
from test_native_aggregate_registration import evidence
from test_native_development_seals import invalidate
from compertum.data.errors import DataError
from compertum.runtime.errors import RuntimeRefused


@pytest.mark.parametrize('kind',['frame','unit_audit','scorecard'])
def test_actual_aggregate_worker_rejects_changed_inherited_evidence(state,monkeypatch,kind):
    controller,run,review,card=evidence(state);task=str(uuid4());review.runs.register(task,run,'aggregate')
    header,_=review.runs.bundle(review.runs.status(task));artifact=next(r['artifact'] for r in header['records'] if r['kind']==kind)
    path=controller.storage.root/artifact['path'];raw=path.read_bytes()
    import compertum.runtime.jobs as jobs
    factory=jobs.JobAPI;changed=[]
    def make_api():
        api=factory();resume=api.ResumeThread
        def changed_at_resume(handle):
            # Last coordinator recheck has passed; exercise the actual child.
            with path.open('r+b') as stream:stream.seek(len(raw)-1);stream.write(b' ' if raw[-1:]!=b' ' else b'X');stream.flush()
            changed.append(True);return resume(handle)
        api.ResumeThread=changed_at_resume;return api
    monkeypatch.setattr(jobs,'JobAPI',make_api)
    try:
        review.step(task);receipt=review.active[2].wait();assert receipt['exit_code']==6 and changed==[True]
        review.tick();s=review.runs.status(task);assert s['state']=='BLOCKED' and s['artifact'] is None and len(s['attempts'])==1
        assert s['attempts'][-1]['reason']=='REVIEW_REJECTED'
        with pytest.raises(DataError):review.runs.resume(task)
    finally:review.pause();controller.pause()


@pytest.mark.parametrize('boundary',['prepare','resume','accept','reuse'])
def test_aggregate_rechecks_revoked_seal_at_every_boundary(state,monkeypatch,boundary):
    controller,run,review,card,seal,remote=evidence(state,with_authority=True);task=str(uuid4());review.runs.register(task,run,'aggregate')
    try:
        if boundary=='prepare':
            invalidate(state,remote,seal)
            with pytest.raises((DataError,RuntimeRefused),match='SEAL_INVALIDATED'):review.step(task)
        elif boundary=='resume':
            begin=review.runs.begin
            def changed(*args,**kwargs):
                result=begin(*args,**kwargs);invalidate(state,remote,seal);return result
            monkeypatch.setattr(review.runs,'begin',changed)
            with pytest.raises((DataError,RuntimeRefused),match='SEAL_INVALIDATED'):review.step(task)
            assert review.active is None and review.runs.status(task)['state']=='BLOCKED'
        else:
            review.step(task);assert review.active[2].wait()['exit_code']==0
            if boundary=='accept':invalidate(state,remote,seal)
            review.tick()
            if boundary=='accept':assert review.runs.status(task)['state']=='BLOCKED'
            else:
                assert review.runs.status(task)['state']=='COMPLETED';invalidate(state,remote,seal)
                with pytest.raises((DataError,RuntimeRefused),match='SEAL_INVALIDATED'):review.step(task)
    finally:review.pause();controller.pause()


def test_aggregate_changed_worker_output_is_preserved_but_never_accepted(state):
    controller,run,review,card=evidence(state);task=str(uuid4());review.runs.register(task,run,'aggregate')
    try:
        review.step(task);assert review.active[2].wait()['exit_code']==0
        path=review.active[1].path;raw=path.read_bytes()
        with path.open('r+b') as stream:stream.seek(len(raw)-1);stream.write(b' ');stream.flush()
        review.tick();s=review.runs.status(task)
        assert s['state']=='BLOCKED' and s['artifact'] is None and s['attempts'][-1]['reason']=='REVIEW_ACCEPTANCE_FAILED'
        assert (controller.storage.root/s['attempts'][-1]['output_path']).exists()
        with pytest.raises(DataError):review.runs.resume(task)
    finally:review.pause();controller.pause()
