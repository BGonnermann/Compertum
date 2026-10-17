"""Declared arithmetic from original activity fields. These examples grant no authority."""
from copy import deepcopy
from uuid import UUID
import json
import pytest

from compertum.runtime.errors import RuntimeRefused
from compertum.paper_fees import calculate_fees
from test_paper_fees import schedule, rule


def fill(index=1, **changes):
    value = dict(id=f'original::{index}', activity_type='FILL',
        order_id=str(UUID(int=200)), symbol='AAPL', side='buy', qty='1',
        cum_qty='1', leaves_qty='0', price='10', type='fill',
        transaction_time='2026-10-09T13:35:00.123456789Z')
    value.update(changes)
    return value


def batches(rows, **changes):
    from compertum.paper_fee_adapter import build_fee_batches
    values = dict(project_id='a'*64, account_identity_sha256='b'*64,
        account_alias='fixture', activities=tuple(rows), empty_at='2026-10-09T13:35:00Z')
    values.update(changes)
    return build_fee_batches(**values)


def test_incremental_partial_fills_use_qty_and_round_once_per_day():
    rows = [fill(1, leaves_qty='2', type='partial_fill'),
        fill(2, qty='2', cum_qty='3', transaction_time='2026-10-09T13:35:00.123456790Z')]
    values, mapping = batches(rows)
    assert len(values) == 1 and len(mapping) == 2
    executions = values[0].to_payload()['executions']
    assert [row['quantity'] for row in executions] == ['1', '2']
    assert len({row['execution_id'] for row in executions}) == 2
    assert {row['order_id'] for row in executions} == {rows[0]['order_id']}
    s = schedule([rule('CAT', charged_sides=['BUY', 'SELL'], basis='SHARES', rate='0.004')])
    result = json.loads(calculate_fees(values[0], (s,)).content)
    cat = next(row for row in result['components'] if row['component'] == 'CAT')
    assert cat['declared_fee'] == '0.02' and cat['groups'][0]['quantity'] == '3'
    assert result['actual_billed_fee'] is None and result['financial_accepted'] is False


@pytest.mark.parametrize('stamp,day', [
    ('2026-10-09T03:59:59.999999999Z', '2026-10-08'),
    ('2026-10-09T04:00:00.000000000Z', '2026-10-09'),
    ('2026-11-01T05:59:59.999999999Z', '2026-11-01'),
    ('2026-11-01T06:00:00.000000000Z', '2026-11-01'),
    ('2026-03-08T06:59:59.999999999Z', '2026-03-08'),
    ('2026-03-08T07:00:00.000000000Z', '2026-03-08'),
])
def test_original_time_keeps_nanoseconds_and_new_york_date(stamp, day):
    values, mapping = batches([fill(transaction_time=stamp)])
    assert values[0].to_payload()['execution_date'] == day
    assert values[0].to_payload()['executions'][0]['executed_at'] == stamp
    assert mapping[0]['original_time'] == stamp


def test_offset_time_is_converted_without_losing_original_text_or_nanoseconds():
    original = '2026-10-09T09:35:00.123456789-04:00'
    values, mapping = batches([fill(transaction_time=original)])
    assert values[0].to_payload()['executions'][0]['executed_at'] == '2026-10-09T13:35:00.123456789Z'
    assert mapping[0]['original_time'] == original


def test_identity_mapping_is_stable_across_recollections():
    rows = [fill()]
    first, mapping = batches(rows)
    again, repeated = batches(deepcopy(rows))
    assert first == again and mapping == repeated
    assert mapping[0]['original_activity_id'] == rows[0]['id']
    assert UUID(mapping[0]['execution_id']).version == 5
    assert mapping[0]['execution_id'] != rows[0]['id']


@pytest.mark.parametrize('change', [dict(project_id='c'*64), dict(account_identity_sha256='d'*64)])
def test_project_and_original_account_identity_separate_internal_ids(change):
    _, first = batches([fill()])
    _, second = batches([fill()], **change)
    assert first[0]['execution_id'] != second[0]['execution_id']


def test_equal_times_and_multiple_symbols_keep_distinct_original_executions():
    values, mapping = batches([fill(1), fill(2, symbol='MSFT', order_id=str(UUID(int=201)))])
    assert len(mapping) == 2 and len({row['execution_id'] for row in mapping}) == 2
    assert {row['symbol'] for row in values[0].to_payload()['executions']} == {'AAPL', 'MSFT'}


def test_repeated_original_activity_is_refused_across_days():
    with pytest.raises(RuntimeRefused):
        batches([fill(1), fill(1, transaction_time='2026-10-10T13:35:00.123456789Z')])


def test_internal_uuid_collision_refuses_without_dropping_an_execution(monkeypatch):
    import compertum.paper_fee_adapter as module
    monkeypatch.setattr(module, 'uuid5', lambda *args: UUID(int=99))
    with pytest.raises(RuntimeRefused):
        batches([fill(1), fill(2)])


@pytest.mark.parametrize('field,value', [('qty', '0'), ('qty', '100000001'), ('price', '100000001'),
    ('symbol', 'UNSUPPORTED'), ('transaction_time', '1999-12-31T23:59:59Z')])
def test_unsupported_fee_values_refuse_without_rounding_or_relabelling(field, value):
    with pytest.raises(RuntimeRefused):
        batches([fill(**{field: value})])


@pytest.mark.parametrize('kind', ['per_day', 'days', 'total'])
def test_execution_and_day_bounds_refuse_instead_of_truncating(kind):
    rows = []
    count = 129 if kind == 'per_day' else 9 if kind == 'days' else 201
    for index in range(count):
        day = 1 if kind == 'per_day' else index+1 if kind == 'days' else index//26+1
        rows.append(fill(index+1, transaction_time=f'2026-10-{day:02}T13:35:00.{index:09}Z'))
    with pytest.raises(RuntimeRefused):
        batches(rows)


def test_eight_days_keep_all_executions_and_empty_input_has_no_actual_fee_claim():
    rows = [fill(i, transaction_time=f'2026-10-{i:02}T13:35:00.123456789Z') for i in range(1, 9)]
    values, mapping = batches(rows)
    assert len(values) == len(mapping) == 8
    empty, mapping = batches([])
    assert len(empty) == 1 and mapping == () and empty[0].to_payload()['executions'] == []
    result = json.loads(calculate_fees(empty[0], (schedule(),)).content)
    assert result['scope'] == 'DECLARED_SCENARIO_ONLY' and result['actual_billed_fee'] is None
