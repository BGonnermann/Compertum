"""Separate processes preserve the native prior-owner-exit requirement."""
from pathlib import Path
import json,sys,os
from uuid import uuid4
sys.path.insert(0,str(Path(__file__).parents[1]))
from compertum.runtime.identity import resolve_project
from compertum.runtime.owners import acquire_owner,release_owner
from compertum.consumption import verify_consumption_guard
from compertum.evaluation_seals import verify_seal_journal
from compertum.recovery import restore_recovery_set,recover_interrupted_restore
root=Path(sys.argv[1]);action=sys.argv[2];project=resolve_project(root)
if action.startswith('prepare'):
 from test_recovery_snapshot_closure import prepared
 from test_evaluation_seals import invalidate
 leases={r:acquire_owner(project,r) for r in ('coordinator','evaluation','execution')}
 try:
  seals,sid,a,result=prepared((project,leases))
  if action=='prepare_restore':
   invalidate(seals,sid,'STATUS_UNCERTAIN');original=project.root_path/a['path'];original.rename(original.with_suffix('.retained'))
  answer=dict(manifest_path=result['manifest_path'],artifact=a,latest=verify_seal_journal(project))
 finally:
  for lease in leases.values():release_owner(lease)
elif action in ('restore','crash_restore'):
 if action=='crash_restore':
  from compertum.runtime._windows import WindowsAPI
  original=WindowsAPI.publish_metadata
  def crash(api,path,raw):
   original(api,path,raw)
   if path.name=='active-generation.json':os._exit(17)
  WindowsAPI.publish_metadata=crash
 answer=restore_recovery_set(sys.argv[3],verify_consumption_guard(project),project.root_path/'state/generations'/str(uuid4()),project=project)
elif action=='recover':answer=recover_interrupted_restore(project)
else:raise ValueError('unknown bounded fixture action')
print(json.dumps(answer))
