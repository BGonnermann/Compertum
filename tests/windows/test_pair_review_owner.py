"""Native ledger durability with explicit stub evidence; no paired run acceptance."""
from copy import deepcopy
from uuid import uuid4
import pytest
from test_native_seals import state
from test_pair_review import packet,pair_inputs,environment
from compertum.data.encoding import canonical
from compertum.data.errors import DataError
from compertum.review_bundle import build_bundle
from compertum.review_runs import ReviewRuns
from compertum.review_evidence import sha


def setup(state,pair_inputs,monkeypatch):
    reviews=ReviewRuns(state[2]);request,meta,_=packet(pair_inputs);raw=build_bundle(**request)
    source={**meta['lanes'][0], 'identity':request['identity']}
    context=dict(source=source,metadata=request['metadata'],records=request['records'],exports=[],plan=[],registration_sha256=sha(raw),raw=raw,native=[])
    monkeypatch.setattr(reviews,'_registration',lambda *args:deepcopy(context))
    monkeypatch.setattr('compertum.review_runs.expected_environment',lambda *args:meta['lanes'][0]['clean_environment'])
    return reviews,request,context


def test_pair_attempt_exhaustion_keeps_single_registration_and_no_exports(state,pair_inputs,monkeypatch):
    reviews,request,context=setup(state,pair_inputs,monkeypatch);task=request['task_id'];run=request['source_run_id']
    s=reviews.register(task,run,'pair_compare');assert s['state']=='READY' and s['preparation_artifacts']==[]
    assert s['request_sha256']==s['registration_sha256']==sha(context['raw'])
    assert reviews.register(task,run,'pair_compare')==s
    for number in (1,2):
        prepared=reviews.prepare(task);assert prepared['number']==number
        result=reviews.interrupt(task,'LAUNCH_RETRYABLE',retry=True)
        assert result['state']==('INTERRUPTED' if number==1 else 'FAILED')
        if number==1:reviews.resume(task)
    with pytest.raises(DataError):reviews.resume(task)
    with pytest.raises(DataError):reviews.register(str(uuid4()),run,'pair_compare')
    restored=ReviewRuns(state[2]).status(task);assert restored==reviews.status(task) and len(restored['attempts'])==2


@pytest.mark.parametrize('boundary',['prepare','bind_task','verify_launch','begin','resume','accept','completed'])
def test_pair_revalidates_dependencies_at_each_authority_boundary(state,pair_inputs,monkeypatch,boundary):
    reviews,request,context=setup(state,pair_inputs,monkeypatch);task=request['task_id'];run=request['source_run_id'];s=reviews.register(task,run,'pair_compare')
    # Dependency invalidation is injected; the real current() must propagate it.
    def revoked(*args):raise DataError('SEAL_INVALIDATED')
    monkeypatch.setattr(reviews,'_registration',revoked)
    if boundary in ('accept','completed'):
        # No native completion claim: isolate refusal before output acceptance.
        s.update(state='RUNNING' if boundary=='accept' else 'COMPLETED');monkeypatch.setattr(reviews,'_load',lambda *args:deepcopy(s))
    calls={'prepare':lambda:reviews.prepare(task),'bind_task':lambda:reviews.bind_task({'task_id':task},{}),'verify_launch':lambda:reviews.verify_launch({'task_id':task},{},str(uuid4())),
        'begin':lambda:reviews.begin({'task_id':task},{},str(uuid4()),{}),'resume':lambda:reviews.resume(task),'accept':lambda:reviews.accept(task,{}),'completed':lambda:reviews.completed(task)}
    with pytest.raises(DataError,match='SEAL_INVALIDATED'):calls[boundary]()
