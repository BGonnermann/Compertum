"""Fixed projections from explicit runtime roots. No product imports or controls."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import time
import ctypes as c
from ctypes import wintypes as w

from journal_snapshot import open_snapshot, read_regular, SnapshotUnavailable
from loop import STAGES

# Each source lists fixed table and column names. Never query a name from a record.
SOURCES = {
 'data': [('execution','state','key','value',"key LIKE 'paper_market_job:%' OR key LIKE 'paper_market_lineage_capture:%'"), ('coordinator','paper_read_routes','packet_id','body','1'),('coordinator','state','key','value',"key LIKE 'paper_market_route:%' OR key LIKE 'paper_market_lineage_route:%'")],
 'quality': [('coordinator','data_snapshot_receipts','task_id','receipt','1')],
 'proposals': [('coordinator','ai_tasks','task_id',None,'1')],
 'experiments': [('coordinator','baseline_runs','run_id','body','1')],
 'development_audit': [('coordinator','audit_runs','task_id','body','1')],
 'final_evaluation': [('coordinator','final_dispatches','attempt_id','body','1'),('coordinator','final_closures','attempt_id','body','1')],
 'independent_audit': [('coordinator','final_audit_runs','task_id','body','1')],
 'authorization': [('execution','paper_native_confirmations','confirmation_id','body','1')],
 'risk': [('execution','state','key','value',"key IN ('admission','armed','execution_health_halt')")],
 'intentions': [('execution','paper_native_intents','intent_id','body','1')],
 'execution': [('execution','fake_intents','intent_id','@state','1')],
 'reconciliation': [('coordinator','state','key','value',"key LIKE 'paper_activity_route:%'")],
 'reports': [('coordinator','campaign_reviews','task_id','body','1')],
}
NAMES = {'coordinator':'research.sqlite','evaluation':'evaluation.sqlite','execution':'execution.sqlite'}
STATES = {'PREPARING','PREPARED','READY','RUNNING','PAUSED','BLOCKED','COMPLETED','STOPPED','FAILED','INTERRUPTED',
          'PUBLISHED','AUTHORIZED','EVIDENCE_READY','ABORTED','CANCELED','CANCELLED','REJECTED','PENDING','WAITING','EXIT_UNVERIFIED',
          'OFFLINE_COMPONENT_VERIFIED','PROPOSED','CONFIRMED','PAPER_CONSUMED','DISARMED','ARMED','HALTED','HEALTHY','DISPATCH_RECORDED'}


def directory_project_id(root):
    """Match the product's existing volume and directory-file-ID identity."""
    class FileID(c.Structure):
        _fields_=[('volume',c.c_ulonglong),('file_id',c.c_ubyte*16)]
    kernel=c.WinDLL('kernel32',use_last_error=True)
    kernel.CreateFileW.argtypes=[w.LPCWSTR,w.DWORD,w.DWORD,c.c_void_p,w.DWORD,w.DWORD,w.HANDLE]
    kernel.CreateFileW.restype=w.HANDLE
    kernel.GetFileInformationByHandleEx.argtypes=[w.HANDLE,c.c_int,c.c_void_p,w.DWORD]
    kernel.GetFileInformationByHandleEx.restype=w.BOOL
    kernel.CloseHandle.argtypes=[w.HANDLE];kernel.CloseHandle.restype=w.BOOL
    handle=kernel.CreateFileW(str(root),0x80,7,None,3,0x02200000,None)
    if handle in (None,c.c_void_p(-1).value): raise SnapshotUnavailable()
    try:
        info=FileID()
        if not kernel.GetFileInformationByHandleEx(handle,18,c.byref(info),c.sizeof(info)): raise SnapshotUnavailable()
        return hashlib.sha256(b'compertum-project-v1\0'+info.volume.to_bytes(8,'little')+bytes(info.file_id)).hexdigest()
    finally: kernel.CloseHandle(handle)


def projection(stage,table,body):
    if body=='@state': return 'state,NULL'
    if body is None: return 'status,NULL'
    if stage=='risk' and table=='state':
        return "CASE WHEN json_valid(value) THEN CASE WHEN key='armed' AND json_type(value)='false' THEN 'DISARMED' WHEN key='armed' AND json_type(value)='true' THEN 'ARMED' WHEN json_type(value)='text' THEN json_extract(value,'$') END END,NULL"
    if table=='final_dispatches':
        return "CASE WHEN json_valid(body) THEN 'DISPATCH_RECORDED' END, CASE WHEN json_valid(body) THEN json_extract(body,'$.attempt.started_at') END"
    if table=='final_closures':
        return "CASE WHEN json_valid(body) THEN json_extract(body,'$.mode') END,NULL"
    return f"CASE WHEN json_valid({body}) THEN coalesce(json_extract({body},'$.state'),json_extract({body},'$.status'),json_extract({body},'$.publication.state')) END, CASE WHEN json_valid({body}) THEN coalesce(json_extract({body},'$.updated_at'),json_extract({body},'$.created_at')) END"


def source_time(value):
    try:
        at = datetime.fromisoformat(value.replace('Z','+00:00'))
        if at.tzinfo is None or at > datetime.now(timezone.utc): return None
        return at.isoformat()
    except (ValueError, TypeError, AttributeError): return None


def json_record(root, relative):
    value = json.loads(read_regular(root, root / relative, 8192))
    if not isinstance(value, dict): raise SnapshotUnavailable()
    return value


class RuntimeReader:
    def __init__(self, root, roots=None):
        self.root = Path(root).absolute()
        # These two known checkouts retain separate runtime identities. Never move either.
        self.test_root = self.root/'.cache/test-runs/native-fee-fresh-20261016-01/native-shared'
        self.roots = [Path(p).absolute() for p in roots] if roots is not None else [self.root, self.root.with_name('Compertum-development'), self.test_root]

    def snapshot(self, processes):
        now = datetime.now(timezone.utc).isoformat(); deadline = time.monotonic() + 3
        stages = {row[0]:dict(id=row[0],connection='No matching records',records=[],sources=[]) for row in STAGES}
        for stage in stages.values():
            if stage['id'] not in SOURCES: stage['connection'] = 'Reporting not implemented'
        runtimes = []
        for index, root in enumerate(self.roots[:4]):
            name = 'Master' if root == self.root else 'Original development runtime' if root == self.root.with_name('Compertum-development') else 'Approved native test runtime' if root==self.test_root else f'Configured runtime {index + 1}'
            runtime = dict(id=hashlib.sha256(str(root).casefold().encode()).hexdigest()[:12], name=name, status='Observed', journals=[])
            runtimes.append(runtime)
            try:
                if not root.is_dir():
                    runtime['status']='Runtime folder missing'; continue
                expected=directory_project_id(root)
                if (root/'state/restore-operation.json').exists() and json_record(root, 'state/restore-operation.json').get('status') not in {'PUBLISHED','ABORTED'}:
                    runtime['status']='Restore in progress; records uncertain'; continue
                generation = json_record(root,'state/active-generation.json') if (root/'state/active-generation.json').exists() else None
                folder = root/'state'
                if generation is not None:
                    if not re.fullmatch(r'[0-9a-f-]{36}', str(generation.get('generation',''))) or generation.get('schema_version') != 1:
                        runtime['status']='Generation pointer invalid'; continue
                    folder = folder/'generations'/generation['generation']
                if (root/'state/locks/coordinator.json').exists():
                    if json_record(root,'state/locks/coordinator.json').get('project_id') != expected:
                        runtime['journals']=[dict(role='coordinator',status='Identity mismatch')];continue
                if generation is not None:
                    if generation.get('project_id') != expected:
                        runtime['status']='Generation pointer invalid'; continue
                for role, filename in NAMES.items():
                    journal = dict(role=role,status='Missing journal'); runtime['journals'].append(journal)
                    path = folder/filename
                    if not path.exists(): continue
                    if time.monotonic() > deadline:
                        journal['status']='Read limit reached'; continue
                    try:
                        db = open_snapshot(root,path)
                        try:
                            meta = dict(db.execute('SELECT key,value FROM metadata LIMIT 8'))
                            if set(meta) != {'schema_version','project_id','role'} or meta.get('schema_version') != '1' or meta.get('role') != role or not re.fullmatch('[0-9a-f]{64}',str(meta.get('project_id',''))) or expected is not None and meta['project_id'] != expected:
                                journal['status']='Identity mismatch'; continue
                            journal['status']='Partial committed snapshot' if db.partial else 'Connected'
                            tables = {r[0] for r in db.execute("SELECT name FROM sqlite_schema WHERE type='table' LIMIT 256")}
                            for stage_id, sources in SOURCES.items():
                                for source_role, table, key, body, condition in sources:
                                    if source_role != role: continue
                                    source = dict(runtime=name,table=table,status='Table not present')
                                    stages[stage_id]['sources'].append(source)
                                    if table not in tables: continue
                                    try:
                                        columns = projection(stage_id,table,body)
                                        rows = db.execute(f'SELECT {key},{columns} FROM {table} WHERE {condition} ORDER BY 3 DESC,1 DESC LIMIT 13').fetchall()
                                        source['status']='Partial rows' if len(rows)>12 else 'Connected'
                                        stages[stage_id]['connection']='Connected'
                                        for identity, state, at in rows[:12]:
                                            state = state if isinstance(state,str) and state in STATES else None
                                            label = 'Saved running; current activity unconfirmed' if state=='RUNNING' else f'Saved: {state.lower().replace("_"," ")}' if state else 'Saved record; state unavailable'
                                            stages[stage_id]['records'].append(dict(record_id=hashlib.sha256(str(identity).encode()).hexdigest()[:12], runtime=name, state=label,source_at=source_time(at), observed_at=now,table=table,scope='Saved engineering or preparation evidence; no operational acceptance'))
                                    except sqlite3.Error: source['status']='Unsupported schema'
                        finally: db.close()
                    except sqlite3.Error: journal['status']='Unsupported journal schema'
                    except (SnapshotUnavailable, ValueError, TypeError): journal['status']='Unavailable or changing journal'
                halt = root/'state/watchdog/halt.json'
                if halt.exists():
                    read_regular(root,halt,65536)
                    runtime['retained_halt']=True
            except (SnapshotUnavailable, ValueError, TypeError, OSError): runtime['status']='Runtime metadata unavailable'
        for stage in stages.values():
            stage['records'].sort(key=lambda r:r['source_at'] or '',reverse=True)
            stage['records']=stage['records'][:12]
            if stage['id'] in SOURCES and stage['connection']!='Connected': stage['connection']='Records unavailable or source table not present'
            elif stage['id'] in SOURCES and any(s['status']!='Connected' for s in stage['sources']): stage['connection']='Partial record coverage'
        return dict(observed_at=now,runtimes=runtimes,stages=list(stages.values()),
                    note='Saved states are observations, not current liveness or financial acceptance. Missing source times are never inferred from file times.')
