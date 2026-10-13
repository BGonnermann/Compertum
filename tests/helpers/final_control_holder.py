"""Native public controls with real evaluation owner, simulated campaign receipts.

The Supervisor uses its existing partial fixture mode: no full reserve/recovery
or numerical Job acceptance is claimed by this small routing test.
"""
from pathlib import Path
import sys,json
from uuid import uuid4
root=Path(sys.argv[1]);operation=sys.argv[2]
if operation=='prepare':
 sys.path.insert(0,str(Path('tests').resolve()))
 import pytest
 from test_shortlist_owner import make_committed,owned,pair_inputs,environment
 from test_shortlist_freeze_journal import freeze_now
 from compertum.final_transaction import recipe_sha256,reserve_final
 from compertum.data.encoding import canonical
 generator=owned.__wrapped__(root);ownership=next(generator)
 try:
  with pytest.MonkeyPatch.context() as patch:
   import test_shortlist_owner as fixture
   original=fixture.canonical
   def complete_failed_state(value):
    if isinstance(value,dict) and value.get('input_kind')=='synthetic-campaign' and value.get('state')=='COMPLETED':
     value.update(campaign_version=1,results=[],maximum_bytes=128*1024**2,last_transition='FIXTURE_FAILED')
     value['attempts']=[dict(unit=o['unit'],attempt=1,identity=o['identity'],status='FAILED',input_sha256=value['request_sha256'],output_path=f"artifacts/runs/{value['run_id']}/baseline/unit-{o['unit']:02}-attempt-1.campaign",dependency_sha256=None,reason=o['reason']) for o in value['outcomes'].values() if o['status']=='FAILED']
     from compertum.simulation.campaign_runs import validate_state
     validate_state(value)
    return original(value)
   patch.setattr(fixture,'canonical',complete_failed_state)
   pair=pair_inputs.__wrapped__(environment.__wrapped__(root,patch));pair[0]['holdout_manifest_sha256']=recipe_sha256()
   seals,p,ticket,states,reviews=make_committed(ownership,pair,patch,real_runtime=True);freeze_now(seals,p,ticket)
   sid=p['source']['seal_id'];reserve_final(seals.test_storage,sid)
   result=seals.handle(dict(operation='prepare_final',seal_id=sid,evaluation_id=str(uuid4())))
   (root/'public-final.json').write_bytes(canonical(result));seals.store.close();reviews.store.close()
 finally:generator.close()
else:
 assert operation=='serve'
 from compertum.runtime.supervisor import Supervisor
 from compertum.runtime.managed import launch_owner
 from compertum.final_controller import FinalController
 from compertum.config import load_config
 s=Supervisor(load_config(root/'config.toml',root),_partial_fixture=True);remote=None
 try:
  job,remote=launch_owner(s.supervisor,'evaluation');s.jobs.append(job)
  s.final=FinalController(s.coordinator,s.storage,remote)
  s.run(maximum_seconds=30)
 finally:
  s.close()
  if remote is not None:remote.close()
