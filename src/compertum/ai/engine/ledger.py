"""Archivist tables for the engine: cycles, steps, sandbox runs and freezes. Rows are inserted once and never rewritten.

Section 19: the Archivist records each step, including rejected memos and failed runs. The engine never deletes or
rewrites a record. A freeze row stops every engine action until the owner clears it (the clearing command is stage E5 work).
"""
from datetime import datetime,timezone
import re
import sqlite3
from uuid import uuid4
from compertum.events import canonical
from compertum.runtime.errors import RuntimeRefused
from ..manual import read_json

MAX_SUMMARY_CYCLES=20
SUMMARY_BYTES=16384
MAX_EXTERNAL_TRIALS=100000
QUEUE_EVENTS=('QUEUED','DENIED','LOOK_COUNTED','VAULT_EVALUATED')
RUN_ID=r'run-[0-9]{8}-[0-9a-f]{8}'


def now():
    return datetime.now(timezone.utc).isoformat()


class EngineLedger:
    def __init__(self,store):
        self.store=store
        with self.store._live(),self.store.conn:
            self.store.conn.executescript('''
                CREATE TABLE IF NOT EXISTS engine_cycles(cycle_id TEXT PRIMARY KEY,cycle_index INTEGER NOT NULL,phase TEXT NOT NULL,record TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS engine_steps(step_id TEXT PRIMARY KEY,cycle_id TEXT NOT NULL,step_index INTEGER NOT NULL,role TEXT NOT NULL,kind TEXT NOT NULL,record TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS engine_runs(run_id TEXT PRIMARY KEY,cycle_id TEXT NOT NULL,status TEXT NOT NULL,record TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS engine_freeze(freeze_id TEXT PRIMARY KEY,created_at TEXT NOT NULL,reason TEXT NOT NULL,cleared_at TEXT,record TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS engine_trials(trial_id TEXT PRIMARY KEY,source TEXT NOT NULL,count INTEGER NOT NULL,recorded_at TEXT NOT NULL,record TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS engine_trial_scores(trial_id TEXT PRIMARY KEY,recorded_at TEXT NOT NULL,record TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS engine_queue(event_id TEXT PRIMARY KEY,candidate_id TEXT NOT NULL,event TEXT NOT NULL,recorded_at TEXT NOT NULL,record TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS engine_looks(look_id TEXT PRIMARY KEY,seal_sha256 TEXT NOT NULL,created_at TEXT NOT NULL,record TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS engine_bounded_runs(row_id TEXT PRIMARY KEY,run_id TEXT NOT NULL,phase TEXT NOT NULL,recorded_at TEXT NOT NULL,record TEXT NOT NULL);
            ''')

    def _insert(self,sql,values):
        with self.store._live(),self.store.conn: self.store.conn.execute(sql,values)

    def _rows(self,sql,values=()):
        with self.store._live(): return [read_json(row[0]) for row in self.store.conn.execute(sql,values)]

    def record_cycle(self,cycle_id,cycle_index,phase,record):
        if phase not in ('START','END'): raise RuntimeRefused('ENGINE_RECORD_DENIED')
        row={'cycle_id':cycle_id,'cycle_index':cycle_index,'phase':phase,'recorded_at':now(),**record}
        self._insert('INSERT INTO engine_cycles VALUES(?,?,?,?)',(f'{cycle_id}:{phase}',cycle_index,phase,canonical(row).decode()));return row

    def record_step(self,cycle_id,step_index,role,kind,record):
        if type(step_index) is not int or not isinstance(role,str) or not isinstance(kind,str): raise RuntimeRefused('ENGINE_RECORD_DENIED')
        row={'step_id':str(uuid4()),'cycle_id':cycle_id,'step_index':step_index,'role':role,'kind':kind,'recorded_at':now(),**record}
        self._insert('INSERT INTO engine_steps VALUES(?,?,?,?,?,?)',(row['step_id'],cycle_id,step_index,role,kind,canonical(row).decode()));return row

    def record_run(self,cycle_id,record):
        row={'cycle_id':cycle_id,'recorded_at':now(),**record}
        self._insert('INSERT INTO engine_runs VALUES(?,?,?,?)',(row['run_id'],cycle_id,row['status'],canonical(row).decode()));return row

    def freeze(self,reason,evidence):
        """Write a freeze row. Only the owner clears it. Section 19: an escape attempt or a write to a fixed part stops the run."""
        if not isinstance(reason,str) or not 1<=len(reason)<=64: raise RuntimeRefused('ENGINE_RECORD_DENIED')
        row={'freeze_id':str(uuid4()),'created_at':now(),'reason':reason,'cleared_at':None,'evidence':evidence}
        self._insert('INSERT INTO engine_freeze VALUES(?,?,?,?,?)',(row['freeze_id'],row['created_at'],reason,None,canonical(row).decode()));return row

    def active_freezes(self):
        return self._rows('SELECT record FROM engine_freeze WHERE cleared_at IS NULL ORDER BY rowid')

    def require_unfrozen(self):
        frozen=self.active_freezes()
        if frozen: raise RuntimeRefused('ENGINE_FROZEN')
        return True

    def clear_freeze(self,freeze_id,owner_note):
        """Owner action. Marks one freeze as cleared and keeps the original row. Stage E5 gives this a command."""
        if not isinstance(owner_note,str) or not 1<=len(owner_note)<=1024: raise RuntimeRefused('ENGINE_RECORD_DENIED')
        with self.store._live(),self.store.conn:
            rows=self.store.conn.execute('SELECT record FROM engine_freeze WHERE freeze_id=? AND cleared_at IS NULL',(freeze_id,)).fetchall()
            if len(rows)!=1: raise RuntimeRefused('ENGINE_FREEZE_UNKNOWN')
            record=read_json(rows[0][0]);cleared=now();record.update(cleared_at=cleared,owner_note=owner_note)
            self.store.conn.execute('UPDATE engine_freeze SET cleared_at=?,record=? WHERE freeze_id=?',(cleared,canonical(record).decode(),freeze_id))
        return record

    # Stage E4: trials, trial scores, the candidate queue and vault looks. All insert-only.
    def _insert_once(self,sql,values,code):
        try: self._insert(sql,values)
        except sqlite3.IntegrityError: raise RuntimeRefused(code) from None

    def record_trial(self,cycle_id,candidate_id,record):
        """One engine candidate is one trial, counted when the cycle records its candidate list, before any run."""
        if not isinstance(cycle_id,str) or not isinstance(candidate_id,str) or not 1<=len(candidate_id)<=128: raise RuntimeRefused('ENGINE_RECORD_DENIED')
        row={'trial_id':candidate_id,'cycle_id':cycle_id,'candidate_id':candidate_id,'source':'engine','count':1,'recorded_at':now(),**record}
        self._insert_once('INSERT INTO engine_trials VALUES(?,?,?,?,?)',(candidate_id,'engine',1,row['recorded_at'],canonical(row).decode()),'ENGINE_TRIAL_DUPLICATE');return row

    def record_external_trials(self,source,count,evidence):
        """Trials from other campaigns (for example the fixed family of 12 in a registered campaign). One row per source, never repeated."""
        if not isinstance(source,str) or not re.fullmatch(r'[A-Za-z0-9._:-]{1,128}',source) or type(count) is not int or not 1<=count<=MAX_EXTERNAL_TRIALS: raise RuntimeRefused('ENGINE_RECORD_DENIED')
        row={'trial_id':f'external:{source}','source':source,'count':count,'recorded_at':now(),'evidence':evidence}
        self._insert_once('INSERT INTO engine_trials VALUES(?,?,?,?,?)',(row['trial_id'],source,count,row['recorded_at'],canonical(row).decode()),'ENGINE_TRIAL_DUPLICATE');return row

    def total_trials(self):
        with self.store._live(): value=self.store.conn.execute('SELECT COALESCE(SUM(count),0) FROM engine_trials').fetchone()[0]
        return int(value)

    def record_trial_score(self,candidate_id,record):
        """The Validator's per-period Sharpe ratio for one engine trial, recorded once. A trial without a score stays counted."""
        with self.store._live(): known=self.store.conn.execute('SELECT COUNT(*) FROM engine_trials WHERE trial_id=? AND source=?',(candidate_id,'engine')).fetchone()[0]
        if known!=1: raise RuntimeRefused('ENGINE_TRIAL_UNKNOWN')
        row={'trial_id':candidate_id,'recorded_at':now(),**record}
        self._insert_once('INSERT INTO engine_trial_scores VALUES(?,?,?)',(candidate_id,row['recorded_at'],canonical(row).decode()),'ENGINE_TRIAL_DUPLICATE');return row

    def trial_sharpes(self):
        """Per-period Sharpe ratios of the scored trials, as recorded (strings), None entries excluded."""
        return [r['sharpe_per_period'] for r in self._rows('SELECT record FROM engine_trial_scores ORDER BY rowid') if r.get('sharpe_per_period') is not None]

    def record_queue_event(self,candidate_id,event,record):
        if not isinstance(candidate_id,str) or not 1<=len(candidate_id)<=128 or event not in QUEUE_EVENTS: raise RuntimeRefused('ENGINE_RECORD_DENIED')
        row={'event_id':str(uuid4()),'candidate_id':candidate_id,'event':event,'recorded_at':now(),**record}
        self._insert('INSERT INTO engine_queue VALUES(?,?,?,?,?)',(row['event_id'],candidate_id,event,row['recorded_at'],canonical(row).decode()));return row

    def queue_events(self,candidate_id=None):
        if candidate_id is None: return self._rows('SELECT record FROM engine_queue ORDER BY rowid')
        return self._rows('SELECT record FROM engine_queue WHERE candidate_id=? ORDER BY rowid',(candidate_id,))

    def record_look(self,look_id,seal_sha256,record,counted=()):
        """The vault look is counted here, before any vault data is read. The look row and the LOOK_COUNTED events of
        `counted` ([(candidate_id, record), ...]) are one transaction: all rows exist, or none."""
        if not isinstance(look_id,str) or not isinstance(seal_sha256,str) or not re.fullmatch(r'[0-9a-f]{64}',seal_sha256): raise RuntimeRefused('ENGINE_RECORD_DENIED')
        if any(not isinstance(cid,str) or not 1<=len(cid)<=128 or not isinstance(extra,dict) for cid,extra in counted): raise RuntimeRefused('ENGINE_RECORD_DENIED')
        stamp=now();row={'look_id':look_id,'seal_sha256':seal_sha256,'created_at':stamp,**record}
        events=[{'event_id':str(uuid4()),'candidate_id':cid,'event':'LOOK_COUNTED','recorded_at':stamp,**extra} for cid,extra in counted]
        try:
            with self.store._live(),self.store.conn:
                self.store.conn.execute('INSERT INTO engine_looks VALUES(?,?,?,?)',(look_id,seal_sha256,stamp,canonical(row).decode()))
                for event in events:
                    self.store.conn.execute('INSERT INTO engine_queue VALUES(?,?,?,?,?)',(event['event_id'],event['candidate_id'],'LOOK_COUNTED',stamp,canonical(event).decode()))
        except sqlite3.IntegrityError: raise RuntimeRefused('ENGINE_LOOK_DUPLICATE') from None
        return row

    def looks(self): return self._rows('SELECT record FROM engine_looks ORDER BY rowid')
    def look(self,look_id):
        rows=self._rows('SELECT record FROM engine_looks WHERE look_id=?',(look_id,))
        if len(rows)!=1: raise RuntimeRefused('ENGINE_LOOK_UNKNOWN')
        return rows[0]

    # Stage E5: bounded runs. One START row when the owner's run begins, one END row when it stops, never rewritten.
    def record_run_phase(self,run_id,phase,record):
        if not isinstance(run_id,str) or not re.fullmatch(RUN_ID,run_id) or phase not in ('START','END'): raise RuntimeRefused('ENGINE_RECORD_DENIED')
        row={'run_id':run_id,'phase':phase,'recorded_at':now(),**record}
        self._insert_once('INSERT INTO engine_bounded_runs VALUES(?,?,?,?,?)',(f'{run_id}:{phase}',run_id,phase,row['recorded_at'],canonical(row).decode()),'ENGINE_RUN_DUPLICATE');return row

    def run_rows(self,run_id): return self._rows('SELECT record FROM engine_bounded_runs WHERE run_id=? ORDER BY rowid',(run_id,))

    def open_runs(self):
        """Run ids with a START row and no END row. A crashed run stays open until the owner closes it."""
        return self._rows("SELECT record FROM engine_bounded_runs a WHERE phase='START' AND NOT EXISTS (SELECT 1 FROM engine_bounded_runs b WHERE b.run_id=a.run_id AND b.phase='END') ORDER BY rowid")

    def close_run(self,run_id,record):
        if not any(r['phase']=='START' for r in self.run_rows(run_id)): raise RuntimeRefused('ENGINE_RUN_UNKNOWN')
        return self.record_run_phase(run_id,'END',record)

    def cycles(self): return self._rows('SELECT record FROM engine_cycles ORDER BY rowid')
    def steps(self,cycle_id): return self._rows('SELECT record FROM engine_steps WHERE cycle_id=? ORDER BY rowid',(cycle_id,))
    def runs(self,cycle_id): return self._rows('SELECT record FROM engine_runs WHERE cycle_id=? ORDER BY rowid',(cycle_id,))

    def summary(self):
        """Compact history for the Director: the last cycles, their hypotheses and candidate outcomes. Bounded to SUMMARY_BYTES. Never vault results."""
        cycles=self.cycles();ends=[c for c in cycles if c['phase']=='END'][-MAX_SUMMARY_CYCLES:]
        recent=[]
        for c in ends:
            hypotheses=[{'id':str(h.get('id'))[:32],'title':str(h.get('title'))[:120]} for h in (c.get('hypotheses') or [])[:3] if isinstance(h,dict)]
            candidates=[{'hypothesis_id':str(x.get('hypothesis_id'))[:32],'status':str(x.get('status'))[:40]} for x in (c.get('candidates') or [])[:3] if isinstance(x,dict)]
            recent.append({'cycle_index':c['cycle_index'],'status':str(c.get('status'))[:40],'hypotheses':hypotheses,'candidates':candidates})
        result={'cycles_completed':len([c for c in cycles if c['phase']=='END']),'active_freezes':len(self.active_freezes()),'recent':recent}
        while recent and len(canonical(result))>SUMMARY_BYTES: recent.pop(0)
        return result
