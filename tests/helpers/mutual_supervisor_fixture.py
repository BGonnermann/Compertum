"""Bounded native supervisor fixture; effects remain disabled."""
from pathlib import Path
import json,sys,time
from compertum.config import load_config
from compertum.runtime.supervisor import Supervisor
from compertum.runtime.owner_rpc import call_owner
root=Path(sys.argv[1]).resolve();victim=sys.argv[2];assert victim in {'execution','watchdog'}
s=Supervisor(load_config(root/'config.toml',root))
try:
 for _ in range(3):
  s.poll_health();assert s.health['status']=='HEALTHY',s.health
  assert s.health['mutual']['verified'] and s.health['owners']['execution']['mutual']['verified']
  time.sleep(.1)
 execution=s.health['owners']['execution'];reserve=execution['reserve']
 assert reserve['capacity_bytes']==reserve['unused_bytes']==1024**3 and reserve['allocated_bytes']>=1024**3
 remote=s.execution.remote if victim=='execution' else s.watchdog
 target=next(job for job in s.jobs if job.pid==remote.descriptor.registration.identity.pid)
 target.close();survivor=s.watchdog if victim=='execution' else s.execution.remote
 began=time.monotonic();observed=None
 while time.monotonic()-began<2:
  observed=call_owner(survivor,'status',{})
  if observed['mutual']['reason']=='PEER_UNAVAILABLE':break
  time.sleep(.05)
 elapsed=time.monotonic()-began
 assert observed['mutual']['reason']=='PEER_UNAVAILABLE' and not observed['mutual']['verified'] and elapsed<2
 s.poll_health();assert s.health['status']=='RESEARCH_BLOCKED'
 print(json.dumps(dict(status='PASS',victim=victim,peer_exit_seconds=elapsed,reserve=reserve,supervisor_relay_verified=True,peer_exit_detected=True,financial_accepted=False)))
finally:s.close()
