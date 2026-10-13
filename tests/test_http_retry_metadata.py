"""Bounded HTTP retry observations; no retry authority or network."""
from dataclasses import FrozenInstanceError
from datetime import datetime,timezone
import pytest
from compertum.runtime.errors import RuntimeRefused
from compertum.runtime.http_retry import normalize_retry_after

UTC=timezone.utc
AT=datetime(2026,10,9,13,20,0,123456,tzinfo=UTC)
MONO=7_000_000_001

def observe(value,at=AT,mono=MONO):return normalize_retry_after(value,observed_at=at,monotonic_ns=mono)

@pytest.mark.parametrize('value,seconds', [('0',0),('1',1),('004',4),('2147483647',2147483647),(' \t60\t ',60)])
def test_decimal_delay_exact_and_immutable(value,seconds):
 r=observe(value);assert r.kind=='DELAY_SECONDS' and r.delay_ns==seconds*10**9
 assert r.not_before_ns==MONO+r.delay_ns and r.observed_at==AT and r.observed_monotonic_ns==MONO
 assert repr(r)=='<RetryAfter redacted>'
 with pytest.raises(FrozenInstanceError):r.delay_ns=0

def test_absence_is_explicit():assert observe(None) is None

@pytest.mark.parametrize('value', ['', ' ', '-1','+1','1.0','1e2','1, 2','1\r\nBad: yes','\uff11\uff12','2147483648','0'*129, '0'*11, True, 1, b'1', 'secret-value',
 'Fri, 09 Oct 2026 13:20:10 UTC','fri, 09 Oct 2026 13:20:10 GMT',
 'Thu, 09 Oct 2026 13:20:10 GMT','Fri, 9 Oct 2026 13:20:10 GMT',
 'Fri, 09 Oct 2026 13:20:61 GMT','Fri, 09 Oct 2026 13:20:60 GMT',
 'Tue, 31 Feb 2026 13:20:10 GMT','Fri, 09 Oct 2026 25:20:10 GMT',
 'Fri, 09 Oct 2026 13:20:10 GMT extra','Fri, 09 Oct 9999 13:20:10 GMT'])
def test_invalid_is_static_refusal(value):
 with pytest.raises(RuntimeRefused,match='^HTTP_RETRY_AFTER_INVALID$'):observe(value)

@pytest.mark.parametrize('value',['Fri, 09 Oct 2026 13:20:10 GMT','Friday, 09-Oct-26 13:20:10 GMT','Fri Oct  9 13:20:10 2026'])
def test_three_rfc_date_forms_match_exact_delay(value):
 r=observe(value);assert r.kind=='HTTP_DATE' and r.delay_ns==9_876_544_000 and r.not_before_ns==MONO+9_876_544_000

@pytest.mark.parametrize('value',['Sun, 06 Nov 1994 08:49:37 GMT','Sunday, 06-Nov-94 08:49:37 GMT','Sun Nov  6 08:49:37 1994'])
def test_past_date_zero_not_negative(value):assert observe(value).delay_ns==0

@pytest.mark.parametrize('at,value,delay',[
 (datetime(2026,10,9,13,20,tzinfo=UTC),'Saturday, 09-Oct-76 13:20:01 GMT',0),
 (datetime(2060,1,1,tzinfo=UTC),'Wednesday, 01-Jan-20 00:00:00 GMT',0),
 (datetime(2090,1,1,tzinfo=UTC),'Wednesday, 01-Jan-10 00:00:00 GMT',631065600*10**9),
])
def test_two_digit_year_rolling_window(at,value,delay):assert observe(value,at).delay_ns==delay

def test_leap_second_normalizes_conservatively():
 at=datetime(2016,12,31,23,59,59,500000,tzinfo=UTC)
 r=observe('Sat, 31 Dec 2016 23:59:60 GMT',at);assert r.delay_ns==500_000_000

@pytest.mark.parametrize('at,mono',[(datetime(2026,1,1),1),(AT,-1),(AT,True),(AT,1.0),(AT,2**63),(None,1)])
def test_invalid_clock_refused_even_without_header(at,mono):
 with pytest.raises(RuntimeRefused,match='^HTTP_RETRY_CLOCK_INVALID$'):observe(None,at,mono)

def test_monotonic_target_overflow_refused():
 with pytest.raises(RuntimeRefused,match='^HTTP_RETRY_AFTER_INVALID$'):observe('1',mono=2**63-1)

def test_absolute_date_excessive_delay_refused():
 with pytest.raises(RuntimeRefused,match='^HTTP_RETRY_AFTER_INVALID$'):observe('Fri, 01 Jan 2100 00:00:00 GMT')
