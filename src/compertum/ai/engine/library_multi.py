"""Multi-stock strategy library (owner, 1 November 2026): long-only portfolios chosen across many real history markets at once.

Each symbol is loaded with the engine's own history loader, so the vault is cut off before this module sees any row. A universe is the set of
symbols whose TRAIN and VALIDATION sessions match the common calendar exactly. Weights chosen at the close of session t earn the returns of t+1.
Every family uses only closes up to t. Turnover costs 0.0005 of NAV per unit of weight changed, the single-market cost.
The benchmark is the equal-weight portfolio of the same universe, rebalanced daily at no cost.

The point-in-time universe sp500-pit (owner, 1 November 2026) holds on each session only the S&P 500 members of that date
(data/indices/sp500/history.json, from tools/update_indices.py) that have a close that day, including members that later left.
Its calendar and its TRAIN and VALIDATION sessions are those of SPY; every row after SPY's last VALIDATION session is dropped on load.
A held stock without a close on the next session earns 0 for that session. A ticker that two companies used is split by date with
data/indices/sp500/periods.json, so each company keeps its own history (DOW-2017 for Dow Chemical, DOW for Dow Inc).
Knobs are chosen on TRAIN only; the chosen setting of each family is scored once on VALIDATION. Every setting tried counts as a trial,
recorded in the ledger before the first VALIDATION score. The gate is the real gate (option C).

    python -m compertum.ai.engine.library_multi --project . sweep --note "why"
"""
import argparse
from collections import Counter
from datetime import datetime,timezone
from decimal import Decimal
import json
import math
from pathlib import Path
import sys
from uuid import uuid4
from compertum.data.errors import DataError
from compertum.runtime.errors import RuntimeRefused
from compertum.simulation.metrics import metrics
from .deflation import deflated_sharpe,moments,trial_variance
from .market import COST

NOTE_LIMIT=500
MIN_UNIVERSE=10
ETFS=frozenset({'AGG','DIA','EEM','EFA','EMB','EWJ','EWZ','FXI','GDX','GLD','HYG','IBB','IEF','IWM','JNK','KRE','LQD','QQQ','SHY','SLV','SMH','SPY',
                'TIP','TLT','USO','VEA','VNQ','VWO','XBI','XHB','XLB','XLE','XLF','XLI','XLK','XLP','XLRE','XLU','XLV','XLY','XRT'})


def panel(markets):
    """markets: {symbol: (train_rows, validation_rows)}. Returns the common calendar and closes, and the symbols left out."""
    calendars=Counter(tuple(r['session'] for r in t+v) for t,v in markets.values())
    if not calendars: raise RuntimeRefused('ENGINE_MARKET_DENIED')
    calendar=calendars.most_common(1)[0][0];keep={};dropped=[]
    for symbol,(train,validation) in sorted(markets.items()):
        if tuple(r['session'] for r in train+validation)!=calendar: dropped.append(symbol);continue
        keep[symbol]=[float(r['close']) for r in train+validation]
    first=next(len(t) for t,v in markets.values() if tuple(r['session'] for r in t+v)==calendar)
    return {'dates':list(calendar),'train':first,'closes':keep,'dropped':dropped}


def _returns(closes):
    return [0.0]+[None if closes[t] is None or closes[t-1] is None else closes[t]/closes[t-1]-1 for t in range(1,len(closes))]


def prepare(p,symbols):
    closes={s:p['closes'][s] for s in symbols};returns={s:_returns(c) for s,c in closes.items()};n=len(p['dates'])
    if 'eligible' in p:
        chosen=set(symbols);eligible=[[s for s in e if s in chosen] for e in p['eligible']]
        ew=[0.0]+[sum(returns[s][t] or 0.0 for s in eligible[t-1])/len(eligible[t-1]) if eligible[t-1] else 0.0 for t in range(1,n)]
    else:
        eligible=[list(symbols)]*n;ew=[sum(returns[s][t] for s in symbols)/len(symbols) for t in range(n)]
    index=[1.0]
    for t in range(1,n): index.append(index[-1]*(1+ew[t]))
    return {'symbols':list(symbols),'eligible':eligible,'closes':closes,'returns':returns,'ew':ew,'index':index,'n':n,'cache':{}}


def _past_return(u,s,t,lookback,skip=0):
    c=u['closes'][s];a=t-skip;b=a-lookback
    return None if b<0 or c[a] is None or c[b] is None else c[a]/c[b]-1


def _vol(u,s,t,window):
    key=('vol',s,window)
    if key not in u['cache']:
        r=u['returns'][s];out=[None]*u['n'];acc=0.0;acc2=0.0;gaps=0
        for i in range(1,u['n']):
            if r[i] is None: gaps+=1
            else: acc+=r[i];acc2+=r[i]*r[i]
            if i>window:
                if r[i-window] is None: gaps-=1
                else: acc-=r[i-window];acc2-=r[i-window]*r[i-window]
            if i>=window and not gaps: mean=acc/window;out[i]=math.sqrt(max(acc2/window-mean*mean,0.0)*window/(window-1))
        u['cache'][key]=out
    return u['cache'][key][t]


def _above_ma(u,s,t,window):
    key=('ma',s,window)
    if key not in u['cache']:
        c=u['closes'][s];out=[None]*u['n'];acc=0.0;gaps=0
        for i in range(u['n']):
            if c[i] is None: gaps+=1
            else: acc+=c[i]
            if i>=window:
                if c[i-window] is None: gaps-=1
                else: acc-=c[i-window]
            if i+1>=window and not gaps: out[i]=c[i]>acc/window
        u['cache'][key]=out
    return u['cache'][key][t]


def _top(scores,share,highest=True):
    known=[(v,s) for s,v in scores.items() if v is not None]
    if not known: return {}
    known.sort(key=lambda x:(-x[0] if highest else x[0],x[1]));k=max(1,math.ceil(share*len(known)))
    chosen=[s for _,s in known[:k]];return {s:1.0/len(chosen) for s in chosen}


def _equal(u,t):
    names=u['eligible'][t]
    return {s:1.0/len(names) for s in names}


def xs_momentum(u,t,lookback,skip,share):
    return _top({s:_past_return(u,s,t,lookback,skip) for s in u['eligible'][t]},share)


def xs_reversal(u,t,lookback,share):
    return _top({s:_past_return(u,s,t,lookback) for s in u['eligible'][t]},share,highest=False)


def xs_lowvol(u,t,window,share):
    return _top({s:_vol(u,s,t,window) for s in u['eligible'][t]},share,highest=False)


def dual_momentum(u,t,lookback,share):
    scores={s:_past_return(u,s,t,lookback) for s in u['eligible'][t]}
    return _top({s:v for s,v in scores.items() if v is not None and v>0},share) if any(v is not None and v>0 for v in scores.values()) else {}


def ew_trend(u,t,window):
    if t+1<window: return {}
    return _equal(u,t) if u['index'][t]>sum(u['index'][t-window+1:t+1])/window else {}


def breadth(u,t,window,level):
    flags=[_above_ma(u,s,t,window) for s in u['eligible'][t]];known=[f for f in flags if f is not None]
    return _equal(u,t) if known and sum(known)/len(known)>level else {}


FAMILIES={
    'xs_momentum':(xs_momentum,[{'lookback':l,'skip':k,'share':q,'hold':h} for l in (20,60,120,252) for k in (0,20) for q in (0.1,0.2) for h in (5,21)]),
    'xs_reversal':(xs_reversal,[{'lookback':l,'share':q,'hold':h} for l in (1,5,10,20) for q in (0.1,0.2) for h in (1,5)]),
    'xs_low_vol':(xs_lowvol,[{'window':w,'share':q,'hold':h} for w in (20,60,120) for q in (0.1,0.2) for h in (5,21)]),
    'dual_momentum':(dual_momentum,[{'lookback':l,'share':q,'hold':21} for l in (60,120,252) for q in (0.1,0.2)]),
    'ew_trend':(ew_trend,[{'window':w,'hold':1} for w in (50,100,200)]),
    'breadth':(breadth,[{'window':w,'level':b,'hold':1} for w in (50,200) for b in (0.4,0.5,0.6)]),
}
SETTINGS=sum(len(grid) for _,grid in FAMILIES.values())


def weights(u,name,knobs):
    """Target weights for every session; a family's weights change only on rebalance sessions (t a multiple of hold)."""
    rule,_=FAMILIES[name];args={k:v for k,v in knobs.items() if k!='hold'};hold=knobs['hold'];out=[];current={}
    for t in range(u['n']):
        if t%hold==0: current=rule(u,t,**args)
        out.append(current)
    return out


def score(u,targets,start,end,cost=float(COST)):
    """NAV over sessions start..end-1: weights chosen at t earn the returns of t+1, minus cost for the weight changed at t."""
    navs=[Decimal(1)];bench=[Decimal(1)];nav=1.0;b=1.0;previous={}
    for t in range(start,end-1):
        w=targets[t];turnover=sum(abs(w.get(s,0.0)-previous.get(s,0.0)) for s in set(w)|set(previous));previous=w
        gross=sum(weight*(u['returns'][s][t+1] or 0.0) for s,weight in w.items())
        nav*=1+gross-cost*turnover;b*=1+u['ew'][t+1]
        if nav<=0: raise RuntimeRefused('ENGINE_SIGNALS_INVALID')
        navs.append(Decimal(repr(nav)));bench.append(Decimal(repr(b)))
    try: scored=metrics(navs,bench);baseline=metrics(bench,bench)
    except DataError as error: raise RuntimeRefused(error.reason) from None
    excess=Decimal(scored['annual_mean_excess']) if scored['annual_mean_excess'] is not None else None
    sharpe=Decimal(scored['sharpe']) if scored['sharpe'] is not None else None
    base=Decimal(baseline['sharpe']) if baseline['sharpe'] is not None else None
    beats=scored['sharpe_status']=='DEFINED' and excess is not None and excess>0 and (base is None or (sharpe is not None and sharpe>base))
    held=sum(1 for t in range(start,end-1) if targets[t])
    return {'sessions':end-start,'sessions_invested':held,'sharpe':scored['sharpe'],'sharpe_status':scored['sharpe_status'],'benchmark_sharpe':baseline['sharpe'],
            'annual_mean_excess':scored['annual_mean_excess'],'max_drawdown':scored['max_drawdown'],'beats_baseline':bool(beats),
            'deflation_inputs':moments(scored['returns'])}


def _safe(u,targets,start,end):
    try: return score(u,targets,start,end)
    except RuntimeRefused as error: return {'refused':error.code}


def choose(u,train):
    chosen={}
    for name,(_,grid) in FAMILIES.items():
        best=None
        for knobs in grid:
            s=_safe(u,weights(u,name,knobs),0,train);value=Decimal(s['sharpe']) if s.get('sharpe_status')=='DEFINED' else None
            if best is None or (value is not None and (best[0] is None or value>best[0])): best=(value,knobs,s)
        chosen[name]={'knobs':best[1],'train_sharpe':None if best[0] is None else str(best[0]),'train_beats':bool(best[2].get('beats_baseline'))}
    return chosen


def universes(p):
    if 'eligible' in p:
        return {'sp500-pit':sorted(p['closes'])} if p['eligible'] and min(len(e) for e in p['eligible'])>=MIN_UNIVERSE else {}
    stocks=[s for s in p['closes'] if s not in ETFS];etfs=[s for s in p['closes'] if s in ETFS]
    return {name:members for name,members in (('stocks',stocks),('etfs',etfs)) if len(members)>=MIN_UNIVERSE}


def sweep(p,ledger,*,run_id,note):
    groups=universes(p)
    if not groups: raise RuntimeRefused('ENGINE_MARKET_DENIED')
    ledger.require_unfrozen()
    prepared={name:prepare(p,members) for name,members in groups.items()};choices={name:choose(u,p['train']) for name,u in prepared.items()}
    trials=SETTINGS*len(groups)
    ledger.record_external_trials(f'library-multi:{run_id}',trials,{'kind':'strategy-library-multi','run_id':run_id,'settings_per_universe':SETTINGS,
                                                                    'universes':{k:len(v) for k,v in groups.items()},'families':sorted(FAMILIES),'note':note})
    total=ledger.total_trials();rows=[]
    for name,u in prepared.items():
        for family,choice in choices[name].items():
            s=_safe(u,weights(u,family,choice['knobs']),p['train'],u['n']);row={'universe':name,'family':family,**choice}
            if 'refused' in s: row.update(validation=s,gate='UNDEFINED');rows.append(row);continue
            inputs=s.pop('deflation_inputs');deflation=deflated_sharpe(inputs,total,trial_variance([],inputs)['trial_variance'])
            row.update(validation=s,deflated_sharpe=deflation['deflated_sharpe'],gate='PASS' if s['beats_baseline'] and deflation['status']=='PASS' else 'FAIL')
            rows.append(row)
    return {'run_id':run_id,'kind':'strategy-library-multi','note':note,'calendar':[p['dates'][0],p['dates'][p['train']],p['dates'][-1]],
            'universes':{k:len(v) for k,v in groups.items()},'dropped':p['dropped'],'skipped':p.get('skipped',[]),'settings_per_universe':SETTINGS,'trials_recorded':trials,'total_trials':total,
            'membership':p.get('membership'),
            'gate_rule':'beats the equal-weight universe and deflated Sharpe >= 0.95 with the total trial count and the null variance (option C)','rows':rows}


def load_panel(root,manifests):
    from .history_market import load_history_market
    markets={};skipped=[]
    for path in manifests:
        try: market,_vault=load_history_market(root,path)
        except RuntimeRefused as error: skipped.append({'symbol':Path(path).parent.name,'code':error.code});continue
        markets[Path(path).parent.name]=(_rows(market['train_csv']),market['validation_rows'])
    p=panel(markets);p['skipped']=skipped
    return p


def _periods(value):
    if not isinstance(value,dict): raise RuntimeRefused('ENGINE_MARKET_INPUT_UNAVAILABLE')
    for ticker,items in value.items():
        if not isinstance(ticker,str) or not isinstance(items,list) or not items: raise RuntimeRefused('ENGINE_MARKET_INPUT_UNAVAILABLE')
        for p in items:
            if not isinstance(p,dict) or not isinstance(p.get('key'),str) or any(not isinstance(p.get(k),(str,type(None))) for k in ('since','until','last','data_since')):
                raise RuntimeRefused('ENGINE_MARKET_INPUT_UNAVAILABLE')
    return value


def _window(key,periods):
    for items in periods.values():
        for p in items:
            if p['key']==key: return p.get('data_since') or p.get('since'),p.get('last'),p.get('until')
    return None,None,None


def resolve_member(ticker,day,periods):
    for p in periods.get(ticker,()):
        if (p.get('since') is None or day>=p['since']) and (p.get('until') is None or day<p['until']): return p['key']
    return None if ticker in periods else ticker


def pit_panel(root,manifests,membership='data/indices/sp500/history.json',reference='SPY',periods_path='data/indices/sp500/periods.json'):
    import bisect
    import hashlib
    from compertum.domain import ContractError,resolve_project_path
    from .history_market import load_history,load_history_market
    paths={Path(m).parent.name:m for m in manifests}
    if reference not in paths: raise RuntimeRefused('ENGINE_MARKET_DENIED')
    market,_vault=load_history_market(root,paths[reference]);train_rows=_rows(market['train_csv'])
    dates=[r['session'] for r in train_rows+market['validation_rows']];n=len(dates);where={d:i for i,d in enumerate(dates)}
    try: raw=resolve_project_path(membership,Path(root).absolute()).read_bytes()
    except (ContractError,OSError): raise RuntimeRefused('ENGINE_MARKET_INPUT_UNAVAILABLE') from None
    history=json.loads(raw);days=history['dates']
    if days[0]>dates[0] or history['last']<dates[-1]: raise RuntimeRefused('ENGINE_MARKET_COVERAGE_INCOMPLETE')
    try: periods=_periods(json.loads(resolve_project_path(periods_path,Path(root).absolute()).read_bytes())['periods'])
    except (ContractError,OSError,ValueError,KeyError,TypeError): raise RuntimeRefused('ENGINE_MARKET_INPUT_UNAVAILABLE') from None
    members=[frozenset(k for k in (resolve_member(t,d,periods) for t in history['members'][bisect.bisect_right(days,d)-1]) if k) for d in dates]
    names=set().union(*members)
    closes={};skipped=[]
    for symbol in sorted(names):
        if symbol not in paths: continue
        try: h=load_history(root,paths[symbol])
        except RuntimeRefused as error: skipped.append({'symbol':symbol,'code':error.code});continue
        c=[None]*n;first,last,until=_window(symbol,periods)
        for day,close in h['closes']:
            if day in where and (first is None or day>=first) and (last is None or day<=last) and (until is None or day<until): c[where[day]]=float(close)
        if sum(x is not None for x in c)>=2: closes[symbol]=c
    eligible=[[s for s in sorted(members[t]) if s in closes and closes[s][t] is not None] for t in range(n)]
    shares=[len(eligible[t])/len(members[t]) for t in range(n)]
    return {'dates':dates,'train':len(train_rows),'closes':closes,'eligible':eligible,'dropped':[],'skipped':skipped,
            'membership':{'path':membership,'sha256':hashlib.sha256(raw).hexdigest(),'periods':periods,'members_in_window':len(names),
                          'with_history':len(closes),'missing':sorted(names-set(closes)-{x['symbol'] for x in skipped}),
                          'coverage_min':round(min(shares),4),'coverage_mean':round(sum(shares)/n,4),'reference':reference}}


def _rows(text):
    import csv,io
    return list(csv.DictReader(io.StringIO(text)))


def main(argv=None):
    parser=argparse.ArgumentParser(prog='compertum.ai.engine.library_multi',description='Sweep the multi-stock library over every real history market.')
    parser.add_argument('--project',type=Path,default=Path('.'));parser.add_argument('--config',type=Path,default=Path('config/default.toml'))
    commands=parser.add_subparsers(dest='command',required=True);run=commands.add_parser('sweep');run.add_argument('--note',required=True)
    run.add_argument('--universe',choices=('all','sp500-pit'),default='all')
    args=parser.parse_args(argv)
    root=args.project.resolve();config=args.config if args.config.is_absolute() else root/args.config
    manifests=[p.relative_to(root).as_posix() for p in sorted((root/'data'/'history').glob('*/manifest.json'))]
    if not manifests or not args.note.strip() or len(args.note)>NOTE_LIMIT: print(json.dumps({'refused':'ENGINE_RUN_LIMITS_DENIED'}));return 2
    from compertum.config import ConfigError,load_config
    from compertum.domain import ContractError
    from compertum.runtime.identity import resolve_project
    from compertum.runtime.owners import acquire_owner,release_owner
    from compertum.storage import StorageManager
    from .ledger import EngineLedger
    lease=None;run_id=f'library-multi-{datetime.now(timezone.utc):%Y%m%d}-{uuid4().hex[:8]}'
    try:
        p=pit_panel(root,manifests) if args.universe=='sp500-pit' else load_panel(root,manifests)
        lease=acquire_owner(resolve_project(root),'coordinator')
        store=StorageManager(lease,load_config(config,root)).store
        report=sweep(p,EngineLedger(store),run_id=run_id,note=args.note)
    except RuntimeRefused as error:
        print(json.dumps({'refused':error.code}));return 2
    except (ContractError,ConfigError) as error:
        print(json.dumps({'refused':getattr(error,'reason',None) or type(error).__name__}));return 2
    finally:
        if lease is not None: release_owner(lease)
    folder=root/'state'/'engine'/'library';folder.mkdir(parents=True,exist_ok=True)
    path=folder/f'{run_id}.json';path.write_text(json.dumps(report,indent=1,sort_keys=True),encoding='utf-8',newline='\n')
    print(json.dumps({'run_id':run_id,'report':str(path),'universes':report['universes'],'dropped':len(report['dropped']),'skipped':report['skipped'],'trials_recorded':report['trials_recorded'],
                      'membership':{k:v for k,v in (report['membership'] or {}).items() if k!='missing'} or None,
                      'total_trials':report['total_trials'],'rows':[{k:r.get(k) for k in ('universe','family','knobs','deflated_sharpe','gate')}|
                      {'sharpe':r['validation'].get('sharpe'),'benchmark_sharpe':r['validation'].get('benchmark_sharpe'),'beats':r['validation'].get('beats_baseline')}
                      for r in report['rows']]},sort_keys=True))
    return 0


if __name__=='__main__': sys.exit(main())
