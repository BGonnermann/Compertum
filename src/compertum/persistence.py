"""Sole-owner SQLite stores and atomic local message transitions."""
from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
import threading
from .domain import canonical,digest,ContractError,file_hash,now

DB_NAMES={'coordinator':'research.sqlite','evaluation':'evaluation.sqlite','execution':'execution.sqlite'}
class StateStore:
    def __init__(self,lease,db_role):
        lease.verify()
        if lease.role!=db_role or db_role not in DB_NAMES:raise ContractError('WRONG_DATABASE_OWNER')
        self.lease=lease;self.role=db_role;root=lease.project.root_path
        pointer=root/'state/active-recovery.json';operation=root/'state/restore-operation.json'
        if operation.exists():
            from .recovery import restore_admission
            if not restore_admission(root):raise ContractError('RESTORE_INCOMPLETE')
        if pointer.exists():
            from .domain import within
            self.path=within(root,json.loads(pointer.read_text())['path'])/DB_NAMES[db_role]
            if not self.path.is_file():raise ContractError('RESTORED_DATABASE_MISSING')
            try:
                probe=sqlite3.connect('file:'+str(self.path)+'?mode=ro',uri=True)
                try:
                    if probe.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ContractError('RESTORED_DATABASE_CORRUPT')
                    tables={r[0] for r in probe.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                    if not {'events','outbox','inbox','kv','requests','seals'}<=tables:raise ContractError('RESTORED_DATABASE_SCHEMA')
                finally:probe.close()
            except sqlite3.DatabaseError:raise ContractError('RESTORED_DATABASE_CORRUPT') from None
        else:self.path=root/'state'/DB_NAMES[db_role]
        self.db=sqlite3.connect(self.path,isolation_level=None,check_same_thread=False);self.lock=threading.RLock();self.depth=0
        self.db.executescript('PRAGMA journal_mode=WAL; PRAGMA synchronous=FULL; PRAGMA foreign_keys=ON; PRAGMA max_page_count=262144; CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY,event_id TEXT UNIQUE NOT NULL,kind TEXT NOT NULL,payload TEXT NOT NULL,hash TEXT NOT NULL); CREATE TABLE IF NOT EXISTS outbox(event_id TEXT PRIMARY KEY REFERENCES events(event_id),acked INTEGER NOT NULL DEFAULT 0); CREATE TABLE IF NOT EXISTS inbox(event_id TEXT PRIMARY KEY,hash TEXT NOT NULL,payload TEXT NOT NULL); CREATE TABLE IF NOT EXISTS kv(key TEXT PRIMARY KEY,value TEXT NOT NULL); CREATE TABLE IF NOT EXISTS requests(request_id TEXT PRIMARY KEY,subject TEXT,generation TEXT,hash TEXT,result TEXT); CREATE TABLE IF NOT EXISTS seals(seal_id TEXT PRIMARY KEY,status TEXT NOT NULL,evaluation_id TEXT);')
        self.db.execute('PRAGMA wal_autocheckpoint=100');self.db.execute('PRAGMA journal_size_limit=10485760')
    @contextmanager
    def transaction(self):
        self.lease.verify()
        with self.lock:
            outer=self.depth==0
            if outer:self.db.execute('BEGIN IMMEDIATE')
            self.depth+=1
            try:
                yield
                if outer:self.db.execute('COMMIT')
            except BaseException:
                if outer:self.db.execute('ROLLBACK')
                raise
            finally:self.depth-=1
    def _event(self,event):
        if set(event)!={'event_id','kind','payload'} or not isinstance(event['event_id'],str):raise ContractError('EVENT_SCHEMA')
        if event['kind'] not in {'TASK_STATUS','ARTIFACT_REGISTERED','BROKER_SIDE_EFFECT'}:raise ContractError('EVENT_KIND')
        if event['kind']=='BROKER_SIDE_EFFECT' and event['payload']!={'synthetic':True}:raise ContractError('M0_ONLY_SYNTHETIC')
        payload=canonical(event)
        if len(payload)>65536:raise ContractError('EVENT_CAPACITY')
        return payload.decode(),digest(event)
    def commit_event(self,event):
        payload,h=self._event(event)
        with self.transaction():
            old=self.db.execute('SELECT seq,hash FROM events WHERE event_id=?',(event['event_id'],)).fetchone()
            if old:
                if old[1]!=h:raise ContractError('EVENT_ID_REUSE')
                return {'event_id':event['event_id'],'sequence':old[0]}
            cursor=self.db.execute('INSERT INTO events(event_id,kind,payload,hash) VALUES(?,?,?,?)',(event['event_id'],event['kind'],payload,h))
            self.db.execute('INSERT INTO outbox(event_id) VALUES(?)',(event['event_id'],))
            return {'event_id':event['event_id'],'sequence':cursor.lastrowid}
    def accept_message(self,event):
        payload,h=self._event(event)
        if event['kind']=='BROKER_SIDE_EFFECT':raise ContractError('SIDE_EFFECT_NONREPLAYABLE')
        with self.transaction():
            old=self.db.execute('SELECT hash FROM inbox WHERE event_id=?',(event['event_id'],)).fetchone()
            if old:
                if old[0]!=h:raise ContractError('MESSAGE_ID_REUSE')
                return {'event_id':event['event_id'],'duplicate':True}
            self.db.execute('INSERT INTO inbox VALUES(?,?,?)',(event['event_id'],h,payload))
            # The event-driven fixture projection changes in this same transaction.
            count=self.get('accepted_transitions',0)
            self.set('accepted_transitions',count+1)
            self.set('last_safe_message',event)
            return {'event_id':event['event_id'],'duplicate':False}
    def acknowledge(self,event_id):
        with self.transaction():self.db.execute('UPDATE outbox SET acked=1 WHERE event_id=?',(event_id,))
    def event_count(self):
        with self.lock:return self.db.execute('SELECT count(*) FROM events').fetchone()[0]
    def accepted_count(self):
        with self.lock:return self.db.execute('SELECT count(*) FROM inbox').fetchone()[0]
    def set(self,key,value):
        payload=canonical(value)
        if len(payload)>65536:raise ContractError('STATE_CAPACITY')
        with self.transaction():self.db.execute('INSERT OR REPLACE INTO kv VALUES(?,?)',(key,payload.decode()))
    def get(self,key,default=None):
        with self.lock:row=self.db.execute('SELECT value FROM kv WHERE key=?',(key,)).fetchone()
        return json.loads(row[0]) if row else default
    def request_once(self,rid,subject,generation,payload,callback):
        h=digest(payload)
        with self.transaction():
            old=self.db.execute('SELECT subject,generation,hash,result FROM requests WHERE request_id=?',(rid,)).fetchone()
            if old:
                if old[:3]!=(subject,generation,h):raise ContractError('REQUEST_ID_REUSE')
                return json.loads(old[3])
            result=callback()
            payload=canonical(result)
            if len(payload)>65536:raise ContractError('CONTROL_RESULT_CAPACITY')
            self.db.execute('INSERT INTO requests VALUES(?,?,?,?,?)',(rid,subject,generation,h,payload.decode()))
            return result
    def checkpoint(self,barrier_id,destination):
        self.lease.verify();destination=Path(destination)
        if destination.exists() or not destination.resolve().is_relative_to(self.lease.project.root_path):raise ContractError('CHECKPOINT_TARGET')
        destination.parent.mkdir(parents=True,exist_ok=True)
        with self.lock:
            if self.depth:raise ContractError('CHECKPOINT_TRANSACTION_ACTIVE')
            backup=sqlite3.connect(destination)
            try:self.db.backup(backup);check=backup.execute('PRAGMA integrity_check').fetchone()[0]
            finally:backup.close()
            if check!='ok':raise ContractError('CHECKPOINT_CORRUPT')
            pending=[json.loads(r[0]) for r in self.db.execute('SELECT e.payload FROM events e JOIN outbox o USING(event_id) WHERE o.acked=0 ORDER BY e.seq')]
            inbox=[{'event_id':r[0],'hash':r[1]} for r in self.db.execute('SELECT event_id,hash FROM inbox ORDER BY event_id')]
            return {'role':self.role,'barrier_id':barrier_id,'path':str(destination.relative_to(self.lease.project.root_path)),'sha256':file_hash(destination),'schema':1,'generation':self.lease.generation,'process_instance_id':self.lease.process_instance_id,'outbox_high_water':self.db.execute('SELECT coalesce(max(seq),0) FROM events').fetchone()[0],'pending_messages':pending,'inbox':inbox,'inbox_high_water':len(inbox)}
    def close(self):self.db.close()

def open_store(lease,db_role):return StateStore(lease,db_role)
