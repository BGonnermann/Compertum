"""One loopback Chat Completions interface for every AI role. The ledger records each call and each refusal."""
import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import math
from pathlib import Path
import time
import tomllib
from types import MappingProxyType
from urllib.parse import urlsplit
from uuid import uuid4
import httpx
from compertum.domain import ContractError,resolve_project_path
from compertum.events import canonical
from compertum.runtime.errors import RuntimeRefused
from compertum.runtime.jobs import available_physical_memory
from .manual import sanitized,read_json

ENGINE_ROLES=frozenset({'director','researcher','mathematician','engineer'})
PROVIDER='loopback'
MAX_BYTES=65536


@dataclass(frozen=True)
class RoleModel:
    role:str
    base_url:str
    model:str


def loopback_base_url(value):
    # Section 19: the address must be loopback, on any port. Nothing else is admitted.
    if not isinstance(value,str) or not 1<=len(value)<=256: raise RuntimeRefused('NON_LOOPBACK_DENIED')
    parsed=urlsplit(value)
    try: port=parsed.port
    except ValueError: raise RuntimeRefused('NON_LOOPBACK_DENIED') from None
    if (parsed.scheme!='http' or parsed.hostname not in ('127.0.0.1','localhost') or parsed.username is not None
            or parsed.password is not None or parsed.query or parsed.fragment or parsed.path.rstrip('/') not in ('','/v1')
            or port is None or not 1<=port<=65535):
        raise RuntimeRefused('NON_LOOPBACK_DENIED')
    return f'http://{parsed.hostname}:{port}/v1'


def recorded_number(value):
    # Only finite numbers enter a ledger record. Anything else is stored as None, and the settings check refuses it.
    return value if type(value) is int or (type(value) is float and math.isfinite(value)) else None


def model_id(value):
    if (not isinstance(value,str) or not 1<=len(value)<=256 or value!=value.strip()
            or any(ord(ch)<32 or ord(ch)==127 for ch in value)):
        raise RuntimeRefused('MODEL_IDENTITY_UNVERIFIED')
    return value


def load_models(path,project_root):
    """Read the bounded role file inside the project. Every role gets exactly one loopback model."""
    root=Path(project_root).absolute()
    try: relative=Path(path).absolute().relative_to(root).as_posix()
    except ValueError: raise RuntimeRefused('CONFIG_OUTSIDE_PROJECT') from None
    try:
        with resolve_project_path(relative,root).open('rb') as stream: raw=stream.read(MAX_BYTES+1)
    except ContractError as error: raise RuntimeRefused(error.reason) from None
    except OSError: raise RuntimeRefused('CONFIG_UNAVAILABLE') from None
    if len(raw)>MAX_BYTES: raise RuntimeRefused('CONFIG_TOO_LARGE')
    try: supplied=tomllib.loads(raw.decode('utf-8'))
    except (UnicodeError,tomllib.TOMLDecodeError): raise RuntimeRefused('INVALID_CONFIG') from None
    roles=supplied.get('roles') if supplied.keys()=={'roles'} else None
    if not isinstance(roles,dict) or roles.keys()!=ENGINE_ROLES: raise RuntimeRefused('UNKNOWN_CONFIG_FIELD')
    result={}
    for role in sorted(ENGINE_ROLES):
        entry=roles[role]
        if not isinstance(entry,dict) or entry.keys()!={'base_url','model'}: raise RuntimeRefused('UNKNOWN_CONFIG_FIELD')
        result[role]=RoleModel(role,loopback_base_url(entry['base_url']),model_id(entry['model']))
    return MappingProxyType(result)


class StoreLedger:
    """Durable per-call records in the project store. Rows are inserted once and never rewritten."""
    def __init__(self,store):
        self.store=store
        with self.store._live(),self.store.conn:
            self.store.conn.execute('CREATE TABLE IF NOT EXISTS engine_model_calls(call_id TEXT PRIMARY KEY,role TEXT NOT NULL,status TEXT NOT NULL,record TEXT NOT NULL)')

    def record(self,entry):
        with self.store._live(),self.store.conn:
            self.store.conn.execute('INSERT INTO engine_model_calls VALUES(?,?,?,?)',(entry['call_id'],entry['role'],entry['status'],canonical(entry).decode()))
        return entry

    def rows(self):
        with self.store._live():
            return [read_json(row[0]) for row in self.store.conn.execute('SELECT record FROM engine_model_calls ORDER BY rowid')]


class ModelClient:
    """Send one bounded Chat Completions request per call. Check memory, the request limit and the server's model first.

    WARNING: with native_limits=True (the default) construction puts the CALLING PROCESS into a one-thread,
    256 MiB, no-child Job for the rest of its life. Only a dedicated adapter process may construct it that way.
    The supervisor, the coordinator and tests must pass native_limits=False.
    """
    def __init__(self,roles,ledger,*,memory_floor_bytes,request_limit,available_memory=available_physical_memory,native_limits=True):
        if (not isinstance(roles,Mapping) or roles.keys()!=ENGINE_ROLES
                or any(not isinstance(spec,RoleModel) or spec.role!=role for role,spec in roles.items())):
            raise RuntimeRefused('UNKNOWN_CONFIG_FIELD')
        # The sender checks every address and model ID again. A RoleModel built by hand gets no exemption.
        for spec in roles.values():
            if loopback_base_url(spec.base_url)!=spec.base_url or model_id(spec.model)!=spec.model: raise RuntimeRefused('UNKNOWN_CONFIG_FIELD')
        if type(memory_floor_bytes) is not int or memory_floor_bytes<1: raise RuntimeRefused('AVAILABLE_RAM_UNVERIFIED')
        if type(request_limit) is not int or not 1<=request_limit<=10000: raise RuntimeRefused('AI_REQUEST_BUDGET')
        self.roles=roles;self.ledger=ledger;self.memory_floor_bytes=memory_floor_bytes;self.request_limit=request_limit
        self.available_memory=available_memory;self.requests=0;self.native_limits=None
        if native_limits:
            # The same one-thread, 256 MiB, no-child Job as the Strata adapter. The supervisor never uses this client.
            from compertum.runtime.managed import constrain_ai_adapter
            self.native_limits=constrain_ai_adapter()

    def _spec(self,role):
        if role not in self.roles: raise RuntimeRefused('AI_ROLE_DENIED')
        return self.roles[role]

    async def _json(self,client,method,url,*,payload=None):
        async with client.stream(method,url,json=payload) as response:
            response.raise_for_status();raw=bytearray()
            async for chunk in response.aiter_bytes():
                if len(raw)+len(chunk)>MAX_BYTES: raise RuntimeRefused('AI_RESPONSE_BOUND')
                raw.extend(chunk)
        sanitized(bytes(raw));return read_json(bytes(raw)),bytes(raw)

    async def _reported_model(self,client,spec):
        models,_=await self._json(client,'GET',spec.base_url+'/models')
        data=models.get('data') if isinstance(models,dict) else None
        ids=[m.get('id') for m in data if isinstance(m,dict)] if isinstance(data,list) else []
        if spec.model not in ids: raise RuntimeRefused('MODEL_IDENTITY_MISMATCH')
        return spec.model

    def probe(self,role):
        """Read-only check that the server lists the configured model. It sends no completion."""
        spec=self._spec(role)
        async def run():
            async with asyncio.timeout(5):
                async with httpx.AsyncClient(trust_env=False,follow_redirects=False,timeout=5) as client:
                    return await self._reported_model(client,spec)
        return asyncio.run(run())

    async def _request(self,spec,payload,seconds):
        async with asyncio.timeout(seconds):
            async with httpx.AsyncClient(trust_env=False,follow_redirects=False,timeout=seconds) as client:
                reported=await self._reported_model(client,spec)
                response,raw=await self._json(client,'POST',spec.base_url+'/chat/completions',payload=payload)
                return reported,response,raw

    def complete(self,role,messages,*,purpose,max_tokens=2048,temperature=0,seconds=120):
        # Build the ledger entry first, so that an unknown role or an unexpected failure is still recorded.
        spec=self.roles.get(role) if isinstance(role,str) else None;started=time.monotonic()
        entry={'call_id':str(uuid4()),'role':role if isinstance(role,str) and len(role)<=64 else 'INVALID_ROLE',
               'purpose':purpose if isinstance(purpose,str) and len(purpose)<=256 else None,'provider':PROVIDER,
               'address':spec.base_url if spec else None,'model_requested':spec.model if spec else None,'model_reported':None,
               'settings':{'temperature':recorded_number(temperature),'max_tokens':recorded_number(max_tokens),
                           'request_seconds':recorded_number(seconds),'stream':False},
               'prompt_sha256':None,'response_sha256':None,'usage':None,'elapsed_seconds':None,
               'available_memory_bytes':None,'memory_floor_bytes':self.memory_floor_bytes,
               'request_index':self.requests+1,'request_limit':self.request_limit,'status':None}
        try:
            if spec is None: raise RuntimeRefused('AI_ROLE_DENIED')
            if not isinstance(purpose,str) or not 1<=len(purpose)<=256: raise RuntimeRefused('AI_TASK_DENIED')
            if (type(max_tokens) is not int or not 1<=max_tokens<=16384 or type(seconds) is not int or not 1<=seconds<=600
                    or type(temperature) not in (int,float) or not 0<=temperature<=2): raise RuntimeRefused('AI_SETTINGS_DENIED')
            if self.requests>=self.request_limit: raise RuntimeRefused('AI_REQUEST_BUDGET')
            available=self.available_memory();entry['available_memory_bytes']=available
            if type(available) is not int or available<self.memory_floor_bytes: raise RuntimeRefused('AVAILABLE_RAM_FLOOR')
            if (not isinstance(messages,list) or not 1<=len(messages)<=64
                    or any(not isinstance(m,dict) or set(m)!={'role','content'} or m['role'] not in {'system','user','assistant'}
                           or not isinstance(m['content'],str) for m in messages)):
                raise RuntimeRefused('AI_MESSAGES_DENIED')
            prompt=canonical(messages);sanitized(prompt);entry['prompt_sha256']=hashlib.sha256(prompt).hexdigest()
            # The attempt counts before any byte leaves. A failed request still uses a request.
            self.requests+=1
            payload={'model':spec.model,'messages':messages,'temperature':temperature,'max_tokens':max_tokens,'stream':False}
            try:
                reported,response,raw=asyncio.run(self._request(spec,payload,seconds))
                entry['model_reported']=reported;entry['response_sha256']=hashlib.sha256(raw).hexdigest()
                choices=response.get('choices') if isinstance(response,dict) else None
                if not isinstance(choices,list) or len(choices)!=1 or not isinstance(choices[0],dict): raise RuntimeRefused('AI_RESPONSE_INVALID')
                message=choices[0].get('message')
                if not isinstance(message,dict) or message.get('tool_calls') or message.get('function_call'): raise RuntimeRefused('AI_TOOL_EXECUTION_DENIED')
                content=message.get('content')
                if not isinstance(content,str) or choices[0].get('finish_reason')!='stop': raise RuntimeRefused('AI_RESPONSE_INCOMPLETE')
                usage=response.get('usage')
                if usage is not None:
                    if (not isinstance(usage,dict) or type(usage.get('prompt_tokens')) is not int
                            or type(usage.get('completion_tokens')) is not int): raise RuntimeRefused('AI_USAGE_BOUND')
                    # Keep only the token counts. A server-sized dict must not grow the record past its bound.
                    usage={k:usage[k] for k in ('prompt_tokens','completion_tokens','total_tokens') if type(usage.get(k)) is int}
            except (TimeoutError,httpx.TimeoutException,httpx.TransportError):
                raise RuntimeRefused('LOCAL_COMPLETION_UNVERIFIED') from None
            except RuntimeRefused as error:
                if error.code=='MODEL_IDENTITY_MISMATCH': raise
                raise RuntimeRefused('AI_RESPONSE_REJECTED') from None
            except (ContractError,httpx.HTTPStatusError,KeyError,TypeError,ValueError):
                raise RuntimeRefused('AI_RESPONSE_REJECTED') from None
            entry.update(usage=usage,status='COMPLETED')
            return content,entry
        except RuntimeRefused as error:
            entry['status']='REFUSED_'+error.code;raise
        finally:
            # Any other exception still leaves a complete row. The ledger never loses a counted attempt.
            if entry['status'] is None: entry['status']='FAILED_UNEXPECTED'
            entry['elapsed_seconds']=time.monotonic()-started
            self.ledger.record(entry)
