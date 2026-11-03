"""Candidate measures and contribution to the book, records only (docs/CANDIDATE_MEASURES_DESIGN.md, parts 1 and 2). Nothing here passes,
ranks or queues a candidate."""
from decimal import Decimal
import gzip
import hashlib
import json
import math
from pathlib import Path
import re

import numpy as np

from compertum.events import canonical
from compertum.runtime.errors import RuntimeRefused
from . import library_multi
from .vault import fold
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


def series_path(project_root,candidate_id):
    if not isinstance(candidate_id,str) or not 1<=len(candidate_id)<=128: raise RuntimeRefused('ENGINE_MEASURES_DENIED')
    return Path(project_root).absolute()/SERIES_DIR/(_SAFE.sub('_',candidate_id)+'.json.gz')


def save_series(project_root,candidate_id,series):
    """Write the daily active returns as gzip JSON with a fixed header time, so the same series gives the same SHA-256."""
    path=series_path(project_root,candidate_id);path.parent.mkdir(parents=True,exist_ok=True)
    data=gzip.compress(json.dumps({'candidate_id':candidate_id,'active':[repr(float(x)) for x in series]},separators=(',',':')).encode('utf-8'),mtime=0)
    if path.exists(): raise RuntimeRefused('ENGINE_MEASURES_DUPLICATE')
    path.write_bytes(data)
    return {'path':path.relative_to(Path(project_root).absolute()).as_posix(),'sha256':hashlib.sha256(data).hexdigest(),'sessions':len(series)}


def load_series(project_root,record):
    data=(Path(project_root).absolute()/record['path']).read_bytes()
    if hashlib.sha256(data).hexdigest()!=record['sha256']: raise RuntimeRefused('ENGINE_MEASURES_CHANGED')
    return [float(x) for x in json.loads(gzip.decompress(data))['active']]


def library_series(project_root,p,candidate_id,eligible,market_sha256):
    """The VALIDATION active returns of one admitted library rule, made once per market from its recorded family and settings, and only when
    a recompute gives the score that was admitted. The file name holds the market fingerprint, so changed market files give a new file."""
    key=f'library:{candidate_id}:{market_sha256[:16]}';path=series_path(project_root,key)
    if path.is_file():
        data=path.read_bytes();record={'path':path.relative_to(Path(project_root).absolute()).as_posix(),'sha256':hashlib.sha256(data).hexdigest()}
        return record,load_series(project_root,record)
    route=eligible.get('route') or {};members=sorted(p['closes'])
    if route.get('family') not in library_multi.FAMILIES or len(members)!=route.get('members'): raise RuntimeRefused('ENGINE_BOOK_CHANGED')
    u=library_multi.prepare(p,members);targets=library_multi.weights(u,route['family'],route['knobs'])
    if hashlib.sha256(canonical(library_multi.score(u,targets,p['train'],u['n']))).hexdigest()!=eligible.get('score_sha256'): raise RuntimeRefused('ENGINE_BOOK_CHANGED')
    series=library_multi.run_navs(u,targets,p['train'],u['n'],None)[4]
    return save_series(project_root,key,series),series


def book_members(ledger,project_root,market_sha256,market=None):
    """The book (decision D2): candidates that passed stage 1 (ELIGIBLE or later) on this market. An engine candidate counts when its own
    measures record names the same market fingerprint; a library rule counts on its own panel universe when its recompute matches.
    Returns (members, skipped); each member has id, kind, sha256 and series."""
    events={}
    for event in ledger.queue_events(): events.setdefault(event['candidate_id'],[]).append(event)
    members=[];skipped=[]
    for cid,rows in events.items():
        state,_,eligible=fold(rows)
        if state is None or eligible is None: continue
        route=eligible.get('route') or {'kind':'engine'}
        try:
            if route.get('kind')=='library-multi':
                if market is None or market.p.get('universe')!=route.get('universe'): continue
                record,series=library_series(project_root,market.p,cid,eligible,market_sha256)
            elif route.get('kind')=='engine':
                found=[s.get('measures') for s in ledger.steps(cid.rsplit(':',1)[0]) if s.get('role')=='validator' and s.get('phase')=='SCORED' and s.get('candidate_id')==cid]
                own=found[-1] if found and isinstance(found[-1],dict) else {}
                if own.get('market_sha256')!=market_sha256 or not isinstance(own.get('series'),dict): continue
                record=own['series'];series=load_series(project_root,record)
            else: continue
        except RuntimeRefused as error: skipped.append({'id':cid,'reason':error.code});continue
        except (OSError,ValueError,KeyError,TypeError) as error: skipped.append({'id':cid,'reason':type(error).__name__});continue
        members.append({'id':cid,'kind':route['kind'],'sha256':record['sha256'],'series':series})
    return members,skipped


def correlation(a,b):
    if a.std()==0 or b.std()==0: return None
    return float(np.corrcoef(a,b)[0,1])


def book_measures(series,members):
    """Contribution to the book: correlation with each member, the Sharpe gain of the equal-weight mix with the candidate, and the Sharpe
    ratio of the candidate's active returns minus the part that a least-squares fit on the members explains (the intercept stays in)."""
    c=np.asarray(series,dtype=float);used=[m for m in members if len(m['series'])==c.size];short=[m['id'] for m in members if len(m['series'])!=c.size]
    if not used: return {'status':'BOOK_EMPTY','members':[],'length_mismatch':short}
    b=np.asarray([m['series'] for m in used],dtype=float);corr=[correlation(c,row) for row in b];known=[x for x in corr if x is not None]
    before=active_sharpe(b.mean(axis=0));after=active_sharpe((b.sum(axis=0)+c)/(len(used)+1))
    beta=np.linalg.lstsq(np.column_stack([np.ones(c.size),b.T]),c,rcond=None)[0]
    return {'status':'MEASURED','members':[{'id':m['id'],'kind':m['kind'],'sha256':m['sha256'],'correlation':r} for m,r in zip(used,corr)],'length_mismatch':short,
            'max_correlation':max(known) if known else None,'mean_correlation':float(np.mean(known)) if known else None,'book_sharpe':before,
            'combined_sharpe_gain':None if before is None or after is None else after-before,'residual_sharpe':active_sharpe(c-b.T@beta[1:])}


def contribution(ledger,project_root,market_sha256,market,series):
    try:
        members,skipped=book_members(ledger,project_root,market_sha256,market)
        record=book_measures(series,members) if members else {'status':'BOOK_EMPTY','members':[]}
        return clean({**record,'skipped':skipped[:20],'skipped_count':len(skipped)})
    except RuntimeRefused as error: return {'status':'UNDEFINED','reason':error.code}
    except Exception as error: return {'status':'UNDEFINED','reason':f'{type(error).__name__}: {str(error)[:200]}'}


def book_view(measures):
    """What the roles see of a candidate (decision D1, middle path): its largest correlation with the book and the combined Sharpe gain."""
    book=(measures or {}).get('book') or {}
    if book.get('status')!='MEASURED': return None
    def two(v): return None if v is None else round(v,2)
    return {'max_correlation':two(book.get('max_correlation')),'combined_sharpe_gain':two(book.get('combined_sharpe_gain'))}


def candidate_measures(*,project_root,candidate_id,signals,score,market=None,validation_rows=None,runs=(),ledger=None,market_sha256=None):
    """All measures of one scored candidate, and its contribution to the book when a ledger is given. Any failure gives status UNDEFINED
    with the reason; it never raises. A failed book gives book status UNDEFINED and keeps the other measures."""
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
        record=clean(record);record['series']=save_series(project_root,candidate_id,paths['base']);record['market_sha256']=market_sha256
        if ledger is not None: record['book']=contribution(ledger,project_root,market_sha256,market,paths['base'])
        return record
    except RuntimeRefused as error: return {'status':'UNDEFINED','reason':error.code}
    except Exception as error: return {'status':'UNDEFINED','reason':f'{type(error).__name__}: {str(error)[:200]}'}
