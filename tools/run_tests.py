"""Run one pytest job in a fresh checked folder and clean its working files only if every test passed (owner decision, 25 October 2026).

    python tools/run_tests.py --name engine-lane --env engine -- tests/test_engine_bench.py -q
    python tools/run_tests.py --name econ --under m5-local-economics-20261017-01 -- tests/test_fixture_order_source.py -q

The job folder is `.cache/test-runs/<name>-<YYYYmmdd-HHMMSS>` (or inside the named existing folder under `.cache/test-runs`, for the economic
fixtures that admit only that folder). It holds:
    output.txt      the full pytest output, always kept
    tmp/            pytest's working files (--basetemp)
    retention.json  what happened to tmp/, always written

Rules from docs/TEST_RETENTION.md:
- tmp/ is removed only when pytest exited 0 and its summary line names no failure or error. Skips do not block cleanup.
- A failed, interrupted or unclear job keeps tmp/ as evidence. Nothing is removed.
- Links are removed as links. Their targets are never followed. A link whose target is outside tmp/ stops the cleanup, and tmp/ stays.
- The job folder, output.txt and retention.json stay.
- The job refuses to start below the free-memory floor, or while an engine run is open (engine tests share its sandbox profile).
This tool uses only the standard library and changes nothing outside its own job folder.
"""
import argparse
import ctypes
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
TEST_RUNS=ROOT/'.cache'/'test-runs'
ENVIRONMENTS={'product':ROOT/'.cache'/'clean-env-m0'/'Scripts'/'python.exe','engine':ROOT/'.cache'/'engine-env'/'Scripts'/'python.exe'}
FLOOR_GIB=8  # the owner's start floor for free host memory (8 GiB since 26 October 2026)
# Whole test files that never touch the sandbox profile. Only these may run while an engine run is open (--allow-during-run).
# 26 October 2026: test_engine_practice.py and test_engine_bench.py ran during bench baseline 1; their sandbox verification uses the same
# fixed profile as the run and could have refused a live job. No job was refused, by luck. A single test node (file::name) is the caller's choice.
SANDBOX_FREE={'tests/test_engine_preflight.py','tests/test_engine_lessons.py','tests/test_engine_limits.py','tests/test_engine_validator.py',
              'tests/test_engine_gepa.py','tests/test_engine_audit.py','tests/test_ai_models_interface.py','tests/test_run_tests_tool.py'}
NAME=re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,80}')


def sandbox_files(pytest_args):
    """Whole test files in the arguments that may use the sandbox profile: every tests/ file that is not in SANDBOX_FREE."""
    out=[]
    for arg in pytest_args:
        if arg.startswith('-') or '::' in arg: continue
        path=arg.replace('\\','/')
        if path.startswith('tests/') and path.endswith('.py') and path not in SANDBOX_FREE: out.append(arg)
        elif path.rstrip('/')=='tests': out.append(arg)
    return out
SUMMARY=re.compile(r'^=*\s*(.*\b(passed|failed|error|errors|skipped|no tests ran)\b.*?)\s*=*$')
BAD=re.compile(r'\b\d+ (failed|errors?|xpassed)\b|\bno tests ran\b|\binterrupted\b',re.I)


def free_gib():
    class Status(ctypes.Structure):
        _fields_=[('length',ctypes.c_uint32),('load',ctypes.c_uint32)]+[(n,ctypes.c_uint64) for n in ('total','available','page_total','page_available','virtual_total','virtual_available','extended')]
    value=Status();value.length=ctypes.sizeof(Status)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(value)): raise OSError('memory query failed')
    return value.available/1024**3


def open_engine_runs(root=ROOT):
    """Engine runs with a START row and no END row, read-only. A missing store means none."""
    store=root/'state'/'research.sqlite'
    if not store.exists(): return []
    connection=sqlite3.connect(store.as_uri()+'?mode=ro',uri=True,timeout=5)
    try:
        try: rows=[json.loads(r[0]) for r in connection.execute('SELECT record FROM engine_bounded_runs ORDER BY rowid')]
        except sqlite3.OperationalError: return []
    finally: connection.close()
    ended={r['run_id'] for r in rows if r.get('phase')=='END'}
    return [r['run_id'] for r in rows if r.get('phase')=='START' and r['run_id'] not in ended]


def summary_line(text):
    """pytest's last summary line, such as '12 passed, 1 skipped in 3.2s', or None."""
    for line in reversed(text.splitlines()):
        match=SUMMARY.match(line.strip())
        if match and re.search(r'\bin [\d.]+s\b',line): return match.group(1).strip()
    return None


def passed(exit_code,text):
    """True only for a complete passing job: exit 0 and a summary line with no failure, error or empty collection."""
    line=summary_line(text)
    return exit_code==0 and line is not None and BAD.search(line) is None and re.search(r'\b\d+ passed\b',line) is not None


def _is_link(entry):
    """A symbolic link or a junction (any reparse point). Never followed."""
    if entry.is_symlink(): return True
    info=entry.stat(follow_symlinks=False)
    return bool(getattr(info,'st_file_attributes',0)&stat.FILE_ATTRIBUTE_REPARSE_POINT)


def _link_target(path):
    try: target=os.readlink(path)
    except OSError: return None
    target=target.removeprefix('\\\\?\\')
    return Path(target) if os.path.isabs(target) else (Path(path).parent/target)


def inventory(tmp):
    """Every entry under tmp, without following links: (files, dirs, links, bytes, links_outside)."""
    tmp=Path(tmp);files=dirs=links=size=0;outside=[];stack=[tmp]
    base=os.path.normcase(os.path.abspath(tmp))
    while stack:
        with os.scandir(stack.pop()) as entries:
            for entry in entries:
                if _is_link(entry):
                    links+=1;target=_link_target(entry.path)
                    resolved=None if target is None else os.path.normcase(os.path.abspath(target))
                    if resolved is None or not (resolved==base or resolved.startswith(base+os.sep)): outside.append(entry.path)
                elif entry.is_dir(follow_symlinks=False): dirs+=1;stack.append(Path(entry.path))
                else: files+=1;size+=entry.stat(follow_symlinks=False).st_size
    return {'files':files,'dirs':dirs,'links':links,'bytes':size,'links_outside':outside}


def _remove_link(path):
    # A directory link or junction is removed with rmdir, which deletes the link itself; a file link with unlink.
    try: os.rmdir(path)
    except (NotADirectoryError,OSError): os.unlink(path)


def remove_tree(tmp):
    """Remove tmp and everything under it. Links first, as links; then files; then folders, deepest first."""
    tmp=Path(tmp);entries=[];stack=[tmp]
    while stack:
        with os.scandir(stack.pop()) as scan:
            for entry in scan:
                if _is_link(entry): entries.append(('link',entry.path))
                elif entry.is_dir(follow_symlinks=False): entries.append(('dir',entry.path));stack.append(Path(entry.path))
                else: entries.append(('file',entry.path))
    for kind,path in entries:
        if kind=='link': _remove_link(path)
    for kind,path in entries:
        if kind=='file':
            try: os.unlink(path)
            except PermissionError: os.chmod(path,stat.S_IWRITE);os.unlink(path)
    for path in sorted((p for k,p in entries if k=='dir'),key=len,reverse=True): os.rmdir(path)
    os.rmdir(tmp)


def clean(job,exit_code,text):
    """Decide and, for a passing job, remove job/tmp. Returns the retention record."""
    tmp=job/'tmp';record={'exit_code':exit_code,'summary':summary_line(text),'passed':passed(exit_code,text),'removed':False}
    if not tmp.exists(): record['reason']='no working folder';return record
    found=inventory(tmp);record['before']={k:v for k,v in found.items() if k!='links_outside'}
    if not record['passed']: record['reason']='the job did not pass completely; working files kept as evidence';return record
    if found['links_outside']:
        record['reason']='a link points outside the working folder; nothing removed';record['links_outside']=found['links_outside'][:20];return record
    remove_tree(tmp);record['removed']=not tmp.exists();record['reason']='complete passing job; working files removed (docs/TEST_RETENTION.md)'
    return record


def job_folder(name,under):
    if not NAME.fullmatch(name): raise SystemExit('refused: --name must be letters, digits, dot, dash or underscore')
    parent=TEST_RUNS
    if under is not None:
        parent=(TEST_RUNS/under)
        if not NAME.fullmatch(under) or not parent.is_dir() or parent.is_symlink(): raise SystemExit(f'refused: --under must name an existing folder under {TEST_RUNS}')
    job=parent/f'{name}-{datetime.now():%Y%m%d-%H%M%S}'
    if job.exists(): raise SystemExit(f'refused: {job} exists; never reuse a test folder')
    return job


def main(argv=None):
    parser=argparse.ArgumentParser(description='Run one pytest job in a fresh checked folder; clean its working files only if every test passed.')
    parser.add_argument('--name',required=True);parser.add_argument('--env',choices=sorted(ENVIRONMENTS),default='product')
    parser.add_argument('--under',help='an existing folder under .cache/test-runs to hold the job folder')
    parser.add_argument('--keep',action='store_true',help='keep the working files even if every test passed')
    parser.add_argument('--allow-during-run',action='store_true',help='run although an engine run is open (only for tests that use no sandbox)')
    parser.add_argument('pytest_args',nargs=argparse.REMAINDER)
    args=parser.parse_args(argv)
    pytest_args=args.pytest_args[1:] if args.pytest_args[:1]==['--'] else args.pytest_args
    if not pytest_args: raise SystemExit('refused: give the test files after --')
    if any(a.startswith('--basetemp') for a in pytest_args): raise SystemExit('refused: this tool sets --basetemp itself')
    free=free_gib()
    if free<FLOOR_GIB: raise SystemExit(f'refused: {free:.1f} GiB free host memory, under the {FLOOR_GIB} GiB floor')
    running=open_engine_runs()
    if running and not args.allow_during_run: raise SystemExit(f'refused: engine run open ({", ".join(running)}); engine tests share its sandbox profile')
    if running and sandbox_files(pytest_args): raise SystemExit(f'refused: engine run open; these files may use the sandbox profile: {", ".join(sandbox_files(pytest_args))}')
    python=ENVIRONMENTS[args.env]
    if not python.exists(): raise SystemExit(f'refused: environment missing: {python}')
    job=job_folder(args.name,args.under);job.mkdir(parents=True)
    output=job/'output.txt';command=[str(python),'-m','pytest','-p','no:cacheprovider','--basetemp',str(job/'tmp'),*pytest_args]
    started=time.monotonic();print(f'job folder: {job}',flush=True)
    with open(output,'w',encoding='utf-8',newline='\n') as sink:
        sink.write('command: '+' '.join(command)+'\n');sink.flush()
        process=subprocess.Popen(command,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace')
        try:
            for line in process.stdout or (): sink.write(line);sys.stdout.write(line)
            exit_code=process.wait()
        except KeyboardInterrupt:
            process.terminate();exit_code=process.wait();sink.write('\ninterrupted by the operator\n')
        sink.write(f'\nexit {exit_code}; elapsed {time.monotonic()-started:.1f} s\n')
    text=output.read_text(encoding='utf-8')
    record={'job':str(job.relative_to(ROOT)),'env':args.env,'command':command,'free_gib_at_start':round(free,1),
            'elapsed_seconds':round(time.monotonic()-started,1),'finished':datetime.now().isoformat(timespec='seconds')}
    if args.keep: record.update(exit_code=exit_code,summary=summary_line(text),passed=passed(exit_code,text),removed=False,reason='--keep given')
    else: record.update(clean(job,exit_code,text))
    record['output_sha256']=hashlib.sha256(output.read_bytes()).hexdigest()
    (job/'retention.json').write_text(json.dumps(record,indent=2),encoding='utf-8',newline='\n')
    print(f"\nresult: {record['summary']}. {record['reason']}. Record: {job/'retention.json'}")
    return exit_code


if __name__=='__main__': sys.exit(main())
