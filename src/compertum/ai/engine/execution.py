"""The Engineer's only way to run code: `run_job` copies the agent's in-memory files into a fresh job folder and runs them in the E2 sandbox.

Before each run: the sandbox verification must hold, no freeze row may exist, and the one heavy-job slot must be free.
During each run the loopback watcher samples the sandbox process's TCP table. A loopback connection freezes the engine.
Every run, including every refusal, leaves one row in `engine_runs` before the result returns to the agent.
"""
import json
from pathlib import Path
from uuid import uuid4
from compertum.runtime.errors import RuntimeRefused
import threading
from compertum.runtime.jobs import hold_job_slot
from compertum.runtime.sandbox import LoopbackWatcher,REPARSE_POINT,require_verified,run_sandboxed

SANDBOX_LOCK=threading.Lock()

MAX_FILES,MAX_FILE_BYTES,MAX_TOTAL_BYTES=32,262144,262144
OUTPUT_HEAD=8192
SIGNALS_BYTES=1024*1024
RESERVED=frozenset({'train.csv','validation.csv','signals.csv','stdout.txt','stderr.txt','targets.json','probe.json'})
MIB=1024**2
SPEC_FILE='/spec.md'  # the Engineer's copy of the specification; never submitted with the code
CANDIDATES_PER_CYCLE=3  # at most this many candidates share one sandbox object (one cycle)


def head(raw):
    return raw[:OUTPUT_HEAD].decode('utf-8',errors='replace')


def job_files(files):
    """Agent paths (/main.py) to relative job paths. Text only, bounded, no reserved names, no escapes."""
    if not isinstance(files,dict) or not 1<=len(files)<=MAX_FILES: raise RuntimeRefused('ENGINE_FILES_DENIED')
    out={};total=0
    for path,content in files.items():
        if not isinstance(path,str) or not isinstance(content,str) or not path.startswith('/'): raise RuntimeRefused('ENGINE_FILES_DENIED')
        relative=path[1:];parts=relative.split('/')
        if (not relative or '\\' in relative or '\0' in relative or any(p in ('','.','..') or p.endswith(' ') or p.endswith('.') for p in parts)
                or len(parts)>4 or parts[-1].lower() in RESERVED or any(ch<' ' for ch in relative)):
            raise RuntimeRefused('ENGINE_FILES_DENIED')
        size=len(content.encode('utf-8'));total+=size
        if size>MAX_FILE_BYTES or total>MAX_TOTAL_BYTES: raise RuntimeRefused('ENGINE_FILES_DENIED')
        out[relative]=content
    return out


FORBIDDEN=(b'PermissionError',b'Access is denied',b'WinError 5')
DATA_TIERS=('train.csv','validation.csv')


def forbidden_access(stderr):
    """True when the job's stderr head shows a denied access.

    Inside its folder a job may read and write every file, so a denial usually is an attempt outside the folder: a fixed
    part, another job, the vault. Limits: on Windows, open() on a directory or deleting an open file inside the folder also
    raises PermissionError (a false freeze; the owner clears it). Code that catches the exception, prints no traceback or
    fills the 64 KiB stderr head first hides the attempt from this scan. The AppContainer is the boundary; this scan is
    evidence only.
    """
    return isinstance(stderr,(bytes,bytearray)) and any(marker in stderr for marker in FORBIDDEN)


def agent_paths(files):
    """Launch-record files (relative path -> text) back to the agent form (/path -> text) that job_files admits."""
    if not isinstance(files,dict) or not files: raise RuntimeRefused('ENGINE_RERUN_DENIED')
    return {'/'+relative:content for relative,content in files.items()}


def remove_data_tiers(job_folder):
    """Delete the data tier files from a finished job folder. The vault rerun calls this so no vault row stays on disk."""
    removed=[]
    for name in DATA_TIERS:
        path=Path(job_folder)/name
        if path.is_file(): path.unlink();removed.append(name)
    return removed


def read_signals(job):
    """Read signals.csv from a finished job folder. The folder is hostile: no reparse point, bounded size, text only."""
    path=job/'signals.csv'
    try: info=path.lstat()
    except FileNotFoundError: return None
    if info.st_file_attributes&REPARSE_POINT or not path.is_file() or info.st_size>SIGNALS_BYTES: raise RuntimeRefused('ENGINE_SIGNALS_INVALID')
    try: return path.read_bytes()[:SIGNALS_BYTES].decode('utf-8')
    except UnicodeError: raise RuntimeRefused('ENGINE_SIGNALS_INVALID') from None


class EngineerSandbox:
    """Runs Engineer jobs for one cycle. Holds the data tiers the Engineer may see: TRAIN and VALIDATION only."""
    def __init__(self,root,*,ledger,lease,verification,cycle_id,train_csv,validation_csv,memory_floor_bytes,seconds=120,memory_bytes=512*MIB,max_runs=3):
        require_verified(verification)
        self.root=Path(root).resolve(strict=True);self.ledger=ledger;self.lease=lease;self.cycle_id=cycle_id
        if not isinstance(train_csv,str) or not isinstance(validation_csv,str): raise RuntimeRefused('ENGINE_MARKET_DENIED')
        self.train_csv=train_csv;self.validation_csv=validation_csv
        self.memory_floor_bytes=memory_floor_bytes;self.seconds=seconds;self.memory_bytes=memory_bytes;self.max_runs=max_runs
        self.runs=[];self._candidate_start=0

    def begin_candidate(self):
        """A new candidate starts: it gets its own `max_runs` Engineer runs. Practice run 11 (25 October 2026) showed that one count for the whole cycle let
        the first candidate use every run and left the others `NO_SIGNALS`, while the prompt told each candidate it had three. The cycle total stays bounded."""
        self._candidate_start=len(self.runs)

    def _launched(self,runs):
        return sum(1 for r in runs if r['job_folder'] is not None and r['purpose']=='engineer')

    def run(self,files,entry):
        """One Engineer run. Returns the bounded record the agent may see. Raises ENGINE_FROZEN after writing the freeze row."""
        record=self._launch(files,entry,purpose='engineer',validation_csv=self.validation_csv,count_limit=True)
        return {k:record[k] for k in ('run_id','entry','status','stdout','stderr','signals_present')}|{'exit_code':(record['result'] or {}).get('exit_code'),'timed_out':(record['result'] or {}).get('timed_out')}

    def rerun_frozen(self,files,entry,*,purpose,validation_csv=None):
        """Trusted re-run of frozen code (stage E6). `files` is the `files` entry of an earlier launch record: the code exactly as
        the agent submitted it, never the job folder after the run. The Auditor reruns on VALIDATION (and on perturbed
        VALIDATION); the Validator reruns on the vault inside a sealed look. Not counted against the Engineer's run limit.
        Returns the full run record, with the signals."""
        if purpose not in ('audit','vault'): raise RuntimeRefused('ENGINE_RERUN_DENIED')
        return self._launch(agent_paths(files),entry,purpose=purpose,validation_csv=self.validation_csv if validation_csv is None else validation_csv,count_limit=False)

    def run_tool(self,code):
        """The analysis tool slot (26 October 2026): GEPA's tool program, run once in the sandbox. The job folder holds train.csv and a
        validation.csv with the header only, so the tool can never read a validation row. Returns the full run record."""
        header=self.validation_csv.split('\n',1)[0]+'\n'
        return self._launch({'/tool.py':code},'tool.py',purpose='tool',validation_csv=header,count_limit=False)

    def _launch(self,files,entry,*,purpose,validation_csv,count_limit):
        record={'run_id':str(uuid4()),'purpose':purpose,'entry':entry if isinstance(entry,str) else None,'status':None,'job_folder':None,'result':None,
                'watcher':None,'stdout':'','stderr':'','signals_present':False,'files':None}
        frozen=None;job=None
        try:
            self.ledger.require_unfrozen()
            if not isinstance(validation_csv,str): raise RuntimeRefused('ENGINE_MARKET_DENIED')
            # The limit counts launched Engineer jobs. A refused request never reaches the sandbox, so it does not use a run.
            if count_limit and (self._launched(self.runs[self._candidate_start:])>=self.max_runs
                                or self._launched(self.runs)>=self.max_runs*CANDIDATES_PER_CYCLE): raise RuntimeRefused('ENGINE_RUN_LIMIT')
            copied=job_files(files);record['files']=copied  # the code as submitted: the only source for reruns and promotion
            if not isinstance(entry,str) or entry not in copied or '/' in entry or not entry.endswith('.py'): raise RuntimeRefused('ENGINE_ENTRY_DENIED')
            job=self.root/f'job-{len(self.runs)+1:03d}-{uuid4().hex[:8]}';job.mkdir();record['job_folder']=str(job)
            for relative,content in copied.items():
                target=job/relative;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(content,encoding='utf-8',newline='\n')
            (job/'train.csv').write_text(self.train_csv,encoding='utf-8');(job/'validation.csv').write_text(validation_csv,encoding='utf-8')
            watcher=LoopbackWatcher()
            with SANDBOX_LOCK,hold_job_slot(self.lease,f'engine-{purpose}-job'):
                result=run_sandboxed(self.root,job,[entry],seconds=self.seconds,memory_bytes=self.memory_bytes,memory_floor_bytes=self.memory_floor_bytes,watcher=watcher)
            watched=watcher.record()
            record.update(result=result.record(),watcher=watched,stdout=head(result.stdout),stderr=head(result.stderr))
            # A seen connection freezes first, even if the watcher later failed. An unverified watcher without evidence is not a clean run.
            if watched['loopback_connections']:
                record['status']='FROZEN'
                frozen=self.ledger.freeze('LOOPBACK_CONNECTION',{'run_id':record['run_id'],'cycle_id':self.cycle_id,'job_folder':str(job),
                                                                 'connections':watched['loopback_connections'],'samples':watched['samples'],'watcher_error':watched['error']})
            elif forbidden_access(result.stderr):
                # A denied access is treated as an attempt outside the job folder (see forbidden_access for the limits).
                # Section 19: the run fails and the engine freezes. Only the owner clears a false freeze.
                record['status']='FORBIDDEN_ACCESS'
                frozen=self.ledger.freeze('FIXED_PART_ACCESS',{'run_id':record['run_id'],'cycle_id':self.cycle_id,'job_folder':str(job),'purpose':purpose,
                                                               'stderr_head':head(result.stderr)[:2048]})
            elif not watched['verified']: record['status']='WATCHER_UNVERIFIED'
            elif result.timed_out: record['status']='TIMED_OUT'
            elif result.disk_overrun: record['status']='DISK_OVERRUN'
            elif result.exit_code!=0: record['status']='FAILED'
            else:
                signals=read_signals(job);record['signals_present']=signals is not None;record['status']='COMPLETED'
                record['signals']=signals
        except RuntimeRefused as error:
            record['status']='REFUSED_'+error.code
        finally:
            self.runs.append(record);self.ledger.record_run(self.cycle_id,{k:v for k,v in record.items() if k!='signals'})
        if frozen is not None: raise RuntimeRefused('ENGINE_FROZEN')
        return record

    def completed_signals(self):
        """The signals from the last completed Engineer run, or None."""
        for record in reversed(self.runs):
            if record['purpose']=='engineer' and record['status']=='COMPLETED' and record.get('signals') is not None: return record['signals']
        return None

    def record_for(self,run_id):
        for record in self.runs:
            if record['run_id']==run_id: return record
        raise RuntimeRefused('ENGINE_RUN_UNKNOWN')


def run_job_tool(sandbox):
    """The Engineer's `run_job` tool bound to one EngineerSandbox. It reads the agent's files from the graph state."""
    from deepagents.backends.utils import file_data_to_string
    from langchain.tools import ToolRuntime,tool

    @tool
    def run_job(entry:str,runtime:ToolRuntime)->str:
        """Run one of your Python files in the sandbox. entry is the file name without a folder, for example main.py. The job folder also holds train.csv and validation.csv next to your file; open them by those names. The result has the status, the exit code, stdout, stderr, whether signals.csv was written, and what to do next. The job folder is not your file store: you cannot read signals.csv yourself; the result tells you about it."""
        files=runtime.state.get('files') or {}
        # /spec.md is the specification the Engineer reads, not part of the program: it is not submitted, rerun or promoted with the code.
        texts={path:file_data_to_string(fd) for path,fd in files.items() if path!=SPEC_FILE and isinstance(fd,dict) and fd.get('encoding','utf-8')=='utf-8'}
        result=sandbox.run(texts,entry)
        if result['signals_present']:
            rows=max((sandbox.runs[-1].get('signals') or '').count('\n')-1,0)
            result['next']=f'signals.csv was written with {rows} rows and is accepted. The job is complete. Do not search for the file. Reply with the single word DONE and one sentence about the program.'
        elif result['status']=='COMPLETED': result['next']='The program ran but wrote no signals.csv in its current folder. Fix the program (open files by their plain names, write signals.csv next to the program) and run it again.'
        else: result['next']='The run did not complete. Read stderr, fix the program with edit_file or write_file, and run it again.'
        return json.dumps(result,sort_keys=True)
    return run_job
