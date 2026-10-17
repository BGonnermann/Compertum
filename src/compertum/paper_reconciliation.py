"""Pure accounting calculations. Callers must qualify original evidence separately.

Matching arithmetic never supplies current ownership, fee coverage or authority.
"""
from decimal import Context, DecimalException, DivisionByZero, InvalidOperation
from decimal import Overflow, ROUND_HALF_EVEN, localcontext
from decimal import Inexact, Rounded
import re

from .attempt_records import is_native, record_key
from .data.encoding import canonical
from .domain import ContractError
from .paper_activity_records import _FILL, _token
from .paper_contracts import identifier, number, symbol
from .paper_responses import _order
from .runtime.errors import RuntimeRefused
from .runtime.paper_read_packet import _nanoseconds


def _need(condition):
    if not condition:
        raise RuntimeRefused('PAPER_RECONCILIATION_UNVERIFIED')


def _whole(value, *, positive=False):
    result = number(value, positive=positive)
    _need(result >= 0 and result == result.to_integral_value() and result <= 10**9)
    return int(result)


def _decimal_text(value):
    result = format(value, 'f')
    if '.' in result:
        result = result.rstrip('0').rstrip('.')
    return '0' if value == 0 else result


def calculate_reconciliation(*, project_id, account_alias, opening_cash,
                             current_cash, attempts, orders, positions, activities):
    """Compare invented or original values without authenticating their origin."""
    return _checked_calculation(project_id, account_alias, opening_cash, current_cash,
                                attempts, orders, positions, activities, require_cash_match=True)


def validate_fill_history(*, project_id, account_alias, opening_cash,
                          current_cash, attempts, orders, positions, activities):
    """Check fill ownership and quantities. An unexplained cash change stays unqualified."""
    value = _checked_calculation(project_id, account_alias, opening_cash, current_cash,
                                 attempts, orders, positions, activities, require_cash_match=False)
    return dict(value, record_type='PaperFillHistoryCalculation')


def _checked_calculation(project, alias, opening, cash, attempts, orders, positions,
                         activities, *, require_cash_match):
    try:
        # At most 64 price digits, 9 quantity digits and 3 summation digits,
        # plus at most 62 fractional digits. Refuse any unanticipated rounding.
        context = Context(prec=160, rounding=ROUND_HALF_EVEN, Emin=-999999,
                          Emax=999999, capitals=1, clamp=0, flags=[],
                          traps=[InvalidOperation, DivisionByZero, Overflow, Inexact, Rounded])
        with localcontext(context):
            return _calculate(project, alias, opening, cash, attempts, orders, positions,
                              activities, require_cash_match=require_cash_match)
    except (ContractError, DecimalException, KeyError, TypeError, ValueError,
            AttributeError, OverflowError, RecursionError):
        raise RuntimeRefused('PAPER_RECONCILIATION_UNVERIFIED') from None


def _calculate(project, alias, opening, observed_cash, attempts, orders, positions,
               activities, *, require_cash_match=True):
    _need(type(require_cash_match) is bool)
    _need(type(project) is str and re.fullmatch('[0-9a-f]{64}', project) is not None)
    _need(type(alias) is str and re.fullmatch('[A-Za-z0-9][A-Za-z0-9_-]{0,63}', alias) is not None)
    for rows, limit in ((attempts, 256), (orders, 200), (positions, 64), (activities, 200)):
        _need(type(rows) is tuple and len(rows) <= limit)
    _need(len(canonical([attempts, orders, positions, activities])) <= 1024**2)
    cash = number(opening)
    broker_cash = number(observed_cash)
    _need(cash >= 0 and broker_cash >= 0)
    known = {}
    attempted = {}
    cancellations = []
    keys = set()
    for record in attempts:
        _need(type(record) is dict and is_native(record.get('intent')))
        key = record_key(record)
        intent = record['intent']
        _need(key not in keys and intent['project_id'] == project and key[0] == alias)
        keys.add(key)
        request = intent['request']
        if request['operation'] == 'CANCEL_ORDER':
            cancellations.append((request['parameters']['order_id'], _nanoseconds(record['attempted_at'])))
        else:
            client = intent['client_order_id']
            _need(client not in known)
            known[client] = request['body']
            attempted[client] = _nanoseconds(record['attempted_at'])

    indexed = {}
    clients = set()
    symbol_assets = {}
    asset_symbols = {}
    def bind_asset(name, asset):
        symbol(name)
        identifier(asset)
        _need(symbol_assets.get(name, asset) == asset and asset_symbols.get(asset, name) == name)
        symbol_assets[name] = asset
        asset_symbols[asset] = name
    for row in orders:
        _need(type(row) is dict)
        oid = identifier(row['id'])
        _order(row, dict(operation='ORDER_BY_ID', parameters=dict(order_id=oid)))
        _need(row.get('asset_class') == 'us_equity' and row.get('order_class') in ('simple', ''))
        bind_asset(row['symbol'], row['asset_id'])
        _need(row.get('legs') in (None, []) and row['status'] not in ('replaced', 'pending_replace'))
        client = row['client_order_id']
        _need(oid not in indexed and client in known and client not in clients)
        _need(_nanoseconds(row['submitted_at']) >= attempted[client])
        body = known[client]
        _need(all(row[key] == body[key] for key in
                  ('symbol', 'qty', 'side', 'type', 'time_in_force', 'extended_hours')))
        _need(row['limit_price'] == body.get('limit_price'))
        indexed[oid] = row
        clients.add(client)
    _need(clients == set(known))
    for oid, at in cancellations:
        _need(oid in indexed and at >= _nanoseconds(indexed[oid]['submitted_at']))

    owned = {}
    totals = {oid: [0, number('0')] for oid in indexed}
    seen = set()
    previous_time = None
    for fill in activities:
        _need(type(fill) is dict and set(fill) == _FILL and fill['activity_type'] == 'FILL')
        event_id = _token(fill['id'])
        _need(event_id not in seen)
        seen.add(event_id)
        at = _nanoseconds(fill['transaction_time'])
        _need(previous_time is None or at >= previous_time)
        previous_time = at
        oid = identifier(fill['order_id'])
        _need(oid in indexed)
        row = indexed[oid]
        _need(at >= _nanoseconds(row['submitted_at']))
        _need(fill['symbol'] == row['symbol'] and fill['side'] == row['side'])
        quantity = _whole(fill['qty'], positive=True)
        cumulative = _whole(fill['cum_qty'], positive=True)
        remaining = _whole(fill['leaves_qty'])
        price = number(fill['price'], positive=True)
        if row['type'] == 'limit':
            limit = number(row['limit_price'], positive=True)
            _need(price <= limit if row['side'] == 'buy' else price >= limit)
        total = _whole(row['qty'], positive=True)
        prior, cost = totals[oid]
        _need(cumulative == prior + quantity and cumulative <= total)
        _need(remaining == total - cumulative)
        _need(fill['type'] == ('fill' if remaining == 0 else 'partial_fill'))
        amount = quantity * price
        totals[oid] = [cumulative, cost + amount]
        sign = 1 if row['side'] == 'buy' else -1
        name = symbol(row['symbol'])
        owned[name] = owned.get(name, 0) + sign * quantity
        cash -= sign * amount
        _need(owned[name] >= 0 and cash >= 0)

    remaining = {}
    for oid, row in indexed.items():
        filled, cost = totals[oid]
        _need(filled == _whole(row['filled_qty']))
        if filled:
            _need(cost == filled * number(row['filled_avg_price'], positive=True))
        else:
            _need(row['filled_avg_price'] is None and cost == 0)
        remaining[oid] = _whole(row['qty'], positive=True) - filled

    observed = {}
    assets = set()
    for row in positions:
        _need(type(row) is dict and row.get('asset_class') == 'us_equity' and row.get('side') == 'long')
        name = symbol(row['symbol'])
        asset = identifier(row['asset_id'])
        bind_asset(name, asset)
        _need(name not in observed and asset not in assets)
        quantity = _whole(row['qty'], positive=True)
        average = number(row['avg_entry_price'], positive=True)
        _need(number(row['cost_basis']) == quantity * average)
        observed[name] = quantity
        assets.add(asset)
    owned = {name: quantity for name, quantity in owned.items() if quantity}
    _need(owned == observed)
    cash_matches = abs(broker_cash - cash) <= number('0.01')
    if require_cash_match:
        _need(cash_matches)
    return dict(version=1, record_type='PaperReconciliationCalculation',
                scope='UNQUALIFIED_CALCULATION', status='BLOCKED', calculation_matches=cash_matches,
                expected_cash=_decimal_text(cash), cash_difference=_decimal_text(broker_cash-cash),
                owned_positions=owned, remaining_quantities=remaining,
                order_count=len(indexed), fill_count=len(activities),
                deficiencies=['ACTION_EVIDENCE_UNVERIFIED', 'CURRENT_BINDINGS_UNVERIFIED',
                              'FEE_LIABILITIES_UNVERIFIED', 'NATIVE_PROVENANCE_UNVERIFIED',
                              'POSITION_COST_RECONSTRUCTION_UNVERIFIED'],
                transport_authorized=False, financial_accepted=False, actual_flat=None)
