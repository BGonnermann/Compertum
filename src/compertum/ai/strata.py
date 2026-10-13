"""Direct bounded loopback proposals; qualification never enables execution."""
import asyncio
from dataclasses import dataclass
from datetime import datetime,timezone
import hashlib
import json
import time
from urllib.parse import urlsplit
import httpx
from compertum.domain import TaskSpec,validate_record,ContractError
from compertum.events import canonical,uuid
from compertum.runtime.errors import RuntimeRefused
from compertum.runtime.jobs import _ACTIVE
from .manual import sanitized,read_json

@dataclass(frozen=True)
class StrataProfile:
    base_url:str
    model_id:str
    identity_sha256:str
    qualified:bool=False

class StrataAdapter:
    def __init__(self,bridge,profile,*,token_counter=None,_fixture_port=None):
        parsed=urlsplit(profile.base_url)
        if (parsed.scheme!='http' or parsed.hostname!='127.0.0.1' or parsed.username or parsed.password
                or parsed.path not in ('','/') or parsed.query or parsed.fragment or not parsed.port):
            raise RuntimeRefused('NON_LOOPBACK_DENIED')
        if profile.base_url!='http://127.0.0.1:8080': raise RuntimeRefused('ENDPOINT_NOT_APPROVED')
        if _fixture_port is not None and (profile.qualified or type(_fixture_port) is not int or not 1024<=_fixture_port<=65535): raise RuntimeRefused('FIXTURE_ENDPOINT_DENIED')
        self.base_url=profile.base_url if _fixture_port is None else f'http://127.0.0.1:{_fixture_port}'
        self.fixture_endpoint=_fixture_port is not None
        if not profile.model_id or len(profile.model_id)>256: raise RuntimeRefused('MODEL_IDENTITY_UNVERIFIED')
        self.bridge=bridge;self.store=bridge.store;self.profile=profile;self.token_counter=token_counter
        with self.store._live(),self.store.conn:
            self.store.conn.execute('CREATE TABLE IF NOT EXISTS local_ai_receipts(request_id TEXT PRIMARY KEY,receipt TEXT NOT NULL)')
            self.store.conn.execute('CREATE TABLE IF NOT EXISTS local_ai_state(key TEXT PRIMARY KEY,value TEXT NOT NULL)')
            # An interrupted client cannot establish that its server work ended.
            self.store.conn.execute("UPDATE local_ai_state SET value='OWNED_REQUEST_UNCERTAIN' WHERE key='dispatch' AND value='IN_FLIGHT'")

    def state(self):
        with self.store._live():
            row=self.store.conn.execute("SELECT value FROM local_ai_state WHERE key='dispatch'").fetchone()
            return row[0] if row else 'IDLE'

    def _state(self,value):
        with self.store.conn: self.store.conn.execute("INSERT INTO local_ai_state VALUES('dispatch',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(value,))

    async def _json(self,client,method,path,*,payload=None):
        async with client.stream(method,self.base_url.rstrip('/')+path,json=payload) as response:
            response.raise_for_status();raw=bytearray()
            async for chunk in response.aiter_bytes():
                if len(raw)+len(chunk)>65536: raise RuntimeRefused('AI_RESPONSE_BOUND')
                raw.extend(chunk)
            value=read_json(bytes(raw))
            if path=='/health' and isinstance(value,dict) and 'api_key' in value:
                # Strata advertises only whether authentication is configured.
                # No credential-shaped value or other endpoint gets this exception.
                if type(value['api_key']) is not bool: raise RuntimeRefused('AI_SENSITIVE_INPUT_DENIED')
                value={k:v for k,v in value.items() if k!='api_key'}|{'authentication_configured':value['api_key']}
                raw=canonical(value)
            sanitized(bytes(raw));return value,bytes(raw)

    async def _health(self,client):
        health,_=await self._json(client,'GET','/health')
        if not isinstance(health,dict) or health.get('loaded') is not True: raise RuntimeRefused('PROVIDER_IDLE_UNVERIFIED')
        if 'active_requests' in health:
            if type(health['active_requests']) is not int or health['active_requests']!=0: raise RuntimeRefused('PROVIDER_IDLE_UNVERIFIED')
        elif health.get('service')=='strata':
            slots,_=await self._json(client,'GET','/slots')
            if not isinstance(slots,list) or not 1<=len(slots)<=16 or any(not isinstance(s,dict) or s.get('is_processing') is not False for s in slots):
                raise RuntimeRefused('PROVIDER_IDLE_UNVERIFIED')
        else: raise RuntimeRefused('PROVIDER_IDLE_UNVERIFIED')
        return {'loaded':True,'idle_observed':True,'observation_monotonic':time.monotonic()}

    def probe_strata(self):
        """Explicit read-only health/model probe; never invoked by doctor/status."""
        async def probe():
            async with asyncio.timeout(5):
                async with httpx.AsyncClient(trust_env=False,follow_redirects=False,timeout=5) as client:
                    health=await self._health(client);models,_=await self._json(client,'GET','/v1/models')
                    if not isinstance(models,dict) or not isinstance(models.get('data'),list) or self.profile.model_id not in [m.get('id') for m in models['data'] if isinstance(m,dict)]:
                        raise RuntimeRefused('MODEL_IDENTITY_MISMATCH')
                    return {'status':'IDLE_OBSERVED','model_id':self.profile.model_id,'health':health,'qualified':False}
        return asyncio.run(probe())

    async def _request(self,payload,seconds):
        async with asyncio.timeout(seconds):
            async with httpx.AsyncClient(trust_env=False,follow_redirects=False,timeout=seconds) as client:
                await self._health(client)
                models,_=await self._json(client,'GET','/v1/models')
                if not isinstance(models,dict) or not isinstance(models.get('data'),list) or self.profile.model_id not in [m.get('id') for m in models['data'] if isinstance(m,dict)]:
                    raise RuntimeRefused('MODEL_IDENTITY_MISMATCH')
                return await self._json(client,'POST','/v1/chat/completions',payload=payload)

    def request_proposal(self,task,messages,*,validate_proposal=True,approved_fixture_id=None,fixture_result_for=None):
        if not isinstance(task,TaskSpec): raise RuntimeRefused('AI_TASK_DENIED')
        if not self.fixture_endpoint:
            from compertum.runtime.managed import constrain_ai_adapter
            self.native_limits=constrain_ai_adapter()
        p=task.to_payload();budget=p['budget']
        if (p['kind'] not in {'AI_PROPOSAL','AI_QUALIFICATION'} or p['model_identity']['provider']!='strata'
                or p['model_identity']['model_label']!=self.profile.model_id
                or p['model_identity']['sha256']!=self.profile.identity_sha256):
            raise RuntimeRefused('MODEL_IDENTITY_MISMATCH')
        if p['permissions']['network_destinations']!=['http://127.0.0.1:8080']: raise RuntimeRefused('NETWORK_PERMISSION_DENIED')
        if (self.fixture_endpoint or not validate_proposal) and p['kind']!='AI_QUALIFICATION': raise RuntimeRefused('AI_TASK_DENIED')
        if p['kind']!='AI_QUALIFICATION' and not self.profile.qualified: raise RuntimeRefused('LOCAL_PROFILE_UNQUALIFIED')
        if self.token_counter is None: raise RuntimeRefused('TOKENIZER_UNVERIFIED')
        if (not isinstance(messages,list) or not 1<=len(messages)<=8
                or any(not isinstance(m,dict) or set(m)!={'role','content'} or m['role'] not in {'system','user','assistant'} or not isinstance(m['content'],str) for m in messages)):
            raise RuntimeRefused('AI_MESSAGES_DENIED')
        if approved_fixture_id is not None:
            uuid(approved_fixture_id)
            if p['kind']!='AI_QUALIFICATION' or 'propose_fixture_tool' not in p['permissions']['tools'] or validate_proposal:
                raise RuntimeRefused('AI_TOOL_EXECUTION_DENIED')
        if fixture_result_for is not None:
            prior=fixture_result_for
            with self.store._live():
                binding=self.store.conn.execute("SELECT task_id,status FROM ai_requests WHERE request_id=?",(prior.get('request_id'),)).fetchone()
            if binding!=(p['task_id'],'COMPLETED') or prior.get('task_id')!=p['task_id'] or prior.get('fictional_call') is None:
                raise RuntimeRefused('AI_CONTEXT_ISOLATION')
            retained=self.store.conn.execute('SELECT receipt FROM local_ai_receipts WHERE request_id=?',(prior['request_id'],)).fetchone()
            if retained is None or json.loads(retained[0])!=prior: raise RuntimeRefused('AI_CONTEXT_ISOLATION')
            call=prior['fictional_call']
            if call['function']['name']!='fixture_lookup': raise RuntimeRefused('AI_TOOL_EXECUTION_DENIED')
            # A dispatcher-supplied constant is the entire tool implementation.
            # No caller content is interpreted as a tool, path or executable.
            messages=[*messages,{'role':'assistant','content':None,'tool_calls':[call]},
                {'role':'tool','tool_call_id':call['id'],'content':'{"fixture_value":7,"synthetic":true}'}]
        sanitized(canonical(messages))
        seconds=min(120,budget['request_deadline_seconds'])
        remaining=(datetime.fromisoformat(p['deadline_at'])-datetime.now(timezone.utc)).total_seconds()
        if seconds<=0 or remaining<=0: raise RuntimeRefused('TASK_DEADLINE_EXCEEDED')
        prompt_hash=hashlib.sha256(canonical(messages)).hexdigest()
        payload={'model':self.profile.model_id,'messages':messages,'temperature':0,'stream':False,
                 'reasoning_effort':'none','max_tokens':min(2048,budget['output_tokens']),'response_format':{'type':'json_object'}}
        if approved_fixture_id is not None:
            payload.pop('response_format')
            payload['tools']=[{'type':'function','function':{'name':'fixture_lookup','description':'Propose a fictional synthetic lookup. No real effect.',
                'parameters':{'type':'object','properties':{'fixture_id':{'type':'string','enum':[approved_fixture_id]}},'required':['fixture_id'],'additionalProperties':False}}}]
            payload['tool_choice']={'type':'function','function':{'name':'fixture_lookup'}}
            payload['parallel_tool_calls']=False
        # Count the fully rendered request, including offered tools/settings.
        # Native qualification supplies the exact recorded tokenizer/template.
        tokens=self.token_counter(payload)
        if type(tokens) is not int or not 0<=tokens<=min(16384,budget['input_tokens']): raise RuntimeRefused('AI_CONTEXT_BOUND')
        with self.store._live():
            if self.state()!='IDLE': raise RuntimeRefused('LOCAL_DISPATCH_BLOCKED')
            if self.store.lease.project_id in _ACTIVE: raise RuntimeRefused('JOB_SLOT_BUSY')
            self.bridge.bind_budget(task);self.bridge.admit_task(p['task_id']);request_id=self.bridge.admit_request(p['task_id'],budget['ai_requests'],'STRATA')
        request_artifact=self.bridge._retain(p['task_id'],f'request-{request_id}.json',canonical({'task':p,'payload':payload,'input_tokens':tokens,'deadline_seconds':min(seconds,remaining)}))
        with self.store._live(): self._state('IN_FLIGHT')
        started=time.monotonic()
        # Keep the slot durably occupied across the network await. Trusted local
        # dispatch checks it too; caller context is copied, never accumulated.
        try:
            response,raw=asyncio.run(self._request(payload,min(seconds,remaining)))
            artifact=self.bridge._retain(p['task_id'],f'local-{request_id}.json',raw)
            if not isinstance(response,dict): raise RuntimeRefused('AI_RESPONSE_INVALID')
            choices=response.get('choices')
            if not isinstance(choices,list) or len(choices)!=1: raise RuntimeRefused('AI_RESPONSE_INVALID')
            if not isinstance(choices[0],dict): raise RuntimeRefused('AI_RESPONSE_INVALID')
            message=choices[0].get('message',{});fictional_call=None
            if not isinstance(message,dict): raise RuntimeRefused('AI_RESPONSE_INVALID')
            if approved_fixture_id is not None:
                calls=message.get('tool_calls')
                if not isinstance(calls,list) or len(calls)!=1 or choices[0].get('finish_reason')!='tool_calls': raise RuntimeRefused('AI_TOOL_EXECUTION_DENIED')
                call=calls[0]
                if (not isinstance(call,dict) or set(call)!={'id','type','function'} or call['type']!='function'
                        or not isinstance(call['id'],str) or not 1<=len(call['id'])<=128 or not isinstance(call['function'],dict)
                        or set(call['function'])!={'name','arguments'} or call['function']['name']!='fixture_lookup'
                        or read_json(call['function']['arguments'])!={'fixture_id':approved_fixture_id}): raise RuntimeRefused('AI_TOOL_EXECUTION_DENIED')
                fictional_call=call;proposal={'name':'fixture_lookup','arguments':{'fixture_id':approved_fixture_id}}
            else:
                if message.get('tool_calls') or message.get('function_call'): raise RuntimeRefused('AI_TOOL_EXECUTION_DENIED')
                content=message.get('content')
                if not isinstance(content,str) or choices[0].get('finish_reason')!='stop': raise RuntimeRefused('AI_RESPONSE_INCOMPLETE')
                if len(content.encode())>budget['output_tokens']: raise RuntimeRefused('AI_OUTPUT_BOUND')
                proposal=read_json(content)
            if validate_proposal:
                proposal=validate_record('ai_proposal.v1',proposal)
                if (proposal['task_id']!=p['task_id'] or proposal['role']!=p['role'] or proposal['input_hashes']!=p['input_hashes']
                        or proposal['prompt_sha256']!=prompt_hash or proposal['provider']['name']!='strata'
                        or proposal['provider']['model_label']!=self.profile.model_id): raise RuntimeRefused('AI_RESPONSE_MISMATCH')
            usage=response.get('usage')
            if usage is not None:
                if (not isinstance(usage,dict) or type(usage.get('prompt_tokens')) is not int or type(usage.get('completion_tokens')) is not int
                        or not 0<=usage['prompt_tokens']<=budget['input_tokens'] or not 0<=usage['completion_tokens']<=budget['output_tokens']):
                    raise RuntimeRefused('AI_USAGE_BOUND')
            receipt={'status':'PROPOSAL_ONLY','task_id':p['task_id'],'request_id':request_id,'proposal':proposal,
                'original':artifact,'request_artifact':request_artifact,'prompt_sha256':prompt_hash,'elapsed_seconds':time.monotonic()-started,'usage':usage,
                'usage_status':'MEASURED' if usage is not None else 'UNKNOWN','executed':False,'fictional_call':fictional_call}
        except (TimeoutError,httpx.TimeoutException,httpx.TransportError):
            with self.store._live(): self._state('OWNED_REQUEST_UNCERTAIN')
            raise RuntimeRefused('LOCAL_COMPLETION_UNVERIFIED') from None
        except (RuntimeRefused,ContractError,httpx.HTTPStatusError,KeyError,TypeError,ValueError) as error:
            # A complete HTTP error/schema response ends this owned transport;
            # no automatic retry, repair request or global cancellation occurs.
            with self.store._live(): self._state('OWNED_REQUEST_UNCERTAIN' if isinstance(error,RuntimeRefused) and error.code=='AI_RESPONSE_BOUND' else 'IDLE')
            raise RuntimeRefused('AI_RESPONSE_REJECTED') from None
        else:
            with self.store._live(),self.store.conn:
                self._state('IDLE');self.store.conn.execute("UPDATE ai_requests SET status='COMPLETED' WHERE request_id=?",(request_id,))
                self.store.conn.execute('INSERT INTO local_ai_receipts VALUES(?,?)',(request_id,canonical(receipt).decode()))
            return receipt

    def recover_idle(self):
        async def probe():
            async with asyncio.timeout(5):
                async with httpx.AsyncClient(trust_env=False,follow_redirects=False,timeout=5) as client:
                    return await self._health(client)
        asyncio.run(probe())
        with self.store._live(): self._state('IDLE')
        return {'status':'IDLE_OBSERVED','automatic_capability':'UNVERIFIED'}


