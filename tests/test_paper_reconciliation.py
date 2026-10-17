"""Pure invented accounting examples. These inputs grant no broker authority."""
import copy
from decimal import localcontext
from uuid import UUID

import pytest

from compertum.runtime.errors import RuntimeRefused
from test_native_attempt_records import records, attempt
from test_paper_portfolio import order, position


def example(*, quantity='1', price='150', side='buy', filled='1', state='filled'):
    p, d = records()
    body = p['request']['body']
    body.update(qty=quantity, side=side)
    if side == 'sell':
        p['purpose'] = 'CLOSE_LONG'
    elif quantity != '1':
        p['purpose'] = 'STRATEGY'
    from compertum.native_attempt_records import sha
    p['request_sha256'] = sha(p['request'])
    d['intent_sha256'] = sha(p)
    row = order(qty=quantity, filled_qty=filled, filled_avg_price=price if filled != '0' else None,
                status=state, side=side, client_order_id=p['client_order_id'],
                submitted_at='2023-11-24T14:35:00.1Z')
    fill = dict(activity_type='FILL', id='20231124::fill-1', order_id=row['id'],
                symbol='AAPL', side=side, qty=filled, cum_qty=filled,
                leaves_qty=str(int(quantity)-int(filled)), price=price,
                transaction_time='2023-11-24T14:35:01.123456789Z',
                type='fill' if quantity == filled else 'partial_fill')
    return p, d, row, fill


def inputs():
    return dict(project_id='a'*64, account_alias='fixture', opening_cash='1000',
                current_cash='1000', attempts=(), orders=(), positions=(), activities=())


def calculate(**changes):
    from compertum.paper_reconciliation import calculate_reconciliation
    values = inputs()
    values.update(changes)
    return calculate_reconciliation(**values)


def purchased():
    p, d, row, fill = example()
    return dict(attempts=(attempt(p, d),), orders=(row,), positions=(position(),),
                activities=(fill,), current_cash='850')


def test_empty_calculation_keeps_missing_coverage_and_authority_blocked():
    result = calculate()
    assert result['calculation_matches'] is True
    assert result['expected_cash'] == '1000' and result['owned_positions'] == {}
    assert result['status'] == 'BLOCKED' and result['actual_flat'] is None
    assert result['transport_authorized'] is result['financial_accepted'] is False
    assert {'FEE_LIABILITIES_UNVERIFIED', 'ACTION_EVIDENCE_UNVERIFIED',
            'NATIVE_PROVENANCE_UNVERIFIED', 'CURRENT_BINDINGS_UNVERIFIED'} <= set(result['deficiencies'])


def test_exact_buy_explains_cash_and_owned_holding_without_mutating_inputs():
    values = purchased()
    original = copy.deepcopy(values)
    result = calculate(**values)
    assert result['expected_cash'] == '850' and result['owned_positions'] == {'AAPL': 1}
    assert result['fill_count'] == 1 and result['order_count'] == 1
    assert result['remaining_quantities'] == {values['orders'][0]['id']: 0}
    assert values == original


def test_partial_fill_cancellation_keeps_remaining_quantity_and_owned_holding():
    p, d, row, fill = example(quantity='2', state='canceled')
    c, decision = records(operation='CANCEL_ORDER')
    c['request']['parameters']['order_id'] = row['id']
    c['request']['target'] = '/v2/orders/'+row['id']
    from compertum.native_attempt_records import sha
    c['request_sha256'] = sha(c['request']); decision['intent_sha256'] = sha(c)
    cancel=attempt(c,decision);cancel['attempted_at']='2023-11-24T14:35:00.2Z'
    result = calculate(attempts=(attempt(p, d), cancel), orders=(row,), positions=(position(),),
                       activities=(fill,), current_cash='850')
    assert result['remaining_quantities'] == {row['id']: 1}
    assert result['owned_positions'] == {'AAPL': 1}


def test_open_unfilled_order_is_owned_without_a_fill_or_cash_change():
    p, d, row, _ = example(filled='0', state='new')
    result = calculate(attempts=(attempt(p, d),), orders=(row,))
    assert result['owned_positions'] == {} and result['remaining_quantities'] == {row['id']: 1}


def test_buy_then_sell_explains_empty_holdings_and_exact_cash():
    p, d, buy, first = example()
    s, decision, sell, last = example(side='sell', price='151')
    sell['id'] = str(UUID(int=102)); last.update(order_id=sell['id'], id='20231124::fill-2',
        transaction_time='2023-11-24T14:35:01.123456790Z')
    result = calculate(attempts=(attempt(p, d), attempt(s, decision)), orders=(buy, sell),
                       activities=(first, last), current_cash='1001')
    assert result['expected_cash'] == '1001' and result['owned_positions'] == {}


@pytest.mark.parametrize('difference', ['0.01', '-0.01'])
def test_existing_one_cent_cash_tolerance_is_explicit(difference):
    from decimal import Decimal
    result = calculate(current_cash=str(Decimal('1000')+Decimal(difference)))
    assert result['cash_difference'] == difference


def test_caller_decimal_context_cannot_change_arithmetic():
    from decimal import Inexact, Rounded, ROUND_UP
    p, d, row, fill = example(price='150.01')
    with localcontext() as ctx:
        ctx.prec = 2
        ctx.rounding = ROUND_UP; ctx.Emax = 2; ctx.Emin = -2
        ctx.traps[Inexact] = True; ctx.traps[Rounded] = True
        result = calculate(attempts=(attempt(p,d),), orders=(row,), activities=(fill,),
                           positions=(position(avg_entry_price='150.01',cost_basis='150.01'),), current_cash='849.99')
    assert result['expected_cash'] == '849.99'


@pytest.mark.parametrize('fault', [
    'missing_attempt', 'missing_order', 'missing_fill', 'duplicate_attempt',
    'duplicate_order', 'duplicate_activity', 'foreign_client', 'foreign_broker',
    'changed_symbol', 'changed_side', 'changed_qty', 'changed_price',
    'overfill', 'changed_cumulative', 'changed_remaining', 'wrong_position',
    'foreign_position', 'foreign_activity', 'fractional_fill', 'negative_cash',
    'cash_difference', 'wrong_project', 'wrong_alias', 'fake_attempt',
    'malformed_fill_id', 'fill_extra_field', 'fractional_position',
    'replaced_order', 'unexplained_sell',
])
def test_incomplete_or_conflicting_evidence_refuses(fault):
    values = purchased()
    p = values['attempts'][0]['intent']; row = values['orders'][0]; fill = values['activities'][0]
    if fault == 'missing_attempt': values['attempts'] = ()
    elif fault == 'missing_order': values['orders'] = ()
    elif fault == 'missing_fill': values['activities'] = ()
    elif fault == 'duplicate_attempt': values['attempts'] *= 2
    elif fault == 'duplicate_order': values['orders'] *= 2
    elif fault == 'duplicate_activity': values['activities'] *= 2
    elif fault == 'foreign_client': row['client_order_id'] = 'cmp-foreign'
    elif fault == 'foreign_broker': fill['order_id'] = str(UUID(int=99))
    elif fault == 'changed_symbol': fill['symbol'] = 'MSFT'
    elif fault == 'changed_side': fill['side'] = 'sell'
    elif fault == 'changed_qty': row['qty'] = '2'
    elif fault == 'changed_price': row['filled_avg_price'] = '149'
    elif fault == 'overfill': fill['qty'] = '2'
    elif fault == 'changed_cumulative': fill['cum_qty'] = '2'
    elif fault == 'changed_remaining': fill['leaves_qty'] = '1'
    elif fault == 'wrong_position': values['positions'][0]['qty'] = '2'
    elif fault == 'foreign_position': values['positions'] += (dict(position(), symbol='MSFT'),)
    elif fault == 'foreign_activity': fill['activity_type'] = 'FEE'
    elif fault == 'fractional_fill': fill['qty'] = '0.5'
    elif fault == 'negative_cash': values['opening_cash'] = '100'
    elif fault == 'cash_difference': values['current_cash'] = '850.011'
    elif fault == 'wrong_project': values['project_id'] = 'b'*64
    elif fault == 'wrong_alias': values['account_alias'] = 'other'
    elif fault == 'fake_attempt': p['record_type'] = 'ExecutionIntent'
    elif fault == 'malformed_fill_id': fill['id'] = '../escape'
    elif fault == 'fill_extra_field': fill['owned'] = True
    elif fault == 'fractional_position': values['positions'][0]['qty'] = '0.5'
    elif fault == 'replaced_order': row['status'] = 'replaced'
    elif fault == 'unexplained_sell':
        p, d, row, fill = example(side='sell')
        values.update(attempts=(attempt(p,d),), orders=(row,), activities=(fill,), positions=(), current_cash='1150')
    with pytest.raises(RuntimeRefused):
        calculate(**values)


@pytest.mark.parametrize('field', ['attempts', 'orders', 'positions', 'activities'])
def test_collections_require_bounded_immutable_container(field):
    with pytest.raises(RuntimeRefused):
        calculate(**{field: []})


@pytest.mark.parametrize('cash', [True, 'NaN', '-1', '1e3', '9'*65])
def test_invalid_cash_refuses(cash):
    with pytest.raises(RuntimeRefused):
        calculate(opening_cash=cash)


@pytest.mark.parametrize('status', ['partially_filled','pending_cancel','canceled'])
def test_exact_two_fill_sequence_and_nanosecond_order(status):
    p,d,row,_=example(quantity='3',filled='2',price='150',state=status)
    _,_,_,a=example(quantity='3',filled='1',price='149')
    a.update(order_id=row['id'])
    b=dict(a,id='20231124::fill-2',price='151',cum_qty='2',leaves_qty='1',
           transaction_time='2023-11-24T14:35:01.123456790Z')
    values=dict(attempts=(attempt(p,d),),orders=(row,),activities=(a,b),
                positions=(position(qty='2',cost_basis='300'),),current_cash='700')
    assert calculate(**values)['remaining_quantities']=={row['id']:1}
    b['transaction_time']='2023-11-24T14:35:01.123456788Z'
    with pytest.raises(RuntimeRefused):calculate(**values)


@pytest.mark.parametrize('fault',['fill_before_attempt','fill_before_submission','submission_before_attempt'])
def test_causal_times_are_checked(fault):
    values=purchased();row=values['orders'][0];fill=values['activities'][0]
    if fault=='fill_before_attempt':fill['transaction_time']='2023-11-24T14:34:59Z'
    elif fault=='fill_before_submission':fill['transaction_time']='2023-11-24T14:35:00.09Z'
    else:row['submitted_at']='2023-11-24T14:34:59Z'
    with pytest.raises(RuntimeRefused):calculate(**values)


def test_cancel_of_unowned_order_refuses_even_when_balances_match():
    p,d=records(operation='CANCEL_ORDER')
    with pytest.raises(RuntimeRefused):calculate(attempts=(attempt(p,d),))


@pytest.mark.parametrize('intermediate',['cash','short'])
def test_intermediate_deficit_refuses_even_when_final_totals_match(intermediate):
    p,d,buy,first=example()
    s,decision,sell,last=example(side='sell',price='151')
    sell['id']=str(UUID(int=102));last.update(order_id=sell['id'],id='20231124::fill-2',
        transaction_time='2023-11-24T14:35:02Z')
    activities=(first,last)
    if intermediate=='short':
        last['transaction_time']='2023-11-24T14:35:01Z'
        first['transaction_time']='2023-11-24T14:35:02Z'
        activities=(last,first)
    with pytest.raises(RuntimeRefused):
        calculate(opening_cash='100',current_cash='101',attempts=(attempt(p,d),attempt(s,decision)),
                  orders=(buy,sell),activities=activities)


@pytest.mark.parametrize('field,limit',[('attempts',256),('orders',200),('positions',64),('activities',200)])
def test_count_limit_plus_one_refuses(field,limit):
    # Each element is a supported row shape. The excess count must refuse first.
    value=purchased()[field][0]
    with pytest.raises(RuntimeRefused):calculate(**{field:(value,)*(limit+1)})


def test_valid_maximum_activity_and_order_inventory():
    attempts=[];orders=[];fills=[]
    for index in range(200):
        p,d,row,fill=example()
        row['id']=str(UUID(int=1000+index));fill.update(order_id=row['id'],id=f'20231124::fill-{index}')
        attempts.append(attempt(p,d));orders.append(row);fills.append(fill)
    result=calculate(opening_cash='100000',current_cash='70000',attempts=tuple(attempts),
                     orders=tuple(orders),activities=tuple(fills),positions=(position(qty='200',cost_basis='30000'),))
    assert result['order_count']==result['fill_count']==200 and result['owned_positions']=={'AAPL':200}


def test_encoded_input_byte_limit_refuses():
    value=purchased();value['orders'][0]['untrusted_extra']='x'*(1024**2)
    with pytest.raises(RuntimeRefused):calculate(**value)


@pytest.mark.parametrize('fault',['position_asset','order_asset','shared_asset'])
def test_asset_identity_cannot_change_while_symbol_matches(fault):
    values=purchased()
    if fault=='position_asset':values['positions'][0]['asset_id']=str(UUID(int=999))
    elif fault=='order_asset':values['orders'][0]['asset_id']=str(UUID(int=999))
    else:
        p,d,row,_=example(filled='0',state='new')
        p['request']['body']['symbol']='MSFT';row.update(symbol='MSFT',id=str(UUID(int=999)))
        from compertum.native_attempt_records import sha
        p['request_sha256']=sha(p['request']);d['intent_sha256']=sha(p)
        values['attempts']+=(attempt(p,d),);values['orders']+=(row,)
    with pytest.raises(RuntimeRefused):calculate(**values)


def test_limit_buy_cannot_fill_above_its_submitted_limit():
    values=purchased();p=values['attempts'][0]['intent'];row=values['orders'][0]
    p['purpose']='FIXTURE_RESTING_BUY';p['request']['body'].update(type='limit',limit_price='150')
    row.update(type='limit',limit_price='150')
    from compertum.native_attempt_records import sha
    p['request_sha256']=sha(p['request']);values['attempts'][0]['decision']['intent_sha256']=sha(p)
    assert calculate(**values)['expected_cash']=='850'
    p['request']['body']['limit_price']='149';row['limit_price']='149'
    p['request_sha256']=sha(p['request']);values['attempts'][0]['decision']['intent_sha256']=sha(p)
    with pytest.raises(RuntimeRefused):calculate(**values)


def test_cancel_cannot_precede_the_order_submission():
    values=purchased();p,d=records(operation='CANCEL_ORDER');oid=values['orders'][0]['id']
    p['request']['parameters']['order_id']=oid;p['request']['target']='/v2/orders/'+oid
    from compertum.native_attempt_records import sha
    p['request_sha256']=sha(p['request']);d['intent_sha256']=sha(p)
    cancel=attempt(p,d);cancel['attempted_at']='2023-11-24T14:35:00.2Z'
    values['attempts']+=(cancel,)
    assert calculate(**values)['expected_cash']=='850'
    cancel['attempted_at']='2023-11-24T14:35:00Z'
    with pytest.raises(RuntimeRefused):calculate(**values)


@pytest.mark.parametrize('fault',['average','basis'])
def test_position_costs_cannot_contradict_each_other(fault):
    values=purchased();values['positions'][0]['avg_entry_price' if fault=='average' else 'cost_basis']='1'
    with pytest.raises(RuntimeRefused):calculate(**values)


def test_wide_decimal_intermediate_balance_keeps_tiny_exact_cash_change():
    attempts=[];orders=[];activities=[]
    specs=[('AAPL','buy','1000000000','1'),('AAPL','sell','1000000000','1'+'0'*63),
           ('MSFT','buy','1','0.'+'0'*61+'1'),('AAPL','buy','1000000000','1'+'0'*63),
           ('AAPL','sell','1000000000','1'),('MSFT','sell','1','0.'+'0'*61+'2')]
    from compertum.native_attempt_records import sha
    for index,(name,side,quantity,price) in enumerate(specs):
        p,d,row,fill=example(quantity=quantity,filled=quantity,side=side,price=price)
        p['request']['body']['symbol']=name;p['request_sha256']=sha(p['request']);d['intent_sha256']=sha(p)
        row.update(symbol=name,id=str(UUID(int=1000+index)),asset_id=str(UUID(int=2000 if name=='AAPL' else 2001)))
        fill.update(symbol=name,order_id=row['id'],id=f'20231124::fill-{index}',
                    transaction_time=f'2023-11-24T14:35:0{index+1}Z')
        attempts.append(attempt(p,d));orders.append(row);activities.append(fill)
    result=calculate(opening_cash='2000000000',current_cash='2000000000',attempts=tuple(attempts),
                     orders=tuple(orders),activities=tuple(activities))
    assert result['expected_cash']=='2000000000.'+'0'*61+'1'
    assert result['cash_difference']=='-0.'+'0'*61+'1'


def test_maximum_retained_attempts_preserve_cancel_targets():
    attempts=[];orders=[]
    from compertum.native_attempt_records import sha
    for index in range(200):
        p,d,row,_=example(filled='0',state='new');row['id']=str(UUID(int=1000+index))
        attempts.append(attempt(p,d));orders.append(row)
    for index in range(56):
        p,d=records(operation='CANCEL_ORDER');oid=orders[index]['id']
        p['request']['parameters']['order_id']=oid;p['request']['target']='/v2/orders/'+oid
        p['request_sha256']=sha(p['request']);d['intent_sha256']=sha(p)
        a=attempt(p,d);a['attempted_at']='2023-11-24T14:35:00.2Z';attempts.append(a)
    assert calculate(attempts=tuple(attempts),orders=tuple(orders))['order_count']==200


def test_maximum_distinct_positions_keep_asset_bindings():
    attempts=[];orders=[];activities=[];positions=[]
    from compertum.native_attempt_records import sha
    for index in range(64):
        name='S'+str(index);asset=str(UUID(int=2000+index));oid=str(UUID(int=1000+index))
        p,d,row,fill=example();p['request']['body']['symbol']=name
        p['request_sha256']=sha(p['request']);d['intent_sha256']=sha(p)
        row.update(symbol=name,asset_id=asset,id=oid)
        fill.update(symbol=name,order_id=oid,id=f'20231124::fill-{index}')
        positions.append(dict(position(),symbol=name,asset_id=asset))
        attempts.append(attempt(p,d));orders.append(row);activities.append(fill)
    result=calculate(opening_cash='100000',current_cash='90400',attempts=tuple(attempts),
                     orders=tuple(orders),activities=tuple(activities),positions=tuple(positions))
    assert len(result['owned_positions'])==64 and result['expected_cash']=='90400'
