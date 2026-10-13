from uuid import uuid4
import pytest
from compertum.domain import TaskSpec,ContractError
from compertum.foundation import fixture_spec


def payload(root):
    source=str(uuid4());p=fixture_spec(root).to_payload();task=p['task_id'];p.update(parent_task_id=source,campaign_id=source)
    p['permissions']['filesystem_bundle']=[f'artifacts/runs/{task}/review/input/request.review',f'artifacts/runs/{source}/baseline/inputs.json',f'artifacts/runs/{source}/baseline/unit-62-attempt-2.campaign']
    p['permissions']['output_directory']=f'artifacts/runs/{task}/review';p['input_hashes']=['a'*64,'b'*64,'c'*64];return p


def test_scorecard_contract_allows_only_its_source_and_request_namespace(tmp_path):
    p=payload(tmp_path);assert TaskSpec(p,project_root=tmp_path).to_payload()==p


@pytest.mark.parametrize('case',['auditor','checker','missing_parent','other_campaign','same_task','unit_outside','extra_input','wrong_attempt','sibling_source','sibling_request','output','request_suffix'])
def test_scorecard_path_exception_stays_narrow(tmp_path,case):
    p=payload(tmp_path);paths=p['permissions']['filesystem_bundle']
    if case=='auditor':p['role']='experiment_auditor'
    elif case=='checker':p['role']='mathematical_checker'
    elif case=='missing_parent':p['parent_task_id']=None
    elif case=='other_campaign':p['campaign_id']=str(uuid4())
    elif case=='same_task':p['parent_task_id']=p['campaign_id']=p['task_id']
    elif case=='unit_outside':paths[2]=paths[2].replace('unit-62','unit-63')
    elif case=='extra_input':paths.append('state/evaluation.sqlite');p['input_hashes'].append('d'*64)
    elif case=='wrong_attempt':paths[2]=paths[2].replace('attempt-2','attempt-3')
    elif case=='sibling_source':paths[2]=paths[2].replace(p['parent_task_id'],str(uuid4()))
    elif case=='sibling_request':paths[0]=paths[0].replace(p['task_id'],str(uuid4()))
    elif case=='output':p['permissions']['output_directory']=f"artifacts/runs/{p['task_id']}/baseline"
    else:paths[0]+='.extra'
    with pytest.raises(ContractError):TaskSpec(p,project_root=tmp_path)


def aggregate_payload(root):
    p=payload(root);task=p['task_id'];p['role']='experiment_auditor'
    paths=p['permissions']['filesystem_bundle']
    paths.extend([f'artifacts/runs/{task}/review/input/unit-audits-0.json',f'artifacts/runs/{uuid4()}/audit/attempt-1.json',f'artifacts/runs/{uuid4()}/review/scorecard-attempt-2.review'])
    p['input_hashes']=['a'*64]*len(paths);return p


def test_aggregate_contract_allows_its_bounded_evidence_namespaces(tmp_path):
    p=aggregate_payload(tmp_path);assert TaskSpec(p,project_root=tmp_path).to_payload()==p


@pytest.mark.parametrize('case',['role','missing_export','foreign_export','extra_export','bad_uuid','other_review','wrong_attempt','database','output'])
def test_aggregate_path_exception_stays_narrow(tmp_path,case):
    p=aggregate_payload(tmp_path);paths=p['permissions']['filesystem_bundle']
    if case=='role':p['role']='experiment_runner'
    elif case=='missing_export':paths.pop(3);p['input_hashes'].pop(3)
    elif case=='foreign_export':paths[3]=paths[3].replace(p['task_id'],str(uuid4()))
    elif case=='extra_export':paths[3]=paths[3].replace('unit-audits-0','unit-audits-2')
    elif case=='bad_uuid':paths[4]='artifacts/runs/not-a-task/audit/attempt-1.json'
    elif case=='other_review':paths[5]=paths[5].replace('scorecard-attempt','aggregate-attempt')
    elif case=='wrong_attempt':paths[4]=paths[4].replace('attempt-1','attempt-3')
    elif case=='database':paths[4]='state/coordinator.sqlite'
    else:p['permissions']['output_directory']=f"artifacts/runs/{p['task_id']}/audit"
    with pytest.raises(ContractError):TaskSpec(p,project_root=tmp_path)


def pair_payload(root):
    p=payload(root);task=p['task_id'];source=p['parent_task_id'];p['role']='experiment_auditor'
    p['permissions']['filesystem_bundle']=[f'artifacts/runs/{task}/review/input/request.review',f'artifacts/runs/{source}/baseline/inputs.json',*[f'artifacts/runs/{uuid4()}/review/aggregate-attempt-{n}.review' for n in (1,2)]]
    p['input_hashes']=['a'*64]*4;return p


def test_pair_contract_admits_only_request_source_and_two_aggregate_artifacts(tmp_path):
    p=pair_payload(tmp_path);assert TaskSpec(p,project_root=tmp_path).to_payload()==p


@pytest.mark.parametrize('fault',['role','extra','missing','same_aggregate','same_source','attempt','path','request','source','output','ordering'])
def test_pair_contract_does_not_expand_existing_foreign_path_access(tmp_path,fault):
    p=pair_payload(tmp_path);paths=p['permissions']['filesystem_bundle']
    if fault=='role':p['role']='experiment_runner'
    elif fault=='extra':paths.append('state/coordinator.sqlite');p['input_hashes'].append('a'*64)
    elif fault=='missing':paths.pop();p['input_hashes'].pop()
    elif fault=='same_aggregate':paths[3]=paths[2].replace('attempt-1','attempt-2')
    elif fault=='same_source':paths[2]=f"artifacts/runs/{p['parent_task_id']}/review/aggregate-attempt-1.review"
    elif fault=='attempt':paths[2]=paths[2].replace('attempt-1','attempt-3')
    elif fault=='path':paths[2]=paths[2].replace('aggregate-attempt','scorecard-attempt')
    elif fault=='request':paths[0]=paths[0].replace(p['task_id'],str(uuid4()))
    elif fault=='source':paths[1]=paths[1].replace(p['parent_task_id'],str(uuid4()))
    elif fault=='ordering':paths[0],paths[1]=paths[1],paths[0]
    else:p['permissions']['output_directory']=f"artifacts/runs/{p['task_id']}/audit"
    with pytest.raises(ContractError):TaskSpec(p,project_root=tmp_path)
