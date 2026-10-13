"""Pure engineering fixture proposals; approval envelopes are never granted."""
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal as D
import hashlib
import json
from uuid import UUID, uuid5
from zoneinfo import ZoneInfo

from .data.encoding import canonical
from .data.calendar import session_times
from .data.errors import DataError
from .domain import ContractError
from .execution_contracts import WATCHLIST
from .paper_contracts import (MAX_BYTES, build_request, identifier, number, require,
                              session_date, strict_json, symbol as valid_symbol, timestamp, utc)
from .paper_portfolio import PaperPortfolioBundle, TERMINAL, build_portfolio_bundle
from .simulation.policy import fixed_decimal, number as decimal_text

NY = ZoneInfo('America/New_York')


def _need(ok, reason):
    if not ok:
        raise ContractError(reason)


def _sha(content):
    return hashlib.sha256(content).hexdigest()


def _inputs(*, quotes, securities, feed, feature_session, created_at, supervision_at):
    require(type(feed) is str and feed in ('sip','iex'))
    require(type(quotes) is list and type(securities) is list and len(quotes) <= 64 and len(securities) <= 64)
    session_date(feature_session)
    created, supervision = timestamp(created_at), timestamp(supervision_at)
    require(supervision <= created)
    for rows in (quotes, securities):
        require(all(type(row) is dict for row in rows))
        seen = set()
        for row in rows:
            valid_symbol(row.get('symbol'))
            require(row['symbol'] not in seen)
            seen.add(row['symbol'])
    for q in quotes:
        require(set(q) == {'symbol', 'bid', 'ask', 'observed_at', 'feed'})
        require(q['feed'] == feed and number(q['ask'], positive=True) >= number(q['bid'], positive=True))
        require(timestamp(q['observed_at']) <= created)
    for s in securities:
        require(set(s) == {'symbol', 'feature_sessions', 'raw_close', 'liquidity_sessions', 'mean_dollar_volume',
                           'feature_session', 'tradable', 'actions_verified', 'mapping_verified'})
        for key in ('feature_sessions', 'liquidity_sessions'):
            require(type(s[key]) is int and 0 <= s[key] <= 100000)
        number(s['raw_close'], positive=True)
        volume = number(s['mean_dollar_volume'], positive=True)
        require(volume <= D('1000000000000000000') and volume.as_tuple().exponent >= -8)
        session_date(s['feature_session'])
        require(all(type(s[key]) is bool for key in ('tradable', 'actions_verified', 'mapping_verified')))
    return dict(version=1, record_type='PaperFixtureInputs', scope='PAPER_WIRE_FIXTURE',
                transport_authorized=False, financial_accepted=False, actual_evidence='UNVERIFIED',
                quotes=quotes, securities=securities, feed=feed, feature_session=feature_session,
                created_at=utc(created_at), supervision_at=utc(supervision_at),
                estimated_cost_fraction='0.001', adverse_buy_buffer='1.01', actual_fees='UNVERIFIED')


@dataclass(frozen=True, slots=True)
class PaperFixtureInputs:
    content: bytes

    def __post_init__(self):
        p = strict_json(self.content)
        fields = ('quotes', 'securities', 'feed', 'feature_session', 'created_at', 'supervision_at')
        require(type(p) is dict and all(key in p for key in fields))
        require(canonical(_inputs(**{key: p[key] for key in fields})) == self.content)

    def to_payload(self):
        return json.loads(self.content)

    @property
    def sha256(self):
        return _sha(self.content)


def build_fixture_inputs(*, quotes, securities, feed, feature_session, created_at, supervision_at):
    return PaperFixtureInputs(canonical(_inputs(quotes=quotes, securities=securities, feed=feed,
                                               feature_session=feature_session, created_at=created_at,
                                               supervision_at=supervision_at)))


def _amount(value):
    amount = number(value, positive=True)
    # Bound fixture arithmetic so the shared 28-digit context remains exact.
    require(amount <= D('1000000') and amount.as_tuple().exponent >= -8)
    return amount


def _quantity(value):
    quantity = number(value, positive=True)
    require(quantity <= 1000000 and quantity == quantity.to_integral_value())
    return int(quantity)


def _session(portfolio, at):
    date = at.astimezone(NY).date().isoformat()
    try:
        session = session_times(date)
    except DataError as exc:
        raise ContractError('FIXTURE_SESSION_UNAVAILABLE') from exc
    rows = portfolio.calendar.to_payload()['observation']
    expected = dict(date=date, open=session.open.astimezone(NY).strftime('%H:%M'),
                    close=session.close.astimezone(NY).strftime('%H:%M'))
    _need([row for row in rows if row['date'] == date] == [expected], 'FIXTURE_CALENDAR_MISMATCH')
    clock = portfolio.clock.to_payload()['observation']
    is_open = session.open <= at < session.close
    _need(clock['is_open'] == is_open, 'FIXTURE_CLOCK_MISMATCH')
    try:
        next_session = session_times(session.next_date)
    except DataError as exc:
        raise ContractError('FIXTURE_SESSION_UNAVAILABLE') from exc
    expected_open = session.open if at < session.open else next_session.open
    expected_close = session.close if at < session.close else next_session.close
    _need(timestamp(clock['next_open']) == expected_open and timestamp(clock['next_close']) == expected_close,
          'FIXTURE_CLOCK_MISMATCH')
    return session


@fixed_decimal
def _proposal(*, portfolio, inputs, kind, symbol, intent_id, now, limit_price, order_id):
    require(type(portfolio) is PaperPortfolioBundle and type(inputs) is PaperFixtureInputs)
    require(type(kind) is str and kind in ('OPEN_BUY', 'RESTING_BUY', 'CANCEL', 'CLOSE_LONG'))
    valid_symbol(symbol)
    identifier(intent_id)
    require(limit_price is None or kind == 'RESTING_BUY')
    require(order_id is None or kind == 'CANCEL')
    at = timestamp(now)
    fresh = build_portfolio_bundle(account=portfolio.account, positions=portfolio.positions,
                                  orders=portfolio.orders, clock=portfolio.clock,
                                  calendar=portfolio.calendar, as_of=now)
    p, facts = fresh.to_payload(), inputs.to_payload()
    _need(p['fixture_complete'], 'FIXTURE_PORTFOLIO_INCOMPLETE')
    _need(timestamp(facts['created_at']) <= at, 'FIXTURE_INPUTS_IN_FUTURE')
    supervision = timestamp(facts['supervision_at'])
    _need(0 <= (at - supervision).total_seconds() < 300, 'FIXTURE_SUPERVISION_EXPIRED')
    session = _session(fresh, at)
    expires = min(at + timedelta(seconds=60), supervision + timedelta(seconds=300))
    origin, account_id, alias = p['account_context']
    open_orders = [row for row in p['orders'] if row['status'] not in TERMINAL]
    quotes = {row['symbol']: row for row in facts['quotes']}
    securities = {row['symbol']: row for row in facts['securities']}

    def quote(name):
        _need(name in quotes, 'FIXTURE_QUOTE_MISSING')
        q = quotes[name]
        _need(0 <= (at - timestamp(q['observed_at'])).total_seconds() <= 30, 'FIXTURE_QUOTE_STALE')
        _amount(q['bid'])
        return _amount(q['ask'])

    def request(index, *, side=None, quantity=None, cancel=None):
        identity = dict(account_id=account_id, intent_id=intent_id, kind=kind, symbol=symbol, child=index)
        common = dict(origin=origin, account_alias=alias, account_id=account_id,
                      request_id=str(uuid5(UUID(intent_id), kind + ':' + str(index))), created_at=utc(now))
        if cancel is not None:
            return build_request(**common, operation='CANCEL_ORDER', parameters={'order_id': cancel}).to_payload()
        body = dict(symbol=symbol, qty=str(quantity), side=side, type='market', time_in_force='day',
                    extended_hours=False, client_order_id='cmp-' + _sha(canonical(identity))[:40])
        if kind == 'RESTING_BUY':
            body.update(type='limit', limit_price=decimal_text(_amount(limit_price)))
        return build_request(**common, operation='SUBMIT_ORDER', body=body).to_payload()

    requests, children, target = [], [], None
    planned = exposure = None
    residual, deadline = None, None
    status = 'DRAFT_REQUIRES_ACTUAL_EVIDENCE_AND_AUTHORIZATION'
    quote_used, cap = None, None
    if kind == 'CANCEL':
        identifier(order_id)
        matches = [row for row in open_orders if row['id'] == order_id and row['symbol'] == symbol]
        _need(len(matches) == 1, 'FIXTURE_CANCEL_TARGET_MISSING')
        target = matches[0]
        requests.append(request(0, cancel=order_id))
    else:
        _need(session.open <= at < session.close, 'FIXTURE_MARKET_CLOSED')
        expires = min(expires, session.close)
        ask = quote(symbol)
        quote_used = quotes[symbol]
        _need(symbol in securities, 'FIXTURE_SECURITY_MISSING')
        security = securities[symbol]
        _need(security['liquidity_sessions'] == 20 and security['feature_session'] == session.previous_date,
              'FIXTURE_LIQUIDITY_UNVERIFIED')
        cap = min(D('2000'), number(security['mean_dollar_volume'], positive=True) * D('.01'))
        conflicts = [row for row in open_orders if row['symbol'] == symbol]
        if kind in ('OPEN_BUY', 'RESTING_BUY'):
            start = datetime.combine(at.astimezone(NY).date(), time(9, 35), NY).astimezone(timezone.utc)
            end = datetime.combine(at.astimezone(NY).date(), time(10, 5), NY).astimezone(timezone.utc)
            _need(start <= at < end, 'FIXTURE_OPENING_WINDOW')
            expires = min(expires, end)
            _need(symbol in WATCHLIST and facts['feature_session'] == session.previous_date
                  and security['feature_sessions'] >= 252 and number(security['raw_close']) >= 5
                  and number(security['mean_dollar_volume']) >= 1000000
                  and all(security[key] for key in ('tradable', 'actions_verified', 'mapping_verified')),
                  'FIXTURE_INELIGIBLE')
            _need(not conflicts, 'FIXTURE_CONFLICTING_ORDER')
            if kind == 'OPEN_BUY':
                _need(not p['positions'] and not open_orders, 'FIXTURE_ACCOUNT_NOT_EMPTY')
                reference = ask
            else:
                _need(any(row['symbol'] == symbol for row in p['positions']), 'FIXTURE_HOLDING_REQUIRED')
                reference = _amount(limit_price)
                _need(reference <= ask * D('.8'), 'FIXTURE_LIMIT_DISCOUNT')
            planned = reference * D('1.001') * D('1.01')
            _need(planned <= cap, 'FIXTURE_INTENT_CAP')
            holdings = sum((_quantity(row['qty']) * quote(row['symbol']) for row in p['positions']), D(0))
            pending = D(0)
            for row in open_orders:
                if row['side'] == 'buy':
                    remaining = _quantity(row['qty']) - int(number(row['filled_qty']))
                    price = _amount(row['limit_price']) if row['type'] == 'limit' else quote(row['symbol'])
                    pending += remaining * price * D('1.001') * D('1.01')
            exposure = holdings + pending + planned
            _need(exposure <= 250, 'FIXTURE_EXPOSURE_CAP')
            _need(pending + planned <= number(p['account_cash']), 'FIXTURE_INSUFFICIENT_CASH')
            requests.append(request(0, side='buy', quantity=1))
        else:
            _need(not conflicts, 'FIXTURE_CONFLICTING_ORDER')
            holdings = [row for row in p['positions'] if row['symbol'] == symbol]
            _need(len(holdings) == 1, 'FIXTURE_LONG_POSITION_REQUIRED')
            residual = _quantity(holdings[0]['qty'])
            child_maximum = int(cap / (ask * D('1.01')))
            deadline = min(at + timedelta(minutes=10), session.close)
            for index in range(12):
                quantity = min(residual, child_maximum)
                if not quantity:
                    break
                child_notional = quantity * ask * D('1.01')
                children.append(dict(index=index, maximum_quantity=quantity,
                                     conservative_notional=decimal_text(child_notional),
                                     notional_cap=decimal_text(cap), requires_previous_terminal_reconciliation=True))
                requests.append(request(index, side='sell', quantity=quantity))
                residual -= quantity
            if residual:
                status = 'BLOCKED_RESIDUAL'
            planned = sum((D(child['conservative_notional']) for child in children), D(0))
    _need(expires > at, 'FIXTURE_PROPOSAL_EXPIRED')
    unverified = ('account_binding', 'system_ownership', 'fill_event_coverage', 'economic_reconciliation',
                  'customer_fees', 'pinned_calendar', 'feed_entitlement', 'eligibility',
                  'native_owner', 'durable_journal', 'execution_watchdog_health', 'supervision', 'price_tick')
    return dict(version=1, record_type='PaperFixtureProposal', scope='ENGINEERING_FIXTURE',
                transport_authorized=False, financial_accepted=False, actual_ownership='UNVERIFIED',
                confirmed_effect=False, actual_flat=None, actual_evidence={key: 'UNVERIFIED' for key in unverified},
                kind=kind, symbol=symbol, intent_id=intent_id, account_context=p['account_context'],
                created_at=utc(now), start_expires_at=expires.isoformat().replace('+00:00', 'Z'),
                operation_deadline=deadline.isoformat().replace('+00:00', 'Z') if deadline else None,
                portfolio_sha256=_sha(fresh.content), original_portfolio_sha256=_sha(portfolio.content),
                inputs_sha256=inputs.sha256, quote=quote_used, feed=facts['feed'],
                estimated_cost_fraction=facts['estimated_cost_fraction'], adverse_buy_buffer=facts['adverse_buy_buffer'],
                planned_notional=decimal_text(planned) if planned is not None else None,
                projected_exposure=decimal_text(exposure) if exposure is not None else None,
                per_intent_cap=decimal_text(cap) if cap is not None else None,
                proposal_status=status, requests=requests, children=children, residual_quantity=residual,
                cancel_target=target, recheck_all_gates_before_every_dispatch=True)


@dataclass(frozen=True, slots=True)
class PaperFixtureProposal:
    portfolio: PaperPortfolioBundle
    inputs: PaperFixtureInputs
    kind: str
    symbol: str
    intent_id: str
    now: str
    limit_price: str | None = None
    order_id: str | None = None
    content: bytes = field(init=False)

    def __post_init__(self):
        payload = _proposal(portfolio=self.portfolio, inputs=self.inputs, kind=self.kind, symbol=self.symbol,
                            intent_id=self.intent_id, now=self.now, limit_price=self.limit_price, order_id=self.order_id)
        content = canonical(payload)
        require(len(content) <= MAX_BYTES)
        object.__setattr__(self, 'content', content)

    @property
    def sha256(self):
        return _sha(self.content)

    def to_payload(self):
        return json.loads(self.content)

    def approval_request(self):
        return dict(version=1, record_type='PaperFixtureApprovalRequest', proposal_sha256=self.sha256,
                    kind=self.kind, intent_id=self.intent_id, status='NOT_GRANTED', transport_authorized=False,
                    scope='ENGINEERING_FIXTURE', financial_accepted=False,
                    start_expires_at=self.to_payload()['start_expires_at'])


def build_fixture_proposal(*, portfolio, inputs, kind, symbol, intent_id, now, limit_price=None, order_id=None):
    return PaperFixtureProposal(portfolio, inputs, kind, symbol, intent_id, now, limit_price, order_id)
