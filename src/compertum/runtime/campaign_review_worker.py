"""Shared bounded campaign scorecard and independent audit worker modes."""
import ctypes as c
import hashlib,json,os
from ._windows import WindowsAPI,OwnedHandle,DWORD
from .identity_pins import runtime_identity
from .startup_record import expected_proof,check_report,validate_proof
from .inherited_input import read_input as _read
from .campaign_environment import verify_input,observed_from_native,check_attempt_environments
from .startup import expected_clean_environment
from compertum.data.encoding import canonical
from compertum.data.errors import DataError
from compertum.review_bundle import read_bundle,read_declared_bundle
from compertum.review_frame import result_binding,pack_review
from compertum.review_evidence import check,successful_receipt,MIB


def scorecard(raw,digest,task,run,read_record):
    from compertum.audit_campaign import reconstruct_history
    from compertum.modeling.campaign_scorecard import build_from_campaign
    identity=runtime_identity()
    header,metadata=read_bundle(raw,expected_sha256=digest,expected_kind='scorecard',expected_task_id=task,expected_source_run_id=run,expected_identity=identity)
    v=json.loads(metadata);state,_=reconstruct_history(v['final_state'].encode(),v['history'],v['controls'])
    check(state['state']=='COMPLETED' and state['run_id']==run and canonical(state['identity'])==canonical(identity) and canonical(state['protocol_seal'])==canonical(header['protocol_seal']))
    expected=[dict(kind='campaign',index=None,artifact=state['input_artifact'])]
    for o in sorted(state['outcomes'].values(),key=lambda o:o['unit']):
        if o['status']=='COMPLETED':expected.append(dict(kind='frame',index=o['unit'],artifact=o['artifact']))
    check(canonical(expected)==canonical(header['records']))
    for a in state['attempts']:
        if a['status']=='COMPLETED':
            n=a['native_execution'];check(n['task_id']==run and n['role']=='experiment_runner' and n['code_sha256']==identity['package_sha256'] and n['lock_sha256']==identity['lock_sha256'] and successful_receipt(a['job_receipt'],n))
    def read(index):
        record=header['records'][index];content=read_record(index,record['artifact'])
        check(type(content) is bytes and len(content)==record['artifact']['size_bytes'] and hashlib.sha256(content).hexdigest()==record['artifact']['sha256'])
        return content
    campaign=read(0);frames={r['artifact']['path']:read(i) for i,r in enumerate(header['records']) if r['kind']=='frame'}
    result=build_from_campaign(campaign,v['final_state'].encode(),frames,expected_campaign_sha256=state['request_sha256'],expected_identity=identity)
    return pack_review(result.content,result_binding('scorecard',task,run,digest,identity,os.getpid()))


def aggregate(raw,digest,task,run,read_record):
    import io
    from compertum.audit_campaign import reconstruct_history,audit_campaign
    from compertum.aggregate_evidence import decode_exports,bind_unit_audit
    from compertum.audit_history import reconstruct
    from compertum.audit_runs import FIELDS
    from compertum.review_runs import ReviewRuns
    from compertum.review_bundle import build_bundle
    from compertum.review_frame import verify_review
    identity=runtime_identity()
    header,metadata=read_bundle(raw,expected_sha256=digest,expected_kind='aggregate',expected_task_id=task,expected_source_run_id=run,expected_identity=identity)
    meta=json.loads(metadata);source,_=reconstruct_history(meta['final_state'].encode(),meta['history'],meta['controls'])
    check(source['state']=='COMPLETED' and source['run_id']==run and canonical(source['identity'])==canonical(identity) and canonical(source['protocol_seal'])==canonical(header['protocol_seal']))
    expected=[dict(kind='campaign',index=None,artifact=source['input_artifact'])]
    for o in sorted(source['outcomes'].values(),key=lambda o:o['unit']):
        if o['status']=='COMPLETED':expected.append(dict(kind='frame',index=o['unit'],artifact=o['artifact']))
    base=[r for r in header['records'] if r['kind'] in ('campaign','frame')];check(canonical(base)==canonical(expected))
    for a in source['attempts']:
        if a['status']=='COMPLETED':
            n=a['native_execution'];check(n['task_id']==run and n['role']=='experiment_runner' and n['code_sha256']==identity['package_sha256'] and n['lock_sha256']==identity['lock_sha256'] and successful_receipt(a['job_receipt'],n))
    def read(index):
        record=header['records'][index];content=read_record(index,record['artifact'])
        check(type(content) is bytes and len(content)==record['artifact']['size_bytes'] and hashlib.sha256(content).hexdigest()==record['artifact']['sha256']);return content
    exports=[read(i) for i,r in enumerate(header['records']) if r['kind']=='audit_history']
    packet,units=decode_exports(exports);check(set(packet)=={'state','history','task'})
    card=ReviewRuns.reconstruct(canonical(packet['state']),packet['history'])
    check(card['kind']=='scorecard' and card['state']=='COMPLETED' and card['source_run_id']==run and canonical(card['identity'])==canonical(identity))
    check_attempt_environments(card['attempts'],source.get('clean_environment'))
    card_request=build_bundle(kind='scorecard',task_id=card['task_id'],source_run_id=run,identity=identity,protocol_seal=header['protocol_seal'],metadata=metadata,records=base)
    check(hashlib.sha256(card_request).hexdigest()==card['request_sha256'])
    request_artifact=card['request_artifact'];check(request_artifact['task_id']==card['task_id'] and request_artifact['path']==f"artifacts/runs/{card['task_id']}/review/input/request.review" and request_artifact['size_bytes']==len(card_request) and request_artifact['sha256']==card['request_sha256'])
    a=card['attempts'][-1];task_raw=canonical(packet['task']);check(len(task_raw)<=64*1024 and hashlib.sha256(task_raw).hexdigest()==a['task_artifact']['sha256']==a['native_execution']['task_sha256'])
    check(a['task_artifact']['task_id']==card['task_id'] and a['task_artifact']['path']==f"artifacts/runs/{card['task_id']}/review/input/task-attempt-{a['number']}.json" and a['task_artifact']['size_bytes']==len(task_raw))
    ReviewRuns._payload(card,packet['task'],dict(records=base))
    card_records=[(i,r) for i,r in enumerate(header['records']) if r['kind']=='scorecard'];check(len(card_records)==1)
    index,record=card_records[0];check(canonical(record['artifact'])==canonical(card['artifact']) and card['artifact']['path']==a['output_path'])
    card_raw=read(index);binding=result_binding('scorecard',card['task_id'],run,card['request_sha256'],identity,a['native_execution']['process']['pid'],startup=expected_proof(a['native_execution']),environment=observed_from_native(a['native_execution']))
    verified=verify_review(io.BytesIO(card_raw),binding)
    check(verified['payload_sha256']==card['payload_sha256'] and verified['payload_bytes']==card['payload_bytes'])
    card_payload=card_raw.split(b'\n',1)[1]
    needed={o['unit'] for o in source['outcomes'].values() if o['status']=='COMPLETED' and o['identity']['phase']=='evaluate'}
    unit_records={r['index']:(i,r) for i,r in enumerate(header['records']) if r['kind']=='unit_audit'}
    check(set(unit_records)==needed and len(units)==len(needed));seen=set();audit_pins=[]
    for item in units:
        check(type(item) is dict and set(item)=={'state','history'})
        s=reconstruct(canonical(item['state']),item['history']);bound=bind_unit_audit(s,source);unit=bound['index']
        check(unit in needed and unit not in seen and s['task_id']!=card['task_id']);seen.add(unit)
        i,record=unit_records[unit];check(canonical(record)==canonical(bound))
        content=read(i);v=json.loads(content);check(canonical(v)==content);check_report(v,FIELDS,s['attempts'][-1]['native_execution'])
        request=s['request'];native=s['attempts'][-1]['native_execution']
        fields=dict(task_id=s['task_id'],role='experiment_auditor',worker_pid=native['process']['pid'],unit=unit,candidate_id=request['candidate_id'],year=request['year'],input_sha256=request['input_artifact']['sha256'],result_frame_sha256=request['result']['artifact']['sha256'],result_payload_sha256=request['result']['payload_sha256'],fit_frame_sha256=request['fit']['artifact']['sha256'] if request['fit'] else None,fit_payload_sha256=request['fit']['payload_sha256'] if request['fit'] else None,runtime_identity=identity,native_authority='AWAITING_COORDINATOR_RECEIPT',financial_accepted=False)
        check(canonical({k:v[k] for k in fields})==canonical(fields) and v['audit_sha256']==s['audit_sha256']==hashlib.sha256(canonical(v['audit'])).hexdigest())
        check(v['audit']['status']=='VERIFIED_PASS' and v['audit']['candidate_sha256']==request['result']['payload_sha256'] and v['audit']['financial_accepted'] is False and v['audit']['full_M3'] is False)
        audit_pins.append(dict(unit=unit,task_id=s['task_id'],artifact_sha256=record['artifact']['sha256'],audit_sha256=s['audit_sha256'],attempts=len(s['attempts']),history_sha256=hashlib.sha256(canonical(item['history'])).hexdigest()))
    campaign=read(0);frames={r['artifact']['path']:read(i) for i,r in enumerate(header['records']) if r['kind']=='frame'}
    report=audit_campaign(campaign,meta['final_state'].encode(),meta['history'],meta['controls'],frames,card_payload,expected_campaign_sha256=source['request_sha256'],expected_identity=identity)
    from compertum.campaign_comparison import build_index
    from compertum.shortlist import project_scorecard
    from compertum.shortlist_ticket import review_pin
    projection=project_scorecard(card_payload,expected_sha256=card['payload_sha256'])
    comparison_index=build_index(source,scorecard_sha256=card['payload_sha256'],unit_audits=audit_pins,selection_projection=projection)
    result=canonical(dict(scorecard_review=review_pin(card,packet['history']),comparison_index=comparison_index,schema='synthetic-native-campaign-audit-v1',status='VERIFIED_PASS',scope='HISTORY_AGGREGATE_AND_COMMITTED_UNIT_AUDIT_CONSISTENCY',source_run_id=run,request_sha256=digest,scorecard_sha256=card['payload_sha256'],scorecard_task_id=card['task_id'],history_audit=json.loads(report.content),unit_audits=audit_pins,required_unit_audits=len(needed),native_authority='AWAITING_COORDINATOR_RECEIPT',financial_accepted=False,full_M3=False,shortlist=[]))
    return pack_review(result,result_binding('aggregate',task,run,digest,identity,os.getpid()))



def pair_compare(raw,digest,task,run,read_record):
    import io
    from compertum.clean_pair import detach_environment
    from compertum.campaign_comparison import compare_indices
    from compertum.review_frame import verify_review
    identity=runtime_identity()
    header,metadata=read_bundle(raw,expected_sha256=digest,expected_kind='pair_compare',expected_task_id=task,expected_source_run_id=run,expected_identity=identity)
    meta=json.loads(metadata)
    def read(i):
        artifact=header['records'][i]['artifact'];content=read_record(i,artifact)
        check(type(content) is bytes and len(content)==artifact['size_bytes'] and hashlib.sha256(content).hexdigest()==artifact['sha256']);return content
    campaign=read(0);_,pair,_,lane=detach_environment(campaign,expected_sha256=header['records'][0]['artifact']['sha256'])
    check(lane=='source' and pair.sha256==meta['pair_sha256'] and canonical(meta['pair'])==pair.content)
    indices=[]
    for i,pins in enumerate(meta['lanes'],1):
        a=pins['aggregate'];n=a['native_execution'];content=read(i)
        binding=result_binding('aggregate',a['task_id'],pins['run_id'],a['request_sha256'],identity,n['process']['pid'],startup=expected_proof(n),environment=observed_from_native(n))
        checked=verify_review(io.BytesIO(content),binding)
        check(checked['payload_sha256']==a['payload_sha256'] and checked['payload_bytes']==a['payload_bytes'])
        payload=content.split(b'\n',1)[1];v=json.loads(payload);check(canonical(v)==payload)
        check(v['schema']=='synthetic-native-campaign-audit-v1' and v['status']=='VERIFIED_PASS' and v['scope']=='HISTORY_AGGREGATE_AND_COMMITTED_UNIT_AUDIT_CONSISTENCY')
        check(v['source_run_id']==pins['run_id'] and v['request_sha256']==a['request_sha256'] and v['financial_accepted'] is False and v['full_M3'] is False)
        history=v['history_audit']['history']
        check(all(history[k]==pins['source_'+k] for k in ('history_sha256','controls_sha256')) and history['final_state_sha256']==pins['source_state_sha256'])
        index=v.get('comparison_index');check(type(index) is dict and index.get('scorecard_sha256')==v['scorecard_sha256']);indices.append(index)
    result=compare_indices(*indices)
    result.update(pair_sha256=meta['pair_sha256'],source_run_id=run,wheel_run_id=meta['lanes'][1]['run_id'],aggregate_payloads={v['lane']:v['aggregate']['payload_sha256'] for v in meta['lanes']})
    return pack_review(canonical(result),result_binding('pair_compare',task,run,digest,identity,os.getpid()))

def main(kind,args,*,startup=None):
    handles=[];code=6
    try:
        validate_proof(startup);check(startup['pid']==os.getpid())
        check(kind in ('scorecard','aggregate','pair_compare') and len(args)==8)
        bundle,sink,size=int(args[0]),int(args[1]),int(args[2]);digest,task,run=args[3:6];maximum=int(args[6])
        others=[int(s) for s in args[7].split(',')];values=[bundle,sink,*others]
        check(3<=len(values)<=105 and len(set(values))==len(values) and all(n>0 for n in values) and 0<size<=16*MIB and maximum==16*MIB)
        api=WindowsAPI();handles=[OwnedHandle(api,n) for n in values]
        for h in handles:check(api.handle_flags(h)&1);api.set_inheritable(h,False)
        raw=_read(api,handles[0],size)
        header,_=read_declared_bundle(raw,expected_sha256=digest,expected_kind=kind,expected_task_id=task,expected_source_run_id=run)
        check(len(others)==len(header['records']))
        primary=header['records'][0];check(primary['kind']=='campaign')
        campaign=_read(api,handles[2],primary['artifact']['size_bytes'])
        environment=verify_input(campaign,primary['artifact']['sha256'],expected=expected_clean_environment(startup))
        check(canonical(header['identity'])==canonical(runtime_identity()))
        def read_record(index,artifact):
            check(artifact==header['records'][index]['artifact'])
            return campaign if index==0 else _read(api,handles[index+2],artifact['size_bytes'])
        compute={'scorecard':scorecard,'aggregate':aggregate,'pair_compare':pair_compare}[kind]
        result=compute(raw,digest,task,run,read_record)
        result=pack_review(result.split(b'\n',1)[1],result_binding(kind,task,run,digest,runtime_identity(),os.getpid(),startup=startup,environment=environment))
        check(len(result)<=maximum)
        for start in range(0,len(result),8*MIB):
            chunk=result[start:start+8*MIB];buffer=c.create_string_buffer(chunk);written=DWORD()
            api.checked(api.WriteFile(handles[1].get(),buffer,len(chunk),c.byref(written),None),'ReviewWrite')
            if written.value!=len(chunk):raise OSError('REVIEW_SHORT_WRITE')
        api.checked(api.FlushFileBuffers(handles[1].get()),'ReviewFlush');code=0
    except Exception as error:
        code=5 if isinstance(error,OSError) else 4 if isinstance(error,DataError) and error.code.startswith('AUDIT_') else 6
    finally:
        for h in handles:
            try:h.close()
            except Exception:code=6
    return code
