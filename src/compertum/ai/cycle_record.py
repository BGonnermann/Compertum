"""Bounded coordinator records. These records grant no dispatch authority."""
from datetime import datetime, timezone
import hashlib
import json

from compertum.domain import validate_record
from compertum.events import canonical, uuid
from compertum.evaluation_protocol import digest
from compertum.runtime.errors import RuntimeRefused
from compertum.runtime.owners import require_live_owner

MAX_RECORDS = 32
MAX_BYTES = 65536
ACTIVE = {'APPROVED', 'RUNNING', 'CHECKING_RESULTS'}
TRANSITIONS = {
    'APPROVED': {'RUNNING', 'PAUSED', 'STOPPED', 'BLOCKED'},
    'RUNNING': {'RUNNING', 'PAUSED', 'STOPPED', 'BLOCKED', 'CHECKING_RESULTS'},
    'CHECKING_RESULTS': {'CHECKING_RESULTS', 'PAUSED', 'STOPPED', 'BLOCKED', 'WAITING_FOR_ASSESSMENT'},
    'PAUSED': {'RUNNING', 'CHECKING_RESULTS', 'STOPPED', 'BLOCKED'},
    'WAITING_FOR_ASSESSMENT': {'AWAITING_OWNER_REVIEW', 'STOPPED', 'BLOCKED'},
    'AWAITING_OWNER_REVIEW': set(), 'STOPPED': set(), 'BLOCKED': set(),
}


def _need(ok, reason):
    if not ok:
        raise RuntimeRefused(reason)


def _checked(value):
    raw = canonical(value)
    _need(len(raw) <= MAX_BYTES, 'CYCLE_RECORD_BOUND')
    return validate_record('research_cycle.v1', value)


def _view(value):
    raw = canonical(value)
    return dict(record=json.loads(raw), sha256=hashlib.sha256(raw).hexdigest())


def _deadline(value):
    end = datetime.fromisoformat(value['deadline'].replace('Z', '+00:00'))
    _need(end > datetime.now(timezone.utc), 'CYCLE_DEADLINE')


class CycleRecords:
    """Save immutable approval bindings with compare-and-write transitions.

    Only a live coordinator can use this store. The future cycle controller
    must authenticate control requests and verify evidence before transitions.
    Creating a record never starts a worker or resumes an interrupted dispatch.
    """

    def __init__(self, storage):
        self.storage = storage
        self.store = storage.store
        require_live_owner(self.store.lease, 'coordinator')
        with self.store._live():
            # Include database and journal overhead in this bounded admission.
            storage._capacity('records', 3*1024**2)
            with self.store.conn:
                self.store.conn.execute('''CREATE TABLE IF NOT EXISTS research_cycles(
                    cycle_id TEXT PRIMARY KEY, run_id TEXT NOT NULL UNIQUE,
                    record TEXT NOT NULL)''')

    def _load(self, cycle_id):
        uuid(cycle_id)
        row = self.store.conn.execute('SELECT record FROM research_cycles WHERE cycle_id=?', (cycle_id,)).fetchone()
        _need(row is not None, 'CYCLE_RECORD_MISSING')
        _need(len(row[0].encode()) <= MAX_BYTES, 'CYCLE_RECORD_BOUND')
        return _checked(json.loads(row[0]))

    def status(self, cycle_id):
        with self.store._live():
            return _view(self._load(cycle_id))

    def create(self, value):
        value = _checked(value)
        with self.store._live(), self.store.conn:
            old = self.store.conn.execute('SELECT record FROM research_cycles WHERE cycle_id=?', (value['cycle_id'],)).fetchone()
            if old is not None:
                _need(canonical(self._load(value['cycle_id'])) == canonical(value), 'CYCLE_RECORD_CONFLICT')
                return _view(value)
            _need(value['state'] == 'APPROVED' and value['sequence'] == 0 and value['dispatch'] is None,
                  'CYCLE_INITIAL_STATE_REQUIRED')
            _need(value['generation'] == self.store.lease.generation, 'CYCLE_OWNER_MISMATCH')
            _deadline(value)
            _need(self.store.conn.execute('SELECT 1 FROM research_cycles WHERE run_id=?', (value['run_id'],)).fetchone() is None,
                  'CYCLE_RUN_ALREADY_CLAIMED')
            _need(self.store.conn.execute('SELECT count(*) FROM research_cycles').fetchone()[0] < MAX_RECORDS,
                  'CYCLE_LEDGER_FULL')
            self.storage._capacity('records', 3*1024**2)
            self.store.conn.execute('INSERT INTO research_cycles VALUES(?,?,?)',
                (value['cycle_id'], value['run_id'], canonical(value).decode()))
            return _view(value)

    def transition(self, cycle_id, expected_hash, change):
        digest(expected_hash)
        _need(type(change) is dict and bool(change) and set(change) <= {'state', 'dispatch', 'reason'},
              'CYCLE_IMMUTABLE_BINDING')
        with self.store._live(), self.store.conn:
            old = self._load(cycle_id)
            _need(_view(old)['sha256'] == expected_hash, 'CYCLE_STATE_CHANGED')
            state = change.get('state', old['state'])
            _need(state in TRANSITIONS[old['state']], 'CYCLE_TRANSITION_DENIED')
            if state in ACTIVE:
                _deadline(old)
                _need(old['sequence'] < 9999, 'CYCLE_SEQUENCE_BOUND')
            if old['state'] == 'PAUSED' and state in ACTIVE:
                _need(old['dispatch'] is None, 'CYCLE_DISPATCH_UNCERTAIN')
            new = _checked(dict(old, **change, sequence=old['sequence']+1,
                updated_at=datetime.now(timezone.utc).isoformat()))
            self.storage._capacity('records', 3*1024**2)
            self.store.conn.execute('UPDATE research_cycles SET record=? WHERE cycle_id=?',
                (canonical(new).decode(), cycle_id))
            return _view(new)

    def recover(self):
        """Quarantine active records when the controller is reconstructed."""
        with self.store._live(), self.store.conn:
            ids = [r[0] for r in self.store.conn.execute('SELECT cycle_id FROM research_cycles ORDER BY cycle_id LIMIT 33')]
            _need(len(ids) <= MAX_RECORDS, 'CYCLE_LEDGER_FULL')
            for cycle_id in ids:
                old = self.status(cycle_id)
                if old['record']['state'] in ACTIVE:
                    self.transition(cycle_id, old['sha256'], dict(
                        state='BLOCKED' if old['record']['dispatch'] else 'PAUSED', reason='OWNER_RESTART'))
