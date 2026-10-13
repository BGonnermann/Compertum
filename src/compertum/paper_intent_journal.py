"""Inert paper preparation consumption in the existing execution journal.

A first consumption is evidence, never transport authority or an effect permit.
"""
import json,sqlite3
from .data.encoding import canonical
from .domain import ContractError
from .storage import JournalReserve
from .persistence import StateStore
from .runtime.paper_read_packet import _local_time
from .execution_contracts import instant
from .fake_execution_journal import FakeIntentJournal,MAX_INTENTS
from .fake_attempt_guard import provision_attempt_guard,require_attempt_guard,append_record
from .attempt_records import is_paper
from .paper_intent_records import prepare,validate_pair,UNCONSUMED,STATES
from .runtime.execution_health import execution_durable
from .runtime.errors import RuntimeRefused

class PaperIntentJournal:
    def __init__(self,store,reserve):
        if type(store) is not StateStore or type(reserve) is not JournalReserve or reserve.lease is not store.lease:raise RuntimeRefused('JOURNAL_UNRESERVED')
        self.base=FakeIntentJournal(store);self.store=store;self.db=store.conn;self.reserve=reserve
        with self.base._transaction():
            evidence=provision_attempt_guard(store)
            if evidence['status']!='VERIFIED':raise RuntimeRefused('EXECUTION_COMPROMISED')
            if store.get_state('fake_attempt_conflict'):raise RuntimeRefused('EXECUTION_COMPROMISED')
            for record in evidence['records']:
                if not is_paper(record['intent']):continue
                p=record['intent'];account=p['account_alias'];key=p['intent_id']
                old=self.db.execute('SELECT body,decision,state FROM fake_intents WHERE account=? AND intent_id=?',(account,key)).fetchone()
                if old is not None and (old[0]!=canonical(p).decode() or old[1]!=canonical(record['decision']).decode()):raise RuntimeRefused('EXECUTION_COMPROMISED')
                if old is None:
                    if self.db.execute('SELECT count(*) FROM fake_intents').fetchone()[0]>=MAX_INTENTS:raise RuntimeRefused('FAKE_JOURNAL_BOUND')
                    self._insert(p,record['decision'],'PAPER_CONSUMED')
                elif old[2] in UNCONSUMED:self.db.execute("UPDATE fake_intents SET state='PAPER_CONSUMED' WHERE account=? AND intent_id=?",(account,key))
                elif old[2]!='PAPER_CONSUMED':raise RuntimeRefused('EXECUTION_COMPROMISED')
                if old is None or old[2] in UNCONSUMED:self.base._event(account,key,'PAPER_RESTORED_CONSUMPTION',dict(at=record['attempted_at']))
            for account,key in self.db.execute("SELECT account,intent_id FROM fake_intents WHERE state='PAPER_PREPARED'").fetchall():
                row=self._row(account,key);p=row['intent']
                if p['owner_instance']!=store.lease.identity.process_instance_id or p['generation']!=store.lease.generation:
                    self.db.execute("UPDATE fake_intents SET state='PAPER_SKIPPED_RESTART' WHERE account=? AND intent_id=?",(account,key))
                    self.base._event(account,key,'PAPER_RESTART',dict(state='PAPER_SKIPPED_RESTART'))

    def _insert(self,p,d,state):
        try:self.db.execute("INSERT INTO fake_intents VALUES(?,?,?,?,?,?,NULL,0,'0',0)",(p['account_alias'],p['intent_id'],p['client_order_id'],canonical(p).decode(),canonical(d).decode(),state))
        except sqlite3.IntegrityError:raise RuntimeRefused('INTENT_CONFLICT') from None

    def _row(self,account,key):
        row=self.db.execute('SELECT CASE WHEN length(CAST(body AS BLOB))<=65536 THEN body END,CASE WHEN length(CAST(decision AS BLOB))<=65536 THEN decision END,state,client_id,order_id,filled,notional,conflict FROM fake_intents WHERE account=? AND intent_id=?',(account,key)).fetchone()
        if row is None:raise RuntimeRefused('INTENT_NOT_FOUND')
        try:
            if type(row[0]) is not str or type(row[1]) is not str:raise ValueError()
            if len(row[0].encode())+len(row[1].encode())>65536:raise ValueError()
            p,d,client=validate_pair(json.loads(row[0]),json.loads(row[1]))
            if (canonical(p).decode()!=row[0] or canonical(d).decode()!=row[1] or row[2] not in STATES or client!=row[3]
                or p['account_alias']!=account or p['intent_id']!=key or p['project_id']!=self.store.lease.project_id
                or row[4:]!=(None,0,'0',0)):raise ValueError()
            return dict(intent=p,preparation=d,status=row[2],client_order_id=client,scope='PAPER_PREPARATION',transport_authorized=False,financial_accepted=False)
        except (ValueError,TypeError,KeyError,ContractError):raise RuntimeRefused('INVALID_PAPER_PREPARATION') from None

    def read(self,account,intent_id):
        with self.base._transaction():return self._row(account,intent_id)

    def record_prepared(self,request,*,expires_at,supporting_sha256):
        with self.base._transaction():
            require_attempt_guard(self.store)
            if self.store.get_state('fake_attempt_conflict'):raise RuntimeRefused('EXECUTION_COMPROMISED')
            p,d=prepare(self.store.lease,request,expires_at=expires_at,supporting_sha256=supporting_sha256)
            key=(p['account_alias'],p['intent_id'])
            previous=self.db.execute('SELECT body,decision FROM fake_intents WHERE account=? AND intent_id=?',key).fetchone()
            if previous:
                if previous!=(canonical(p).decode(),canonical(d).decode()):raise RuntimeRefused('INTENT_CONFLICT')
                return self._row(*key)
            if self.db.execute('SELECT count(*) FROM fake_intents').fetchone()[0]>=MAX_INTENTS:raise RuntimeRefused('FAKE_JOURNAL_BOUND')
            self._insert(p,d,'PAPER_PREPARED');self.base._event(*key,'PAPER_PREPARED',dict(intent_sha256=d['intent_sha256']))
            return self._row(*key)

    def consume(self,account,intent_id,*,now):
        at=_local_time(now)
        with self.base._transaction():
            evidence=require_attempt_guard(self.store)
            if self.store.get_state('fake_attempt_conflict'):raise RuntimeRefused('EXECUTION_COMPROMISED')
            row=self._row(account,intent_id);p=row['intent'];first=False
            if row['status']=='PAPER_PREPARED':
                prior=next((v for v in evidence['records'] if (v['intent']['account_alias'],v['intent']['intent_id'])==(account,intent_id)),None)
                if prior is not None:
                    if prior['intent']!=p or prior['decision']!=row['preparation']:raise RuntimeRefused('EXECUTION_COMPROMISED')
                    state='PAPER_CONSUMED'
                elif p['generation']!=self.store.lease.generation or p['owner_instance']!=self.store.lease.identity.process_instance_id:state='PAPER_SKIPPED_RESTART'
                elif not instant(p['created_at'])<=at<instant(p['expires_at']):state='PAPER_SKIPPED_WINDOW_EXPIRED'
                else:
                    if type(self.reserve) is not JournalReserve or self.reserve.lease is not self.store.lease:raise RuntimeRefused('JOURNAL_UNRESERVED')
                    execution_durable(self.store,self.reserve)
                    recorded=append_record(self.store,dict(intent=p,decision=row['preparation'],attempted_at=now,client_order_id=row['client_order_id']))
                    first=recorded['first'];state='PAPER_CONSUMED'
                self.db.execute('UPDATE fake_intents SET state=? WHERE account=? AND intent_id=?',(state,account,intent_id))
                self.base._event(account,intent_id,'PAPER_CONSUMPTION',dict(at=now,state=state,first_consumption=first))
            return dict(first_consumption=first,record=self._row(account,intent_id),transport_authorized=False,financial_accepted=False)
