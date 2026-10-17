"""Private original-record comparison. Missing fee and action coverage blocks use."""
from dataclasses import dataclass
import hashlib
import json
import sqlite3

from compertum.attempt_records import is_native
from compertum.data.encoding import canonical
from compertum.domain import ContractError
from compertum.fake_attempt_guard import verify_attempt_guard
from compertum.paper_reconciliation import calculate_reconciliation
from compertum.paper_position_costs import calculate_position_costs
from .errors import RuntimeRefused
from .owners import _MUTEX, _owner_scope
from .paper_account_context import _PaperAccountContext
from .paper_activity_evidence import open_activity_evidence
from .paper_market_lineage_evidence import _published
from .paper_opening import _original
from .paper_portfolio_context import _portfolio_context, _journal_snapshot
from .paper_credential_slot import load_paper_slot, _slot, _payload as slot_payload
from .paper_credentials import open_paper_credentials
from .paper_read_secrecy import _reject_reflections
from . import paper_account_binding as binding


_FACTORY = object()
_INVALID = (ContractError, ValueError, TypeError, KeyError, AttributeError,
            OverflowError, RecursionError, UnicodeError, sqlite3.Error)


def _need(value, code='PAPER_RECONCILIATION_CONTEXT_CHANGED'):
    if not value:
        raise RuntimeRefused(code)


def _sha(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def _capture(owner, context, portfolio, activity_id, *, position_costs=False):
    _need(type(position_costs) is bool)
    _need(type(context) is _PaperAccountContext and owner._account_context is context)
    _need(context._owner is owner and not context._closed)
    proof = portfolio._prepare_proof()
    activity = owner._activities
    _need(activity is not None and activity.o is owner)
    record = activity._read(activity_id)
    _need(record['state'] == 'PUBLISHED' and record['manifest'] is not None)
    preflight = owner.preflight(context._packet)
    account = context.diagnostic()
    _need(account['confirmation_status'] == 'CONFIRMED_CURRENT_CONTEXT')
    _need(record['subject'] == context._subject and record['packet_id'] == context._packet)
    alias = record['account_alias']
    _need(alias == account['account_alias'])
    opening, cash = _original(owner, alias)
    _need(opening['reference']['disposition'] == 'CLEAN_ZERO_HISTORY')
    journal = _journal_snapshot(owner)
    with _owner_scope(owner.lease) as guard:
        history = verify_attempt_guard(guard.project)
    _need(history['status'] == 'VERIFIED' and journal['classes']['unknown'] == 0)
    with open_activity_evidence(owner.lease, alias, activity_id, record['manifest']) as opened:
        snapshot = opened.snapshot()
    collection = snapshot['collection']
    seed = collection['bindings']
    _need(collection['state'] == 'COMPLETE' and collection['summary']['traversal_complete'])
    _need(collection['reason'] is None and collection['summary']['native_closed'])
    _need(set(collection['summary']['deficiencies']) <= {
        'OWNERSHIP_UNVERIFIED', 'ECONOMIC_COVERAGE_UNVERIFIED', 'FEE_LIABILITIES_UNVERIFIED',
        'ACTION_EVIDENCE_UNVERIFIED', 'NATIVE_PROVENANCE_UNVERIFIED'})
    _need(collection['binding'] == record['binding'] and collection['plan_sha256'] == record['plan_sha256'])
    _need(collection['summary'] == record['summary'] and collection['provenance'] in {'PAPER_TLS','LOOPBACK_FIXTURE'})
    _need(seed['account_context_sha256'] == context._binding and seed['opening_sha256'] == opening['sha256'])
    _need(seed['history_sha256'] == journal['sha256'] and seed['credential_sha256'] == preflight._credential_sha)
    _need(collection['expected_account_id'] == preflight._account_id)
    _need(collection['execution_generation'] == owner.lease.generation
          and collection['execution_instance'] == owner.lease.identity.process_instance_id)
    _need(seed['project_id'] == owner.lease.project_id and seed['account_alias'] == alias)

    rows = [json.loads(raw) for _, raw in preflight._records]
    observed_account = [row['observation'] for row in rows if row['operation'] == 'ACCOUNT']
    positions = [row['observation'] for row in rows if row['operation'] == 'POSITIONS']
    order_pages = [row['observation'] for row in rows if row['operation'] == 'ORDERS']
    _need(len(observed_account) == len(positions) == 1 and bool(order_pages))
    _need(not positions[0]['deficiencies'] and all(not page['deficiencies'] for page in order_pages))
    _need(account['order_coverage'] == 'OBSERVED_SHORT_TERMINAL_PAGE')
    native = tuple(row for row in history['records'] if is_native(row['intent'])
                   and row['intent']['account_alias'] == alias)
    fills = tuple(row for page in collection['pages'] for row in page['parsed']['rows'])
    calculate = calculate_position_costs if position_costs else calculate_reconciliation
    calculation = calculate(project_id=owner.lease.project_id, account_alias=alias,
        opening_cash=cash, current_cash=observed_account[0]['cash'], attempts=native,
        orders=tuple(row for page in order_pages for row in page['rows']),
        positions=tuple(positions[0]['rows']), activities=fills)
    stable = dict(context=context._binding, activity=record, opening=opening,
                  journal=journal['sha256'], history_sha256=history['sha256'],
                  preflight=preflight._content_sha, calculation=calculation,
                  position_costs=position_costs)
    pin = _sha(stable)

    def original():
        _need(owner._account_context is context and context._owner is owner and not context._closed)
        _need(owner._activities is activity and owner._preflight is preflight)
        _need(_journal_snapshot(owner)['sha256'] == journal['sha256'])
        _need(binding._state(owner, 'paper_opening:'+alias) == opening)
        with _owner_scope(owner.lease) as guard:
            _published(guard, record['manifest'])
        _need(activity._read(activity_id) == record)
        with _slot(owner.lease) as (guard, path):
            _need(guard.api.read_regular(path, maximum=16384) == expected_slot)
        _need(preflight._content_sha == stable['preflight'] and context._binding == stable['context'])

    result = dict(version=1, record_type='PaperReconciliationDiagnostic', status='BLOCKED',
        observation_status='MATCHING_LOOPBACK_OBSERVATIONS' if collection['provenance'] == 'LOOPBACK_FIXTURE'
            else 'MATCHING_ORIGINAL_OBSERVATIONS',
        order_count=calculation['order_count'], fill_count=calculation['fill_count'],
        position_count=len(calculation['owned_positions']),
        unverified_requirements=['ACTION_EVIDENCE_UNVERIFIED', 'FEE_LIABILITIES_UNVERIFIED',
            'POSITION_COST_RECONSTRUCTION_UNVERIFIED', 'RISK_UNVERIFIED', 'DURABLE_CONSUMPTION_UNVERIFIED'],
        transport_authorized=False, financial_accepted=False, actual_flat=None)
    if position_costs:
        complete = calculation['position_costs_complete']
        _need(type(complete) is bool)
        result['record_type'] = 'PaperPositionCostDiagnostic'
        result['position_cost_status'] = ('MATCHING_RECORDED_FILL_COSTS' if complete
                                          else 'UNSUPPORTED_FILL_COST_HISTORY')
        if complete:
            result['unverified_requirements'].remove('POSITION_COST_RECONSTRUCTION_UNVERIFIED')
        else:
            result['unverified_requirements'].append('UNSUPPORTED_FILL_COST_HISTORY')
    protected = load_paper_slot(owner.lease, alias)
    _need(hashlib.sha256(protected.ciphertext).hexdigest() == seed['credential_sha256'])
    expected_slot = slot_payload(protected)
    raw = canonical(result)
    _need(preflight._account_id.encode() not in raw)
    with open_paper_credentials(owner.lease, protected) as credentials:
        _reject_reflections(raw, tuple(credentials.headers().values()))
    proof._check()
    original()
    proof._finish()
    return proof, pin, canonical(calculation), result, original


@dataclass(frozen=True, slots=True, repr=False, init=False)
class _ReconciliationContext:
    _owner: object
    _db: object
    _context: object
    _portfolio: object
    _activity_id: str
    _binding: str
    _calculation: bytes
    _position_costs: bool
    _closed: bool

    def __init__(self, *, _factory=None, **fields):
        _need(_factory is _FACTORY, 'PAPER_RECONCILIATION_UNQUALIFIED')
        for key, value in fields.items():
            object.__setattr__(self, key, value)

    def __repr__(self):
        return '<PrivatePaperReconciliationContext redacted>'

    def __reduce_ex__(self, protocol):
        raise RuntimeRefused('PAPER_RECONCILIATION_SERIALIZATION_FORBIDDEN')

    def close(self):
        with _MUTEX:
            object.__setattr__(self, '_closed', True)
            self._portfolio.close()

    def _prepare_proof(self):
        with _MUTEX:
            _need(not self._closed, 'PAPER_RECONCILIATION_CONTEXT_UNAVAILABLE')
            try:
                pending = self._db.in_transaction
            except sqlite3.Error:
                self.close()
                raise RuntimeRefused('PAPER_RECONCILIATION_DATABASE_CLOSED') from None
            _need(not pending, 'PAPER_RECONCILIATION_TRANSACTION_OPEN')
            try:
                mode = self._position_costs
                _need(type(mode) is bool)
                owner = self._owner
                with _owner_scope(owner.lease), owner.store._live():
                    _need(owner.db is self._db and not owner._closed)
                    proof, pin, calculation, result, original = _capture(
                        owner, self._context, self._portfolio, self._activity_id, position_costs=mode)
                    _need(self._position_costs is mode)
                    _need(pin == self._binding and calculation == self._calculation)
                    check, finish, invalidate = proof._check, proof._finish, proof._invalidate

                    def identity():
                        _need(not self._closed and owner.db is self._db and not self._context._closed)
                        _need(owner._account_context is self._context and self._binding == pin
                              and self._calculation == calculation)
                        _need(self._position_costs is mode)

                    def checked():
                        identity()
                        try:
                            check()
                        except RuntimeRefused as error:
                            invalidate(error.code)
                            raise
                        original()
                        identity()

                    def finished():
                        identity()
                        try:
                            finish()
                        except RuntimeRefused as error:
                            invalidate(error.code)
                            raise
                        identity()

                    def invalidated(reason):
                        self.close()

                    proof._check = checked
                    proof._finish = finished
                    proof._invalidate = invalidated
                    proof._final_identity = identity
                    proof._content = canonical(result)
                    return proof
            except RuntimeRefused:
                self.close()
                raise
            except _INVALID:
                self.close()
                raise RuntimeRefused('PAPER_RECONCILIATION_INVALID') from None

    def diagnostic(self):
        return self._prepare_proof()._verify()


def _context(owner, *, subject, packet_id, activity_id, position_costs):
    with _MUTEX:
        _need(type(position_costs) is bool)
        db = owner.db
        try:
            pending = db.in_transaction
        except sqlite3.Error:
            raise RuntimeRefused('PAPER_RECONCILIATION_DATABASE_CLOSED') from None
        _need(not pending, 'PAPER_RECONCILIATION_TRANSACTION_OPEN')
        context = owner._account_context
        _need(type(context) is _PaperAccountContext and context._owner is owner and not context._closed)
        _need(context._subject == subject and context._packet == packet_id)
        portfolio = _portfolio_context(context)
        try:
            with _owner_scope(owner.lease), owner.store._live():
                _, pin, calculation, _, _ = _capture(
                    owner, context, portfolio, activity_id, position_costs=position_costs)
                return _ReconciliationContext(_factory=_FACTORY, _owner=owner, _db=db, _context=context,
                    _portfolio=portfolio, _activity_id=activity_id, _binding=pin,
                    _calculation=calculation, _position_costs=position_costs, _closed=False)
        except (RuntimeRefused, *_INVALID):
            portfolio.close()
            raise RuntimeRefused('PAPER_RECONCILIATION_INVALID') from None


def reconciliation_context(owner, *, subject, packet_id, activity_id):
    return _context(owner, subject=subject, packet_id=packet_id, activity_id=activity_id, position_costs=False)


def position_cost_context(owner, *, subject, packet_id, activity_id):
    return _context(owner, subject=subject, packet_id=packet_id, activity_id=activity_id, position_costs=True)
