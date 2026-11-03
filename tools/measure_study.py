"""Candidate measures study, part 3 of docs/CANDIDATE_MEASURES_DESIGN.md (owner, 3 November 2026: "go ahead with part 3").

It reads the engine ledger read-only and the series files, writes one report, and changes nothing else. It opens no vault: the vault study
uses only the vault results that evaluate_in_vault already recorded.

    .cache/engine-env/Scripts/python.exe tools/measure_study.py [--out reports/MEASURE_STUDY_<date>.md]

- Proxy study: Spearman rank correlation between each early measure (first two thirds of VALIDATION) and the active Sharpe ratio of the
  last third, with a 95% bootstrap interval, for each market and for all markets together. One combined least-squares model on the early
  measures gives a cross-validated R squared, to compare with Quantopian's 17%.
- Vault study: the same table, with the full VALIDATION measures against the vault's active Sharpe ratio.
- Every table states its sample size. Below MIN_SAMPLE candidates, every result is labeled too small to use.
"""
import argparse
from datetime import date
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import sys

import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parent))
import run_tests  # noqa: E402

ROOT=run_tests.ROOT
MIN_SAMPLE=30
BOOTSTRAP=2000
SEED=20261103
FOLDS=5
YEAR=252
EARLY=('early.active_sharpe','early.tail_ratio','early.hit_rate','early.block_sharpes.min','early.block_sharpes.spread','early.block_sharpes.positive',
       'early.lag_drop','early.cost_2x_active_sharpe','early.autocorrelation','early.newey_west_t','engineer_runs','code_bytes')
OVERLAP=('exposure','turnover_per_year','concentration.effective_assets','concentration.max_weight','book.max_correlation','book.combined_sharpe_gain',
         'book.residual_sharpe')
FULL=tuple(name.replace('early.','full.') for name in EARLY)+OVERLAP
SMALL='too small to use'


def read_ledger(root=ROOT):
    """(candidates, vault) from the live store, read-only. A candidate is a validator score step with measured status."""
    store,_=run_tests.engine_store(root)
    if not store.exists(): return [],{}
    connection=sqlite3.connect(store.as_uri()+'?mode=ro',uri=True,timeout=5)
    try:
        def rows(sql): return [json.loads(r[0]) for r in connection.execute(sql)]
        try:
            ends={c['cycle_id']:c for c in rows("SELECT record FROM engine_cycles WHERE phase='END'")}
            steps=rows("SELECT record FROM engine_steps WHERE role='validator' AND kind='score'")
            events=rows("SELECT record FROM engine_queue WHERE event='VAULT_EVALUATED'")
        except sqlite3.OperationalError as error:
            if 'no such table' in str(error): return [],{}
            raise
    finally: connection.close()
    candidates=[]
    for step in steps:
        measured=step.get('measures')
        if step.get('phase')!='SCORED' or not isinstance(measured,dict) or measured.get('status')!='MEASURED': continue
        end=ends.get(step['cycle_id']) or {}
        candidates.append({'candidate_id':step['candidate_id'],'purpose':end.get('purpose','unknown'),'market':measured.get('market_sha256') or end.get('market_sha256') or 'unknown',
                           'measures':measured})
    vault={}
    for event in events:
        sharpe=((event.get('result') or {}).get('deflation_inputs') or {}).get('sharpe_per_period')
        if event.get('status')=='SCORED' and sharpe is not None: vault[event['candidate_id']]=float(sharpe)*math.sqrt(YEAR)
    return candidates,vault


def value(record,path):
    for key in path.split('.'):
        if not isinstance(record,dict): return None
        record=record.get(key)
    return float(record) if isinstance(record,(int,float)) and not isinstance(record,bool) and math.isfinite(record) else None


def ranks(x):
    order=np.argsort(x,kind='mergesort');r=np.empty(len(x));r[order]=np.arange(1,len(x)+1);out=r.copy()
    for v in np.unique(x):
        same=x==v
        if same.sum()>1: out[same]=r[same].mean()
    return out


def spearman(x,y):
    a=ranks(np.asarray(x,dtype=float));b=ranks(np.asarray(y,dtype=float))
    if a.std()==0 or b.std()==0: return None
    return float(np.corrcoef(a,b)[0,1])


def interval(x,y,rng):
    x=np.asarray(x,dtype=float);y=np.asarray(y,dtype=float);values=[]
    for _ in range(BOOTSTRAP):
        pick=rng.integers(0,len(x),len(x));rho=spearman(x[pick],y[pick])
        if rho is not None: values.append(rho)
    return (float(np.percentile(values,2.5)),float(np.percentile(values,97.5))) if len(values)>=BOOTSTRAP//2 else None


def combined(table,target):
    """Out-of-sample R squared of one least-squares model on the standardized columns, with FOLDS folds in a fixed order."""
    x=np.asarray(table,dtype=float);y=np.asarray(target,dtype=float);n=len(y)
    if x.ndim!=2 or x.shape[1]==0 or n<2*FOLDS or n<=x.shape[1]+FOLDS: return None
    predicted=np.empty(n);folds=np.arange(n)%FOLDS
    for k in range(FOLDS):
        train=folds!=k;mean=x[train].mean(axis=0);sd=x[train].std(axis=0);sd[sd==0]=1
        design=np.column_stack([np.ones(train.sum()),(x[train]-mean)/sd]);beta=np.linalg.lstsq(design,y[train],rcond=None)[0]
        predicted[~train]=np.column_stack([np.ones((~train).sum()),(x[~train]-mean)/sd])@beta
    total=((y-y.mean())**2).sum()
    return None if total==0 else float(1-((y-predicted)**2).sum()/total)


def correlations(records,names,target,rng):
    out=[]
    for name in names:
        pairs=[(value(r,name),t) for r,t in zip(records,target) if value(r,name) is not None and t is not None]
        x=[p[0] for p in pairs];y=[p[1] for p in pairs];rho=spearman(x,y) if len(pairs)>=3 else None
        out.append({'measure':name,'n':len(pairs),'spearman':rho,'interval':interval(x,y,rng) if rho is not None else None,'overlap':name in OVERLAP,
                    'label':SMALL if len(pairs)<MIN_SAMPLE else 'usable'})
    return out


def study(records,names,target,rng,model_names):
    keep=[i for i,t in enumerate(target) if t is not None];records=[records[i] for i in keep];target=[target[i] for i in keep]
    usable=[n for n in model_names if all(value(r,n) is not None for r in records)]
    r2=combined([[value(r,n) for n in usable] for r in records],target) if usable else None
    return {'n':len(records),'label':SMALL if len(records)<MIN_SAMPLE else 'usable','table':correlations(records,names,target,rng),
            'combined':{'measures':usable,'r_squared':r2}}


def series_check(root,candidates):
    bad=[]
    for c in candidates:
        record=c['measures'].get('series') or {}
        path=root/str(record.get('path',''))
        if not record.get('path') or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=record.get('sha256'): bad.append(c['candidate_id'])
    return bad


def run(root=ROOT):
    candidates,vault=read_ledger(root);rng=np.random.default_rng(SEED)
    markets={}
    for c in candidates: markets.setdefault(c['market'],[]).append(c)
    def proxy(group): return study([c['measures'] for c in group],EARLY+OVERLAP,[value(c['measures'],'late_active_sharpe') for c in group],rng,EARLY)
    joined=[c for c in candidates if c['candidate_id'] in vault]
    purposes={}
    for c in candidates: purposes[c['purpose']]=purposes.get(c['purpose'],0)+1
    return {'date':date.today().isoformat(),'candidates':len(candidates),'purposes':purposes,'series_problems':series_check(root,candidates),
            'proxy':{'all':proxy(candidates),**{m:proxy(g) for m,g in sorted(markets.items(),key=lambda kv:-len(kv[1]))}},
            'vault':study([c['measures'] for c in joined],FULL,[vault[c['candidate_id']] for c in joined],rng,tuple(n.replace('early.','full.') for n in EARLY)),
            'vault_results':len(vault)}


def number(v,places=2): return '-' if v is None else f'{v:.{places}f}'


def table_text(result):
    lines=[f"Sample: {result['n']} candidates ({result['label']}).",'','| Measure | n | Spearman | 95% interval | Note |','|---|---|---|---|---|']
    for row in result['table']:
        ci=row['interval'];note=[row['label']]+(['overlaps the target period'] if row['overlap'] else [])
        lines.append(f"| `{row['measure']}` | {row['n']} | {number(row['spearman'])} | {'-' if ci is None else number(ci[0])+' to '+number(ci[1])} | {', '.join(note)} |")
    model=result['combined']
    lines+=['',f"Combined model, cross-validated R squared: {number(model['r_squared'],3)} on {len(model['measures'])} measures ({result['label']}). Quantopian found 0.17."]
    return lines


def report_text(result):
    lines=[f"# Candidate measures study - {result['date']}",'',
           'Source: `tools/measure_study.py` (docs/CANDIDATE_MEASURES_DESIGN.md, part 3). It read the ledger read-only and opened no vault.',
           f"Below {MIN_SAMPLE} candidates every result is labeled \"{SMALL}\". No result here changes the gate or the ranking; a change goes to the owner as a separate proposal.",'',
           f"Measured candidates: {result['candidates']}. By purpose: {', '.join(f'{k} {v}' for k,v in sorted(result['purposes'].items())) or 'none'}.",
           f"Series files missing or changed: {len(result['series_problems'])}.",'',
           '## Proxy study','','Target: active Sharpe ratio of the last third of VALIDATION. The models saw scores on the whole of VALIDATION, so this is a proxy, never vault evidence.','']
    for name,part in result['proxy'].items():
        lines+=[f"### {'All markets' if name=='all' else 'Market '+name[:12]}",'']+table_text(part)+['']
    lines+=['## Vault study','',f"Vault results recorded: {result['vault_results']}. Joined with measured candidates: {result['vault']['n']}.",'']
    lines+=table_text(result['vault']) if result['vault']['n'] else ['No measured candidate has a vault result yet.']
    return '\n'.join(lines)+'\n'


def main(argv=None,root=ROOT):
    parser=argparse.ArgumentParser(description='Study which candidate measures predict later results. Reads only; writes one report.')
    parser.add_argument('--out',type=Path,default=None)
    args=parser.parse_args(argv)
    result=run(root);out=args.out or root/'reports'/f"MEASURE_STUDY_{result['date'].replace('-','')}.md"
    out=out if out.is_absolute() else root/out
    out.write_text(report_text(result),encoding='utf-8',newline='\n')
    print(json.dumps({'report':str(out),'candidates':result['candidates'],'proxy_all':result['proxy']['all']['label'],'vault_joined':result['vault']['n']}))
    return 0


if __name__=='__main__': sys.exit(main())
