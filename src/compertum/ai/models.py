"""One Chat Completions interface for every AI role: loopback servers, plus the remote providers the owner lists in
config/providers.toml. The ledger records each call and each refusal, never a key."""
import asyncio
import contextvars
import threading
from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import math
import os
from pathlib import Path
import re
import sys
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
CYCLE:contextvars.ContextVar[str|None]=contextvars.ContextVar('engine_cycle',default=None)
MAX_BYTES=65536
MAX_OUTPUT_TOKENS,MAX_SECONDS=16384,600
RESPONSE_BYTES=262144  # a reply, thinking text included; raised from 65536 with the per-model caps (26 October 2026)
MAX_TOOLS,MAX_TOOL_CALLS,MAX_ARGUMENT_BYTES=16,8,16384
_TOOL_NAME=re.compile(r'^[A-Za-z0-9_-]{1,64}$')
_MESSAGE_KEYS={'system':{'role','content'},'user':{'role','content'},'assistant':{'role','content','tool_calls'},'tool':{'role','content','tool_call_id'}}


@dataclass(frozen=True)
class RoleModel:
    role:str
    base_url:str
    model:str
    provider:str=PROVIDER  # 'loopback', or the name of an owner-listed remote provider
    key_env:str|None=None  # the user environment variable that holds the provider's key; None sends no key
    # Optional per-model limits from the model file (26 October 2026): a model that thinks before it answers (deepseek-v4-pro) used
    # all 2048 output tokens on thinking. When set, they replace the caller's output-token cap and time limit for this model's calls.
    max_tokens:int|None=None
    seconds:int|None=None


# Remote providers (owner standard, 26 October 2026: the engine runs on any local model, API key or sign-in). The owner lists each
# remote provider in PROVIDERS_FILE; listing one is the owner's authorization for it, and the engine never writes that file. The first
# entry was DeepSeek, authorized on 26 October 2026 with no spending limit; the per-run request limit still bounds each run.
# A key is read at request time from the named user environment variable, sent only in the Authorization header to that provider,
# and never recorded, printed or stored in the project.
PROVIDERS_FILE='config/providers.toml'
_KEY=re.compile(r'[\x21-\x7e]{8,512}')
_PROVIDER_NAME=re.compile(r'[a-z0-9][a-z0-9-]{0,31}')
_KEY_ENV=re.compile(r'[A-Z][A-Z0-9_]{1,63}')
_URL_PATH=re.compile(r'(/[A-Za-z0-9._-]+){0,6}')


def remote_base_url(value):
    """An HTTPS base URL in one exact form: lower-case host, default port, no user, query or fragment; the path is kept (some
    providers serve under /v1 or /api/v1). Anything else is refused."""
    if not isinstance(value,str) or not 1<=len(value)<=256 or not value.startswith('https://'): raise RuntimeRefused('NON_LOOPBACK_DENIED')
    parsed=urlsplit(value)
    try: port=parsed.port
    except ValueError: raise RuntimeRefused('NON_LOOPBACK_DENIED') from None
    host=parsed.hostname;path=parsed.path.rstrip('/')
    if (not host or port not in (None,443) or parsed.username is not None or parsed.password is not None or parsed.query or parsed.fragment
            or parsed.netloc.lower() not in (host,host+':443') or not _URL_PATH.fullmatch(path)
            or not re.fullmatch(r'[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+',host)):
        raise RuntimeRefused('NON_LOOPBACK_DENIED')
    return f'https://{host}{path}'


def load_providers(project_root):
    """The owner's remote providers: {base URL: (name, key variable or None)}. No file means loopback only."""
    root=Path(project_root).absolute()
    if not (root/PROVIDERS_FILE).exists(): return MappingProxyType({})
    try:
        with resolve_project_path(PROVIDERS_FILE,root).open('rb') as stream: raw=stream.read(MAX_BYTES+1)
    except ContractError as error: raise RuntimeRefused(error.reason) from None
    except OSError: raise RuntimeRefused('CONFIG_UNAVAILABLE') from None
    if len(raw)>MAX_BYTES: raise RuntimeRefused('CONFIG_TOO_LARGE')
    try: supplied=tomllib.loads(raw.decode('utf-8'))
    except (UnicodeError,tomllib.TOMLDecodeError): raise RuntimeRefused('INVALID_CONFIG') from None
    entries=supplied.get('providers') if supplied.keys()=={'providers'} else None
    if not isinstance(entries,dict) or len(entries)>32: raise RuntimeRefused('UNKNOWN_CONFIG_FIELD')
    result={}
    for name,entry in entries.items():
        if not _PROVIDER_NAME.fullmatch(name) or name==PROVIDER or not isinstance(entry,dict) or 'base_url' not in entry or not entry.keys()<={'base_url','key_variable'}:
            raise RuntimeRefused('UNKNOWN_CONFIG_FIELD')
        # key_variable holds the NAME of a user environment variable, never the key. A value that is not such a name may be a pasted
        # key (26 October 2026): it is refused with its own code, and the value is never echoed.
        if 'key_variable' in entry and not (isinstance(entry['key_variable'],str) and _KEY_ENV.fullmatch(entry['key_variable'])): raise RuntimeRefused('PROVIDER_KEY_IN_FILE')
        base=remote_base_url(entry['base_url'])
        if base in result: raise RuntimeRefused('UNKNOWN_CONFIG_FIELD')
        result[base]=(name,entry.get('key_variable'))
    return MappingProxyType(result)


def model_base_url(value,providers):
    """A loopback address (section 19), or the base URL of a provider the owner listed. Anything else is refused."""
    if isinstance(value,str) and value.startswith('https://'):
        base=remote_base_url(value)
        if base not in providers: raise RuntimeRefused('NON_LOOPBACK_DENIED')
        return base
    return loopback_base_url(value)


def checked_spec(spec):
    """Check a RoleModel again at the sender: a loopback model has no key; a remote one has an exact HTTPS address, a provider name
    and, if any, a well-formed key variable. Which remote addresses are allowed is decided when load_models reads the owner's files."""
    if not isinstance(spec,RoleModel) or model_id(spec.model)!=spec.model: return False
    if not (spec.max_tokens is None or (type(spec.max_tokens) is int and 1<=spec.max_tokens<=MAX_OUTPUT_TOKENS)): return False
    if not (spec.seconds is None or (type(spec.seconds) is int and 1<=spec.seconds<=MAX_SECONDS)): return False
    if spec.provider==PROVIDER: return loopback_base_url(spec.base_url)==spec.base_url and spec.key_env is None
    return (isinstance(spec.provider,str) and bool(_PROVIDER_NAME.fullmatch(spec.provider)) and remote_base_url(spec.base_url)==spec.base_url
            and (spec.key_env is None or (isinstance(spec.key_env,str) and bool(_KEY_ENV.fullmatch(spec.key_env)))))


def user_variable(name):
    """One named user environment variable: from the process, else from the user's registry key (a variable set after this
    process's parent started is only there). Nothing else is read."""
    value=os.environ.get(name)
    if value is None and sys.platform=='win32':
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,'Environment') as key: value=winreg.QueryValueEx(key,name)[0]
        except OSError: value=None
    return value


def auth_headers(spec,read=None):
    """The request headers for one role model: none without a key variable; else the bearer key. A missing or malformed key refuses."""
    if spec.key_env is None: return {}
    value=(read or user_variable)(spec.key_env)
    if not isinstance(value,str) or not _KEY.fullmatch(value): raise RuntimeRefused('AI_CREDENTIAL_UNAVAILABLE')
    return {'Authorization':'Bearer '+value}


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


def tool_names(tools):
    """Validate an allowlist of Chat Completions tool schemas and return the sorted names. None means no tools."""
    if tools is None: return None
    if not isinstance(tools,list) or not 1<=len(tools)<=MAX_TOOLS: raise RuntimeRefused('AI_TOOLS_DENIED')
    names=[]
    for tool in tools:
        function=tool.get('function') if isinstance(tool,dict) and tool.keys()=={'type','function'} and tool.get('type')=='function' else None
        if (not isinstance(function,dict) or not function.keys()<={'name','description','parameters'} or 'name' not in function
                or not isinstance(function['name'],str) or not _TOOL_NAME.match(function['name'])
                or not isinstance(function.get('description',''),str) or not isinstance(function.get('parameters',{}),dict)):
            raise RuntimeRefused('AI_TOOLS_DENIED')
        names.append(function['name'])
    try: size=len(canonical(tools))
    except (ContractError,RuntimeRefused,ValueError,TypeError): raise RuntimeRefused('AI_TOOLS_DENIED') from None
    if len(set(names))!=len(names) or size>MAX_BYTES: raise RuntimeRefused('AI_TOOLS_DENIED')
    return sorted(names)


def tool_calls_from(value,names):
    """Validate tool calls from a message. Each call must name an allowlisted tool and carry a JSON object as arguments."""
    if names is None: raise RuntimeRefused('AI_TOOL_EXECUTION_DENIED')
    if not isinstance(value,list) or not 1<=len(value)<=MAX_TOOL_CALLS: raise RuntimeRefused('AI_TOOL_EXECUTION_DENIED')
    calls=[]
    for call in value:
        function=call.get('function') if isinstance(call,dict) and call.keys()<={'id','type','function','index'} else None
        identity=call.get('id') if isinstance(call,dict) else None
        if (not isinstance(function,dict) or function.keys()!={'name','arguments'} or function['name'] not in names
                or call.get('type','function')!='function' or not isinstance(identity,str) or not 1<=len(identity)<=128
                or not isinstance(function['arguments'],str) or len(function['arguments'].encode('utf-8'))>MAX_ARGUMENT_BYTES):
            raise RuntimeRefused('AI_TOOL_EXECUTION_DENIED')
        try: arguments=read_json(function['arguments'].encode('utf-8'))
        except RuntimeRefused: raise RuntimeRefused('AI_TOOL_EXECUTION_DENIED') from None
        if not isinstance(arguments,dict): raise RuntimeRefused('AI_TOOL_EXECUTION_DENIED')
        calls.append({'id':identity,'name':function['name'],'arguments':arguments})
    if len({c['id'] for c in calls})!=len(calls): raise RuntimeRefused('AI_TOOL_EXECUTION_DENIED')
    return calls


def check_messages(messages,names):
    """Admit system, user, assistant and tool messages with string content. Assistant tool calls need the allowlist.

    A tool-result message (role tool) is admitted with or without an allowlist: it is text the engine produced, not a call.
    """
    if not isinstance(messages,list) or not 1<=len(messages)<=64: raise RuntimeRefused('AI_MESSAGES_DENIED')
    for m in messages:
        role=m.get('role') if isinstance(m,dict) else None
        if role not in _MESSAGE_KEYS or not {'role','content'}<=m.keys()<=_MESSAGE_KEYS[role] or not isinstance(m['content'],str):
            raise RuntimeRefused('AI_MESSAGES_DENIED')
        if role=='tool' and (not isinstance(m.get('tool_call_id'),str) or not 1<=len(m['tool_call_id'])<=128): raise RuntimeRefused('AI_MESSAGES_DENIED')
        if role=='assistant' and 'tool_calls' in m:
            try: tool_calls_from(m['tool_calls'],names)
            except RuntimeRefused: raise RuntimeRefused('AI_MESSAGES_DENIED') from None


def load_models(path,project_root):
    """Read the bounded role file inside the project. Every role gets exactly one model: loopback, or a provider the owner listed."""
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
    providers=load_providers(root)
    roles=supplied.get('roles') if supplied.keys()=={'roles'} else None
    if not isinstance(roles,dict) or roles.keys()!=ENGINE_ROLES: raise RuntimeRefused('UNKNOWN_CONFIG_FIELD')
    result={}
    for role in sorted(ENGINE_ROLES):
        entry=roles[role]
        if not isinstance(entry,dict) or not {'base_url','model'}<=entry.keys()<={'base_url','model','max_tokens','seconds'}: raise RuntimeRefused('UNKNOWN_CONFIG_FIELD')
        limits={k:entry.get(k) for k in ('max_tokens','seconds')}
        if not (limits['max_tokens'] is None or (type(limits['max_tokens']) is int and 1<=limits['max_tokens']<=MAX_OUTPUT_TOKENS)): raise RuntimeRefused('AI_SETTINGS_DENIED')
        if not (limits['seconds'] is None or (type(limits['seconds']) is int and 1<=limits['seconds']<=MAX_SECONDS)): raise RuntimeRefused('AI_SETTINGS_DENIED')
        base=model_base_url(entry['base_url'],providers);provider,key_env=providers.get(base,(PROVIDER,None))
        result[role]=RoleModel(role,base,model_id(entry['model']),provider,key_env,limits['max_tokens'],limits['seconds'])
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


# Reply checks whose own code reaches the caller (26 October 2026, after bench baseline 1). Each is a step fault in the engine (cycle.STEP_FAULTS).
# Every other refusal inside the request block still becomes AI_RESPONSE_REJECTED, so the engine's behavior does not change; the inner code is kept
# in the record as refusal_detail. A reply stopped at the token cap (finish_reason 'length') is AI_RESPONSE_TRUNCATED.
PASSED_CODES=frozenset({'AI_RESPONSE_INVALID','AI_RESPONSE_INCOMPLETE','AI_RESPONSE_TRUNCATED','AI_RESPONSE_BOUND','AI_TOOL_EXECUTION_DENIED','AI_USAGE_BOUND'})
FINISH_CHARS=32


def usage_counts(usage):
    """The token counts of a reply, bounded: prompt, completion and total, plus reasoning tokens when the server reports them. None when absent."""
    if usage is None: return None
    if not isinstance(usage,dict) or type(usage.get('prompt_tokens')) is not int or type(usage.get('completion_tokens')) is not int: raise RuntimeRefused('AI_USAGE_BOUND')
    # Keep only the token counts. A server-sized dict must not grow the record past its bound.
    counts={k:usage[k] for k in ('prompt_tokens','completion_tokens','total_tokens') if type(usage.get(k)) is int}
    details=usage.get('completion_tokens_details')
    if isinstance(details,dict) and type(details.get('reasoning_tokens')) is int: counts['reasoning_tokens']=details['reasoning_tokens']
    return counts


class ModelClient:
    """Send one bounded Chat Completions request per call. Check memory, the request limit and the server's model first.

    WARNING: with native_limits=True (the default) construction puts the CALLING PROCESS into a one-thread,
    256 MiB, no-child Job for the rest of its life. Only a dedicated adapter process may construct it that way.
    The supervisor, the coordinator and tests must pass native_limits=False.
    """
    def __init__(self,roles,ledger,*,memory_floor_bytes,request_limit,available_memory=available_physical_memory,native_limits=True,gate=None,transcript=None):
        if (not isinstance(roles,Mapping) or roles.keys()!=ENGINE_ROLES
                or any(not isinstance(spec,RoleModel) or spec.role!=role for role,spec in roles.items())):
            raise RuntimeRefused('UNKNOWN_CONFIG_FIELD')
        # The sender checks every address and model ID again. A RoleModel built by hand gets no exemption.
        for spec in roles.values():
            if not checked_spec(spec): raise RuntimeRefused('UNKNOWN_CONFIG_FIELD')
        if type(memory_floor_bytes) is not int or memory_floor_bytes<1: raise RuntimeRefused('AVAILABLE_RAM_UNVERIFIED')
        if type(request_limit) is not int or not 1<=request_limit<=10000: raise RuntimeRefused('AI_REQUEST_BUDGET')
        if (gate is not None and not callable(gate)) or (transcript is not None and not callable(transcript)): raise RuntimeRefused('AI_SETTINGS_DENIED')
        self.roles=roles;self.ledger=ledger;self.memory_floor_bytes=memory_floor_bytes;self.request_limit=request_limit
        self._count_lock=threading.Lock();self._record_lock=threading.Lock()
        # gate: a callable with no arguments that raises RuntimeRefused when no new request may start (stage E5 kill switch,
        # hour limit, freeze). It runs before every request, so a stop takes effect at the next request boundary.
        self.available_memory=available_memory;self.requests=0;self.native_limits=None;self.gate=gate
        # transcript: a callable that receives the full text of every sent request and its reply (step S3, owner request 26 October 2026:
        # a dataset for later fine-tuning). The ledger row keeps hashes only; the transcript keeps the words. Never headers, so never a key.
        self.transcript=transcript;self.transcript_failures=0
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
                if len(raw)+len(chunk)>RESPONSE_BYTES: raise RuntimeRefused('AI_RESPONSE_BOUND')
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
        spec=self._spec(role);headers=auth_headers(spec)
        async def run():
            async with asyncio.timeout(5):
                async with httpx.AsyncClient(trust_env=False,follow_redirects=False,timeout=5,headers=headers) as client:
                    return await self._reported_model(client,spec)
        return asyncio.run(run())

    async def _request(self,spec,payload,seconds,headers):
        async with asyncio.timeout(seconds):
            async with httpx.AsyncClient(trust_env=False,follow_redirects=False,timeout=seconds,headers=headers) as client:
                reported=await self._reported_model(client,spec)
                response,raw=await self._json(client,'POST',spec.base_url+'/chat/completions',payload=payload)
                return reported,response,raw

    def complete(self,role,messages,*,purpose,max_tokens=2048,temperature=0,seconds=120,override_tokens=False):
        """One text completion. No tools are offered, so any tool call in the reply is refused."""
        content,_,entry=self._complete(role,messages,None,purpose,max_tokens,temperature,seconds,override_tokens=override_tokens)
        return content,entry

    def complete_tools(self,role,messages,tools,*,purpose,max_tokens=2048,temperature=0,seconds=120,override_tokens=False):
        """One completion with an allowlist of tools. Returns (content, tool_calls, entry). The engine executes the calls, never the model."""
        return self._complete(role,messages,tools,purpose,max_tokens,temperature,seconds,tools_required=True,override_tokens=override_tokens)

    def _complete(self,role,messages,tools,purpose,max_tokens,temperature,seconds,*,tools_required=False,override_tokens=False):
        # Build the ledger entry first, so that an unknown role or an unexpected failure is still recorded.
        spec=self.roles.get(role) if isinstance(role,str) else None;started=time.monotonic()
        # The model file's cap for this model, unless the caller overrides it: the engine's settings slot (26 October 2026) may choose a cap per role.
        # The override stays inside the same bound of 1 to 16384 tokens.
        if spec is not None and spec.max_tokens is not None and not override_tokens: max_tokens=spec.max_tokens
        if spec is not None and spec.seconds is not None: seconds=spec.seconds
        entry={'call_id':str(uuid4()),'role':role if isinstance(role,str) and len(role)<=64 else 'INVALID_ROLE',
               'purpose':purpose if isinstance(purpose,str) and len(purpose)<=256 else None,'provider':spec.provider if spec else PROVIDER,
               'address':spec.base_url if spec else None,'model_requested':spec.model if spec else None,'model_reported':None,
               'settings':{'temperature':recorded_number(temperature),'max_tokens':recorded_number(max_tokens),
                           'request_seconds':recorded_number(seconds),'stream':False},
               'prompt_sha256':None,'response_sha256':None,'usage':None,'finish_reason':None,'refusal_detail':None,'elapsed_seconds':None,
               'available_memory_bytes':None,'memory_floor_bytes':self.memory_floor_bytes,
               'request_index':self.requests+1,'request_limit':self.request_limit,'tools':None,'tool_calls':None,'status':None,'cycle_id':CYCLE.get()}
        exchange=None  # set once the request is sent: only sent requests reach the transcript
        try:
            if spec is None: raise RuntimeRefused('AI_ROLE_DENIED')
            if not isinstance(purpose,str) or not 1<=len(purpose)<=256: raise RuntimeRefused('AI_TASK_DENIED')
            if (type(max_tokens) is not int or not 1<=max_tokens<=16384 or type(seconds) is not int or not 1<=seconds<=600
                    or type(temperature) not in (int,float) or not 0<=temperature<=2): raise RuntimeRefused('AI_SETTINGS_DENIED')
            if tools_required and tools is None: raise RuntimeRefused('AI_TOOLS_DENIED')
            names=tool_names(tools);entry['tools']=names
            if self.gate is not None: self.gate()
            if self.requests>=self.request_limit: raise RuntimeRefused('AI_REQUEST_BUDGET')
            available=self.available_memory();entry['available_memory_bytes']=available
            if type(available) is not int or available<self.memory_floor_bytes: raise RuntimeRefused('AVAILABLE_RAM_FLOOR')
            check_messages(messages,names)
            prompt=canonical(messages);sanitized(prompt);entry['prompt_sha256']=hashlib.sha256(prompt).hexdigest()
            if tools is not None: sanitized(canonical(tools))
            headers=auth_headers(spec)  # a remote provider without its key refuses here, before the request counts
            # The attempt counts before any byte leaves. A failed request still uses a request.
            with self._count_lock:
                if self.requests>=self.request_limit: raise RuntimeRefused('AI_REQUEST_BUDGET')
                self.requests+=1;entry['request_index']=self.requests
            exchange={'messages':messages,'tools':names}
            payload={'model':spec.model,'messages':messages,'temperature':temperature,'max_tokens':max_tokens,'stream':False}
            if tools is not None: payload.update(tools=tools,tool_choice='auto')
            tool_calls=[]
            try:
                reported,response,raw=asyncio.run(self._request(spec,payload,seconds,headers))
                entry['model_reported']=reported;entry['response_sha256']=hashlib.sha256(raw).hexdigest()
                choices=response.get('choices') if isinstance(response,dict) else None
                if not isinstance(choices,list) or len(choices)!=1 or not isinstance(choices[0],dict): raise RuntimeRefused('AI_RESPONSE_INVALID')
                # The stop reason and the token counts are recorded before every reply check, so a refused reply keeps them (bench baseline 1:
                # three Mathematician reviews stopped at the cap and the record showed neither). The cap check comes before the tool-call
                # and usage checks: a reply cut off inside a tool call has broken arguments, and it is truncated, not a tool fault (review, 26 October 2026).
                finish=choices[0].get('finish_reason')
                entry['finish_reason']=finish if isinstance(finish,str) and len(finish)<=FINISH_CHARS else (None if finish is None else 'INVALID')
                try: usage=usage_counts(response.get('usage'));usage_fault=None
                except RuntimeRefused as error: usage=None;usage_fault=error
                entry['usage']=usage
                if finish=='length': raise RuntimeRefused('AI_RESPONSE_TRUNCATED')
                if usage_fault is not None: raise usage_fault
                message=choices[0].get('message')
                if not isinstance(message,dict) or message.get('function_call'): raise RuntimeRefused('AI_TOOL_EXECUTION_DENIED')
                # A thinking model's thinking text. The whole raw reply, this text included, already passed the secret check in _request.
                if isinstance(message.get('reasoning_content'),str): exchange['reasoning']=message['reasoning_content']
                if message.get('tool_calls'):
                    tool_calls=tool_calls_from(message['tool_calls'],names)
                    entry['tool_calls']=[{'id':c['id'],'name':c['name'],'arguments_sha256':hashlib.sha256(canonical(c['arguments'])).hexdigest()} for c in tool_calls]
                content=message.get('content')
                if content is None and tool_calls: content=''
                if not isinstance(content,str) or finish not in ('stop','tool_calls') or (finish=='tool_calls')!=bool(tool_calls):
                    raise RuntimeRefused('AI_RESPONSE_INCOMPLETE')
                sanitized(content.encode('utf-8'));exchange.update(content=content,tool_calls=tool_calls)
            except (TimeoutError,httpx.TimeoutException,httpx.TransportError):
                raise RuntimeRefused('LOCAL_COMPLETION_UNVERIFIED') from None
            except RuntimeRefused as error:
                if error.code=='MODEL_IDENTITY_MISMATCH': raise
                entry['refusal_detail']=error.code
                raise RuntimeRefused(error.code if error.code in PASSED_CODES else 'AI_RESPONSE_REJECTED') from None
            except (ContractError,httpx.HTTPStatusError,KeyError,TypeError,ValueError) as error:
                entry['refusal_detail']=type(error).__name__[:64]
                raise RuntimeRefused('AI_RESPONSE_REJECTED') from None
            entry.update(usage=usage,status='COMPLETED')
            return content,tool_calls,entry
        except RuntimeRefused as error:
            entry['status']='REFUSED_'+error.code;raise
        finally:
            # Any other exception still leaves a complete row. The ledger never loses a counted attempt.
            if entry['status'] is None: entry['status']='FAILED_UNEXPECTED'
            entry['elapsed_seconds']=time.monotonic()-started
            with self._record_lock:
                self.ledger.record(entry)
                if self.transcript is not None and exchange is not None:
                    try: self.transcript({**{k:entry[k] for k in ('call_id','role','purpose','provider','model_requested','model_reported','request_index','status','finish_reason','usage','elapsed_seconds','settings','cycle_id')},**exchange})
                    except Exception: self.transcript_failures+=1  # a lost transcript line never stops the run; the count is reported
