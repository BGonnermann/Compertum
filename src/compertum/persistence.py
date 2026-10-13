"""Native owner-checked SQLite stores, bounded checkpoints, durable receipts."""
from contextlib import contextmanager
from dataclasses import dataclass, asdict
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import time
from uuid import uuid4
from .events import canonical, prepare_event, validate_message, uuid
from .runtime.errors import RuntimeRefused
from .runtime.owners import _owner_scope, require_live_owner

STORE_NAMES={'coordinator':'research.sqlite','evaluation':'evaluation.sqlite','execution':'execution.sqlite'}
_STORES={}
MAX_SNAPSHOT_BYTES=16*1024*1024
MAX_EXPORT_ROWS=1024


def checked_path(root, path):
    root=Path(root).resolve(); path=Path(path).absolute()
    # Canonical native roots have an extended-length prefix; normalize spelling
    # before lexical containment without resolving any child reparse points.
    if os.name=='nt' and not str(root).startswith('\\\\?\\'): root=Path('\\\\?\\'+str(root))
    if os.name=='nt' and not str(path).startswith('\\\\?\\'):
        path=Path('\\\\?\\'+str(path))
    try: relative=path.relative_to(root)
    except ValueError: raise RuntimeRefused('PATH_DENIED') from None
    if not relative.parts or any(p in ('.','..') or ':' in p for p in relative.parts):
        raise RuntimeRefused('PATH_DENIED')
    current=root
    for part in relative.parts:
        current=current/part
        try: info=current.lstat()
        except FileNotFoundError: continue
        if current.is_symlink() or getattr(info,'st_file_attributes',0)&0x400 or (current.is_file() and info.st_nlink!=1):
            raise RuntimeRefused('PATH_DENIED')
    return path


@dataclass(frozen=True)
class EventReceipt:
    event_id: str
    sha256: str
    sequence: int
    role: str
    project_id: str


class StateStore:
    def __init__(self,lease,role,guard):
        self.lease=lease; self.role=role; self.root=guard.project.root_path
        self.path=_active_store_path(self.root,lease.project_id,role)
        self.closed=False; self.conn=None; self.pin=None
        for suffix in ('-wal','-shm'): checked_path(self.root,Path(str(self.path)+suffix))
        existed=self.path.exists()
        if existed:
            # Inspect first without changing journal mode or creating schema.
            check=None
            try:
                check=sqlite3.connect(self.path.as_uri()+'?mode=ro',uri=True,timeout=1)
                metadata=dict(check.execute('SELECT key,value FROM metadata'))
                if metadata!={'schema_version':'1','project_id':lease.project_id,'role':role}:
                    raise RuntimeRefused('STORE_IDENTITY_MISMATCH')
            except sqlite3.Error:
                raise RuntimeRefused('STORE_IDENTITY_MISMATCH') from None
            finally:
                if check is not None: check.close()
        try:
            if role=='evaluation':
                from .consumption import _provision, verify_consumption_guard
                from .evaluation_seals import _provision_seal_journal,verify_seal_journal
                if not existed:
                    # A surviving older consumption identity is not proof that a
                    # lost seal journal never existed. Do not regenerate authority.
                    consumption_existed=(self.root/'state/evaluation-consumption').exists()
                    seals_existed=(self.root/'state/evaluation-seals').exists()
                    if seals_existed and not consumption_existed:
                        raise RuntimeRefused('EVALUATION_COMPROMISED')
                    if consumption_existed and not seals_existed:
                        raise RuntimeRefused('SEAL_JOURNAL_COMPROMISED')
                    _provision(lease,guard.project)
                    _provision_seal_journal(lease,guard.project)
                if verify_seal_journal(guard.project)['status']!='VERIFIED':
                    raise RuntimeRefused('SEAL_JOURNAL_COMPROMISED')
                if verify_consumption_guard(guard.project)['status']!='VERIFIED':
                    raise RuntimeRefused('EVALUATION_COMPROMISED')
            self.conn=sqlite3.connect(self.path,timeout=1,check_same_thread=False)
            self.conn.execute('PRAGMA journal_mode=WAL'); self.conn.execute('PRAGMA synchronous=FULL')
            page=self.conn.execute('PRAGMA page_size').fetchone()[0]
            if self.conn.execute('PRAGMA page_count').fetchone()[0]*page>16*1024**2: raise RuntimeRefused('STORE_BOUND_EXCEEDED')
            self.conn.execute(f'PRAGMA max_page_count={16*1024**2//page}')
            self.conn.execute('PRAGMA wal_autocheckpoint=256');self.conn.execute('PRAGMA journal_size_limit=16777216')
            self.conn.execute('PRAGMA foreign_keys=ON'); self.conn.execute('PRAGMA busy_timeout=1000')
            self.conn.executescript('''
                CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY AUTOINCREMENT,event_id TEXT UNIQUE NOT NULL,sha256 TEXT NOT NULL,body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS outbox(event_id TEXT PRIMARY KEY REFERENCES events(event_id),ack TEXT);
                CREATE TABLE IF NOT EXISTS inbox(seq INTEGER PRIMARY KEY AUTOINCREMENT,event_id TEXT UNIQUE NOT NULL,sha256 TEXT NOT NULL,body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS state(key TEXT PRIMARY KEY,value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS attempts(run_id TEXT NOT NULL,task_id TEXT NOT NULL,attempt INTEGER NOT NULL,status TEXT NOT NULL,lineage TEXT NOT NULL,PRIMARY KEY(run_id,attempt));
                CREATE TABLE IF NOT EXISTS db_checkpoints(checkpoint_id TEXT PRIMARY KEY,barrier_id TEXT NOT NULL,generation INTEGER NOT NULL,instance TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS consumption(seal_id TEXT PRIMARY KEY,evaluation_id TEXT NOT NULL,body TEXT NOT NULL);
            ''')
            with self.conn:
                expected={'schema_version':'1','project_id':lease.project_id,'role':role}
                existing=dict(self.conn.execute('SELECT key,value FROM metadata'))
                if existing and existing!=expected: raise RuntimeRefused('STORE_IDENTITY_MISMATCH')
                for key,value in expected.items(): self.conn.execute('INSERT OR IGNORE INTO metadata VALUES(?,?)',(key,value))
                self.conn.execute("UPDATE attempts SET status='INTERRUPTED' WHERE status='RUNNING'")
            if role=='execution':
                from .fake_attempt_guard import initialize_attempt_guard,ZERO
                evidence=initialize_attempt_guard(lease,guard.project,fresh_store=not existed)
                if not existed and evidence['status']=='VERIFIED':
                    with self.conn:self.conn.execute("INSERT OR IGNORE INTO state VALUES('fake_attempt_guard_head',?)",(canonical({'sequence':0,'sha256':ZERO}).decode(),))
            self.pin=guard.api.open_file(self.path,0x80000000,3)
        except BaseException:
            self.close(); raise

    def close(self):
        if not self.closed:
            self.closed=True
            try:
                if self.conn is not None: self.conn.close()
            finally:
                if self.pin is not None: self.pin.close()
                if _STORES.get(self.lease) is self: _STORES.pop(self.lease,None)

    @contextmanager
    def _live(self):
        with _owner_scope(self.lease) as guard:
            if self.closed: raise RuntimeRefused('STORE_CLOSED')
            require_live_owner(self.lease,self.role)
            for suffix in ('','-wal','-shm'): checked_path(self.root,Path(str(self.path)+suffix))
            yield guard

    def _transition(self,message):
        if message['kind'] in {'FIXTURE_TRANSITION','CONTROL'}:
            payload=message['payload']
            if set(payload)!={'key','value'} or not isinstance(payload['key'],str) or not 1<=len(payload['key'])<=128:
                raise RuntimeRefused('TRANSITION_INVALID')
            validate_transition(payload)
            value=canonical(payload['value']).decode()
            self.conn.execute('INSERT INTO state VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(payload['key'],value))

    def commit_event(self,item):
        with self._live(),self.conn:
            message,digest=prepare_event(item,self.lease)
            previous=self.conn.execute('SELECT seq,sha256 FROM events WHERE event_id=?',(item['event_id'],)).fetchone()
            if previous:
                if previous[1]!=digest: raise RuntimeRefused('EVENT_CONFLICT')
                return EventReceipt(item['event_id'],digest,previous[0],self.role,self.lease.project_id)
            self._transition(message)
            cursor=self.conn.execute('INSERT INTO events(event_id,sha256,body) VALUES(?,?,?)',(item['event_id'],digest,canonical(message).decode()))
            self.conn.execute('INSERT INTO outbox VALUES(?,NULL)',(item['event_id'],))
            return EventReceipt(item['event_id'],digest,cursor.lastrowid,self.role,self.lease.project_id)

    def accept_message(self,message):
        with self._live(),self.conn:
            digest=validate_message(message,self.lease)
            if not message['replayable']: raise RuntimeRefused('NONREPLAYABLE_MESSAGE')
            previous=self.conn.execute('SELECT seq,sha256 FROM inbox WHERE event_id=?',(message['event_id'],)).fetchone()
            if previous:
                if previous[1]!=digest: raise RuntimeRefused('EVENT_CONFLICT')
                return EventReceipt(message['event_id'],digest,previous[0],self.role,self.lease.project_id)
            self._transition(message)
            cursor=self.conn.execute('INSERT INTO inbox(event_id,sha256,body) VALUES(?,?,?)',(message['event_id'],digest,canonical(message).decode()))
            return EventReceipt(message['event_id'],digest,cursor.lastrowid,self.role,self.lease.project_id)

    def acknowledge(self,event_id,receipt):
        with self._live(),self.conn:
            row=self.conn.execute('SELECT sha256,body FROM events WHERE event_id=?',(event_id,)).fetchone()
            if (not row or not isinstance(receipt,EventReceipt) or receipt.event_id!=event_id
                    or receipt.sha256!=row[0] or receipt.project_id!=self.lease.project_id
                    or receipt.role!=json.loads(row[1])['target_role']): raise RuntimeRefused('ACK_DENIED')
            self.conn.execute('UPDATE outbox SET ack=? WHERE event_id=?',(canonical(asdict(receipt)).decode(),event_id))

    def pending(self):
        with self._live():
            rows=self.conn.execute('SELECT body FROM events JOIN outbox USING(event_id) WHERE ack IS NULL ORDER BY seq LIMIT ?',(MAX_EXPORT_ROWS+1,)).fetchall()
            if len(rows)>MAX_EXPORT_ROWS: raise RuntimeRefused('CHECKPOINT_BOUND_EXCEEDED')
            return [json.loads(row[0]) for row in rows]

    def get_state(self,key):
        with self._live():
            row=self.conn.execute('SELECT value FROM state WHERE key=?',(key,)).fetchone()
            return json.loads(row[0]) if row else None

    def inspect(self):
        with self._live():
            return {'journal_mode':self.conn.execute('PRAGMA journal_mode').fetchone()[0],
                    'synchronous':self.conn.execute('PRAGMA synchronous').fetchone()[0],
                    'foreign_keys':self.conn.execute('PRAGMA foreign_keys').fetchone()[0],
                    'event_count':self.conn.execute('SELECT count(*) FROM events').fetchone()[0],
                    'inbox_count':self.conn.execute('SELECT count(*) FROM inbox').fetchone()[0]}

    def record_attempt(self,run_id,task_id,attempt,status,lineage):
        uuid(run_id); uuid(task_id)
        if type(attempt) is not int or not 1<=attempt<=2 or status not in {'RUNNING','PAUSED','COMPLETED','FAILED','INTERRUPTED','TIMED_OUT'}:
            raise RuntimeRefused('ATTEMPT_DENIED')
        raw=canonical(lineage).decode()
        with self._live(),self.conn:
            old=self.conn.execute('SELECT task_id,lineage FROM attempts WHERE run_id=? AND attempt=?',(run_id,attempt)).fetchone()
            if old and old!=(task_id,raw): raise RuntimeRefused('ATTEMPT_CONFLICT')
            self.conn.execute('INSERT INTO attempts VALUES(?,?,?,?,?) ON CONFLICT(run_id,attempt) DO UPDATE SET status=excluded.status',(run_id,task_id,attempt,status,raw))

    def attempts(self):
        with self._live():
            rows=self.conn.execute('SELECT run_id,task_id,attempt,status,lineage FROM attempts ORDER BY run_id,attempt LIMIT ?',(MAX_EXPORT_ROWS+1,)).fetchall()
            if len(rows)>MAX_EXPORT_ROWS: raise RuntimeRefused('CHECKPOINT_BOUND_EXCEEDED')
            return [dict(run_id=r[0],task_id=r[1],attempt=r[2],status=r[3],lineage=json.loads(r[4])) for r in rows]

    def consumption(self):
        with self._live(): return [json.loads(row[0]) for row in self.conn.execute('SELECT body FROM consumption ORDER BY seal_id')]

    def mirror_consumption(self,record):
        with self._live(),self.conn:
            require_live_owner(self.lease,'evaluation')
            raw=canonical(record).decode()
            old=self.conn.execute('SELECT body FROM consumption WHERE seal_id=?',(record['seal_id'],)).fetchone()
            if old and old[0]!=raw: raise RuntimeRefused('SEAL_ALREADY_CONSUMED')
            self.conn.execute('INSERT OR IGNORE INTO consumption VALUES(?,?,?)',(record['seal_id'],record['evaluation_id'],raw))

    def checkpoint(self,barrier_id,destination,*,maximum_bytes=MAX_SNAPSHOT_BYTES):
        uuid(barrier_id)
        if type(maximum_bytes) is not int or not 0<maximum_bytes<=MAX_SNAPSHOT_BYTES: raise RuntimeRefused('CHECKPOINT_BOUND_EXCEEDED')
        with self._live() as guard:
            destination=checked_path(self.root,destination)
            if destination.exists(): raise RuntimeRefused('CHECKPOINT_EXISTS')
            destination.parent.mkdir(parents=True,exist_ok=True)
            with guard.api.open_directory(destination.parent):
                checkpoint_id=str(uuid4())
                with self.conn:
                    self.conn.execute('INSERT INTO db_checkpoints VALUES(?,?,?,?)',(checkpoint_id,barrier_id,self.lease.generation,self.lease.identity.process_instance_id))
                if self.conn.execute('PRAGMA page_count').fetchone()[0]*self.conn.execute('PRAGMA page_size').fetchone()[0]>maximum_bytes:
                    raise RuntimeRefused('CHECKPOINT_BOUND_EXCEEDED')
                pending=self.pending(); attempts=self.attempts()
                inbox=self.conn.execute('SELECT event_id,sha256,seq FROM inbox ORDER BY seq LIMIT ?',(MAX_EXPORT_ROWS+1,)).fetchall()
                if len(inbox)>MAX_EXPORT_ROWS: raise RuntimeRefused('CHECKPOINT_BOUND_EXCEEDED')
                deadline=time.monotonic()+30
                def progress(status,remaining,total):
                    if time.monotonic()>deadline or total*4096>maximum_bytes: raise RuntimeRefused('CHECKPOINT_BOUND_EXCEEDED')
                # Exclusive create before SQLite opens it; never overwrite prior evidence.
                with destination.open('xb'): pass
                target=sqlite3.connect(destination)
                try:
                    self.conn.backup(target,pages=16,progress=progress,sleep=.01)
                    # Saved snapshots must be readable without creating WAL sidecars.
                    # Only the copy changes mode; the live owner remains WAL/FULL.
                    if target.execute('PRAGMA journal_mode=DELETE').fetchone()[0] != 'delete':
                        raise RuntimeRefused('CHECKPOINT_DURABILITY_UNVERIFIED')
                finally: target.close()
                with destination.open('r+b') as stream: stream.flush(); os.fsync(stream.fileno())
                size=destination.stat().st_size
                if size>maximum_bytes: raise RuntimeRefused('CHECKPOINT_BOUND_EXCEEDED')
                with destination.open('rb') as stream: digest=hashlib.file_digest(stream,'sha256').hexdigest()
                return {'checkpoint_id':checkpoint_id,'barrier_id':barrier_id,'role':self.role,'generation':self.lease.generation,'project_id':self.lease.project_id,
                        'path':str(destination.relative_to(self.root)),'size_bytes':size,'sha256':digest,'schema_version':1,
                        'event_high_water':self.conn.execute('SELECT coalesce(max(seq),0) FROM events').fetchone()[0],
                        'inbox_high_water':self.conn.execute('SELECT coalesce(max(seq),0) FROM inbox').fetchone()[0],
                        'pending':pending,'deduplication':[dict(event_id=r[0],sha256=r[1],sequence=r[2]) for r in inbox],'attempts':attempts}


def open_store(lease,db_role):
    require_live_owner(lease,db_role)
    if db_role not in STORE_NAMES: raise RuntimeRefused('WRONG_OWNER_ROLE')
    with _owner_scope(lease) as guard:
        if lease in _STORES: return _STORES[lease]
        store=StateStore(lease,db_role,guard)
        _STORES[lease]=store; guard.resources.append(store)
        return store


def _active_store_path(root,project_id,role):
    phase=root/'state/restore-operation.json';pointer=root/'state/active-generation.json'
    if phase.exists():
        from .runtime._windows import WindowsAPI
        record=json.loads(WindowsAPI().read_regular(checked_path(root,phase)))
        if record.get('status') not in {'PUBLISHED','ABORTED'}: raise RuntimeRefused('RESTORE_RECOVERY_REQUIRED')
    if not pointer.exists(): return checked_path(root,root/'state'/STORE_NAMES[role])
    from .runtime._windows import WindowsAPI
    value=json.loads(WindowsAPI().read_regular(checked_path(root,pointer)))
    if set(value)!={'schema_version','project_id','generation','operation_id'} or value['schema_version']!=1 or value['project_id']!=project_id:
        raise RuntimeRefused('RESTORE_RECOVERY_REQUIRED')
    uuid(value['generation']);uuid(value['operation_id'])
    path=checked_path(root,root/'state/generations'/value['generation']/STORE_NAMES[role])
    if not path.is_file(): raise RuntimeRefused('RESTORE_RECOVERY_REQUIRED')
    return path

def validate_transition(payload):
    # M0 message delivery has no control-plane authority. Controls use their
    # authenticated request ledger; fixture events only update fixture state.
    if not isinstance(payload,dict) or set(payload)!={'key','value'} or not isinstance(payload['key'],str) or not (payload['key']=='fixture' or payload['key'].startswith('fixture.')):
        raise RuntimeRefused('TRANSITION_AUTHORITY_DENIED')
