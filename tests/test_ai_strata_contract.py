import json,httpx,pytest
from compertum.ai.strata import request_proposal,probe_strata,MODEL
from compertum.domain import ContractError,TaskSpec,Budget
from compertum.runtime.identity import resolve_project
from compertum.runtime.owners import acquire_owner
from compertum.persistence import open_store

def transport(task,kind,seen):
    def reply(request):
        seen.append(request)
        if request.url.path=='/health':return httpx.Response(200,json={'model':MODEL,'loaded':True})
        if request.url.path=='/v1/models':return httpx.Response(200,json={'data':[{'id':MODEL}]})
        if request.url.path=='/v1/status':return httpx.Response(200,json={'model':MODEL,'engine':'fixture','concurrency':{'serving':1},'context':{'max_positions':65536},'activity':{'in_flight':0},'structured_output':{}})
        if kind=='http':return httpx.Response(503)
        if kind=='malformed':return httpx.Response(200,content=b'not-json')
        message={'content':json.dumps({'schema_version':1,'task_id':task.task_id,'summary':'OK'})}
        if kind=='tool':message['tool_calls']=[{'function':'fictional'}]
        if kind=='mismatch':message['content']=json.dumps({'schema_version':1,'task_id':'other','summary':'OK'})
        return httpx.Response(200,json={'choices':[{'message':message,'finish_reason':'stop'}],'usage':{'prompt_tokens':100,'completion_tokens':10}})
    return httpx.MockTransport(reply)

@pytest.mark.parametrize('kind',['malformed','http','tool','mismatch','valid'])
def test_strict_response_and_no_retry(tmp_path,kind):
    with acquire_owner(resolve_project(tmp_path),'coordinator') as lease:
        store=open_store(lease,'coordinator');task=TaskSpec(kind='AI_QUALIFICATION');seen=[]
        with httpx.Client(transport=transport(task,kind,seen),trust_env=False) as client:
            if kind=='valid':assert request_proposal(store,task,[{'role':'user','content':'fixture'}],client=client,diagnostic=True)['executed'] is False
            else:
                with pytest.raises((ContractError,httpx.HTTPError)):request_proposal(store,task,[{'role':'user','content':'fixture'}],client=client,diagnostic=True)
        assert len([r for r in seen if r.method=='POST'])==1
        assert store.get('ai-requests:'+__import__('compertum.domain',fromlist=['now']).now()[:10])==1;store.close()

def test_input_context_endpoint_and_request_limit(tmp_path):
    with pytest.raises(ContractError,match='ENDPOINT'):probe_strata('https://example.com')
    with acquire_owner(resolve_project(tmp_path),'coordinator') as lease:
        store=open_store(lease,'coordinator');task=TaskSpec(kind='AI_QUALIFICATION',budget=Budget(ai_requests=1));seen=[]
        with httpx.Client(transport=transport(task,'valid',seen),trust_env=False) as client:
            with pytest.raises(ContractError,match='INPUT'):request_proposal(store,task,[{'role':'user','content':'x'*17000}],client=client,diagnostic=True)
            with pytest.raises(ContractError,match='TOOL'):request_proposal(store,task,[{'role':'tool','content':'fake'}],client=client,diagnostic=True)
            request_proposal(store,task,[{'role':'user','content':'one'}],client=client,diagnostic=True)
            with pytest.raises(ContractError,match='LIMIT'):request_proposal(store,task,[{'role':'user','content':'two'}],client=client,diagnostic=True)
        store.close()

def test_incoming_deadline_is_preserved_or_expired_without_io(tmp_path):
    from datetime import timedelta
    from compertum.domain import utc_time,now
    with acquire_owner(resolve_project(tmp_path),'coordinator') as lease:
        store=open_store(lease,'coordinator');seen=[];expired=TaskSpec(kind='AI_QUALIFICATION',deadline_at='2000-01-01T00:00:00Z')
        with httpx.Client(transport=transport(expired,'valid',seen),trust_env=False) as c:
            with pytest.raises(ContractError,match='DEADLINE'):request_proposal(store,expired,[{'role':'user','content':'x'}],client=c,diagnostic=True)
        assert not seen
        deadline=(utc_time(now())+timedelta(seconds=2)).isoformat();task=TaskSpec(kind='AI_QUALIFICATION',deadline_at=deadline)
        with httpx.Client(transport=transport(task,'valid',seen),trust_env=False) as c:r=request_proposal(store,task,[{'role':'user','content':'x'}],client=c,diagnostic=True)
        assert utc_time(r['task']['deadline_at'])==utc_time(deadline);store.close()

def test_only_fixed_fictional_call_is_admitted_without_execution(tmp_path):
    from compertum.ai.strata import validate_fictional_call
    call={'id':'fictional-call','type':'function','function':{'name':'fixture_sum','arguments':'{"a":2,"b":3}'}}
    assert validate_fictional_call(call)==call
    with pytest.raises(ContractError):validate_fictional_call({**call,'function':{'name':'filesystem_write','arguments':'{}'}})
    with acquire_owner(resolve_project(tmp_path),'coordinator') as lease:
        store=open_store(lease,'coordinator');task=TaskSpec(kind='AI_QUALIFICATION');seen=[];base=transport(task,'valid',seen)
        def response(request):
            if request.method!='POST':return base.handle_request(request)
            body=json.loads(request.content);assert 'response_format' not in body and body['tools'][0]['function']['name']=='fixture_sum' and body['strata_mcp'] is False
            return httpx.Response(200,json={'choices':[{'message':{'role':'assistant','content':None,'tool_calls':[call]},'finish_reason':'tool_calls'}],'usage':{'prompt_tokens':150,'completion_tokens':20}})
        with httpx.Client(transport=httpx.MockTransport(response),trust_env=False) as c:r=request_proposal(store,task,[{'role':'user','content':'a2b3'}],client=c,diagnostic=True,fictional_tools=True)
        assert r['executed'] is False and r['fictional_tool_call']==call and not (tmp_path/'executed').exists();store.close()
