"""Run every routine test lane and answer CHECK: PASS or CHECK: FAIL. Rules: docs/TEST_RETENTION.md (2 November 2026)."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parent))
import run_tests  # noqa: E402

ROOT=run_tests.ROOT
HISTORY='check-history.jsonl'
PREFIX='check-'
FAILED='failed.json'
PRODUCT_TESTS=('acceptance','audit','bench','bench_run','compare','gepa','gepa_run','history_market','lessons','limits','practice','practice_run','preflight',
               'real_market','roles','run','sandbox','tail','transcripts','validator','library','library_multi','panel','libraries','measures')
PRODUCT_EXTRA=('tests/test_ai_models_interface.py','tests/test_pull_bars.py','tests/test_route_search.py','tests/test_update_indices.py')
TOOL_TESTS=('tests/test_run_tests_tool.py','tests/test_run_cost_tool.py','tests/test_base_eval.py','tests/test_clean_test_runs.py','tests/test_check_tool.py','tests/test_measure_study.py')
RESULTS=re.compile(r'^([.FEsxX]+)(?:\s+\[\s*\d+/\d+\])?\s*$')
COUNT=re.compile(r'\[\s*(\d+)/(\d+)\]\s*$')
LIGHT=frozenset({'harness','tools'})  # lanes that start no sandbox job; they run beside the sandbox lanes, which run one at a time


def lane_files(root=ROOT):
    engine=sorted(p.relative_to(root).as_posix() for p in (root/'tests').glob('test_engine_*.py'))
    harness=sorted(p.relative_to(root).as_posix() for p in (root/'tests').glob('test_harness_*.py'))
    return {'engine':('engine',engine+['tests/windows/test_harness_sandbox.py']),'product':('product',[f'tests/test_engine_{n}.py' for n in PRODUCT_TESTS]+list(PRODUCT_EXTRA)+[t for t in TOOL_TESTS if (root/t).is_file()]),
            'harness':('engine',harness),'tools':('engine',[t for t in TOOL_TESTS if (root/t).is_file()])}


def progress(text):
    """(done, total or None, failed) from pytest's -q output with the count style: each full line of results ends with [done/total]."""
    head=text.split('\n=',1)[0];lines=head.split('\n');done=0;total=None;failed=0
    for line in lines:
        marks=RESULTS.match(line)
        if not marks: continue
        failed+=sum(marks.group(1).count(x) for x in 'FE');count=COUNT.search(line)
        if count: done,total=int(count.group(1)),int(count.group(2))
        elif line is lines[-1]: done+=len(marks.group(1))
    return done,total,failed


def show_line(name,text,started):
    done,total,failed=progress(text);seconds=int(time.monotonic()-started)
    share=f'{done}/{total} tests ({100*done//total}%)' if total else f'{done} tests'
    return f"  {name}: {share}{f', {failed} failed' if failed else ''}, {seconds//60}:{seconds%60:02d} elapsed"


def run_lane(name,env,files,runs,live=False):
    job=runs/f"{PREFIX}{name}-{datetime.now():%Y%m%d-%H%M%S}";job.mkdir(parents=True)
    python=run_tests.ENVIRONMENTS[env]
    command=[str(python),'-m','pytest','-p','no:cacheprovider','--basetemp',str(job/'tmp'),'-q','-o','console_output_style=count',*files]
    started=time.monotonic();output=job/'output.txt'
    with open(output,'w',encoding='utf-8',newline='\n') as sink:
        process=subprocess.Popen(command,cwd=ROOT,stdout=sink,stderr=subprocess.STDOUT,env={**os.environ,'PYTHONUNBUFFERED':'1'})
        while process.poll() is None:
            if live: print('\r'+show_line(name,output.read_text(encoding='utf-8',errors='replace'),started).ljust(72),end='',flush=True)
            try: process.wait(timeout=2)
            except subprocess.TimeoutExpired: pass
        code=process.returncode
    if live: print('\r'+' '*72+'\r',end='',flush=True)
    text=output.read_text(encoding='utf-8',errors='replace')
    return {'lane':name,'env':env,'files':len(files),'exit_code':code,'summary':run_tests.summary_line(text),'passed':run_tests.passed(code,text),
            'seconds':round(time.monotonic()-started,1),'output_sha256':hashlib.sha256(text.encode('utf-8')).hexdigest(),'folder':job}


def settle(result,runs):
    job=result.pop('folder');row={**result,'run':job.name,'at':datetime.now().isoformat(timespec='seconds')}
    if result['passed']:
        run_tests.remove_tree(job)
        old=[p for p in runs.glob(f"{PREFIX}{result['lane']}-*") if p.is_dir() and not p.is_symlink() and (p/FAILED).is_file()]
        for folder in old: run_tests.remove_tree(folder)
        row['resolved_failures']=[p.name for p in old]
    else:
        (job/FAILED).write_text(json.dumps(row,indent=1),encoding='utf-8',newline='\n');row['evidence']=job.relative_to(ROOT).as_posix()
    with open(runs/HISTORY,'a',encoding='utf-8',newline='\n') as history: history.write(json.dumps(row,sort_keys=True)+'\n')
    return row


def main(argv=None,runs=None):
    parser=argparse.ArgumentParser(description='Run every routine test lane and answer PASS or FAIL.')
    parser.add_argument('--lanes',default='engine,product,harness,tools')
    args=parser.parse_args(argv)
    runs=Path(runs) if runs is not None else run_tests.TEST_RUNS;runs.mkdir(parents=True,exist_ok=True)
    lanes=lane_files();chosen=[name.strip() for name in args.lanes.split(',') if name.strip()]
    if not chosen or any(name not in lanes for name in chosen): raise SystemExit(f'refused: lanes must come from {sorted(lanes)}')
    gib=run_tests.free_gib()
    if gib<run_tests.FLOOR_GIB: raise SystemExit(f'refused: {gib:.1f} GiB free host memory, under the {run_tests.FLOOR_GIB} GiB floor')
    if run_tests.open_engine_runs(): raise SystemExit('refused: an engine run is open; the lanes use the sandbox')
    for name in chosen:
        if not run_tests.ENVIRONMENTS[lanes[name][0]].exists(): raise SystemExit(f'refused: environment missing for lane {name}')
    started=time.monotonic();results={}
    def report(name,result):
        results[name]=settle(result,runs);print(f"  {name}: {'pass' if results[name]['passed'] else 'FAIL'} - {results[name]['summary']}",flush=True)
    beside=[n for n in chosen if n in LIGHT];alone=[n for n in chosen if n not in LIGHT]
    with ThreadPoolExecutor(max_workers=max(len(beside),1)) as pool:
        pending={n:pool.submit(run_lane,n,*lanes[n],runs) for n in beside}
        for name in alone: report(name,run_lane(name,*lanes[name],runs,live=sys.stdout.isatty()))
        for name,future in pending.items(): report(name,future.result())
    rows=[results[n] for n in chosen]
    ok=all(r['passed'] for r in rows);minutes=(time.monotonic()-started)/60
    print(f"CHECK: {'PASS' if ok else 'FAIL'} ({', '.join(r['lane']+' '+str(r['summary']) for r in rows)}) in {minutes:.1f} min")
    if not ok: print('Evidence: '+', '.join(r['evidence'] for r in rows if not r['passed']))
    return 0 if ok else 1


if __name__=='__main__': sys.exit(main())
