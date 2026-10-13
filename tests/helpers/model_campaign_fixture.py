"""Invented complete sessions spanning a small annual fit and evaluation boundary."""
from datetime import timedelta
from functools import lru_cache
from decimal import Decimal as D
import json
from compertum.data.calendar import session_times
from compertum.data.snapshot import validate_snapshot
from compertum.modeling.registry import annual_cutoff
from helpers.simulation_fixture import SECTORS

@lru_cache(maxsize=3)
def campaign_fixture(year=2021):
    first=annual_cutoff(year).date().isoformat();dates=[first]
    for _ in range(297):dates.insert(0,session_times(dates[0]).previous_date)
    for _ in range(31):dates.append(session_times(dates[-1]).next_date)
    chunks=[]
    for j,symbol in enumerate(SECTORS):
        for offset in range(0,len(dates)-1,128):
            sessions=dates[offset:min(offset+128,len(dates)-1)];rows=[]
            for date in sessions:
                t=session_times(date);n=session_times(t.next_date);i=dates.index(date)
                for ref,adj,label,available,day in [('daily','raw',t.open.replace(hour=5,minute=0),n.decision,date),('daily','split',t.open.replace(hour=5,minute=0),n.decision,date),('close','raw',t.close_reference,t.close+timedelta(minutes=15),date),('entry','raw',n.entry,n.entry+timedelta(minutes=16),t.next_date)]:
                    index=i+(ref=='entry');price=format(D(80)+D(index)*(j+1)/20,'f')
                    rows.append(dict(asset_id=symbol,session_date=day,reference=ref,adjustment=adj,feed='iex',revision_id='invented-v1',bar_label_time=label.isoformat(),provider_timestamp=label.isoformat(),retrieved_at='2026-10-09T00:00:00Z',first_seen_at='2026-10-09T00:00:00Z',feature_available_at='2026-10-09T00:00:00Z',simulated_available_at=available.isoformat(),simulated_revision_available_at=available.isoformat(),open=price,high=price,low=price,close=price,volume='50000'))
            chunks.append(validate_snapshot(json.dumps(dict(schema_version='1',source=dict(provider='synthetic',feed='iex',vintage='candidate-fixture-v1',availability_basis='SIMULATED_AVAILABILITY',aggregation='PROVIDER_DAILY'),assets=[dict(asset_id=symbol,symbol=symbol)],feature_sessions=sessions,bars=rows,actions=[])).encode()))
    return tuple(chunks),dates[252],dates[296],first,dates[327],session_times(dates[328]).decision.isoformat()
