"""Authenticated operator presence records. Never an arm or broker-write grant."""
from datetime import timedelta
import hashlib,math,re,sqlite3
from uuid import uuid4
from compertum.data.encoding import canonical
from compertum.domain import ContractError
from compertum.events import uuid
from compertum.paper_contracts import strict_json,timestamp
from .errors import RuntimeRefused
from .paper_final_proof import _final_proof
from .owners import _owner_scope
from .paper_preflight import _live,_measure
from . import paper_account_binding as binding
from .paper_input_context import _account_manifest,_final_account
from .paper_credential_slot import load_paper_slot,_slot,_payload as slot_payload
from .paper_credentials import open_paper_credentials
from .paper_read_evidence import open_read_evidence
from .paper_market_lineage_evidence import _published as published_original
from .paper_read_secrecy import _reject_reflections

_FIELDS={'version','record_type','presence_id','request_sha256','project_id','subject_key','account_alias','packet_id',
         'owner_instance','owner_generation','component_id','credential_sha256','identity_sha256','account_sha256',
         'confirmation_sha256','alias_sha256','manifest_sha256','acknowledged_at','expires_at','acknowledged_mono'}
_INVALID=(ContractError,ValueError,TypeError,KeyError,AttributeError,OverflowError,RecursionError,UnicodeError,sqlite3.Error)


def _need(value,code='PAPER_PRESENCE_INVALID'):
    if not value:raise RuntimeRefused(code)


def _sha(value):return hashlib.sha256(canonical(value)).hexdigest()


def _hash(value):_need(type(value) is str and re.fullmatch('[0-9a-f]{64}',value) is not None)


class _PresenceOwner:
    def __init__(self,parent):
        self.parent=parent;self.db=parent.db;self.instance=str(uuid4());self._issued={};self._revoked={};self._closed=False;self._reason=None
        self._owners=(parent.store,parent.reserve,parent.health,parent.lease)
        self._start,self._start_mono=_measure();self._last,self._last_mono=self._start,self._start_mono

    def __repr__(self):return '<NativePaperPresence private state redacted>'
    def __reduce_ex__(self,protocol):raise RuntimeRefused('PAPER_PRESENCE_SERIALIZATION_FORBIDDEN')
    def close(self):self._closed=True;self._issued.clear();self._revoked.clear()

    def _schema(self,create=False):
        table=self.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='paper_presence_records'").fetchone()
        version=self.db.execute("SELECT value FROM state WHERE key='paper_presence_version'").fetchone()
        _need(bool(table)==(version is not None) and (version is None or version==('1',)),'PAPER_PRESENCE_STATE_CORRUPT')
        _need(not self._issued or table,'PAPER_PRESENCE_STATE_CORRUPT')
        if table:
            _need(self.db.execute('SELECT count(*) FROM paper_presence_records').fetchone()[0]<=128,'PAPER_PRESENCE_HISTORY_BOUND')
            return
        _need(create,'PAPER_PRESENCE_UNKNOWN')
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            self.db.execute('CREATE TABLE paper_presence_records(presence_id TEXT PRIMARY KEY,sha256 TEXT NOT NULL,body TEXT NOT NULL,reason TEXT)')
            changed=self.db.execute("INSERT INTO state VALUES('paper_presence_version','1')")
            _need(changed.rowcount==1,'PAPER_PRESENCE_WRITE_UNVERIFIED');self._schema()

    def _read(self,ident):
        row=self.db.execute('SELECT sha256,CASE WHEN length(CAST(body AS BLOB))<=8192 THEN body END,reason FROM paper_presence_records WHERE presence_id=?',(ident,)).fetchone()
        _need(row is not None,'PAPER_PRESENCE_STATE_CORRUPT' if ident in self._issued else 'PAPER_PRESENCE_UNKNOWN')
        try:
            pin,raw,reason=row;p=strict_json(raw.encode())
            _need(type(p) is dict and set(p)==_FIELDS and canonical(p).decode()==raw and _sha(p)==pin)
            _need(type(p['version']) is int and p['version']==1 and p['record_type']=='NativePaperPresence')
            for key in ('presence_id','packet_id','owner_instance','component_id'):uuid(p[key])
            _need(p['presence_id']==ident and p['project_id']==self.parent.lease.project_id)
            for key in _FIELDS:
                if key.endswith('_sha256') or key in ('project_id','subject_key'):_hash(p[key])
            _need(type(p['owner_generation']) is int and 0<p['owner_generation']<2**63)
            _need(type(p['account_alias']) is str and re.fullmatch('[A-Za-z0-9][A-Za-z0-9_-]{0,63}',p['account_alias']) is not None)
            start,end=timestamp(p['acknowledged_at']),timestamp(p['expires_at'])
            _need(start.isoformat()==p['acknowledged_at'] and end.isoformat()==p['expires_at'] and end-start==timedelta(seconds=300))
            _need(type(p['acknowledged_mono']) in (int,float) and math.isfinite(p['acknowledged_mono']) and 0<=p['acknowledged_mono']<1e15)
            _need(reason is None or type(reason) is str and re.fullmatch('[A-Z][A-Z0-9_]{0,95}',reason) is not None)
            if ident in self._issued:_need(self._issued[ident]==pin)
            if ident in self._revoked and reason is not None:_need(reason==self._revoked[ident])
            # A read during another component's transaction may observe a
            # mutation that will roll back. Its proof invalidator records the
            # failure after rollback; never retain that transient row value.
            if reason is not None and ident in self._issued and not self.db.in_transaction:self._revoked[ident]=reason
            return p,reason
        except (RuntimeRefused,*_INVALID):raise RuntimeRefused('PAPER_PRESENCE_STATE_CORRUPT') from None

    def _clock(self):
        _need(not self._closed,'PAPER_PRESENCE_CLOSED')
        owner=self.parent
        if owner._presence is not self or any(a is not b for a,b in zip(self._owners,(owner.store,owner.reserve,owner.health,owner.lease))):
            self._reason=self._reason or 'PAPER_PRESENCE_OWNER_REPLACED'
        _need(self._reason is None,self._reason or 'PAPER_PRESENCE_INVALIDATED')
        now,mono=_measure();du=(now-self._last).total_seconds();dm=mono-self._last_mono
        if du<0 or dm<0 or abs((now-self._start).total_seconds()-(mono-self._start_mono))>5:
            self._reason='PAPER_PRESENCE_CLOCK_CHANGED'
        elif du>15 or dm>15:self._reason='PAPER_PRESENCE_SERVICE_GAP'
        _need(self._reason is None,self._reason or 'PAPER_PRESENCE_INVALIDATED')
        self._last,self._last_mono=now,mono;return now,mono

    def _age(self,p):
        now,mono=self._clock();du=(now-timestamp(p['acknowledged_at'])).total_seconds();dm=mono-p['acknowledged_mono']
        _need(du>=0 and dm>=0 and abs(du-dm)<=5,'PAPER_PRESENCE_CLOCK_CHANGED')
        _need(du<300 and dm<300,'PAPER_PRESENCE_EXPIRED')
        return now,mono

    def _revoke(self,p,reason):
        _,prior=self._read(p['presence_id'])
        if prior is not None:return prior
        # Revocation cannot be undone by restoring an older database row.
        if p['presence_id'] in self._issued:self._revoked[p['presence_id']]=reason
        with self.db:
            changed=self.db.execute('UPDATE paper_presence_records SET reason=? WHERE presence_id=? AND sha256=? AND reason IS NULL',(reason,p['presence_id'],_sha(p)))
            _need(changed.rowcount==1 and self._read(p['presence_id'])==(p,reason),'PAPER_PRESENCE_WRITE_UNVERIFIED')
        return reason

    def tick(self):
        if self._closed:return
        try:
            _live(self.parent);self._clock()
            if not self._issued:return
            self._schema()
            for ident in tuple(self._issued):
                p,reason=self._read(ident)
                if reason is None:
                    try:self._age(p)
                    except RuntimeRefused as error:self._revoke(p,error.code)
        except RuntimeRefused as error:self._reason=self._reason or error.code
        except _INVALID:self._reason='PAPER_PRESENCE_STATE_CORRUPT'

    def _original_records(self,p):
        owner=self.parent;value=owner._read(p['packet_id']);record=binding._stored(owner,p['packet_id'])
        _need(record is not None and record['confirmed_at'] is not None,'PAPER_PRESENCE_CONFIRMATION_REQUIRED')
        facts=record['proposal'];alias=binding._alias(owner,p['account_alias'],p['identity_sha256'])
        _need(alias is not None)
        _need(all(value[k]==p[k] for k in ('project_id','subject_key','account_alias','packet_id','owner_instance','owner_generation','credential_sha256')))
        _need(facts['identity_sha256']==p['identity_sha256'])
        manifest=_account_manifest(owner,value)
        _need((_sha(value),_sha(record),_sha(alias),_sha(manifest))==tuple(p[k] for k in ('account_sha256','confirmation_sha256','alias_sha256','manifest_sha256')))
        return value,record,alias,manifest

    def _originals(self,p):
        original=self._original_records(p)
        with open_read_evidence(self.parent.lease,p['account_alias'],p['packet_id'],original[3]):pass
        _need(self._original_records(p)==original)
        return original

    def _final_originals(self,p,original,protected):
        # All diagnostic, health and decryption callbacks must already be done.
        # Compare durable publication/slot bytes without another decryption.
        with _owner_scope(self.parent.lease) as guard:published_original(guard,original[3])
        _need(self._original_records(p)==original)
        with _slot(self.parent.lease) as (guard,path):
            _need(guard.api.read_regular(path,maximum=16384)==slot_payload(protected),'PAPER_PRESENCE_CREDENTIAL_CHANGED')
        _need(not self.parent._closed and self.parent.health.reason is None,'EXECUTION_HEALTH_UNVERIFIED')

    def _current(self,p):
        owner=self.parent;_live(owner)
        _need(p['presence_id'] not in self._revoked,self._revoked.get(p['presence_id'],'PAPER_PRESENCE_INVALIDATED'))
        _need(p['component_id']==self.instance and self._issued.get(p['presence_id'])==_sha(p),'PAPER_PRESENCE_OWNER_REPLACED')
        _need(p['owner_generation']==owner.lease.generation and p['owner_instance']==owner.lease.identity.process_instance_id,'PAPER_PRESENCE_OWNER_REPLACED')
        original=self._originals(p);protected=load_paper_slot(owner.lease,p['account_alias'])
        _need(hashlib.sha256(protected.ciphertext).hexdigest()==p['credential_sha256'],'PAPER_PRESENCE_CREDENTIAL_CHANGED')
        result=self._receipt(p)
        with open_paper_credentials(owner.lease,protected) as opened:_reject_reflections(canonical(result),tuple(opened.headers().values()))
        _need(self._originals(p)==original)
        protected=load_paper_slot(owner.lease,p['account_alias'])
        _need(hashlib.sha256(protected.ciphertext).hexdigest()==p['credential_sha256'],'PAPER_PRESENCE_CREDENTIAL_CHANGED')
        _live(owner)
        def final():
            self._final_originals(p,original,protected)
            _need(self._read(p['presence_id'])==(p,None) and p['presence_id'] not in self._revoked)
        def finish():
            _need(self.db is owner.db,'PAPER_PRESENCE_OWNER_REPLACED')
            _need(not owner._closed and owner.health.reason is None,'EXECUTION_HEALTH_UNVERIFIED')
            _need(p['component_id']==self.instance and self._issued.get(p['presence_id'])==_sha(p),'PAPER_PRESENCE_OWNER_REPLACED')
            _need(p['owner_generation']==owner.lease.generation and p['owner_instance']==owner.lease.identity.process_instance_id,'PAPER_PRESENCE_OWNER_REPLACED')
            _need(p['presence_id'] not in self._revoked,'PAPER_PRESENCE_INVALIDATED')
            self._age(p)
        final();finish()
        return final,finish

    def _invalidate_proof(self,p,reason):
        ident=p['presence_id'];self._revoked.setdefault(ident,reason)
        try:
            # Preserve caller work. Sticky local invalidation is immediate;
            # normal inspection can persist it after the caller rolls back.
            if not self.db.in_transaction:self._revoke(p,self._revoked[ident])
        except RuntimeRefused as error:self._reason=self._reason or error.code
        except _INVALID:self._reason=self._reason or 'PAPER_PRESENCE_STATE_CORRUPT'

    def _prepare_proof(self,*,subject,presence_id):
        try:
            _need(not self._closed,'PAPER_PRESENCE_CLOSED');_hash(subject);uuid(presence_id)
            _need(not self.db.in_transaction,'PAPER_PRESENCE_TRANSACTION_OPEN');self._schema()
            p,reason=self._read(presence_id)
            # Bad callers cannot revoke another authenticated subject's receipt.
            _need(p['subject_key']==subject,'READ_OPERATOR_CHANGED')
            try:
                _need(reason is None,reason or 'PAPER_PRESENCE_INVALIDATED')
                final,finish=self._current(p)
                def check():
                    self._schema();final()
                return _final_proof(self.parent,check,finish,lambda code:self._invalidate_proof(p,code),p)
            except RuntimeRefused as error:
                self._invalidate_proof(p,error.code);raise
        except RuntimeRefused as error:
            if error.code in {'PAPER_PRESENCE_STATE_CORRUPT','PAPER_PRESENCE_WRITE_UNVERIFIED'}:
                self._reason=self._reason or error.code
            raise
        except _INVALID:
            self._reason=self._reason or 'PAPER_PRESENCE_STATE_CORRUPT'
            raise RuntimeRefused(self._reason) from None

    def _receipt(self,p):
        return dict(version=1,scope='NATIVE_PAPER_PRESENCE_ONLY',status='ACKNOWLEDGEMENT_RECORDED',current_presence='NOT_ASSERTED',
                    presence_id=p['presence_id'],presence_sha256=_sha(p),project_id=p['project_id'],account_alias=p['account_alias'],packet_id=p['packet_id'],
                    acknowledged_at=p['acknowledged_at'],expires_at=p['expires_at'],transport_authorized=False,financial_accepted=False)

    def _acknowledge(self,packet):
        owner=self.parent;ident=packet['request_id'];value=owner._read(packet['command']['packet_id'])
        _need(value['subject_key']==packet['subject_key'],'READ_OPERATOR_CHANGED')
        _live(owner);self._clock();manifest=_account_manifest(owner,value)
        proposal,record,diagnostic,_,_=binding._live(owner,value,manifest)
        context=proposal._context
        _need(record['confirmed_at'] is not None,'PAPER_PRESENCE_CONFIRMATION_REQUIRED')
        _need(diagnostic['transport_provenance']=='PAPER_TLS','PAPER_PRESENCE_NATIVE_ORIGIN_REQUIRED')
        facts=record['proposal'];alias=binding._alias(owner,value['account_alias'],facts['identity_sha256']);_need(alias is not None)
        now,mono=self._clock()
        p=dict(version=1,record_type='NativePaperPresence',presence_id=ident,request_sha256=_sha(packet),project_id=owner.lease.project_id,
               subject_key=packet['subject_key'],account_alias=value['account_alias'],packet_id=value['packet_id'],owner_instance=owner.lease.identity.process_instance_id,
               owner_generation=owner.lease.generation,component_id=self.instance,credential_sha256=value['credential_sha256'],identity_sha256=facts['identity_sha256'],
               account_sha256=_sha(value),confirmation_sha256=_sha(record),alias_sha256=_sha(alias),manifest_sha256=_sha(manifest),
               acknowledged_at=now.isoformat(),expires_at=(now+timedelta(seconds=300)).isoformat(),acknowledged_mono=mono)
        raw=canonical(p).decode();_need(len(raw.encode())<=8192,'PAPER_PRESENCE_RECORD_BOUND')
        protected=load_paper_slot(owner.lease,p['account_alias'])
        with open_paper_credentials(owner.lease,protected) as opened:_reject_reflections(canonical(dict(record=p,receipt=self._receipt(p))),tuple(opened.headers().values()))
        _need(proposal._context._account_id not in raw,'PAPER_READ_PRIVATE_ID_REFLECTION')
        _need(self.db.execute('SELECT count(*) FROM paper_presence_records').fetchone()[0]<128,'PAPER_PRESENCE_HISTORY_BOUND')
        with self.db:
            # Health callbacks may commit their own durable halt. Finish every
            # callback before inserting a receipt into this connection.
            _need(binding._live(owner,value,manifest)[:2]==(proposal,record))
            _need(self._originals(p)==(value,record,alias,manifest))
            context.diagnostic()
            protected=load_paper_slot(owner.lease,p['account_alias'])
            _need(hashlib.sha256(protected.ciphertext).hexdigest()==p['credential_sha256'],'PAPER_PRESENCE_CREDENTIAL_CHANGED')
            _live(owner)
            self._final_originals(p,(value,record,alias,manifest),protected)
            _need(owner._account_proposal is proposal and not proposal._closed and proposal._context is context
                  and owner._preflight is context and not context._closed and context._owner is owner)
            _final_account(context);self._age(p)
            _need(not self.db.in_transaction,'PAPER_PRESENCE_TRANSACTION_OPEN')
            changed=self.db.execute('INSERT INTO paper_presence_records VALUES(?,?,?,NULL)',(ident,_sha(p),raw))
            _need(changed.rowcount==1 and self._read(ident)==(p,None),'PAPER_PRESENCE_WRITE_UNVERIFIED')
            _need(self._original_records(p)==(value,record,alias,manifest))
            _need(owner._account_proposal is proposal and not proposal._closed and proposal._context is context
                  and owner._preflight is context and not context._closed and context._owner is owner
                  and owner.health.reason is None,'PAPER_PRESENCE_ACK_INVALIDATED')
            # Only durable readbacks and pure checks occur after INSERT. Never
            # invoke a diagnostic/health callback that could commit it early.
            _final_account(context)
            self._age(p)
        self._issued[ident]=_sha(p)
        return self._receipt(p)

    def handle(self,packet):
        _need(not self._closed,'PAPER_PRESENCE_CLOSED')
        try:
            _need(type(packet) is dict and set(packet)=={'request_id','subject_key','command'},'CONTROL_PAYLOAD_DENIED')
            uuid(packet['request_id']);_hash(packet['subject_key']);command=packet['command']
            _need(type(command) is dict and type(command.get('operation')) is str,'CONTROL_PAYLOAD_DENIED')
            op=command['operation'];keys={'acknowledge':{'operation','packet_id'},'inspect':{'operation','presence_id'}}
            _need(op in keys and set(command)==keys[op],'CONTROL_PAYLOAD_DENIED')
            uuid(command['packet_id'] if op=='acknowledge' else command['presence_id'])
            _need(not self.db.in_transaction,'PAPER_PRESENCE_TRANSACTION_OPEN');self._schema(create=op=='acknowledge')
            if op=='acknowledge':
                if packet['request_id'] in self._issued or self.db.execute('SELECT 1 FROM paper_presence_records WHERE presence_id=?',(packet['request_id'],)).fetchone():
                    p,_=self._read(packet['request_id']);_need(p['request_sha256']==_sha(packet),'REQUEST_CONFLICT')
                    return self._receipt(p)
                return self._acknowledge(packet)
            p,reason=self._read(command['presence_id']);_need(p['subject_key']==packet['subject_key'],'READ_OPERATOR_CHANGED')
            if reason is None:
                try:self._current(p)
                except RuntimeRefused as error:reason=self._revoke(p,error.code)
            result=dict(self._receipt(p),presence_status='CURRENT' if reason is None else 'INVALIDATED',reason=reason,order_admission='BLOCKED')
            _need(len(canonical(result))<=4096,'PAPER_PRESENCE_RECORD_BOUND');return result
        except RuntimeRefused as error:
            # A failed revocation or corrupted durable record cannot regain
            # authority merely because later reads return the old bytes again.
            if error.code in {'PAPER_PRESENCE_STATE_CORRUPT','PAPER_PRESENCE_WRITE_UNVERIFIED'}:
                self._reason=self._reason or error.code
            raise
        except _INVALID:
            self._reason='PAPER_PRESENCE_STATE_CORRUPT';raise RuntimeRefused(self._reason) from None
