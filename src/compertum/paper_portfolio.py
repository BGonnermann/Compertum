"""Bounded portfolio-list fixtures; no ownership, ledger or real-flat claim."""
from dataclasses import dataclass, field
import hashlib
import json
from zoneinfo import ZoneInfo

from .data.encoding import canonical
from .domain import ContractError
from .paper_contracts import MAX_BYTES, identifier, number, require, session_date, symbol, timestamp, utc
from .paper_responses import PaperResponse, _order

TERMINAL = ('filled', 'canceled', 'expired', 'rejected', 'replaced')


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _text(value):
    return value if type(value) is str and len(value) <= 128 else None


def _duplicates(rows, key):
    values = [row[key] for row in rows if row.get(key) is not None]
    return len(values) != len(set(values))


def parse_portfolio_rows(body, request):
    """Keep an indexed representation even when an account row is unsupported."""
    require(type(body) is list)
    kind = request['operation']
    require(kind in ('POSITIONS', 'ORDERS'))
    rows, issues = [], []
    if kind == 'ORDERS' and len(body) > request['parameters']['limit']:
        issues.append('PAGE_LIMIT_EXCEEDED')
    for index, raw in enumerate(body):
        row = raw if type(raw) is dict else {}
        item = dict(index=index, row_sha256=_sha(canonical(raw)))
        names = ('asset_id', 'symbol', 'asset_class', 'qty', 'side', 'avg_entry_price', 'cost_basis') if kind == 'POSITIONS' else (
            'id', 'client_order_id', 'asset_id', 'symbol', 'asset_class', 'qty', 'filled_qty', 'filled_avg_price',
            'side', 'type', 'time_in_force', 'status', 'limit_price', 'submitted_at', 'order_class')
        item.update({key: _text(row.get(key)) for key in names})
        problems = []
        if type(raw) is not dict:
            problems.append('ROW_NOT_OBJECT')
        try:
            identifier(row.get('asset_id'))
            symbol(row.get('symbol'))
            require(row.get('asset_class') == 'us_equity')
        except ContractError:
            problems.append('UNSUPPORTED_ASSET')
        if kind == 'POSITIONS':
            try:
                quantity = number(row.get('qty'), positive=True)
                require(quantity == quantity.to_integral_value() and row.get('side') == 'long')
                number(row.get('avg_entry_price'), positive=True)
                number(row.get('cost_basis'))
            except ContractError:
                problems.append('UNSUPPORTED_POSITION')
        else:
            item['extended_hours'] = row.get('extended_hours') if type(row.get('extended_hours')) is bool else None
            try:
                identifier(row.get('id'))
                _order(row, {'operation': 'ORDER_BY_ID', 'parameters': {'order_id': row.get('id')}})
                timestamp(row.get('submitted_at'))
                require(row.get('order_class') in ('simple', '') and row.get('legs') in (None, []))
            except ContractError:
                problems.append('UNSUPPORTED_ORDER')
            if not (type(row.get('client_order_id')) is str and row['client_order_id'].startswith('cmp-')):
                problems.append('FOREIGN_CLIENT_ID')
        issues.extend(f'ROW_{index}_{problem}' for problem in problems)
        rows.append(item)
    keys = ('asset_id', 'symbol') if kind == 'POSITIONS' else ('id', 'client_order_id')
    for key in keys:
        if _duplicates(rows, key):
            issues.append('DUPLICATE_' + key.upper())
    return dict(kind=kind, rows=rows, deficiencies=issues)


def _bundle(*, account, positions, orders, clock, calendar, as_of):
    require(type(orders) is tuple and len(orders) <= 8)
    at = timestamp(as_of)
    issues, references = [], []
    anchor = None
    request_ids = set()
    responses = [('ACCOUNT', account), ('POSITIONS', positions)] + [('ORDERS', value) for value in orders] + [('CLOCK', clock), ('CALENDAR', calendar)]
    payloads = []
    for index, (operation, response) in enumerate(responses):
        if response is None:
            issues.append(operation + '_MISSING')
            payloads.append(None)
            continue
        require(type(response) is PaperResponse)
        p = response.to_payload()
        request = response.request.to_payload()
        identity = (p['origin'], p['account_id'], p['account_alias'])
        if anchor is None:
            anchor = identity
        elif identity != anchor:
            issues.append('ACCOUNT_CONTEXT_CHANGED')
        references.append(dict(index=index, operation=p['operation'], expected_operation=operation, request_id=p['request_id'],
                               request_sha256=p['request_sha256'], response_sha256=_sha(response.content),
                               raw_sha256=p['raw_sha256'], created_at=request['created_at'], received_at=p['received_at']))
        if p['operation'] != operation:
            issues.append('WRONG_OPERATION')
            payloads.append(None)
            continue
        if p['request_id'] in request_ids:
            issues.append('DUPLICATE_REQUEST_ID')
        request_ids.add(p['request_id'])
        received = timestamp(p['received_at'])
        started = timestamp(request['created_at'])
        age = (at - started).total_seconds()
        if not 0 <= age <= (5 if operation == 'CLOCK' else 30) or not started <= received <= at:
            issues.append(operation + '_STALE_OR_OUT_OF_ORDER')
        if p['outcome'] != 'SUCCESS_FIXTURE':
            issues.append(operation + '_UNCONFIRMED')
            payloads.append(None)
        else:
            payloads.append(p)
    account_p, positions_p = payloads[:2]
    pages = payloads[2:2 + len(orders)]
    clock_p, calendar_p = payloads[-2:]
    position_rows = positions_p['observation']['rows'] if positions_p else []
    if positions_p:
        issues.extend('POSITIONS_' + reason for reason in positions_p['observation']['deficiencies'])
    if not orders:
        issues.append('ORDERS_MISSING')
    order_rows = []
    last_id = previous_received = previous_submission = initial_limit = None
    previous_full = True
    for page_index, (response, page) in enumerate(zip(orders, pages)):
        if page is None:
            previous_full = False
            continue
        query = response.request.to_payload()['parameters']
        rows = page['observation']['rows']
        issues.extend('ORDERS_' + reason for reason in page['observation']['deficiencies'])
        if page_index == 0:
            initial_limit = query['limit']
            if 'after_order_id' in query:
                issues.append('ORDERS_INITIAL_CURSOR')
        else:
            if not previous_full or last_id is None or query.get('after_order_id') != last_id or query['limit'] != initial_limit:
                issues.append('ORDERS_CURSOR_CHAIN')
            if previous_received is None or timestamp(response.request.to_payload()['created_at']) < previous_received:
                issues.append('ORDERS_OUT_OF_ORDER')
        for row in rows:
            try:
                submitted = timestamp(row['submitted_at'])
                if submitted > timestamp(page['received_at']) or (previous_submission is not None and submitted < previous_submission):
                    issues.append('ORDERS_SUBMISSION_ORDER')
                previous_submission = submitted
            except ContractError:
                issues.append('ORDERS_SUBMISSION_TIME_UNVERIFIED')
            order_rows.append(dict(row, page=page_index))
        previous_full = len(rows) == query['limit']
        if rows:
            last_id = rows[-1]['id']
        previous_received = timestamp(page['received_at'])
        if page_index == len(orders) - 1 and len(rows) >= query['limit']:
            issues.append('ORDERS_TRUNCATED')
    for key in ('id', 'client_order_id'):
        if _duplicates(order_rows, key):
            issues.append('ORDERS_DUPLICATE_' + key.upper())
    if account_p:
        observed_account = account_p['observation']
        if observed_account['status'] != 'ACTIVE' or any(observed_account[key] for key in ('trading_blocked', 'account_blocked', 'trade_suspended_by_user')):
            issues.append('ACCOUNT_BLOCKED')
        if number(observed_account['cash']) < 0:
            issues.append('NEGATIVE_ACCOUNT_CASH')
    if clock_p and not 0 <= (at - timestamp(clock_p['observation']['timestamp'])).total_seconds() <= 5:
        issues.append('CLOCK_STALE_OR_AHEAD')
    if calendar_p:
        query = calendar.request.to_payload()['parameters']
        market_date = at.astimezone(ZoneInfo('America/New_York')).date()
        if not session_date(query['start']) <= market_date <= session_date(query['end']):
            issues.append('CALENDAR_RANGE_GAP')
    issues = sorted(set(issues))
    complete = not issues
    nonterminal = [row for row in order_rows if row['status'] not in TERMINAL]
    return dict(version=1, record_type='PaperPortfolioBundle', scope='PAPER_WIRE_FIXTURE',
                transport_authorized=False, financial_accepted=False, account_binding='UNVERIFIED',
                ownership='UNVERIFIED', fill_event_coverage='UNVERIFIED', economic_reconciliation='UNVERIFIED',
                pinned_calendar_agreement='UNVERIFIED', eligibility_and_quotes='UNVERIFIED', atomic_snapshot=False,
                actual_flat=None, as_of=utc(as_of), account_context=list(anchor) if anchor else None,
                fixture_complete=complete, deficiencies=issues,
                fixture_empty_positions_and_open_orders=(not position_rows and not nonterminal) if complete else None,
                positions=position_rows, orders=order_rows, order_cursor=last_id,
                cursor_kind='SUBMISSION_LIST_POSITION_ONLY', evidence=references,
                account_cash=account_p['observation']['cash'] if account_p else None,
                buying_power=account_p['observation']['buying_power'] if account_p else None)


@dataclass(frozen=True, slots=True)
class PaperPortfolioBundle:
    account: PaperResponse | None
    positions: PaperResponse | None
    orders: tuple
    clock: PaperResponse | None
    calendar: PaperResponse | None
    as_of: str
    content: bytes = field(init=False)

    def __post_init__(self):
        p = _bundle(account=self.account, positions=self.positions, orders=self.orders,
                    clock=self.clock, calendar=self.calendar, as_of=self.as_of)
        content = canonical(p)
        require(len(content) <= MAX_BYTES)
        object.__setattr__(self, 'content', content)

    def to_payload(self):
        return json.loads(self.content)


def build_portfolio_bundle(*, account, positions, orders: tuple, clock, calendar, as_of):
    return PaperPortfolioBundle(account, positions, orders, clock, calendar, as_of)
