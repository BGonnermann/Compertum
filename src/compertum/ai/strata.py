"""Bounded loopback-only model requests. No tool executor, retries or credentials."""
import json,time,io,socket,http.client
from dataclasses import replace
from datetime import timedelta
import httpx
from ..domain import ContractError,canonical,ensure_safe,validate_record,now,utc_time,digest,file_hash
from .manual import claim_ai_task

BASE='http://127.0.0.1:8080'
MODEL='qwen3.8-flash-next-iq2_xs'

def native_post(body,timeout,port=8080,method='POST',path='/v1/chat/completions'):
    """Absolute deadline applies to every socket read, including slow headers/body."""
    end=time.monotonic()+timeout
    connection=http.client.HTTPConnection('127.0.0.1',port,timeout=timeout)
    class DeadlineReader(io.RawIOBase):
        def readable(self):return True
        def readinto(self,buf):
            remaining=end-time.monotonic()
            if remaining<=0:raise socket.timeout('OWNED_DEADLINE')
            connection.sock.settimeout(remaining)
            return connection.sock.recv_into(buf)
    class SocketView:
        def makefile(self,*args,**kwargs):return io.BufferedReader(DeadlineReader())
    try:
        connection.request(method,path,body=canonical(body) if method=='POST' else None,headers={'Content-Type':'application/json','Connection':'close'})
        response=http.client.HTTPResponse(SocketView());response.begin()
        if not 200<=response.status<300:raise ContractError('LOCAL_HTTP_FAILURE:'+str(response.status))
        data=bytearray()
        while chunk:=response.read(16384):
            if len(data)+len(chunk)>65536:raise ContractError('AI_RESPONSE_LIMIT')
            data.extend(chunk)
        response.close();return bytes(data)
    except (TimeoutError,socket.timeout):raise httpx.ReadTimeout('OWNED_DEADLINE') from None
    finally:connection.close()
def probe_strata(base_url=BASE,client=None,deadline_monotonic=None):
    if base_url!=BASE:raise ContractError('UNAPPROVED_ENDPOINT')
    own=client is None;c=client or httpx.Client(timeout=5,trust_env=False,follow_redirects=False)
    try:
        values={}
        for p in ('/health','/v1/models','/v1/status'):
            remaining=min(5,deadline_monotonic-time.monotonic()) if deadline_monotonic is not None else 5
            if remaining<=0:raise ContractError('AI_TASK_DEADLINE')
            values[p]=json.loads(native_post(None,remaining,method='GET',path=p)) if own else c.get(BASE+p,timeout=remaining).raise_for_status().json()
        status=values['/v1/status'];health=values['/health']
        if health.get('model')!=MODEL or status.get('model')!=MODEL or values['/v1/models']['data'][0]['id']!=MODEL:raise ContractError('MODEL_IDENTITY_CHANGED')
        if status['concurrency']['serving']!=1 or status['context']['max_positions']!=65536 or not health.get('loaded'):raise ContractError('SERVING_CAPABILITY_CHANGED')
        return {'at':now(),'model':MODEL,'engine':status['engine'],'context':65536,'slots':1,'in_flight':status['activity']['in_flight'],'structured_output':status['structured_output'],'modalities':['text'],'health':'AVAILABLE'}
    finally:
        if own:c.close()

def validate_fictional_call(call):
    if not isinstance(call,dict) or set(call)!={'id','type','function'} or call['type']!='function' or not isinstance(call['id'],str) or not 0<len(call['id'])<=256:raise ContractError('FICTIONAL_TOOL_SCHEMA')
    fn=call['function']
    if not isinstance(fn,dict) or set(fn)!={'name','arguments'} or fn['name']!='fixture_sum' or not isinstance(fn['arguments'],str) or len(fn['arguments'])>1024:raise ContractError('FICTIONAL_TOOL_SCHEMA')
    args=json.loads(fn['arguments'])
    if set(args)!={'a','b'} or any(type(args[k]) is not int for k in args) or args!={'a':2,'b':3}:raise ContractError('FICTIONAL_TOOL_ARGUMENTS')
    ensure_safe(call);return call

def request_proposal(store,task,messages,client=None,timeout=120,diagnostic=False,post=None,fictional_tools=False,fixture_result=None):
    if not 0<timeout<=120 or task.kind not in {'AI_PROPOSAL','AI_QUALIFICATION'}:raise ContractError('AI_REQUEST_CONTRACT')
    if (fictional_tools or fixture_result) and task.kind!='AI_QUALIFICATION':raise ContractError('QUALIFICATION_ONLY_TOOL_FIXTURE')
    issued=utc_time(now());expires=issued+timedelta(seconds=timeout)
    if task.deadline_at:expires=min(expires,utc_time(task.deadline_at))
    effective=(expires-issued).total_seconds()
    if effective<=0:raise ContractError('AI_TASK_DEADLINE')
    end=time.monotonic()+effective
    ensure_safe(messages)
    if not isinstance(messages,list) or not messages or len(messages)>8:raise ContractError('AI_CONTEXT_INVALID')
    for m in messages:
        if set(m)!={'role','content'} or m['role'] not in {'system','user','assistant'} or not isinstance(m['content'],str):raise ContractError('TOOL_EXECUTION_DENIED')
    if fixture_result:
        call=validate_fictional_call(fixture_result)
        messages=messages[:1]+[{'role':'assistant','content':None,'tool_calls':[call]},{'role':'tool','tool_call_id':call['id'],'content':'5'}]+messages[1:]
    contract=replace(task,input_hashes=(digest(messages),),code_hash=file_hash(__file__),expected_schema='fictional_tool_call' if fictional_tools else 'ai_proposal',deadline_at=expires.isoformat())
    # Conservative byte bound includes a fixed template margin; does not guess BPE ratios.
    if len(canonical(messages))+1024>task.budget.input_tokens:raise ContractError('AI_INPUT_LIMIT')
    own=client is None;c=client or httpx.Client(timeout=timeout,trust_env=False,follow_redirects=False)
    from ..runtime.jobs import ResourceSlot
    slot=ResourceSlot(store.lease.project)
    try:
        cap=probe_strata(client=None if own else c,deadline_monotonic=end)
        if cap['in_flight'] or store.get('local-timeout-unresolved',False):raise ContractError('LOCAL_BUSY_OR_UNCERTAIN')
        if not diagnostic:
            if store.get('local-qualified',False) is not True:raise ContractError('LOCAL_UNQUALIFIED')
            from ..storage import StorageManager
            if not StorageManager(store).check_storage()['admitted']:raise ContractError('ADMISSION_UNHEALTHY')
        claim_ai_task(store,task.task_id)
        day=now()[:10]
        with store.transaction():
            used=store.get('ai-requests:'+day,0);attempts=store.get('ai-attempts:'+task.task_id,0)
            if used>=40 or attempts>=task.budget.ai_requests:raise ContractError('AI_REQUEST_LIMIT')
            store.set('ai-requests:'+day,used+1);store.set('ai-attempts:'+task.task_id,attempts+1)
        body={'model':MODEL,'messages':messages,'temperature':0,'reasoning_effort':'none','stream':False,'max_tokens':min(2048,task.budget.output_tokens),'response_format':{'type':'json_object'},'tool_choice':'none','strata_mcp':False}
        if fictional_tools:
            body.pop('response_format');body['tools']=[{'type':'function','function':{'name':'fixture_sum','description':'Fictional qualification proposal only. No executable implementation.','parameters':{'type':'object','additionalProperties':False,'required':['a','b'],'properties':{'a':{'type':'integer'},'b':{'type':'integer'}}}}}]
            body['tool_choice']={'type':'function','function':{'name':'fixture_sum'}}
        start=time.monotonic()
        remaining=end-start
        if remaining<=0:raise ContractError('AI_TASK_DEADLINE')
        # Streaming transport bounds retained bytes even though server JSON is non-streaming.
        try:
            if post or own:data=(post or native_post)(body,remaining)
            else:
                # Deterministic contract-test transport only; production uses native deadline IO.
                with c.stream('POST',BASE+'/v1/chat/completions',json=body,timeout=timeout) as response:
                    response.raise_for_status();data=bytearray()
                    for chunk in response.iter_bytes(chunk_size=16384):
                        if len(data)+len(chunk)>65536:raise ContractError('AI_RESPONSE_LIMIT')
                        data.extend(chunk)
        except httpx.TimeoutException:
            store.set('local-timeout-unresolved',True);raise ContractError('LOCAL_TIMEOUT_UNVERIFIED') from None
        raw=json.loads(data);ensure_safe(raw);choice=raw['choices'][0];message=choice['message']
        usage=raw.get('usage',{})
        if usage.get('prompt_tokens',0)>16384 or usage.get('completion_tokens',0)>2048 or choice.get('finish_reason')=='length':raise ContractError('AI_TOKEN_LIMIT')
        calls=message.get('tool_calls')
        if fictional_tools:
            if not isinstance(calls,list) or len(calls)!=1:raise ContractError('FICTIONAL_TOOL_CALL_REQUIRED')
            call=validate_fictional_call(calls[0])
            return {'at':now(),'task':contract.record(),'fictional_tool_call':call,'messages':messages,'settings':body|{'messages':None},'usage':raw.get('usage',{}),'latency_seconds':time.monotonic()-start,'executed':False,'raw_response':raw,'capability':cap}
        if calls or message.get('function_call'):raise ContractError('TOOL_EXECUTION_DENIED')
        text=message.get('content')
        if not isinstance(text,str) or len(text.encode())>8192:raise ContractError('AI_OUTPUT_LIMIT')
        proposal=validate_record('ai_proposal',json.loads(text))
        if proposal['task_id']!=task.task_id:raise ContractError('TASK_MISMATCH')
        return {'at':now(),'task':contract.record(),'proposal':proposal,'messages':messages,'settings':body|{'messages':None},'usage':usage,'latency_seconds':time.monotonic()-start,'executed':False,'raw_response':raw,'capability':cap}
    except (KeyError,IndexError,TypeError,json.JSONDecodeError):raise ContractError('AI_RESPONSE_INVALID') from None
    finally:
        slot.close()
        if own:c.close()

def confirm_owned_timeout_idle(store):
    # No global cancellation. Verified idle only clears transport uncertainty;
    # native cancellation qualification is a separate, still unverified capability.
    cap=probe_strata()
    if cap['in_flight']!=0:raise ContractError('LOCAL_BUSY_OR_UNCERTAIN')
    store.set('local-timeout-unresolved',False);return cap
