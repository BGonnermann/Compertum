import json
import pytest
from compertum.runtime.identity import resolve_project
from compertum.runtime.owners import acquire_owner
from compertum.persistence import open_store
from compertum.domain import TaskSpec,ContractError,now
from compertum.ai.manual import export_subscription_task,import_proposal

def test_manual_bundle_provenance_and_no_execution(tmp_path):
    with acquire_owner(resolve_project(tmp_path),'coordinator') as lease:
        store=open_store(lease,'coordinator');task=TaskSpec(kind='AI_PROPOSAL');artifact=export_subscription_task(store,task,{'question':'Describe fixture','fixture':True})
        assert artifact['path'].endswith('packet.json')
        bundle=tmp_path/'artifacts/ai'/task.task_id;response=bundle/'response.json';metadata={'provider':'subscription_manual','model':'operator supplied','operator_supplied':True,'response_at':now()}
        response.write_text(json.dumps({'schema_version':1,'task_id':task.task_id,'summary':'Proposal only','claims':['fictional tool, never dispatched']}))
        (tmp_path/'protected-sentinel.json').write_text(response.read_text())
        with pytest.raises(ContractError,match='BUNDLE'):import_proposal(store,task.task_id,'protected-sentinel.json',metadata)
        value=json.loads(response.read_text());value['execute']='arbitrary';response.write_text(json.dumps(value))
        with pytest.raises(ContractError,match='SCHEMA'):import_proposal(store,task.task_id,str(response.relative_to(tmp_path)),metadata)
        del value['execute'];response.write_text(json.dumps(value));result=import_proposal(store,task.task_id,str(response.relative_to(tmp_path)),metadata)
        assert result['result']['executed'] is False and not (tmp_path/'executed').exists()
        assert store.get('ai-requests:'+now()[:10])==1;store.close()

def test_manual_secrets_and_expiry_fail_closed(tmp_path):
    with acquire_owner(resolve_project(tmp_path),'coordinator') as lease:
        store=open_store(lease,'coordinator');task=TaskSpec(kind='AI_PROPOSAL')
        with pytest.raises(ContractError,match='SECRET'):export_subscription_task(store,task,{'question':'sk-'+'s'*24})
        with pytest.raises(ContractError,match='BUNDLE'):export_subscription_task(store,task,{'path':'protected-sentinel'})
        export_subscription_task(store,task,{'question':'fixture'});state=store.get('ai:'+task.task_id);state['expires_at']='2000-01-01T00:00:00Z';store.set('ai:'+task.task_id,state)
        with pytest.raises(ContractError,match='EXPIRED'):import_proposal(store,task.task_id,'missing.json',{})
        store.close()

def test_expired_task_cannot_receive_new_manual_deadline(tmp_path):
    with acquire_owner(resolve_project(tmp_path),'coordinator') as lease:
        store=open_store(lease,'coordinator');task=TaskSpec(kind='AI_PROPOSAL',deadline_at='2000-01-01T00:00:00Z')
        with pytest.raises(ContractError,match='DEADLINE'):export_subscription_task(store,task,{'question':'expired'})
        assert not (tmp_path/'artifacts').exists();store.close()

def test_explicit_coordinator_inbox_retains_original_envelope(tmp_path):
    from compertum.ai.manual import import_inbox_proposal
    with acquire_owner(resolve_project(tmp_path),'coordinator') as lease:
        store=open_store(lease,'coordinator');task=TaskSpec(kind='AI_PROPOSAL');export_subscription_task(store,task,{'question':'fixture'})
        inbox=tmp_path/'artifacts/inbox';inbox.mkdir();container={'proposal':{'schema_version':1,'task_id':task.task_id,'summary':'synthetic'},'provenance':{'provider':'subscription_manual','model':'synthetic fixture only','operator_supplied':True,'response_at':now()}}
        path=inbox/'response.json';path.write_text(json.dumps(container))
        result=import_inbox_proposal(store,task.task_id,'artifacts/inbox/response.json')
        assert result['result']['executed'] is False and (tmp_path/result['result']['original']['path']).read_bytes()==path.read_bytes();store.close()
