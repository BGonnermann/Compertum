"""Strict M0 boundary contracts; no financial or provider behavior."""
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import uuid
import jsonschema

GIB=1024**3
class ContractError(ValueError): pass

def now(): return datetime.now(timezone.utc).isoformat()
def new_id(): return str(uuid.uuid4())
def canonical(value):
    ensure_safe(value)
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def digest(value): return hashlib.sha256(canonical(value)).hexdigest()
def file_hash(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        while chunk:=f.read(1024**2):h.update(chunk)
    return h.hexdigest()
def utc_time(value):
    try: dt=datetime.fromisoformat(value.replace('Z','+00:00'))
    except (ValueError,AttributeError): raise ContractError('INVALID_TIMESTAMP') from None
    if dt.tzinfo is None or dt.utcoffset().total_seconds()!=0: raise ContractError('UTC_REQUIRED')
    return dt
def ensure_safe(value):
    if isinstance(value,float) and not math.isfinite(value): raise ContractError('NONFINITE')
    if isinstance(value,str) and re.search(r'\b(?:sk-[A-Za-z0-9_-]{12,}|AIza[A-Za-z0-9_-]{25,})\b',value): raise ContractError('SECRET_SHAPED_INPUT')
    if isinstance(value,dict):
        for key,item in value.items():
            if str(key).lower() in {'api_key','access_token','secret','authorization','password'}: raise ContractError('SECRET_FIELD')
            ensure_safe(item)
    elif isinstance(value,(list,tuple)):
        for item in value: ensure_safe(item)
def within(root,relative):
    root=Path(root).resolve(); rel=Path(relative)
    if rel.is_absolute() or ':' in str(rel) or '..' in rel.parts: raise ContractError('PATH_ESCAPE')
    target=(root/rel).resolve()
    if not target.is_relative_to(root): raise ContractError('PATH_ESCAPE')
    current=root
    for part in rel.parts:
        current=current/part
        if current.exists() and getattr(current.lstat(),'st_file_attributes',0)&0x400: raise ContractError('REPARSE_TARGET')
    return target
def atomic_json(path,value):
    payload=canonical(value)
    if len(payload)>8*1024**2: raise ContractError('RECEIPT_CAPACITY')
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name(path.name+'.'+new_id()+'.tmp')
    with temp.open('xb') as f: f.write(payload); f.flush(); os.fsync(f.fileno())
    os.replace(temp,path)
def validate_record(schema_name,payload,schema_root=None):
    ensure_safe(payload)
    if schema_name not in {'task','control_receipt','artifact_manifest','recovery_manifest','ai_proposal','consumption_event'}: raise ContractError('UNKNOWN_SCHEMA')
    root=Path(schema_root) if schema_root else Path(__file__).resolve().parent/'resources'
    try:
        schema=json.loads((root/(schema_name+'.v1.json')).read_text())
        jsonschema.Draft202012Validator(schema,format_checker=jsonschema.FormatChecker()).validate(payload)
    except (jsonschema.ValidationError,OSError,json.JSONDecodeError): raise ContractError('SCHEMA_INVALID') from None
    for key,value in payload.items():
        if (key=='at' or key.endswith('_at')) and value is not None: utc_time(value)
    def paths(value):
        if isinstance(value,dict):
            for key,item in value.items():
                if (key=='at' or key.endswith('_at')) and item is not None:utc_time(item)
                if key in {'path','original_path'}:
                    if not isinstance(item,str) or Path(item).is_absolute() or ':' in item or '..' in Path(item).parts:raise ContractError('PATH_ESCAPE')
                paths(item)
        elif isinstance(value,list):
            for item in value:paths(item)
    paths(payload)
    return payload

@dataclass(frozen=True)
class Budget:
    cpu_threads:int=4
    ram_bytes:int=4*GIB
    output_bytes:int=2*GIB
    wall_seconds:int=1800
    attempts:int=2
    ai_requests:int=8
    input_tokens:int=16384
    output_tokens:int=2048
    def __post_init__(self):
        maxima={'cpu_threads':4,'ram_bytes':4*GIB,'output_bytes':2*GIB,'wall_seconds':2700,'attempts':2,'ai_requests':10,'input_tokens':16384,'output_tokens':2048}
        for key,maximum in maxima.items():
            value=getattr(self,key)
            if type(value) is not int or not 0<value<=maximum: raise ContractError('BUDGET_INVALID:'+key)

@dataclass(frozen=True)
class TaskSpec:
    task_id:str=field(default_factory=new_id)
    kind:str='OFFLINE_FIXTURE'
    role:str='fixture'
    input_hashes:tuple=()
    code_hash:str=''
    expected_schema:str='artifact_manifest'
    deadline_at:str|None=None
    permissions:tuple=('development_read','task_write')
    budget:Budget=field(default_factory=Budget)
    def __post_init__(self):
        if self.kind not in {'OFFLINE_FIXTURE','AI_PROPOSAL','AI_QUALIFICATION','RECOVERY_FIXTURE'}: raise ContractError('CAPABILITY_UNAVAILABLE')
        if not set(self.permissions)<= {'development_read','task_write','model_proposal','loopback'}: raise ContractError('PERMISSION_DENIED')
        if self.deadline_at: utc_time(self.deadline_at)
    def record(self):
        r=json.loads(canonical(asdict(self))); r['schema_version']=1
        return validate_record('task',r)

def receipt(action,state='CONFIRMED',exit_code=0,reason='',request_id=None,generation=None,artifacts=()):
    return {'schema_version':1,'request_id':request_id or new_id(),'action':action,'target':'M0','state':state,'evidence':'VERIFIED_PASS' if exit_code==0 else 'UNVERIFIED','generation':generation,'at':now(),'exit_code':exit_code,'reason':reason,'artifacts':list(artifacts)}
