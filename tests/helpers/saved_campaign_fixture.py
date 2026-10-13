"""Small persistence fixtures retain real boundaries but intentionally lack warmup."""
from dataclasses import replace
from functools import lru_cache
import json
from compertum.data.calendar import session_times
from compertum.data.encoding import canonical
from compertum.data.snapshot import validate_snapshot
from compertum.modeling.campaign import FoldInput
from helpers.model_campaign_fixture import campaign_fixture,SECTORS

@lru_cache(maxsize=2)
def campaign_folds(full=False):
    result=[]
    for year in (2021,2022,2023):
        chunks,ts,te,start,end,asof=campaign_fixture(year)
        if not full:
            end=session_times(start).next_date;ts=te
            selected={te,start,end};filtered=[]
            for chunk in chunks:
                value=json.loads(chunk.content);dates=selected.intersection(value['feature_sessions'])
                if not dates:continue
                value['feature_sessions']=sorted(dates)
                entry_dates={session_times(d).next_date for d in dates}
                value['bars']=[b for b in value['bars'] if b['session_date'] in (entry_dates if b['reference']=='entry' else dates)]
                filtered.append(validate_snapshot(canonical(value)))
            chunks=tuple(filtered);asof=session_times(session_times(end).next_date).decision.isoformat()
        result.append(FoldInput(chunks,SECTORS,ts,te,start,end,asof))
    return tuple(result)
