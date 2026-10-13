"""Pure bounded ticket contracts; no committed evidence or freeze authority."""
from copy import deepcopy
import json
from uuid import uuid4
import pytest
from test_pair_review import packet,pair_inputs,environment,sha,artifact
from compertum.data.encoding import canonical
from compertum.data.errors import DataError
from compertum.runtime import campaign_review_worker as worker
from compertum.review_bundle import build_bundle
from compertum.shortlist_ticket import build_ticket,read_ticket


def inputs(pair_inputs,monkeypatch):
    request,meta,contents=packet(pair_inputs);monkeypatch.setattr(worker,'runtime_identity',lambda:request['identity']);raw=build_bundle(**request)
    frame=worker.pair_compare(raw,sha(raw),request['task_id'],request['source_run_id'],lambda i,a:contents[i]);comparison=frame.split(b'\n',1)[1];v=json.loads(comparison)
    def pin(task,kind,run,content,payload_pin=None,payload_bytes=None):
        return dict(task_id=task,kind=kind,source_run_id=run,state_sha256='a'*64,history_sha256='b'*64,request_sha256='c'*64,artifact=artifact(task,f'artifacts/runs/{task}/review/{kind}-attempt-1.review',content),payload_sha256=payload_pin or sha(content.split(b'\n',1)[1]),payload_bytes=payload_bytes or len(content.split(b'\n',1)[1]))
    reviews=dict(scorecard=pin(str(uuid4()),'scorecard',request['source_run_id'],b'header\ncard',v['scorecard_sha256'],4),comparison=pin(request['task_id'],'pair_compare',request['source_run_id'],frame))
    for i,lane in enumerate(meta['lanes'],1):reviews[lane['lane']+'_aggregate']=pin(lane['aggregate']['task_id'],'aggregate',lane['run_id'],contents[i])
    return dict(project_id=meta['pair']['project_id'],pair=meta['pair'],pair_sha256=meta['pair_sha256'],protocol_sha256={lane['lane']:lane['protocol_seal']['protocol_sha256'] for lane in meta['lanes']},reviews=reviews,comparison=comparison)


def test_ticket_reproduces_exact_compact_worker_selection(pair_inputs,monkeypatch):
    args=inputs(pair_inputs,monkeypatch);ticket=build_ticket(**args);v=read_ticket(ticket.content,expected_sha256=ticket.sha256,comparison=args['comparison'])
    assert build_ticket(**args)==ticket and len(ticket.content)<=24*1024
    assert read_ticket(ticket.content,expected_sha256=ticket.sha256)==v
    assert len(v['comparison']['selection_projection']['dispositions'])==12 and len(v['comparison']['selection_projection']['evaluation_slots'])==36 and v['financial_accepted'] is False


@pytest.mark.parametrize('fault',['project','pair','missing_review','same_task','wheel_anchor','path','payload','card','aggregate','boolean','protocol','unmatched_comparison'])
def test_ticket_refuses_unmatched_or_relabelled_evidence(pair_inputs,monkeypatch,fault):
    args=inputs(pair_inputs,monkeypatch);r=args['reviews']
    if fault=='project':args['project_id']='f'*64
    elif fault=='pair':args['pair_sha256']='f'*64
    elif fault=='missing_review':r.pop('wheel_aggregate')
    elif fault=='same_task':r['scorecard']['task_id']=r['comparison']['task_id']
    elif fault=='wheel_anchor':r['comparison']['source_run_id']=args['pair']['wheel']['run_id']
    elif fault=='path':r['comparison']['artifact']['path']=r['comparison']['artifact']['path'].replace('attempt-1','attempt-3')
    elif fault=='payload':r['comparison']['payload_sha256']='f'*64
    elif fault=='card':r['scorecard']['payload_sha256']='f'*64
    elif fault=='aggregate':r['wheel_aggregate']['payload_sha256']='f'*64
    elif fault=='boolean':r['comparison']['payload_bytes']=True
    elif fault=='protocol':args['protocol_sha256']['wheel']='invalid'
    else:args['comparison']+=b' '
    with pytest.raises(DataError):build_ticket(**args)


@pytest.mark.parametrize('fault',['selection','scope','extra','oversize'])
def test_rehashed_ticket_cannot_change_the_selection(pair_inputs,monkeypatch,fault):
    args=inputs(pair_inputs,monkeypatch);ticket=build_ticket(**args);v=json.loads(ticket.content)
    if fault=='selection':v['comparison']['selection_projection']['selected']=[]
    elif fault=='scope':v['financial_accepted']=True
    elif fault=='extra':v['authority']=True
    else:v['padding']='x'*(24*1024)
    raw=canonical(v)
    with pytest.raises(DataError):read_ticket(raw,expected_sha256=sha(raw),comparison=args['comparison'])
