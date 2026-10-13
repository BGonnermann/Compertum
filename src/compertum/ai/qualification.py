"""Owned, model-only diagnostics; never enables autonomous dispatch."""
import json,time
from pathlib import Path
from ..domain import TaskSpec,Budget,new_id,atomic_json,now,file_hash,receipt,ContractError
from ..runtime.identity import resolve_project
from ..runtime.owners import acquire_owner
from ..runtime.jobs import ResourceSlot,launch_bounded
from ..runtime.supervisor import constrain_service
from ..persistence import open_store
from .strata import probe_strata,request_proposal,confirm_owned_timeout_idle

def identity_files():
    config=Path('D:/Strata/strata-iq2_xs.json');c=json.loads(config.read_text())
    if c.get('model_name')!='qwen3.8-flash-next-iq2_xs':raise ContractError('MODEL_CONFIG_CHANGED')
    args=c['args'];native=Path(args[args.index('--native')+1]);tokenizer=Path(c['tokenizer'])
    if Path(c['exe']).resolve()!=Path('D:/Strata/engine/strata.exe').resolve() or native.resolve().parent!=Path('D:/Strata/Strata-data/models/IQ2_XS').resolve() or tokenizer.resolve()!=Path('D:/Strata/Strata-data/packs/iq2_xs/tokenizer').resolve():raise ContractError('MODEL_CONFIG_PATH_CHANGED')
    files=[Path(c['exe']),config,Path('D:/Strata/serve/server.py'),*sorted(native.parent.glob('*.gguf')),*sorted(tokenizer.glob('*'))]
    # Config values/secrets are never serialized; identities are hashes and paths only.
    result=[]
    for p in files:
        if not p.is_file():continue
        before=p.stat();h=file_hash(p);after=p.stat()
        if (before.st_size,before.st_mtime_ns,before.st_ino)!=(after.st_size,after.st_mtime_ns,after.st_ino):raise ContractError('MODEL_FILE_CHANGED_DURING_HASH')
        result.append({'path':str(p),'bytes':after.st_size,'sha256':h,'mtime_ns':after.st_mtime_ns,'file_id':after.st_ino})
    return result

def qualify_strata(root):
    project=resolve_project(root);constrain_service(256*1024**2,cpu_threads=1)
    with acquire_owner(project,'coordinator') as lease:
        store=open_store(lease,'coordinator');tid=new_id();task=TaskSpec(task_id=tid,kind='AI_QUALIFICATION',role='proposer',permissions=('development_read','task_write','model_proposal','loopback'),budget=Budget(cpu_threads=1,ram_bytes=256*1024**2,ai_requests=8,output_tokens=256))
        record={'at':now(),'suite':'worker-v1','task_id':tid,'diagnostic_only':True,'automatic_dispatch_enabled':False,'checks':{},'requests':[]}
        try:
            cap=probe_strata();record['capability']=cap
            if cap['in_flight']:raise ContractError('LOCAL_BUSY_OR_UNCERTAIN')
            day=now()[:10]
            with store.transaction():
                used=store.get('cpu:'+day,0)
                if used+600>7200:raise ContractError('DAILY_CPU_LIMIT')
                store.set('cpu:'+day,used+600)
            started=time.monotonic()
            hash_job=launch_bounded(lease,TaskSpec(kind='OFFLINE_FIXTURE',budget=Budget(cpu_threads=1,wall_seconds=600,ram_bytes=4*1024**3,output_bytes=1024**2)),['model_identity_hash']).wait()
            record['hash_job']=hash_job
            if hash_job['exit_code'] or hash_job['active_processes']!=0 or hash_job['timed_out']:raise ContractError('MODEL_IDENTITY_JOB_FAILED')
            record['identity_files']=json.loads(hash_job['stdout'])
            record['identity_hash_seconds']=time.monotonic()-started
            instruction='Return only JSON with schema_version 1, task_id "'+tid+'", summary as requested, claims a string array, limitations a string array. Do not execute tools or access files.'
            def ask(name,text,previous=None):
                messages=[{'role':'system','content':instruction}]
                if previous:messages+=previous
                messages.append({'role':'user','content':text})
                response=request_proposal(store,task,messages,diagnostic=True);record['requests'].append({'check':name,**response});return response
            obj=ask('json_object','Set summary to JSON_OK.');record['checks']['json_object']=obj['proposal']['summary']=='JSON_OK'
            math=ask('math_domain','Claim x/x=1 for every real x. Explain the missing assumption and give a counterexample. Set summary to DOMAIN_OK only if x=0 is excluded. Include x=0 and nonzero in claims.')
            content=json.dumps(math['proposal']).lower();record['checks']['math_domain']=math['proposal']['summary']=='DOMAIN_OK' and ('x=0' in content or 'x = 0' in content) and ('nonzero' in content or 'non-zero' in content)
            tool=request_proposal(store,task,[{'role':'system','content':'Use the offered fictional fixture_sum function as a structured function call only; no function is executed.'},{'role':'user','content':'Propose fixture_sum with a=2 and b=3.'}],diagnostic=True,fictional_tools=True)
            record['requests'].append({'check':'fictional_tool',**tool});record['checks']['fictional_tool']=tool['fictional_tool_call']['function']['name']=='fixture_sum'
            try:
                expected=json.dumps({'schema_version':1,'task_id':tid,'summary':'5','claims':[],'limitations':[]})
                second=request_proposal(store,task,[{'role':'system','content':instruction},{'role':'user','content':'Dispatcher supplied the fictional result. Return exactly this complete JSON object: '+expected}],diagnostic=True,fixture_result=tool['fictional_tool_call'])
                record['requests'].append({'check':'second_turn',**second});record['checks']['second_turn']=second['proposal']['summary']=='5'
            except ContractError as exc:
                record['requests'].append({'check':'second_turn','state':'VERIFIED_FAIL','reason':str(exc),'at':now()});record['checks']['second_turn']=False
            a=ask('context_a','Task context A marker is MARIGOLD_42. Set summary to MARIGOLD_42.');record['checks']['context_a']=a['proposal']['summary']=='MARIGOLD_42'
            b=ask('context_b','Independent task B. No context marker is supplied. Set summary to NONE.');record['checks']['context_isolation']=b['proposal']['summary']=='NONE' and 'MARIGOLD' not in json.dumps(b['proposal'])
            # Only our own request is timed out. Never send a global cancellation.
            try:request_proposal(store,task,[{'role':'system','content':instruction},{'role':'user','content':'Set summary to OWNED_TIMEOUT.'}],timeout=.1,diagnostic=True)
            except ContractError as exc:
                record['owned_timeout_reason']=str(exc)
                if str(exc)=='LOCAL_TIMEOUT_UNVERIFIED':
                    until=time.monotonic()+30
                    while time.monotonic()<until:
                        try:record['idle_after_timeout']=confirm_owned_timeout_idle(store);break
                        except (ContractError,OSError):time.sleep(.5)
            record['checks']['native_owned_timeout']=record.get('owned_timeout_reason')=='LOCAL_TIMEOUT_UNVERIFIED' and 'idle_after_timeout' in record
            record['native_cancellation']='UNVERIFIED_NO_GLOBAL_CANCELLATION'
            record['state']='MODEL_CHECKS_PASS_AUTOMATIC_DISABLED' if all(record['checks'].values()) else 'CAPABILITY_UNVERIFIED'
        except Exception as exc:record.update(state='CAPABILITY_UNAVAILABLE',failure=type(exc).__name__,reason=str(exc) if isinstance(exc,ContractError) else 'SEE_NATIVE_FAILURE')
        finally:
            store.set('local-qualified',False);store.close()
            atomic_json(project.root_path/'artifacts/m0/ai/runs'/tid/'strata_worker_v1.json',record)
            atomic_json(project.root_path/'artifacts/m0/ai/strata_worker_v1.json',record)
        result=receipt('ai-qualify',exit_code=0 if record['state']=='MODEL_CHECKS_PASS_AUTOMATIC_DISABLED' else 3,reason=record['state']);result['result']={'path':'artifacts/m0/ai/strata_worker_v1.json','checks':record['checks'],'native_cancellation':record.get('native_cancellation','UNVERIFIED'),'automatic_dispatch_enabled':False};return result
