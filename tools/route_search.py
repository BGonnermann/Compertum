"""Model routing search (owner, 31 October 2026): find which model should serve each role, with at most one cycle per market per test.

    python tools/route_search.py --project . next       write the next batch of candidate firms and print the command that runs them together
    python tools/route_search.py --project . score RECORD   read a finished batch record, score every candidate, keep or discard, print the table
    python tools/route_search.py --project . status     print the log as a table
    python tools/route_search.py --project . roles      print each scored firm's model time, output tokens and faults by role
    python tools/route_search.py --project . import RUN_ID --firm NAME[,NAME,NAME,NAME]
                                                         add a finished bench run as one more pass of a firm (same model files, same bench)

The search is a coordinate ascent, in the autoresearch form (edit, measure, keep or discard). It starts from the firm in
config/route_search.toml, measures every pool model as a one-model firm (owner, 31 October 2026: one model for everything is preferred
when it is close, because its cost is upfront and measurable), then for one role at a time tries every other model of the pool in that role. A candidate is a model
file config/models-route-N.toml; one trip runs a batch of candidates together through tools\\practice.ps1 with FILE::ID entries.
Each candidate is measured once on bench-4 at one cycle per market (16 cycles). It replaces the incumbent when its mean level is
higher by at least the keep margin, or equal within the margin with more patterns found; a false discovery or an incomplete report
discards it. A one-pass mean is noisy (the two halves of a run differed by up to 2.2 levels, and two passes of the same firm by 0.75, on
31 October 2026), so a win smaller than the incumbent's half-spread is retested once, and the two passes are averaged before the decision.
The incumbent is always judged on the average of all its own passes, so a challenger's average never meets one lucky or unlucky pass. Speed and cost are recorded and
break ties. The cost of a batch is the OpenRouter credits balance before and after (authoritative); the token estimate per firm sits
beside it. The owner starts every trip; nothing here runs on its own. The log is state/engine/route-search/log.jsonl; every candidate
stays in it, kept or not.
"""
import argparse
from decimal import Decimal
import json
import os
from pathlib import Path
import sys
import tomllib
import urllib.request

CREDITS_URL='https://openrouter.ai/api/v1/credits'
KEY_ENV='OPENROUTER_API_KEY'


def credits_balance(seconds=30):
    """The OpenRouter credits balance in dollars, or None when the key is absent or the request fails. The key is never printed or logged."""
    key=os.environ.get(KEY_ENV)
    if not key: return None
    try:
        request=urllib.request.Request(CREDITS_URL,headers={'Authorization':'Bearer '+key})
        with urllib.request.urlopen(request,timeout=seconds) as reply: data=json.load(reply)['data']
        return float(round(Decimal(str(data['total_credits']))-Decimal(str(data['total_usage'])),4))
    except Exception: return None

ROLES=('director','researcher','mathematician','engineer')
ROLE_ORDER=('mathematician','engineer','researcher','director')  # the roles that cost the most model time first (measured 31 October 2026)
LOG='state/engine/route-search/log.jsonl'
PLAN='config/route_search.toml'


def load_plan(root):
    plan=tomllib.loads((root/PLAN).read_text(encoding='utf-8'))
    pool={p['name']:p for p in plan['pool']}
    for p in pool.values():
        for key in ('file','model','input_per_million','output_per_million'):
            if key not in p: raise ValueError(f'pool entry {p.get("name")} lacks {key}')
    start=plan['start']
    if set(start)!=set(ROLES) or any(start[r] not in pool for r in ROLES): raise ValueError('start must name a pool entry for every role')
    return {'pool':pool,'start':start,'batch':int(plan.get('batch',4)),'keep_margin':Decimal(str(plan.get('keep_margin','0.3'))),
            'bench_set':plan.get('bench_set','bench-4'),'requests':int(plan.get('requests',600)),'roles':tuple(plan.get('roles',ROLE_ORDER))}


def read_log(root):
    path=root/LOG
    if not path.exists(): return []
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]


def append_log(root,entry):
    path=root/LOG;path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('a',encoding='utf-8') as stream: stream.write(json.dumps(entry,sort_keys=True)+'\n')


def firm_key(firm): return '|'.join(f'{r}={firm[r]}' for r in ROLES)


def halves(levels):
    """The mean of the first and of the second half of a run's first-cycle levels, and their spread."""
    if not levels: return None
    half=len(levels)//2;first=levels[:half] or levels;second=levels[half:] or levels
    a=Decimal(sum(first))/len(first);b=Decimal(sum(second))/len(second)
    return {'first':float(round(a,2)),'second':float(round(b,2)),'spread':float(round(abs(a-b),2))}


def passes_of(log,key):
    """Every measured single pass of one firm, once each (a retested entry carries both of its passes)."""
    seen={};
    for e in log:
        if e.get('kind')!='scored' or e.get('key')!=key or not e.get('metrics'): continue
        for single in e['metrics'].get('pass_list') or [e['metrics']]:
            if single.get('run_id') and single['run_id'] not in seen: seen[single['run_id']]=single
    return list(seen.values())


def incumbent(log,start):
    """The current best firm: the start firm, replaced by every kept candidate in order; its score is the average of all its passes."""
    firm=dict(start);score=None
    for e in log:
        if e.get('kind')=='scored' and e.get('decision')=='keep': firm=e['firm'];score=e['metrics']
    if score is not None:
        passes=passes_of(log,firm_key(firm))
        if len(passes)>1: score=averaged(passes)
    return firm,score


def role_file(root,pool_entry):
    """The role table of a pool entry, read from its model file (limits and thinking cap included)."""
    text=(root/'config'/f"models-{pool_entry['file']}.toml").read_text(encoding='utf-8')
    roles=tomllib.loads(text)['roles']
    return {r:{**roles[r],'model':pool_entry['model']} for r in ROLES}


def write_candidate(root,index,firm,pool):
    """config/models-route-N.toml: each role from the pool entry's file, with that entry's model."""
    lines=[f'# Route search candidate {index} (generated by tools/route_search.py). '+', '.join(f'{r}: {firm[r]}' for r in ROLES),'']
    for r in ROLES:
        entry=role_file(root,pool[firm[r]])[r]
        lines.append(f'[roles.{r}]')
        for key in ('base_url','model','max_tokens','reasoning_tokens','seconds','temperature'):
            if key in entry: lines.append(f'{key} = {json.dumps(entry[key])}')
        lines.append('')
    name=f'route-{index}'
    (root/'config'/f'models-{name}.toml').write_text('\n'.join(lines),encoding='utf-8',newline='\n')
    return name


def tried(log):
    return {e['key'] for e in log if e.get('kind') in ('planned','scored')}


def retests(log):
    """Firms whose first pass ended in 'retest' and that have no second pass planned yet."""
    second={e['key'] for e in log if e.get('kind')=='planned' and e.get('pass')==2}
    return [e['firm'] for e in log if e.get('kind')=='scored' and e.get('decision')=='retest' and e['key'] not in second]


def next_batch(plan,log):
    """The next candidates: retests first, then the incumbent with one role swapped, in role order, skipping firms already tried."""
    firm,_=incumbent(log,plan['start'])
    done=tried(log);batch=[dict(f) for f in retests(log)][:plan['batch']]
    if len(batch)>=plan['batch']: return batch
    if firm_key(firm) not in done: batch.append(dict(firm))  # the start firm is measured first, so every keep is against a measured incumbent
    for name in plan['pool']:  # every pool model as a one-model firm, measured under the same conditions as the start
        single={r:name for r in ROLES}
        if firm_key(single) in done or single in batch: continue
        batch.append(single)
        if len(batch)>=plan['batch']: return batch
    for role in plan['roles']:
        for name in plan['pool']:
            if name==firm[role]: continue
            candidate={**firm,role:name}
            if firm_key(candidate) in done or candidate in batch: continue
            batch.append(candidate)
            if len(batch)>=plan['batch']: return batch
    return batch


def cost_of(root,run_id,pool):
    """Dollars from the transcript's token counts and the pool's prices (OpenRouter list prices of 31 October 2026)."""
    prices={p['model']:(Decimal(str(p['input_per_million'])),Decimal(str(p['output_per_million']))) for p in pool.values()}
    path=root/'state'/'engine'/'transcripts'/f'{run_id}.jsonl'
    if not path.exists(): return None
    total=Decimal(0)
    for line in path.read_text(encoding='utf-8').splitlines():
        d=json.loads(line);u=d.get('usage') or {};p=prices.get(d.get('model_requested'))
        if p is None: continue
        total+=Decimal(u.get('prompt_tokens',0))*p[0]/1000000+Decimal(u.get('completion_tokens',0))*p[1]/1000000
    return float(round(total,4))


def roles_of(root,run_id):
    """Per role, from the transcript: calls, model seconds, output tokens and refused calls. Shows where a firm spends its time."""
    path=root/'state'/'engine'/'transcripts'/f'{run_id}.jsonl'
    if not path.exists(): return None
    out={r:{'calls':0,'seconds':0.0,'output_tokens':0,'faults':0,'model':None} for r in ROLES}
    for line in path.read_text(encoding='utf-8').splitlines():
        d=json.loads(line);r=d.get('role')
        if r not in out: continue
        row=out[r];row['calls']+=1;row['seconds']+=float(d.get('elapsed_seconds') or 0);row['output_tokens']+=(d.get('usage') or {}).get('completion_tokens',0)
        row['model']=row['model'] or d.get('model_requested')
        if d.get('status')!='COMPLETED': row['faults']+=1
    for row in out.values(): row['seconds']=round(row['seconds'],1)
    return out


def metrics_of(root,run,pool):
    rep=run['report'];faults=sum(len(c.get('faults') or []) for c in run['cycles'])
    levels=[m['levels'][0] for m in rep.get('markets') or [] if m.get('levels')]
    return {'run_id':run['run_id'],'reason':run['reason'],'verdict':rep['verdict'],'mean_level':rep['mean_level'],'found':rep['patterns_found'],
            'false':rep['false_discoveries'],'candidates':rep['candidates_total'],'requests':run['requests'],'minutes':round(run['elapsed_seconds']/60,1),
            'faults':faults,'cost':cost_of(root,run['run_id'],pool),'halves':halves(levels),'roles':roles_of(root,run['run_id'])}


def averaged(passes):
    """Several passes of one firm as one measure, per pass: mean level, patterns found, faults, minutes, cost and halves averaged;
    false discoveries summed (one is enough to discard); the worst verdict kept. pass_list keeps every single pass."""
    singles=[]
    for m in passes: singles.extend(m.get('pass_list') or [m])
    n=len(singles);last=singles[-1]
    def avg(key,digits=2):
        values=[s[key] for s in singles if s.get(key) is not None]
        return round(sum(values)/len(values),digits) if values else None
    mean=sum(Decimal(s['mean_level']) for s in singles)/n
    out={**last,'mean_level':format(mean.quantize(Decimal('0.01')),'f'),'found':avg('found',1),'false':sum(s['false'] for s in singles),'faults':avg('faults',1),
         'requests':avg('requests',0),'minutes':avg('minutes',1),'cost':avg('cost',4),
         'verdict':next((s['verdict'] for s in singles if s['verdict']!='MEASURED'),'MEASURED'),'passes':n,
         'pass_list':[{k:v for k,v in s.items() if k not in ('pass_list','roles')} for s in singles]}
    halves_list=[s['halves'] for s in singles if s.get('halves')]
    if halves_list:
        a=round(sum(h['first'] for h in halves_list)/len(halves_list),2);b=round(sum(h['second'] for h in halves_list)/len(halves_list),2)
        out['halves']={'first':a,'second':b,'spread':round(abs(a-b),2)}
    return out


def combined(first,second): return averaged([first,second])


def decide(metrics,best,margin,final=False):
    """keep, discard or retest. A win smaller than the incumbent's half-spread is retested once (final=True after the second pass)."""
    if metrics['verdict']!='MEASURED' or metrics['false']: return 'discard','false discovery or incomplete'
    if best is None: return 'keep','first measured firm'
    mine=Decimal(metrics['mean_level']);theirs=Decimal(best['mean_level'])
    spread=Decimal(str((best.get('halves') or {}).get('spread',0)))
    if mine>=theirs+margin:
        if not final and mine-theirs<spread: return 'retest',f'mean level up by {mine-theirs}, under the incumbent half-spread {spread}'
        return 'keep',f'mean level up by {mine-theirs}'
    if mine>theirs-margin and metrics['found']>best['found']:
        if not final and spread>margin: return 'retest',f'within the margin with more patterns found, incumbent half-spread {spread}'
        return 'keep',f'within the margin with more patterns found ({metrics["found"]} against {best["found"]})'
    return 'discard',f'mean level {mine} against {theirs}'


def read_record(path):
    raw=Path(path).read_bytes()
    for enc in ('utf-8-sig','utf-16'):
        try: text=raw.decode(enc);break
        except UnicodeDecodeError: continue
    else: raise ValueError('record is not UTF-8 or UTF-16')
    lines=[l for l in text.splitlines() if l.lstrip().startswith('{')]
    return json.loads(lines[-1])


def do_next(root,plan):
    log=read_log(root);batch=next_batch(plan,log)
    if not batch: print('nothing left to try in this round');return 0
    used={int(e['name'].split('-')[1]) for e in log if e.get('kind')=='planned'};index=max(used,default=0)
    again={firm_key(f) for f in retests(log)};names=[]
    for firm in batch:
        index+=1;name=write_candidate(root,index,firm,plan['pool']);names.append((name,firm))
        append_log(root,{'kind':'planned','name':name,'key':firm_key(firm),'firm':firm,'pass':2 if firm_key(firm) in again else 1})
    append_log(root,{'kind':'batch','names':[n for n,_ in names],'balance_before':credits_balance()})
    entries=','.join(f'{name}::' for name,_ in names)  # FILE:: takes the file's own roles, one model per role
    print('candidates:')
    for name,firm in names: print(f"  {name}: "+', '.join(f'{r} {firm[r]}' for r in ROLES))
    print('run them together (the owner starts it):')
    print(f'  tools\\start_run.ps1 -Models openrouter -Model "{entries}" -Mode bench -BenchSet {plan["bench_set"]} -CyclesPerMarket 1 -Requests {plan["requests"]} '
          f'-Note "route search batch: {", ".join(n for n,_ in names)}"')
    return 0


def do_score(root,plan,record_path):
    log=read_log(root);record=read_record(record_path)
    runs=record.get('runs') or {None:record}
    planned={e['name']:e for e in log if e.get('kind')=='planned'}
    for entry,run in runs.items():
        name=entry.split('::')[0] if entry else None
        if name not in planned: print(f'{entry}: not a planned candidate, skipped');continue
        if 'run_id' not in run:
            append_log(root,{'kind':'scored','name':name,'key':planned[name]['key'],'firm':planned[name]['firm'],'metrics':None,'decision':'discard','why':f"refused: {run.get('refused') or run.get('failure')}"})
            continue
        _,best=incumbent(read_log(root),plan['start'])
        metrics=metrics_of(root,run,plan['pool']);final=False
        if planned[name].get('pass')==2:
            first=[e for e in read_log(root) if e.get('kind')=='scored' and e['key']==planned[name]['key'] and e.get('decision')=='retest']
            if first and first[-1].get('metrics'): metrics=combined(first[-1]['metrics'],metrics);final=True
        decision,why=decide(metrics,best,plan['keep_margin'],final=final)
        append_log(root,{'kind':'scored','name':name,'key':planned[name]['key'],'firm':planned[name]['firm'],'metrics':metrics,'decision':decision,'why':why})
    batches=[e for e in read_log(root) if e.get('kind')=='batch']
    if batches and 'balance_after' not in batches[-1]:
        after=credits_balance();before=batches[-1].get('balance_before')
        append_log(root,{'kind':'batch_end','names':batches[-1]['names'],'balance_after':after,'spend':None if after is None or before is None else round(before-after,4)})
    return do_status(root,plan)


def do_status(root,plan):
    log=read_log(root);firm,best=incumbent(log,plan['start'])
    print('name | mathematician | engineer | researcher | director | mean | halves | found | false | faults | min | $ est | decision | why')
    for e in log:
        if e.get('kind')=='batch_end': print(f"batch {', '.join(e['names'])}: balance after {e['balance_after']}, spend {e['spend']} (OpenRouter credits)");continue
        if e.get('kind')!='scored': continue
        m=e['metrics'] or {};f=e['firm'];h=m.get('halves') or {}
        print(f"{e['name']} | {f['mathematician']} | {f['engineer']} | {f['researcher']} | {f['director']} | {m.get('mean_level','-')} | {h.get('first','-')}/{h.get('second','-')} | "
              f"{m.get('found','-')} | {m.get('false','-')} | {m.get('faults','-')} | {m.get('minutes','-')} | {m.get('cost','-')} | {e['decision']} | {e['why']}")
    print('incumbent: '+', '.join(f'{r} {firm[r]}' for r in ROLES)+(f" (mean {best['mean_level']}, found {best['found']})" if best else ' (not measured yet)'))
    return 0


def do_import(root,plan,run_id,firm_names):
    """One finished bench run as one more pass of a firm. The run must have used the same model files and the same bench set."""
    import sqlite3
    names=[x.strip() for x in firm_names.split(',')]
    if len(names)==1: names=names*4
    if len(names)!=4 or any(n not in plan['pool'] for n in names): raise SystemExit('--firm takes one pool name or four (director, researcher, mathematician, engineer)')
    firm=dict(zip(ROLES,names))
    db=sqlite3.connect(f"file:{(root/'state'/'research.sqlite').as_posix()}?mode=ro",uri=True)
    rows={phase:json.loads(rec) for phase,rec in db.execute('SELECT phase,record FROM engine_bounded_runs WHERE run_id=?',(run_id,))}
    if 'END' not in rows or 'report' not in rows['END']: raise SystemExit(f'{run_id}: no finished bench report')
    models=rows['START'].get('models') or {}
    for r in ROLES:
        if models.get(r,{}).get('model')!=plan['pool'][firm[r]]['model']: raise SystemExit(f'{run_id}: the {r} ran {models.get(r,{}).get("model")}, not {firm[r]}')
    end=rows['END'];roles=roles_of(root,run_id)
    run={'run_id':run_id,'reason':end['reason'],'requests':end['requests'],'elapsed_seconds':end['elapsed_seconds'],'report':end['report'],
         'cycles':[{'faults':[None]*sum(r['faults'] for r in (roles or {}).values())}]}
    metrics=metrics_of(root,run,plan['pool'])
    append_log(root,{'kind':'scored','name':f'import-{run_id}','key':firm_key(firm),'firm':firm,'metrics':metrics,'decision':'pass','why':'an earlier run of the same firm, imported'})
    print(f"imported {run_id} as a pass of "+', '.join(f'{r} {firm[r]}' for r in ROLES)+f" (mean {metrics['mean_level']})")
    return do_status(root,plan)


def do_roles(root,plan):
    """Each scored firm by role: model, calls, model minutes, output tokens and faults, so the owner sees which model earns its place in which role."""
    print('name | role | model | calls | model min | output tokens | faults')
    for e in read_log(root):
        if e.get('kind')!='scored' or not e.get('metrics') or not e['metrics'].get('roles'): continue
        for r in ROLES:
            row=e['metrics']['roles'][r]
            print(f"{e['name']} | {r} | {row['model']} | {row['calls']} | {round(row['seconds']/60,1)} | {row['output_tokens']} | {row['faults']}")
    return 0


def main(argv=None):
    parser=argparse.ArgumentParser(prog='tools/route_search.py')
    parser.add_argument('--project',type=Path,default=Path('.'))
    commands=parser.add_subparsers(dest='command',required=True)
    commands.add_parser('next');commands.add_parser('status');commands.add_parser('roles')
    score=commands.add_parser('score');score.add_argument('record')
    imported=commands.add_parser('import');imported.add_argument('run_id');imported.add_argument('--firm',required=True)
    args=parser.parse_args(argv);root=args.project.resolve();plan=load_plan(root)
    if args.command=='next': return do_next(root,plan)
    if args.command=='score': return do_score(root,plan,args.record)
    if args.command=='roles': return do_roles(root,plan)
    if args.command=='import': return do_import(root,plan,args.run_id,args.firm)
    return do_status(root,plan)


if __name__=='__main__': sys.exit(main())
