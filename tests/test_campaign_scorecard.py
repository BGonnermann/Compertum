import copy,hashlib,json
import pytest
from compertum.modeling.campaign_scorecard import build_from_campaign
from compertum.data.encoding import canonical
from compertum.data.errors import DataError
from compertum.simulation.campaign_record import pack_result
from test_campaign_audit import evidence


def args(evidence):
    return {key:evidence[key] for key in ('campaign','final_state','frames','expected_campaign_sha256','expected_identity')}


def test_worker_scorecard_reproduces_all_slots_and_keeps_failures(evidence):
    result=build_from_campaign(**args(evidence));body=json.loads(result.content)
    assert result.content==evidence['scorecard']
    assert result.sha256==hashlib.sha256(result.content).hexdigest()
    assert body['counts']=={'completed':9,'failed':27,'pending':0}
    assert len(body['search_history'])==36 and body['shortlist']==[]
    assert body['financial_accepted'] is False


@pytest.mark.parametrize('case',['missing_frame','extra_frame','frame_bytes','input_hash','runtime','incomplete','state_encoding','payload_pin','source_window','source_market'])
def test_scorecard_worker_refuses_incomplete_or_rebound_campaign(evidence,case):
    v=copy.deepcopy(args(evidence));s=json.loads(v['final_state'])
    record=next(o for o in s['outcomes'].values() if o['status']=='COMPLETED');path=record['artifact']['path']
    if case=='missing_frame':v['frames'].pop(path)
    elif case=='extra_frame':v['frames'][path+'.orphan']=v['frames'][path]
    elif case=='frame_bytes':v['frames'][path]+=b' '
    elif case=='input_hash':v['expected_campaign_sha256']='0'*64
    elif case=='runtime':v['expected_identity']['package_sha256']='0'*64
    elif case=='incomplete':s['state']='STOPPED'
    elif case=='state_encoding':v['final_state']+=b' '
    elif case=='payload_pin':record['payload_sha256']='0'*64
    else:
        body=json.loads(v['frames'][path].split(b'\n',1)[1])
        if case=='source_window':body['training_end']='2020-12-30'
        else:
            body['market_sha256']='0'*64
            for replay in body['replays'].values():replay['market_sha256']='0'*64
        raw=canonical(body);frame=pack_result(raw,s['request_sha256'],record['unit'],record['dependency_sha256'])
        record['artifact'].update(size_bytes=len(frame),sha256=hashlib.sha256(frame).hexdigest());record['payload_sha256']=hashlib.sha256(raw).hexdigest();v['frames'][path]=frame
    if case!='state_encoding':v['final_state']=canonical(s)
    with pytest.raises(DataError):build_from_campaign(**v)

@pytest.fixture(scope='module')
def ridge_evidence(tmp_path_factory):
    from uuid import uuid4
    from compertum.runtime.identity import resolve_project
    from compertum.runtime.owners import acquire_owner,release_owner
    from compertum.simulation.runs import SavedRuns
    from compertum.simulation.campaign_runs import interrupt
    from compertum.modeling.campaign import UNITS
    from helpers.saved_campaign_fixture import campaign_folds
    from test_storage import manager
    root=tmp_path_factory.mktemp('scorecard-valid-ridge');project=resolve_project(root);lease=acquire_owner(project,'coordinator')
    try:
        storage=manager((project,{'coordinator':lease}));runs=SavedRuns(storage);run=str(uuid4())
        runs.create_campaign(run,campaign_folds(True));runs.control(run,str(uuid4()),'resume')
        for _ in range(5):runs.step(run)
        assert runs._load(run)['outcomes'][UNITS[4].key]['status']=='COMPLETED'
        # Explicitly injected deterministic failures retain all remaining trial slots.
        while runs.summary(run)['state']!='COMPLETED':
            runs.begin_campaign(run,runs.prepare_campaign(run));interrupt(runs,run,'MISSING_REFERENCE',terminal=True)
        state=runs._load(run);card=runs.campaign_scorecard(run)
        frames={o['artifact']['path']:(root/o['artifact']['path']).read_bytes() for o in state['outcomes'].values() if o['status']=='COMPLETED'}
        campaign=(root/state['input_artifact']['path']).read_bytes()
        return dict(campaign=campaign,final_state=canonical(state),frames=frames,scorecard=card.content,expected_campaign_sha256=hashlib.sha256(campaign).hexdigest(),expected_identity=state['identity'])
    finally:release_owner(lease)


def test_scorecard_retains_real_committed_ridge_and_parent(ridge_evidence):
    assert build_from_campaign(**args(ridge_evidence)).content==ridge_evidence['scorecard']
    assert json.loads(ridge_evidence['scorecard'])['counts']=={'completed':4,'failed':32,'pending':0}


def rewrite(v,index,edit):
    from compertum.modeling.campaign import UNITS
    state=json.loads(v['final_state']);record=state['outcomes'][UNITS[index].key];path=record['artifact']['path']
    body=json.loads(v['frames'][path].split(b'\n',1)[1]);edit(body)
    raw=canonical(body);frame=pack_result(raw,state['request_sha256'],index,record['dependency_sha256'])
    record['payload_sha256']=hashlib.sha256(raw).hexdigest();record['artifact'].update(size_bytes=len(frame),sha256=hashlib.sha256(frame).hexdigest());v['frames'][path]=frame
    if UNITS[index].phase=='fit':
        for child in state['outcomes'].values():
            if child['status']=='COMPLETED' and UNITS[child['unit']].fit_unit==index:
                child['dependency_sha256']=record['payload_sha256']
                for attempt in state['attempts']:
                    if attempt['unit']==child['unit']:attempt['dependency_sha256']=record['payload_sha256']
                childpath=child['artifact']['path'];payload=v['frames'][childpath].split(b'\n',1)[1]
                framed=pack_result(payload,state['request_sha256'],child['unit'],child['dependency_sha256']);v['frames'][childpath]=framed
                child['artifact'].update(size_bytes=len(framed),sha256=hashlib.sha256(framed).hexdigest())
    v['final_state']=canonical(state)


@pytest.mark.parametrize('case',['parent_rows_hash','child_embedded_fit','original_scoring_time'])
def test_coherent_rehash_cannot_rebind_fit_or_scoring_time(ridge_evidence,case):
    v=copy.deepcopy(args(ridge_evidence))
    if case=='parent_rows_hash':rewrite(v,3,lambda body:body.update(fit_rows_sha256='0'*64))
    elif case=='child_embedded_fit':rewrite(v,4,lambda body:body['dataset_assembly'].update(assembled_rows=body['dataset_assembly']['assembled_rows']+1))
    else:
        for index in (0,1,2,4):rewrite(v,index,lambda body:body['prediction_report'].update(scoring_as_of='2021-12-31T00:00:00+00:00'))
    with pytest.raises(DataError):build_from_campaign(**v)


def test_embedded_fit_must_preserve_json_types(ridge_evidence):
    v=copy.deepcopy(args(ridge_evidence))
    rewrite(v,4,lambda body:body['dataset_assembly'].update(financial_accepted=0))
    with pytest.raises(DataError):build_from_campaign(**v)
