"""Candidate measures, records only (docs/CANDIDATE_MEASURES_DESIGN.md, part 1). Nothing here passes, ranks or queues a candidate."""
from decimal import Decimal
import gzip
import hashlib
import json
import math
from pathlib import Path
import re

import numpy as np

from compertum.runtime.errors import RuntimeRefused
from . import library_multi
from .market import cost_at,nav_paths,parse_signals

YEAR=252
BLOCKS=4
EARLY=2/3
SERIES_DIR=Path('state')/'engine'/'series'
_SAFE=re.compile(r'[^A-Za-z0-9_.-]')


def single_paths(text,rows):
    positions=parse_signals(text,rows)
    returns=[Decimal(r['return']) for r in rows];rates=[Decimal(r.get('rate','0')) for r in rows];costs=[cost_at(r['session']) for r in rows]
    def active(held,charged): return [float(a) for a in nav_paths(held,returns,rates,charged)[4]]
    return {'base':active(positions,costs),'lagged':active([0]+positions[:-1],costs),'cost_2x':active(positions,[2*c for c in costs]),'weights':None}


def panel_paths(market,text):
    from .panel import parse_weights
    p=market.p;targets=parse_weights(text,p,market.aliases);u=library_multi.prepare(p,sorted(p['closes']));start,end=p['train'],u['n']
    def active(chosen,costs): return library_multi.run_navs({**u,'costs':costs},chosen,start,end,None)[4]
    return {'base':active(targets,u['costs']),'lagged':active([{}]+list(targets[:-1]),u['costs']),'cost_2x':active(targets,[2*c for c in u['costs']]),
            'weights':targets[start:end-1]}


def active_sharpe(a):
    a=np.asarray(a,dtype=float)
    if a.size<2: return None
    sd=a.std(ddof=1)
    return None if not sd>0 else float(a.mean()/sd*math.sqrt(YEAR))


def tail_ratio(a):
    low=abs(float(np.percentile(a,5)))
    return None if low==0 else float(np.percentile(a,95))/low


def lag_autocorr(a):
    a=np.asarray(a,dtype=float)
    if a.size<3 or a[:-1].std()==0 or a[1:].std()==0: return None
    return float(np.corrcoef(a[:-1],a[1:])[0,1])


def newey_west(a):
    """t-statistic of the mean with the Newey-West variance (Bartlett weights, lags floor(4 (n/100)^(2/9)))."""
    a=np.asarray(a,dtype=float);n=a.size
    if n<3: return None
    d=a-a.mean();lags=int(4*(n/100)**(2/9));var=float(d@d)/n
    for k in range(1,min(lags,n-1)+1): var+=2*(1-k/(lags+1))*float(d[k:]@d[:-k])/n
    return None if not var>0 else float(a.mean()/math.sqrt(var/n))


def block_sharpes(a):
    values=[active_sharpe(b) for b in np.array_split(np.asarray(a,dtype=float),BLOCKS)]
    known=[v for v in values if v is not None]
    return {'values':values,'min':min(known) if known else None,'spread':max(known)-min(known) if known else None,'positive':sum(v>0 for v in known)}


def concentration(weights):
    invested=[w for w in weights if w and sum(w.values())>0]
    if not invested: return None
    effective=[sum(w.values())**2/sum(x*x for x in w.values()) for w in invested]
    return {'effective_assets':float(np.mean(effective)),'max_weight':max(max(w.values()) for w in invested)}


def series_measures(paths,part=slice(None)):
    base=np.asarray(paths['base'],dtype=float)[part];lagged=np.asarray(paths['lagged'],dtype=float)[part];doubled=np.asarray(paths['cost_2x'],dtype=float)[part]
    if base.size<2*BLOCKS: raise RuntimeRefused('ENGINE_MEASURES_SHORT')
    sharpe=active_sharpe(base);late=active_sharpe(lagged)
    return {'sessions':int(base.size),'active_sharpe':sharpe,'tail_ratio':tail_ratio(base),'hit_rate':float((base>0).mean()),'block_sharpes':block_sharpes(base),
            'lag_drop':None if sharpe is None or late is None else sharpe-late,'cost_2x_active_sharpe':active_sharpe(doubled),
            'autocorrelation':lag_autocorr(base),'newey_west_t':newey_west(base)}


def clean(value):
    if isinstance(value,float): return round(value,8) if math.isfinite(value) else None
    if isinstance(value,dict): return {k:clean(v) for k,v in value.items()}
    if isinstance(value,list): return [clean(v) for v in value]
    return value


def save_series(project_root,candidate_id,series):
    """Write the daily active returns as gzip JSON with a fixed header time, so the same series gives the same SHA-256."""
    if not isinstance(candidate_id,str) or not 1<=len(candidate_id)<=128: raise RuntimeRefused('ENGINE_MEASURES_DENIED')
    folder=Path(project_root).absolute()/SERIES_DIR;folder.mkdir(parents=True,exist_ok=True)
    data=gzip.compress(json.dumps({'candidate_id':candidate_id,'active':[repr(float(x)) for x in series]},separators=(',',':')).encode('utf-8'),mtime=0)
    path=folder/(_SAFE.sub('_',candidate_id)+'.json.gz')
    if path.exists(): raise RuntimeRefused('ENGINE_MEASURES_DUPLICATE')
    path.write_bytes(data)
    return {'path':path.relative_to(Path(project_root).absolute()).as_posix(),'sha256':hashlib.sha256(data).hexdigest(),'sessions':len(series)}


def load_series(project_root,record):
    data=(Path(project_root).absolute()/record['path']).read_bytes()
    if hashlib.sha256(data).hexdigest()!=record['sha256']: raise RuntimeRefused('ENGINE_MEASURES_CHANGED')
    return [float(x) for x in json.loads(gzip.decompress(data))['active']]


def candidate_measures(*,project_root,candidate_id,signals,score,market=None,validation_rows=None,runs=()):
    """All part 1 measures of one scored candidate. Any failure gives status UNDEFINED with the reason; it never raises."""
    try:
        paths=panel_paths(market,signals) if market is not None else single_paths(signals,validation_rows)
        cut=int(len(paths['base'])*EARLY)
        sessions=int(score.get('sessions') or 0)
        exposure=(score['sessions_invested'] if market is not None else score['positions_held'])/sessions if sessions else None
        turnover=float(score['turnover_per_year']) if market is not None else score['position_changes']*YEAR/max(sessions-1,1)
        built=[r for r in runs if r.get('purpose')=='engineer' and r.get('job_folder') is not None]
        source=next((r for r in reversed(built) if r.get('status')=='COMPLETED' and r.get('signals') is not None),None)
        record={'status':'MEASURED','full':series_measures(paths),'early':series_measures(paths,slice(None,cut)),
                'late_active_sharpe':active_sharpe(paths['base'][cut:]),'exposure':exposure,'turnover_per_year':turnover,
                'concentration':concentration(paths['weights']) if paths['weights'] is not None else None,'engineer_runs':len(built),
                'code_bytes':sum(len(v.encode('utf-8')) for v in (source.get('files') or {}).values()) if source else None}
        record=clean(record);record['series']=save_series(project_root,candidate_id,paths['base'])
        return record
    except RuntimeRefused as error: return {'status':'UNDEFINED','reason':error.code}
    except Exception as error: return {'status':'UNDEFINED','reason':f'{type(error).__name__}: {str(error)[:200]}'}
