"""Two real owner lifetimes around a consumed start, before native launch."""
import json
from dataclasses import asdict, replace
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pytest import MonkeyPatch
from compertum.runtime.identity import resolve_project
from compertum.runtime.owners import acquire_owner, release_owner
from compertum.coordinator import Coordinator
from compertum.research import ResearchController
from compertum.storage import StorageManager
from compertum.config import load_config
from test_ai_campaign_start import ready, decision, start
from test_prepared_campaign import prepared
from test_clean_pair import pair_inputs
from test_environment_manifest import environment

root, stage = Path(sys.argv[1]), sys.argv[2]
project = resolve_project(root)
leases = {role: acquire_owner(project, role) for role in ('coordinator', 'evaluation', 'execution')}
patch = MonkeyPatch()
try:
    if stage == 'interrupt':
        inputs = pair_inputs.__wrapped__(environment.__wrapped__(root, patch))
        fixture = prepared.__wrapped__((project, leases), inputs, patch)
        parts, payload = ready(fixture)
        c, controller = parts[:2]
        approval = decision(c, payload)
        receipt = start(parts, payload, approval)
        for _ in range(20):
            if controller.runs.summary(payload['run_id'])['state'] == 'READY': break
            controller.tick()
        assert controller.runs.summary(payload['run_id'])['state'] == 'READY'
        assert controller.active is None
        binding = c.store.conn.execute('SELECT subject,payload_hash,generation,action,payload FROM control_requests WHERE request_id=?',
            (approval.request_id,)).fetchone()
        with (root/'start-handoff.json').open('x') as stream:
            json.dump(dict(payload=payload, approval=asdict(approval), receipt=receipt, binding=binding), stream)
        controller.pending.close()
        controller.pending = None
    else:
        handoff = json.loads((root/'start-handoff.json').read_text())
        storage = StorageManager(leases['coordinator'], load_config(root/'config.toml', root))
        c = Coordinator(storage.store, health=lambda: dict(status='HEALTHY', observed_monotonic=time.monotonic()))
        controller = ResearchController(c, storage, cooperative=True)
        fresh = replace(decision(c, handoff['payload']), request_id=handoff['approval']['request_id'])
        result = c.start_reviewed_campaign(fresh, handoff['payload'], controller=controller)
        assert result == handoff['receipt']
        assert fresh.target_generation > handoff['approval']['target_generation']
        assert controller.pending is None and controller.active is None
        state = controller.runs.summary(handoff['payload']['run_id'])
        assert state['state'] == 'PAUSED' and state['attempts'] == []
        binding = c.store.conn.execute('SELECT subject,payload_hash,generation,action,payload FROM control_requests WHERE request_id=?',
            (fresh.request_id,)).fetchone()
        assert list(binding) == handoff['binding']
        with (root/'start-restart-result.json').open('x') as stream:
            json.dump(dict(generation_before=handoff['approval']['target_generation'], generation_after=fresh.target_generation,
                state=state['state'], attempts=state['attempts'], receipt_state=result['state']), stream)
finally:
    patch.undo()
    for lease in leases.values(): release_owner(lease)
