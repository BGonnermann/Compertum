"""Native clean-start Supervisor fixture; no substitute owner or health checks."""
import ctypes as c
import hashlib,json,sys
from pathlib import Path
from compertum.runtime.startup import require_entrypoint_startup
proof=require_entrypoint_startup()
from compertum.runtime.supervisor import Supervisor
from compertum.config import load_config
from compertum.clean_pair import PairRecord,read_pair
from compertum.clean_registration import register_pair
from compertum.development_seals import create_prepared_campaign
from compertum.runtime.jobs import JobAPI

root=Path(sys.argv[1]).resolve();lane=sys.argv[2]
assert lane in {'source','wheel'}
raw=(root/'clean-pair.json').read_bytes();pair=PairRecord(raw,hashlib.sha256(raw).hexdigest())
value=read_pair(pair.content,expected_sha256=pair.sha256)
raw=(root/(lane+'-prepared.json')).read_bytes();pin=hashlib.sha256(raw).hexdigest()
s=Supervisor(load_config(root/'config.toml',root));original=s.status
try:
 register_pair(s.research.runs,pair)
 member=value[lane]
 create_prepared_campaign(s.research.runs,member['run_id'],raw,expected_sha256=pin,seal_id=member['seal_id'],evaluation=s.evaluation.remote)
 del raw
 def status():
  v=original();v['fixture_startup']=proof
  limits=JobAPI().limits(s.self_job)
  v['fixture_coordinator_peak_memory']=limits.peak_process_memory
  return v
 s.status=status
 s.run(maximum_seconds=175)
finally:s.close()