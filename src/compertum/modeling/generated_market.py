"""Closed synthetic full-calendar market; no caller rows, paths or data access."""
from datetime import timedelta
from decimal import Decimal as D
import hashlib,json
from importlib.metadata import version
from compertum.data.calendar import session_times
from compertum.data.snapshot import validate_snapshot
from compertum.data.encoding import canonical
from compertum.data.errors import DataError
from compertum.final_recipe import recipe_for_pin
from compertum.simulation.market import load_market
from compertum.simulation.policy import fixed_decimal
from .registry import _calendar_cutoff


@fixed_decimal
def generate_market(raw,*,expected_sha256):
    if type(raw) is not bytes or not 0<len(raw)<=4096 or hashlib.sha256(raw).hexdigest()!=expected_sha256:
        raise DataError('GENERATED_RECIPE_UNVERIFIED')
    v=recipe_for_pin(expected_sha256)
    if canonical(v)!=raw:raise DataError('GENERATED_RECIPE_UNVERIFIED')
    if v['schema']!='builtin-generated-final-recipe-v2':raise DataError('GENERATED_RECIPE_UNSUPPORTED')
    if version(v['calendar']['package'])!=v['calendar']['version']:raise DataError('GENERATED_CALENDAR_CHANGED')
    dates=[v['warmup_start']]
    while dates[-1]!=v['last_score']:
        if len(dates)>=1024:raise DataError('INPUT_BOUND')
        dates.append(session_times(dates[-1]).next_date)
    training=dates.index(v['initial_training_start']);scoring=dates.index(v['first_score'])
    if training!=v['warmup_sessions'] or scoring-training!=v['initial_training_sessions']:
        raise DataError('GENERATED_CALENDAR_CHANGED')
    times={day:session_times(day) for day in dates};indices={day:i for i,day in enumerate(dates)}
    chunks=[];terminal=[]
    for j,symbol in enumerate(v['symbols']):
        for offset in range(0,len(dates)-1,128):
            sessions=dates[:-1][offset:offset+128];bars=[]
            for day in sessions:
                t=times[day];n=session_times(t.next_date);i=indices[day]
                refs=[('daily','raw',t.open.replace(hour=5,minute=0),n.decision,day,i),
                    ('daily','split',t.open.replace(hour=5,minute=0),n.decision,day,i),
                    ('close','raw',t.close_reference,t.close+timedelta(minutes=15),day,i)]
                # No price row in reserved2026, even though final scoring
                # availability can legitimately be in the next session.
                refs.append(('entry','raw',n.entry,n.entry+timedelta(minutes=16),t.next_date,i+1))
                for reference,adjustment,label,available,row_day,index in refs:
                    price=format(D(80)+D(index)*(j+1)/20,'f')
                    bars.append(dict(asset_id=symbol,session_date=row_day,reference=reference,adjustment=adjustment,
                        feed='iex',revision_id='invented-final-v2',bar_label_time=label.isoformat(),provider_timestamp=label.isoformat(),
                        retrieved_at='2026-10-10T00:00:00Z',first_seen_at='2026-10-10T00:00:00Z',feature_available_at='2026-10-10T00:00:00Z',
                        simulated_available_at=available.isoformat(),simulated_revision_available_at=available.isoformat(),
                        open=price,high=price,low=price,close=price,volume=v['volume']))
            value=dict(schema_version='1',source=dict(provider='synthetic',feed='iex',vintage='generated-final-v2',
                availability_basis='SIMULATED_AVAILABILITY',aggregation='PROVIDER_DAILY'),
                assets=[dict(asset_id=symbol,symbol=symbol)],feature_sessions=sessions,bars=bars,actions=[])
            chunks.append(validate_snapshot(canonical(value)))
        # Snapshot feature sessions require a next-session entry. The closed
        # generator adds only its fixed terminal marks, with no 2026 prices.
        # Copy a validated same-symbol row so all source/availability fields
        # follow the same contract; replace every date-dependent value.
        prototype=next(b for b in json.loads(chunks[-1].content)['bars'] if b['reference']=='close')
        last=times[dates[-1]];after=session_times(last.next_date)
        price=format(D(80)+D(len(dates)-1)*(j+1)/20,'f')
        for reference,label,available in (
            ('daily',last.open.replace(hour=5,minute=0),after.decision),
            ('close',last.close_reference,last.close+timedelta(minutes=15))):
            terminal.append(dict(prototype,session_date=dates[-1],reference=reference,
                bar_label_time=label.isoformat(),provider_timestamp=label.isoformat(),
                simulated_available_at=available.isoformat(),simulated_revision_available_at=available.isoformat(),
                open=price,high=price,low=price,close=price))
    terminal_bytes=canonical(terminal)
    total_bytes=sum(len(c.content) for c in chunks)+len(terminal_bytes)
    if len(chunks)>64 or total_bytes>16*1024**2:raise DataError('INPUT_BOUND')
    market=load_market(tuple(chunks),v['sectors'])
    for row in terminal:
        key=(row['asset_id'],row['session_date'],row['reference'])
        if key in market.rows:raise DataError('DUPLICATE_BAR')
        market.rows[key]=row
    boundary_sha=hashlib.sha256(terminal_bytes).hexdigest()
    market.sha256=hashlib.sha256(canonical(dict(schema='generated-final-market-v2',
        recipe_sha256=expected_sha256,snapshot_market_sha256=market.sha256,terminal_sha256=boundary_sha))).hexdigest()
    annual={}
    for year in v['years']:
        days=[day for day in dates[scoring:] if day[:4]==str(year)]
        cutoff=_calendar_cutoff(year)
        if cutoff.date().isoformat()!=days[0]:raise DataError('GENERATED_CALENDAR_CHANGED')
        annual[str(year)]=dict(training_start=v['initial_training_start'],training_end=times[days[0]].previous_date,
            start=days[0],end=days[-1],cutoff=cutoff.isoformat(),scoring_as_of=session_times(times[days[-1]].next_date).decision.isoformat())
    metadata=dict(schema='generated-final-market-v2',recipe_sha256=expected_sha256,symbols=v['symbols'],
        sectors=v['sectors'],sessions=dates,scoring_sessions=dates[scoring:],training_start=v['initial_training_start'],
        annual=annual,chunk_sha256=[c.sha256 for c in chunks],terminal_sha256=boundary_sha,
        input_bytes=total_bytes,market_sha256=market.sha256,financial_accepted=False,
        limitations=['PARTIAL_TRAINING_FROM_2023_NOT_2016','THREE_OF_TWELVE_STOCKS','SIMULATED_AVAILABILITY','ZERO_UNVERIFIED_FEES'])
    return market,metadata

