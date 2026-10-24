"""Archivist tables for the engine: cycles, steps, sandbox runs and freezes. Rows are inserted once and never rewritten.

Section 19: the Archivist records each step, including rejected memos and failed runs. The engine never deletes or
rewrites a record. A freeze row stops every engine action until the owner clears it (the clearing command is stage E5 work).
"""
from datetime import datetime,timezone
from uuid import uuid4
from compertum.events import canonical
from compertum.runtime.errors import RuntimeRefused
from ..manual import read_json

MAX_SUMMARY_CYCLES=20
SUMMARY_BYTES=16384


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
