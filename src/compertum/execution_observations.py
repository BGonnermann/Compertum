"""Execution-owned observations for an invented constant-price control fixture.

No public observation or readiness flags are accepted. Capital history remains
uninitialized, so this builder cannot admit a strategy or real financial action.
"""
from datetime import timedelta
from decimal import Decimal
from uuid import uuid4
from .domain import ExecutionCalendar,ExecutionInputs,ExecutionObservation
from .execution_authority import ExecutionAuthority
from .execution_contracts import instant,record_sha256
from .deterministic_broker import DeterministicBroker
from .fake_execution_journal import FakeIntentJournal
from .fake_attempt_guard import require_attempt_guard
from .fake_economic_opening import require_opening
from .fake_economic_ledger import reconcile
from .attempt_records import is_fake
from .runtime.errors import RuntimeRefused
from .persistence import checked_path


def _close_all(resources):
    error=None
    for resource in resources:
        try:resource.close()
        except BaseException as failure:
            if error is None:error=failure
    if error is not None:raise error


class FakeObservationOwner:
    def __init__(self,authority):
        if type(authority) is not ExecutionAuthority:raise RuntimeRefused('WRONG_OWNER_ROLE')
        self.authority=authority;self.store=authority.store;self.journal=None;self.broker=None;self.pins=[];self.closed=False
        with self.store._live() as guard:guard.resources.append(self)

    def close(self):
        if self.closed:return
        self.closed=True
        resources=([self.broker] if self.broker is not None else [])+list(reversed(self.pins))
        self.pins=[]
        _close_all(resources)

    def _require_uncompromised(self):
        for key,expected in (('fake_attempt_conflict','false'),('execution_status','"VERIFIED"')):
            row=self.store.conn.execute('SELECT CASE WHEN length(value)<=32 THEN value ELSE NULL END FROM state WHERE key=?',(key,)).fetchone()
            if row is not None and row!=(expected,):raise RuntimeRefused('EXECUTION_COMPROMISED')

    def _broker_paths(self):
        path=checked_path(self.store.root,self.store.root/'state/fake-broker')
        for suffix in ('','-wal','-shm'):checked_path(self.store.root,path/('deterministic-broker.sqlite'+suffix))
        return path

    def _open_broker(self,guard,account):
        path=self._broker_paths()
        if not (path/'deterministic-broker.sqlite').is_file():raise RuntimeRefused('FAKE_BROKER_MISSING')
        pins=[]
        try:
            # The native owner already pins root/state; retain this child and DB
            # without delete sharing before SQLite resolves or opens any path.
            pins.append(guard.api.open_directory(path))
            pins.append(guard.api.open_file(path/'deterministic-broker.sqlite',0x80000000,3))
            info=guard.api.file_info(pins[-1])
            if info.attributes&(0x400|0x10) or info.links!=1:raise RuntimeRefused('PATH_DENIED')
            self._broker_paths()
            broker=DeterministicBroker(path,account=account,create=False)
        except BaseException as error:
            try:_close_all(reversed(pins))
            finally:raise error
        self.broker=broker;self.pins=pins

    def read(self):
        # Journal/authority helpers own their transactions. Never let them commit
        # a caller's partially prepared request or plan.
        if self.closed:raise RuntimeRefused('OBSERVATION_OWNER_CLOSED')
        with self.store._live() as guard:
            if self.store.conn.in_transaction:raise RuntimeRefused('OBSERVATION_TRANSACTION_OPEN')
            self._require_uncompromised()
            before=self.authority.observation_context();profile=before['profile']
            if self.journal is None:self.journal=FakeIntentJournal(self.store)
            self._require_uncompromised()
            evidence=require_attempt_guard(self.store)
            # The shared guard is fully verified before selecting fake economics.
            evidence={**evidence,'records':[v for v in evidence['records'] if is_fake(v['intent'])]}
            if self.broker is None:self._open_broker(guard,profile['account_alias'])
            self._broker_paths()
            if self.broker.account!=profile['account_alias']:raise RuntimeRefused('FAKE_ACCOUNT_CHANGED')
            snapshot=self.broker.snapshot()
            economics=reconcile(require_opening(self.store,self.broker),evidence,snapshot)
            context=self.authority.observation_context()
            if any(context[k]!=before[k] for k in ('session_id','profile_sha256','owner_instance','generation')):
                raise RuntimeRefused('SESSION_INPUTS_CHANGED')
            c=profile['calendar'];inputs=profile['inputs'];now=context['market_at']
            unknown=self.store.conn.execute("SELECT 1 FROM fake_intents WHERE state IN ('SUBMITTING','UNKNOWN') LIMIT 1").fetchone() is not None
            submissions=sum(v['intent']['kind']=='STRATEGY' and instant(v['attempted_at']).date().isoformat()==c['session_date'] for v in evidence['records'])
            # The fixture defines 20 identical invented volume observations.
            # It does not attest historical liquidity or supply live prices.
            quotes=[dict(symbol=v['symbol'],sector=v['sector'],bid=v['raw_close'],ask=v['raw_close'],observed_at=now,feed='fixture',
                mean_dollar_volume=v['mean_dollar_volume'],liquidity_sessions=20,liquidity_as_of=inputs['feature_session'],
                liquidity_verified=inputs['feature_session']==c['prior_session'] and Decimal(v['mean_dollar_volume'])>0) for v in inputs['securities']]
            entry=instant(c['session_open_at'])+timedelta(minutes=5)
            record=ExecutionObservation(dict(schema_version='1',record_type='ExecutionObservation',scope='DETERMINISTIC_FAKE',currency='USD',
                observation_id=str(uuid4()),account_alias=snapshot['account_alias'],generation=self.store.lease.generation,observed_at=now,feed='fixture',
                clock=dict(observed_at=now,broker_at=now,calendar_sha256=inputs['calendar_sha256'],calendar_verified=True,prior_session=c['prior_session'],
                    session_open_at=c['session_open_at'],session_close_at=c['session_close_at'],strategy_open_at=entry.isoformat(),strategy_close_at=(entry+timedelta(minutes=1)).isoformat()),
                health=dict(execution_at=now,watchdog_at=context['watchdog_at'],supervision_at=context['supervision_at'],connected=True,account_enabled=True,
                    durable=True,resources_ok=True,exclusive_owner=True,journal_reserved=True,broker_cancel_allowed=True),
                authority=dict(ownership_complete=all(v['owned'] for v in snapshot['orders']),foreign_activity=False,unknown_intents=unknown,
                    armed=False,halted=context['halted'],strategy_admitted=False,strategy_sha256=inputs['strategy_sha256'],authorization_sha256=inputs['authorization_sha256'],
                    rebalance_id=inputs['rebalance_id'],inputs_sha256=record_sha256(ExecutionInputs(inputs))),
                account=dict(reconciled_at=before['market_at'],sleeve_cash=economics['expected_cash'],broker_cash=snapshot['cash'],prior_close_nav='0',prior_peak_nav='0',submissions=submissions,
                    dividend_receivables='0',undebited_liabilities='0'),
                positions=[dict(symbol=s,quantity=str(q),owned_quantity=economics['owned_positions'].get(s,0)) for s,q in sorted(snapshot['positions'].items())],orders=snapshot['orders'],quotes=quotes))
            return record,dict(context,calendar=ExecutionCalendar(c))
