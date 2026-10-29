"""Check whether synthetic markets can be passed and cannot be faked, before the firm is measured on them.

    python tools/calibrate_markets.py OUTPUT.json [--workers 6]

For each market length, pattern and calibration seed, the exact planted rule is scored on VALIDATION and run through the
bench gate at several trial counts. On markets with no pattern, 45 simple rules are scored the same way; any pass is a
false discovery. The tool makes no model call and starts no sandbox. Seeds 5000 to 5007 are outside every reserved range.
See docs/ENGINE_PLAN.md, "Calibrated markets".
"""
import argparse
from concurrent.futures import ProcessPoolExecutor
import json
from pathlib import Path
import statistics
import sys
import time
from compertum.ai.engine import bench
from compertum.ai.engine.deflation import deflated_sharpe,trial_variance
from compertum.ai.engine.market import score_signals,split_market_tiers,synthetic_market

LENGTHS=(500,1000,1500,2000,3000,4096)
TRIALS=(60,192,1200)
SEEDS=range(5000,5008)
PATTERNS=(('momentum',5,0.004),('momentum',10,0.004),('reversal',3,0.004),('reversal',5,0.004),('momentum',5,0.002),('reversal',3,0.002))
REGIMES={'momentum then reversal':(bench.regime(0,'momentum',5),bench.regime(250,'reversal',3)),
         'reversal, noise change':(bench.regime(0,'reversal',3,noise=0.006),bench.regime(250,'reversal',3,noise=0.02))}
EMPTY={'no pattern':None,
       'changing noise':(bench.regime(0,None,0,noise=0.005),bench.regime(200,None,0,noise=0.02)),
       'steady drift 0.001':(bench.regime(0,None,0,drift=0.001),)}


def scaled(regimes,length):
    return [{**r,'start':r['start']*length//500} for r in regimes]


def simple_rules(train,validation):
    history=[float(r['return']) for r in train];closes=[float(r['close']) for r in train];rules={}
    for row in validation:
        history.append(float(row['return']));closes.append(float(row['close']))
        for window in range(1,21):
            recent=sum(history[-window:])
            rules.setdefault(f'momentum {window}',[]).append(1 if recent>0 else 0);rules.setdefault(f'reversal {window}',[]).append(1 if recent<0 else 0)
        for window in (5,10,20,50,100):
            rules.setdefault(f'above ma {window}',[]).append(1 if closes[-1]>sum(closes[-window:])/len(closes[-window:]) else 0)
    return rules


def gate(score,trials):
    if not score['beats_baseline']: return None
    inputs=score['deflation_inputs']
    return float(deflated_sharpe(inputs,trials,trial_variance([],inputs)['trial_variance'])['deflated_sharpe'] or 0)


def one(job):
    length,label,seed,planted,regimes,kind,window=job
    train,validation,_=split_market_tiers(synthetic_market(seed,length,planted=planted,regimes=regimes))
    out={'length':length,'label':label,'seed':seed,'validation':len(validation),'patterned':kind is not None}
    if kind is not None:
        reference=score_signals(bench.signals_text(validation,bench.reference_positions(train,validation,kind,window,regimes)),validation)
        out['reference']={str(t):gate(reference,t) for t in TRIALS}
    else:
        passing={str(t):[] for t in TRIALS}
        for name,positions in simple_rules(train,validation).items():
            score=score_signals(bench.signals_text(validation,positions),validation)
            for t in TRIALS:
                value=gate(score,t)
                if value is not None and value>=0.95: passing[str(t)].append(name)
        out['search_passing']=passing
    return out


def jobs():
    for length in LENGTHS:
        for seed in SEEDS:
            for kind,window,strength in PATTERNS:
                yield (length,f'{kind} {window} at {strength}',seed,{'kind':kind,'window':window,'strength':strength},None,kind,window)
            for label,regimes in REGIMES.items(): yield (length,label,seed,None,scaled(regimes,length),'regimes',None)
            for label,regimes in EMPTY.items(): yield (length,label,seed,None,None if regimes is None else scaled(regimes,length),None,None)


def table(rows):
    labels=list(dict.fromkeys(r['label'] for r in rows));lines=[]
    for t in TRIALS:
        lines.append(f'\n{t} trials: planted rule passes the gate (of {len(SEEDS)} seeds), then empty markets where a simple rule passes')
        lines.append(f"{'market':28}"+''.join(f'{n:>7}' for n in LENGTHS))
        for label in labels:
            group=[r for r in rows if r['label']==label]
            if group[0]['patterned']: count=lambda r:(r['reference'][str(t)] or 0)>=0.95
            else: count=lambda r:bool(r['search_passing'][str(t)])
            lines.append(f'{label:28}'+''.join(f"{sum(1 for r in group if r['length']==n and count(r)):>7}" for n in LENGTHS))
    lines.append('\nmedian planted-rule deflated Sharpe at 192 trials')
    for label in labels:
        group=[r for r in rows if r['label']==label and r['patterned']]
        if group: lines.append(f'{label:28}'+''.join(f"{statistics.median([r['reference']['192'] or 0 for r in group if r['length']==n]):>7.2f}" for n in LENGTHS))
    return '\n'.join(lines)


def main(argv=None):
    parser=argparse.ArgumentParser(description='Calibrate synthetic market lengths against the bench gate.')
    parser.add_argument('output',type=Path);parser.add_argument('--workers',type=int,default=6)
    args=parser.parse_args(argv);start=time.time()
    with ProcessPoolExecutor(max_workers=max(1,min(args.workers,8))) as pool: rows=list(pool.map(one,list(jobs()),chunksize=4))
    args.output.write_text(json.dumps({'lengths':LENGTHS,'trials':TRIALS,'seeds':list(SEEDS),'rows':rows},indent=0),encoding='utf-8')
    print(table(rows));print(f'\n{len(rows)} markets, {round(time.time()-start)} seconds, written to {args.output}')
    return 0


if __name__=='__main__': sys.exit(main())
