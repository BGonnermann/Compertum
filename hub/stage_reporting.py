"""Opt-in reports from actual work. The Hub calls only read_reports.

This module never starts a command, calculation, model, or operational loop.
"""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
import threading
from uuid import UUID, uuid4

from job_events import event_folder, project_key
from journal_snapshot import read_regular, SnapshotUnavailable
from process_watch import observe
from runtime_records import directory_project_id

METRICS = {
    'mathematics': {'checks_completed','checks_total','counterexamples'},
    'qualification': {'checks_passed','checks_failed','checks_total'},
    'signals': {'signals_count','blocked_count','items_checked'},
    'feedback': {'items_reviewed','revisions_requested','items_total'},
}
TERMINAL = {'Completed','Failed','Interrupted','Blocked'}
SPECIAL = {'mathematics': {'Counterexample found'}, 'qualification': {'Rejected'},
           'signals': {'No signal'}, 'feedback': {'Revision requested','No change'}}
SLOTS = 32
FIELDS = {'version','run_id','project','directory_identity','stage','kind','state','started_at',
          'observed_at','finished_at','pid','process_identity','metrics'}


def now(): return datetime.now(timezone.utc).isoformat()


def report_folder(root): return event_folder(root).parent / 'stage-reports'


def safe_folder(folder):
    for path in (folder,*folder.parents):
        if path.exists() and (path.is_symlink() or getattr(path.lstat(),'st_file_attributes',0)&0x400):
            raise SnapshotUnavailable()


def current_identity(root):
    return next((row['identity'] for row in observe(root,exclude_pids=set())['processes'] if row['pid']==os.getpid()),None)


def valid_metrics(stage,metrics):
    return isinstance(metrics,dict) and set(metrics)<=METRICS[stage] and all(type(value) is int and 0<=value<=10**9 for value in metrics.values())


class StageReport:
    """Wrap separately authorized work and publish only fixed reporting fields."""
    def __init__(self,root,stage,*,kind='engineering',folder=None):
        if stage not in METRICS or kind not in {'engineering','operational'}: raise ValueError('Invalid stage or work type')
        self.root=Path(root).absolute();self.stage=stage;self.kind=kind
        self.folder=Path(folder).absolute() if folder is not None else report_folder(self.root)
        self.available=False;self.target=None;self.value=None;self.thread=None
        self.lock=threading.Lock();self.stop=threading.Event();self.warned=False

    def unavailable(self):
        self.available=False;self.stop.set()
        if not self.warned:
            try: print('Stage reporting is unavailable. The original work continues.',file=sys.stderr)
            except OSError: pass
            self.warned=True

    def publish(self):
        if not self.available: return
        try:
            safe_folder(self.folder)
            # Refuse a changed slot or linked record before replacing it.
            read_regular(self.folder,self.target,8192)
            self.value['observed_at']=now()
            raw=(json.dumps(self.value,sort_keys=True)+'\n').encode()
            if len(raw)>8192: raise SnapshotUnavailable()
            pending=self.folder/(self.value['run_id']+'.pending')
            with pending.open('xb') as stream: stream.write(raw)
            pending.replace(self.target)
        except (OSError,ValueError): self.unavailable()

    def __enter__(self):
        try:
            safe_folder(self.folder);self.folder.mkdir(parents=True,exist_ok=True);safe_folder(self.folder)
            identity=directory_project_id(self.root)
            for index in range(SLOTS):
                target=self.folder/f'{self.stage}-{index:02}.json'
                try:
                    descriptor=os.open(target,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
                    os.close(descriptor);self.target=target;break
                except FileExistsError: continue
            if self.target is None: raise SnapshotUnavailable()
            at=now()
            self.value=dict(version=1,run_id=str(uuid4()),project=project_key(self.root),directory_identity=identity,
                            stage=self.stage,kind=self.kind,state='Running',started_at=at,observed_at=at,finished_at=None,
                            pid=os.getpid(),process_identity=current_identity(self.root),metrics={})
            self.available=True;self.publish()
            if self.available:
                self.thread=threading.Thread(target=self.heartbeat,name='compertum-stage-report',daemon=True);self.thread.start()
        except (OSError,ValueError): self.unavailable()
        return self

    def heartbeat(self):
        while not self.stop.wait(1):
            with self.lock:
                if self.value['state']=='Running': self.publish()

    def update(self,**metrics):
        if not valid_metrics(self.stage,metrics): raise ValueError('Invalid stage progress')
        with self.lock:
            if self.value is not None and self.value['state']=='Running':
                self.value['metrics'].update(metrics);self.publish()

    def bind_process(self,pid,identity):
        if type(pid) is not int or not 0<pid<2**32 or identity is not None and (not isinstance(identity,str) or not re.fullmatch(str(pid)+r'-\d+',identity)):
            raise ValueError('Invalid process identity')
        with self.lock:
            if self.value is not None and self.value['state']=='Running':
                self.value.update(pid=pid,process_identity=identity);self.publish()

    def finish(self,state='Completed',*,_force=False):
        if state not in TERMINAL|SPECIAL[self.stage]: raise ValueError('Invalid stage outcome')
        self.stop.set()
        if self.thread is not None and self.thread is not threading.current_thread(): self.thread.join(timeout=2)
        with self.lock:
            if self.value is not None and (self.value['state']=='Running' or _force):
                self.value.update(state=state,finished_at=now());self.publish()

    def __exit__(self,kind,error,traceback):
        self.finish('Interrupted' if kind is not None and issubclass(kind,KeyboardInterrupt) else 'Failed' if kind else 'Completed',_force=kind is not None)
        return False


def read_reports(root,processes,folder=None):
    root=Path(root).absolute();folder=Path(folder).absolute() if folder is not None else report_folder(root)
    result={'stages':{stage:dict(status='No report received',reports=[]) for stage in METRICS}}
    if not folder.exists(): return result
    try:
        safe_folder(folder)
        if not folder.is_dir():raise SnapshotUnavailable()
        expected=directory_project_id(root)
    except (OSError,ValueError):
        for row in result['stages'].values():row['status']='Report source unavailable'
        return result
    identities={row['identity'] for row in processes}
    for stage,target in result['stages'].items():
        invalid=False
        for index in range(SLOTS):
            path=folder/f'{stage}-{index:02}.json'
            if not path.exists():continue
            try:
                value=json.loads(read_regular(folder,path,8192))
                if not isinstance(value,dict) or set(value)!=FIELDS or type(value['version']) is not int or value['version']!=1:raise ValueError()
                if value['project']!=project_key(root) or value['directory_identity']!=expected or value['stage']!=stage:raise ValueError()
                if not isinstance(value['run_id'],str) or str(UUID(value['run_id']))!=value['run_id']:raise ValueError()
                if value['kind'] not in {'engineering','operational'} or value['state'] not in TERMINAL|SPECIAL[stage]|{'Running'}:raise ValueError()
                if type(value['pid']) is not int or not 0<value['pid']<2**32 or not valid_metrics(stage,value['metrics']):raise ValueError()
                identity=value['process_identity']
                if identity is not None and (not isinstance(identity,str) or not re.fullmatch(str(value['pid'])+r'-\d+',identity)):raise ValueError()
                at=datetime.fromisoformat(value['observed_at']);started=datetime.fromisoformat(value['started_at'])
                current=datetime.now(timezone.utc)
                if at.tzinfo is None or started.tzinfo is None or not started<=at<=current:raise ValueError()
                state=value['state']
                if state=='Running':
                    if value['finished_at'] is not None:raise ValueError()
                    if (current-at).total_seconds()>8:state='Stale observation'
                    elif identity not in identities:state='Process not verified'
                else:
                    finished=datetime.fromisoformat(value['finished_at'])
                    if finished.tzinfo is None or not started<=finished<=at:raise ValueError()
                target['reports'].append({key:value[key] for key in FIELDS-{'version','project','directory_identity'}}|{'state':state})
            except (OSError,ValueError,TypeError,KeyError,AttributeError):invalid=True
        target['reports'].sort(key=lambda row:row['observed_at'],reverse=True)
        if len(target['reports'])>12:invalid=True;target['reports']=target['reports'][:12]
        target['status']='Invalid or incomplete reports' if invalid else 'Stage reporting connected' if target['reports'] else 'No report received'
    return result
