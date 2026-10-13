from uuid import uuid4
import pytest
from compertum.domain import TaskSpec,ContractError
from compertum.foundation import fixture_spec


def payload(root):
    source=str(uuid4());p=fixture_spec(root).to_payload();p.update(role='experiment_auditor',parent_task_id=source,campaign_id=source)
    p['permissions']['filesystem_bundle']=[f'artifacts/runs/{source}/baseline/inputs.json',f'artifacts/runs/{source}/baseline/unit-04-attempt-1.campaign',f'artifacts/runs/{source}/baseline/unit-03-attempt-1.campaign']
    p['input_hashes']=['a'*64,'b'*64,'c'*64];return p


def test_auditor_can_reference_its_exact_source_campaign_namespace(tmp_path):
    p=payload(tmp_path);assert TaskSpec(p,project_root=tmp_path).to_payload()==p


@pytest.mark.parametrize('case',['runner','checker','missing_parent','other_campaign','same_task','unit_outside','extra_input','wrong_attempt','sibling_source'])
def test_auditor_source_exception_does_not_broaden_other_roles_or_namespaces(tmp_path,case):
    p=payload(tmp_path)
    if case=='runner':p['role']='experiment_runner'
    elif case=='checker':p['role']='mathematical_checker'
    elif case=='missing_parent':p['parent_task_id']=None
    elif case=='other_campaign':p['campaign_id']=str(uuid4())
    elif case=='same_task':p['parent_task_id']=p['campaign_id']=p['task_id']
    elif case=='unit_outside':p['permissions']['filesystem_bundle'][1]=p['permissions']['filesystem_bundle'][1].replace('unit-04','unit-63')
    elif case=='extra_input':p['permissions']['filesystem_bundle'].append('state/evaluation.sqlite')
    elif case=='wrong_attempt':p['permissions']['filesystem_bundle'][1]=p['permissions']['filesystem_bundle'][1].replace('attempt-1','attempt-3')
    else:p['permissions']['filesystem_bundle'][1]=p['permissions']['filesystem_bundle'][1].replace(p['parent_task_id'],str(uuid4()))
    with pytest.raises(ContractError):TaskSpec(p,project_root=tmp_path)
