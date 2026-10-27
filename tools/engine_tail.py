"""Watch a bounded engine run live, read-only.

    python tools/engine_tail.py [--project PATH] [--seconds 2] [--width 160] [--all-steps] [--no-text] [--replay] [--once]

Prints what happens as it happens, until Ctrl+C:
  RUN     a run starts (note, models, limits) or ends (reason, cycles, requests, time)
  CYCLE   a cycle starts or ends; at the end its level from 1 to 10 and one line per idea: its level, Sharpe against
          buy-and-hold, deflated Sharpe against the 0.95 gate, the Auditor's verdict and its title
  MODEL   one model call: role, time, tokens, and the start of the reply (from the saved transcript, 26 October 2026)
  SANDBOX a sandbox job: the Engineer's runs, and the analysis tool with the start of its report (--all-steps: the Auditor's reruns too)
  SCORE, AUDIT, GEPA and fault lines from the step records; --all-steps also shows every step request and reply
--replay first prints the latest run so far, without its model calls (the ledger keeps no time for a model call).

It opens the store read-only (SQLite URI mode=ro) and reads the transcript files; it takes no lease and changes nothing.
"""
import argparse
import json
from pathlib import Path
import re
import sqlite3
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT/'src') not in sys.path: sys.path.insert(0,str(ROOT/'src'))
from compertum.ai.engine.levels import LEVELS,candidate_level,cycle_level  # noqa: E402  (no engine library; reads records only)

TABLES=('engine_bounded_runs','engine_cycles','engine_steps','engine_runs','engine_model_calls')
TRANSCRIPTS='state/engine/transcripts'
QUIET=frozenset({'REQUEST','REPLY'})  # step phases that the MODEL lines already show
WAIT_PASSES=2  # a model call waits this many passes for its transcript line before it prints without the reply text
KEEP_LINES=2000  # transcript lines held while they wait for their model call
INDENT=' '*8  # idea lines under a CYCLE END line


def flat(text):
    """Model or record text on one line: every run of whitespace becomes one space."""
    return re.sub(r'\s+',' ',str(text if text is not None else '')).strip()


def clip(line,width):
    """A printed line, cut to width characters. Column padding is kept."""
    return line if len(line)<=width else line[:max(width-3,0)]+'...'


def number(value):
    try: return f'{float(value):.2f}'
    except (TypeError,ValueError): return '-'


def stamp(record): return str(record.get('recorded_at') or '')[11:19] or ' '*8


def run_line(run_id,phase,record):
    if phase=='START':
        models=sorted({str(m['model']) for m in (record.get('models') or {}).values() if isinstance(m,dict) and m.get('model')})
        limits=record.get('limits') or {}
        parts=[f"{limits.get('cycle_limit')} cycles" if limits.get('cycle_limit') else None,f"{limits.get('hour_limit')} hours" if limits.get('hour_limit') else None,
               f"{limits.get('request_limit')} requests" if limits.get('request_limit') else None]
        kind=record.get('kind') or record.get('purpose') or 'practice'
        return (f"RUN     {run_id} START {kind}: \"{flat(record.get('owner_approval'))}\" | models {', '.join(models) or '-'} | "
                f"limits {', '.join(p for p in parts if p) or '-'}")
    minutes=f"{float(record['elapsed_seconds'])/60:.0f} min" if record.get('elapsed_seconds') is not None else '-'
    transcript=record.get('transcript') or {}
    saved=f" | transcript {transcript.get('lines')} lines" if transcript else ''
    return f"RUN     {run_id} END {record.get('reason') or ''} | {record.get('cycles','-')} cycles, {record.get('requests','-')} requests, {minutes}{saved}"


def cycle_lines(index,phase,record):
    if phase=='START': return [f"CYCLE   #{index} START ({record.get('purpose') or 'practice'})"]
    try: level=cycle_level(record)
    except Exception: level=None  # an unfinished or unusual record still prints
    tool=record.get('tool') or {}
    lines=[f"CYCLE   #{index} END {record.get('status') or ''}"+(f" | level {level} of 10: {LEVELS.get(level,'')}" if level else '')
           +(f" | tool {tool.get('status')}" if tool else '')]
    titles={h.get('id'):flat(h.get('title')) for h in record.get('hypotheses') or [] if isinstance(h,dict)}
    scores=record.get('scores') or {};built=set()
    for candidate in record.get('candidates') or []:
        if not isinstance(candidate,dict): continue
        hid=candidate.get('hypothesis_id');built.add(hid);score=scores.get(hid) if isinstance(scores.get(hid),dict) else None
        try: parts=[f'level {candidate_level(candidate,score)}']
        except Exception: parts=[]
        parts.append(str(candidate.get('status')))
        if score: parts.append(f"Sharpe {number(score.get('sharpe'))} vs buy-and-hold {number(score.get('benchmark_sharpe'))}")
        if candidate.get('deflation'): parts.append(f"deflated {number(candidate['deflation'].get('deflated_sharpe'))} (gate 0.95)")
        if candidate.get('audit'): parts.append(f"Auditor {candidate['audit'].get('label')}")
        lines.append(f"{INDENT}{hid}: "+' | '.join(parts)+f" | \"{titles.get(hid,'untitled')}\"")
    for hid,decision in (record.get('decisions') or {}).items():
        if hid not in built and isinstance(decision,dict) and decision.get('decision')!='approve':
            lines.append(f"{INDENT}{hid}: not built ({flat(decision.get('reason'))}) | \"{titles.get(hid,'untitled')}\"")
    for fault in record.get('faults') or []:
        if isinstance(fault,dict): lines.append(f"{INDENT}fault: {fault.get('role')} {fault.get('kind')} {fault.get('code')}")
    return lines


def step_line(role,kind,record,all_steps=False):
    """One line for a step record, or None when another line already says it."""
    phase=record.get('phase') or ''
    who=record.get('hypothesis_id') or (record.get('candidate_id') or '').rsplit(':',1)[-1]
    if kind=='proposal':  # a GEPA rewrite of one part of the firm
        verdict='rewrote' if record.get('changed') else 'kept'
        return f"GEPA    {verdict} {role} ({phase}, {record.get('new_bytes')} bytes)"
    if kind=='score' and phase=='SCORED':
        score=record.get('score') or {};deflation=record.get('deflation') or {}
        return (f"SCORE   {who}: Sharpe {number(score.get('sharpe'))} vs buy-and-hold {number(score.get('benchmark_sharpe'))} | "
                f"deflated {number(deflation.get('deflated_sharpe'))} over {deflation.get('trials')} trials | {record.get('status')}")
    if kind=='audit': return f"AUDIT   {who}: {phase} {flat('; '.join((record.get('audit') or {}).get('reasons') or []))}".rstrip()
    if kind=='candidates': return f"STEP    {record.get('count')} ideas become candidates (each one is a counted trial)"
    if kind=='run' and role=='tool': return None  # the SANDBOX line shows the tool's run and report
    if phase in QUIET and not all_steps: return None
    detail=flat(record.get('code') or record.get('reason') or '')
    return f"STEP    {role:<13} {kind:<9} {phase:<14} {detail} {who}".rstrip()


def sandbox_line(record,all_steps=False):
    purpose=record.get('purpose') or '';status=record.get('status') or ''
    if purpose=='tool':
        report=record.get('stdout') if status=='COMPLETED' else record.get('stderr')
        return f"SANDBOX tool {status}: {flat(report)}"
    if purpose=='audit' and not all_steps: return None  # the AUDIT line gives the Auditor's verdict on its reruns
    result=record.get('result') or {}
    extra=' signals written' if record.get('signals_present') else (f" exit {result.get('exit_code')}" if result.get('exit_code') not in (None,0) else '')
    return f"SANDBOX {purpose} {record.get('entry') or ''} {status}{extra}"


def call_line(record,saved,text=True):
    usage=record.get('usage') or {};elapsed=record.get('elapsed_seconds')
    thinking=usage.get('reasoning_tokens')
    tokens=f"in {usage.get('prompt_tokens','?')} out {usage.get('completion_tokens','?')}"+(f" (thinking {thinking})" if thinking else '')
    purpose=str(record.get('purpose') or '')
    label=f"GEPA reflects on {purpose.removeprefix('gepa-reflect-')}" if purpose.startswith('gepa-reflect-') else str(record.get('role'))
    line=f"MODEL   {label:<13} {elapsed:5.1f}s {tokens}" if isinstance(elapsed,(int,float)) else f"MODEL   {label:<13} {tokens}"
    if record.get('status')!='COMPLETED': line+=f" | {record.get('status')}"
    if text and saved:
        calls=[str(c['name']) for c in saved.get('tool_calls') or [] if isinstance(c,dict) and c.get('name')]
        reply=('calls '+', '.join(calls)) if calls else flat(saved.get('content'))
        if reply: line+=' | '+reply
    return line


class Transcripts:
    """Reads new lines of the run's transcript file and keeps them by call_id until their MODEL line prints."""
    def __init__(self,project): self.folder=project/TRANSCRIPTS;self.offsets={};self.by_call={}

    def poll(self,run_id):
        if not run_id: return
        path=self.folder/f'{run_id}.jsonl'
        if not path.is_file(): return
        with path.open('rb') as stream:
            stream.seek(self.offsets.get(run_id,0));data=stream.read()
        end=data.rfind(b'\n')
        if end<0: return
        self.offsets[run_id]=self.offsets.get(run_id,0)+end+1
        for raw in data[:end+1].splitlines():
            try: line=json.loads(raw)
            except ValueError: continue
            if isinstance(line,dict) and line.get('call_id'): self.by_call[line['call_id']]=line
        while len(self.by_call)>KEEP_LINES: self.by_call.pop(next(iter(self.by_call)))  # lines from before the viewer started are never taken

    def take(self,call_id): return self.by_call.pop(call_id,None)


def rows_after(connection,table,last_rowid):
    return connection.execute(f'SELECT rowid,* FROM "{table}" WHERE rowid>? ORDER BY rowid',(last_rowid,)).fetchall()


def record_of(row):
    try: value=json.loads(row[-1])
    except (TypeError,ValueError): return {}
    return value if isinstance(value,dict) else {}


def main(argv=None):
    parser=argparse.ArgumentParser(prog='engine_tail',description='Read-only live view of the engine ledger and transcripts.')
    parser.add_argument('--project',type=Path,default=Path('.'));parser.add_argument('--seconds',type=float,default=2.0)
    parser.add_argument('--width',type=int,default=160,help='longest printed line, in characters')
    parser.add_argument('--all-steps',action='store_true',help='also print every step request and reply, and the Auditor\'s sandbox reruns')
    parser.add_argument('--no-text',action='store_true',help='do not print the start of each reply')
    parser.add_argument('--replay',action='store_true',help='print the latest run so far first (without its model calls), then follow')
    parser.add_argument('--once',action='store_true',help='print one pass and stop (with --replay: the latest run so far)')
    args=parser.parse_args(argv)
    project=args.project.resolve();path=project/'state'/'research.sqlite'
    if not path.is_file(): print(f'no store at {path}');return 2
    uri=path.as_uri()+'?mode=ro';last={table:0 for table in TABLES};first=True;run_id=None;since=None;pending=[]
    transcripts=Transcripts(project)
    print(f'watching {path} (read-only). Ctrl+C to stop.')
    try:
        while True:
            connection=sqlite3.connect(uri,uri=True,timeout=1);events=[]  # (time, lines): each pass prints in time order
            try:
                for table in TABLES:
                    try: rows=rows_after(connection,table,last[table])
                    except sqlite3.Error: continue
                    for row in rows:
                        last[table]=row[0];record=record_of(row);when=str(record.get('recorded_at') or '')
                        if table=='engine_bounded_runs':
                            if row[3]=='START': run_id=row[2];since=when
                            lines=[run_line(row[2],row[3],record)]
                        elif table=='engine_cycles': lines=cycle_lines(row[2],row[3],record)
                        elif table=='engine_steps': lines=[step_line(row[4],row[5],record,args.all_steps)]
                        elif table=='engine_runs': lines=[sandbox_line(record,args.all_steps)]
                        else:
                            if not first: pending.append([record,0])  # model calls carry no time; old ones are never replayed
                            continue
                        events.append((when,[clip(f'{stamp(record)} {line}',args.width) for line in lines if line]))
            finally: connection.close()
            if first:
                # The first pass only finds where the ledger ends. With --replay it prints the latest run so far, without its model calls.
                events=[e for e in events if args.replay and since is not None and e[0]>=since]
            out=[line for _,lines in sorted(events,key=lambda e:e[0]) for line in lines]
            # Model calls print after the pass's timed lines, once their transcript line has arrived or after WAIT_PASSES passes without it.
            transcripts.poll(run_id);still=[]
            for item in pending:
                saved=transcripts.take(item[0].get('call_id'))
                if saved is None and item[1]<WAIT_PASSES and not args.no_text: item[1]+=1;still.append(item);continue
                out.append(clip(' '*9+call_line(item[0],saved,text=not args.no_text),args.width))
            pending=still;first=False
            for line in out: print(line)
            sys.stdout.flush()
            if args.once: return 0
            time.sleep(args.seconds)
    except KeyboardInterrupt: return 0


if __name__=='__main__': sys.exit(main())
