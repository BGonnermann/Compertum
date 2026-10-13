"""Pair validation reuses only one call's checked context; no native authority."""
from collections import Counter
from contextlib import nullcontext
from copy import deepcopy
from types import SimpleNamespace
import json,sqlite3
import pytest
from test_pair_review import packet,pair_inputs,environment
from compertum.clean_pair import build_pair
from compertum.data.encoding import canonical
from compertum.data.errors import DataError
from compertum.review_evidence import sha
from compertum.review_runs import ReviewRuns
from compertum.pair_review import registration


@pytest.fixture
def validation(pair_inputs,monkeypatch):
    request,meta,_=packet(pair_inputs);pair=build_pair(**pair_inputs[0])
    db=sqlite3.connect(':memory:')
    db.executescript('CREATE TABLE campaign_reviews(task_id,source_run_id,kind); CREATE TABLE campaign_review_history(task_id,seq,body,sha256,previous_sha256);')
    reviews=ReviewRuns.__new__(ReviewRuns)
    reviews.store=SimpleNamespace(conn=db,_live=lambda:nullcontext(SimpleNamespace(project=None)))
    states={};contexts={};counts=Counter();seals=[];output_fault=[None]
    for lane in meta['lanes']:
        a=deepcopy(lane['aggregate']);task=a['task_id'];run=lane['run_id'];raw=canonical({'task':task})
        s=dict(a,source_run_id=run,kind='aggregate',identity=request['identity'],state='COMPLETED',request_sha256=sha(raw),attempts=[dict(native_execution=a['native_execution'],job_receipt=a['job_receipt'])])
        source=dict(run_id=run,identity=request['identity'],protocol_seal=lane['protocol_seal'],clean_environment=lane['clean_environment'],input_artifact=lane['input_artifact'],attempts=[])
        context=dict(source=source,metadata=canonical(dict(final_state='{}',history=[],controls=[])),native=[],raw=raw)
        states[task]=s;contexts[task]=context;db.execute('INSERT INTO campaign_reviews VALUES(?,?,?)',(task,run,'aggregate'))
    def context(kind,task,run):
        assert kind=='aggregate' and states[task]['source_run_id']==run
        counts[task]+=1
        seal(reviews.store,contexts[task]['source'])
        return deepcopy(contexts[task])
    def output(s,artifact):
        if output_fault[0] is not None:output_fault[0](s)
        assert artifact==s['artifact']
        return dict(payload_sha256=s['payload_sha256'],payload_bytes=s['payload_bytes'])
    def seal(store,source):
        seals.append(source['run_id'])
        if source['run_id'] in revoked:raise DataError('SEAL_INVALIDATED')
        return source['protocol_seal']
    revoked=set()
    monkeypatch.setattr(reviews,'_load',lambda task:deepcopy(states[task]))
    monkeypatch.setattr(reviews,'_registration',context)
    monkeypatch.setattr(reviews,'bundle',lambda s:(dict(protocol_seal=contexts[s['task_id']]['source']['protocol_seal']),contexts[s['task_id']]['metadata']))
    monkeypatch.setattr(reviews,'_prepared_request',lambda s,c:c['raw'])
    monkeypatch.setattr(reviews,'_output',output)
    monkeypatch.setattr('compertum.review_runs.expected_environment',lambda store,run:next(l['clean_environment'] for l in meta['lanes'] if l['run_id']==run))
    monkeypatch.setattr('compertum.clean_registration.member_registration',lambda *a,**k:(pair,'source'))
    monkeypatch.setattr('compertum.development_seals.check_campaign_seal',seal)
    try:yield SimpleNamespace(reviews=reviews,request=request,states=states,contexts=contexts,counts=counts,seals=seals,revoked=revoked,output_fault=output_fault)
    finally:db.close()


def evaluate(v):return registration(v.reviews,v.request['task_id'],v.request['source_run_id'])


def test_pair_validates_each_aggregate_once_without_cross_call_cache(validation):
    v=validation;first=evaluate(v)
    assert v.counts==Counter({task:1 for task in v.states})
    assert v.seals==[c['source']['run_id'] for c in v.contexts.values() for _ in range(2)]
    assert evaluate(v)==first
    assert v.counts==Counter({task:2 for task in v.states})
    # A later call must observe changed committed request evidence.
    task=next(iter(v.states));v.contexts[task]['raw']+=b'changed'
    with pytest.raises(DataError):evaluate(v)


@pytest.mark.parametrize('lane',[0,1])
def test_pair_rechecks_seal_after_aggregate_output_verification(validation,lane):
    v=validation;task=list(v.states)[lane];run=v.states[task]['source_run_id']
    def revoke(s):
        if s['task_id']==task:v.revoked.add(run)
    v.output_fault[0]=revoke
    with pytest.raises(DataError,match='SEAL_INVALIDATED'):evaluate(v)
    assert run in v.seals


def test_completed_context_keeps_public_result_and_output_refusal(validation):
    v=validation;task=next(iter(v.states))
    assert v.reviews.completed(task)==v.states[task]
    s,context=v.reviews._completed_with_context(task)
    assert s==v.states[task] and context==v.contexts[task]
    def corrupt(s):raise DataError('REVIEW_EVIDENCE_UNVERIFIED')
    v.output_fault[0]=corrupt
    with pytest.raises(DataError):v.reviews._completed_with_context(task)
    with pytest.raises(DataError):v.reviews.completed(task)
