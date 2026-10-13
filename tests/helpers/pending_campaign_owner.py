"""Exit a real owner process with an uncommitted cooperative resume."""
import json,os,sys
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from test_saved_campaigns import setup
from compertum.runtime.owners import acquire_owner,release_owner
from compertum.runtime.identity import resolve_project
from compertum.research import ResearchController
project=resolve_project(Path(sys.argv[1]));lease=acquire_owner(project,'coordinator')
try:
    storage,runs,run,_=setup((project,{'coordinator':lease}))
    controller=ResearchController(SimpleNamespace(status=lambda:{'research_state':'RUNNING'},require_health=lambda:None),storage,cooperative=True)
    controller.control(run,str(uuid4()),'resume');proof=controller.pending.proof;controller.tick()
    assert proof.bundle is not None and controller.active is None and runs.summary(run)['attempts']==[]
finally:release_owner(lease)
assert proof.closed and proof.state is None
print(json.dumps(dict(run_id=run,pid=os.getpid(),proof_closed=True)))
