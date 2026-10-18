"""Closed sessions still require a fresh, consistent original clock."""
from copy import deepcopy
import pytest
from compertum.runtime.paper_preflight import _calendar

def records():
 return [dict(operation='CALENDAR',observation=[]),dict(operation='CLOCK',received_at='2026-10-17T19:00:00Z',
  observation=dict(timestamp='2026-10-17T19:00:00Z',is_open=False,next_open='2026-10-19T13:30:00Z',next_close='2026-10-19T20:00:00Z'))]

def test_closed_day_checks_original_clock_without_requiring_a_session():
 agreement,reasons=_calendar(records(),'2026-10-17')
 assert agreement=='NO_PINNED_SESSION' and not any(x.startswith('CLOCK') for x in reasons)

@pytest.mark.parametrize('fault',['stale','open','next-open','next-close','missing'])
def test_closed_day_clock_faults_remain_visible(fault):
 rows=deepcopy(records());clock=rows[1]['observation']
 if fault=='stale':rows[1]['received_at']='2026-10-17T19:00:06Z'
 elif fault=='open':clock['is_open']=True
 elif fault=='next-open':clock['next_open']='2026-10-20T13:30:00Z'
 elif fault=='next-close':clock['next_close']='2026-10-20T20:00:00Z'
 else:rows.pop()
 _,reasons=_calendar(rows,'2026-10-17')
 assert any(x.startswith('CLOCK') for x in reasons)
