import copy,hashlib,json
from uuid import uuid4
import pytest
from compertum.data.encoding import canonical
from compertum.data.errors import DataError
from compertum.review_bundle import build_bundle,read_bundle


def inputs(kind='scorecard'):
    task,source=str(uuid4()),str(uuid4())
    def artifact(owner,path,size=10):return dict(artifact_id=str(uuid4()),task_id=owner,path=path,size_bytes=size,sha256='d'*64)
    records=[dict(kind='campaign',index=None,artifact=artifact(source,f'artifacts/runs/{source}/baseline/inputs.json')),
        dict(kind='frame',index=0,artifact=artifact(source,f'artifacts/runs/{source}/baseline/unit-00-attempt-1.campaign'))]
    if kind=='aggregate':
        audit,scorecard=str(uuid4()),str(uuid4())
        records.extend([dict(kind='unit_audit',index=0,artifact=artifact(audit,f'artifacts/runs/{audit}/audit/attempt-1.json')),
            dict(kind='audit_history',index=0,artifact=artifact(task,f'artifacts/runs/{task}/review/input/unit-audits-0.json')),
            dict(kind='scorecard',index=None,artifact=artifact(scorecard,f'artifacts/runs/{scorecard}/review/scorecard-attempt-1.review'))])
    return dict(kind=kind,task_id=task,source_run_id=source,
        identity={'package_sha256':'a'*64,'lock_sha256':'b'*64,'python':'3.14.7','distributions':[['compertum','0.0.1']]},
        protocol_seal={'seal_id':str(uuid4()),'protocol_sha256':'e'*64,'ticket_sha256':'f'*64,'admission_event_sha256':'0'*64},
        metadata=canonical({'final_state':'{}','history':[],'controls':[]}),records=records)


def read(raw,v):
    return read_bundle(raw,expected_sha256=hashlib.sha256(raw).hexdigest(),expected_kind=v['kind'],expected_task_id=v['task_id'],expected_source_run_id=v['source_run_id'],expected_identity=v['identity'])


@pytest.mark.parametrize('kind',['scorecard','aggregate'])
def test_bundle_exact_manifest_and_metadata(kind):
    v=inputs(kind);raw=build_bundle(**v);header,metadata=read(raw,v)
    assert header['records']==v['records'] and metadata==v['metadata']
    assert header['financial_accepted'] is False and header['metadata_sha256']==hashlib.sha256(metadata).hexdigest()


@pytest.mark.parametrize('case',['role','same_task','runtime','seal','duplicate','ordering','path','source_owner','source_size','negative','boolean_size','hash','frame_index','fit_audit','foreign_history','extra_scorecard','missing_scorecard','too_many_exports','metadata_bound','total_campaign_bound','extra_field'])
def test_bundle_refuses_out_of_contract_inputs(case):
    v=inputs('aggregate');records=v['records']
    if case=='role':v['kind']='arbitrary'
    elif case=='same_task':v['task_id']=v['source_run_id']
    elif case=='runtime':v['identity']['python']='3.13.0'
    elif case=='seal':v['protocol_seal']['ticket_sha256']='broken'
    elif case=='duplicate':records.insert(2,copy.deepcopy(records[1]))
    elif case=='ordering':records[0],records[1]=records[1],records[0]
    elif case=='path':records[1]['artifact']['path']='../secret'
    elif case=='source_owner':records[0]['artifact']['task_id']=str(uuid4())
    elif case=='source_size':records[0]['artifact']['size_bytes']=20*1024**2+1
    elif case=='negative':records[0]['artifact']['size_bytes']=-1
    elif case=='boolean_size':records[0]['artifact']['size_bytes']=True
    elif case=='hash':records[0]['artifact']['sha256']='F'*64
    elif case=='frame_index':records[1]['index']=True
    elif case=='fit_audit':records[2]['index']=3
    elif case=='foreign_history':records[3]['artifact']['task_id']=str(uuid4())
    elif case=='extra_scorecard':records.append(copy.deepcopy(records[-1]))
    elif case=='missing_scorecard':records.pop()
    elif case=='too_many_exports':
        for i in (1,2):
            r=copy.deepcopy(records[3]);r['index']=i;r['artifact']['artifact_id']=str(uuid4());r['artifact']['path']=f"artifacts/runs/{v['task_id']}/review/input/unit-audits-{i}.json";records.insert(-1,r)
    elif case=='metadata_bound':v['metadata']=b'x'*(16*1024**2)
    elif case=='total_campaign_bound':
        records[0]['artifact']['size_bytes']=20*1024**2
        for i in range(1,9):
            r=copy.deepcopy(records[1]);r['index']=i;r['artifact'].update(artifact_id=str(uuid4()),path=f"artifacts/runs/{v['source_run_id']}/baseline/unit-{i:02}-attempt-1.campaign",size_bytes=16*1024**2);records.insert(i+1,r)
    else:records[0]['artifact']['authority']=True
    with pytest.raises(DataError):build_bundle(**v)


@pytest.mark.parametrize('case',['metadata','encoding','header','hash','task','source','kind','runtime','trailing','header_bound'])
def test_bundle_consumer_requires_exact_external_pins(case):
    v=inputs();raw=build_bundle(**v);digest=hashlib.sha256(raw).hexdigest()
    if case=='metadata':raw=raw[:-1]+b' '
    elif case=='encoding':raw=b' '+raw
    elif case=='header':
        line,body=raw.split(b'\n',1);h=json.loads(line);h['financial_accepted']=0;raw=canonical(h)+b'\n'+body;digest=hashlib.sha256(raw).hexdigest()
    elif case=='hash':digest='0'*64
    elif case=='task':v['task_id']=str(uuid4())
    elif case=='source':v['source_run_id']=str(uuid4())
    elif case=='kind':v['kind']='aggregate'
    elif case=='runtime':v['identity']['lock_sha256']='0'*64
    elif case=='trailing':raw+=b' '
    else:raw=b'x'*65537+b'\n'+b'{}'
    with pytest.raises(DataError):read_bundle(raw,expected_sha256=digest,expected_kind=v['kind'],expected_task_id=v['task_id'],expected_source_run_id=v['source_run_id'],expected_identity=v['identity'])


@pytest.mark.parametrize('case',['frame_path','artifact_identity','metadata_size','metadata_digest','trailing_rehashed'])
def test_rehashed_manifest_keeps_internal_bounds(case):
    v=inputs();raw=build_bundle(**v)
    if case=='frame_path':v['records'][1]['artifact']['path']=v['records'][1]['artifact']['path'].replace('unit-00','unit-01')
    elif case=='artifact_identity':v['records'][1]['artifact']['artifact_id']=v['records'][0]['artifact']['artifact_id']
    else:
        line,body=raw.split(b'\n',1);header=json.loads(line)
        if case=='metadata_size':header['metadata_bytes']+=1
        elif case=='metadata_digest':header['metadata_sha256']='0'*64
        else:body+=b' '
        raw=canonical(header)+b'\n'+body
    with pytest.raises(DataError):
        if case in ('frame_path','artifact_identity'):build_bundle(**v)
        else:read(raw,v)


def maximal_inputs():
    from compertum.modeling.campaign import UNITS
    v=inputs('aggregate');source=v['source_run_id'];records=[v['records'][0]];records[0]['artifact']['size_bytes']=20*1024**2
    def artifact(owner,path,size):return dict(artifact_id=str(uuid4()),task_id=owner,path=path,size_bytes=size,sha256='d'*64)
    remaining=108*1024**2
    for i in range(63):
        size=min(16*1024**2,remaining-(62-i));remaining-=size
        records.append(dict(kind='frame',index=i,artifact=artifact(source,f'artifacts/runs/{source}/baseline/unit-{i:02}-attempt-1.campaign',size)))
    assert remaining==0
    for i,u in enumerate(UNITS):
        if u.phase=='evaluate':
            task=str(uuid4());records.append(dict(kind='unit_audit',index=i,artifact=artifact(task,f'artifacts/runs/{task}/audit/attempt-1.json',16*1024**2)))
    for i in (0,1):records.append(dict(kind='audit_history',index=i,artifact=artifact(v['task_id'],f"artifacts/runs/{v['task_id']}/review/input/unit-audits-{i}.json",8*1024**2)))
    score=copy.deepcopy(v['records'][-1]);score['artifact']['size_bytes']=16*1024**2;records.append(score);v['records']=records
    value=json.loads(v['metadata']);value['history']=[{'padding':'x'*(10*1024**2)}]
    # Header width stabilizes once the metadata length has eight digits.
    for _ in range(3):
        v['metadata']=canonical(value);raw=build_bundle(**v)
        value['history'][0]['padding']+='x'*(16*1024**2-len(raw))
    v['metadata']=canonical(value)
    assert len(build_bundle(**v))==16*1024**2
    return v


def test_exact_104_handle_752_mib_limit_counts_first_export_header():
    v=maximal_inputs();raw=build_bundle(**v)
    assert len(v['records'])+1==104
    assert len(raw)+sum(r['artifact']['size_bytes'] for r in v['records'])==752*1024**2
    assert len(raw)+sum(r['artifact']['size_bytes'] for r in v['records'] if r['kind'] in ('audit_history','scorecard'))==48*1024**2
    assert read(raw,v)[1]==v['metadata']
    # One extra export byte exceeds both aggregate byte budgets.
    v['records'][-2]['artifact']['size_bytes']+=1
    with pytest.raises(DataError):build_bundle(**v)
    v['records'][-2]['artifact']['size_bytes']-=1
    extra=copy.deepcopy(v['records'][-2]);extra['index']=2;extra['artifact']['artifact_id']=str(uuid4());extra['artifact']['path']=extra['artifact']['path'].replace('-1.json','-2.json');v['records'].insert(-1,extra)
    with pytest.raises(DataError):build_bundle(**v)

@pytest.mark.parametrize('kind',['scorecard','aggregate'])
def test_declared_bundle_validation_does_not_claim_observed_runtime(kind):
    from compertum.review_bundle import read_declared_bundle
    v=inputs(kind);raw=build_bundle(**v)
    header,metadata=read_declared_bundle(raw,expected_sha256=hashlib.sha256(raw).hexdigest(),expected_kind=kind,expected_task_id=v['task_id'],expected_source_run_id=v['source_run_id'])
    assert header['identity']==v['identity'] and metadata==v['metadata']

@pytest.mark.parametrize('fault',['hash','header_bound','extra','identity'])
def test_declared_bundle_retains_all_structural_and_external_pin_checks(fault):
    from compertum.review_bundle import read_declared_bundle
    v=inputs();raw=build_bundle(**v);pin=hashlib.sha256(raw).hexdigest()
    if fault=='hash':pin='0'*64
    elif fault=='header_bound':raw=b'x'*65537+b'\n{}';pin=hashlib.sha256(raw).hexdigest()
    else:
        h,body=raw.split(b'\n',1);header=json.loads(h)
        if fault=='extra':header['observed_runtime']=True
        else:header['identity']['python']='3.13.0'
        raw=canonical(header)+b'\n'+body;pin=hashlib.sha256(raw).hexdigest()
    with pytest.raises(DataError):read_declared_bundle(raw,expected_sha256=pin,expected_kind=v['kind'],expected_task_id=v['task_id'],expected_source_run_id=v['source_run_id'])
