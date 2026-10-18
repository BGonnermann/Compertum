"""A simulated market clock must leave actual timeout clocks unchanged."""
from datetime import datetime, timedelta, timezone
import time

import pytest


def record():
    return {
        'kind': 'SIMULATED_MARKET_CLOCK', 'version': 1,
        'start_at': '2026-10-19T13:36:00Z',
        'actual_anchor_monotonic_ns': 1_000_000_000,
        'maximum_elapsed_seconds': 120,
        'plan_sha256': 'a' * 64, 'project_id': 'b' * 64,
    }


def clock(sample):
    from helpers.fixture_market_clock import MarketClock
    return MarketClock(record(), plan_sha256='a' * 64, project_id='b' * 64,
                       monotonic_ns=lambda: sample[0])


def test_market_time_advances_at_actual_elapsed_rate():
    sample = [1_000_000_000]
    value = clock(sample)
    sample[0] += 3_125_000_000
    assert value.now() == datetime(2026, 10, 19, 13, 36, 3, 125000, timezone.utc)
    assert value.timestamp() == value.now().timestamp()
    assert value.stamp() == '2026-10-19T13:36:03.125000Z'


@pytest.mark.parametrize('elapsed', [-1, 120_000_000_000, 121_000_000_000])
def test_market_clock_refuses_outside_actual_job_lifetime(elapsed):
    sample = [1_000_000_000]
    value = clock(sample)
    sample[0] += elapsed
    with pytest.raises(ValueError, match='TEST_MARKET_CLOCK'):
        value.now()


def test_market_clock_refuses_reversed_actual_elapsed_time():
    sample = [2_000_000_000]
    value = clock(sample)
    value.now()
    sample[0] -= 1
    with pytest.raises(ValueError, match='TEST_MARKET_CLOCK'):
        value.now()


@pytest.mark.parametrize('field,value', [
    ('plan_sha256', 'c' * 64), ('project_id', 'c' * 64),
    ('maximum_elapsed_seconds', 121), ('actual_anchor_monotonic_ns', True),
    ('kind', 'PAPER_BROKER_CLOCK'), ('version', True),
    ('start_at', '2026-10-19T13:36:00'),
])
def test_market_clock_refuses_changed_binding_or_limits(field, value):
    from helpers.fixture_market_clock import MarketClock
    frame = record()
    frame[field] = value
    with pytest.raises(ValueError, match='TEST_MARKET_CLOCK'):
        MarketClock(frame, plan_sha256='a' * 64, project_id='b' * 64,
                    monotonic_ns=lambda: 1_000_000_000)


def test_market_clock_refuses_unknown_fields():
    from helpers.fixture_market_clock import MarketClock
    frame = dict(record(), actual_broker_authorized=True)
    with pytest.raises(ValueError, match='TEST_MARKET_CLOCK'):
        MarketClock(frame, plan_sha256='a' * 64, project_id='b' * 64,
                    monotonic_ns=lambda: 1_000_000_000)


def test_owner_scope_changes_only_market_clock_functions():
    from helpers.fixture_market_clock import owner_market_clock
    from compertum.runtime import execution_health, paper_read_owner, paper_market_owner
    from compertum.runtime import paper_market_collection, paper_market_fresh, service_budget, jobs
    actual_time = time.time
    actual_mono = time.monotonic
    actual_ns = time.monotonic_ns
    original_read_time = paper_read_owner.time
    original_utc = paper_market_collection._utc
    with owner_market_clock(clock([1_000_000_000])):
        assert paper_read_owner._now().startswith('2026-10-19T13:36:00')
        assert paper_market_owner._now().startswith('2026-10-19T13:36:00')
        assert paper_market_collection._utc() == paper_market_fresh._utc() == '2026-10-19T13:36:00Z'
        assert time.time is execution_health.time.time is actual_time
        assert time.monotonic is jobs.time.monotonic is actual_mono
        assert service_budget.time.monotonic_ns is actual_ns
        assert paper_read_owner.time.monotonic is actual_mono
        assert paper_read_owner.time.monotonic_ns is actual_ns
    assert paper_read_owner.time is original_read_time
    assert paper_market_collection._utc is original_utc


def test_owner_scope_restores_clocks_after_failure():
    from helpers.fixture_market_clock import owner_market_clock
    from compertum.runtime import paper_read_owner
    original = paper_read_owner.time
    with pytest.raises(RuntimeError, match='test failure'):
        with owner_market_clock(clock([1_000_000_000])):
            raise RuntimeError('test failure')
    assert paper_read_owner.time is original


def test_order_reply_timestamp_uses_the_same_clock_as_its_request():
    from helpers.fixture_market_clock import owner_market_clock
    from compertum.runtime import paper_fixture_orders
    sample = [1_000_000_000]
    value = clock(sample)
    request_at = value.now()
    with owner_market_clock(value):
        sample[0] += 3_000_000_000
        received_at = paper_fixture_orders._utc_now()
    assert (received_at - request_at).total_seconds() == 3


@pytest.mark.parametrize('hour,minute,accepted', [(9, 34, False), (9, 35, True), (10, 5, False)])
def test_simulated_clock_keeps_original_buying_window(hour, minute, accepted):
    from windows.test_paper_fixture_dispatch_control import window
    plan = dict(session_date='2026-10-19', phase='BUY')
    # Keep the original two-minute completion margin in every boundary check.
    now = datetime(2026, 10, 19, hour + 4, minute, tzinfo=timezone.utc)
    if accepted:
        window(plan, now=now)
    else:
        with pytest.raises(AssertionError, match='NATIVE_BUY_WINDOW_UNAVAILABLE'):
            window(plan, now=now)


def test_market_clock_does_not_extend_driver_deadline():
    from windows.test_paper_fixture_dispatch_control import Driver, WORK_SECONDS
    value = clock([1_000_000_000])
    before = time.monotonic()
    driver = Driver(None)
    value.now()
    assert before <= driver.started <= time.monotonic()
    assert driver.end == driver.started + WORK_SECONDS


def plan():
    return dict(scope='CONTROLLED_LOCAL_REHEARSAL', project_id='b' * 64,
                phase='BUY', session_date='2026-10-19', clock_substituted=True,
                queue_clock_substituted=False, actual_timeout_clocks_substituted=False,
                market_clock=dict(kind='SIMULATED_MARKET_CLOCK', version=1,
                                  start_at=record()['start_at']))


def test_clock_record_is_bound_to_the_exact_simulated_plan():
    from helpers.fixture_market_clock import clock_for_plan
    value = clock_for_plan(plan(), record(), plan_sha256='a' * 64,
                           monotonic_ns=lambda: 1_000_000_000)
    assert value.stamp() == '2026-10-19T13:36:00Z'


@pytest.mark.parametrize('field,value', [
    ('scope', 'ACTUAL_BROKER'), ('project_id', 'c' * 64),
    ('session_date', '2026-10-20'), ('clock_substituted', False),
    ('queue_clock_substituted', True), ('actual_timeout_clocks_substituted', True),
])
def test_clock_record_refuses_changed_test_scope(field, value):
    from helpers.fixture_market_clock import clock_for_plan
    changed = dict(plan(), **{field: value})
    with pytest.raises(ValueError, match='TEST_MARKET_CLOCK'):
        clock_for_plan(changed, record(), plan_sha256='a' * 64,
                       monotonic_ns=lambda: 1_000_000_000)


def test_clock_record_refuses_a_changed_market_start():
    from helpers.fixture_market_clock import clock_for_plan
    changed = plan()
    changed['market_clock']['start_at'] = '2026-10-19T14:00:00Z'
    with pytest.raises(ValueError, match='TEST_MARKET_CLOCK'):
        clock_for_plan(changed, record(), plan_sha256='a' * 64,
                       monotonic_ns=lambda: 1_000_000_000)


def test_clock_record_refuses_extra_clock_controls():
    from helpers.fixture_market_clock import clock_for_plan
    changed = plan()
    changed['market_clock']['skip_warmup'] = True
    with pytest.raises(ValueError, match='TEST_MARKET_CLOCK'):
        clock_for_plan(changed, record(), plan_sha256='a' * 64,
                       monotonic_ns=lambda: 1_000_000_000)


@pytest.mark.parametrize('start,accepted', [('13:22:00', True), ('13:25:00', False)])
def test_simulated_history_keeps_the_original_cutoff(start, accepted):
    from windows.test_paper_fixture_dispatch_control import window
    current = datetime.fromisoformat('2026-10-19T' + start + '+00:00')
    value = dict(session_date='2026-10-19', phase='HISTORY')
    if accepted:
        window(value, now=current)
    else:
        with pytest.raises(AssertionError, match='NATIVE_HISTORY_WINDOW_UNAVAILABLE'):
            window(value, now=current)
