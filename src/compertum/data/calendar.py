"""Exchange sessions from the installed locked calendar, without network access."""
from dataclasses import dataclass
from datetime import date,datetime,time,timedelta,timezone
from functools import lru_cache
import re
from zoneinfo import ZoneInfo
import exchange_calendars as xc
from .errors import DataError

NY=ZoneInfo('America/New_York')

def session_date(value):
    if not isinstance(value,str):raise DataError('INVALID_DATE')
    try:
        d=date.fromisoformat(value)
        if d.isoformat()!=value or not 2000<=d.year<=2100:raise ValueError()
        return d
    except ValueError:raise DataError('INVALID_DATE') from None

def utc_time(value):
    if not isinstance(value,str) or not re.fullmatch(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,6})?(?:Z|\+00:00)',value):
        raise DataError('INVALID_TIME')
    try:return datetime.fromisoformat(value.replace('Z','+00:00'))
    except ValueError:raise DataError('INVALID_TIME') from None

@lru_cache(maxsize=4)
def _calendar(year):
    return xc.get_calendar('XNYS',start=f'{year-1}-01-01',end=f'{year+1}-12-31')

@dataclass(frozen=True)
class SessionTimes:
    open:datetime
    close:datetime
    decision:datetime
    entry:datetime
    close_reference:datetime
    next_date:str
    previous_date:str

def session_times(value):
    session_date(value)  # Reject unhashable caller values before the cache boundary.
    return _session_times(value)

@lru_cache(maxsize=2048)
def _session_times(value):
    d=session_date(value)
    try:
        cal=_calendar(d.year)
        if not cal.is_session(value):raise DataError('NOT_EXCHANGE_SESSION')
        opened=cal.session_open(value).to_pydatetime();closed=cal.session_close(value).to_pydatetime()
        decision=datetime.combine(d,time(9,25),NY).astimezone(timezone.utc)
        entry=datetime.combine(d,time(9,35),NY).astimezone(timezone.utc)
        return SessionTimes(opened,closed,decision,entry,closed-timedelta(minutes=1),str(cal.next_session(value).date()),str(cal.previous_session(value).date()))
    except (ValueError,OverflowError,KeyError):raise DataError('CALENDAR_UNAVAILABLE') from None
