"""Hand-calculated position costs from invented local records."""
import copy
from decimal import Decimal, localcontext
from uuid import UUID

import pytest

from compertum.native_attempt_records import sha
from compertum.runtime.errors import RuntimeRefused
from test_native_attempt_records import attempt
from test_paper_portfolio import position
from test_paper_reconciliation import example, inputs


def history(rows, holdings=()):
    """Each (symbol, side, quantity, price) is a separate fully filled order."""
    values = inputs()
    attempts, orders, fills = [], [], []
    cash = Decimal('1000')
    for index, (name, side, quantity, price) in enumerate(rows, 1):
        p, decision, order, fill = example(quantity=str(quantity), price=str(price), side=side,
                                          filled=str(quantity))
        p['request']['body']['symbol'] = name
        p['request_sha256'] = sha(p['request'])
        decision['intent_sha256'] = sha(p)
        order.update(id=str(UUID(int=100+index)), symbol=name,
                     asset_id=str(UUID(int=200+ord(name[0]))))
        fill.update(order_id=order['id'], symbol=name, id=f'20231124::cost-{index}',
                    transaction_time=f'2023-11-24T14:35:{index:02d}Z')
        cash += (1 if side == 'sell' else -1)*Decimal(str(quantity))*Decimal(str(price))
        attempts.append(attempt(p, decision))
        orders.append(order)
        fills.append(fill)
    values.update(attempts=tuple(attempts), orders=tuple(orders), activities=tuple(fills),
                  positions=tuple(position(symbol=name, qty=str(quantity),
                      asset_id=str(UUID(int=200+ord(name[0]))),
                      avg_entry_price=str(average), cost_basis=str(cost))
                      for name, quantity, average, cost in holdings), current_cash=str(cash))
    return values


def calculate(values):
    from compertum.paper_position_costs import calculate_position_costs
    return calculate_position_costs(**values)


@pytest.mark.parametrize('rows,holdings,expected', [
    ([], [], {}),
    ([('AAPL','buy',2,'10')], [('AAPL',2,'10','20')], {'AAPL':'20'}),
    ([('AAPL','buy',2,'10'),('AAPL','buy',2,'12')],
     [('AAPL',4,'11','44')], {'AAPL':'44'}),
    ([('AAPL','buy',4,'10'),('AAPL','sell',1,'15')],
     [('AAPL',3,'10','30')], {'AAPL':'30'}),
    ([('AAPL','buy',4,'10'),('AAPL','sell',1,'15'),('AAPL','sell',1,'14')],
     [('AAPL',2,'10','20')], {'AAPL':'20'}),
    ([('AAPL','buy',2,'10'),('AAPL','sell',1,'15'),('AAPL','buy',2,'10.00')],
     [('AAPL',3,'10','30')], {'AAPL':'30'}),
    ([('AAPL','buy',2,'10'),('AAPL','sell',2,'15')], [], {'AAPL':'0'}),
    ([('AAPL','buy',2,'10'),('AAPL','buy',2,'12'),('AAPL','sell',4,'15')],
     [], {'AAPL':'0'}),
    ([('AAPL','buy',2,'10'),('AAPL','sell',2,'15'),('AAPL','buy',1,'10')],
     [('AAPL',1,'10','10')], {'AAPL':'10'}),
    ([('AAPL','buy',1,'0.01'),('MSFT','buy',2,'20.25')],
     [('AAPL',1,'0.01','0.01'),('MSFT',2,'20.25','40.50')], {'AAPL':'0.01','MSFT':'40.5'}),
])
def test_supported_costs_have_hand_calculated_values(rows, holdings, expected):
    values = history(rows, holdings)
    original = copy.deepcopy(values)
    result = calculate(values)
    assert result['expected_position_costs'] == expected
    assert result['unsupported_symbols'] == [] and result['position_costs_complete'] is True
    assert 'POSITION_COST_RECONSTRUCTION_UNVERIFIED' not in result['deficiencies']
    assert result['status'] == 'BLOCKED' and result['actual_flat'] is None
    assert result['transport_authorized'] is result['financial_accepted'] is False
    assert {'FEE_LIABILITIES_UNVERIFIED','ACTION_EVIDENCE_UNVERIFIED',
            'NATIVE_PROVENANCE_UNVERIFIED','CURRENT_BINDINGS_UNVERIFIED'} <= set(result['deficiencies'])
    assert values == original


@pytest.mark.parametrize('rows,holdings,expected', [
    ([('AAPL','buy',2,'10'),('AAPL','buy',2,'12'),('AAPL','sell',1,'15')],
     [('AAPL',3,'11','33')], {}),
    ([('AAPL','buy',2,'10'),('AAPL','sell',1,'15'),('AAPL','buy',2,'13')],
     [('AAPL',3,'12','36')], {}),
    ([('AAPL','buy',2,'10'),('AAPL','sell',2,'15'),('AAPL','buy',2,'13')],
     [('AAPL',2,'13','26')], {}),
    ([('AAPL','buy',2,'10'),('AAPL','buy',2,'12'),('AAPL','sell',1,'15'),
      ('AAPL','sell',3,'15')], [], {'AAPL':'0'}),
    ([('AAPL','buy',2,'10'),('AAPL','sell',1,'15'),('AAPL','buy',2,'13'),
      ('AAPL','sell',3,'15')], [], {'AAPL':'0'}),
    ([('AAPL','buy',2,'10'),('AAPL','buy',2,'12'),('AAPL','sell',1,'15'),
      ('AAPL','sell',3,'15'),('AAPL','buy',1,'10')], [('AAPL',1,'10','10')], {}),
    ([('AAPL','buy',2,'10'),('AAPL','sell',1,'15'),('AAPL','buy',2,'13'),
      ('AAPL','sell',3,'15'),('AAPL','buy',1,'14')], [('AAPL',1,'14','14')], {}),
    ([('AAPL','buy',2,'10'),('AAPL','sell',1,'15'),('AAPL','buy',2,'13'),
      ('MSFT','buy',1,'20')], [('AAPL',3,'12','36'),('MSFT',1,'20','20')], {'MSFT':'20'}),
])
def test_ambiguous_history_stays_unsupported_even_after_flattening(rows, holdings, expected):
    result = calculate(history(rows, holdings))
    assert result['unsupported_symbols'] == ['AAPL']
    assert result['expected_position_costs'] == expected
    assert result['position_costs_complete'] is False
    assert 'POSITION_COST_RECONSTRUCTION_UNVERIFIED' in result['deficiencies']
    assert 'UNSUPPORTED_FILL_COST_HISTORY' in result['deficiencies']
    assert result['transport_authorized'] is result['financial_accepted'] is False


@pytest.mark.parametrize('quantity,average,cost', [(2,'11','22'), (2,'10','21'), (1,'20','20')])
def test_conflicting_current_cost_average_or_quantity_refuses(quantity, average, cost):
    values = history([('AAPL','buy',2,'10')], [('AAPL',quantity,average,cost)])
    with pytest.raises(RuntimeRefused):
        calculate(values)


@pytest.mark.parametrize('flatten', [False, True])
def test_unsupported_symbol_cannot_hide_another_symbol_cost_conflict(flatten):
    rows = [('AAPL','buy',2,'10'),('AAPL','sell',1,'15'),('AAPL','buy',2,'13')]
    if flatten:
        rows += [('AAPL','sell',3,'15'),('AAPL','buy',3,'12')]
    values = history([*rows,('MSFT','buy',1,'20')],
                     [('AAPL',3,'12','36'),('MSFT',1,'21','21')])
    with pytest.raises(RuntimeRefused):
        calculate(values)


@pytest.mark.parametrize('fault', ['missing_fill','duplicate_fill','asset_change','malformed_price','wrong_cash'])
def test_original_reconciliation_refusals_still_apply(fault):
    values = history([('AAPL','buy',2,'10')], [('AAPL',2,'10','20')])
    if fault == 'missing_fill':
        values['activities'] = ()
    elif fault == 'duplicate_fill':
        values['activities'] *= 2
    elif fault == 'asset_change':
        values['positions'][0]['asset_id'] = str(UUID(int=999))
    elif fault == 'malformed_price':
        values['activities'][0]['price'] = 'NaN'
    elif fault == 'wrong_cash':
        values['current_cash'] = '999'
    with pytest.raises(RuntimeRefused):
        calculate(values)


def test_host_decimal_rounding_does_not_change_exact_cost():
    from decimal import Inexact, Rounded, ROUND_UP
    values = history([('AAPL','buy',3,'10.01'),('AAPL','sell',1,'12.34')],
                     [('AAPL',2,'10.01','20.02')])
    with localcontext() as context:
        context.prec = 2
        context.rounding = ROUND_UP
        context.traps[Inexact] = context.traps[Rounded] = True
        assert calculate(values)['expected_position_costs'] == {'AAPL':'20.02'}


def test_complete_sale_through_partial_fills_preserves_unsupported_history():
    values = history([('AAPL','buy',2,'10'),('AAPL','buy',2,'12'),('AAPL','sell',4,'15')])
    last = values['activities'][-1]
    partial = dict(last, id='20231124::cost-partial', qty='1',cum_qty='1',leaves_qty='3',
                   type='partial_fill',transaction_time='2023-11-24T14:35:02.5Z')
    last.update(qty='3')
    values['activities'] = (*values['activities'][:-1],partial,last)
    result = calculate(values)
    assert result['expected_position_costs'] == {'AAPL':'0'}
    assert result['unsupported_symbols'] == ['AAPL']


def test_overnight_dates_do_not_clear_the_unsupported_history():
    values = history([('AAPL','buy',2,'10'),('AAPL','sell',1,'15'),('AAPL','buy',2,'13')],
                     [('AAPL',3,'12','36')])
    values['activities'][-1]['transaction_time'] = '2023-11-27T14:35:03Z'
    assert calculate(values)['unsupported_symbols'] == ['AAPL']
