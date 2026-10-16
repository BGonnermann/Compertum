"""Durable invented-effect lifecycle in the existing native execution store.

This journal has no transport, broker capability or real-account admission.
A one-use simulated attempt is deliberately lost across restart rather than
reissued. Live reserve/authority authentication belongs to owner integration.
"""
from contextlib import contextmanager
from decimal import Decimal as D
import hashlib
import json
from .data.encoding import canonical
from .domain import ExecutionIntent,ExecutionDecision,ExecutionObservation
from .execution_contracts import instant,record_sha256,TERMINAL
from .execution_risk import client_order_id
from .persistence import StateStore
from .runtime.errors import RuntimeRefused
from .runtime.owners import require_live_owner
from .events import uuid
from .attempt_records import is_fake

MAX_INTENTS=256
MAX_EVENTS=512


class FakeIntentJournal:
    def __init__(self,store):
        if type(store) is not StateStore:raise RuntimeRefused('WRONG_OWNER_ROLE')
        require_live_owner(store.lease,'execution');self.store=store;self.db=store.conn
        with self._transaction():
            for statement in (
                'CREATE TABLE IF NOT EXISTS fake_intents(account TEXT NOT NULL,intent_id TEXT NOT NULL,client_id TEXT NOT NULL,body TEXT NOT NULL,decision TEXT NOT NULL,state TEXT NOT NULL,order_id TEXT,filled INTEGER NOT NULL,notional TEXT NOT NULL,conflict INTEGER NOT NULL,PRIMARY KEY(account,intent_id),UNIQUE(account,client_id))',
                'CREATE TABLE IF NOT EXISTS fake_intent_events(seq INTEGER PRIMARY KEY AUTOINCREMENT,account TEXT NOT NULL,intent_id TEXT NOT NULL,kind TEXT NOT NULL,body TEXT NOT NULL)',
                'CREATE TABLE IF NOT EXISTS fake_broker_events(account TEXT NOT NULL,event_id TEXT NOT NULL,sha256 TEXT NOT NULL,PRIMARY KEY(account,event_id))',
                'CREATE TABLE IF NOT EXISTS fake_event_applications(account TEXT NOT NULL,event_id TEXT NOT NULL,intent_id TEXT NOT NULL,PRIMARY KEY(account,event_id,intent_id))',
                'CREATE TABLE IF NOT EXISTS fake_incidents(account TEXT NOT NULL,intent_id TEXT NOT NULL,next_index INTEGER NOT NULL,last_elapsed REAL NOT NULL,PRIMARY KEY(account,intent_id))',
                'CREATE TABLE IF NOT EXISTS fake_execution_session(singleton INTEGER PRIMARY KEY CHECK(singleton=1),owner_instance TEXT NOT NULL,state TEXT NOT NULL)'):
                self.db.execute(statement)
            columns={v[1] for v in self.db.execute('PRAGMA table_info(fake_incidents)')}
            if 'started_at' not in columns:self.db.execute('ALTER TABLE fake_incidents ADD COLUMN started_at TEXT')
            if 'active' not in columns:
                self.db.execute('ALTER TABLE fake_incidents ADD COLUMN active INTEGER NOT NULL DEFAULT 1')
                self.db.execute("UPDATE fake_incidents SET active=EXISTS(SELECT 1 FROM fake_intents i WHERE i.account=fake_incidents.account AND i.intent_id=fake_incidents.intent_id AND i.state IN ('UNKNOWN','SUBMITTING'))")
            from .fake_attempt_guard import provision_attempt_guard
            preserved=provision_attempt_guard(store)
            if preserved['status']=='VERIFIED':
                for record in preserved['records']:
                    if not is_fake(record['intent']):continue
                    i=record['intent'];account=i['account_alias'];key=i['intent_id']
                    old=self.db.execute('SELECT body,decision,state FROM fake_intents WHERE account=? AND intent_id=?',(account,key)).fetchone()
                    if old is not None and (old[0]!=canonical(i).decode() or old[1]!=canonical(record['decision']).decode()):
                        self.db.execute("INSERT INTO state VALUES('fake_attempt_conflict','true') ON CONFLICT(key) DO UPDATE SET value='true'")
                        continue
                    if old is None:
                        if self.db.execute('SELECT count(*) FROM fake_intents').fetchone()[0]>=MAX_INTENTS:raise RuntimeRefused('FAKE_JOURNAL_BOUND')
                        self.db.execute("INSERT INTO fake_intents VALUES(?,?,?,?,?,'UNKNOWN',NULL,0,'0',0)",(account,key,record['client_order_id'],canonical(i).decode(),canonical(record['decision']).decode()))
                    elif old[2] in {'CHECKED','SKIPPED_RESTART','SKIPPED_WINDOW_EXPIRED'}:
                        self.db.execute("UPDATE fake_intents SET state='UNKNOWN' WHERE account=? AND intent_id=?",(account,key))
                    if old is None or old[2] in {'CHECKED','SKIPPED_RESTART','SKIPPED_WINDOW_EXPIRED'}:
                        self._event(account,key,'SUBMITTING',dict(at=record['attempted_at'],client_order_id=record['client_order_id'],restored_from_preserved_evidence=True))
                        self._start_incident(account,key,record['attempted_at'])
            instance=store.lease.identity.process_instance_id
            previous=self.db.execute('SELECT owner_instance FROM fake_execution_session WHERE singleton=1').fetchone()
            if previous is None or previous[0]!=instance:
                rows=self.db.execute("SELECT account,intent_id,state FROM fake_intents WHERE state IN ('CHECKED','SUBMITTING')").fetchall()
                for account,intent_id,state in rows:
                    new='UNKNOWN' if state=='SUBMITTING' else 'SKIPPED_RESTART'
                    self.db.execute('UPDATE fake_intents SET state=? WHERE account=? AND intent_id=?',(new,account,intent_id))
                    self._event(account,intent_id,'RESTART',dict(previous=state,state=new))
                    if new=='UNKNOWN':self._start_incident(account,intent_id,self._attempted_at(account,intent_id))
                self.db.execute("INSERT INTO fake_execution_session VALUES(1,?,'RECONCILING') ON CONFLICT(singleton) DO UPDATE SET owner_instance=excluded.owner_instance,state='RECONCILING'",(instance,))

    @contextmanager
    def _transaction(self):
        with self.store._live():
            require_live_owner(self.store.lease,'execution')
            with self.db:yield

    def _event(self,account,intent_id,kind,payload):
        if self.db.execute('SELECT COUNT(*) FROM fake_intent_events').fetchone()[0]>=MAX_EVENTS:raise RuntimeRefused('FAKE_JOURNAL_BOUND')
        body=canonical(payload)
        if len(body)>65536:raise RuntimeRefused('FAKE_JOURNAL_BOUND')
        self.db.execute('INSERT INTO fake_intent_events(account,intent_id,kind,body) VALUES(?,?,?,?)',(account,intent_id,kind,body.decode()))

    def _attempted_at(self,account,intent_id):
        attempted=self.db.execute("SELECT body FROM fake_intent_events WHERE account=? AND intent_id=? AND kind='SUBMITTING' ORDER BY seq LIMIT 1",(account,intent_id)).fetchone()
        if attempted is None:raise RuntimeRefused('INCIDENT_START_MISSING')
        return json.loads(attempted[0])['at']

    def _start_incident(self,account,intent_id,now):
        prior=self.db.execute('SELECT active,started_at FROM fake_incidents WHERE account=? AND intent_id=?',(account,intent_id)).fetchone()
        if prior and prior[0]:
            if prior[1] is None:self.db.execute('UPDATE fake_incidents SET started_at=? WHERE account=? AND intent_id=?',(self._attempted_at(account,intent_id),account,intent_id))
            return
        self.db.execute('INSERT INTO fake_incidents(account,intent_id,next_index,last_elapsed,started_at,active) VALUES(?,?,0,0,?,1) ON CONFLICT(account,intent_id) DO UPDATE SET next_index=0,last_elapsed=0,started_at=excluded.started_at,active=1',(account,intent_id,now))
        self._event(account,intent_id,'INCIDENT_STARTED',dict(at=now))

    def _finish_incident(self,account,intent_id,now):
        prior=self.db.execute('SELECT started_at,next_index,last_elapsed FROM fake_incidents WHERE account=? AND intent_id=? AND active=1',(account,intent_id)).fetchone()
        if prior:
            self.db.execute('UPDATE fake_incidents SET active=0 WHERE account=? AND intent_id=?',(account,intent_id))
            self._event(account,intent_id,'INCIDENT_RESOLVED',dict(at=now,started_at=prior[0],next_index=prior[1],last_elapsed=prior[2]))

    def _row(self,account,intent_id):
        row=self.db.execute('SELECT body,decision,state,order_id,filled,notional,client_id,conflict FROM fake_intents WHERE account=? AND intent_id=?',(account,intent_id)).fetchone()
        if row is None:raise RuntimeRefused('INTENT_NOT_FOUND')
        if not is_fake(json.loads(row[0])):raise RuntimeRefused('INTENT_SCOPE_MISMATCH')
        return dict(intent=json.loads(row[0]),decision=json.loads(row[1]),status=row[2],order_id=row[3],filled_quantity=row[4],filled_notional=row[5],client_order_id=row[6],conflicting_observation=bool(row[7]),scope='DETERMINISTIC_FAKE',financial_accepted=False)

    def read(self,account,intent_id):
        with self._transaction():return self._row(account,intent_id)

    def record_checked(self,intent,decision):
        if type(intent) is not ExecutionIntent or type(decision) is not ExecutionDecision:raise RuntimeRefused('INVALID_EXECUTION_RECORD')
        i=intent.to_payload();d=decision.to_payload();account=i['account_alias'];key=i['intent_id'];body=canonical(i).decode()
        with self._transaction():
            previous=self.db.execute('SELECT body FROM fake_intents WHERE account=? AND intent_id=?',(account,key)).fetchone()
            if previous:
                if previous[0]!=body:raise RuntimeRefused('INTENT_CONFLICT')
                # A new observation/decision cannot turn a prior attempt into a retry.
                return self._row(account,key)
            if not(d['allowed'] and d['intent_sha256']==record_sha256(intent) and d['snapshot_sha256']==i['snapshot_sha256'] and d['account_alias']==account and d['generation']==i['generation']==self.store.lease.generation):raise RuntimeRefused('DECISION_BINDING_DENIED')
            if self.db.execute('SELECT COUNT(*) FROM fake_intents').fetchone()[0]>=MAX_INTENTS:raise RuntimeRefused('FAKE_JOURNAL_BOUND')
            self.db.execute("INSERT INTO fake_intents VALUES(?,?,?,?,?,'CHECKED',NULL,0,'0',0)",(account,key,client_order_id(intent),body,canonical(d).decode()))
            self._event(account,key,'CHECKED',dict(intent_sha256=record_sha256(intent),decision_sha256=record_sha256(decision)))
            return self._row(account,key)

    def begin_attempt(self,account,intent_id,*,now):
        at=instant(now)
        with self._transaction():
            row=self._row(account,intent_id);i=row['intent']
            if row['status']!='CHECKED':return dict(simulate_once=False,record=row)
            if i['generation']!=self.store.lease.generation:raise RuntimeRefused('STALE_GENERATION')
            from .fake_attempt_guard import require_attempt_guard,record_attempt
            evidence=require_attempt_guard(self.store)
            if self.store.get_state('fake_attempt_conflict'):raise RuntimeRefused('EXECUTION_COMPROMISED')
            for prior in evidence['records']:
                if (prior['intent']['account_alias'],prior['intent']['intent_id'])==(account,intent_id):
                    if prior['intent']!=i or prior['decision']!=row['decision']:raise RuntimeRefused('EXECUTION_COMPROMISED')
                    self.db.execute("UPDATE fake_intents SET state='UNKNOWN' WHERE account=? AND intent_id=?",(account,intent_id))
                    self._event(account,intent_id,'SUBMITTING',dict(at=prior['attempted_at'],client_order_id=row['client_order_id'],restored_from_preserved_evidence=True))
                    self._start_incident(account,intent_id,prior['attempted_at'])
                    return dict(simulate_once=False,record=self._row(account,intent_id))
            if not instant(i['created_at'])<=at<instant(i['expires_at']):
                self.db.execute("UPDATE fake_intents SET state='SKIPPED_WINDOW_EXPIRED' WHERE account=? AND intent_id=?",(account,intent_id));self._event(account,intent_id,'EXPIRED',dict(at=now))
                return dict(simulate_once=False,record=self._row(account,intent_id))
            if self.db.execute("SELECT 1 FROM fake_intents WHERE state IN ('SUBMITTING','UNKNOWN') LIMIT 1").fetchone():raise RuntimeRefused('UNKNOWN_INTENT')
            recorded=record_attempt(self.store,ExecutionIntent(i),ExecutionDecision(row['decision']),now=now)
            if not recorded['first']:
                self.db.execute("UPDATE fake_intents SET state='UNKNOWN' WHERE account=? AND intent_id=?",(account,intent_id))
                self._event(account,intent_id,'SUBMITTING',dict(at=recorded['record']['attempted_at'],client_order_id=row['client_order_id'],restored_from_preserved_evidence=True))
                self._start_incident(account,intent_id,recorded['record']['attempted_at'])
                return dict(simulate_once=False,record=self._row(account,intent_id))
            self.db.execute("UPDATE fake_intents SET state='SUBMITTING' WHERE account=? AND intent_id=?",(account,intent_id));self._event(account,intent_id,'SUBMITTING',dict(at=now,client_order_id=row['client_order_id']))
            self._start_incident(account,intent_id,now)
            return dict(simulate_once=True,record=self._row(account,intent_id))

    def uncertain(self,account,intent_id,*,reason,now):
        if reason not in {'TIMEOUT','DISCONNECT','SERVER_ERROR','LOOKUP_404','CONFLICTING_OBSERVATION'}:raise RuntimeRefused('INVALID_UNCERTAINTY')
        instant(now)
        with self._transaction():
            row=self._row(account,intent_id)
            if row['status'] in {'CHECKED','SKIPPED_RESTART','SKIPPED_WINDOW_EXPIRED'}:raise RuntimeRefused('INTENT_NOT_ATTEMPTED')
            if row['status'] not in TERMINAL or reason=='CONFLICTING_OBSERVATION':
                self._start_incident(account,intent_id,now)
                self.db.execute("UPDATE fake_intents SET state='UNKNOWN',conflict=CASE WHEN ? THEN 1 ELSE conflict END WHERE account=? AND intent_id=?",(reason=='CONFLICTING_OBSERVATION',account,intent_id));self._event(account,intent_id,'UNKNOWN',dict(reason=reason,at=now))
            return self._row(account,intent_id)

    def observe(self,account,intent_id,observation,*,event_id):
        if type(observation) is not ExecutionObservation:raise RuntimeRefused('INVALID_EXECUTION_RECORD')
        uuid(event_id);o=observation.to_payload()
        with self._transaction():
            row=self._row(account,intent_id);i=row['intent']
            if o['account_alias']!=account or o['generation']!=self.store.lease.generation:raise RuntimeRefused('OBSERVATION_BINDING_DENIED')
            if row['status'] in {'CHECKED','SKIPPED_RESTART','SKIPPED_WINDOW_EXPIRED'}:raise RuntimeRefused('INTENT_NOT_ATTEMPTED')
            orders=[v for v in o['orders'] if (v['order_id']==i['order_id'] if i['kind']=='CANCEL' else v['client_order_id']==row['client_order_id'])]
            if len(orders)!=1:raise RuntimeRefused('ORDER_NOT_OBSERVED')
            order=orders[0]
            if not(order['owned'] and order['symbol']==i['symbol'] and (i['kind']=='CANCEL' or (order['side']==i['side'] and order['quantity']==i['quantity']))):raise RuntimeRefused('ORDER_BINDING_DENIED')
            if row['order_id'] is not None and row['order_id']!=order['order_id']:raise RuntimeRefused('ORDER_BINDING_DENIED')
            fingerprint=hashlib.sha256(canonical(order)).hexdigest()
            previous=self.db.execute('SELECT sha256 FROM fake_broker_events WHERE account=? AND event_id=?',(account,event_id)).fetchone()
            if previous:
                if previous[0]!=fingerprint:raise RuntimeRefused('BROKER_EVENT_CONFLICT')
                applied=self.db.execute('SELECT 1 FROM fake_event_applications WHERE account=? AND event_id=? AND intent_id=?',(account,event_id,intent_id)).fetchone()
                if applied and row['status']!='UNKNOWN':return row
            else:self.db.execute('INSERT INTO fake_broker_events VALUES(?,?,?)',(account,event_id,fingerprint))
            self.db.execute('INSERT OR IGNORE INTO fake_event_applications VALUES(?,?,?)',(account,event_id,intent_id))
            current=row['status'];incoming=order['status'];filled=order['filled_quantity'];notional=order['filled_notional'];state=incoming;conflict=row['conflicting_observation']
            if filled<row['filled_quantity']:
                state=current;filled=row['filled_quantity'];notional=row['filled_notional']
            elif filled==row['filled_quantity']:
                if D(notional)!=D(row['filled_notional']):conflict=True;notional=row['filled_notional']
                elif current in TERMINAL:
                    state=current
                    if incoming in TERMINAL and incoming!=current:conflict=True
            elif current in TERMINAL or D(notional)<=D(row['filled_notional']):
                conflict=True;filled=row['filled_quantity'];notional=row['filled_notional']
            if conflict:
                state='UNKNOWN';self._start_incident(account,intent_id,o['observed_at'])
            elif state not in {'UNKNOWN','SUBMITTING'}:self._finish_incident(account,intent_id,o['observed_at'])
            self.db.execute('UPDATE fake_intents SET state=?,order_id=?,filled=?,notional=?,conflict=? WHERE account=? AND intent_id=?',(state,order['order_id'],filled,notional,int(conflict),account,intent_id))
            self._event(account,intent_id,'OBSERVATION',dict(event_id=event_id,observation=o,observation_sha256=record_sha256(observation),order=order,result=state))
            return self._row(account,intent_id)

    def status(self):
        with self._transaction():
            intents=self.db.execute("SELECT count(*) FROM fake_intents WHERE json_extract(body,'$.record_type')='ExecutionIntent'").fetchone()[0]
            events=self.db.execute("SELECT count(*) FROM fake_intent_events e JOIN fake_intents i ON i.account=e.account AND i.intent_id=e.intent_id WHERE json_extract(i.body,'$.record_type')='ExecutionIntent'").fetchone()[0]
            return dict(scope='DETERMINISTIC_FAKE',order_admission='DISARMED',reconciliation='RECONCILING',
                        intents=intents,events=events,financial_accepted=False)


    def reserve_poll(self,account,intent_id,*,now):
        """Persist one due lookup; a missed schedule never causes a query burst."""
        at=instant(now);schedule=(0,2,5,10,20,30)
        with self._transaction():
            row=self._row(account,intent_id)
            if row['status'] not in {'SUBMITTING','UNKNOWN'}:return dict(poll=False,status=row['status'])
            self._start_incident(account,intent_id,self._attempted_at(account,intent_id))
            index,last,started=self.db.execute('SELECT next_index,last_elapsed,started_at FROM fake_incidents WHERE account=? AND intent_id=?',(account,intent_id)).fetchone()
            elapsed=(at-instant(started)).total_seconds()
            if elapsed<last or elapsed<0:raise RuntimeRefused('INCIDENT_CLOCK_REVERSED')
            due=[j for j,offset in enumerate(schedule) if offset<=elapsed]
            next_index=max(due)+1 if due else 0
            allowed=elapsed<120 and next_index>index
            self.db.execute('UPDATE fake_incidents SET next_index=?,last_elapsed=? WHERE account=? AND intent_id=?',(max(index,next_index),elapsed,account,intent_id))
            if allowed:self._event(account,intent_id,'POLL_RESERVED',dict(at=now,elapsed_seconds=elapsed,index=next_index-1))
            return dict(poll=allowed,status='UNRESOLVED_LIMIT' if elapsed>=120 else 'UNKNOWN',elapsed_seconds=elapsed)
