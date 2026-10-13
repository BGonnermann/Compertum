import hashlib
import json
from datetime import datetime,timezone
from pathlib import Path
import shutil
import sys
import pytest
sys.path.insert(0,str(Path(__file__).parent/'helpers'))
from ai_fixture import ai_task,proposal
from compertum.ai.manual import ManualBridge
from compertum.config import load_config
from compertum.storage import StorageManager
from compertum.runtime.identity import resolve_project
from compertum.runtime.owners import acquire_owner,release_owner
from compertum.runtime.errors import RuntimeRefused

@pytest.fixture
def bridge(tmp_path):
    shutil.copyfile(Path(__file__).parents[1]/'config/default.toml',tmp_path/'config.toml')
    lease=acquire_owner(resolve_project(tmp_path),'coordinator')
    try: yield ManualBridge(StorageManager(lease,load_config(tmp_path/'config.toml',tmp_path))),tmp_path
    finally: release_owner(lease)

def packet(bridge):
    b,root=bridge;task,relative=ai_task(root);artifact=b.export_subscription_task(task,prompt='Check this fixture.',files=[relative])
    value=json.loads((root/artifact['path']).read_bytes());response=proposal(task,value['prompt_sha256'])
    path=root/relative;path=path.with_name('response.json');path.write_text(json.dumps(response))
    meta={'provider':'manual_subscription','model_label':'synthetic-model','received_at':datetime.now(timezone.utc).isoformat(),'provenance':'SYNTHETIC_FIXTURE'}
    return b,root,task,path,response,meta

def test_manual_original_and_provenance_retained_without_execution(bridge):
    b,root,task,path,response,meta=packet(bridge)
    response['proposed_patch']="raise SystemExit('DO_NOT_EXECUTE')";path.write_text(json.dumps(response))
    result=b.import_proposal(task.to_payload()['task_id'],path,meta)
    assert result['executed'] is False and result['hosted_response_observed'] is False
    assert result['status']=='PROPOSAL_ONLY'
    assert (root/result['original']['path']).read_bytes()==path.read_bytes()
    assert b.import_proposal(task.to_payload()['task_id'],path,meta)==result

def test_outside_bundle_and_sensitive_input_are_denied_before_export(bridge):
    b,root=bridge;task,relative=ai_task(root)
    outside=root/'protected.txt';outside.write_text('PROTECTED_SENTINEL')
    with pytest.raises(RuntimeRefused,match='AI_BUNDLE_DENIED'): b.export_subscription_task(task,prompt='x',files=['protected.txt'])
    (root/relative).write_text('PROTECTED_SENTINEL')
    with pytest.raises(RuntimeRefused,match='AI_SENSITIVE_INPUT_DENIED'): b.export_subscription_task(task,prompt='x',files=[relative])
    assert b.store.conn.execute('SELECT count(*) FROM ai_tasks').fetchone()[0]==0

@pytest.mark.parametrize('mutation',['unknown','mismatch','expired','sensitive'])
def test_manual_invalid_or_late_response_never_becomes_proposal(bridge,mutation):
    b,root,task,path,response,meta=packet(bridge);task_id=task.to_payload()['task_id']
    if mutation=='unknown': response['execute']=True
    elif mutation=='mismatch': response['prompt_sha256']='f'*64
    elif mutation=='expired':
        with b.store.conn: b.store.conn.execute("UPDATE ai_tasks SET deadline='2020-01-01T00:00:00+00:00'")
    else: response['summary']='PROTECTED_SENTINEL'
    path.write_text(json.dumps(response))
    with pytest.raises(RuntimeRefused): b.import_proposal(task_id,path,meta)
    assert b.store.conn.execute('SELECT status FROM ai_tasks').fetchone()[0]=='WAITING_FOR_OPERATOR'


def test_aggregate_output_budget_and_idempotent_retention(bridge):
    b,root,task,path,response,meta=packet(bridge);task_id=task.to_payload()['task_id']
    first=b._retain(task_id,'bounded.txt',b'x'*100)
    assert b._retain(task_id,'bounded.txt',b'x'*100)==first
    b._retain(task_id,'large.txt',b'x'*(128*1024))
    with pytest.raises(RuntimeRefused,match='AI_OUTPUT_BUDGET'): b._retain(task_id,'overflow.txt',b'x'*(128*1024))
    assert not (root/f'artifacts/runs/{task_id}/ai/overflow.txt').exists()
