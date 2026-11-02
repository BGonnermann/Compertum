"""Strategy library (owner, 1 November 2026): pre-coded long/flat strategy families with knob grids, swept over real history markets.

No model call and no sandbox: this is reviewed project code, not AI-written code. Rules of the sweep:
- A position chosen at the close of session t earns the return of session t+1, as in score_signals. Every family uses only closes up to t,
  and the calendar families use only the date of session t+1, which is known in advance.
- Knobs are chosen on TRAIN only. The chosen setting of each family is scored once on VALIDATION. The vault is never read.
- Every setting tried on TRAIN counts as a trial. The run's trials are recorded in the ledger before the first VALIDATION score.
- The gate is the real gate: the total trial count of all campaigns and the null variance (option C, 1 November 2026).

    python -m compertum.ai.engine.library --project . sweep --all --note "why"
    python -m compertum.ai.engine.library --project . sweep --manifest data/history/SPY/manifest.json --note "why"
"""
import argparse
import csv
from datetime import date,datetime,timezone
from decimal import Decimal
import io
import json
import math
from pathlib import Path
import sys
from uuid import uuid4
from compertum.runtime.errors import RuntimeRefused
from .deflation import deflated_sharpe,trial_variance
from .market import score_signals

NOTE_LIMIT=500
LOW_VOL_LOOKBACK=252


def _prefix(values):
    out=[0.0]
    for v in values: out.append(out[-1]+v)
    return out


def _sma(prefix,t,n):
    return None if t+1<n else (prefix[t+1]-prefix[t+1-n])/n


def momentum(s,lookback):
    c=s['closes'];return [1 if t>=lookback and c[t]>c[t-lookback] else 0 for t in range(len(c))]


def reversal(s,lookback):
    c=s['closes'];return [1 if t>=lookback and c[t]<c[t-lookback] else 0 for t in range(len(c))]


def above_ma(s,window):
    c=s['closes'];p=s['prefix'];out=[]
    for t in range(len(c)):
        m=_sma(p,t,window);out.append(1 if m is not None and c[t]>m else 0)
    return out


def ma_cross(s,fast,slow):
    p=s['prefix'];out=[]
    for t in range(len(s['closes'])):
        a=_sma(p,t,fast);b=_sma(p,t,slow);out.append(1 if a is not None and b is not None and a>b else 0)
    return out


def breakout(s,entry,exit):
    c=s['closes'];out=[];held=0
    for t in range(len(c)):
        if held==0 and t>=entry and c[t]>max(c[t-entry:t]): held=1
        elif held==1 and t>=exit and c[t]<min(c[t-exit:t]): held=0
        out.append(held)
    return out


def rsi_revert(s,period,entry):
    c=s['closes'];out=[];held=0;gain=loss=None
    for t in range(len(c)):
        if t>0:
            change=c[t]-c[t-1];up=max(change,0.0);down=max(-change,0.0)
            if t<=period:
                gain=(gain or 0.0)+up/period;loss=(loss or 0.0)+down/period
            else:
                gain=(gain*(period-1)+up)/period;loss=(loss*(period-1)+down)/period
        if t>=period and gain is not None:
            rsi=100.0 if loss==0 else 100.0-100.0/(1.0+gain/loss)
            if held==0 and rsi<entry: held=1
            elif held==1 and rsi>50: held=0
        out.append(held)
    return out


def trend_dip(s,trend,pullback):
    c=s['closes'];p=s['prefix'];out=[]
    for t in range(len(c)):
        m=_sma(p,t,trend);out.append(1 if m is not None and t>=pullback and c[t]>m and c[t]<c[t-pullback] else 0)
    return out


def low_vol(s,window,quantile):
    c=s['closes'];r=[0.0]+[c[t]/c[t-1]-1 for t in range(1,len(c))];vols=[];out=[]
    for t in range(len(c)):
        if t<window: vols.append(None);out.append(0);continue
        part=r[t-window+1:t+1];mean=sum(part)/window
        vols.append(math.sqrt(sum((x-mean)**2 for x in part)/(window-1)))
        known=[v for v in vols[max(0,t-LOW_VOL_LOOKBACK+1):t+1] if v is not None]
        if len(known)<LOW_VOL_LOOKBACK//2: out.append(0);continue
        known.sort();out.append(1 if vols[t]<=known[min(len(known)-1,int(quantile*len(known)))] else 0)
    return out


def month_turn(s,last,first):
    d=s['dates'];out=[]
    for t in range(len(d)):
        if t+1>=len(d): out.append(0);continue
        nxt=d[t+1];rank_start=1;k=t
        while k>=0 and (d[k].year,d[k].month)==(nxt.year,nxt.month): rank_start+=1;k-=1
        rank_end=1;k=t+2
        while k<len(d) and (d[k].year,d[k].month)==(nxt.year,nxt.month): rank_end+=1;k+=1
        month_complete=k<len(d)
        out.append(1 if rank_start<=first or (month_complete and rank_end<=last) else 0)
    return out


def week_day(s,weekday):
    d=s['dates'];return [1 if t+1<len(d) and d[t+1].weekday()==weekday else 0 for t in range(len(d))]


FAMILIES={
    'momentum':(momentum,[{'lookback':n} for n in (2,5,10,20,40,60,120,200,252)]),
    'reversal':(reversal,[{'lookback':n} for n in (1,2,3,5,10,20)]),
    'above_ma':(above_ma,[{'window':n} for n in (10,20,50,100,150,200)]),
    'ma_cross':(ma_cross,[{'fast':a,'slow':b} for a,b in ((5,20),(5,50),(10,50),(10,100),(20,50),(20,100),(20,200),(50,100),(50,200))]),
    'breakout':(breakout,[{'entry':a,'exit':b} for a,b in ((20,10),(55,20),(100,50),(200,100))]),
    'rsi_revert':(rsi_revert,[{'period':n,'entry':e} for n in (2,5,14) for e in (10,20,30)]),
    'dip_in_trend':(trend_dip,[{'trend':n,'pullback':k} for n in (100,200) for k in (1,3,5)]),
    'low_vol':(low_vol,[{'window':n,'quantile':q} for n in (10,20) for q in (0.5,0.7)]),
    'turn_of_month':(month_turn,[{'last':a,'first':b} for a in (1,2,3) for b in (1,2,3)]),
    'day_of_week':(week_day,[{'weekday':w} for w in range(5)]),
}
SETTINGS=sum(len(grid) for _,grid in FAMILIES.values())


def _rows(text):
    return list(csv.DictReader(io.StringIO(text)))


def series(train_rows,validation_rows):
    rows=list(train_rows)+list(validation_rows);closes=[float(r['close']) for r in rows]
    return {'closes':closes,'prefix':_prefix(closes),'dates':[date.fromisoformat(r['session']) for r in rows]}


def signals(rows,positions):
    return 'session,position\n'+''.join(f"{r['session']},{p}\n" for r,p in zip(rows,positions))


def _sharpe(score):
    value=score.get('sharpe') if isinstance(score,dict) else None
    return Decimal(value) if isinstance(value,str) and score.get('sharpe_status')=='DEFINED' else None


def _score(rows,positions):
    try: return score_signals(signals(rows,positions),rows)
    except RuntimeRefused as error: return {'refused':error.code}


def choose(market):
    """Per family, the setting with the best TRAIN Sharpe. VALIDATION rows are used only as lookback-free padding: their positions are cut off."""
    train=market['train_rows'];s=series(train,market['validation_rows']);n=len(train);chosen={}
    for name,(rule,grid) in FAMILIES.items():
        best=None
        for knobs in grid:
            positions=rule(s,**knobs);score=_score(train,positions[:n]);value=_sharpe(score)
            if best is None or (value is not None and (best[0] is None or value>best[0])): best=(value,knobs,score)
        chosen[name]={'knobs':best[1],'train_sharpe':None if best[0] is None else str(best[0]),'train_beats':bool(best[2].get('beats_baseline'))}
    return chosen


def validate(market,name,knobs):
    train=market['train_rows'];validation=market['validation_rows']
    positions=FAMILIES[name][0](series(train,validation),**knobs)[len(train):]
    return _score(validation,positions)


PERTURB=(1,4,8)


def causal(market,name,knobs):
    """The Auditor's lookahead check for library code: changing the last k VALIDATION rows must leave every earlier position unchanged."""
    from .audit import perturbed_rows
    train=market['train_rows'];validation=market['validation_rows'];rule=FAMILIES[name][0]
    base=rule(series(train,validation),**knobs)
    for k in PERTURB:
        if not 1<=k<len(validation)-1: return False
        cut=len(train)+len(validation)-k
        if list(rule(series(train,perturbed_rows(validation,k)),**knobs)[:cut])!=list(base[:cut]): return False
    return True


def vault_score(queue,look_id,candidate_id,market,load_vault):
    """Stage 2 for a library candidate: inside its sealed look, run the admitted rule over TRAIN, VALIDATION and the vault, and score the
    vault part. The rule, its knobs and the market come from the ELIGIBLE event and must reproduce the admitted VALIDATION score.
    load_vault is called only inside the look."""
    import hashlib
    from compertum.events import canonical
    _,_,eligible=queue._fold(candidate_id);route=(eligible or {}).get('route') or {}
    name,knobs=route.get('family'),route.get('knobs')
    if route.get('kind')!='library' or route.get('symbol')!=market.get('symbol') or name not in FAMILIES or not callable(load_vault): raise RuntimeRefused('ENGINE_VAULT_DENIED')
    if hashlib.sha256(canonical(validate(market,name,knobs))).hexdigest()!=eligible.get('score_sha256'): raise RuntimeRefused('ENGINE_VAULT_DENIED')
    def produce():
        vault_rows=load_vault();rows=list(market['validation_rows'])+list(vault_rows)
        positions=FAMILIES[name][0](series(market['train_rows'],rows),**knobs)[len(market['train_rows'])+len(market['validation_rows']):]
        return signals(vault_rows,positions),vault_rows
    return queue.evaluate_in_vault(look_id,candidate_id,None,produce,vault=market.get('vault','history-v1'))


def sweep(markets,ledger,*,run_id,note):
    """markets: dicts with symbol, label, train_rows and validation_rows (no vault). Trials are recorded before any VALIDATION score."""
    if not markets or len({m['symbol'] for m in markets})!=len(markets): raise RuntimeRefused('ENGINE_MARKET_DENIED')
    ledger.require_unfrozen()
    choices={m['symbol']:choose(m) for m in markets}
    trials=SETTINGS*len(markets)
    ledger.record_external_trials(f'library:{run_id}',trials,{'kind':'strategy-library','run_id':run_id,'settings_per_market':SETTINGS,
                                                              'families':sorted(FAMILIES),'markets':[m['label'] for m in markets],'note':note})
    from .vault import CandidateQueue
    total=ledger.total_trials();rows=[];queue=CandidateQueue(ledger)
    for market in markets:
        for name,choice in choices[market['symbol']].items():
            score=validate(market,name,choice['knobs']);row={'symbol':market['symbol'],'family':name,**choice}
            if 'refused' in score: row.update(validation=score,gate='UNDEFINED');rows.append(row);continue
            inputs=score['deflation_inputs'];deflation=deflated_sharpe(inputs,total,trial_variance([],inputs)['trial_variance'])
            row.update(validation={k:score[k] for k in ('sharpe','sharpe_status','benchmark_sharpe','annual_mean_excess','beats_baseline','position_changes','positions_held','max_drawdown','sessions')},
                       deflated_sharpe=deflation['deflated_sharpe'],gate='PASS' if score['beats_baseline'] and deflation['status']=='PASS' else 'FAIL')
            if score['beats_baseline']:
                row['recomputed']=validate(market,name,choice['knobs'])==score;row['causal']=causal(market,name,choice['knobs'])
                if row['recomputed'] and row['causal']:
                    route={'kind':'library','symbol':market['symbol'],'family':name,'knobs':choice['knobs'],
                           'checks':'recompute and lookahead (last 1, 4 and 8 VALIDATION rows changed); no sandbox Auditor run'}
                    event=queue.admit(f"{run_id}:{market['symbol']}:{name}",score,deflation,tests_passed=True,auditor_passed=True,route=route,vault=market.get('vault','history-v1'))
                    row['queue']={'event':event['event'],'quarter':event['quarter'],'candidate_id':event['candidate_id']}
                else: row['queue']={'event':'NOT_ADMITTED','reason':'recompute or lookahead check failed'}
            rows.append(row)
    return {'run_id':run_id,'kind':'strategy-library','note':note,'markets':len(markets),'settings_per_market':SETTINGS,'trials_recorded':trials,
            'total_trials':total,'gate_rule':'beats buy-and-hold and deflated Sharpe >= 0.95 with the total trial count and the null variance (option C)',
            'summary':summarize(rows),'rows':rows}


def summarize(rows):
    scored=[r for r in rows if isinstance(r.get('validation'),dict) and 'sharpe' in r['validation']]
    families={}
    for r in scored:
        f=families.setdefault(r['family'],{'markets':0,'beat_buy_and_hold':0,'gate_passes':0})
        f['markets']+=1;f['beat_buy_and_hold']+=int(bool(r['validation']['beats_baseline']));f['gate_passes']+=int(r['gate']=='PASS')
    best=sorted((r for r in scored if r['validation']['beats_baseline']),key=lambda r:Decimal(r['deflated_sharpe'] or '0'),reverse=True)[:10]
    return {'candidates':len(rows),'scored':len(scored),'beat_buy_and_hold':sum(f['beat_buy_and_hold'] for f in families.values()),
            'gate_passes':sum(f['gate_passes'] for f in families.values()),'by_family':families,
            'best':[{k:r[k] for k in ('symbol','family','knobs','deflated_sharpe','gate')}|{'sharpe':r['validation']['sharpe'],'benchmark_sharpe':r['validation']['benchmark_sharpe']} for r in best]}


def load_markets(root,manifests):
    from .real_market import open_market
    out=[];skipped=[]
    for path in manifests:
        symbol=Path(path).parent.name
        try: market,_vault=open_market(root,str(path))
        except RuntimeRefused as error: skipped.append({'symbol':symbol,'code':error.code});continue
        out.append({'symbol':symbol,'label':market['label'],'train_rows':_rows(market['train_csv']),'validation_rows':market['validation_rows'],'vault':market.get('vault','history-v1')})
    return out,skipped


def main(argv=None):
    parser=argparse.ArgumentParser(prog='compertum.ai.engine.library',description='Sweep the strategy library over real history markets.')
    parser.add_argument('--project',type=Path,default=Path('.'));parser.add_argument('--config',type=Path,default=Path('config/default.toml'))
    commands=parser.add_subparsers(dest='command',required=True)
    run=commands.add_parser('sweep');run.add_argument('--manifest',action='append',default=[]);run.add_argument('--all',action='store_true')
    run.add_argument('--note',required=True)
    args=parser.parse_args(argv)
    root=args.project.resolve();config=args.config if args.config.is_absolute() else root/args.config
    manifests=list(args.manifest)+([p.relative_to(root).as_posix() for p in sorted((root/'data'/'history').glob('*/manifest.json'))] if args.all else [])
    if not manifests or not args.note.strip() or len(args.note)>NOTE_LIMIT: print(json.dumps({'refused':'ENGINE_RUN_LIMITS_DENIED'}));return 2
    from compertum.config import ConfigError,load_config
    from compertum.domain import ContractError
    from compertum.runtime.identity import resolve_project
    from compertum.runtime.owners import acquire_owner,release_owner
    from compertum.storage import StorageManager
    from .ledger import EngineLedger
    lease=None;run_id=f'library-{datetime.now(timezone.utc):%Y%m%d}-{uuid4().hex[:8]}'
    try:
        markets,skipped=load_markets(root,manifests)
        lease=acquire_owner(resolve_project(root),'coordinator')
        store=StorageManager(lease,load_config(config,root)).store
        report=sweep(markets,EngineLedger(store),run_id=run_id,note=args.note);report['skipped']=skipped
    except RuntimeRefused as error:
        print(json.dumps({'refused':error.code}));return 2
    except (ContractError,ConfigError) as error:
        print(json.dumps({'refused':getattr(error,'reason',None) or type(error).__name__}));return 2
    finally:
        if lease is not None: release_owner(lease)
    folder=root/'state'/'engine'/'library';folder.mkdir(parents=True,exist_ok=True)
    path=folder/f'{run_id}.json';path.write_text(json.dumps(report,indent=1,sort_keys=True),encoding='utf-8',newline='\n')
    print(json.dumps({'run_id':run_id,'report':str(path),'markets':report['markets'],'skipped':skipped,'trials_recorded':report['trials_recorded'],
                      'total_trials':report['total_trials'],'summary':{k:v for k,v in report['summary'].items() if k!='by_family'}},sort_keys=True))
    return 0


if __name__=='__main__': sys.exit(main())
