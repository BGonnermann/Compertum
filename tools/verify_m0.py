"""Fresh M0 verification. Missing evidence always blocks engineering acceptance."""
import json,subprocess,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from compertum.domain import atomic_json,file_hash,new_id,now

REQUIRED=('environment','contracts_scope','native_suite','ownership_authentication','durability_recovery','process_storage','offline_reproduction','manual_bridge','local_qualification','independent_review')
def acceptance_state(gates):return 'ENGINEERING_FOUNDATIONS_READY' if gates and all(v=='VERIFIED_PASS' for v in gates.values()) else 'M0_BLOCKED'

def run_checked(root,args,name,timeout=240):
    began=time.monotonic();run=subprocess.run(args,cwd=root,capture_output=True,text=True,timeout=timeout)
    if len(run.stdout.encode())+len(run.stderr.encode())>1024**2:raise RuntimeError('VERIFICATION_LOG_CAPACITY')
    record={'at':now(),'argv':args,'exit_code':run.returncode,'elapsed_seconds':time.monotonic()-began,'stdout':run.stdout,'stderr':run.stderr}
    atomic_json(root/'artifacts/m0'/name,record);return record

def source_inventory(root):
    files=[]
    for folder in ('src','tests','schemas','config','tools','docs'):
        files.extend(p for p in (root/folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts)
    files.extend(root/p for p in ('AGENTS.md','pyproject.toml','uv.lock','.gitignore','.python-version','Solo_Quant_System_Build_Preparation.md'))
    return {str(p.relative_to(root)):file_hash(p) for p in sorted(files)}

def verify_m0(project_root):
    root=Path(project_root).resolve();runid=new_id();gates={g:'UNVERIFIED' for g in REQUIRED};details={}
    full=run_checked(root,[sys.executable,'-B','-m','pytest','tests','-q','-p','no:cacheprovider','--basetemp','.cache/test-runs/full-'+runid,'--tb=short'],'full_suite.json')
    atomic_json(root/'artifacts/m0/history'/runid/'full_suite.json',full)
    gates['native_suite']='VERIFIED_PASS' if full['exit_code']==0 else 'VERIFIED_FAIL'
    if full['exit_code']==0 and 'skipped' not in full['stdout'].lower():
        for name in ('contracts_scope','ownership_authentication','durability_recovery','manual_bridge'):gates[name]='VERIFIED_PASS'
    for cmd,name in [([sys.executable,'-B','-m','compertum','doctor','--read-only','--json'],'doctor.json'),([sys.executable,'-B','-m','compertum','foundation','check','--suite','m0','--offline','--json'],'foundation.json')]:run_checked(root,cmd,name)
    # Test evidence and review reconciliation are explicit; suite success alone is insufficient.
    from compertum.storage import sample_storage
    began=time.monotonic()
    try:
        observation=sample_storage(root);elapsed=time.monotonic()-began
        details['storage']={'observation':observation,'seconds':elapsed,'within_deadline':elapsed<=5}
        gates['process_storage']='VERIFIED_FAIL' if elapsed>5 else 'UNVERIFIED'
    except OSError as exc:
        gates['process_storage']='VERIFIED_FAIL';details['storage']={'reason':type(exc).__name__,'code':exc.errno,'seconds':time.monotonic()-began,'coverage':'INCOMPLETE_NO_PERMISSION_CHANGE'}
    def read(name):
        try:return json.loads((root/'artifacts/m0'/name).read_text())
        except (OSError,ValueError):return {}
    environment=read('final_environment.json');clean=read('clean_reproduction.json');local=read('ai/strata_worker_v1.json');scope=read('scope_review.json')
    if environment.get('python',{}).get('version')=='3.14.7' and environment.get('packages') and all(p.get('import')=='VERIFIED_PASS' for p in environment['packages'].values()) and environment.get('documents',{}).get('uv.lock')==file_hash(root/'uv.lock'):gates['environment']='VERIFIED_PASS'
    if clean.get('state')=='VERIFIED_PASS' and clean.get('noneditable') and clean.get('lock_sha256')==file_hash(root/'uv.lock') and clean.get('wheel_sha256')==file_hash(root/'.cache/m0-wheel/compertum-0.1.0-py3-none-any.whl'):gates['offline_reproduction']='VERIFIED_PASS'
    if local.get('checks') and all(local['checks'].values()) and any('fictional_tool_call' in q for q in local.get('requests',[])):gates['local_qualification']='VERIFIED_PASS'
    strict=read('ai/strict_wrapper.json')
    if strict.get('full_current_profile','').startswith('UNVERIFIED'):
        gates['local_qualification']='UNVERIFIED';details['strict_ai_wrapper']={'state':strict.get('state'),'full_current_profile':strict['full_current_profile'],'checks':strict.get('checks',{})}
    details['native_cancellation']={'state':local.get('native_cancellation','UNVERIFIED'),'automatic_local_dispatch':False}
    current_scope={str(p.relative_to(root)):file_hash(p) for p in sorted((root/'src/compertum').rglob('*.py'))}
    if scope.get('state')=='VERIFIED_PASS' and scope.get('source_hashes')==current_scope and (root/'reports/M0_INDEPENDENT_REVIEW.md').exists():gates['independent_review']='VERIFIED_PASS'
    else:gates['contracts_scope']='UNVERIFIED'
    result={'at':now(),'run_id':runid,'state':acceptance_state(gates),'strategy':'STRATEGY_NOT_EVALUATED','paper':'PAPER_DISABLED','gates':gates,'details':details,'source_hashes':source_inventory(root),'spending_usd':0}
    atomic_json(root/'artifacts/m0/acceptance.json',result);return result

if __name__=='__main__':
    result=verify_m0(Path(__file__).resolve().parents[1])
    print(json.dumps({k:result[k] for k in ('state','run_id','strategy','paper','gates','details')},sort_keys=True))
