"""Check an inert synthetic evidence sequence; never certify real operations."""
from dataclasses import dataclass, field
import hashlib
import json
from zoneinfo import ZoneInfo

from .data.encoding import canonical
from .domain import ContractError
from .paper_contracts import MAX_BYTES, number, require, timestamp
from .paper_fixture_plans import PaperFixtureProposal
from .paper_portfolio import PaperPortfolioBundle, TERMINAL
from .paper_responses import PaperResponse


def _sha(content):
    return hashlib.sha256(content).hexdigest()


def _need(ok, reason):
    if not ok:
        raise ContractError(reason)


@dataclass(frozen=True, slots=True)
class PaperFixtureStep:
    proposal: PaperFixtureProposal
    replies: tuple
    after: PaperPortfolioBundle
    content: bytes = field(init=False)

    def __post_init__(self):
        require(type(self.proposal) is PaperFixtureProposal and type(self.after) is PaperPortfolioBundle)
        require(type(self.replies) is tuple and len(self.replies) <= 12 and all(type(r) is PaperResponse for r in self.replies))
        object.__setattr__(self, 'content', canonical(dict(record_type='PaperFixtureStep', scope='PAPER_WIRE_FIXTURE',
                           proposal_sha256=self.proposal.sha256, replies_sha256=[_sha(r.content) for r in self.replies],
                           after_sha256=_sha(self.after.content), transport_authorized=False)))

    def to_payload(self):
        return json.loads(self.content)


_IDENTITY = ('id', 'client_order_id', 'symbol', 'qty', 'side', 'type', 'time_in_force',
             'extended_hours', 'limit_price')
_HISTORY_IDENTITY = _IDENTITY + ('asset_id', 'asset_class', 'submitted_at', 'order_class')


def _sequence(*, baseline, opening, holding_recovery, resting, resting_recovery, cancellation, closing):
    require(all(type(p) is PaperPortfolioBundle for p in (baseline, holding_recovery, resting_recovery)))
    require(all(type(s) is PaperFixtureStep for s in (opening, resting, cancellation, closing)))
    initial = baseline.to_payload()
    _need(initial['fixture_complete'] and not initial['positions'] and not initial['orders'], 'WALKTHROUGH_BASELINE_NOT_EMPTY')
    account = initial['account_context']
    day = timestamp(initial['as_of']).astimezone(ZoneInfo('America/New_York')).date()
    symbol = opening.proposal.symbol
    history, evidence, request_ids, client_ids, intent_ids = {}, [], set(), set(), set()
    previous = baseline

    def observe(bundle, *, new_orders=(), after_time=None):
        nonlocal history, previous
        p = bundle.to_payload()
        _need(p['fixture_complete'] and p['account_context'] == account, 'WALKTHROUGH_ACCOUNT_OR_COVERAGE')
        at = timestamp(p['as_of'])
        _need(at >= timestamp(previous.as_of) and at.astimezone(ZoneInfo('America/New_York')).date() == day,
              'WALKTHROUGH_TIME_ORDER')
        if after_time is not None:
            _need(all(timestamp(r.request.to_payload()['created_at']) >= after_time for r in (bundle.positions, *bundle.orders)),
                  'WALKTHROUGH_OBSERVATION_PRECEDES_EFFECT')
        rows = {r['id']: r for r in p['orders']}
        added = {r['id']: r for r in new_orders}
        _need(len(added) == len(new_orders) and not (set(added) & set(history)), 'WALKTHROUGH_DUPLICATE_ORDER')
        _need(set(rows) == set(history) | set(added), 'WALKTHROUGH_ORDER_COVERAGE_CHANGED')
        for order_id, old in list(history.items()) + list(added.items()):
            row = rows[order_id]
            keys = _HISTORY_IDENTITY if order_id in history else _IDENTITY
            _need(all(row[key] == old[key] for key in keys), 'WALKTHROUGH_ORDER_IDENTITY_CHANGED')
            if order_id in added:
                _need(timestamp(old['_created_at']) <= timestamp(row['submitted_at']) <= timestamp(old['_received_at']),
                      'WALKTHROUGH_SUBMISSION_TIME')
            _need(number(row['filled_qty']) >= number(old['filled_qty']), 'WALKTHROUGH_FILL_REVERSED')
            if number(row['filled_qty']) == number(old['filled_qty']):
                _need(row['filled_avg_price'] == old['filled_avg_price'], 'WALKTHROUGH_FILL_PRICE_CHANGED')
            if old['status'] in TERMINAL:
                _need(row['status'] == old['status'] and row['filled_qty'] == old['filled_qty'], 'WALKTHROUGH_TERMINAL_CHANGED')
            _need(row['symbol'] == symbol and row['status'] != 'replaced', 'WALKTHROUGH_UNEXPECTED_ACTIVITY')
        assets = {r['asset_id'] for r in rows.values()}
        _need((not rows or len(assets) == 1) and all(r['asset_id'] in assets for r in p['positions']),
              'WALKTHROUGH_ASSET_IDENTITY_CHANGED')
        quantity = sum(int(number(r['filled_qty'])) * (1 if r['side'] == 'buy' else -1) for r in rows.values())
        _need(quantity >= 0, 'WALKTHROUGH_SHORT_POSITION')
        expected = {symbol: quantity} if quantity else {}
        actual = {r['symbol']: int(number(r['qty'])) for r in p['positions']}
        _need(actual == expected, 'WALKTHROUGH_QUANTITY_NOT_RECONCILED')
        history, previous = rows, bundle
        evidence.append(dict(kind='PORTFOLIO', sha256=_sha(bundle.content), as_of=p['as_of']))
        return p

    observe(baseline)

    def step(value, kind):
        p = value.proposal.to_payload()
        _need(p['kind'] == kind and p['symbol'] == symbol and p['account_context'] == account, 'WALKTHROUGH_WRONG_STAGE')
        _need(value.proposal.portfolio.content == previous.content, 'WALKTHROUGH_PROPOSAL_SNAPSHOT_CHANGED')
        _need(timestamp(p['created_at']) >= timestamp(previous.as_of), 'WALKTHROUGH_TIME_ORDER')
        _need(p['intent_id'] not in intent_ids, 'WALKTHROUGH_DUPLICATE_INTENT')
        intent_ids.add(p['intent_id'])
        _need(p['residual_quantity'] in (None, 0) and p['requests'], 'WALKTHROUGH_CLOSE_RESIDUAL')
        _need(len(value.replies) == len(p['requests']), 'WALKTHROUGH_REPLY_COVERAGE')
        new_orders = []
        received = timestamp(p['created_at'])
        for draft, response in zip(p['requests'], value.replies):
            _need(response.request.content == canonical(draft), 'WALKTHROUGH_REPLY_NOT_BOUND')
            _need(draft['request_id'] not in request_ids, 'WALKTHROUGH_DUPLICATE_REQUEST')
            request_ids.add(draft['request_id'])
            r = response.to_payload()
            current = timestamp(r['received_at'])
            _need(received <= current <= timestamp(value.after.as_of), 'WALKTHROUGH_TIME_ORDER')
            if p['operation_deadline']:
                _need(current <= timestamp(p['operation_deadline']), 'WALKTHROUGH_CLOSE_DEADLINE')
            received = current
            if kind == 'CANCEL':
                _need(r['outcome'] == 'CANCEL_REQUEST_ACCEPTED_UNCONFIRMED', 'WALKTHROUGH_CANCEL_UNCONFIRMED')
            else:
                _need(r['outcome'] == 'SUCCESS_FIXTURE', 'WALKTHROUGH_SUBMIT_UNCONFIRMED')
                observed = r['observation']
                _need(observed['client_order_id'] not in client_ids, 'WALKTHROUGH_DUPLICATE_CLIENT_ID')
                client_ids.add(observed['client_order_id'])
                new_orders.append(dict(observed, _created_at=draft['created_at'], _received_at=r['received_at']))
        after = observe(value.after, new_orders=new_orders, after_time=received)
        evidence.append(dict(kind=kind, step_sha256=_sha(value.content), proposal_sha256=value.proposal.sha256))
        return p, after, new_orders

    open_p, _, bought = step(opening, 'OPEN_BUY')
    buy_id = bought[0]['id']
    _need(history[buy_id]['status'] == 'filled' and number(history[buy_id]['filled_qty']) == 1,
          'WALKTHROUGH_OPENING_NOT_FILLED')
    observe(holding_recovery, after_time=timestamp(previous.as_of))
    _, _, rested = step(resting, 'RESTING_BUY')
    rest_id = rested[0]['id']
    _need(history[rest_id]['status'] not in TERMINAL, 'WALKTHROUGH_RESTING_NOT_ACTIVE')
    observe(resting_recovery, after_time=timestamp(previous.as_of))
    _need(history[rest_id]['status'] not in TERMINAL, 'WALKTHROUGH_CANCEL_TARGET_NOT_ACTIVE')
    cancel_p, _, _ = step(cancellation, 'CANCEL')
    _need(cancel_p['cancel_target']['id'] == rest_id and history[rest_id]['status'] in TERMINAL,
          'WALKTHROUGH_CANCEL_NOT_TERMINAL')
    _, final, sold = step(closing, 'CLOSE_LONG')
    _need(all(history[r['id']]['status'] == 'filled' and number(history[r['id']]['filled_qty']) == number(r['qty']) for r in sold),
          'WALKTHROUGH_CLOSE_NOT_FILLED')
    _need(final['fixture_empty_positions_and_open_orders'] is True, 'WALKTHROUGH_FINAL_NOT_EMPTY')
    closed = sum(int(number(history[r['id']]['filled_qty'])) for r in sold)
    missing = ['PAPER_ACCOUNT_BINDING_AND_AUTHORIZED_READS', 'ACTUAL_ELIGIBILITY_QUOTES_TICKS_AND_ENTITLEMENT',
               'SCOPED_OPERATOR_APPROVAL_FOR_EACH_WRITE', 'EXCLUSIVE_OWNER_JOURNAL_HEALTH_AND_SUPERVISION',
               'RESEARCH_PAUSE_WITHIN_30_SECONDS_AND_MONITORING_CONTINUITY',
               'NATIVE_RESTART_IDENTITY_AND_NO_RESUBMISSION', 'ACTUAL_SERIAL_DISPATCH_AND_POST_COUNT',
               'ACTUAL_START_TIMING_WITHIN_AUTHORIZATION_AND_MARKET_WINDOW',
               'SYSTEM_OWNERSHIP_AND_CASH_FEE_RECONCILIATION', 'FINAL_HALTED_DISARMED_STATE', 'INDEPENDENT_REAL_WALKTHROUGH_AUDIT']
    return dict(version=1, record_type='PaperWalkthroughCheck', scope='PAPER_WIRE_FIXTURE',
                status='INTERNAL_FIXTURE_SEQUENCE_VALID', actual_m5_accepted=False, financial_accepted=False,
                transport_authorized=False, actual_flat=None, fixture_final_empty=True,
                account_context=account, symbol=symbol, opening_quantity=1, closed_quantity=closed,
                final_observed_at=final['as_of'], evidence=evidence, missing_actual_evidence=missing,
                historical_m4_evidence_not_reclassified=True)


@dataclass(frozen=True, slots=True)
class PaperWalkthroughCheck:
    baseline: PaperPortfolioBundle
    opening: PaperFixtureStep
    holding_recovery: PaperPortfolioBundle
    resting: PaperFixtureStep
    resting_recovery: PaperPortfolioBundle
    cancellation: PaperFixtureStep
    closing: PaperFixtureStep
    content: bytes = field(init=False)

    def __post_init__(self):
        fields = ('baseline', 'opening', 'holding_recovery', 'resting', 'resting_recovery', 'cancellation', 'closing')
        content = canonical(_sequence(**{key: getattr(self, key) for key in fields}))
        require(len(content) <= MAX_BYTES)
        object.__setattr__(self, 'content', content)

    def to_payload(self):
        return json.loads(self.content)

    @property
    def sha256(self):
        return _sha(self.content)


def check_fixture_walkthrough(*, baseline, opening, holding_recovery, resting, resting_recovery, cancellation, closing):
    return PaperWalkthroughCheck(baseline, opening, holding_recovery, resting, resting_recovery, cancellation, closing)

