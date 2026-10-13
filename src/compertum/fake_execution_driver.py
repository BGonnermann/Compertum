"""Bounded fixture integration only. No transport or live capability routing."""
from uuid import uuid4
from .domain import ExecutionIntent,ExecutionObservation,ContractError
from .execution_contracts import TERMINAL,instant
from .execution_risk import assess
from .execution_plans import assess_control
from .fake_execution_journal import FakeIntentJournal
from .fake_attempt_guard import require_attempt_guard
from .fake_economic_opening import require_opening
from .fake_economic_ledger import reconcile
from .deterministic_broker import DeterministicBroker,SimulatedTimeout
from .runtime.errors import RuntimeRefused
import sqlite3,json


class FakeExecutionDriver:
    def __init__(self,journal,broker):
        if type(journal) is not FakeIntentJournal or type(broker) is not DeterministicBroker:raise ContractError('FAKE_COMPONENT_REQUIRED')
        self.journal=journal;self.broker=broker

    def _economics(self,snapshot):
        return reconcile(require_opening(self.journal.store,self.broker),require_attempt_guard(self.journal.store),snapshot)

    def observation(self,template,*,now):
        return self._observation(template,self.broker.snapshot(),now=now)

    def _observation(self,template,s,*,now):
        if type(template) is not ExecutionObservation:raise ContractError('INVALID_EXECUTION_RECORD')
        economics=self._economics(s)
        o=template.to_payload()
        if o['account_alias']!=s['account_alias']:raise ContractError('FAKE_ACCOUNT_CHANGED')
        o.update(observation_id=str(uuid4()),observed_at=now,orders=s['orders'],positions=[dict(symbol=symbol,quantity=str(qty),owned_quantity=economics['owned_positions'].get(symbol,0)) for symbol,qty in sorted(s['positions'].items())])
        o['account'].update(reconciled_at=now,sleeve_cash=economics['expected_cash'],broker_cash=s['cash'])
        o['generation']=self.journal.store.lease.generation
        return ExecutionObservation(o)

    def _observe(self,intent,template,*,now):
        i=intent.to_payload();s=self.broker.snapshot();o=self._observation(template,s,now=now)
        row=self.journal.read(i['account_alias'],i['intent_id'])
        matches=[v for v in s['events'] if (v['order']['order_id']==i['order_id'] if i['kind']=='CANCEL' else v['order']['client_order_id']==row['client_order_id'])]
        if not matches:raise RuntimeRefused('ORDER_NOT_OBSERVED')
        return self.journal.observe(i['account_alias'],i['intent_id'],o,event_id=matches[-1]['event_id'])

    def dispatch(self,intent,observation,*,now,calendar,inputs=None,plan=None,authorization=None,start=None,outcome='ACK',invisible_lookups=0):
        if type(intent) is not ExecutionIntent or type(observation) is not ExecutionObservation:raise ContractError('INVALID_EXECUTION_RECORD')
        i=intent.to_payload();account=i['account_alias'];key=i['intent_id']
        if account!=self.broker.account:raise ContractError('FAKE_ACCOUNT_CHANGED')
        choices={'ACK','TIMEOUT_AFTER_REQUEST'} if i['kind']=='CANCEL' else {'ACK','TIMEOUT_BEFORE_ACCEPT','TIMEOUT_AFTER_ACCEPT'}
        if outcome not in choices or type(invisible_lookups) is not int or not 0<=invisible_lookups<=6:raise ContractError('INVALID_FIXTURE_SCENARIO')
        # Repeated control calls report existing state and never call the fixture again.
        try:old=self.journal.read(account,key)
        except RuntimeRefused as exc:
            if exc.code!='INTENT_NOT_FOUND':raise
            old=None
        if old is not None:
            if old['intent']!=i:raise RuntimeRefused('INTENT_CONFLICT')
            if old['status']!='CHECKED':return old
        s=self.broker.snapshot();economics=self._economics(s);o=observation.to_payload()
        if o['account']['sleeve_cash']!=economics['expected_cash'] or o['account']['broker_cash']!=s['cash'] or {p['symbol']:p['owned_quantity'] for p in o['positions'] if p['owned_quantity']}!=s['positions'] or sorted(o['orders'],key=lambda p:p['order_id'])!=sorted(s['orders'],key=lambda p:p['order_id']):raise RuntimeRefused('FAKE_RECONCILIATION_CHANGED')
        decision=assess(intent,observation,now=now,calendar=calendar,inputs=inputs) if i['kind']=='STRATEGY' else assess_control(intent,observation,plan,authorization,start=start,now=now,calendar=calendar)
        if not decision['allowed']:return dict(status='REFUSED',decision=decision.to_payload(),scope='DETERMINISTIC_FAKE',financial_accepted=False)
        self.journal.record_checked(intent,decision)
        attempt=self.journal.begin_attempt(account,key,now=now)
        if not attempt['simulate_once']:return attempt['record']
        try:
            if i['kind']=='CANCEL':self.broker.request_cancel(i['order_id'],outcome=outcome)
            else:self.broker.submit(intent,outcome=outcome,invisible_lookups=invisible_lookups)
        except (SimulatedTimeout,sqlite3.Error):return self.journal.uncertain(account,key,reason='TIMEOUT',now=now)
        try:return self._observe(intent,observation,now=now)
        except sqlite3.Error:return self.journal.uncertain(account,key,reason='DISCONNECT',now=now)
        except (ContractError,RuntimeRefused):
            return self.journal.uncertain(account,key,reason='CONFLICTING_OBSERVATION',now=now)

    def reconcile(self,intent,template,*,now):
        """Explicit positive snapshot reconciliation; never spend a lookup or retry."""
        i=intent.to_payload();account=i['account_alias'];key=i['intent_id'];row=self.journal.read(account,key)
        if row['intent']!=i:raise RuntimeRefused('INTENT_CONFLICT')
        if row['status'] in TERMINAL or row['status'].startswith('SKIPPED') or row['status']=='CHECKED':return row
        at=instant(now)
        if at<instant(template.to_payload()['observed_at']):raise RuntimeRefused('INCIDENT_CLOCK_REVERSED')
        incident=self.journal.db.execute('SELECT started_at,last_elapsed FROM fake_incidents WHERE account=? AND intent_id=?',(account,key)).fetchone()
        if incident and (at-instant(incident[0])).total_seconds()<incident[1]:raise RuntimeRefused('INCIDENT_CLOCK_REVERSED')
        latest=self.journal.db.execute("SELECT body FROM fake_intent_events WHERE account=? AND intent_id=? AND kind='OBSERVATION' ORDER BY seq DESC LIMIT 1",(account,key)).fetchone()
        if latest and at<instant(json.loads(latest[0])['observation']['observed_at']):raise RuntimeRefused('INCIDENT_CLOCK_REVERSED')
        try:return self._observe(intent,template,now=now)
        except sqlite3.Error:return self.journal.uncertain(account,key,reason='DISCONNECT',now=now)
        except (ContractError,RuntimeRefused) as error:
            if isinstance(error,RuntimeRefused) and error.code=='ORDER_NOT_OBSERVED':
                return row if row['status'] in {'UNKNOWN','SUBMITTING'} else self.journal.uncertain(account,key,reason='DISCONNECT',now=now)
            return self.journal.uncertain(account,key,reason='CONFLICTING_OBSERVATION',now=now)

    def poll(self,intent,template,*,now):
        i=intent.to_payload();account=i['account_alias'];key=i['intent_id'];row=self.journal.read(account,key)
        if row['intent']!=i:raise RuntimeRefused('INTENT_CONFLICT')
        if row['status'] in TERMINAL or row['status'].startswith('SKIPPED') or row['status']=='CHECKED':return row
        if row['status'] in {'UNKNOWN','SUBMITTING'}:
            schedule=self.journal.reserve_poll(account,key,now=now)
            if not schedule['poll']:return dict(row,incident=schedule)
        client=row['client_order_id']
        try:
            if i['kind']=='CANCEL':
                orders=[v for v in self.broker.snapshot()['orders'] if v['order_id']==i['order_id']]
                if not orders:return self.journal.uncertain(account,key,reason='LOOKUP_404',now=now)
                client=orders[0]['client_order_id']
            found=self.broker.lookup(client)
        except (SimulatedTimeout,sqlite3.Error):return self.journal.uncertain(account,key,reason='DISCONNECT',now=now)
        except (ContractError,RuntimeRefused):return self.journal.uncertain(account,key,reason='CONFLICTING_OBSERVATION',now=now)
        if found is None:return self.journal.uncertain(account,key,reason='LOOKUP_404',now=now)
        try:return self._observe(intent,template,now=now)
        except sqlite3.Error:return self.journal.uncertain(account,key,reason='DISCONNECT',now=now)
        except (ContractError,RuntimeRefused):return self.journal.uncertain(account,key,reason='CONFLICTING_OBSERVATION',now=now)
