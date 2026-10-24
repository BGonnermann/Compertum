"""The Engineer's only way to run code: `run_job` copies the agent's in-memory files into a fresh job folder and runs them in the E2 sandbox.

Before each run: the sandbox verification must hold, no freeze row may exist, and the one heavy-job slot must be free.
During each run the loopback watcher samples the sandbox process's TCP table. A loopback connection freezes the engine.
Every run, including every refusal, leaves one row in `engine_runs` before the result returns to the agent.
"""
import json
from pathlib import Path
from uuid import uuid4
from compertum.runtime.errors import RuntimeRefused
from compertum.runtime.jobs import hold_job_slot
from compertum.runtime.sandbox import LoopbackWatcher,REPARSE_POINT,require_verified,run_sandboxed

MAX_FILES,MAX_FILE_BYTES,MAX_TOTAL_BYTES=32,262144,262144
OUTPUT_HEAD=8192
SIGNALS_BYTES=1024*1024
RESERVED=frozenset({'train.csv','validation.csv','signals.csv','stdout.txt','stderr.txt','targets.json','probe.json'})
MIB=1024**2


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
        self.runs=[]

    def run(self,files,entry):
        """One sandbox run. Returns the bounded record the agent may see. Raises ENGINE_FROZEN after writing the freeze row."""
        record={'run_id':str(uuid4()),'entry':entry if isinstance(entry,str) else None,'status':None,'job_folder':None,'result':None,'watcher':None,
                'stdout':'','stderr':'','signals_present':False}
        frozen=None
        try:
            self.ledger.require_unfrozen()
            # The limit counts launched jobs. A refused request never reaches the sandbox, so it does not use a run.
            if sum(1 for r in self.runs if r['job_folder'] is not None)>=self.max_runs: raise RuntimeRefused('ENGINE_RUN_LIMIT')
            copied=job_files(files)
            if not isinstance(entry,str) or entry not in copied or '/' in entry or not entry.endswith('.py'): raise RuntimeRefused('ENGINE_ENTRY_DENIED')
            job=self.root/f'job-{len(self.runs)+1:03d}-{uuid4().hex[:8]}';job.mkdir();record['job_folder']=str(job)
            for relative,content in copied.items():
                target=job/relative;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(content,encoding='utf-8',newline='\n')
            (job/'train.csv').write_text(self.train_csv,encoding='utf-8');(job/'validation.csv').write_text(self.validation_csv,encoding='utf-8')
            watcher=LoopbackWatcher()
            with hold_job_slot(self.lease,'engine-engineer-job'):
                result=run_sandboxed(self.root,job,[entry],seconds=self.seconds,memory_bytes=self.memory_bytes,memory_floor_bytes=self.memory_floor_bytes,watcher=watcher)
            watched=watcher.record()
            record.update(result=result.record(),watcher=watched,stdout=head(result.stdout),stderr=head(result.stderr))
            # A seen connection freezes first, even if the watcher later failed. An unverified watcher without evidence is not a clean run.
            if watched['loopback_connections']:
                record['status']='FROZEN'
                frozen=self.ledger.freeze('LOOPBACK_CONNECTION',{'run_id':record['run_id'],'cycle_id':self.cycle_id,'job_folder':str(job),
                                                                 'connections':watched['loopback_connections'],'samples':watched['samples'],'watcher_error':watched['error']})
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
        return {k:record[k] for k in ('run_id','entry','status','stdout','stderr','signals_present')}|{'exit_code':(record['result'] or {}).get('exit_code'),'timed_out':(record['result'] or {}).get('timed_out')}

    def completed_signals(self):
        """The signals from the last completed run, or None."""
        for record in reversed(self.runs):
            if record['status']=='COMPLETED' and record.get('signals') is not None: return record['signals']
        return None


def run_job_tool(sandbox):
    """The Engineer's `run_job` tool bound to one EngineerSandbox. It reads the agent's files from the graph state."""
    from deepagents.backends.utils import file_data_to_string
    from langchain.tools import ToolRuntime,tool

    @tool
    def run_job(entry:str,runtime:ToolRuntime)->str:
        """Run one of your Python files in the sandbox. entry is the file name without a folder, for example main.py. The job folder also holds train.csv and validation.csv. The result has the status, the exit code, stdout and stderr."""
        files=runtime.state.get('files') or {}
        texts={path:file_data_to_string(fd) for path,fd in files.items() if isinstance(fd,dict) and fd.get('encoding','utf-8')=='utf-8'}
        return json.dumps(sandbox.run(texts,entry),sort_keys=True)
    return run_job
