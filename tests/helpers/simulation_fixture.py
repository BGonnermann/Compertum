"""Entirely invented prices. The date axis alone comes from the exchange calendar."""
from datetime import timedelta
from decimal import Decimal
from functools import lru_cache
import json

from compertum.data.calendar import session_times
from compertum.data.snapshot import validate_snapshot


@lru_cache(maxsize=8)
def fixture(symbols=('AAPL','MSFT','JPM','SPY'), scored=44):
    dates=['2020-01-02']
    for _ in range(252+scored):
        dates.append(session_times(dates[-1]).next_date)
    chunks=[]
    for symbol in symbols:
        for offset in range(0,len(dates)-1,128):
            sessions=dates[offset:min(offset+128,len(dates)-1)]
            rows=[]
            for date in sessions:
                t=session_times(date);n=session_times(t.next_date)
                # Strong momentum at the first decision, then constant execution marks.
                index=dates.index(date)
                daily='80' if index<241 and symbol!='SPY' else '100'
                for ref,adj,label,available,price,day in (
                    ('daily','raw',t.open.replace(hour=5,minute=0),n.decision,daily,date),
                    ('daily','split',t.open.replace(hour=5,minute=0),n.decision,daily,date),
                    ('close','raw',t.close_reference,t.close+timedelta(minutes=15),'100',date),
                    ('entry','raw',n.entry,n.entry+timedelta(minutes=16),'100',t.next_date)):
                    rows.append(dict(asset_id=symbol,session_date=day,reference=ref,adjustment=adj,feed='iex',revision_id='v1',
                        bar_label_time=label.isoformat(),provider_timestamp=label.isoformat(),retrieved_at='2026-10-09T00:00:00Z',
                        first_seen_at='2026-10-09T00:00:00Z',feature_available_at='2026-10-09T00:00:00Z',
                        simulated_available_at=available.isoformat(),simulated_revision_available_at=available.isoformat(),
                        open=price,high=price,low=price,close=price,volume='20000'))
            chunks.append(validate_snapshot(json.dumps(dict(schema_version='1',source=dict(provider='synthetic',feed='iex',
                vintage='baseline-fixture-v1',availability_basis='SIMULATED_AVAILABILITY',aggregation='PROVIDER_DAILY'),
                assets=[dict(asset_id=symbol,symbol=symbol)],feature_sessions=sessions,bars=rows,actions=[])).encode()))
    return tuple(chunks),dates[252],dates[251+scored],tuple(dates)


def changed(chunks, edit):
    result=[]
    for chunk in chunks:
        value=json.loads(chunk.content);edit(value)
        result.append(validate_snapshot(json.dumps(value).encode()))
    return tuple(result)


SECTORS={'AAPL':'fixture-tech','MSFT':'fixture-tech','JPM':'fixture-bank','SPY':'fixture-index'}


def with_action(chunks,day,kind='DIVIDEND',factor='2',known='2020-01-01T00:00:00Z',pay_date=None):
    action=dict(action_id='action-fixture-1',asset_id='AAPL',kind=kind,effective_session=day,
        ex_date=day if kind=='DIVIDEND' else None,pay_date=(pay_date or day) if kind=='DIVIDEND' else None,
        factor=factor if kind=='SPLIT' else None,amount='1' if kind=='DIVIDEND' else None,
        first_known_at=None,simulated_known_at=known,lineage='synthetic')
    def edit(v):
        if v['assets'][0]['symbol']!='AAPL':return
        include=day<=v['feature_sessions'][-1]
        if include:v['actions'].append(action.copy())
        if kind=='SPLIT':
            f=Decimal(factor)
            for b in v['bars']:
                if b['session_date']>=day or (include and b['adjustment']=='split'):
                    for k in ('open','high','low','close'):b[k]=format(Decimal(b[k])/f,'f')
                    b['volume']=format(Decimal(b['volume'])*f,'f')
    return changed(chunks,edit)
