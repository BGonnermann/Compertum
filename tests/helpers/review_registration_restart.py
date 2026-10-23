"""Two real owner lifetimes over one synthetic registration fixture."""
import json
from dataclasses import asdict
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pytest import MonkeyPatch
from compertum.runtime.identity import resolve_project
from compertum.runtime.owners import acquire_owner, release_owner
from compertum.runtime.ipc import ProtocolDecision
from compertum.coordinator import Coordinator
from compertum.research import ResearchController
from compertum.ai.manual import ManualBridge
from compertum.storage import StorageManager
from compertum.config import load_config
from compertum.evaluation_seals import EvaluationSeals
from compertum.persistence import open_store
from test_ai_campaign_registration import setup, decision, register
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
        parts = setup(fixture)
        c, controller, bridge, seals, raw, payload = parts
        approval = decision(c, payload)
        def interrupted(*args, **kwargs):
            raise OSError('synthetic crash after campaign persistence')
        patch.setattr(bridge, 'link_review_campaign', interrupted)
        try:
            register(parts, approval)
        except OSError:
            pass
        else:
            raise AssertionError('interruption did not happen')
        binding = c.store.conn.execute('SELECT subject,payload_hash,generation,action,payload FROM control_requests WHERE request_id=?',
            (approval.request_id,)).fetchone()
        state = controller.runs._load(payload['run_id'])
        handoff = dict(payload=payload, approval=asdict(approval), binding=binding,
            runtime=state['identity'], input_path=state['input_artifact']['path'])
        with (root/'restart-handoff.json').open('x') as stream:
            json.dump(handoff, stream)
    else:
        handoff = json.loads((root/'restart-handoff.json').read_text())
        import compertum.development_seals as d
        import compertum.evaluation_seals as e
        import compertum.simulation.runs as r
        for module in (d, e, r):
            patch.setattr(module, 'runtime_identity', lambda: handoff['runtime'])
        storage = StorageManager(leases['coordinator'], load_config(root/'config.toml', root))
        c = Coordinator(storage.store, health=lambda: dict(status='HEALTHY', observed_monotonic=time.monotonic()))
        controller = ResearchController(c, storage)
        bridge = ManualBridge(storage)
        seals = EvaluationSeals(open_store(leases['evaluation'], 'evaluation'))
        payload = handoff['payload']
        raw = (root/handoff['input_path']).read_bytes()
        fresh = decision(c, payload, request_id=handoff['approval']['request_id'])
        def forbidden(*args, **kwargs):
            raise AssertionError('recovery recreated campaign')
        patch.setattr(d, 'create_prepared_campaign', forbidden)
        result = register((c, controller, bridge, seals, raw, payload), fresh)
        binding = c.store.conn.execute('SELECT subject,payload_hash,generation,action,payload FROM control_requests WHERE request_id=?',
            (fresh.request_id,)).fetchone()
        state = controller.runs.summary(payload['run_id'])
        report = dict(generation_before=handoff['approval']['target_generation'], generation_after=fresh.target_generation,
            campaigns=c.store.conn.execute('SELECT count(*) FROM baseline_runs').fetchone()[0],
            attempts=state['attempts'], state=state['state'], original_approval_preserved=list(binding) == handoff['binding'])
        assert result['generation'] == report['generation_before']
        with (root/'restart-result.json').open('x') as stream:
            json.dump(report, stream)
finally:
    patch.undo()
    for lease in leases.values():
        release_owner(lease)
