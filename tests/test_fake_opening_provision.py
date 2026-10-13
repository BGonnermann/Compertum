"""Actual preparation exit and selected package origin; no reserve claim."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent/'windows'))
from test_fake_operator_control import provision
from compertum.runtime.identity import resolve_project
from compertum.runtime.owners import acquire_owner,release_owner
from compertum.persistence import open_store
from compertum.fake_execution_journal import FakeIntentJournal
from compertum.deterministic_broker import DeterministicBroker
from compertum.fake_economic_opening import require_opening

def test_native_provision_process_exits_before_replacement_owner(tmp_path):
 receipt=provision(tmp_path);assert receipt['generation']==1
 project=resolve_project(tmp_path);lease=acquire_owner(project,'execution')
 try:
  assert lease.generation==2
  store=open_store(lease,'execution');FakeIntentJournal(store)
  b=DeterministicBroker(tmp_path/'state/fake-broker',create=False)
  try:assert require_opening(store,b)=={'account_alias':'fake-account','cash':'5500','positions':{'AAPL':45}}
  finally:b.close()
 finally:release_owner(lease)
