"""Explicit owner control of one fixed synthetic research cycle."""
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json

from compertum.campaign_contract import UNITS
from compertum.domain import validate_record
from compertum.events import canonical, uuid
from compertum.evaluation_protocol import digest
from compertum.runtime.errors import RuntimeRefused
from compertum.runtime.ipc import ProtocolDecision
from compertum.runtime.owners import require_live_owner
from .cycle_record import CycleRecords, ACTIVE, _checked, _deadline, _need
from .registration import require_complete
from .cycle_ownership import require_control_clear

ACTION = 'control_research_cycle'
BINDINGS = {'run_id', 'registration_request_id', 'first_start_request_id',
    'prepared_sha256', 'plan_sha256', 'seal_id', 'schedule_sha256', 'maximum_bytes',
    'deadline', 'scorecard_task_id', 'aggregate_task_id'}


def fingerprint(store, subject, generation, payload):
    return hashlib.sha256(canonical(dict(subject=subject, action=ACTION, payload=payload,
        target_role='coordinator', target_generation=generation, project_id=store.lease.project_id))).hexdigest()


class ResearchCycleController:
    def __init__(self, coordinator, storage, *, research, auditor, reviews):
        from compertum.research import ResearchController
        from compertum.auditor import AuditorController
        from compertum.campaign_review import CampaignReviewController
        require_live_owner(storage.store.lease, 'coordinator')
        _need(coordinator.store is storage.store and all(
            isinstance(obj, cls) and obj.coordinator is coordinator and obj.storage is storage
            for obj, cls in ((research, ResearchController), (auditor, AuditorController),
                             (reviews, CampaignReviewController))), 'CYCLE_OWNER_MISMATCH')
        _need(getattr(coordinator, '_research_cycle', None) is None, 'CYCLE_ALREADY_ATTACHED')
        self.coordinator = coordinator
        self.storage = storage
        self.store = storage.store
        self.research, self.auditor, self.reviews = research, auditor, reviews
        self.records = CycleRecords(storage)
        self.cycle_id = self.store.get_state('active_research_cycle')
        self._dispatch_depth = 0
        self.records.recover()
        coordinator._research_cycle = self

    def status(self, cycle_id):
        return self.records.status(cycle_id)

    def _binding(self, value, subject):
        run = value['run_id']
        _need(self.store.get_state('review_registration_run:'+run) == value['registration_request_id']
            and self.store.get_state('review_start_run:'+run) == value['first_start_request_id'], 'CYCLE_APPROVAL_BINDING')
        rows = []
        for request, action in ((value['registration_request_id'], 'register_reviewed_campaign'),
                                (value['first_start_request_id'], 'start_reviewed_campaign')):
            row = self.store.conn.execute('SELECT subject,action,payload,receipt FROM control_requests WHERE request_id=?', (request,)).fetchone()
            _need(row is not None and row[:2] == (subject, action), 'CYCLE_OPERATOR_MISMATCH')
            receipt = validate_record('control_receipt.v1', json.loads(row[3]), project_root=self.store.root)
            _need(receipt['confirmed'] and receipt['action'] == action and receipt['request_id'] == request
                and receipt['target'] == run, 'CYCLE_FIRST_START_UNVERIFIED')
            rows.append(json.loads(row[2]))
        require_complete(self.research.runs, run)
        state = self.research.runs._load(run)
        _need(all(rows[0].get(k) == value[k] for k in ('run_id', 'prepared_sha256', 'plan_sha256', 'seal_id', 'maximum_bytes'))
            and rows[1] == dict(run_id=run, registration_request_id=value['registration_request_id'], approval='START_FIRST_RESEARCH_UNIT')
            and state['request_sha256'] == value['prepared_sha256']
            and state['maximum_bytes'] == value['maximum_bytes']
            and state.get('protocol_seal', {}).get('seal_id') == value['seal_id']
            and value['schedule_sha256'] == hashlib.sha256(canonical([asdict(u) for u in UNITS])).hexdigest(),
            'CYCLE_INPUTS_CHANGED')
        _need(state['state'] in {'PAUSED', 'READY', 'RUNNING', 'COMPLETED'}, 'CYCLE_RUN_UNAVAILABLE')
        return state

    def _ready(self):
        require_control_clear(self.store, self.cycle_id)
        _need(self.coordinator.status()['research_state'] == 'RUNNING', 'RESEARCH_PAUSED')
        self.coordinator.require_health()
        self.research._require_recovery_clear()

    def _pause_children(self):
        failure = None
        for controller in (self.research, self.auditor, self.reviews):
            try:
                controller.pause()
            except Exception as error:
                failure = failure or error
        if failure is not None:
            raise failure
        _need(not self.research.busy and self.auditor.active is None and self.reviews.active is None,
              'CYCLE_CHILD_CLEANUP_UNVERIFIED')

    def _receipt(self, request):
        row = self.store.conn.execute('SELECT receipt FROM control_requests WHERE request_id=?', (request,)).fetchone()
        _need(row is not None, 'CYCLE_REQUEST_MISSING')
        return validate_record('control_receipt.v1', json.loads(row[0]), project_root=self.store.root)

    def control(self, decision, payload):
        require_live_owner(self.store.lease, 'coordinator')
        _need(getattr(self.coordinator, '_research_cycle', None) is self, 'CYCLE_OWNER_MISMATCH')
        _need(type(payload) is dict and len(canonical(payload)) <= 8192 and type(decision) is ProtocolDecision,
              'CYCLE_APPROVAL_REQUIRED')
        uuid(decision.request_id)
        digest(decision.subject_key)
        _need(type(decision.target_generation) is int and decision.target_generation == self.store.lease.generation
            and decision.payload_hash == fingerprint(self.store, decision.subject_key, decision.target_generation, payload),
            'CYCLE_APPROVAL_REQUIRED')
        operation = payload.get('operation')
        required = {'operation', 'cycle_id'}
        if operation == 'approve': required |= BINDINGS | {'approval'}
        elif operation == 'resume': required |= {'expected_hash'}
        _need(operation in {'approve', 'status', 'pause', 'stop', 'resume'} and set(payload) == required, 'CYCLE_PAYLOAD_DENIED')
        uuid(payload['cycle_id'])
        with self.store._live():
            old = self.store.conn.execute('SELECT subject,payload_hash,generation,action,payload FROM control_requests WHERE request_id=?', (decision.request_id,)).fetchone()
            if old is not None:
                _need(old[0] == decision.subject_key and old[3] == ACTION and old[4] == canonical(payload).decode()
                    and 0 < old[2] <= decision.target_generation
                    and old[1] == fingerprint(self.store, old[0], old[2], payload), 'CYCLE_REQUEST_CONFLICT')
                return self._receipt(decision.request_id)
            if operation == 'approve':
                _need(payload['approval'] == 'RUN_FIXED_SYNTHETIC_CYCLE', 'CYCLE_APPROVAL_REQUIRED')
                now = datetime.now(timezone.utc)
                value = _checked(dict(schema_version='1', record_type='ResearchCycle',
                    cycle_id=payload['cycle_id'], approval_request_id=decision.request_id,
                    operator=decision.subject_key, generation=decision.target_generation,
                    **{k: payload[k] for k in BINDINGS}, state='APPROVED', sequence=0,
                    dispatch=None, reason='OWNER_APPROVED', updated_at=now.isoformat(),
                    financial_acceptance=False, execute_next=False))
                _deadline(value)
                _need((datetime.fromisoformat(value['deadline'].replace('Z', '+00:00'))-now).total_seconds() <= 1800,
                      'CYCLE_DEADLINE')
                _need(self.store.get_state('active_research_cycle') is None, 'CYCLE_DISPATCH_OWNED')
                self._binding(value, decision.subject_key)
                self._ready()
                _need(self.research.pending is None and (self.research.active is None or self.research.active[0] == value['run_id'])
                    and self.auditor.active is None and self.reviews.active is None, 'CYCLE_DISPATCH_BUSY')
            else:
                saved = self.status(payload['cycle_id'])
                value = saved['record']
                _need(value['operator'] == decision.subject_key, 'CYCLE_OPERATOR_MISMATCH')
                if operation == 'status': return saved
                claim = self.store.get_state('active_research_cycle')
                _need(claim == value['cycle_id'] or (claim is None and value['state'] == 'WAITING_FOR_ASSESSMENT'
                    and operation in {'pause', 'stop'}), 'CYCLE_DISPATCH_OWNED')
                if operation == 'resume':
                    _need(value['state'] == 'PAUSED' and payload['expected_hash'] == saved['sha256'], 'CYCLE_STATE_CHANGED')
                    _need(value['dispatch'] is None, 'CYCLE_DISPATCH_UNCERTAIN')
                    _deadline(value)
                    state = self._binding(value, decision.subject_key)
                    self._ready()
                else:
                    _need(value['state'] in ACTIVE | {'PAUSED', 'WAITING_FOR_ASSESSMENT'}, 'CYCLE_TERMINAL')
            _need(self.store.conn.execute('SELECT count(*) FROM control_requests').fetchone()[0] < 10000, 'CONTROL_LEDGER_FULL')
            self.storage._capacity('records', 3*1024**2)
            receipt = dict(schema_version='1', record_type='ControlReceipt', request_id=decision.request_id,
                action=ACTION, target=value['cycle_id'], state='PENDING', evidence_label='UNVERIFIED', confirmed=False,
                generation=decision.target_generation, requested_at=datetime.now(timezone.utc).isoformat(),
                observed_at=None, exit_code=None, reason='CYCLE_CONTROL_RECORDED', artifacts=[])
            validate_record('control_receipt.v1', receipt, project_root=self.store.root)
            with self.store.conn:
                self.store.conn.execute('INSERT INTO control_requests VALUES(?,?,?,?,?,?,?)',
                    (decision.request_id, decision.subject_key, decision.payload_hash, decision.target_generation,
                     ACTION, canonical(payload).decode(), canonical(receipt).decode()))
                if operation == 'approve':
                    self.coordinator._state('active_research_cycle', value['cycle_id'])
                    self.records.create(value)
                elif operation in {'pause', 'stop'}:
                    self.coordinator._state('research_cycle_control_pending:'+value['cycle_id'],
                        dict(request_id=decision.request_id, operation=operation))
            self.cycle_id = value['cycle_id']
            if operation in {'pause', 'stop'}:
                if claim == value['cycle_id']:
                    self._pause_children()
                if operation == 'stop' or value['state'] not in {'PAUSED', 'WAITING_FOR_ASSESSMENT'}:
                    self.records.transition(value['cycle_id'], saved['sha256'],
                        dict(state='STOPPED' if operation == 'stop' else 'PAUSED', reason='OWNER_'+operation.upper()))
            elif operation == 'resume':
                self.records.transition(value['cycle_id'], saved['sha256'],
                    dict(state='CHECKING_RESULTS' if state['state'] == 'COMPLETED' else 'RUNNING', reason='OWNER_RESUMED'))
            receipt.update(state='CONFIRMED', evidence_label='VERIFIED_PASS', confirmed=True,
                observed_at=datetime.now(timezone.utc).isoformat(), exit_code=0, reason='CYCLE_'+operation.upper()+'_RECORDED')
            validate_record('control_receipt.v1', receipt, project_root=self.store.root)
            with self.store.conn:
                self.store.conn.execute('UPDATE control_requests SET receipt=? WHERE request_id=?',
                    (canonical(receipt).decode(), decision.request_id))
                if operation in {'pause', 'stop'}:
                    self.coordinator._state('research_cycle_control_pending:'+value['cycle_id'], None)
            return receipt

    def close(self):
        if self.cycle_id is not None and self.store.get_state('active_research_cycle') == self.cycle_id:
            self._pause_children()
        if self.cycle_id is not None:
            saved = self.status(self.cycle_id)
            if saved['record']['state'] in ACTIVE:
                self.records.transition(self.cycle_id, saved['sha256'], dict(state='PAUSED', reason='CONTROLLER_CLOSED'))
        if getattr(self.coordinator, '_research_cycle', None) is self:
            self.coordinator._research_cycle = None
