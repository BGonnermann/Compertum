"""A bounded isolated engineering fixture, never a strategy result."""
import time,json
from pathlib import Path
from .domain import new_id,receipt,digest,atomic_json
from .coordinator import FIXTURE
from .cli import start_research,control

def run_foundation_suite(root,offline=True):
    if not offline:raise ValueError('M0_OFFLINE_ONLY')
    target=Path(root)/'.cache/foundation'/new_id();target.mkdir(parents=True)
    start_research(target);deadline=time.monotonic()+15
    try:
        while time.monotonic()<deadline:
            status=control(target,'status')['result']
            if status['storage_healthy']:break
            time.sleep(.1)
        resumed=control(target,'resume')
        if resumed['exit_code']:raise RuntimeError('FOUNDATION_HEALTH_UNVERIFIED')
        task=control(target,'fixture')['result'];tid=task['task_id']
        while time.monotonic()<deadline:
            status=control(target,'status')['result'];task=next(t for t in status['tasks'] if t['task_id']==tid)
            if task['state']=='COMPLETE':break
            time.sleep(.1)
        if task['state']!='COMPLETE' or task['artifact']['sha256']!=digest(FIXTURE):raise RuntimeError('FOUNDATION_FIXTURE_FAILED')
        result=receipt('foundation');result['result']={'state':'FIXTURE_VERIFIED','artifact':task['artifact'],'sha256':digest(FIXTURE),'fixture_root':str(target),'strategy':'STRATEGY_NOT_EVALUATED','paper':'PAPER_DISABLED','project_admission':'NOT_CERTIFIED'}
        atomic_json(target/'foundation-receipt.json',result);return result
    finally:control(target,'shutdown')
