"""Bounded Retry-After observations. No scheduling or retry authority."""
from dataclasses import dataclass
from datetime import datetime,timedelta,timezone
import re
from .errors import RuntimeRefused

_MONTHS='Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec'.split()
_DAYS='Mon Tue Wed Thu Fri Sat Sun'.split()
_LONG='Monday Tuesday Wednesday Thursday Friday Saturday Sunday'.split()
_TIME=r'([0-9]{2}):([0-9]{2}):([0-9]{2})'
_MAX_WAIT_NS=(2**31-1)*10**9
_MAX_NS=2**63-1

@dataclass(frozen=True,repr=False)
class _RetryAfter:
    kind:str
    delay_ns:int
    observed_at:datetime
    observed_monotonic_ns:int
    not_before_ns:int
    def __repr__(self):return '<RetryAfter redacted>'


def _date(value,now):
    match=re.fullmatch(r'([A-Za-z]{3}), ([0-9]{2}) ([A-Za-z]{3}) ([0-9]{4}) '+_TIME+r' GMT',value)
    obsolete=False
    if match:
        day,number,month,year,hour,minute,second=match.groups()
    else:
        match=re.fullmatch(r'([A-Za-z]+), ([0-9]{2})-([A-Za-z]{3})-([0-9]{2}) '+_TIME+r' GMT',value)
        if match:
            day,number,month,year,hour,minute,second=match.groups();obsolete=True
        else:
            match=re.fullmatch(r'([A-Za-z]{3}) ([A-Za-z]{3}) ( [0-9]|[0-9]{2}) '+_TIME+r' ([0-9]{4})',value)
            if not match:raise ValueError
            day,month,number,hour,minute,second,year=match.groups()
    month=_MONTHS.index(month)+1
    year,number,hour,minute,second=map(int,(year,number,hour,minute,second))
    if obsolete:
        year=((now.year+50)//100)*100+year
        if (year,month,number,hour,minute,second,0)>(now.year+50,now.month,now.day,now.hour,now.minute,now.second,now.microsecond):year-=100
    leap=second==60
    if leap and (hour,minute)!=(23,59):raise ValueError
    result=datetime(year,month,number,hour,minute,59 if leap else second,tzinfo=timezone.utc)
    if (_LONG if obsolete else _DAYS).index(day)!=result.weekday():raise ValueError
    return result+timedelta(seconds=1) if leap else result


def normalize_retry_after(value,*,observed_at,monotonic_ns):
    """Normalize the single header at receipt; all arithmetic is integer based."""
    if (type(observed_at) is not datetime or observed_at.tzinfo is not timezone.utc
            or type(monotonic_ns) is not int or not 0<=monotonic_ns<=_MAX_NS):
        raise RuntimeRefused('HTTP_RETRY_CLOCK_INVALID')
    if value is None:return None
    try:
        if type(value) is not str or not 1<=len(value)<=128:raise ValueError
        text=value.strip(' \t')
        if re.fullmatch(r'[0-9]{1,10}',text):
            kind='DELAY_SECONDS';wait=int(text)*10**9
        else:
            kind='HTTP_DATE';delta=_date(text,observed_at)-observed_at
            wait=max(0,(delta.days*86400+delta.seconds)*10**9+delta.microseconds*1000)
        if not 0<=wait<=_MAX_WAIT_NS or monotonic_ns+wait>_MAX_NS:raise ValueError
        return _RetryAfter(kind,wait,observed_at,monotonic_ns,monotonic_ns+wait)
    except (ValueError,OverflowError,TypeError):
        raise RuntimeRefused('HTTP_RETRY_AFTER_INVALID') from None
