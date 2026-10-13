"""M0 terminal interface. Unsupported milestones have no dispatch path."""
import argparse
import json
from pathlib import Path
import sys
from .domain import ContractError
from .config import load_config,ConfigError
from .runtime.errors import RuntimeRefused


def main(argv=None):
    parser=argparse.ArgumentParser(prog='compertum')
    parser.add_argument('--project-root',type=Path,default=Path.cwd())
    parser.add_argument('command',nargs='?',default='status');parser.add_argument('verb',nargs='?')
    parser.add_argument('--json',action='store_true');parser.add_argument('--read-only',action='store_true')
    parser.add_argument('--mode',default='research');parser.add_argument('--config',type=Path,default=Path('config/default.toml'))
    parser.add_argument('--checkpoint',action='store_true');parser.add_argument('--suite');parser.add_argument('--offline',action='store_true')
    parser.add_argument('--task');parser.add_argument('--provider');parser.add_argument('--response');parser.add_argument('--reason');parser.add_argument('--run');parser.add_argument('--seal')
    args,unknown=parser.parse_known_args(argv);root=args.project_root.absolute()
    action=(args.command,args.verb)
    try:
        if unknown: raise RuntimeRefused('CAPABILITY_UNAVAILABLE')
        if action==('ai','status'):
            from .ai.manual import provider_status
            result=provider_status()
        elif args.command=='doctor' and args.read_only:
            from .runtime.identity import resolve_project
            from .storage import sample_storage
            project=resolve_project(root);observed=sample_storage(project)
            result={'status':'READ_ONLY','python':sys.version.split()[0],'project_id':project.project_id,
                'project_bytes':observed['total_bytes'],'free_bytes':observed['free_bytes'],
                'broker_state':'NOT_CONFIGURED','order_admission':'DISARMED','strategy_state':'NOT_EVALUATED',
                'strata':'NOT_PROBED','subscription_quota':'UNKNOWN'}
        elif action==('foundation','check') and args.suite=='m0' and args.offline:
            from .foundation import run_foundation_suite
            from .runtime.supervisor import control
            from .runtime._windows import NativeCallError
            config=load_config(root/args.config,root)
            try: result=run_foundation_suite(config,offline=True)
            except RuntimeRefused as error:
                if error.code!='OWNER_BUSY': raise
                import time
                submitted=control(root,'foundation.check',{'operation':'submit'})
                deadline=time.monotonic()+30
                while time.monotonic()<deadline:
                    status=control(root,'status');result=next(r for r in status['fixtures'] if r['task_id']==submitted['task_id'])
                    if result['status']!='RUNNING': break
                    time.sleep(.1)
                if result['status']!='COMPLETED': raise RuntimeRefused('FOUNDATION_UNVERIFIED')
                result={'status':'FOUNDATION_VERIFIED','task_id':result['task_id'],'artifact':result['artifact'],'ai_requests':0,'strategy_state':'NOT_EVALUATED','paper':'DISABLED'}
        elif args.command=='start' and args.mode=='research':
            from .runtime.supervisor import Supervisor,control
            config=load_config(root/args.config,root)
            try: supervisor=Supervisor(config)
            except RuntimeRefused as error:
                if error.code!='OWNER_BUSY': raise
                result=control(root,'attach')
            else:
                print(json.dumps({'status':'STARTED','project_id':supervisor.project.project_id,'generation':supervisor.supervisor.generation}),flush=True)
                supervisor.run();result={'status':'STOPPED','order_admission':'DISARMED'}
        else:
            from .runtime.supervisor import control
            actions={('status',None):'status',('research','pause'):'pause_research',('research','resume'):'resume_research',
                     ('research','stop'):'stop_research',('checkpoint',None):'checkpoint'}
            if args.command=='baseline' and args.verb in {'status','resume','step','pause','stop'} and args.run:
                result=control(root,'baseline',{'run_id':args.run,'operation':args.verb})
            elif args.command=='final' and args.verb in {'status','resume','step','pause','stop','recover'} and args.seal:
                result=control(root,'final',{'seal_id':args.seal,'operation':args.verb})
            elif action==('ai','export') and args.task and args.provider=='subscription':
                result=control(root,'ai.export',{'task_id':args.task,'provider':args.provider})
            elif action==('ai','import') and args.task and args.response:
                result=control(root,'ai.import',{'task_id':args.task,'response':args.response})
            elif action in actions:
                payload={'reason':args.reason} if action==('research','pause') and args.reason else {'run_id':args.run} if action==('research','stop') and args.run else {}
                result=control(root,actions[action],payload)
            elif action==('shutdown',None) and args.checkpoint: result=control(root,'shutdown')
            elif action==('foundation','check') and args.suite=='m0' and args.offline:
                result=control(root,'foundation.check',{'operation':'submit'})
            else: raise RuntimeRefused('CAPABILITY_UNAVAILABLE')
        print(json.dumps(result,sort_keys=True));return 0
    except (RuntimeRefused,ContractError,ConfigError) as error:
        reason=error.code if isinstance(error,RuntimeRefused) else error.reason
        print(json.dumps({'status':reason,'order_admission':'DISARMED'}));return 3

if __name__=='__main__': raise SystemExit(main())


