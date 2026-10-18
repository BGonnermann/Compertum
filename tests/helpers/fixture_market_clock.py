"""A market clock for local tests. Actual elapsed-time clocks stay unchanged."""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from importlib import import_module
from types import SimpleNamespace
import re
from threading import Lock
import time
from zoneinfo import ZoneInfo


class MarketClock:
    """Advance one fixed market start at the rate of the actual monotonic clock."""

    def __init__(self, record, *, plan_sha256, project_id, monotonic_ns=time.monotonic_ns):
        keys = {'kind', 'version', 'start_at', 'actual_anchor_monotonic_ns',
                'maximum_elapsed_seconds', 'plan_sha256', 'project_id'}
        try:
            valid = (
                type(record) is dict and set(record) == keys
                and record['kind'] == 'SIMULATED_MARKET_CLOCK'
                and type(record['version']) is int and record['version'] == 1
                and type(record['maximum_elapsed_seconds']) is int
                and record['maximum_elapsed_seconds'] == 120
                and type(record['actual_anchor_monotonic_ns']) is int
                and 0 < record['actual_anchor_monotonic_ns'] < 2**63
                and all(type(pin) is str and re.fullmatch('[0-9a-f]{64}', pin)
                        for pin in (plan_sha256, project_id))
                and record['plan_sha256'] == plan_sha256
                and record['project_id'] == project_id
                and type(record['start_at']) is str and record['start_at'].endswith('Z')
                and callable(monotonic_ns)
            )
            if not valid:
                raise ValueError
            start = datetime.fromisoformat(record['start_at'].replace('Z', '+00:00'))
            if start.utcoffset() != timedelta(0):
                raise ValueError
        except (ValueError, TypeError, KeyError, OverflowError):
            raise ValueError('TEST_MARKET_CLOCK_INVALID') from None
        self._start = start
        self._anchor = record['actual_anchor_monotonic_ns']
        self._last = self._anchor
        self._actual_ns = monotonic_ns
        self._lock = Lock()
        self.now()

    def now(self, tz=timezone.utc):
        with self._lock:
            observed = self._actual_ns()
            if type(observed) is not int or not self._last <= observed < self._anchor + 120 * 10**9:
                raise ValueError('TEST_MARKET_CLOCK_EXPIRED_OR_REVERSED')
            self._last = observed
            value = self._start + timedelta(microseconds=(observed - self._anchor) // 1000)
        return value.astimezone(tz)

    def timestamp(self):
        return self.now().timestamp()

    def stamp(self):
        return self.now().isoformat().replace('+00:00', 'Z')


def clock_for_plan(plan, record, *, plan_sha256, monotonic_ns=time.monotonic_ns):
    """Bind the simulated clock to its original project, plan, and market date."""
    try:
        spec = plan['market_clock']
        if not (
            plan['scope'] == 'CONTROLLED_LOCAL_REHEARSAL'
            and plan['clock_substituted'] is True
            and plan['queue_clock_substituted'] is False
            and plan['actual_timeout_clocks_substituted'] is False
            and type(spec) is dict and set(spec) == {'kind', 'version', 'start_at'}
            and spec['kind'] == 'SIMULATED_MARKET_CLOCK'
            and type(spec['version']) is int and spec['version'] == 1
            and record['start_at'] == spec['start_at']
        ):
            raise ValueError
        value = MarketClock(record, plan_sha256=plan_sha256, project_id=plan['project_id'],
                            monotonic_ns=monotonic_ns)
        if value.now(ZoneInfo('America/New_York')).date().isoformat() != plan['session_date']:
            raise ValueError
        return value
    except (KeyError, TypeError, ValueError):
        raise ValueError('TEST_MARKET_CLOCK_PLAN_INVALID') from None


@contextmanager
def owner_market_clock(clock):
    """Replace market timestamp functions inside a test execution process only."""
    if type(clock) is not MarketClock:
        raise ValueError('TEST_MARKET_CLOCK_INVALID')
    actual = SimpleNamespace(time=clock.timestamp, monotonic=time.monotonic,
                             monotonic_ns=time.monotonic_ns, sleep=time.sleep)
    replacements = [
        ('paper_read_owner', 'time', actual),
        ('paper_market_owner', 'time', actual),
        ('paper_market_collection', '_utc', clock.stamp),
        ('paper_market_fresh', '_utc', clock.stamp),
        ('_winhttp_get', '_utc_now', clock.now),
        ('paper_fixture_orders', '_utc_now', clock.now),
        ('fixture_source_binding', 'datetime', SimpleNamespace(now=clock.now)),
    ]
    # Load all targets before a replacement can affect another module's imports.
    targets = [(import_module('compertum.runtime.' + name), attribute, replacement)
               for name, attribute, replacement in replacements]
    previous = [(module, attribute, getattr(module, attribute))
                for module, attribute, replacement in targets]
    try:
        for module, attribute, replacement in targets:
            setattr(module, attribute, replacement)
        yield
    finally:
        for module, attribute, original in reversed(previous):
            setattr(module, attribute, original)
