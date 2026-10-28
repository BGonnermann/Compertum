"""Read-only comparison of two completed bench or holdout runs."""
import argparse
from collections import Counter
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import sys
from compertum.events import canonical
from compertum.runtime.errors import RuntimeRefused
from . import bench
from .ledger import RUN_ID


def market_sha256(market):
    return hashlib.sha256(canonical({'train_csv':market['train_csv'],'validation_csv':market['validation_csv']})).hexdigest()


def run_rows(connection,run_id):
    if not isinstance(run_id,str) or not re.fullmatch(RUN_ID,run_id): raise RuntimeRefused('ENGINE_RUN_UNKNOWN')
    rows=[json.loads(r[0]) for r in connection.execute('SELECT record FROM engine_bounded_runs WHERE run_id=? ORDER BY rowid',(run_id,))]
    starts=[r for r in rows if r.get('phase')=='START'];ends=[r for r in rows if r.get('phase')=='END']
    if len(starts)!=1 or len(ends)!=1: raise RuntimeRefused('ENGINE_RUN_UNKNOWN')
    return starts[0],ends[0]


def legacy_report(connection,start,end):
    purpose=start.get('purpose')
    if purpose not in ('bench','holdout'): raise RuntimeRefused('ENGINE_RUN_PURPOSE_DENIED')
    labels=start.get('markets') or []
    counts=Counter(labels)
    if not counts or len(set(counts.values()))!=1: raise RuntimeRefused('ENGINE_RUN_INCOMPLETE')
    first=next(iter(counts))
    set_name=start.get('holdout_set') if purpose=='holdout' else first.split(':',1)[0]
    markets=bench.set_markets(set_name)
    by_hash={market_sha256(m):m['label'] for m in markets}
    cycles=[]
    for raw, in connection.execute("SELECT record FROM engine_cycles WHERE phase='END' ORDER BY rowid"):
        record=json.loads(raw)
        if record.get('run_id')!=start['run_id']: continue
        record['market']=by_hash.get(record.get('market_sha256'));cycles.append(record)
    return bench.report(cycles,markets,counts[first])


def run_summary(connection,run_id):
    start,end=run_rows(connection,run_id)
    purpose=start.get('purpose')
    if purpose not in ('bench','holdout'): raise RuntimeRefused('ENGINE_RUN_PURPOSE_DENIED')
    cycles=[json.loads(raw) for raw, in connection.execute("SELECT record FROM engine_cycles WHERE phase='END' AND json_extract(record,'$.run_id')=? ORDER BY rowid",(run_id,))]
    statuses=Counter(c.get('status') for cycle in cycles for c in cycle.get('candidates') or [])
    report=end.get('report') or legacy_report(connection,start,end)
    return {'run_id':run_id,'purpose':purpose,'reason':end.get('reason'),'requests':end.get('requests'),'elapsed_seconds':end.get('elapsed_seconds'),
            'cycles':len(cycles),'faults':sum(len(cycle.get('faults') or []) for cycle in cycles),'statuses':dict(sorted(statuses.items())),'report':report}


def _delta(left,right,key):
    a,b=left.get(key),right.get(key)
    if isinstance(a,str) and isinstance(b,str):
        try: return format(Decimal(b)-Decimal(a),'f')
        except ArithmeticError: return None
    return b-a if isinstance(a,(int,float)) and isinstance(b,(int,float)) else None


def compare_summaries(left,right):
    if left['report']['cycles_per_market']!=right['report']['cycles_per_market']: raise RuntimeRefused('ENGINE_COMPARISON_INCOMPATIBLE')
    keys=('patterns_found','false_discoveries','candidates_total','requests','elapsed_seconds','faults')
    markets=[]
    right_markets={m['market']:m for m in right['report']['markets']}
    for a in left['report']['markets']:
        b=right_markets.get(a['market'])
        if b is None: raise RuntimeRefused('ENGINE_COMPARISON_INCOMPATIBLE')
        markets.append({'market':a['market'],'left_levels':a['levels'],'right_levels':b['levels'],
                        'left_best_capture':a['best_capture'],'right_best_capture':b['best_capture'],
                        'left_found':a.get('found'),'right_found':b.get('found'),
                        'left_false_discoveries':a.get('false_discoveries'),'right_false_discoveries':b.get('false_discoveries')})
    return {'left_run':left['run_id'],'right_run':right['run_id'],'cycles_per_market':left['report']['cycles_per_market'],
            'delta':{key:_delta(left if key in left else left['report'],right if key in right else right['report'],key) for key in keys},
            'mean_level_delta':_delta(left['report'],right['report'],'mean_level'),'markets':markets,
            'warning':'Equal paired runs reduce measurement differences. One comparison does not establish repeatable improvement.'}


def compare(store_path,left_run,right_run):
    path=Path(store_path).absolute()
    if not path.is_file(): raise RuntimeRefused('ENGINE_STORE_UNAVAILABLE')
    connection=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)
    try:
        left=run_summary(connection,left_run);right=run_summary(connection,right_run)
        return {'runs':[left,right],'comparison':compare_summaries(left,right)}
    finally: connection.close()


def main(argv=None):
    parser=argparse.ArgumentParser(prog='compertum.ai.engine.compare',description='Read-only comparison of two completed evaluation runs.')
    parser.add_argument('--project',type=Path,default=Path('.'));parser.add_argument('left_run');parser.add_argument('right_run')
    args=parser.parse_args(argv)
    try: result=compare(args.project.resolve()/'state'/'research.sqlite',args.left_run,args.right_run)
    except RuntimeRefused as error:
        print(json.dumps({'refused':error.code}));return 2
    except sqlite3.Error:
        print(json.dumps({'refused':'ENGINE_STORE_UNAVAILABLE'}));return 2
    print(json.dumps(result,sort_keys=True));return 0


if __name__=='__main__': sys.exit(main())
