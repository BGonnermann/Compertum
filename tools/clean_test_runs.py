"""Remove disposable test files under .cache/test-runs (docs/TEST_RETENTION.md).

    python tools/clean_test_runs.py --engine-sandboxes [--folder NAME ...] [--apply]

Without --apply it only reports. Each target keeps its top folder; only its contents go.
"""
import argparse
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0,str(Path(__file__).resolve().parent))
import run_tests  # noqa: E402

SANDBOX_PREFIX='engine-practice-'
KEEP=frozenset({'m5-local-economics-20261017-01'})
RECORDS='cleanup-records'


def queued_events(root):
    store,_=run_tests.engine_store(root)
    if not store.exists(): return 0
    connection=sqlite3.connect(store.as_uri()+'?mode=ro',uri=True,timeout=5)
    try:
        try: return connection.execute('SELECT COUNT(*) FROM engine_queue').fetchone()[0]
        except sqlite3.OperationalError as error:
            if 'no such table' in str(error): return 0
            raise
    finally: connection.close()


def choose(test_runs,folders,engine_sandboxes):
    chosen=[]
    if engine_sandboxes: chosen+=sorted(p for p in test_runs.iterdir() if p.is_dir() and not p.is_symlink() and p.name.startswith(SANDBOX_PREFIX))
    for name in folders:
        path=test_runs/name
        if name in KEEP or Path(name).name!=name or not path.is_dir() or path.is_symlink(): raise SystemExit(f'refused folder: {name}')
        chosen.append(path)
    return chosen


def empty(target):
    for entry in list(os.scandir(target)):
        if run_tests._is_link(entry): run_tests._remove_link(entry.path)
        elif entry.is_dir(follow_symlinks=False): run_tests.remove_tree(entry.path)
        else: os.unlink(entry.path)


def run(root,folders,engine_sandboxes,apply,open_runs=None,queued=None,free=None):
    test_runs=Path(root)/'.cache'/'test-runs'
    runs=run_tests.open_engine_runs(root) if open_runs is None else open_runs
    if runs: return {'refused':'an engine run is open','open_runs':runs}
    gib=run_tests.free_gib() if free is None else free
    if gib<run_tests.FLOOR_GIB: return {'refused':f'free memory {gib:.1f} GiB is below {run_tests.FLOOR_GIB} GiB'}
    events=queued_events(root) if queued is None else queued
    sandboxes=engine_sandboxes and events==0
    targets=[];removed={'files':0,'dirs':0,'bytes':0}
    for target in choose(test_runs,folders,sandboxes):
        found=run_tests.inventory(target);row={'folder':target.name,'files':found['files'],'dirs':found['dirs'],'bytes':found['bytes']}
        if found['links_outside']: row['skipped']='a link points outside the folder';targets.append(row);continue
        if apply:
            empty(target);row['removed']=not any(os.scandir(target))
            if row['removed']:
                for key in removed: removed[key]+=row[key]
        targets.append(row)
    record={'applied':apply,'at':datetime.now(timezone.utc).isoformat(),'targets':targets,'removed':removed,
            'engine_sandboxes':'skipped: the queue has events' if engine_sandboxes and not sandboxes else engine_sandboxes}
    if apply and targets:
        folder=test_runs/RECORDS;folder.mkdir(exist_ok=True)
        (folder/f"cleanup-{datetime.now():%Y%m%d-%H%M%S}.json").write_text(json.dumps(record,indent=1),encoding='utf-8',newline='\n')
    return record


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument('--engine-sandboxes',action='store_true');parser.add_argument('--folder',action='append',default=[]);parser.add_argument('--apply',action='store_true')
    args=parser.parse_args(argv)
    record=run(run_tests.ROOT,args.folder,args.engine_sandboxes,args.apply)
    print(json.dumps(record if 'refused' in record else {**record,'targets':len(record['targets'])}))
    return 2 if 'refused' in record else 0


if __name__=='__main__': raise SystemExit(main())
