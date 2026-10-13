"""Shared synthetic packets; no provider or protected input is accessed."""
from datetime import datetime,timedelta,timezone
import hashlib
from uuid import uuid4
from compertum.foundation import fixture_spec
from compertum.domain import TaskSpec

def ai_task(root,provider='manual_subscription',*,deadline=2):
    value=fixture_spec(root).to_payload();task_id=value['task_id'];now=datetime.now(timezone.utc)
    value.update(role='research_proposer' if provider=='manual_subscription' else 'ai_adapter',
        kind='AI_PROPOSAL' if provider=='manual_subscription' else 'AI_QUALIFICATION',
        model_identity={'provider':provider,'model_label':'synthetic-model','sha256':'a'*64})
    value['permissions']['tools']=[];value['permissions']['network_destinations']=[] if provider=='manual_subscription' else ['http://127.0.0.1:8080']
    value['budget'].update(output_bytes=256*1024,ai_requests=3,input_tokens=16384,output_tokens=2048,request_deadline_seconds=deadline)
    relative=f'artifacts/ai/{task_id}/input/fixture.txt';path=root/relative;path.parent.mkdir(parents=True);path.write_text('M0 synthetic fixture: 2+2=4.')
    value['permissions']['filesystem_bundle']=[relative];value['input_hashes']=[hashlib.sha256(path.read_bytes()).hexdigest()]
    return TaskSpec(value,project_root=root),relative

def proposal(task,prompt_hash):
    p=task.to_payload()
    return {'schema_version':'1','record_type':'AIProposal','proposal_id':str(uuid4()),'task_id':p['task_id'],'role':p['role'],
        'created_at':datetime.now(timezone.utc).isoformat(),'prompt_sha256':prompt_hash,'input_hashes':p['input_hashes'],
        'provider':{'name':p['model_identity']['provider'],'model_label':'synthetic-model','usage_status':'UNKNOWN'},
        'state':'PROPOSAL_ONLY','summary':'Synthetic fixture only','assumptions':[],'falsifier':'Hash differs','citations':[],
        'proposed_patch':None,'fictional_tool_proposal':None}
