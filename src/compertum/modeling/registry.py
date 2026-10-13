"""Predeclared candidates and feature order from BUILD_SPEC section 9."""
from datetime import datetime,time,timezone
from compertum.campaign_contract import FEATURES,Variant,VARIANTS,variant
from compertum.data.errors import DataError

def annual_cutoff(year):
    from compertum.data.calendar import NY,session_times,_calendar
    if type(year) is not int or year not in (2021,2022,2023):raise DataError('DEVELOPMENT_YEAR_REQUIRED')
    return _calendar_cutoff(year)


def _calendar_cutoff(year):
    from compertum.data.calendar import NY,session_times,_calendar
    if type(year) is not int or not 2001<=year<=2099:raise DataError('CALENDAR_UNAVAILABLE')
    try:
        date=str(_calendar(year).date_to_session(f'{year}-01-01',direction='next').date())
    except (ValueError,KeyError,OverflowError) as exc:raise DataError('CALENDAR_UNAVAILABLE') from exc
    session_times(date)
    return datetime.combine(datetime.fromisoformat(date).date(),time(7),NY).astimezone(timezone.utc)
