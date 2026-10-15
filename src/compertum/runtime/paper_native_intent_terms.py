"""Exact proposed terms and calendar bounds; no ownership or risk approval."""
from datetime import datetime,time,timedelta,timezone
from zoneinfo import ZoneInfo
import re
from compertum.data.calendar import session_times
from compertum.data.errors import DataError
from compertum.paper_contracts import identifier,symbol,session_date
from compertum.paper_fixture_plans import _amount
from .errors import RuntimeRefused

PURPOSES=frozenset({'CANCEL','CLOSE_LONG','FIXTURE_BUY','FIXTURE_RESTING_BUY','STRATEGY'})
NY=ZoneInfo('America/New_York')


def need(value,code='PAPER_INTENT_TERMS_INVALID'):
    if not value:raise RuntimeRefused(code)


def _name(value):
    need(type(value) is str and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}',value) is not None)


def _quantity(value):
    need(type(value) is int and 1<=value<=1000000);return value


def exact_terms(purpose,terms,*,stored=False):
    need(type(purpose) is str and purpose in PURPOSES and type(terms) is dict)
    value=dict(terms);symbol(value.get('symbol'))
    if purpose=='CANCEL':
        need(set(value)=={'symbol','order_id'});identifier(value['order_id'])
    elif purpose.startswith('FIXTURE_'):
        if stored:
            need(type(value.get('quantity')) is int and value.pop('quantity')==1)
            need(value.pop('maximum_exposure',None)=='250')
        fields={'fixture_id','symbol'}|({'limit_price'} if purpose=='FIXTURE_RESTING_BUY' else set())
        need(set(value)==fields);_name(value['fixture_id'])
        if 'limit_price' in value:value['limit_price']=format(_amount(value['limit_price']).normalize(),'f')
        value.update(quantity=1,maximum_exposure='250')
    elif purpose=='CLOSE_LONG':
        need(set(value)=={'symbol','quantity','children'});_quantity(value['quantity'])
        children=value['children'];need(type(children) is list and 1<=len(children)<=12)
        result=[]
        for child in children:
            need(type(child) is dict and set(child)=={'maximum_quantity','notional_cap'})
            quantity=_quantity(child['maximum_quantity']);amount=_amount(child['notional_cap']);need(amount<=2000)
            result.append(dict(maximum_quantity=quantity,notional_cap=format(amount.normalize(),'f')))
        need(sum(c['maximum_quantity'] for c in result)==value['quantity']);value['children']=result
    else:
        if stored:
            need(value.pop('order_type',None)=='market' and value.pop('time_in_force',None)=='day')
            need(value.pop('extended_hours',None) is False)
        need(set(value)=={'candidate_id','candidate_version','protocol_sha256','symbol','side','quantity','rebalance_session'})
        _name(value['candidate_id']);_name(value['candidate_version']);_quantity(value['quantity'])
        need(type(value['protocol_sha256']) is str and re.fullmatch('[0-9a-f]{64}',value['protocol_sha256']) is not None)
        need(value['side'] in ('buy','sell'));session_date(value['rebalance_session'])
        value.update(order_type='market',time_in_force='day',extended_hours=False)
    return value


def time_bounds(purpose,terms,at,diagnostic):
    need(diagnostic['calendar_agreement']=='MATCHES_PINNED_CALENDAR','PAPER_INTENT_CALENDAR_UNVERIFIED')
    need(not any('CLOCK' in reason or 'CALENDAR' in reason for reason in diagnostic['deficiencies']),'PAPER_INTENT_CLOCK_UNVERIFIED')
    if purpose=='CANCEL':return at+timedelta(seconds=60),None
    day=at.astimezone(NY).date()
    try:session=session_times(day.isoformat())
    except DataError:raise RuntimeRefused('PAPER_INTENT_CALENDAR_UNVERIFIED') from None
    need(session.open<=at<session.close,'PAPER_INTENT_WINDOW')
    end=session.close
    if purpose.startswith('FIXTURE_') or purpose=='STRATEGY':
        start=datetime.combine(day,time(9,35),NY).astimezone(timezone.utc)
        stop=datetime.combine(day,time(9,36) if purpose=='STRATEGY' else time(10,5),NY).astimezone(timezone.utc)
        need(start<=at<stop,'PAPER_INTENT_WINDOW');end=min(end,stop)
    if purpose=='STRATEGY':need(terms['rebalance_session']==day.isoformat(),'PAPER_INTENT_SESSION_CHANGED')
    return min(at+timedelta(seconds=60),end),min(at+timedelta(seconds=600),session.close) if purpose=='CLOSE_LONG' else None
