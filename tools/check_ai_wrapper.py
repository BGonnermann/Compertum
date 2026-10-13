"""Native strict wrapper evidence; three live probes, no tool execution."""
import ctypes as C,json,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from compertum.domain import TaskSpec,Budget,now,new_id,atomic_json,ContractError,validate_record
from compertum.runtime.identity import resolve_project
from compertum.runtime.owners import acquire_owner
from compertum.runtime.supervisor import constrain_service
from compertum.runtime.jobs import launch_bounded,ExtendedLimits,QueryJob
from compertum.persistence import open_store
from compertum.ai.strata import request_proposal,probe_strata

def run(root):
    p=resolve_project(root);handle=constrain_service(256*1024**2,cpu_threads=1);actual=ExtendedLimits()
    assert QueryJob(handle,9,C.byref(actual),C.sizeof(actual),None) and actual.job_memory==256*1024**2 and actual.basic.affinity==1
    with acquire_owner(p,'coordinator') as lease:
        store=open_store(lease,'coordinator');prior=json.loads((root/'artifacts/m0/ai/strata_worker_v1.json').read_text());record={'at':now(),'parent_memory_bytes':actual.job_memory,'cpu_mask':actual.basic.affinity,'checks':{},'requests':[],'full_current_profile':'UNVERIFIED_DAILY_REQUEST_BUDGET','automatic_dispatch':False}
        day=now()[:10];used=store.get('cpu:'+day,0)
        if used+600>7200:raise ContractError('DAILY_CPU_LIMIT')
        store.set('cpu:'+day,used+600)
        try:
            job=launch_bounded(lease,TaskSpec(budget=Budget(cpu_threads=1,wall_seconds=600,output_bytes=1024**2)),['model_identity_hash']).wait();record['hash_job']=job
            assert job['exit_code']==0 and job['active_processes']==0 and not job['timed_out']
            current=json.loads(job['stdout']);assert {r['path']:r['sha256'] for r in current}=={r['path']:r['sha256'] for r in prior['identity_files']};record['identity_files']=current;record['checks']['same_model_native_hash']=True
            task=TaskSpec(kind='AI_QUALIFICATION',role='proposer',permissions=('model_proposal','loopback'),budget=Budget(cpu_threads=1,ram_bytes=256*1024**2,ai_requests=3,output_tokens=256));tid=task.task_id
            system='Return only the JSON object '+json.dumps({'schema_version':1,'task_id':tid,'summary':'5','claims':[],'limitations':[]})
            first=request_proposal(store,task,[{'role':'system','content':system},{'role':'user','content':'Return the specified JSON.'}],diagnostic=True);record['requests'].append(first);record['checks']['json']=first['proposal']['summary']=='5'
            tool=request_proposal(store,task,[{'role':'user','content':'Propose the fictional fixture_sum with a=2 and b=3.'}],diagnostic=True,fictional_tools=True);record['requests'].append(tool);record['checks']['structured_tool']=bool(tool['fictional_tool_call'])
            second=request_proposal(store,task,[{'role':'system','content':system},{'role':'user','content':'Use the dispatcher-supplied fictional result. Return the exact specified JSON object.'}],diagnostic=True,fixture_result=tool['fictional_tool_call']);record['requests'].append(second);record['checks']['second_turn']=second['proposal']['summary']=='5'
            record['state']='VERIFIED_PASS' if all(record['checks'].values()) else 'VERIFIED_FAIL'
        except Exception as exc:record.update(state='VERIFIED_FAIL',failure=type(exc).__name__,reason=str(exc) if isinstance(exc,ContractError) else 'NATIVE_CHECK_FAILED')
        finally:store.set('local-qualified',False);store.close();atomic_json(root/'artifacts/m0/ai/strict_wrapper.json',record)
        return {'state':record['state'],'checks':record['checks'],'full_current_profile':record['full_current_profile']}

if __name__=='__main__':print(json.dumps(run(Path(__file__).resolve().parents[1]),sort_keys=True))
