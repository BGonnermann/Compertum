"""Bounded incident evidence and per-result operator warning witnesses."""
import math
from .events import uuid
from .execution_contracts import instant
from .execution_authority import _decode
from .runtime.errors import RuntimeRefused

KIND='OPERATOR_INCIDENT_RESULT'
CONTRACT='incident-result-v1'

def _bad():raise RuntimeRefused('OPERATION_STATE_CORRUPT')

def _time(value):
    if type(value) is not str or not 1<=len(value.encode('utf-8'))<=64:_bad()
    try:return instant(value)
    except (TypeError,ValueError):_bad()

def _elapsed(value):
    if type(value) not in (int,float) or not math.isfinite(value) or not 0<=value<=315537897600:_bad()
    return value

def _incident(started,elapsed,index,active,*,at=None):
    start=_time(started);_elapsed(elapsed)
    if type(index) is not int or not 0<=index<=6 or type(active) is not int or active not in (0,1):_bad()
    if at is not None and not 0<=elapsed<=(_time(at)-start).total_seconds():_bad()
    return dict(started_at=started,last_elapsed=elapsed,next_index=index,active=active)

def current(db,intent):
    row=db.execute('SELECT CASE WHEN length(CAST(started_at AS BLOB))<=64 THEN started_at END,last_elapsed,next_index,active FROM fake_incidents WHERE account=? AND intent_id=?',(intent['account_alias'],intent['intent_id'])).fetchone()
    return None if row is None else _incident(*row)

def _events(db,intent,kind,maximum):
    rows=db.execute('SELECT CASE WHEN length(CAST(body AS BLOB))<=1024 THEN body END FROM fake_intent_events WHERE account=? AND intent_id=? AND kind=? ORDER BY seq LIMIT ?',(intent['account_alias'],intent['intent_id'],kind,maximum+1)).fetchall()
    if len(rows)>maximum:_bad()
    for raw, in rows:
        try:value=_decode(raw,1024)
        except RuntimeRefused:_bad()
        if type(value) is not dict:_bad()
        yield value

def verify_incident(db,intent,started,elapsed=120,at=None):
    _time(started);_elapsed(elapsed)
    if at is not None and (_time(at)-_time(started)).total_seconds()!=elapsed:_bad()
    row=current(db,intent)
    if row is not None and row['started_at']==started and row['last_elapsed']>=elapsed:return True
    for event in _events(db,intent,'INCIDENT_RESOLVED',512):
        if set(event)!={'at','started_at','next_index','last_elapsed'}:_bad()
        old=_incident(event['started_at'],event['last_elapsed'],event['next_index'],0,at=event['at'])
        if old['started_at']==started and old['last_elapsed']>=elapsed and (at is None or _time(at)<=_time(event['at'])):return True
    return False

def warning(started,elapsed):
    return dict(reason='UNRESOLVED_LIMIT',operator_action_required=True,incident_started_at=started) if elapsed>=120 else {}

def current_warning(db,intent,status):
    if status not in {'UNKNOWN','SUBMITTING'}:return {}
    row=current(db,intent)
    if row is None:return {}  # An interrupted submission may precede incident creation.
    if row['active']!=1:_bad()
    return warning(row['started_at'],row['last_elapsed'])

def result_witness(db,intent,request_id,*,required=True):
    found=[]
    for event in _events(db,intent,KIND,64):
        if set(event)!={'request_id','at','intent_status','started_at','elapsed_seconds'}:_bad()
        try:uuid(event['request_id'])
        except (ValueError,TypeError,RuntimeRefused):_bad()
        _time(event['at']);_time(event['started_at']);_elapsed(event['elapsed_seconds'])
        if event['intent_status'] not in {'UNKNOWN','SUBMITTING'} or (_time(event['at'])-_time(event['started_at'])).total_seconds()!=event['elapsed_seconds']:_bad()
        if event['request_id']==request_id:found.append(event)
    if len(found)>1 or required and not found:_bad()
    return found[0] if found else None

def record_result(journal,intent,request_id,status,now):
    """Commit independent incident evidence before the two operator result mirrors."""
    if status not in {'UNKNOWN','SUBMITTING'}:return {}
    account,key=intent['account_alias'],intent['intent_id'];uuid(request_id);at=_time(now)
    with journal._transaction():
        actual=journal._row(account,key)
        if actual['intent']!=intent or actual['status']!=status:_bad()
        row=current(journal.db,intent)
        if row is None or row['active']!=1:_bad()
        elapsed=(at-_time(row['started_at'])).total_seconds();_elapsed(elapsed)
        if elapsed<row['last_elapsed']:raise RuntimeRefused('INCIDENT_CLOCK_REVERSED')
        changed=journal.db.execute('UPDATE fake_incidents SET last_elapsed=? WHERE account=? AND intent_id=?',(elapsed,account,key))
        if changed.rowcount!=1 or current(journal.db,intent)!=dict(row,last_elapsed=elapsed):raise RuntimeRefused('INCIDENT_ALERT_WRITE_UNVERIFIED')
        witness=dict(request_id=request_id,at=now,intent_status=status,started_at=row['started_at'],elapsed_seconds=elapsed)
        journal._event(account,key,KIND,witness)
        if result_witness(journal.db,intent,request_id)!=witness:raise RuntimeRefused('INCIDENT_ALERT_WRITE_UNVERIFIED')
    return warning(row['started_at'],elapsed)
