"""Explicit first-unit approval through the existing cooperative research runner."""
import hashlib
import json
from datetime import datetime, timezone
from uuid import uuid5, NAMESPACE_URL

from compertum.domain import validate_record
from compertum.events import canonical, uuid
from compertum.evaluation_protocol import digest
from compertum.runtime.errors import RuntimeRefused
from compertum.runtime.ipc import ProtocolDecision
from compertum.runtime.owners import require_live_owner
from .registration import require_complete

ACTION = 'start_reviewed_campaign'
FIELDS = {'registration_request_id', 'run_id', 'approval'}


def _need(condition, reason='START_APPROVAL_REQUIRED'):
    if not condition:
        raise RuntimeRefused(reason)


def _fingerprint(store, subject, generation, payload):
    return hashlib.sha256(canonical(dict(subject=subject, action=ACTION, payload=payload,
        target_role='coordinator', target_generation=generation, project_id=store.lease.project_id))).hexdigest()


def _saved(store, request_id):
    row = store.conn.execute('SELECT receipt FROM control_requests WHERE request_id=?', (request_id,)).fetchone()
    _need(row is not None, 'START_RECORD_MISSING')
    receipt = json.loads(row[0])
    validate_record('control_receipt.v1', receipt, project_root=store.root)
    return receipt


class _StartOperation:
    """One resume followed by one step, under the original shared deadline."""
    action = ACTION

    def __init__(self, controller, run_id, request_id):
        from compertum.campaign_operation import _CampaignOperation
        self.controller = controller
        self.run_id = run_id
        self.request_id = request_id
        self.created_at = datetime.now(timezone.utc)
        self.inner = _CampaignOperation(controller, run_id, 'resume', created_at=self.created_at,
            request_id=str(uuid5(NAMESPACE_URL, request_id+'/resume')))

    @property
    def phase(self):
        return self.inner.phase

    def view(self):
        return dict(self.inner.view(), operation=ACTION)

    def _record(self, *, failed=False, reason):
        from compertum.coordinator import utc_now
        store = self.controller.store
        receipt = _saved(store, self.request_id)
        receipt.update(state='FAILED' if failed else 'CONFIRMED', confirmed=not failed,
            evidence_label='VERIFIED_FAIL' if failed else 'VERIFIED_PASS',
            observed_at=utc_now(), exit_code=2 if failed else 0, reason=reason)
        validate_record('control_receipt.v1', receipt, project_root=store.root)
        with store.conn:
            store.conn.execute('UPDATE control_requests SET receipt=? WHERE request_id=?',
                (canonical(receipt).decode(), self.request_id))

    def advance(self):
        from compertum.campaign_operation import _CampaignOperation
        c = self.controller
        with c.store._live():
            _need(c.coordinator.status()['research_state'] == 'RUNNING', 'RESEARCH_PAUSED')
            require_complete(c.runs, self.run_id)
            if not self.inner.advance():
                return False
            if self.inner.action == 'resume':
                self.inner.close()
                # Resume changes the saved state. A new proof must verify it.
                self.inner = _CampaignOperation(c, self.run_id, 'step', created_at=self.created_at)
                return False
            _need(c.active is not None and c.active[0] == self.run_id, 'START_EFFECT_UNVERIFIED')
            self._record(reason='FIRST_RESEARCH_UNIT_STARTED')
            return True

    def _pause_unstarted(self):
        c = self.controller
        state = c.runs._load(self.run_id)
        if state['state'] == 'READY':
            c.runs.control(self.run_id, str(uuid5(NAMESPACE_URL, self.request_id+'/pause')), 'pause')

    def fail(self, error):
        # A launch or receipt failure can leave a real supervised child. Do not
        # claim failure or replay the request when its effect is uncertain.
        if self.controller.active is not None:
            raise RuntimeRefused('START_EFFECT_UNCERTAIN') from error
        self.inner.fail(error)
        self._pause_unstarted()
        self._record(failed=True, reason=getattr(error, 'code', 'START_PREPARATION_FAILED'))

    def cancel(self, reason, terminal=False):
        self.inner.cancel(reason, terminal)
        self._pause_unstarted()
        self._record(failed=True, reason=reason)

    def close(self):
        self.inner.close()


def start(coordinator, decision, payload, *, controller):
    """Consume exact trusted approval before any dispatch; never retry it.

    This owner-facing API adds no transport capability. Its approval names the
    immutable registration request, which binds the plan, seal and prepared input.
    """
    from compertum.coordinator import utc_now
    from compertum.research import ResearchController
    from compertum.runtime.jobs import preflight_campaign

    store = coordinator.store
    require_live_owner(store.lease, 'coordinator')
    _need(isinstance(controller, ResearchController) and controller.coordinator is coordinator
        and controller.store is store, 'START_OWNER_MISMATCH')
    _need(type(payload) is dict and set(payload) == FIELDS and type(decision) is ProtocolDecision)
    for value in (decision.request_id, payload['registration_request_id'], payload['run_id']):
        uuid(value)
    digest(decision.subject_key)
    _need(payload['approval'] == 'START_FIRST_RESEARCH_UNIT'
        and type(decision.target_generation) is int and decision.target_generation == store.lease.generation)
    _need(decision.payload_hash == _fingerprint(store, decision.subject_key, decision.target_generation, payload))

    with store._live():
        binding = (decision.subject_key, decision.payload_hash, decision.target_generation, ACTION, canonical(payload).decode())
        old = store.conn.execute('SELECT subject,payload_hash,generation,action,payload FROM control_requests WHERE request_id=?',
            (decision.request_id,)).fetchone()
        if old is not None:
            _need(old[0] == decision.subject_key and old[3:5] == binding[3:5]
                and type(old[2]) is int and 0 < old[2] <= decision.target_generation
                and old[1] == _fingerprint(store, old[0], old[2], payload), 'START_REQUEST_CONFLICT')
            return _saved(store, decision.request_id)
        from .cycle_ownership import require_dispatch_owner
        require_dispatch_owner(controller)
        _need(store.get_state('review_start_run:'+payload['run_id']) is None, 'START_ALREADY_CONSUMED')
        _need(store.get_state('review_registration_run:'+payload['run_id']) == payload['registration_request_id'],
            'START_REGISTRATION_MISMATCH')
        require_complete(controller.runs, payload['run_id'])
        registration = _saved(store, payload['registration_request_id'])
        _need(registration['action'] == 'register_reviewed_campaign' and registration['confirmed'], 'REGISTRATION_INCOMPLETE')
        controller._require_recovery_clear()
        _need(not controller.busy, 'JOB_SLOT_BUSY')
        _need(coordinator.status()['research_state'] == 'RUNNING', 'RESEARCH_PAUSED')
        coordinator.require_health()
        state = controller.runs._load(payload['run_id'])
        _need(state.get('input_kind') == 'synthetic-campaign' and state['state'] == 'PAUSED'
            and not state['attempts'] and not state['outcomes'], 'START_FIRST_UNIT_REQUIRED')
        preflight_campaign(controller.storage.lease)
        controller.storage._capacity('records', 16*1024**2)
        _need(store.conn.execute('SELECT count(*) FROM control_requests').fetchone()[0] < 10000, 'CONTROL_LEDGER_FULL')
        _need(store.conn.execute('SELECT count(*) FROM baseline_controls WHERE run_id=?', (payload['run_id'],)).fetchone()[0] < 127,
            'CONTROL_BOUND')
        receipt = dict(schema_version='1', record_type='ControlReceipt', request_id=decision.request_id,
            action=ACTION, target=payload['run_id'], state='PENDING', evidence_label='UNVERIFIED', confirmed=False,
            generation=decision.target_generation, requested_at=utc_now(), observed_at=None, exit_code=None,
            reason='START_CONSUMED_NO_AUTOMATIC_RETRY', artifacts=registration['artifacts'])
        validate_record('control_receipt.v1', receipt, project_root=store.root)
        operation = _StartOperation(controller, payload['run_id'], decision.request_id)
        try:
            with store.conn:
                store.conn.execute('INSERT INTO control_requests VALUES(?,?,?,?,?,?,?)',
                    (decision.request_id, *binding, canonical(receipt).decode()))
                coordinator._state('review_start_run:'+payload['run_id'], decision.request_id)
        except BaseException:
            operation.close()
            raise
        controller.pending = operation
        if not controller.cooperative:
            while controller.pending is not None:
                controller._advance_pending(propagate=True)
        return _saved(store, decision.request_id)
