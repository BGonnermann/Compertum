"""The firm-panel vault route (docs/PANEL_CANDIDATES_DESIGN.md, phase 4; owner, 3 November 2026: "yes go ahead with all of it").

Stage 1: an engine panel candidate that beat the benchmark and passed the Auditor is promoted (its submitted files, by hash) and becomes
ELIGIBLE on french-v1 with this route: the code hash, the hashes of the two input files it saw, the entry file and the number of industries.
Stage 2, inside a counted look only: the frozen code must first reproduce its admitted VALIDATION score from the same files; then it runs
once more with the vault sessions appended to panel_validation.csv, and only the vault sessions are scored against the equal-weight
industries. The roles never see a vault row: only this module reads them, through french_panel(with_vault=True) inside the look.
"""
import hashlib
import json
from pathlib import Path

from compertum.events import canonical
from compertum.runtime.errors import RuntimeRefused
from . import library_multi
from .execution import remove_data_tiers
from .panel import PanelMarket,asset_names,panel_files,parse_weights
from .promotion import promoted_folder

ROUTE='firm-panel'
UNIVERSE='french49'
VAULT='french-v1'


def sha(data): return hashlib.sha256(data if isinstance(data,bytes) else data.encode('utf-8')).hexdigest()


def route_record(market,files,entry):
    """The route of an ELIGIBLE firm-panel candidate: enough to rebuild and check everything it saw."""
    return {'kind':ROUTE,'universe':UNIVERSE,'entry':entry,'code_sha256':sha(canonical(files)),'members':len(market.p['closes']),
            'inputs':{name:sha(text) for name,text in sorted(market.files.items())}}


def frozen_files(project_root,candidate_id,route):
    """The promoted files of the candidate, checked against the manifest and the route's code hash."""
    folder=promoted_folder(project_root,candidate_id)
    try:
        manifest=json.loads((folder/'manifest.json').read_bytes())
        files={name:(folder/name).read_text(encoding='utf-8') for name in manifest['files']}
    except (OSError,ValueError,KeyError,TypeError): raise RuntimeRefused('ENGINE_VAULT_DENIED') from None
    if any(sha(text)!=manifest['files'][name] for name,text in files.items()) or sha(canonical(files))!=route.get('code_sha256'): raise RuntimeRefused('ENGINE_VAULT_DENIED')
    return files


def vault_score(queue,look_id,candidate_id,*,project_root,manifests,sandbox):
    """Stage 2 for one firm-panel candidate. sandbox is an EngineerSandbox with the panel layout and the candidate's TRAIN and VALIDATION
    files; its reruns are trusted reruns of frozen code, not Engineer runs."""
    _,_,eligible=queue._fold(candidate_id);route=(eligible or {}).get('route') or {}
    if route.get('kind')!=ROUTE or route.get('universe')!=UNIVERSE or not isinstance(route.get('entry'),str): raise RuntimeRefused('ENGINE_VAULT_DENIED')
    files=frozen_files(project_root,candidate_id,route)
    p=library_multi.french_panel(project_root,manifests);market=PanelMarket(p)
    if len(p['closes'])!=route.get('members') or {k:sha(v) for k,v in sorted(market.files.items())}!=route.get('inputs'): raise RuntimeRefused('ENGINE_VAULT_DENIED')
    if sandbox.train_csv!=market.files['panel_train.csv'] or sandbox.validation_csv!=market.files['panel_validation.csv']: raise RuntimeRefused('ENGINE_VAULT_DENIED')
    again=sandbox.rerun_frozen(files,route['entry'],purpose='audit')
    if again['status']!='COMPLETED' or again.get('signals') is None or sha(canonical(market.score(again['signals'])))!=eligible.get('score_sha256'):
        raise RuntimeRefused('ENGINE_VAULT_DENIED')
    members=sorted(p['closes']);aliases=asset_names(members)

    def read():
        full=library_multi.french_panel(project_root,manifests,with_vault=True);start=len(p['dates'])
        if full['dates'][:start]!=p['dates'] or sorted(full['closes'])!=members or asset_names(sorted(full['closes']))!=aliases: raise RuntimeRefused('ENGINE_VAULT_DENIED')
        record=sandbox.rerun_frozen(files,route['entry'],purpose='vault',validation_csv=panel_files(full,aliases)['panel_validation.csv'])
        if record.get('job_folder'): remove_data_tiers(record['job_folder'])
        if record['status']!='COMPLETED' or record.get('signals') is None: raise RuntimeRefused('ENGINE_SIGNALS_INVALID')
        return full,start,record['signals']

    def scored(produced):
        full,start,signals=produced;u=library_multi.prepare(full,members)
        return library_multi.score(u,parse_weights(signals,full,aliases),start,u['n'])
    return queue.evaluate_in_vault(look_id,candidate_id,None,read,vault=VAULT,score=scored)


def main(argv=None,available_memory=None):
    """Owner command, one candidate inside an open look:
        python -m compertum.ai.engine.firm_panel --project . vault --look LOOK_ID --candidate CANDIDATE_ID
    It checks free memory and every sandbox slot with the NumPy library, as a practice start does, then runs vault_score."""
    import argparse
    from datetime import date
    from multiprocessing.connection import Listener
    from uuid import uuid4
    from compertum.config import ConfigError,load_config
    from compertum.domain import ContractError
    from compertum.runtime.identity import resolve_project
    from compertum.runtime.jobs import available_physical_memory
    from compertum.runtime.owners import acquire_owner,release_owner
    from compertum.runtime.sandbox import verify_slots
    from compertum.storage import StorageManager
    from .audit import engine_fixed_targets
    from .execution import EngineerSandbox
    from .ledger import EngineLedger
    from .libraries import CODE_ROOT,PACKAGES,check_library,library_folder
    from .panel import french_manifests
    from .practice import START_FLOOR
    from .vault import CandidateQueue
    parser=argparse.ArgumentParser(prog='compertum.ai.engine.firm_panel',description='Vault test of one firm-panel candidate inside an open look.')
    parser.add_argument('--project',type=Path,default=Path('.'));parser.add_argument('--config',type=Path,default=Path('config/default.toml'))
    commands=parser.add_subparsers(dest='command',required=True)
    vault=commands.add_parser('vault');vault.add_argument('--look',required=True);vault.add_argument('--candidate',required=True)
    args=parser.parse_args(argv)
    root=args.project.resolve();config=args.config if args.config.is_absolute() else root/args.config;lease=None
    try:
        available=(available_memory or available_physical_memory)()
        if type(available) is not int or available<START_FLOOR: raise RuntimeRefused('AVAILABLE_RAM_FLOOR')
        manifests=french_manifests(root)
        lease=acquire_owner(resolve_project(root),'coordinator');ledger=EngineLedger(StorageManager(lease,load_config(config,root)).store)
        market=PanelMarket(library_multi.french_panel(root,manifests))
        sandbox_root=root/'.cache'/'test-runs'/f'engine-vault-{date.today():%Y%m%d}-{uuid4().hex[:8]}';sandbox_root.mkdir(parents=True)
        pipe=r'\\.\pipe\compertum-vault-'+uuid4().hex[:8];listener=Listener(pipe,'AF_PIPE');manifest=check_library(CODE_ROOT)
        try: verification=verify_slots(sandbox_root,memory_floor_bytes=START_FLOOR,fixed_targets=engine_fixed_targets(root),pipe=pipe,
                                       library=library_folder(CODE_ROOT),library_version=PACKAGES['numpy'])
        finally: listener.close()
        verification['library']['manifest']=manifest
        sandbox=EngineerSandbox(sandbox_root,ledger=ledger,lease=lease,verification=verification,cycle_id=f'vault-{args.look}'[:64],train_csv=market.files['panel_train.csv'],
                                validation_csv=market.files['panel_validation.csv'],memory_floor_bytes=START_FLOOR,layout='panel')
        event=vault_score(CandidateQueue(ledger),args.look,args.candidate,project_root=root,manifests=manifests,sandbox=sandbox)
    except RuntimeRefused as error:
        print(json.dumps({'refused':error.code}));return 2
    except (ContractError,ConfigError) as error:
        print(json.dumps({'refused':getattr(error,'reason',None) or type(error).__name__}));return 2
    finally:
        if lease is not None: release_owner(lease)
    print(json.dumps({k:event.get(k) for k in ('candidate_id','event','status','look_id','confirmation')},sort_keys=True,default=str));return 0


if __name__=='__main__':
    import sys
    sys.exit(main())
