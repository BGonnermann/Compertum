"""One pre-effect invented account declaration; preparation process exits first."""
from pathlib import Path
import sys,json,os
import compertum
from compertum.runtime.identity import resolve_project
from compertum.runtime.owners import acquire_owner,release_owner
from compertum.persistence import open_store
from compertum.fake_execution_journal import FakeIntentJournal
from compertum.deterministic_broker import DeterministicBroker
from compertum.fake_economic_opening import provision_opening
root=Path(sys.argv[1]).resolve();assert '.cache' in root.parts and 'test-runs' in root.parts
project=resolve_project(root);lease=acquire_owner(project,'execution')
try:
 store=open_store(lease,'execution');FakeIntentJournal(store)
 broker=DeterministicBroker(root/'state/fake-broker',cash='5500',positions={'AAPL':45})
 try:
  pin=provision_opening(store,broker,cash='5500',positions={'AAPL':45})
  receipt={'status':'OPENING_PROVISIONED','generation':lease.generation,'pid':os.getpid(),'package_origin':str(Path(compertum.__file__).resolve()),'opening':pin}
 finally:broker.close()
finally:release_owner(lease)

print(json.dumps(receipt),flush=True)
