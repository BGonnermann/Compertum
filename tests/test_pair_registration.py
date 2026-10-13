"""Pair registration dependency tests with explicit in-memory evidence stubs."""
from contextlib import contextmanager
from copy import deepcopy
import json,sqlite3
from types import SimpleNamespace
from uuid import uuid4
import pytest
from test_pair_review import packet,pair_inputs,environment
from compertum.clean_pair import PairRecord
from compertum.data.encoding import canonical
from compertum.data.errors import DataError
from compertum.pair_review import registration


def reviews_fixture(pair_inputs,monkeypatch):
    request,meta,_=packet(pair_inputs);db=sqlite3.connect(':memory:')
    db.executescript('CREATE TABLE campaign_reviews(task_id TEXT,source_run_id TEXT,kind TEXT); CREATE TABLE campaign_review_history(task_id TEXT,seq INTEGER,body TEXT,sha256 TEXT,previous_sha256 TEXT);')
    @contextmanager
    def live():yield SimpleNamespace(project=object())
    store=SimpleNamespace(conn=db,_live=live);reviews=SimpleNamespace(store=store);calls=[];contexts={};aggregates={}
    for lane in meta['lanes']:
        a=lane['aggregate'];task=a['task_id'];run=lane['run_id'];db.execute('INSERT INTO campaign_reviews VALUES(?,?,?)',(task,run,'aggregate'))
        aggregates[task]=dict(task_id=task,request_sha256=a['request_sha256'],artifact=a['artifact'],payload_sha256=a['payload_sha256'],payload_bytes=a['payload_bytes'],attempts=[dict(native_execution=a['native_execution'],job_receipt=a['job_receipt'])])
        source={k:lane[k] for k in ('run_id','protocol_seal','input_artifact','clean_environment')};source.update(identity=request['identity'],attempts=[])
        contexts[task]=dict(source=source,metadata=canonical(dict(final_state=canonical(source).decode(),history=[],controls=[])),native=[])
    def completed(task):calls.append(task);return deepcopy(aggregates[task])
    reviews.completed=completed;reviews._registration=lambda kind,task,run:deepcopy(contexts[task])
    reviews._completed_with_context=lambda task:(reviews.completed(task),deepcopy(contexts[task]))
    import compertum.development_seals as seals
    monkeypatch.setattr(seals,'check_campaign_seal',lambda store,source:source['protocol_seal'])
    import compertum.clean_registration as registry
    monkeypatch.setattr(registry,'member_registration',lambda *a,**kw:(PairRecord(canonical(meta['pair']),meta['pair_sha256']),'source' if a[2]==request['source_run_id'] else 'wheel'))
    return reviews,request,meta,calls,contexts


def test_registration_revalidates_both_committed_aggregates_and_retains_compact_pins(pair_inputs,monkeypatch):
    reviews,request,meta,calls,_=reviews_fixture(pair_inputs,monkeypatch)
    try:
        result=registration(reviews,request['task_id'],request['source_run_id']);v=json.loads(result['metadata'])
        assert calls==[lane['aggregate']['task_id'] for lane in meta['lanes']]
        assert result['exports']==result['plan']==[] and len(result['records'])==3
        assert all('history' not in lane and 'final_state' not in lane for lane in v['lanes'])
        assert len(result['native'])==2 and len(result['raw'])<64*1024
        again=registration(reviews,request['task_id'],request['source_run_id']);assert again['raw']==result['raw']
    finally:reviews.store.conn.close()


@pytest.mark.parametrize('fault',['wheel_anchor','missing','duplicate','source_invalidated','wheel_invalidated','wrong_pair','changed_history','changed_receipt'])
def test_registration_refuses_unavailable_or_changed_lane_evidence(pair_inputs,monkeypatch,fault):
    reviews,request,meta,calls,contexts=reviews_fixture(pair_inputs,monkeypatch)
    try:
        task=request['task_id'];run=request['source_run_id'];before=registration(reviews,task,run)
        wheel=meta['lanes'][1];a=wheel['aggregate']
        if fault=='wheel_anchor':run=wheel['run_id']
        elif fault=='missing':reviews.store.conn.execute('DELETE FROM campaign_reviews WHERE task_id=?',(a['task_id'],))
        elif fault=='duplicate':reviews.store.conn.execute('INSERT INTO campaign_reviews VALUES(?,?,?)',(str(uuid4()),wheel['run_id'],'aggregate'))
        elif fault.endswith('_invalidated'):
            target=meta['lanes'][0 if fault=='source_invalidated' else 1]['aggregate']['task_id'];original=reviews.completed
            def revoked(t):
                if t==target:raise DataError('SEAL_INVALIDATED')
                return original(t)
            reviews.completed=revoked
        elif fault=='wrong_pair':contexts[a['task_id']]['source']['clean_environment']['pair_sha256']='f'*64
        elif fault=='changed_history':contexts[a['task_id']]['metadata']=canonical(dict(final_state='{}',history=[],controls=[]))
        else:
            original=reviews.completed
            def changed(t):
                v=original(t)
                if t==a['task_id']:v['attempts'][0]['job_receipt']['peak_job_memory']+=1
                return v
            reviews.completed=changed
        if fault in ('changed_history','changed_receipt'):
            after=registration(reviews,task,run);assert after['registration_sha256']!=before['registration_sha256']
        else:
            with pytest.raises(DataError):registration(reviews,task,run)
    finally:reviews.store.conn.close()
