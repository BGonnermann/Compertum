"""A fresh test process must restore copied clocks after the clock scope exits."""
import os
import subprocess
import sys


def test_fresh_order_module_restores_the_original_reply_clock():
    script = '''
import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd() / 'tests'))
from helpers.fixture_market_clock import MarketClock, owner_market_clock
from compertum.runtime import _winhttp_get
actual = _winhttp_get._utc_now
assert 'compertum.runtime.paper_fixture_orders' not in sys.modules
frame = dict(kind='SIMULATED_MARKET_CLOCK', version=1, start_at='2026-10-19T13:36:00Z',
             actual_anchor_monotonic_ns=1000000000, maximum_elapsed_seconds=120,
             plan_sha256='a'*64, project_id='b'*64)
clock = MarketClock(frame, plan_sha256='a'*64, project_id='b'*64,
                    monotonic_ns=lambda: 1000000000)
with owner_market_clock(clock):
    from compertum.runtime import paper_fixture_orders
    assert paper_fixture_orders._utc_now() == clock.now()
assert paper_fixture_orders._utc_now is actual
assert _winhttp_get._utc_now is actual
'''
    env = dict(os.environ, __PYVENV_LAUNCHER__=sys.executable)
    result = subprocess.run([sys.executable, '-B', '-c', script], executable=sys._base_executable,
                            env=env, timeout=5, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
