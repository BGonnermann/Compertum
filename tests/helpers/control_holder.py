"""Bounded separate-process durable control server for native tests."""
from dataclasses import asdict
import json
from pathlib import Path
import sys
import time
from compertum.runtime.identity import resolve_project
from compertum.runtime.owners import acquire_owner,release_owner
from compertum.runtime.ipc import start_role_pipe
from compertum.runtime.control import serve_control_once
from compertum.persistence import open_store
from compertum.coordinator import Coordinator

root=Path(sys.argv[1]);project=resolve_project(root)
delay=int(sys.argv[2]) if len(sys.argv)>2 else 0
assert delay in (0,6)
delayed=False
supervisor=acquire_owner(project,'supervisor');coordinator=acquire_owner(project,'coordinator')
try:
    state=Coordinator(open_store(coordinator,'coordinator'))
    endpoint=start_role_pipe(supervisor,frozenset({'pause_research','resume_research','status'}))
    (root/'route.json').write_text(json.dumps(asdict(endpoint.descriptor.registration)))
    def handle(decision,action,payload):
        global delayed
        if not delayed:delayed=True;time.sleep(delay)
        if action=='status': return state.status()
        return state.control(decision,action,payload)
    for _ in range(4): serve_control_once(endpoint,handle,timeout=5)
finally:
    release_owner(coordinator);release_owner(supervisor)

