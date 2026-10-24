"""Owner commands for the engine: list the engine state, clear a freeze, close an abandoned run. Stage E5.

    python -m compertum.ai.engine.control --project PATH list
    python -m compertum.ai.engine.control --project PATH clear-freeze --freeze FREEZE_ID --note "why"
    python -m compertum.ai.engine.control --project PATH close-run --run RUN_ID --note "why"

The command takes the coordinator owner lease for its duration, so it cannot run while the coordinator or a bounded run
holds it. Every action keeps the original row and adds the owner's note. Exit 0 on success, 2 on a refusal.
"""
import argparse
import json
from pathlib import Path
import sys
from compertum.config import ConfigError,load_config
from compertum.domain import ContractError
from compertum.runtime.errors import RuntimeRefused
from compertum.runtime.identity import resolve_project
from compertum.runtime.owners import acquire_owner,release_owner
from compertum.storage import StorageManager
from .ledger import EngineLedger
from .limits import NOTE_LIMIT,utc_now


def engine_state(store):
    ledger=EngineLedger(store)
    return {'active_freezes':ledger.active_freezes(),'open_runs':ledger.open_runs(),'total_trials':ledger.total_trials()}


def clear_freeze(store,freeze_id,owner_note):
    """Owner action. The freeze row stays; it gains cleared_at and the note."""
    return EngineLedger(store).clear_freeze(freeze_id,owner_note)


def close_abandoned_run(store,run_id,owner_note):
    """Owner action for a run that stopped without an END row (for example a crash). Adds the END row with the note."""
    if not isinstance(owner_note,str) or not 1<=len(owner_note)<=NOTE_LIMIT: raise RuntimeRefused('ENGINE_RECORD_DENIED')
    ledger=EngineLedger(store)
    if not any(r['run_id']==run_id for r in ledger.open_runs()): raise RuntimeRefused('ENGINE_RUN_UNKNOWN')
    return ledger.close_run(run_id,{'reason':'OWNER_CLOSED','owner_note':owner_note,'ended_at':utc_now()})


def main(argv=None):
    parser=argparse.ArgumentParser(prog='compertum.ai.engine.control',description='Owner commands for the section 19 engine.')
    parser.add_argument('--project',type=Path,default=Path('.'));parser.add_argument('--config',type=Path,default=Path('config/default.toml'))
    commands=parser.add_subparsers(dest='command',required=True)
    commands.add_parser('list')
    freeze=commands.add_parser('clear-freeze');freeze.add_argument('--freeze',required=True);freeze.add_argument('--note',required=True)
    run=commands.add_parser('close-run');run.add_argument('--run',required=True);run.add_argument('--note',required=True)
    args=parser.parse_args(argv)
    root=args.project.resolve();config=args.config if args.config.is_absolute() else root/args.config
    lease=None
    try:
        lease=acquire_owner(resolve_project(root),'coordinator')
        store=StorageManager(lease,load_config(config,root)).store
        if args.command=='list': result=engine_state(store)
        elif args.command=='clear-freeze': result=clear_freeze(store,args.freeze,args.note)
        else: result=close_abandoned_run(store,args.run,args.note)
    except RuntimeRefused as error:
        print(json.dumps({'refused':error.code}));return 2
    except (ContractError,ConfigError) as error:
        # A busy owner (OWNER_BUSY, the usual case during a run) is a RuntimeRefused; config and contract errors report their reason.
        print(json.dumps({'refused':getattr(error,'reason',None) or type(error).__name__}));return 2
    finally:
        if lease is not None: release_owner(lease)
    print(json.dumps(result,sort_keys=True));return 0


if __name__=='__main__': sys.exit(main())
