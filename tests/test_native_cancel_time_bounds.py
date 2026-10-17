"""A cancellation plan needs a valid clock, but no open exchange session."""
from datetime import datetime,timedelta,timezone
import pytest
from compertum.runtime.errors import RuntimeRefused
from compertum.runtime.paper_native_intent_terms import time_bounds,exact_terms

def values():
 at=datetime(2026,10,17,19,0,tzinfo=timezone.utc)
 terms=exact_terms('CANCEL',dict(symbol='MSFT',order_id='11111111-1111-4111-8111-111111111111'))
 return at,terms,dict(calendar_agreement='NO_SESSION',deficiencies=['CALENDAR_NO_SESSION'])

def test_cancel_plan_remains_available_outside_an_exchange_session():
 at,terms,diagnostic=values();end,operation=time_bounds('CANCEL',terms,at,diagnostic)
 assert end==at+timedelta(seconds=60) and operation is None

@pytest.mark.parametrize('reason',['CLOCK_MISSING','BROKER_CLOCK_MISMATCH'])
def test_cancel_plan_still_refuses_an_unverified_clock(reason):
 at,terms,diagnostic=values();diagnostic['deficiencies'].append(reason)
 with pytest.raises(RuntimeRefused):time_bounds('CANCEL',terms,at,diagnostic)

def test_buy_cannot_use_the_cancellation_session_rule():
 at,_,diagnostic=values();terms=exact_terms('FIXTURE_BUY',dict(fixture_id='local-finish',symbol='MSFT'))
 with pytest.raises(RuntimeRefused):time_bounds('FIXTURE_BUY',terms,at,diagnostic)
