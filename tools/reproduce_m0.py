"""Non-editable installed-wheel evidence from outside the source import path."""
import importlib.metadata,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from compertum.domain import atomic_json,file_hash,now,new_id

def reproduce_m0():
    clean=ROOT/'.cache/clean-env-m0/Scripts/python.exe';workspace=ROOT/'.cache/clean-runs'/new_id();workspace.mkdir(parents=True)
    records=[]
    def run(args):
        value=subprocess.run([str(clean),'-B',*args],cwd=workspace,capture_output=True,text=True,timeout=40)
        record={'argv':[str(clean),'-B',*args],'cwd':str(workspace),'exit_code':value.returncode,'stdout':value.stdout,'stderr':value.stderr};records.append(record)
        if value.returncode:raise RuntimeError('CLEAN_REPRODUCTION_FAILED')
        return json.loads(value.stdout)
    identity=run(['-c','import compertum,json,importlib.metadata;print(json.dumps({"module":compertum.__file__,"packages":{d.metadata["Name"].lower():d.version for d in importlib.metadata.distributions()}}))'])
    if not Path(identity['module']).resolve().is_relative_to(ROOT/'.cache/clean-env-m0'):raise RuntimeError('EDITABLE_SOURCE_LEAK')
    current={d.metadata['Name'].lower():d.version for d in importlib.metadata.distributions()}
    if current!=identity['packages']:raise RuntimeError('ENVIRONMENT_VERSION_MISMATCH')
    doctor=run(['-m','compertum','doctor','--read-only','--json']);foundation=run(['-m','compertum','foundation','check','--suite','m0','--offline','--json'])
    check='''
from pathlib import Path
import json
from compertum.domain import TaskSpec,validate_record
from compertum.runtime.identity import resolve_project
from compertum.runtime.owners import acquire_owner
from compertum.persistence import open_store
r=Path.cwd()/'state-check';r.mkdir();p=resolve_project(r)
with acquire_owner(p,'coordinator') as l:
 s=open_store(l,'coordinator');event={'event_id':'clean-delivery','kind':'TASK_STATUS','payload':{'fixture':True}};s.accept_message(event);s.accept_message(event);assert s.get('accepted_transitions')==1;s.close()
validate_record('task',TaskSpec().record());print(json.dumps({'state':'SCHEMA_STATE_VERIFIED','transitions':1}))
'''
    state=run(['-c',check]);baseline=json.loads((ROOT/'artifacts/m0/foundation.json').read_text());prior=json.loads(baseline['stdout'])
    if foundation['result']['sha256']!=prior['result']['sha256']:raise RuntimeError('FIXTURE_HASH_MISMATCH')
    result={'at':now(),'state':'VERIFIED_PASS','noneditable':True,'identity':identity,'wheel_sha256':file_hash(ROOT/'.cache/m0-wheel/compertum-0.1.0-py3-none-any.whl'),'lock_sha256':file_hash(ROOT/'uv.lock'),'foundation_hash':foundation['result']['sha256'],'schema_state':state,'commands':records}
    atomic_json(ROOT/'artifacts/m0/clean_reproduction.json',result);return {'state':result['state'],'foundation_hash':result['foundation_hash'],'package_count':len(current),'noneditable':True}

if __name__=='__main__':print(json.dumps(reproduce_m0(),sort_keys=True))
