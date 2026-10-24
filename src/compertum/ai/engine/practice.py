"""The owner's practice-run command (section 19 and docs/ENGINE_PLAN.md, "Practice runs").

    python -m compertum.ai.engine.practice --project PATH models
    python -m compertum.ai.engine.practice --project PATH run --cycles N [--hours H] --requests R --note "why"
                                                            [--seed 12 --sessions 500 --strength 0.004]

`models` lists the model IDs that each configured loopback server reports (read-only, no completion). The owner copies
the IDs into config/models.toml. `run` starts one bounded run against the configured servers on a synthetic market with a
planted pattern. The command takes the coordinator owner lease for the run, verifies the sandbox with the fixed-part
probe targets, sets the research state to RUNNING for the run and back afterwards, and prints the run record as JSON.
It starts no server: the owner serves the model (for example Flint in LM Studio) before running it. Strata stays off.
The owner stops a run by creating state/engine/STOP inside the project. Exit 0 on success, 2 on a refusal.
"""
import argparse
import asyncio
from datetime import date
import json
from multiprocessing.connection import Listener
from pathlib import Path
import sys
from uuid import uuid4
import httpx
from compertum.config import ConfigError,load_config
from compertum.domain import ContractError
from compertum.events import canonical
from compertum.runtime.errors import RuntimeRefused
from compertum.runtime.identity import resolve_project
from compertum.runtime.jobs import available_physical_memory
from compertum.runtime.owners import acquire_owner,release_owner
from compertum.runtime.sandbox import verify_sandbox
from compertum.storage import StorageManager
from compertum.ai.models import load_models,loopback_base_url
from .audit import engine_fixed_targets
from .limits import RunLimits
from .market import market_csv,split_market_tiers,synthetic_market

START_FLOOR=16*1024**3  # the owner's start floor for free host memory (14 October 2026 direction)
MODELS_BYTES=65536
MAX_MODEL_IDS=64


def list_models(base_url,seconds=5):
    """The model IDs a loopback server reports at GET /models. No completion is sent. Bounded reply."""
    url=loopback_base_url(base_url)
    async def fetch():
        async with asyncio.timeout(seconds):
            async with httpx.AsyncClient(trust_env=False,follow_redirects=False,timeout=seconds) as client:
                async with client.stream('GET',url+'/models') as response:
                    response.raise_for_status();raw=bytearray()
                    async for chunk in response.aiter_bytes():
                        if len(raw)+len(chunk)>MODELS_BYTES: raise RuntimeRefused('AI_RESPONSE_BOUND')
                        raw.extend(chunk)
                    return bytes(raw)
    try: raw=asyncio.run(fetch())
    except (TimeoutError,httpx.HTTPError): raise RuntimeRefused('LOCAL_COMPLETION_UNVERIFIED') from None
    try: value=json.loads(raw.decode('utf-8'))
    except (UnicodeError,ValueError): raise RuntimeRefused('AI_RESPONSE_INVALID') from None
    data=value.get('data') if isinstance(value,dict) else None
    ids=[m['id'] for m in data if isinstance(m,dict) and isinstance(m.get('id'),str) and 1<=len(m['id'])<=256] if isinstance(data,list) else []
    return sorted(set(ids))[:MAX_MODEL_IDS]


def models_report(project_root):
    """For every configured role: the address, the configured model, and whether the server lists it."""
    root=Path(project_root).absolute();roles=load_models(root/'config'/'models.toml',root)
    servers={}
    for spec in roles.values():
        if spec.base_url in servers: continue
        try: servers[spec.base_url]={'models':list_models(spec.base_url),'error':None}
        except RuntimeRefused as error: servers[spec.base_url]={'models':[],'error':error.code}
    report={role:{'address':spec.base_url,'model':spec.model,'listed':spec.model in servers[spec.base_url]['models']} for role,spec in sorted(roles.items())}
    return {'servers':servers,'roles':report,'all_listed':all(r['listed'] for r in report.values())}


def set_research_state(store,value):
    with store._live(),store.conn: store.conn.execute('INSERT INTO state VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',('research_state',canonical(value).decode()))


def research_state(store):
    with store._live(): return store.get_state('research_state') or 'PAUSED'


def practice_market(seed,sessions,strength):
    rows=synthetic_market(seed,sessions,planted={'kind':'momentum','window':5,'strength':strength});train,validation,vault=split_market_tiers(rows)
    return {'train_csv':market_csv(train),'validation_csv':market_csv(validation),'validation_rows':validation,'label':f'seed {seed}, {sessions} sessions, strength {strength}'},vault


def run_practice(project_root,config_path,*,cycles,hours,requests,note,seed=12,sessions=500,strength=0.004,available_memory=available_physical_memory,gepa=False):
    """One owner-started bounded run against the configured model servers on a synthetic market. gepa=True runs the E7 prompt
    improvement instead of plain cycles (the cycle limit then bounds GEPA's evaluations). Returns the printed record."""
    root=Path(project_root).absolute()
    available=available_memory()
    if type(available) is not int or available<START_FLOOR: raise RuntimeRefused('AVAILABLE_RAM_FLOOR')
    if type(seed) is not int or type(sessions) is not int or type(strength) not in (int,float): raise RuntimeRefused('ENGINE_MARKET_DENIED')
    market,vault=practice_market(seed,sessions,strength)
    markets=[market,practice_market(seed+1,sessions,strength)[0]] if gepa else [market]
    roles=load_models(root/'config'/'models.toml',root)
    lease=acquire_owner(resolve_project(root),'coordinator')
    try:
        store=StorageManager(lease,load_config(config_path,root)).store
        sandbox_root=root/'.cache'/'test-runs'/f'engine-practice-{date.today():%Y%m%d}-{uuid4().hex[:8]}';sandbox_root.mkdir(parents=True)
        pipe=r'\\.\pipe\compertum-practice-'+uuid4().hex[:8];listener=Listener(pipe,'AF_PIPE')
        try: verification=verify_sandbox(sandbox_root,memory_floor_bytes=START_FLOOR,fixed_targets=engine_fixed_targets(root),pipe=pipe)
        finally: listener.close()
        previous=research_state(store);set_research_state(store,'RUNNING')
        try:
            limits=RunLimits(request_limit=requests,cycle_limit=cycles,hour_limit=hours)
            if gepa:
                from .gepa_run import run_gepa
                result=run_gepa(store=store,lease=lease,project_root=root,sandbox_root=sandbox_root,verification=verification,roles=roles,markets=markets,
                                memory_floor_bytes=START_FLOOR,limits=limits,owner_approval=note)
            else:
                from .run import run_bounded  # needs the engine environment; imported after the checks that need none
                result=run_bounded(store=store,lease=lease,project_root=root,sandbox_root=sandbox_root,verification=verification,roles=roles,market=market,
                                   memory_floor_bytes=START_FLOOR,limits=limits,owner_approval=note)
        finally:
            set_research_state(store,previous);after=research_state(store)
        candidates=[{'cycle_index':c['cycle_index'],'status':c['status'],'market':c.get('market'),'candidates':[{'hypothesis_id':x.get('hypothesis_id'),'status':x.get('status'),
                     'deflation':x.get('deflation'),'audit':(x.get('audit') or {}).get('label')} for x in c.get('candidates') or []]} for c in result['cycles']]
        record={'run_id':result['run_id'],'kind':'gepa' if gepa else 'cycles','reason':result['reason'],'cycles':candidates,'requests':result['requests'],
                'elapsed_seconds':result['elapsed_seconds'],'summary_path':result['summary_path'],'sandbox_root':str(sandbox_root),'models':result['models'],
                'vault_sessions_held_back':len(vault),'verification':{'failed':verification['failed'],'observations':verification['observations']},
                'research_state_after':after,'free_memory_bytes_at_start':available}
        if gepa and result.get('prompts'):
            p=result['prompts'];g=p.get('gepa') or {}
            record['prompts']={'folder':p['folder'],'best_index':p['best_index'],'mean_scores':p['mean_scores'],'candidate_count':p['candidate_count'],
                               'gepa_best_folder_index':g.get('best_folder_index'),'gepa_val_aggregate_scores':g.get('val_aggregate_scores'),'gepa_total_metric_calls':g.get('total_metric_calls')}
        return record
    finally: release_owner(lease)


def main(argv=None):
    parser=argparse.ArgumentParser(prog='compertum.ai.engine.practice',description='Owner practice run of the section 19 engine against loopback model servers.')
    parser.add_argument('--project',type=Path,default=Path('.'));parser.add_argument('--config',type=Path,default=Path('config/default.toml'))
    commands=parser.add_subparsers(dest='command',required=True)
    commands.add_parser('models')
    for name in ('run','gepa'):
        sub=commands.add_parser(name)
        sub.add_argument('--cycles',type=int);sub.add_argument('--hours',type=float);sub.add_argument('--requests',type=int,required=True);sub.add_argument('--note',required=True)
        sub.add_argument('--seed',type=int,default=12);sub.add_argument('--sessions',type=int,default=500);sub.add_argument('--strength',type=float,default=0.004)
    apply=commands.add_parser('apply-prompts');apply.add_argument('--run',required=True);apply.add_argument('--candidate',type=int,required=True)
    args=parser.parse_args(argv)
    root=args.project.resolve();config=args.config if args.config.is_absolute() else root/args.config
    try:
        if args.command=='models': result=models_report(root)
        elif args.command=='apply-prompts':
            from .gepa_run import apply_prompts
            result=apply_prompts(root,args.run,args.candidate)
        else: result=run_practice(root,config,cycles=args.cycles,hours=args.hours,requests=args.requests,note=args.note,seed=args.seed,sessions=args.sessions,strength=args.strength,
                                  gepa=args.command=='gepa')
    except RuntimeRefused as error:
        print(json.dumps({'refused':error.code}));return 2
    except (ContractError,ConfigError) as error:
        print(json.dumps({'refused':getattr(error,'reason',None) or type(error).__name__}));return 2
    print(json.dumps(result,sort_keys=True));return 0


if __name__=='__main__': sys.exit(main())
