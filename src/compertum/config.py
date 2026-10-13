from dataclasses import dataclass
from pathlib import Path
import tomllib
from .domain import ContractError,GIB

@dataclass(frozen=True)
class M0Config:
    root:Path
    paper_enabled:bool=False
    mode:str='research'
    storage_cap_gib:int=50
    cpu_threads:int=4
    ram_gib:int=4
    daily_ai_tasks:int=8
    daily_ai_requests:int=40
    daily_cpu_seconds:int=7200
    strata_url:str='http://127.0.0.1:8080'
    manual_wait_seconds:int=86400
    def capability(self,name):
        return 'AVAILABLE' if name in {'status','doctor','research','foundation','ai'} else 'CAPABILITY_UNAVAILABLE'

def load_config(path,project_root):
    data=tomllib.loads(Path(path).read_text(encoding='utf-8'))
    allowed=set(M0Config.__dataclass_fields__)-{'root'}
    if set(data)-allowed: raise ContractError('UNKNOWN_CONFIG_FIELD')
    cfg=M0Config(root=Path(project_root).resolve(),**data)
    if cfg.paper_enabled is not False or cfg.mode!='research': raise ContractError('CAPABILITY_UNAVAILABLE')
    maxima={'storage_cap_gib':50,'cpu_threads':4,'ram_gib':4,'daily_ai_tasks':8,'daily_ai_requests':40,'daily_cpu_seconds':7200,'manual_wait_seconds':86400}
    for key,maximum in maxima.items():
        if type(getattr(cfg,key)) is not int or not 0<getattr(cfg,key)<=maximum: raise ContractError('CONFIG_LIMIT:'+key)
        if getattr(cfg,key)!=maximum:raise ContractError('M0_NONDEFAULT_LIMIT_UNSUPPORTED:'+key)
    if cfg.strata_url!='http://127.0.0.1:8080': raise ContractError('UNAPPROVED_ENDPOINT')
    return cfg
