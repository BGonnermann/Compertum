"""Synthetic pair-review contracts; these packets grant no owner authority."""
from copy import deepcopy
import hashlib,json
from uuid import uuid4
import pytest
from test_clean_pair import pair_inputs,environment
from test_campaign_comparison import build as index
from compertum.clean_pair import build_pair,attach_environment
from compertum.data.encoding import canonical
from compertum.data.errors import DataError
from compertum.runtime.identity import PeerObservation
from compertum.runtime.job_identity import capture_execution_identity
from compertum.runtime.startup_record import expected_proof
from compertum.runtime.campaign_environment import observed_from_native
from compertum.review_bundle import build_bundle,read_bundle
from compertum.review_frame import result_binding,pack_review


def sha(raw):return hashlib.sha256(raw).hexdigest()


def artifact(task,path,raw):return dict(task_id=task,artifact_id=str(uuid4()),path=path,sha256=sha(raw),size_bytes=len(raw))


def packet(pair_inputs):
    args,math=pair_inputs;pair=build_pair(**args);p=json.loads(pair.content);task=str(uuid4());lanes=[];contents=[]
    for i,lane in enumerate(('source','wheel')):
        run=p[lane]['run_id'];audit=str(uuid4());campaign=attach_environment(math,pair=pair,manifest=args[lane],lane=lane)
        expected=dict(schema='expected-clean-campaign-v1',pair_sha256=pair.sha256,manifest_sha256=p[lane]['manifest_sha256'],lane=lane,run_id=run)
        native=capture_execution_identity(PeerObservation(100+i,123456789+i,'S-1-5-21-1-2-3-1001','S-1-5-5-100-200'),{'task_id':audit,'role':'experiment_auditor','code_sha256':p['runtime']['package_sha256'],'lock_sha256':p['runtime']['lock_sha256']},'compertum.runtime.audit_worker',startup={'image_sha256':'e'*64,'volume_serial':123,'file_id':'f'*32,'plan_sha256':'1'*64},clean_environment=expected)
        receipt=dict(pid=100+i,exit_code=0,timed_out=False,active_processes=0,assigned_before_resume=True,affinity=15,memory_limit=4*1024**3,peak_job_memory=1024**2,observed_child_pids=[],observed_children_exited=True,execution_identity=native)
        body=canonical(dict(schema='synthetic-native-campaign-audit-v1',status='VERIFIED_PASS',scope='HISTORY_AGGREGATE_AND_COMMITTED_UNIT_AUDIT_CONSISTENCY',source_run_id=run,request_sha256='1'*64,scorecard_sha256=index()['scorecard_sha256'],comparison_index=index(),financial_accepted=False,full_M3=False,history_audit=dict(history=dict(final_state_sha256='2'*64,history_sha256='3'*64,controls_sha256='4'*64))))
        raw=pack_review(body,result_binding('aggregate',audit,run,'1'*64,p['runtime'],100+i,startup=expected_proof(native),environment=observed_from_native(native)))
        lanes.append(dict(lane=lane,run_id=run,protocol_seal=dict(seal_id=p[lane]['seal_id'],protocol_sha256='5'*64,ticket_sha256='6'*64,admission_event_sha256='7'*64),input_artifact=artifact(run,f'artifacts/runs/{run}/baseline/inputs.json',campaign),clean_environment=expected,source_state_sha256='2'*64,source_history_sha256='3'*64,source_controls_sha256='4'*64,aggregate=dict(task_id=audit,request_sha256='1'*64,artifact=artifact(audit,f'artifacts/runs/{audit}/review/aggregate-attempt-1.review',raw),payload_sha256=sha(body),payload_bytes=len(body),native_execution=native,job_receipt=receipt,history_sha256='8'*64)))
        contents.append(raw)
        if lane=='source':primary=campaign
    metadata=dict(schema='synthetic-pair-review-metadata-v1',pair=p,pair_sha256=pair.sha256,lanes=lanes)
    records=[dict(kind='campaign',index=None,artifact=lanes[0]['input_artifact'])]+[dict(kind='aggregate',index=i,artifact=l['aggregate']['artifact']) for i,l in enumerate(lanes)]
    request=dict(kind='pair_compare',task_id=task,source_run_id=p['source']['run_id'],identity=p['runtime'],protocol_seal=lanes[0]['protocol_seal'],metadata=canonical(metadata),records=records)
    return request,metadata,[primary,*contents]


def test_pair_bundle_uses_only_four_readonly_inputs(pair_inputs):
    request,meta,contents=packet(pair_inputs);raw=build_bundle(**request)
    header,body=read_bundle(raw,expected_sha256=sha(raw),expected_kind='pair_compare',expected_task_id=request['task_id'],expected_source_run_id=request['source_run_id'],expected_identity=request['identity'])
    assert len(header['records'])+1==4 and json.loads(body)==meta and len(raw)<64*1024


@pytest.mark.parametrize('fault',['swap','pair','run','seal','native_lane','receipt','input','foreign_aggregate','missing','duplicate','legacy_metadata','wheel_anchor','extra','payload_bytes'])
def test_pair_bundle_refuses_mixed_or_unbounded_evidence(pair_inputs,fault):
    request,meta,_=packet(pair_inputs);lane=meta['lanes'][1]
    if fault=='swap':meta['lanes'].reverse()
    elif fault=='pair':meta['pair_sha256']='0'*64
    elif fault=='run':lane['run_id']=str(uuid4())
    elif fault=='seal':lane['protocol_seal']['seal_id']=str(uuid4())
    elif fault=='native_lane':lane['aggregate']['native_execution']['clean_environment']['lane']='source'
    elif fault=='receipt':lane['aggregate']['job_receipt']['exit_code']=5
    elif fault=='input':lane['input_artifact']['task_id']=meta['lanes'][0]['run_id']
    elif fault=='foreign_aggregate':request['records'][2]['artifact']=deepcopy(request['records'][1]['artifact'])
    elif fault=='missing':request['records'].pop()
    elif fault=='duplicate':request['records'].append(deepcopy(request['records'][2]))
    elif fault=='legacy_metadata':meta=dict(final_state='{}',history=[],controls=[])
    elif fault=='wheel_anchor':request['source_run_id']=lane['run_id']
    elif fault=='extra':meta['authority']=True
    else:lane['aggregate']['payload_bytes']=True
    request['metadata']=canonical(meta)
    with pytest.raises(DataError):build_bundle(**request)


def test_pair_worker_compares_math_but_retains_distinct_native_bindings(pair_inputs,monkeypatch):
    from compertum.runtime import campaign_review_worker as worker
    request,meta,contents=packet(pair_inputs);monkeypatch.setattr(worker,'runtime_identity',lambda:request['identity']);raw=build_bundle(**request)
    result=worker.pair_compare(raw,sha(raw),request['task_id'],request['source_run_id'],lambda i,a:contents[i])
    body=json.loads(result.split(b'\n',1)[1]);assert body['status']=='EXACT_MATCH' and body['matched_units']==63
    assert body['pair_sha256']==meta['pair_sha256'] and body['source_run_id']!=body['wheel_run_id']
    assert body['financial_accepted'] is False and body['full_M3'] is False


@pytest.mark.parametrize('fault',['old_aggregate','index','history','native_frame','payload_pin','source_pair'])
def test_pair_worker_refuses_changed_committed_payload(pair_inputs,monkeypatch,fault):
    from compertum.runtime import campaign_review_worker as worker
    request,meta,contents=packet(pair_inputs);monkeypatch.setattr(worker,'runtime_identity',lambda:request['identity'])
    if fault=='source_pair':
        body=json.loads(contents[0]);body['clean_pair']['lane']='wheel';contents[0]=canonical(body);request['records'][0]['artifact']=meta['lanes'][0]['input_artifact']=artifact(request['source_run_id'],request['records'][0]['artifact']['path'],contents[0])
    else:
        header,body=contents[2].split(b'\n',1);h=json.loads(header);v=json.loads(body)
        if fault=='old_aggregate':v.pop('comparison_index')
        elif fault=='index':v['comparison_index']['scorecard_sha256']='f'*64
        elif fault=='history':v['history_audit']['history']['history_sha256']='f'*64
        elif fault=='native_frame':h['environment']['lane']='source'
        body=canonical(v);h.update(payload_sha256=sha(body),payload_bytes=len(body));contents[2]=canonical(h)+b'\n'+body
        a=meta['lanes'][1]['aggregate'];a['artifact']=artifact(a['task_id'],a['artifact']['path'],contents[2]);request['records'][2]['artifact']=a['artifact']
        if fault!='payload_pin':a.update(payload_sha256=sha(body),payload_bytes=len(body))
        else:a['payload_sha256']='f'*64
    request['metadata']=canonical(meta);raw=build_bundle(**request)
    with pytest.raises(DataError):worker.pair_compare(raw,sha(raw),request['task_id'],request['source_run_id'],lambda i,a:contents[i])
