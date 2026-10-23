"""Coordinator-owned reviewed registration. No execution or automatic recovery."""
import hashlib
import json

from compertum.events import canonical, uuid
from compertum.domain import validate_record
from compertum.runtime.errors import RuntimeRefused
from compertum.runtime.ipc import ProtocolDecision
from compertum.runtime.owners import require_live_owner
from compertum.ai.history import _plan, _campaign, _published

ACTION = 'register_reviewed_campaign'
FIELDS = {'task_id', 'plan_sha256', 'run_id', 'prepared_sha256', 'seal_id',
          'maximum_bytes', 'approval'}


def _need(condition, reason='REGISTRATION_APPROVAL_REQUIRED'):
    if not condition:
        raise RuntimeRefused(reason)


def _key(kind, identity):
    return 'review_registration_'+kind+':'+identity


def _artifact(manifest):
    return {key: manifest[key] for key in ('artifact_id', 'path', 'size_bytes', 'sha256')}


def _fingerprint(store, subject, generation, payload):
    value = dict(subject=subject, action=ACTION, payload=payload, target_role='coordinator',
        target_generation=generation, project_id=store.lease.project_id)
    return hashlib.sha256(canonical(value)).hexdigest()


def require_complete(runs, run_id):
    """Incomplete registration never permits resume or unit preparation."""
    with runs.store._live():
        request_id = runs.store.get_state(_key('run', run_id))
        if request_id is None:
            return
        row = runs.store.conn.execute(
            'SELECT action,payload,receipt FROM control_requests WHERE request_id=?',
            (request_id,)).fetchone()
        _need(row is not None and row[0] == ACTION, 'REGISTRATION_INCOMPLETE')
        payload, receipt = json.loads(row[1]), json.loads(row[2])
        _need(payload.get('run_id') == run_id and receipt.get('request_id') == request_id
            and receipt.get('action') == ACTION and receipt.get('state') == 'CONFIRMED'
            and receipt.get('confirmed') is True, 'REGISTRATION_INCOMPLETE')
        validate_record('control_receipt.v1', receipt, project_root=runs.store.root)
        from compertum.ai.manual import ManualBridge
        bridge = ManualBridge(runs.storage)
        plan, artifact = _plan(bridge, payload['task_id'])
        raw, link_artifact = _published(bridge, payload['task_id'], 'campaign-link.json')
        link = json.loads(raw)
        state = runs._load(run_id)
        # The original confirmed receipt binds the full link. Do not walk result
        # artifacts here; cooperative campaign verification owns those checks.
        _need(link.get('run_id') == run_id and link.get('task_id') == payload['task_id']
            and artifact['sha256'] == payload['plan_sha256']
            and link.get('review_plan') == artifact
            and link.get('request_sha256') == state['request_sha256'] == payload['prepared_sha256']
            and state['maximum_bytes'] == payload['maximum_bytes']
            and receipt['artifacts'] == [_artifact(artifact),
                _artifact(state['input_artifact']), _artifact(link_artifact)],
            'REGISTRATION_EVIDENCE_CHANGED')


def register(coordinator, decision, payload, *, controller, bridge, prepared_raw, evaluation):
    """Consume an exact authenticated operator decision; retain partial effects.

    This owner-facing API receives a ProtocolDecision from trusted control code.
    No CLI or worker command is added to an authentication allowlist here.
    """
    from compertum.coordinator import utc_now
    from compertum.research import ResearchController
    from compertum.ai.manual import ManualBridge
    from compertum import development_seals
    from compertum.prepared_campaign import read_prepared
    from compertum.evaluation_protocol import digest

    store = coordinator.store
    require_live_owner(store.lease, 'coordinator')
    _need(isinstance(controller, ResearchController) and controller.coordinator is coordinator
        and controller.store is store and isinstance(bridge, ManualBridge)
        and bridge.storage is controller.storage and bridge.store is store,
        'REGISTRATION_OWNER_MISMATCH')
    _need(type(payload) is dict and set(payload) == FIELDS)
    _need(type(decision) is ProtocolDecision)
    uuid(decision.request_id)
    for field in ('task_id', 'run_id', 'seal_id'):
        uuid(payload[field])
    for field in ('plan_sha256', 'prepared_sha256'):
        digest(payload[field])
    digest(decision.subject_key)
    _need(payload['approval'] == 'REGISTER_PAUSED_CAMPAIGN'
        and type(payload['maximum_bytes']) is int and 0 < payload['maximum_bytes'] <= 128*1024**2)
    _need(type(decision.target_generation) is int and decision.target_generation == store.lease.generation)
    _need(decision.payload_hash == _fingerprint(store, decision.subject_key, decision.target_generation, payload))

    with store._live():
        controller._require_recovery_clear()
        _need(not controller.busy, 'JOB_SLOT_BUSY')
        coordinator.require_health()
        plan, plan_artifact = _plan(bridge, payload['task_id'])
        _need(plan_artifact['sha256'] == payload['plan_sha256'], 'REGISTRATION_PLAN_CHANGED')
        bundle, pair, lane = read_prepared(prepared_raw, expected_sha256=payload['prepared_sha256'],
            identity=development_seals.runtime_identity())
        member = json.loads(pair.content)[lane]
        _need(member['run_id'] == payload['run_id'] and member['seal_id'] == payload['seal_id']
            and bundle['maximum_bytes'] == payload['maximum_bytes'], 'REGISTRATION_INPUT_CHANGED')
        binding = (decision.subject_key, decision.payload_hash, decision.target_generation, ACTION, canonical(payload).decode())
        old = store.conn.execute(
            'SELECT subject,payload_hash,generation,action,payload,receipt FROM control_requests WHERE request_id=?',
            (decision.request_id,)).fetchone()
        if old is not None:
            # Authenticate recovery against the new owner without replacing the
            # original operator, generation, payload hash, or approval record.
            _need(old[0] == decision.subject_key and old[3:5] == binding[3:5]
                and type(old[2]) is int and 0 < old[2] <= decision.target_generation
                and old[1] == _fingerprint(store, old[0], old[2], payload), 'REGISTRATION_CONFLICT')
        for kind, identity in (('run', payload['run_id']), ('task', payload['task_id'])):
            saved = store.get_state(_key(kind, identity))
            _need(saved == decision.request_id if old else saved is None, 'REGISTRATION_CONFLICT')
        exists = store.conn.execute('SELECT 1 FROM baseline_runs WHERE run_id=?', (payload['run_id'],)).fetchone()
        if old is None:
            _need(not exists, 'REGISTRATION_CONFLICT')
            link_path = f"artifacts/runs/{payload['task_id']}/ai/campaign-link.json"
            _need(not store.conn.execute('SELECT 1 FROM reservations WHERE path=?', (link_path,)).fetchone(),
                'REGISTRATION_CONFLICT')
            _need(store.conn.execute('SELECT count(*) FROM control_requests').fetchone()[0] < 10000,
                'CONTROL_LEDGER_FULL')
            controller.storage._capacity('records', payload['maximum_bytes'])
            now = utc_now()
            receipt = dict(schema_version='1', record_type='ControlReceipt', request_id=decision.request_id,
                action=ACTION, target=payload['run_id'], state='PENDING', evidence_label='UNVERIFIED', confirmed=False,
                generation=decision.target_generation, requested_at=now, observed_at=None, exit_code=None,
                reason='REGISTRATION_INCOMPLETE', artifacts=[_artifact(plan_artifact)])
            validate_record('control_receipt.v1', receipt, project_root=store.root)
            # Commit the whole request before seal or campaign persistence.
            with store.conn:
                store.conn.execute('INSERT INTO control_requests VALUES(?,?,?,?,?,?,?)',
                    (decision.request_id, *binding, canonical(receipt).decode()))
                coordinator._state(_key('run', payload['run_id']), decision.request_id)
                coordinator._state(_key('task', payload['task_id']), decision.request_id)
        else:
            receipt = json.loads(old[5])
            validate_record('control_receipt.v1', receipt, project_root=store.root)
            _need(receipt['state'] in ('PENDING', 'CONFIRMED'), 'REGISTRATION_INCOMPLETE')
            _need(receipt['request_id'] == decision.request_id and receipt['action'] == ACTION
                and receipt['target'] == payload['run_id'] and receipt['generation'] == old[2],
                'REGISTRATION_CONFLICT')

        if not exists:
            _need(receipt['state'] == 'PENDING', 'REGISTRATION_INCOMPLETE')
            development_seals.create_prepared_campaign(controller.runs, payload['run_id'], prepared_raw,
                expected_sha256=payload['prepared_sha256'], seal_id=payload['seal_id'], evaluation=evaluation)
        state, campaign = _campaign(bridge, controller.runs, payload['run_id'])
        development_seals.check_campaign_seal(store, state)
        _need(state['request_sha256'] == payload['prepared_sha256']
            and state['maximum_bytes'] == payload['maximum_bytes'], 'REGISTRATION_INPUT_CHANGED')
        if receipt['state'] == 'CONFIRMED':
            history = bridge.review_history(payload['task_id'], runs=controller.runs)
            _need(history['campaign']['run_id'] == payload['run_id']
                and receipt['artifacts'] == [_artifact(plan_artifact), _artifact(state['input_artifact']), _artifact(history['link'])],
                'REGISTRATION_CONFLICT')
            return receipt
        _need(state['state'] == 'PAUSED' and not state['attempts'] and not state['outcomes'],
            'REGISTRATION_INCOMPLETE')
        # After campaign persistence recovery only completes the missing link.
        link = bridge.link_review_campaign(payload['task_id'], payload['run_id'], runs=controller.runs)
        receipt.update(state='CONFIRMED', evidence_label='VERIFIED_PASS', confirmed=True,
            observed_at=utc_now(), exit_code=0, reason='CAMPAIGN_REGISTERED_PAUSED',
            artifacts=[_artifact(plan_artifact), _artifact(state['input_artifact']), _artifact(link)])
        validate_record('control_receipt.v1', receipt, project_root=store.root)
        with store.conn:
            store.conn.execute('UPDATE control_requests SET receipt=? WHERE request_id=?',
                (canonical(receipt).decode(), decision.request_id))
        return receipt
