"""Persistent deterministic broker fixture; no HTTP, credentials or real account."""
from contextlib import contextmanager
from decimal import Decimal as D
from pathlib import Path
import hashlib
import json
import sqlite3
from uuid import uuid4,uuid5,NAMESPACE_URL
from compertum.domain import ExecutionIntent,ContractError
from compertum.data.encoding import canonical
from compertum.execution_contracts import TERMINAL
from compertum.execution_risk import client_order_id
from compertum.simulation.policy import number
from decimal import Context,localcontext,ROUND_HALF_EVEN,InvalidOperation,DivisionByZero,Overflow
from functools import wraps

def fixed_decimal(function):
    @wraps(function)
    def call(*args,**kwargs):
        context=Context(prec=40,rounding=ROUND_HALF_EVEN,Emin=-999999,Emax=999999,capitals=1,clamp=0,flags=[],traps=[InvalidOperation,DivisionByZero,Overflow])
        with localcontext(context):return function(*args,**kwargs)
    return call
from compertum.persistence import checked_path


class SimulatedTimeout(Exception):pass


class DeterministicBroker:
    """Independent fixture state; transactions survive an execution-owner crash."""
    def __init__(self,root,*,account='fake-account',cash='10000',positions=None,create=True):
        import re
        if type(create) is not bool:raise ContractError('INVALID_FIXTURE_CREATE')
        if not isinstance(account,str) or not re.fullmatch(r'fake-[a-z0-9_-]{1,48}',account):raise ContractError('FAKE_ACCOUNT_REQUIRED')
        if type(cash) is not str or not re.fullmatch(r'(?:0|[1-9][0-9]{0,11})(?:\.\d{1,8})?',cash):raise ContractError('INVALID_FIXTURE_CASH')
        positions={} if positions is None else positions
        if type(positions) is not dict or len(positions)>64 or any(type(symbol) is not str or not re.fullmatch('[A-Z]{1,8}',symbol) or type(quantity) is not int or not 0<=quantity<=1000000000 for symbol,quantity in positions.items()):raise ContractError('INVALID_FIXTURE_POSITION')
        self.root=Path(root).resolve()
        if create:self.root.mkdir(parents=True,exist_ok=True)
        self.path=checked_path(self.root,self.root/'deterministic-broker.sqlite');self.account=account
        if not create and not self.path.is_file():raise ContractError('FAKE_BROKER_MISSING')
        for suffix in ('-wal','-shm'):checked_path(self.root,Path(str(self.path)+suffix))
        if self.path.exists():
            inspection=sqlite3.connect(self.path.as_uri()+'?mode=ro',uri=True,timeout=1)
            try:
                identity=dict(inspection.execute('SELECT CASE WHEN length(key)<=64 THEN key END,CASE WHEN length(value)<=128 THEN value END FROM fixture_identity LIMIT 6'))
                legacy={'schema':'1','scope':'DETERMINISTIC_FAKE','account':account}
                sha=identity.get('opening_sha256')
                bound=type(sha) is str and re.fullmatch('[0-9a-f]{64}',sha) and identity==dict(legacy,schema='2',opening_sha256=sha)
                if identity!=legacy and not bound:raise ContractError('FAKE_STORE_IDENTITY')
                if not create:
                    # Reading an established account never repairs or initializes it.
                    expected={'fixture_identity','account','positions','orders','calls','broker_events','sqlite_sequence'}
                    if {v[0] for v in inspection.execute("SELECT name FROM sqlite_master WHERE type='table'")}!=expected:raise ContractError('FAKE_STORE_IDENTITY')
                    if inspection.execute('SELECT alias FROM account LIMIT 2').fetchall()!=[(account,)]:raise ContractError('FAKE_STORE_IDENTITY')
            except sqlite3.Error:raise ContractError('FAKE_STORE_IDENTITY') from None
            finally:inspection.close()
        self.db=sqlite3.connect(self.path.as_uri()+('?mode=rwc' if create else '?mode=rw'),uri=True,timeout=1);self.db.execute('PRAGMA journal_mode=WAL');self.db.execute('PRAGMA synchronous=FULL');self.db.execute('PRAGMA max_page_count=512')
        if not create:return
        try:
            with self._transaction():
                for statement in (
                    'CREATE TABLE IF NOT EXISTS fixture_identity(key TEXT PRIMARY KEY,value TEXT NOT NULL)',
                    'CREATE TABLE IF NOT EXISTS account(alias TEXT PRIMARY KEY,cash TEXT NOT NULL)',
                    'CREATE TABLE IF NOT EXISTS positions(symbol TEXT PRIMARY KEY,quantity INTEGER NOT NULL)',
                    'CREATE TABLE IF NOT EXISTS orders(client TEXT PRIMARY KEY,body TEXT NOT NULL,record TEXT NOT NULL,cancel_requested INTEGER NOT NULL,hidden INTEGER NOT NULL)',
                    'CREATE TABLE IF NOT EXISTS calls(sequence INTEGER PRIMARY KEY AUTOINCREMENT,kind TEXT NOT NULL,identity TEXT NOT NULL)',
                    'CREATE TABLE IF NOT EXISTS broker_events(sequence INTEGER PRIMARY KEY AUTOINCREMENT,event_id TEXT UNIQUE NOT NULL,record TEXT NOT NULL)'):
                    self.db.execute(statement)
                existing=self.db.execute('SELECT alias FROM account').fetchall()
                if existing and existing!=[(account,)]:raise ContractError('FAKE_ACCOUNT_CHANGED')
                if not existing:
                    self.db.executemany('INSERT INTO fixture_identity VALUES(?,?)',[('schema','1'),('scope','DETERMINISTIC_FAKE'),('account',account)])
                    self.db.execute('INSERT INTO account VALUES(?,?)',(account,number(D(cash))))
                    self.db.executemany('INSERT INTO positions VALUES(?,?)',list(positions.items()))
        except BaseException:
            self.db.close();raise

    @contextmanager
    def _transaction(self,*,write=True):
        self.db.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
        try:
            yield
            self.db.commit()
        except BaseException:
            self.db.rollback();raise

    def close(self):self.db.close()

    def _call(self,kind,identity):
        if self.db.execute('SELECT COUNT(*) FROM calls').fetchone()[0]>=512:raise ContractError('FAKE_BROKER_BOUND')
        self.db.execute('INSERT INTO calls(kind,identity) VALUES(?,?)',(kind,identity))

    def _event(self,record):
        if self.db.execute('SELECT COUNT(*) FROM broker_events').fetchone()[0]>=512:raise ContractError('FAKE_BROKER_BOUND')
        event_id=str(uuid4());self.db.execute('INSERT INTO broker_events(event_id,record) VALUES(?,?)',(event_id,canonical(record).decode()));return event_id

    def _order(self,order_id):
        for client,raw in self.db.execute('SELECT client,record FROM orders'):
            record=json.loads(raw)
            if record['order_id']==order_id:return client,record
        raise ContractError('FAKE_ORDER_NOT_FOUND')

    def submit(self,intent,*,outcome='ACK',invisible_lookups=0):
        if type(intent) is not ExecutionIntent:raise ContractError('INVALID_EXECUTION_RECORD')
        i=intent.to_payload()
        if i['account_alias']!=self.account or i['kind']=='CANCEL':raise ContractError('FAKE_ORDER_BINDING')
        if outcome not in {'ACK','TIMEOUT_BEFORE_ACCEPT','TIMEOUT_AFTER_ACCEPT'} or type(invisible_lookups) is not int or not 0<=invisible_lookups<=6:raise ContractError('INVALID_FIXTURE_SCENARIO')
        client=client_order_id(intent);body=canonical(i).decode();record=None
        with self._transaction():self._call('SUBMIT',client)
        with self._transaction():
            previous=self.db.execute('SELECT body,record FROM orders WHERE client=?',(client,)).fetchone()
            if previous:
                if previous[0]!=body:raise ContractError('FAKE_CLIENT_ID_CONFLICT')
                record=json.loads(previous[1])
            elif outcome!='TIMEOUT_BEFORE_ACCEPT':
                if self.db.execute('SELECT COUNT(*) FROM orders').fetchone()[0]>=256:raise ContractError('FAKE_BROKER_BOUND')
                record=dict(order_id=str(uuid5(NAMESPACE_URL,'compertum-fixture:'+self.account+':'+client)),client_order_id=client,symbol=i['symbol'],side=i['side'],quantity=i['quantity'],filled_quantity=0,filled_notional='0',status='ACKNOWLEDGED',owned=True)
                self.db.execute('INSERT INTO orders VALUES(?,?,?,0,?)',(client,body,canonical(record).decode(),invisible_lookups));self._event(record)
        # The accepted transaction commits before the invented lost response.
        if outcome!='ACK':raise SimulatedTimeout(outcome)
        return record

    def lookup(self,client):
        with self._transaction():
            self._call('LOOKUP',client);row=self.db.execute('SELECT record,hidden FROM orders WHERE client=?',(client,)).fetchone()
            if row is None:return None
            if row[1]:
                self.db.execute('UPDATE orders SET hidden=hidden-1 WHERE client=?',(client,));return None
            return json.loads(row[0])

    @fixed_decimal
    def fill(self,order_id,quantity,price):
        if type(quantity) is not int or quantity<=0:raise ContractError('INVALID_FIXTURE_FILL')
        import re
        if type(price) is not str or not re.fullmatch(r'(?:0|[1-9][0-9]{0,11})(?:\.\d{1,8})?',price):raise ContractError('INVALID_FIXTURE_FILL')
        price=D(price)
        if not price.is_finite() or price<=0:raise ContractError('INVALID_FIXTURE_FILL')
        with self._transaction():
            client,order=self._order(order_id)
            if order['status'] in TERMINAL or quantity>order['quantity']-order['filled_quantity']:raise ContractError('INVALID_FIXTURE_FILL')
            cost=quantity*price;cash=D(self.db.execute('SELECT cash FROM account').fetchone()[0]);row=self.db.execute('SELECT quantity FROM positions WHERE symbol=?',(order['symbol'],)).fetchone();owned=row[0] if row else 0
            if order['side']=='buy':
                if cost>cash:raise ContractError('FAKE_INSUFFICIENT_CASH')
                owned+=quantity;cash-=cost
            else:
                if quantity>owned:raise ContractError('FAKE_SHORT_DENIED')
                owned-=quantity;cash+=cost
            order['filled_quantity']+=quantity;order['filled_notional']=number(D(order['filled_notional'])+cost);order['status']='FILLED' if order['filled_quantity']==order['quantity'] else 'PARTIALLY_FILLED'
            self.db.execute('UPDATE account SET cash=?',(number(cash),));self.db.execute('INSERT INTO positions VALUES(?,?) ON CONFLICT(symbol) DO UPDATE SET quantity=excluded.quantity',(order['symbol'],owned));self.db.execute('UPDATE orders SET record=? WHERE client=?',(canonical(order).decode(),client));event_id=self._event(order)
            return dict(event_id=event_id,order=order)

    def request_cancel(self,order_id,*,outcome='ACK'):
        if outcome not in {'ACK','TIMEOUT_AFTER_REQUEST'}:raise ContractError('INVALID_FIXTURE_SCENARIO')
        with self._transaction():self._call('CANCEL',order_id)
        with self._transaction():
            client,order=self._order(order_id)
            status=422 if order['status'] in TERMINAL else 204
            if status==204:self.db.execute('UPDATE orders SET cancel_requested=1 WHERE client=?',(client,))
        if outcome!='ACK':raise SimulatedTimeout(outcome)
        return dict(status=status,order_id=order_id)

    def finish_cancel(self,order_id):
        with self._transaction():
            client,order=self._order(order_id)
            if not self.db.execute('SELECT cancel_requested FROM orders WHERE client=?',(client,)).fetchone()[0]:raise ContractError('FAKE_CANCEL_NOT_REQUESTED')
            if order['status'] not in TERMINAL:
                order['status']='CANCELED';self.db.execute('UPDATE orders SET record=? WHERE client=?',(canonical(order).decode(),client));self._event(order)
            return order

    def snapshot(self):
        with self._transaction(write=False):
            return dict(scope='DETERMINISTIC_FAKE',account_alias=self.account,cash=self.db.execute('SELECT cash FROM account').fetchone()[0],positions={s:q for s,q in self.db.execute('SELECT symbol,quantity FROM positions ORDER BY symbol') if q},orders=[json.loads(v[0]) for v in self.db.execute('SELECT record FROM orders ORDER BY client')],calls=[dict(kind=k,identity=i) for k,i in self.db.execute('SELECT kind,identity FROM calls ORDER BY sequence')],event_sequence=(self.db.execute("SELECT seq FROM sqlite_sequence WHERE name='broker_events'").fetchone() or (0,))[0],events=[dict(sequence=n,event_id=e,order=json.loads(v)) for n,e,v in self.db.execute('SELECT sequence,event_id,record FROM broker_events ORDER BY sequence')])
