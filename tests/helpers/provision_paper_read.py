"""Invented credential provisioning in a process that must exit before ownership transfers."""
from pathlib import Path
import sys
from compertum.config import load_config
from compertum.runtime.identity import resolve_project
from compertum.runtime.owners import acquire_owner,release_owner
from compertum.runtime.paper_credentials import seal_paper_credentials
from compertum.runtime.paper_credential_slot import provision_paper_slot
from compertum.storage import StorageManager,reserve_runtime_paths
from compertum.persistence import open_store
root=Path(sys.argv[1]).resolve();assert '.cache' in root.parts and 'test-runs' in root.parts
config=load_config(root/'config.toml',root);project=resolve_project(root)
coord=acquire_owner(project,'coordinator');execution=acquire_owner(project,'execution')
try:
 m=StorageManager(coord,config);reserve_runtime_paths(m)
 open_store(execution,'execution')
 p=seal_paper_credentials(execution,'fixture',bytearray(b'INVENTED_KEY_12345'),bytearray(b'INVENTED_SECRET_12345'))
 provision_paper_slot(execution,p)
finally:release_owner(execution);release_owner(coord)

