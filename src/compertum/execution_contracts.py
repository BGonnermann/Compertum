"""Pure invented-account contracts. A valid record grants no transport authority."""
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
import hashlib
from uuid import UUID
from .domain import ContractError
from .data.encoding import canonical
from .simulation.policy import fixed_decimal

WATCHLIST=('AAPL','MSFT','AMZN','GOOGL','META','NVDA','JPM','XOM','JNJ','PG','UNH','HD')
TERMINAL=frozenset({'FILLED','CANCELED','EXPIRED','REJECTED'})

def instant(value):
    from .domain import _utc_time
    if not _utc_time(value):raise ContractError('INVALID_UTC_TIMESTAMP')
    return datetime.fromisoformat(value.replace('Z','+00:00'))


@fixed_decimal
def validate_execution_record(p):
    def require(value):
        if not value:raise ContractError('INVALID_EXECUTION_RECORD')
    def walk(value):
        if type(value) is float:require(False)
        if type(value) is dict:
            for key,item in value.items():
                if key.endswith('_id') and key!='client_order_id' and item is not None:
                    try:require(str(UUID(item))==item and UUID(item).int!=0)
                    except (ValueError,TypeError,AttributeError):require(False)
                walk(item)
        elif type(value) is list:
            for item in value:walk(item)
    walk(p);require(len(canonical(p))<=65536)
    if p['record_type']=='ExecutionDecision':
        require(p['allowed']==(not p['reasons']))
    elif p['record_type']=='ExecutionCalendar':
        opened=instant(p['session_open_at']);closed=instant(p['session_close_at']);ny=ZoneInfo('America/New_York')
        require(opened.astimezone(ny).date().isoformat()==p['session_date']==closed.astimezone(ny).date().isoformat())
        require(opened.astimezone(ny).time()==time(9,30) and closed.astimezone(ny).time() in (time(13),time(16)))
        require(p['prior_session']<p['session_date'] and opened.weekday()<5)
    elif p['record_type']=='ExecutionInputs':
        require(len({v['symbol'] for v in p['securities']})==len(p['securities']))
        mapping={v['symbol']:v['sector'] for v in p['securities']}
        require(p['sector_mapping_sha256']==hashlib.sha256(canonical(mapping)).hexdigest())
    elif p['record_type']=='ExecutionIntent':
        require(instant(p['created_at'])<instant(p['expires_at']))
        if p['kind']=='STRATEGY':require(p['side'] in ('buy','sell') and p['quantity']>0 and p['plan_id'] is None and p['child_index'] is None and p['order_id'] is None)
        elif p['kind']=='CLOSE_LONG':require(p['side']=='sell' and p['quantity']>0 and p['plan_id'] is not None and p['child_index'] is not None and p['order_id'] is None)
        else:require(p['side'] is None and p['quantity']==0 and p['plan_id'] is not None and p['child_index'] is None and p['order_id'] is not None)
    elif p['record_type']=='ExecutionPlan':
        from decimal import Decimal
        require(instant(p['created_at'])<instant(p['start_expires_at'])<=instant(p['deadline']))
        require((instant(p['start_expires_at'])-instant(p['created_at'])).total_seconds()<=60)
        require((instant(p['deadline'])-instant(p['created_at'])).total_seconds()<=600)
        require(len({v['symbol'] for v in p['positions']})==len(p['positions']))
        require(len({v['order_id'] for v in p['cancel_orders']})==len(p['cancel_orders']))
        require([v['index'] for v in p['children']]==list(range(len(p['children']))))
        require(len({v['intent_id'] for v in p['children']+p['cancel_orders']})==len(p['children'])+len(p['cancel_orders']))
        positions={v['symbol']:v for v in p['positions']}
        require(all(v['symbol'] in positions for v in p['children']))
        for item in p['positions']:
            children=[v for v in p['children'] if v['symbol']==item['symbol']]
            require(item['quantity']==item['planned_quantity']+item['residual_quantity'])
            require(item['planned_quantity']==sum(v['maximum_quantity'] for v in children))
            require(Decimal(item['cap'])>0 and Decimal(item['ask'])>=Decimal(item['bid'])>0)
            for child in children:
                require(child['maximum_quantity']>0)
                require(Decimal(child['maximum_notional'])==Decimal(item['cap'])<=2000)
                require(Decimal(child['planned_notional'])==child['maximum_quantity']*Decimal(item['ask'])*Decimal('1.01')<=Decimal(child['maximum_notional']))
        if p['kind']=='CANCEL':require(not p['positions'] and not p['children'])
    elif p['record_type']=='ExecutionStart':
        require(instant(p['started_at'])<instant(p['deadline']))
    elif p['record_type']=='ExecutionAuthorization':
        require(instant(p['authorized_at'])<instant(p['start_expires_at']))
    else:
        for field,key in (('quotes','symbol'),('positions','symbol'),('orders','order_id'),('orders','client_order_id')):
            require(len({r[key] for r in p[field]})==len(p[field]))
        require(all(o['filled_quantity']<=o['quantity'] and o['quantity']>0 for o in p['orders']))
        for order in p['orders']:
            from decimal import Decimal
            require((order['filled_quantity']==0)==(Decimal(order['filled_notional'])==0))
            if order['status']=='FILLED':require(order['filled_quantity']==order['quantity'])
            elif order['status']=='PARTIALLY_FILLED':require(0<order['filled_quantity']<order['quantity'])
            elif order['status']=='ACKNOWLEDGED':require(order['filled_quantity']==0)
            elif order['status']=='REJECTED':require(order['filled_quantity']==0)
        clock=p['clock'];start=instant(clock['session_open_at']);end=instant(clock['session_close_at'])
        require(start<end and start<=instant(clock['strategy_open_at'])<instant(clock['strategy_close_at'])<=end)
        require(clock['prior_session']<start.date().isoformat())


def record_sha256(record):
    return hashlib.sha256(canonical(record.to_payload())).hexdigest()


def calendar_reasons(observation,calendar):
    from .domain import ExecutionCalendar
    if type(calendar) is not ExecutionCalendar:return ['CALENDAR_PIN_REQUIRED']
    o=observation.to_payload();c=calendar.to_payload();clock=o['clock']
    if clock['calendar_sha256']!=record_sha256(calendar):return ['CALENDAR_CHANGED']
    if any(clock[k]!=c[k] for k in ('prior_session','session_open_at','session_close_at')):return ['CALENDAR_MISMATCH']
    day=instant(c['session_open_at']).astimezone(ZoneInfo('America/New_York')).date()
    start=datetime.combine(day,time(9,35),ZoneInfo('America/New_York')).astimezone(timezone.utc)
    if instant(clock['strategy_open_at'])!=start or instant(clock['strategy_close_at'])!=start+timedelta(minutes=1):return ['STRATEGY_WINDOW_CHANGED']
    return []
