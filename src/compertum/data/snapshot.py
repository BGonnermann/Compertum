"""Immutable synthetic snapshots and explicit historical availability rules."""
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal,localcontext
import hashlib,json,re
from .calendar import NY,session_date,session_times,utc_time
from .errors import DataError
from .encoding import canonical
from .snapshot_text import MAX_INPUT,SECRET,safe_text

MAX_BARS=1024
BAR_FIELDS=set('asset_id session_date reference adjustment feed revision_id bar_label_time provider_timestamp retrieved_at first_seen_at feature_available_at simulated_available_at simulated_revision_available_at open high low close volume'.split())
ACTION_FIELDS=set('action_id asset_id kind effective_session ex_date pay_date factor amount first_known_at simulated_known_at lineage'.split())
TIME_FIELDS=('bar_label_time','provider_timestamp','retrieved_at','first_seen_at','feature_available_at','simulated_available_at','simulated_revision_available_at')




def _fields(value,expected):
    if not isinstance(value,dict) or set(value)!=expected:raise DataError('INVALID_FIELDS')


def _id(value):
    if not isinstance(value,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}',value):raise DataError('INVALID_ID')
    return value


def _number(value,*,zero=False):
    if not isinstance(value,str) or not re.fullmatch(r'\d{1,16}(?:\.\d{1,12})?',value):raise DataError('INVALID_NUMBER')
    d=Decimal(value)
    if d<0 or (d==0 and not zero) or len(d.as_tuple().digits)>28:raise DataError('INVALID_NUMBER')
    with localcontext() as ctx:
        ctx.prec=28
        return format(d.normalize(),'f')


def _equal(left,right):
    return abs(left-right)<=Decimal('1e-10')+Decimal('1e-8')*abs(right)


@dataclass(frozen=True)
class Snapshot:
    content:bytes
    sha256:str
    diagnostics:tuple[str,...]


def validate_snapshot(raw):
    text=safe_text(raw)
    def pairs(items):
        result={}
        for k,v in items:
            if k in result:raise DataError('DUPLICATE_KEY')
            result[k]=v
        return result
    try:value=json.loads(text,object_pairs_hook=pairs,parse_constant=lambda _:(_ for _ in ()).throw(DataError('INVALID_NUMBER')))
    except (ValueError,RecursionError) as e:
        if isinstance(e,DataError):raise
        raise DataError('INVALID_JSON') from None
    _fields(value,{'schema_version','source','assets','feature_sessions','bars','actions'})
    if value['schema_version']!='1':raise DataError('SCHEMA_VERSION')
    source=value['source'];_fields(source,{'provider','feed','vintage','availability_basis','aggregation'})
    if source['provider']!='synthetic':raise DataError('SYNTHETIC_ONLY')
    if source['feed']!='iex' or source['availability_basis']!='SIMULATED_AVAILABILITY' or source['aggregation']!='PROVIDER_DAILY':raise DataError('INVALID_SOURCE')
    _id(source['vintage'])
    assets=value['assets'];sessions=value['feature_sessions'];bars=value['bars'];actions=value['actions']
    if not isinstance(assets,list) or not 1<=len(assets)<=13 or not isinstance(sessions,list) or not 1<=len(sessions)<=256:raise DataError('INPUT_BOUND')
    if not isinstance(bars,list) or not 1<=len(bars)<=MAX_BARS or not isinstance(actions,list) or len(actions)>256:raise DataError('INPUT_BOUND')
    ids=[];symbols=[]
    for asset in assets:
        _fields(asset,{'asset_id','symbol'});ids.append(_id(asset['asset_id']));symbols.append(_id(asset['symbol']))
    if len(set(ids))!=len(ids) or len(set(symbols))!=len(symbols):raise DataError('DUPLICATE_ASSET')
    for s in sessions:session_times(s)
    if len(set(sessions))!=len(sessions):raise DataError('DUPLICATE_SESSION')
    sessions=sorted(sessions);diagnostics={'SYNTHETIC_ONLY','FINANCIAL_ACCEPTANCE_UNVERIFIED'}
    action_keys=set();action_ids=set()
    for action in actions:
        _fields(action,ACTION_FIELDS);_id(action['action_id']);_id(action['lineage'])
        if action['asset_id'] not in ids or action['kind'] not in ('SPLIT','DIVIDEND'):raise DataError('INVALID_ACTION')
        session_times(action['effective_session']);key=(action['asset_id'],action['kind'],action['effective_session'])
        if key in action_keys or action['action_id'] in action_ids:raise DataError('DUPLICATE_ACTION')
        action_keys.add(key);action_ids.add(action['action_id'])
        if action['effective_session']>sessions[-1]:raise DataError('ACTION_OUTSIDE_VINTAGE')
        if action['first_known_at'] is None:diagnostics.add('ACTION_KNOWLEDGE_UNVERIFIED')
        else:action['first_known_at']=utc_time(action['first_known_at']).isoformat()
        action['simulated_known_at']=utc_time(action['simulated_known_at']).isoformat()
        if action['kind']=='SPLIT':
            if any(action[k] is not None for k in ('ex_date','pay_date','amount')):raise DataError('INVALID_ACTION')
            action['factor']=_number(action['factor'])
            if Decimal(action['factor'])==1:raise DataError('INVALID_ACTION')
        else:
            if action['factor'] is not None or action['ex_date']!=action['effective_session']:raise DataError('ACTION_DATES')
            if session_date(action['pay_date'])<session_date(action['ex_date']):raise DataError('ACTION_DATES')
            action['amount']=_number(action['amount'],zero=True)
    rows={}
    for bar in bars:
        _fields(bar,BAR_FIELDS)
        if bar['asset_id'] not in ids:raise DataError('UNKNOWN_ASSET')
        if bar['feed']!=source['feed']:raise DataError('FEED_MISMATCH')
        if bar['reference'] not in ('daily','entry','close') or bar['adjustment'] not in ('raw','split'):raise DataError('INVALID_REFERENCE')
        if bar['reference']!='daily' and bar['adjustment']!='raw':raise DataError('INVALID_REFERENCE')
        _id(bar['revision_id']);times=session_times(bar['session_date'])
        key=(bar['asset_id'],bar['session_date'],bar['reference'],bar['adjustment'])
        if key in rows:raise DataError('DUPLICATE_ROW')
        rows[key]=bar
        for k in TIME_FIELDS:bar[k]=utc_time(bar[k]).isoformat()
        stamp={k:utc_time(bar[k]) for k in TIME_FIELDS}
        if not stamp['provider_timestamp']<=stamp['first_seen_at']<=stamp['retrieved_at'] or stamp['feature_available_at']<stamp['first_seen_at']:raise DataError('ACTUAL_TIME_ORDER')
        if bar['reference']=='daily':
            if stamp['bar_label_time'].astimezone(NY).date().isoformat()!=bar['session_date']:raise DataError('REFERENCE_TIME')
            earliest=session_times(times.next_date).decision
        else:
            expected=times.entry if bar['reference']=='entry' else times.close_reference
            if stamp['bar_label_time']!=expected:raise DataError('REFERENCE_TIME')
            earliest=expected+timedelta(minutes=16)
        if stamp['simulated_available_at']<earliest or stamp['simulated_revision_available_at']<stamp['simulated_available_at']:raise DataError('AVAILABILITY_BEFORE_POLICY')
        for k in ('open','high','low','close','volume'):bar[k]=_number(bar[k],zero=k=='volume')
        o,h,l,c=(Decimal(bar[k]) for k in ('open','high','low','close'))
        if not l<=o<=h or not l<=c<=h:raise DataError('INVALID_OHLC')
    expected=set()
    for asset in ids:
        for s in sessions:
            next_s=session_times(s).next_date
            expected.update(((asset,s,'daily','raw'),(asset,s,'daily','split'),(asset,s,'close','raw'),(asset,next_s,'entry','raw')))
    if set(rows)!=expected:raise DataError('MISSING_ROW' if expected-set(rows) else 'UNEXPECTED_ROW')
    with localcontext() as ctx:
        ctx.prec=28
        for asset in ids:
            for s in sessions:
                rawbar=rows[(asset,s,'daily','raw')];adjusted=rows[(asset,s,'daily','split')];factor=Decimal(1)
                for action in actions:
                    if action['asset_id']==asset and action['kind']=='SPLIT' and s<action['effective_session']<=sessions[-1]:factor*=Decimal(action['factor'])
                if not all(_equal(Decimal(adjusted[k])*factor,Decimal(rawbar[k])) for k in ('open','high','low','close')) or not _equal(Decimal(adjusted['volume']),Decimal(rawbar['volume'])*factor):raise DataError('ADJUSTMENT_MISMATCH')
    value.update(assets=sorted(assets,key=lambda a:a['asset_id']),feature_sessions=sessions,bars=[rows[k] for k in sorted(rows)],actions=sorted(actions,key=lambda a:(a['asset_id'],a['effective_session'],a['kind'],a['action_id'])))
    content=canonical(value)
    if len(content)>MAX_INPUT:raise DataError('INPUT_BOUND')
    return Snapshot(content,hashlib.sha256(content).hexdigest(),tuple(sorted(diagnostics)))


def feature_rows(snapshot,execution_session):
    if not isinstance(snapshot,Snapshot):raise DataError('INVALID_SNAPSHOT')
    verified=validate_snapshot(snapshot.content)
    if verified.sha256!=snapshot.sha256 or verified.diagnostics!=snapshot.diagnostics:raise DataError('SNAPSHOT_CORRUPT')
    value=json.loads(verified.content);times=session_times(execution_session)
    if times.previous_date not in value['feature_sessions']:raise DataError('FEATURE_COVERAGE')
    rows=tuple(b for b in value['bars'] if b['reference']=='daily' and b['session_date']==times.previous_date)
    if any(max(utc_time(b['simulated_available_at']),utc_time(b['simulated_revision_available_at']))>times.decision for b in rows):raise DataError('FEATURE_UNAVAILABLE')
    # Future-effective splits also affect retrospectively adjusted price levels.
    if any((a['effective_session']<=execution_session or a['kind']=='SPLIT') and utc_time(a['simulated_known_at'])>times.decision for a in value['actions']):raise DataError('ACTION_UNAVAILABLE')
    return rows
