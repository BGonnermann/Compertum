"""Run bounded Windows M0 checks and retain an honest acceptance receipt.

No installs, provider requests, service starts, publication or cleanup. Existing
fixture paths must be within this checkout's checked test-runs namespace.
"""
import argparse
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time
from uuid import uuid4
import xml.etree.ElementTree as ET

GATES=('environment','contracts','ownership','durability','resources','recovery','offline','manual_bridge','local_fallback','scope_audit')


def aggregate(gates):
    if set(gates)!=set(GATES) or any(v not in {'VERIFIED_PASS','VERIFIED_FAIL','UNVERIFIED','PENDING_EXTERNAL_TIME'} for v in gates.values()):
        raise ValueError('INVALID_GATE_SET')
    return {'status':'ENGINEERING_FOUNDATIONS_READY' if all(v=='VERIFIED_PASS' for v in gates.values()) else 'M0_BLOCKED',
            'gates':dict(gates),'strategy_state':'NOT_EVALUATED','paper':'DISABLED'}



TEST_GROUPS={
    'contracts':('test_contracts','test_config','test_cli'),
    'durability':('test_persistence','test_consumption','test_coordinator'),
    'resources':('test_jobs','test_storage','test_storage_monitor','test_managed_watchdog','test_m0_lifecycle'),
    'recovery':('test_recovery','test_recovery_barrier'),
    'manual_bridge':('test_ai_manual',),
    'offline':('test_m0_lifecycle','test_foundation_fixture','test_ai_timeout'),
    'ownership':('test_ownership','test_ipc','test_bootstrap','test_remote_owners','test_control'),
}
PLATFORM_REFUSALS=frozenset(
    [f'tests.test_native_verification_gate.test_native_verification_refuses_cloud_without_creating_receipts[args{i}]' for i in range(7)]+
    ['tests.test_owner_channel.test_cloud_numeric_handle_does_not_create_remote_owner_authority',
     'tests.test_pipe_contract.test_native_pipe_adapter_refuses_cloud_without_creating_a_transport',
     'tests.test_runtime_policy.test_non_windows_identity_refuses_before_any_files_are_created',
     'tests.test_worker_bootstrap.test_cloud_cannot_receive_native_bootstrap_from_a_numeric_handle'])


def suite_gates(totals,exit_code,expected_count):
    rows=totals['cases'];gates=dict.fromkeys(TEST_GROUPS,'UNVERIFIED')
    if exit_code!=0 or any(r['status']=='FAIL' for r in rows): return dict.fromkeys(TEST_GROUPS,'VERIFIED_FAIL')
    if expected_count is None or expected_count!=len(rows) or not rows: return gates
    if any(r['status']=='SKIP' and r['name'] not in PLATFORM_REFUSALS for r in rows): return gates
    for gate,modules in TEST_GROUPS.items():
        groups=[[r for r in rows if '.'+name+'.' in '.'+r['name']] for name in modules]
        if all(group and all(r['status']=='PASS' for r in group) for group in groups): gates[gate]='VERIFIED_PASS'
    return gates


def digest(path):
    with path.open('rb') as stream: return hashlib.file_digest(stream,'sha256').hexdigest()


def source_identity(root):
    files=[p for directory in ('src/compertum','schemas','tools','tests') for p in (root/directory).rglob('*') if p.is_file() and p.suffix in {'.py','.json'}]
    files += [root/name for name in ('pyproject.toml','uv.lock','docs/BUILD_SPEC.md','docs/M0_IMPLEMENTATION_PLAN.md')]
    rows={p.relative_to(root).as_posix():digest(p) for p in sorted(files)}
    return {'sha256':hashlib.sha256(json.dumps(rows,sort_keys=True).encode()).hexdigest(),'files':rows}


def junit(path):
    rows=[]
    for case in ET.parse(path).getroot().iter('testcase'):
        status='SKIP' if case.find('skipped') is not None else 'FAIL' if case.find('failure') is not None or case.find('error') is not None else 'PASS'
        rows.append({'name':case.attrib.get('classname','')+'.'+case.attrib['name'],'status':status})
    return {'passed':sum(r['status']=='PASS' for r in rows),'failed':sum(r['status']=='FAIL' for r in rows),'skipped':sum(r['status']=='SKIP' for r in rows),'cases':rows}


def verify_m0(root,*,recovery_project=None,managed_project=None,wheel_python=None):
    root=Path(root).resolve()
    from compertum.persistence import checked_path
    from compertum.storage import sample_storage,GIB
    from compertum.runtime.identity import resolve_project
    if os.name!='nt' or platform.python_version()!='3.14.7' or sys.prefix==sys.base_prefix: raise RuntimeError('ENVIRONMENT_PREREQUISITE_UNVERIFIED')
    root=resolve_project(root).root_path
    scratch=checked_path(root,root/'.cache/test-runs');scratch.mkdir(parents=True,exist_ok=True)
    out=scratch/('m0-acceptance-'+str(uuid4()));out.mkdir()
    recovery_project=checked_path(root,Path(recovery_project).resolve()) if recovery_project else out/'recovery-project'
    managed_project=checked_path(root,Path(managed_project).resolve()) if managed_project else out/'managed-project'
    if not recovery_project.is_relative_to(scratch) or not managed_project.is_relative_to(scratch): raise RuntimeError('FIXTURE_ROOT_DENIED')
    observed=sample_storage(resolve_project(root))
    new_reserves=sum(not (p/'state/execution-reserve.bin').exists() for p in {recovery_project,managed_project})
    if observed['categories']['scratch']+new_reserves*GIB+64*1024**2>5*GIB:
        raise RuntimeError('SCRATCH_HEADROOM_UNVERIFIED')
    before=source_identity(root);commands=[]
    env={k:v for k,v in os.environ.items() if k.upper() in {'SYSTEMROOT','WINDIR','SYSTEMDRIVE','COMSPEC','PATH','PATHEXT','USERPROFILE','APPDATA','LOCALAPPDATA'}}
    temp=out/'temp';temp.mkdir();env.update(TEMP=str(temp),TMP=str(temp),PYTHONDONTWRITEBYTECODE='1',PYTHONNOUSERSITE='1')
    for name in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'): env[name]='4'
    def run(label,argv,timeout=240):
        start=time.monotonic();rawout=b'';rawerr=b''
        try:
            result=subprocess.run(argv,cwd=root,env=env,capture_output=True,timeout=timeout)
            code=result.returncode;rawout=result.stdout;rawerr=result.stderr
        except subprocess.TimeoutExpired as error:
            code=124;rawout=error.stdout or b'';rawerr=error.stderr or b''
        except OSError: code=125
        if len(rawout)+len(rawerr)>8*1024**2: code=126
        (out/(label+'.log')).write_bytes(rawout[:4*1024**2]);(out/(label+'.stderr.log')).write_bytes(rawerr[:4*1024**2])
        record={'label':label,'argv':list(map(str,argv)),'exit_code':code,'elapsed_seconds':time.monotonic()-start,'stdout':str((out/(label+'.log')).relative_to(root)),'stderr':str((out/(label+'.stderr.log')).relative_to(root))}
        commands.append(record)
        with (out/'commands.jsonl').open('a',encoding='utf-8') as stream: stream.write(json.dumps(record)+'\n')
        print(json.dumps({'label':label,'exit_code':code,'elapsed_seconds':record['elapsed_seconds']}),flush=True)
        return code,rawout
    tests=out/'all.xml'
    run('environment',[sys.executable,'-B',str(root/'tools/verify_environment.py'),'--project-root',str(root)])
    run('doctor',[sys.executable,'-B','-m','compertum','--project-root',str(root),'doctor','--read-only','--json'])
    managed_project.mkdir(parents=True,exist_ok=True)
    config=managed_project/'config.toml'
    if not config.exists():
        with config.open('xb') as stream: stream.write((root/'config/default.toml').read_bytes())
    run('offline-source',[sys.executable,'-B','-m','compertum','--project-root',str(managed_project),'foundation','check','--suite','m0','--offline','--config','config.toml','--json'],60)
    if wheel_python:
        wheel_python=Path(wheel_python).resolve()
        run('wheel-environment',[str(wheel_python),'-B',str(root/'tools/verify_environment.py'),'--project-root',str(root)])
        run('wheel-contracts',[str(wheel_python),'-B','-m','pytest','-q','tests/test_contracts.py','tests/test_config.py','tests/test_persistence.py','--tb=short','--basetemp',str(out/'wheel-tests'),'--junitxml',str(out/'wheel.xml')])
        run('offline-wheel',[str(wheel_python),'-B','-m','compertum','--project-root',str(managed_project),'foundation','check','--suite','m0','--offline','--config','config.toml','--json'],60)
    # Run the healthy-owner phase before recovery tests intentionally and
    # permanently compromise this disposable project's evaluation authority.
    # Every test file is still included once; no gate is skipped or relaxed.
    first=root/'tests/windows/test_recovery_barrier.py'
    files=sorted({*root.joinpath('tests').rglob('test_*.py'),*root.joinpath('tests').rglob('*_test.py')})
    files=[first,*[p for p in files if p!=first]]
    collect_code,collected=run('collection',[sys.executable,'-B','-m','pytest',*map(str,files),'--collect-only','-q'])
    expected_count=sum('::' in line for line in collected.decode('utf-8',errors='replace').splitlines()) if collect_code==0 else None
    run('full-suite',[sys.executable,'-B','-m','pytest',*map(str,files),'-q','--tb=short','--basetemp',str(out/'pytest'),'--junitxml',str(tests),'--m0-recovery-project',str(recovery_project),'--m0-managed-project',str(managed_project)],600)
    run('native-ownership',[sys.executable,'-B',str(root/'tools/verify_native_ownership.py'),'--suite','all','--run-fixtures'],150)
    gates=dict.fromkeys(GATES,'UNVERIFIED');bylabel={r['label']:r for r in commands}
    def good(*labels): return all(label in bylabel and bylabel[label]['exit_code']==0 for label in labels)
    totals=junit(tests) if tests.exists() else {'passed':0,'failed':0,'skipped':0,'cases':[]}
    gates.update(suite_gates(totals,bylabel['full-suite']['exit_code'],expected_count))
    if not good('native-ownership'): gates['ownership']='UNVERIFIED'
    if good('environment','wheel-environment','wheel-contracts'): gates['environment']='VERIFIED_PASS'
    offline_tests=gates['offline'];gates['offline']='UNVERIFIED'
    if offline_tests=='VERIFIED_PASS' and good('offline-source','offline-wheel'):
        one=json.loads((out/'offline-source.log').read_bytes());two=json.loads((out/'offline-wheel.log').read_bytes())
        expected=hashlib.sha256(b'compertum-offline-fixture-v1\n').hexdigest()
        if one.get('artifact',{}).get('sha256')==two.get('artifact',{}).get('sha256')==expected: gates['offline']='VERIFIED_PASS'
    # Live qualification and independent review require their own current,
    # attributable evidence. Portable tests cannot fill either gate.
    after=source_identity(root)
    if before!=after: gates={k:'UNVERIFIED' for k in GATES}
    receipt=aggregate(gates)|{'created_at':datetime.now(timezone.utc).isoformat(),'python':platform.python_version(),'windows':platform.platform(),
        'source':before,'source_unchanged':before==after,'commands':commands,'test_counts':{k:v for k,v in totals.items() if k!='cases'},'expected_test_count':expected_count,
        'limitations':['Live Strata qualification requires explicit request authority and fresh native model evidence.','Independent review disposition must be reconciled with this exact source.'],
        'evidence_directory':str(out),'fixture_projects':[str(recovery_project),str(managed_project)]}
    (out/'result.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':receipt['status'],'gates':gates,'evidence_directory':str(out)}),flush=True)
    return receipt


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--project-root',type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument('--recovery-project',type=Path);parser.add_argument('--managed-project',type=Path);parser.add_argument('--wheel-python',type=Path)
    args=parser.parse_args()
    result=verify_m0(args.project_root,recovery_project=args.recovery_project,managed_project=args.managed_project,wheel_python=args.wheel_python)
    return 0 if result['status']=='ENGINEERING_FOUNDATIONS_READY' else 3

if __name__=='__main__': raise SystemExit(main())
