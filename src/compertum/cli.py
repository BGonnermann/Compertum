"""M0 command graph. Unsupported financial verbs exit before any transport."""
import argparse,json,time,sys,shutil,subprocess
from dataclasses import asdict
from pathlib import Path
from .domain import receipt,ContractError,new_id
from .runtime.identity import resolve_project
from .runtime.ipc import RoleEndpoint,request
from .runtime.supervisor import spawn_service

def endpoint(root):return RoleEndpoint(**json.loads((Path(root)/'state/runtime/endpoint.json').read_text()))
def control(root,action,**fields):return request(endpoint(root),{'action':action,'request_id':fields.pop('request_id',new_id()),**fields})
def start_research(root):
    p=resolve_project(root)
    try:return control(root,'status')
    except (OSError,RuntimeError,PermissionError):pass
    child=spawn_service(p.root_path,'supervisor');deadline=time.monotonic()+10
    while time.monotonic()<deadline:
        try:return control(root,'status')
        except (OSError,RuntimeError,PermissionError):time.sleep(.1)
    raise ContractError('START_UNVERIFIED')

def doctor(root):
    from .config import load_config
    cfg=load_config(Path(__file__).resolve().parent/'resources/default.toml',root)
    from .storage import sample_storage
    from .ai.strata import probe_strata
    tools={}
    for name,args in {'git':['--version'],'uv':['--version'],'nvidia-smi':['--query-gpu=name,driver_version,memory.total,memory.free','--format=csv,noheader']}.items():
        path=shutil.which(name)
        if path:
            observed=subprocess.run([path,*args],capture_output=True,text=True,timeout=10);tools[name]={'exit_code':observed.returncode,'observed':observed.stdout[:2048]}
        else:tools[name]={'state':'UNVERIFIED'}
    try:storage={'state':'OBSERVED','observation':sample_storage(root)}
    except OSError as exc:storage={'state':'UNVERIFIED','reason':type(exc).__name__,'code':exc.errno}
    try:provider=probe_strata()
    except Exception as exc:provider={'health':'UNAVAILABLE','reason':type(exc).__name__}
    result=receipt('doctor');result['result']={'python':sys.version.split()[0],'tools':tools,'financial_capability':'CAPABILITY_UNAVAILABLE','broker':'NOT_CONFIGURED','strategy':'STRATEGY_NOT_EVALUATED','paper':'PAPER_DISABLED','provider_subscription':'UNKNOWN','strata':provider,'strata_inference':'NOT_INVOKED','config':{k:str(v) for k,v in asdict(cfg).items()},'storage':storage};return result

def main(argv=None):
    args=list(sys.argv[1:] if argv is None else argv);root=Path.cwd()
    # The checked root option is useful for bounded tests; no arbitrary inputs execute.
    if '--root' in args:
        i=args.index('--root');root=Path(args[i+1]).resolve();del args[i:i+2]
    args=[a for a in args if a!='--json']
    try:
        if args and args[0]=='doctor' and set(args[1:])<= {'--read-only'}:result=doctor(root)
        elif args==['status']:
            try:result=control(root,'status')
            except (OSError,RuntimeError,PermissionError):result=receipt('status','STOPPED');result['result']={'broker':'NOT_CONFIGURED','paper':'PAPER_DISABLED','strategy':'STRATEGY_NOT_EVALUATED','owner':'UNAVAILABLE'}
        elif args and args[0]=='start':
            parser=argparse.ArgumentParser();parser.add_argument('--mode',choices=['research']);parser.add_argument('--config',default='config/default.toml');a=parser.parse_args(args[1:])
            from .config import load_config
            load_config(root/a.config,root);result=start_research(root)
        elif args==['research','pause'] or (len(args)==4 and args[:3]==['research','pause','--reason']):result=control(root,'pause',reason=args[3] if len(args)==4 else 'operator')
        elif args==['research','resume']:result=control(root,'resume')
        elif args[:2]==['research','stop'] and (len(args)==3 or len(args)==4 and args[2]=='--run'):result=control(root,'stop',run_id=args[-1])
        elif args==['shutdown','--checkpoint']:result=control(root,'shutdown')
        elif args==['foundation','check','--suite','m0','--offline']:
            from .foundation import run_foundation_suite
            result=run_foundation_suite(root)
        elif args and args[0]=='ai':
            from .ai.manual import cli_ai
            result=cli_ai(root,args[1:])
        else:result=receipt('unavailable','FAILED',3,'CAPABILITY_UNAVAILABLE')
    except (OSError,RuntimeError,ValueError) as exc:result=receipt('command','FAILED',3,type(exc).__name__)
    except SystemExit:result=receipt('unavailable','FAILED',3,'CAPABILITY_UNAVAILABLE')
    print(json.dumps(result,sort_keys=True));return result['exit_code']
