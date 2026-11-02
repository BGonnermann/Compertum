"""Add up the model calls of one engine run from its saved transcript, read-only.

    python tools/run_cost.py [RUN_ID] [--project PATH]

Without RUN_ID it reads the newest transcript. One line per role and a total: calls, request seconds, prompt tokens,
cached prompt tokens, completion tokens, and the provider's cost in US dollars. The cost covers only the calls whose reply
reported one; the line says how many did. Transcripts from before 2 November 2026 hold no cost and no cached tokens.
"""
import argparse
import json
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parents[1]
TRANSCRIPTS='state/engine/transcripts'
RUN_ID=re.compile(r'run-\d{8}-[0-9a-f]{8}')
FIELDS=('calls','seconds','prompt','cached','completion','priced','cost')


def find_file(root,run_id):
    folder=Path(root)/TRANSCRIPTS
    if run_id is not None:
        if not RUN_ID.fullmatch(run_id): raise SystemExit(f'refused: not a run ID: {run_id}')
        path=folder/f'{run_id}.jsonl'
        if not path.is_file(): raise SystemExit(f'no transcript for {run_id}')
        return path
    files=sorted(folder.glob('run-*.jsonl'),key=lambda p:p.stat().st_mtime)
    if not files: raise SystemExit('no transcripts')
    return files[-1]


def add_up(lines):
    roles={}
    for line in lines:
        try: record=json.loads(line)
        except ValueError: continue
        if not isinstance(record,dict): continue
        row=roles.setdefault(str(record.get('role')),dict.fromkeys(FIELDS,0))
        row['calls']+=1
        seconds=record.get('elapsed_seconds')
        if isinstance(seconds,(int,float)): row['seconds']+=seconds
        usage=record.get('usage')
        if not isinstance(usage,dict): usage={}
        for field,key in (('prompt','prompt_tokens'),('cached','cached_tokens'),('completion','completion_tokens')):
            if type(usage.get(key)) is int: row[field]+=usage[key]
        cost=usage.get('cost')
        if isinstance(cost,(int,float)) and not isinstance(cost,bool):
            row['priced']+=1;row['cost']+=cost
    total=dict.fromkeys(FIELDS,0)
    for row in roles.values():
        for field in FIELDS: total[field]+=row[field]
    return roles,total


def show_row(name,row):
    cost=f"${row['cost']:.4f} ({row['priced']} of {row['calls']} calls priced)" if row['priced'] else 'no cost reported'
    cached=f"{row['cached']/row['prompt']:.0%}" if row['prompt'] else '-'
    return (f"{name:<14}{row['calls']:>6} calls {row['seconds']/60:>7.1f} min  prompt {row['prompt']:>10,}  cached {cached:>4}"
            f"  completion {row['completion']:>9,}  {cost}")


def main(argv=None):
    parser=argparse.ArgumentParser(description='Add up the model calls of one engine run, read-only.')
    parser.add_argument('run_id',nargs='?');parser.add_argument('--project',default=str(ROOT))
    args=parser.parse_args(argv)
    path=find_file(args.project,args.run_id)
    with open(path,encoding='utf-8') as source: roles,total=add_up(source)
    print(path.stem)
    for name in sorted(roles): print(show_row(name,roles[name]))
    print(show_row('total',total))
    return 0


if __name__=='__main__': sys.exit(main())
