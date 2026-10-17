"""Compare costs that do not depend on an unverified broker cost method."""
from decimal import Context, DecimalException, DivisionByZero, InvalidOperation
from decimal import Inexact, Overflow, ROUND_HALF_EVEN, Rounded, localcontext

from .paper_contracts import number
from .paper_reconciliation import calculate_reconciliation, _decimal_text, _need
from .runtime.errors import RuntimeRefused


def calculate_position_costs(*, project_id, account_alias, opening_cash,
                             current_cash, attempts, orders, positions, activities):
    """Validate original arithmetic, then compare supported recorded-fill costs.

    These calculations do not authenticate records or grant broker authority.
    Unsupported history remains unsupported after a later complete sale.
    """
    result = calculate_reconciliation(
        project_id=project_id, account_alias=account_alias, opening_cash=opening_cash,
        current_cash=current_cash, attempts=attempts, orders=orders,
        positions=positions, activities=activities)
    context = Context(prec=160, rounding=ROUND_HALF_EVEN, Emin=-999999,
                      Emax=999999, capitals=1, clamp=0, flags=[],
                      traps=[InvalidOperation, DivisionByZero, Overflow, Inexact, Rounded])
    try:
        with localcontext(context):
            return _compare(result, positions, activities)
    except DecimalException:
        raise RuntimeRefused('PAPER_POSITION_COST_UNVERIFIED') from None


def _compare(result, positions, activities):
    holdings, costs, prices = {}, {}, {}
    sold, unsupported = set(), set()
    for fill in activities:
        name = fill['symbol']
        quantity = int(number(fill['qty']))
        price = number(fill['price'])
        prior = holdings.get(name, 0)
        if fill['side'] == 'buy':
            earlier = prices.setdefault(name, set())
            if name in sold and any(previous != price for previous in earlier):
                unsupported.add(name)
            earlier.add(price)
            holdings[name] = prior + quantity
            if name not in unsupported:
                costs[name] = costs.get(name, number('0')) + quantity*price
        else:
            sold.add(name)
            if quantity < prior and len(prices[name]) > 1:
                unsupported.add(name)
            holdings[name] = prior - quantity
            if holdings[name] == 0:
                costs[name] = number('0')
            elif name not in unsupported:
                costs[name] -= quantity*next(iter(prices[name]))

    # A known zero current cost does not clear unsupported historical processing.
    expected = {name: _decimal_text(costs[name]) for name in sorted(holdings)
                if name not in unsupported or holdings[name] == 0}
    for row in positions:
        name = row['symbol']
        if name not in unsupported:
            _need(number(row['cost_basis']) == costs[name])
    result = dict(result, record_type='PaperPositionCostCalculation',
                  expected_position_costs=expected,
                  unsupported_symbols=sorted(unsupported),
                  position_costs_complete=not unsupported)
    if not unsupported:
        result['deficiencies'] = [value for value in result['deficiencies']
                                  if value != 'POSITION_COST_RECONSTRUCTION_UNVERIFIED']
    else:
        result['deficiencies'] = [*result['deficiencies'], 'UNSUPPORTED_FILL_COST_HISTORY']
    return result
