"""Bounded run limits, the owner-set hard maximum, the run gate and the daily summary (section 19, "Bounded unattended runs").

Stage E5. No engine library. The product environment imports this module.

- The owner starts each run with a cycle limit or an hour limit. The run stops at the first limit it reaches.
- Each run states its AI request limit. The owner approves it when the run starts. `config/engine.toml` holds the hard
  maximum that caps every run's limit. Only the owner raises it, through a reviewed commit. 0 means unset: no run starts.
- The run gate runs before every model request and every cycle step. It refuses when the owner paused or stopped
  research (`research pause`, `research stop`), when the hour limit passed, or when a freeze row exists.
- The daily summary is plain text, private local evidence under `state/engine/`, never committed.
"""
from dataclasses import dataclass
from datetime import datetime,timezone
from pathlib import Path
import re
import time
import tomllib
from compertum.domain import ContractError,resolve_project_path
from compertum.runtime.errors import RuntimeRefused
from .ledger import RUN_ID
from .vault import CandidateQueue

SETTINGS_PATH='config/engine.toml'
MAX_SETTINGS_BYTES=16384
HARD_MAXIMUM_CEILING=10000  # the E1 client refuses any request limit above this
MAX_CYCLES=1000
MAX_HOURS=168
NOTE_LIMIT=1024
SUMMARY_BYTES=65536
SUMMARY_DIR='state/engine'
STOP_FILE='state/engine/STOP'  # the owner creates this file to stop a run; no lease needed
STOP_REASONS={'AI_REQUEST_BUDGET':'REQUEST_LIMIT','ENGINE_STOPPED':'KILL_SWITCH','ENGINE_HOUR_LIMIT':'HOUR_LIMIT','ENGINE_FROZEN':'FROZEN'}


def utc_now(): return datetime.now(timezone.utc).isoformat()


def load_run_settings(project_root,path=SETTINGS_PATH):
    """Read the bounded settings file inside the project. The only key is the owner's hard maximum."""
    root=Path(project_root).absolute()
    try:
        with resolve_project_path(path,root).open('rb') as stream: raw=stream.read(MAX_SETTINGS_BYTES+1)
    except ContractError as error: raise RuntimeRefused(error.reason) from None
    except OSError: raise RuntimeRefused('CONFIG_UNAVAILABLE') from None
    if len(raw)>MAX_SETTINGS_BYTES: raise RuntimeRefused('CONFIG_TOO_LARGE')
    try: supplied=tomllib.loads(raw.decode('utf-8'))
    except (UnicodeError,tomllib.TOMLDecodeError): raise RuntimeRefused('INVALID_CONFIG') from None
    run=supplied.get('run') if supplied.keys()=={'run'} else None
    if not isinstance(run,dict) or run.keys()!={'request_hard_maximum'}: raise RuntimeRefused('UNKNOWN_CONFIG_FIELD')
    value=run['request_hard_maximum']
    if type(value) is not int or not 0<=value<=HARD_MAXIMUM_CEILING: raise RuntimeRefused('INVALID_CONFIG')
    return {'request_hard_maximum':value,'path':path}


@dataclass(frozen=True)
class RunLimits:
    request_limit:int
    cycle_limit:int|None=None
    hour_limit:int|float|None=None


def check_limits(limits,hard_maximum):
    """Admit the owner's limits for one run. At least one of cycle or hour limit; the request limit never above the hard maximum."""
    if not isinstance(limits,RunLimits) or type(hard_maximum) is not int or hard_maximum<0: raise RuntimeRefused('ENGINE_RUN_LIMITS_DENIED')
    if hard_maximum==0: raise RuntimeRefused('ENGINE_HARD_MAXIMUM_UNSET')
    cycles,hours,requests=limits.cycle_limit,limits.hour_limit,limits.request_limit
    if cycles is None and hours is None: raise RuntimeRefused('ENGINE_RUN_LIMITS_DENIED')
    if cycles is not None and (type(cycles) is not int or not 1<=cycles<=MAX_CYCLES): raise RuntimeRefused('ENGINE_RUN_LIMITS_DENIED')
    if hours is not None and (type(hours) not in (int,float) or not 0<hours<=MAX_HOURS): raise RuntimeRefused('ENGINE_RUN_LIMITS_DENIED')
    if type(requests) is not int or not 1<=requests<=hard_maximum: raise RuntimeRefused('ENGINE_REQUEST_LIMIT_DENIED')
    return {'cycle_limit':cycles,'hour_limit':hours,'request_limit':requests,'request_hard_maximum':hard_maximum}


class RunGate:
    """The kill switch, the hour limit and the freeze, checked before every request and every step.

    Two kill switches, both read at every check:
    - The stop file `state/engine/STOP` inside the project. The owner creates it to stop a run and removes it before the
      next run. It needs no lease, so it works while the run process holds the coordinator owner lease.
    - The coordinator's research_state. `research pause` and `research stop` set it away from RUNNING when a Supervisor
      hosts the run; a standalone run reads it from its own store.
    A stop takes effect at the next request or step boundary; a request already in flight ends within its own timeout.
    """
    def __init__(self,store,ledger,*,project_root,hour_limit=None,clock=time.monotonic):
        if hour_limit is not None and (type(hour_limit) not in (int,float) or not 0<hour_limit<=MAX_HOURS): raise RuntimeRefused('ENGINE_RUN_LIMITS_DENIED')
        self.store=store;self.ledger=ledger;self.stop_file=Path(project_root).absolute()/STOP_FILE
        self.hour_limit=hour_limit;self.clock=clock;self.started=clock();self.checks=0;self.last_refusal=None;self.trigger=None

    def research_state(self):
        with self.store._live(): return self.store.get_state('research_state') or 'PAUSED'

    def stop_requested(self): return self.stop_file.exists()

    def elapsed_seconds(self): return self.clock()-self.started

    def __call__(self):
        self.checks+=1
        try:
            self.ledger.require_unfrozen()
            if self.stop_requested(): self.trigger='STOP_FILE';raise RuntimeRefused('ENGINE_STOPPED')
            if self.research_state()!='RUNNING': self.trigger='RESEARCH_STATE';raise RuntimeRefused('ENGINE_STOPPED')
            if self.hour_limit is not None and self.elapsed_seconds()>=self.hour_limit*3600: raise RuntimeRefused('ENGINE_HOUR_LIMIT')
        except RuntimeRefused as error:
            self.last_refusal=error.code;raise
        return True


def stop_reason(code):
    return STOP_REASONS.get(code,'STOPPED_'+code)


def summary_text(run,ledger,*,now=None):
    """Plain-English daily summary of one bounded run: cycles, ideas tried, results, failures, the queue, freezes, models."""
    limits=run['limits'];stamp=now or utc_now();lines=[]
    lines.append('Compertum engine daily summary')
    lines.append(f"Run {run['run_id']}. Written {stamp[:19]} UTC. Started {str(run['started_at'])[:19]} UTC.")
    status='still running' if run.get('reason') is None else f"ended, reason {run['reason']}"
    lines.append(f'Status: {status}.')
    parts=[]
    if limits.get('cycle_limit') is not None: parts.append(f"{limits['cycle_limit']} cycles")
    if limits.get('hour_limit') is not None: parts.append(f"{limits['hour_limit']} hours")
    parts.append(f"{limits['request_limit']} AI requests (hard maximum {limits['request_hard_maximum']})")
    lines.append('Limits: '+', '.join(parts)+'.')
    lines.append(f"Owner approval: {run['owner_approval']}")
    cycles=run.get('cycles') or [];elapsed=run.get('elapsed_seconds')
    lines.append(f"Progress: {len(cycles)} cycles completed in this run, {run.get('requests',0)} AI requests used"
                 +(f", {elapsed/60:.1f} minutes elapsed." if isinstance(elapsed,(int,float)) else '.'))
    lines.append('');lines.append('Ideas tried:')
    beat=rejected=deflated=failed=0;stops=[]
    for cycle in cycles:
        titles={h['id']:h['title'] for h in cycle.get('hypotheses') or [] if isinstance(h,dict)}
        if not cycle.get('candidates') and not titles: lines.append(f"- cycle {cycle['cycle_index']}: no hypotheses ({cycle['status']})")
        for hid,title in titles.items():
            candidate=next((c for c in cycle.get('candidates') or [] if c.get('hypothesis_id')==hid),None)
            if candidate is None: outcome='memo rejected or not specified'
            else:
                deflation=candidate.get('deflation') or {}
                outcome=f"{candidate.get('status')}"+(f", DSR {deflation.get('deflated_sharpe')} over {deflation.get('trials')} trials" if deflation else '')
                status=candidate.get('status')
                if status=='BEATS_BASELINE_PENDING_AUDIT': beat+=1
                elif status=='REJECTED_DEFLATED': deflated+=1
                elif status=='REJECTED': rejected+=1
                else: failed+=1
            lines.append(f"- cycle {cycle['cycle_index']}: {title[:120]} ({hid}): {outcome}")
        if cycle.get('stop_code'): stops.append(f"cycle {cycle['cycle_index']} stopped with {cycle['stop_code']}")
    lines.append('');lines.append('Results:')
    lines.append(f'- {beat} candidates beat the baseline and passed the deflation gate (audit pending).')
    lines.append(f'- {deflated} beat the baseline but failed the deflation gate. {rejected} did not beat the baseline. {failed} produced no valid signals.')
    lines.append('');lines.append('Failures:')
    run_statuses={}
    for cycle in cycles:
        for row in ledger.runs(cycle['cycle_id']):
            if row['status']!='COMPLETED': run_statuses[row['status']]=run_statuses.get(row['status'],0)+1
    for item in stops: lines.append('- '+item)
    for status,count in sorted(run_statuses.items()): lines.append(f'- {count} sandbox jobs ended {status}')
    if not stops and not run_statuses: lines.append('- none')
    queue=CandidateQueue(ledger).queued()
    lines.append('');lines.append('Queue: '+(', '.join(queue[:20])+(f' and {len(queue)-20} more' if len(queue)>20 else '') if queue else 'empty')+'.')
    freezes=ledger.active_freezes()
    lines.append('Freezes: '+(', '.join(f"{f['reason']} ({f['freeze_id']})" for f in freezes) if freezes else 'none')+'.')
    lines.append('');lines.append('Models used (as configured and verified by the client at each request):')
    for role,spec in sorted((run.get('models') or {}).items()): lines.append(f"- {role}: {spec['model']} at {spec['address']}")
    text='\n'.join(lines)+'\n'
    while len(text.encode('utf-8'))>SUMMARY_BYTES and len(lines)>12:
        # Drop the oldest "Ideas tried" line first. The header and the closing sections stay.
        index=next((i for i,l in enumerate(lines) if l.startswith('- cycle ')),None)
        if index is None: break
        del lines[index];text='\n'.join(lines)+'\n'
    return text


def write_summary(project_root,run,ledger,*,now=None):
    """Write the summary file for today under state/engine inside the project. One file per run and day, rewritten each time."""
    root=Path(project_root).absolute()
    if not isinstance(run.get('run_id'),str) or not re.fullmatch(RUN_ID,run['run_id']): raise RuntimeRefused('ENGINE_RECORD_DENIED')
    stamp=now or utc_now();folder=root/SUMMARY_DIR;folder.mkdir(parents=True,exist_ok=True)
    path=folder/f"summary-{run['run_id']}-{stamp[:10]}.md"
    text=summary_text(run,ledger,now=stamp)
    with path.open('w',encoding='utf-8',newline='\n') as stream: stream.write(text)
    return path
