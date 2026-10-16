"""Real independent owners stay responsive during a slow admission scan."""
import json,sys,time
from pathlib import Path
from compertum.config import load_config
from compertum.runtime.supervisor import Supervisor
from compertum.runtime.owner_rpc import call_owner

root=Path(sys.argv[1]);supervisor=Supervisor(load_config(root/'config.toml',root))
try:
    probe=supervisor.storage.health_probe;delayed=[False];samples=[]
    def slow_probe():
        if not delayed[0]:
            delayed[0]=True;until=time.monotonic()+16.2
            while time.monotonic()<until:
                probe();samples.append(supervisor.get_health());time.sleep(.05)
        probe()
    supervisor.storage.health_probe=slow_probe
    observation=supervisor.storage.observation()
    assert 16<=observation['scan_seconds']<30
    supervisor.poll_health()
    assert supervisor.health['status']=='HEALTHY'
    assert supervisor.health['mutual']['verified']
    assert supervisor.health['owners']['execution']['mutual']['verified']
    assert all(value['status']=='HEALTHY' for value in samples)
    reserve=supervisor.health['owners']['execution']['reserve']
    assert reserve['capacity_bytes']==reserve['unused_bytes']==1024**3
    assert reserve['allocated_bytes']>=1024**3 and not reserve['sparse']
    supervisor.jobs[1].close()
    until=time.monotonic()+3
    while time.monotonic()<until:
        status=call_owner(supervisor.watchdog,'status',{})
        if status['reason']=='PEER_UNAVAILABLE':break
        time.sleep(.05)
    assert status['reason']=='PEER_UNAVAILABLE'
    print(json.dumps(dict(status='VERIFIED',scan_seconds=observation['scan_seconds'],
        health_samples=len(samples),reserve=reserve,peer_loss_reason=status['reason'])))
finally:supervisor.close()
