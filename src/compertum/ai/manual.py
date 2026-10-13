import json
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from ..domain import ContractError,TaskSpec,atomic_json,now,utc_time,within,new_id,validate_record,digest,file_hash,ensure_safe,receipt,canonical
from ..storage import StorageManager

def claim_ai_task(store,task_id):
    day=now()[:10]
    with store.transaction():
        tasks=store.get('ai-tasks:'+day,[])
        if task_id not in tasks:
            if len(tasks)>=8:raise ContractError('DAILY_AI_TASK_LIMIT')
            store.set('ai-tasks:'+day,tasks+[task_id])

def export_subscription_task(store,task,inputs):
    if task.kind!='AI_PROPOSAL':raise ContractError('AI_TASK_REQUIRED')
    ensure_safe(inputs)
    # Inputs are explicitly bundled values, never arbitrary paths or protected records.
    if not isinstance(inputs,dict) or set(inputs)-{'question','fixture'}:raise ContractError('BUNDLE_INPUT_DENIED')
    created=utc_time(now());expiry=created+timedelta(hours=24)
    if task.deadline_at:expiry=min(expiry,utc_time(task.deadline_at))
    if expiry<=created:raise ContractError('AI_TASK_DEADLINE')
    expiry=expiry.isoformat()
    task=replace(task,input_hashes=(digest(inputs),),code_hash=file_hash(__file__),expected_schema='ai_proposal',deadline_at=expiry)
    packet={'task':task.record(),'inputs':inputs,'created_at':now(),'expires_at':expiry,'schema':json.loads((Path(__file__).resolve().parents[1]/'resources/ai_proposal.v1.json').read_text()),'provider':'subscription_manual','hosted_response_observed':False}
    claim_ai_task(store,task.task_id);manager=StorageManager(store);payload=json.dumps(packet,sort_keys=True).encode()
    if len(payload)>16384:raise ContractError('AI_INPUT_LIMIT')
    grant=manager.reserve_bytes(task.task_id,'records',len(payload));writer=manager.open_artifact(grant,'artifacts/ai/'+task.task_id+'/packet.json')
    try:writer.write(payload);artifact=writer.publish()
    finally:writer.close()
    store.set('ai:'+task.task_id,{'state':'WAITING_FOR_OPERATOR','packet':artifact,'created_at':packet['created_at'],'expires_at':packet['expires_at'],'attempts':0})
    return artifact

def import_proposal(store,task_id,response_path,metadata):
    state=store.get('ai:'+task_id)
    if not state or state['state']!='WAITING_FOR_OPERATOR':raise ContractError('AI_TASK_UNKNOWN_OR_COMPLETE')
    if utc_time(now())>utc_time(state['expires_at']):raise ContractError('MANUAL_WAIT_EXPIRED')
    if set(metadata)!={'provider','model','operator_supplied','response_at'} or metadata['provider']!='subscription_manual' or metadata['operator_supplied'] is not True:raise ContractError('PROVENANCE_REQUIRED')
    ensure_safe(metadata);timestamp=utc_time(metadata['response_at'])
    if not utc_time(state['created_at'])<=timestamp<=utc_time(now()):raise ContractError('RESPONSE_TIME_INVALID')
    root=store.lease.project.root_path;path=within(root,response_path)
    # Response must be explicitly deposited in this task's bundle.
    if not path.is_relative_to(root/'artifacts/ai'/task_id) or path.stat().st_size>65536:raise ContractError('BUNDLE_READ_DENIED')
    original=path.read_bytes();proposal=validate_record('ai_proposal',json.loads(original))
    if proposal['task_id']!=task_id:raise ContractError('TASK_MISMATCH')
    if len(original)>8192:raise ContractError('AI_OUTPUT_LIMIT')
    day=now()[:10]
    with store.transaction():
        used=store.get('ai-requests:'+day,0)
        if used>=40:raise ContractError('DAILY_AI_REQUEST_LIMIT')
        store.set('ai-requests:'+day,used+1)
    state.update(state='PROPOSAL_ONLY',response_hash=file_hash(path),metadata=metadata,proposal=proposal);store.set('ai:'+task_id,state)
    result=receipt('ai-import');result['result']={'state':'PROPOSAL_ONLY','executed':False,'response_hash':state['response_hash']};return result

def provider_status():return {'primary':'subscription_manual','subscription_access':'UNKNOWN','quota':'UNKNOWN','expiry':'USER_SUPPLIED_MARCH_2027','api_credits':'NOT_ASSUMED','automatic_hosted_adapter':'DISABLED','local_automatic':'DISABLED_PENDING_QUALIFICATION'}

def import_inbox_proposal(store,task_id,response_path):
    # Only the coordinator admits explicit inbox envelopes; worker reads remain bundle-only.
    state=store.get('ai:'+task_id)
    if not state or state['state']!='WAITING_FOR_OPERATOR':raise ContractError('AI_TASK_UNKNOWN_OR_COMPLETE')
    root=store.lease.project.root_path;path=within(root,response_path)
    if path.parent!=root/'artifacts/inbox' or path.stat().st_size>16384:raise ContractError('INBOX_READ_DENIED')
    raw=path.read_bytes();container=json.loads(raw);ensure_safe(container)
    if set(container)!={'proposal','provenance'}:raise ContractError('INBOX_PROVENANCE_REQUIRED')
    validate_record('ai_proposal',container['proposal'])
    manager=StorageManager(store);saved=[]
    for suffix,payload in [('original-inbox.json',raw),('proposal.json',canonical(container['proposal']))]:
        grant=manager.reserve_bytes(task_id,'records',len(payload));writer=manager.open_artifact(grant,'artifacts/ai/'+task_id+'/'+new_id()+'-'+suffix)
        try:writer.write(payload);saved.append(writer.publish())
        finally:writer.close()
    result=import_proposal(store,task_id,saved[1]['path'],container['provenance']);result['result']['original']=saved[0];return result

def cli_ai(root,args):
    if args==['status']:
        result=receipt('ai-status');result['result']=provider_status();return result
    if args==['qualify','--provider','strata','--suite','worker-v1']:
        from .qualification import qualify_strata
        return qualify_strata(root)
    # Manual writes go through the active authenticated coordinator, not a CLI DB writer.
    from ..cli import control
    if len(args)==3 and args[:2]==['export','--question']:return control(root,'ai-export',question=args[2])
    if len(args)==5 and args[:2]==['export','--task'] and args[3:]==['--provider','subscription']:return control(root,'ai-export-existing',task_id=args[2])
    if len(args)==5 and args[:2]==['import','--task'] and args[3]=='--response':return control(root,'ai-import-inbox',task_id=args[2],response_path=args[4])
    if len(args)==7 and args[0]=='import' and args[1]=='--task' and args[3]=='--response' and args[5]=='--metadata':
        meta=within(root,args[6]);return control(root,'ai-import',task_id=args[2],response_path=args[4],metadata=json.loads(meta.read_text()))
    raise ContractError('CAPABILITY_UNAVAILABLE')
