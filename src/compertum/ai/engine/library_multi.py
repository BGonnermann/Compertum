"""Multi-stock strategy library (owner, 1 November 2026): long-only portfolios chosen across many real history markets at once.

Each symbol is loaded with the engine's own history loader, so the vault is cut off before this module sees any row. A universe is the set of
symbols whose TRAIN and VALIDATION sessions match the common calendar exactly. Weights chosen at the close of session t earn the returns of t+1.
Every family uses only closes up to t. The benchmark is the equal-weight portfolio of the same universe, rebalanced daily at no cost.
Honest scoring (owner, 2 November 2026, fixes 1 to 3; see market.py): cash earns the daily risk-free rate; Sharpe ratios are above the rate;
the deflated Sharpe ratio tests active returns; turnover pays the era cost of market.cost_at per unit of weight traded. Weights drift with
returns between trades, so a trade back to target pays for the drift. A family trades only on its rebalance sessions: a session whose target
is the same object as the session before is held. beats_baseline also needs the same weights one session later to beat the benchmark.

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
import re
import sys
from uuid import uuid4
from compertum.data.errors import DataError
from compertum.runtime.errors import RuntimeRefused
from compertum.simulation.metrics import metrics
from .deflation import deflated_sharpe,moments,trial_variance
from .market import cost_at,dated,verdict

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
    rates=[float(x) for x in p['rates']] if 'rates' in p else [0.0]*n
    return {'symbols':list(symbols),'eligible':eligible,'closes':closes,'returns':returns,'ew':ew,'index':index,'n':n,'cache':{},
            'rates':rates,'costs':[float(cost_at(d)) for d in p['dates']],'dates':p['dates']}


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


def run_navs(u,targets,start,end,cost):
    """NAV paths over sessions start..end-1: weights chosen at t earn the returns of t+1, cash earns the rate of t+1, and a trade at t
    pays the cost of t for the weight changed against the drifted weights. Also the benchmark, both above the rate, and active returns."""
    one=Decimal(1);navs=[one];bench=[one];above=[one];bench_above=[one];active=[];nav=b=na=ba=1.0;held={};turnover_total=0.0
    for t in range(start,end-1):
        w=targets[t];rf=u['rates'][t+1];market=u['ew'][t+1]
        if t==start or w is not targets[t-1]:
            turnover=sum(abs(w.get(s,0.0)-held.get(s,0.0)) for s in set(w)|set(held));held=dict(w);turnover_total+=turnover
        else: turnover=0.0
        r={s:(u['returns'][s][t+1] or 0.0) for s in held}
        gross=sum(x*r[s] for s,x in held.items())+(1.0-sum(held.values()))*rf;step=gross-(u['costs'][t] if cost is None else cost)*turnover
        nav*=1+step;b*=1+market;na*=1+step-rf;ba*=1+market-rf;active.append(step-market)
        if min(nav,na,ba)<=0 or 1+gross<=0: raise RuntimeRefused('ENGINE_SIGNALS_INVALID')
        held={s:x*(1+r[s])/(1+gross) for s,x in held.items()}
        navs.append(Decimal(repr(nav)));bench.append(Decimal(repr(b)));above.append(Decimal(repr(na)));bench_above.append(Decimal(repr(ba)))
    return navs,bench,above,bench_above,active,turnover_total


def score(u,targets,start,end,cost=None,lag=True):
    """The score of weights over sessions start..end-1 against the equal-weight universe. cost None charges the era cost of each session."""
    def measure(chosen):
        navs,bench,above,bench_above,active,turnover=run_navs(u,chosen,start,end,cost)
        try: return metrics(navs,bench),metrics(above,bench_above),metrics(bench_above,bench_above),active,turnover
        except DataError as error: raise RuntimeRefused(error.reason) from None
    scored,sharpe,baseline,active,turnover=measure(targets);beats=verdict(scored,sharpe,baseline);lag_check=None
    if lag and all(dated(d) for d in u['dates'][start:end]):
        lagged=[{}]+list(targets[:-1]);lag_scored,lag_sharpe,_,_,_=measure(lagged);ok=verdict(lag_scored,lag_sharpe,baseline)
        lag_check={'sharpe':lag_sharpe['sharpe'],'annual_mean_excess':lag_scored['annual_mean_excess'],'beats':ok};beats=beats and ok
    held=sum(1 for t in range(start,end-1) if targets[t])
    return {'sessions':end-start,'sessions_invested':held,'sharpe':sharpe['sharpe'],'sharpe_status':sharpe['sharpe_status'],'benchmark_sharpe':baseline['sharpe'],
            'annual_mean_excess':scored['annual_mean_excess'],'max_drawdown':scored['max_drawdown'],'beats_baseline':bool(beats),'lag_check':lag_check,
            'turnover_per_year':format(Decimal(repr(turnover*252/max(end-start-1,1))).quantize(Decimal('0.0001')),'f'),
            'cash_rate':'session rate' if any(u['rates'][start:end]) else '0','cost_per_change':'by era (market.cost_at)' if cost is None else repr(cost),
            'deflation_inputs':moments([repr(a) for a in active])}


def _safe(u,targets,start,end,lag=True):
    try: return score(u,targets,start,end,lag=lag)
    except RuntimeRefused as error: return {'refused':error.code}


def choose(u,train):
    chosen={}
    for name,(_,grid) in FAMILIES.items():
        best=None
        for knobs in grid:
            s=_safe(u,weights(u,name,knobs),0,train,lag=False);value=Decimal(s['sharpe']) if s.get('sharpe_status')=='DEFINED' else None
            if best is None or (value is not None and (best[0] is None or value>best[0])): best=(value,knobs,s)
        chosen[name]={'knobs':best[1],'train_sharpe':None if best[0] is None else str(best[0]),'train_beats':bool(best[2].get('beats_baseline'))}
    return chosen


def universes(p):
    if 'eligible' in p:
        return {p.get('universe','sp500-pit'):sorted(p['closes'])} if p['eligible'] and min(len(e) for e in p['eligible'])>=MIN_UNIVERSE else {}
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
    admit_rows(p,ledger,run_id,groups,rows)
    return {'run_id':run_id,'kind':'strategy-library-multi','note':note,'calendar':[p['dates'][0],p['dates'][p['train']],p['dates'][-1]],
            'universes':{k:len(v) for k,v in groups.items()},'dropped':p['dropped'],'skipped':p.get('skipped',[]),'settings_per_universe':SETTINGS,'trials_recorded':trials,'total_trials':total,
            'membership':p.get('membership'),
            'gate_rule':'beats the equal-weight universe and deflated Sharpe >= 0.95 with the total trial count and the null variance (option C)','rows':rows}


def load_panel(root,manifests):
    from .history_market import build_market
    markets={};skipped=[]
    for path in manifests:
        try: market,_vault=build_market(root,path)
        except RuntimeRefused as error: skipped.append({'symbol':Path(path).parent.name,'code':error.code});continue
        markets[Path(path).parent.name]=(_rows(market['train_csv']),market['validation_rows'])
    from .french_market import rates_for
    p=panel(markets);p['skipped']=skipped;p['rates']=rates_for(root,p['dates'])
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


def french_panel(root,manifests,with_vault=False):
    """The 49 French industry portfolios on their own calendar: TRAIN before VALIDATION_START, VALIDATION before VAULT_START; vault rows are
    never loaded, except with_vault=True, which only the stage-2 vault scorer passes inside a counted look. An industry is eligible on a
    session when it has a close; it joins on the day after its last missing value."""
    from .french_market import VALIDATION_START,VAULT_START,load_french,rates_for
    series={};skipped=[]
    for path in manifests:
        try: history=load_french(root,path)
        except RuntimeRefused as error: skipped.append({'symbol':Path(path).parent.name,'code':error.code});continue
        if history['symbol'] not in ('Mkt','RF'): series[history['symbol']]=dict(history['closes'])
    dates=sorted({d for c in series.values() for d in c if with_vault or d<VAULT_START})
    if not dates: raise RuntimeRefused('ENGINE_MARKET_DENIED')
    closes={s:[float(c[d]) if d in c else None for d in dates] for s,c in series.items()}
    eligible=[[s for s in sorted(closes) if closes[s][t] is not None] for t in range(len(dates))]
    return {'dates':dates,'train':sum(1 for d in dates if d<VALIDATION_START),'closes':closes,'eligible':eligible,'dropped':[],'skipped':skipped,'rates':rates_for(root,dates),
            'universe':'french49','vault':'french-v1','membership':{'source':'Kenneth French Data Library, 49 industry portfolios, value weighted, daily','industries':len(closes),
            'validation_start':VALIDATION_START,'vault_start':VAULT_START,'smallest_universe':min(len(e) for e in eligible)}}


PERTURB=(1,4,8)
ROUTES=frozenset({'french49'})


def causal(p,members,family,knobs):
    """The Auditor's lookahead check for a portfolio rule: changing the closes of the last k sessions leaves every earlier weight unchanged.
    Each symbol gets its own factor, so rankings across symbols change too, not only the level."""
    n=len(p['dates']);base=weights(prepare(p,members),family,knobs)
    def factor(j,t): return (0.85+0.3*((j*7)%11)/10)*(1-0.01*(t-n+k))
    for k in PERTURB:
        if not 1<=k<n-p['train']-1: return False
        q={**p,'closes':{s:[c if c is None or t<n-k else c*factor(j,t) for t,c in enumerate(closes)] for j,(s,closes) in enumerate(sorted(p['closes'].items()))}}
        if weights(prepare(q,members),family,knobs)[:n-k]!=base[:n-k]: return False
    return True


def admit_rows(p,ledger,run_id,groups,rows):
    """Stage 1 for portfolio rules: a setting that beat the equal-weight universe is ELIGIBLE when a recompute gives the same score and the
    lookahead check passes. Only universes with a vault scorer (ROUTES) are admitted."""
    from .vault import CandidateQueue
    queue=CandidateQueue(ledger)
    for row in rows:
        if not (row.get('validation') or {}).get('beats_baseline'): continue
        if row['universe'] not in ROUTES: row['queue']={'event':'NOT_ADMITTED','reason':'no vault scorer for this universe'};continue
        members=groups[row['universe']];u=prepare(p,members)
        full=_safe(u,weights(u,row['family'],row['knobs']),p['train'],u['n'])
        again=_safe(prepare(p,members),weights(prepare(p,members),row['family'],row['knobs']),p['train'],u['n'])
        row['recomputed']=full==again;row['causal']=causal(p,members,row['family'],row['knobs'])
        if not (row['recomputed'] and row['causal']): row['queue']={'event':'NOT_ADMITTED','reason':'recompute or lookahead check failed'};continue
        inputs=full['deflation_inputs'];deflation=deflated_sharpe(inputs,ledger.total_trials(),trial_variance([],inputs)['trial_variance'])
        route={'kind':'library-multi','run_id':run_id,'universe':row['universe'],'family':row['family'],'knobs':row['knobs'],'members':len(members),
               'checks':'recompute and lookahead (closes of the last 1, 4 and 8 sessions changed); no sandbox Auditor run'}
        event=queue.admit(f"{run_id}:{row['universe']}:{row['family']}",full,deflation,tests_passed=True,auditor_passed=True,route=route,vault=p.get('vault','history-v1'))
        row['queue']={'event':event['event'],'quarter':event['quarter'],'candidate_id':event['candidate_id']}
    return rows


def admit_report(report,p,ledger):
    """Stage 1 for a sweep that ran before the route existed: every row must reproduce its recorded VALIDATION score from the same files.
    No trial is recorded again; the sweep's trials are already in the ledger."""
    if report.get('kind')!='strategy-library-multi' or not isinstance(report.get('rows'),list): raise RuntimeRefused('ENGINE_QUEUE_DENIED')
    groups=universes(p)
    if set(report.get('universes') or {})!=set(groups) or any(len(groups[k])!=v for k,v in report['universes'].items()): raise RuntimeRefused('ENGINE_QUEUE_DENIED')
    rows=[dict(r) for r in report['rows'] if isinstance(r,dict) and r.get('universe') in groups and r.get('family') in FAMILIES]
    for row in rows:
        u=prepare(p,groups[row['universe']]);again=_safe(u,weights(u,row['family'],row['knobs']),p['train'],u['n']);again.pop('deflation_inputs',None)
        if again!=row.get('validation'): raise RuntimeRefused('ENGINE_QUEUE_DENIED')
    return admit_rows(p,ledger,report['run_id'],groups,rows)


def vault_score(queue,look_id,candidate_id,root,manifests):
    """Stage 2 for a french49 portfolio rule: the admitted rule must reproduce its VALIDATION score from the same files; then, inside the
    counted look, the rule runs over the whole history and only the vault sessions are scored against the equal-weight industries."""
    import hashlib
    from compertum.events import canonical
    _,_,eligible=queue._fold(candidate_id);route=(eligible or {}).get('route') or {}
    if route.get('kind')!='library-multi' or route.get('universe')!='french49' or route.get('family') not in FAMILIES: raise RuntimeRefused('ENGINE_VAULT_DENIED')
    family,knobs=route['family'],route['knobs']
    p=french_panel(root,manifests);members=sorted(p['closes']);u=prepare(p,members)
    if len(members)!=route.get('members') or hashlib.sha256(canonical(_safe(u,weights(u,family,knobs),p['train'],u['n']))).hexdigest()!=eligible.get('score_sha256'):
        raise RuntimeRefused('ENGINE_VAULT_DENIED')
    def read():
        full=french_panel(root,manifests,with_vault=True);start=len(p['dates'])
        if full['dates'][:start]!=p['dates'] or sorted(full['closes'])!=members: raise RuntimeRefused('ENGINE_VAULT_DENIED')
        return full,start
    def scored(produced):
        full,start=produced;w=prepare(full,members);return score(w,weights(w,family,knobs),start,w['n'])
    return queue.evaluate_in_vault(look_id,candidate_id,None,read,vault='french-v1',score=scored)


def pit_panel(root,manifests,membership='data/indices/sp500/history.json',reference='SPY',periods_path='data/indices/sp500/periods.json'):
    import bisect
    import hashlib
    from compertum.domain import ContractError,resolve_project_path
    from .history_market import load_history,build_market
    paths={Path(m).parent.name:m for m in manifests}
    if reference not in paths: raise RuntimeRefused('ENGINE_MARKET_DENIED')
    market,_vault=build_market(root,paths[reference]);train_rows=_rows(market['train_csv'])
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
    from .french_market import rates_for
    return {'dates':dates,'train':len(train_rows),'closes':closes,'eligible':eligible,'dropped':[],'skipped':skipped,'rates':rates_for(root,dates),
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
    run.add_argument('--universe',choices=('all','sp500-pit','french49'),default='all')
    admit=commands.add_parser('admit');admit.add_argument('--run',required=True)
    vault=commands.add_parser('vault');vault.add_argument('--look',required=True);vault.add_argument('--candidate',required=True)
    args=parser.parse_args(argv)
    root=args.project.resolve();config=args.config if args.config.is_absolute() else root/args.config
    if args.command in ('admit','vault'): return queue_command(args,root,config)
    folder='french' if args.universe=='french49' else 'history'
    manifests=[p.relative_to(root).as_posix() for p in sorted((root/'data'/folder).glob('*/manifest.json'))]
    if not manifests or not args.note.strip() or len(args.note)>NOTE_LIMIT: print(json.dumps({'refused':'ENGINE_RUN_LIMITS_DENIED'}));return 2
    from compertum.config import ConfigError,load_config
    from compertum.domain import ContractError
    from compertum.runtime.identity import resolve_project
    from compertum.runtime.owners import acquire_owner,release_owner
    from compertum.storage import StorageManager
    from .ledger import EngineLedger
    lease=None;run_id=f'library-multi-{datetime.now(timezone.utc):%Y%m%d}-{uuid4().hex[:8]}'
    try:
        p=pit_panel(root,manifests) if args.universe=='sp500-pit' else french_panel(root,manifests) if args.universe=='french49' else load_panel(root,manifests)
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


def queue_command(args,root,config):
    from compertum.config import ConfigError,load_config
    from compertum.domain import ContractError
    from compertum.runtime.identity import resolve_project
    from compertum.runtime.owners import acquire_owner,release_owner
    from compertum.storage import StorageManager
    from .ledger import EngineLedger
    from .vault import CandidateQueue
    french=[q.relative_to(root).as_posix() for q in sorted((root/'data'/'french').glob('*/manifest.json'))];lease=None
    try:
        lease=acquire_owner(resolve_project(root),'coordinator');ledger=EngineLedger(StorageManager(lease,load_config(config,root)).store)
        if args.command=='admit':
            if not re.fullmatch(r'library-multi-[0-9]{8}-[0-9a-f]{8}',args.run): raise RuntimeRefused('ENGINE_QUEUE_DENIED')
            report=json.loads((root/'state'/'engine'/'library'/f'{args.run}.json').read_text(encoding='utf-8'))
            if report.get('universes')!={'french49':49}: raise RuntimeRefused('ENGINE_QUEUE_DENIED')
            rows=admit_report(report,french_panel(root,french),ledger)
            result={'admitted':[r['queue'] for r in rows if r.get('queue')]}
        else:
            event=vault_score(CandidateQueue(ledger),args.look,args.candidate,root,french)
            result={'candidate':args.candidate,'status':event['status'],'confirmation':event.get('confirmation')}
    except RuntimeRefused as error:
        print(json.dumps({'refused':error.code}));return 2
    except (ContractError,ConfigError,OSError,ValueError) as error:
        print(json.dumps({'refused':getattr(error,'reason',None) or type(error).__name__}));return 2
    finally:
        if lease is not None: release_owner(lease)
    print(json.dumps(result,sort_keys=True,default=str));return 0


if __name__=='__main__': sys.exit(main())
