"""Immutable native proposed intents. Confirmation never grants order authority."""
from datetime import timedelta
import hashlib,json,math,re,sqlite3
from uuid import uuid4
from compertum.data.encoding import canonical
from compertum.domain import ContractError
from compertum.events import uuid
from compertum.paper_contracts import strict_json,timestamp
from compertum.paper_portfolio import TERMINAL
from .errors import RuntimeRefused
from .paper_preflight import _live,_measure
from .paper_credential_slot import load_paper_slot
from .paper_credentials import open_paper_credentials
from .paper_read_secrecy import _reject_reflections
from .paper_native_intent_terms import exact_terms,time_bounds,PURPOSES
from .paper_native_intent_commit import finish_operation

_INVALID=(ContractError,ValueError,TypeError,KeyError,AttributeError,OverflowError,RecursionError,UnicodeError,sqlite3.Error)
_SCHEMA={
    'paper_native_intents':'CREATE TABLE paper_native_intents(intent_id TEXT PRIMARY KEY,sha256 TEXT NOT NULL,body TEXT NOT NULL)',
    'paper_native_confirmations':'CREATE TABLE paper_native_confirmations(confirmation_id TEXT PRIMARY KEY,intent_id TEXT NOT NULL UNIQUE,sha256 TEXT NOT NULL,body TEXT NOT NULL)',
    'paper_native_invalidations':'CREATE TABLE paper_native_invalidations(intent_id TEXT PRIMARY KEY,reason TEXT NOT NULL)',
}
_TABLES=set(_SCHEMA)
_FIELDS={'version','record_type','intent_id','request_sha256','project_id','subject_key','account_alias','packet_id',
    'fresh_job_id','capture_id','purpose','terms','context_sha256','presence_id','presence_sha256','owner_instance',
    'owner_generation','component_id','credential_sha256','identity_sha256','created_at','created_mono','expires_at',
    'operation_deadline','target_observation_sha256'}
_CONF_FIELDS={'version','record_type','confirmation_id','request_sha256','intent_id','intent_sha256','project_id',
    'subject_key','account_alias','purpose','presence_id','presence_sha256','owner_instance','owner_generation',
    'component_id','credential_sha256','identity_sha256','confirmed_at','confirmed_mono','expires_at'}
_COMMON=('project_id','subject_key','account_alias','purpose','presence_id','presence_sha256','owner_instance',
    'owner_generation','component_id','credential_sha256','identity_sha256','expires_at')


def _need(value,code='PAPER_INTENT_STATE_CORRUPT'):
    if not value:raise RuntimeRefused(code)


def _sha(value):return hashlib.sha256(canonical(value)).hexdigest()


def _hash(value):_need(type(value) is str and re.fullmatch('[0-9a-f]{64}',value) is not None)


def _mono(value):_need(type(value) in (int,float) and math.isfinite(value) and 0<=value<1e15)


class _NativeIntents:
    def __init__(self,parent):
        self.parent=parent;self.db=parent.db;self.instance=str(uuid4());self._issued={};self._confirmed={};self._revoked={}
        self._closed=False;self._reason=None;self._owners=(parent.store,parent.reserve,parent.health,parent.lease,parent.db)
        self._start,self._start_mono=_measure();self._last,self._last_mono=self._start,self._start_mono

    def __repr__(self):return '<NativePaperIntents private state redacted>'
    def __reduce_ex__(self,protocol):raise RuntimeRefused('PAPER_INTENT_SERIALIZATION_FORBIDDEN')
    def close(self):self._closed=True;self._issued.clear();self._confirmed.clear();self._revoked.clear()

    def _schema(self,create=False):
        found={r[0] for r in self.db.execute("SELECT name FROM sqlite_master WHERE type='table'") if r[0] in _TABLES}
        version=self.db.execute("SELECT value FROM state WHERE key='paper_native_intent_version'").fetchone()
        _need((not found and version is None and not self._issued) or (found==_TABLES and version==('1',)))
        if found:
            for table in _TABLES:
                _need(self.db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchall()==[(_SCHEMA[table],)])
                _need(self.db.execute('SELECT count(*) FROM '+table).fetchone()[0]<=128,'PAPER_INTENT_HISTORY_BOUND')
            return
        _need(create,'PAPER_INTENT_UNKNOWN')
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            for sql in _SCHEMA.values():self.db.execute(sql)
            changed=self.db.execute("INSERT INTO state VALUES('paper_native_intent_version','1')")
            _need(changed.rowcount==1,'PAPER_INTENT_WRITE_UNVERIFIED');self._schema()

    def _decode(self,row,fields):
        _need(row is not None and type(row[1]) is str)
        pin,raw=row;p=strict_json(raw.encode())
        _need(type(p) is dict and set(p)==fields and canonical(p).decode()==raw and _sha(p)==pin)
        _need(type(p['version']) is int and p['version']==1)
        for key in fields:
            if key.endswith('_sha256') and p[key] is not None:_hash(p[key])
        for key in ('project_id','subject_key'):_hash(p[key])
        _need(p['project_id']==self.parent.lease.project_id)
        _need(type(p['account_alias']) is str and re.fullmatch('[A-Za-z0-9][A-Za-z0-9_-]{0,63}',p['account_alias']) is not None)
        _need(type(p['owner_generation']) is int and 0<p['owner_generation']<2**63)
        for key in ('owner_instance','component_id','presence_id'):uuid(p[key])
        return p

    def _one(self,sql,args):
        rows=self.db.execute(sql,args).fetchmany(2);_need(len(rows)<=1)
        return rows[0] if rows else None

    def _read(self,ident):
        row=self._one('SELECT sha256,CASE WHEN length(CAST(body AS BLOB))<=16384 THEN body END FROM paper_native_intents WHERE intent_id=?',(ident,))
        _need(row is not None,'PAPER_INTENT_STATE_CORRUPT' if ident in self._issued else 'PAPER_INTENT_UNKNOWN')
        p=self._decode(row,_FIELDS);_need(p['record_type']=='NativePaperIntent' and p['intent_id']==ident)
        if ident in self._issued:_need(self._issued[ident][0]==_sha(p))
        for key in ('intent_id','packet_id'):uuid(p[key])
        _need(p['purpose'] in PURPOSES and exact_terms(p['purpose'],p['terms'],stored=True)==p['terms'])
        if p['purpose']=='CANCEL':
            _need(p['fresh_job_id'] is p['capture_id'] is None);_hash(p['target_observation_sha256'])
        else:
            uuid(p['fresh_job_id']);uuid(p['capture_id']);_need(p['target_observation_sha256'] is None)
        created,expires=timestamp(p['created_at']),timestamp(p['expires_at']);_mono(p['created_mono'])
        _need(created.isoformat()==p['created_at'] and expires.isoformat()==p['expires_at'] and timedelta(0)<expires-created<=timedelta(seconds=60))
        if p['purpose']=='CLOSE_LONG':
            end=timestamp(p['operation_deadline']);_need(end.isoformat()==p['operation_deadline'] and expires<=end<=created+timedelta(seconds=600))
        else:_need(p['operation_deadline'] is None)
        return p

    def _confirmation(self,p):
        ident=p['intent_id'];row=self._one('SELECT confirmation_id,sha256,CASE WHEN length(CAST(body AS BLOB))<=16384 THEN body END FROM paper_native_confirmations WHERE intent_id=?',(ident,))
        if row is None:
            _need(ident not in self._confirmed);return None
        c=self._decode(row[1:],_CONF_FIELDS);_need(c['record_type']=='NativePaperConfirmation' and row[0]==c['confirmation_id'])
        uuid(c['confirmation_id']);_need(c['intent_id']==ident and c['intent_sha256']==_sha(p))
        _need(all(c[k]==p[k] for k in _COMMON));_mono(c['confirmed_mono'])
        at=timestamp(c['confirmed_at']);_need(at.isoformat()==c['confirmed_at'] and timestamp(p['created_at'])<=at<timestamp(p['expires_at']))
        _need(0<=c['confirmed_mono']-p['created_mono']<60)
        if ident in self._confirmed:_need(self._confirmed[ident]==_sha(c))
        return c

    def _reason_for(self,ident):
        row=self._one('SELECT reason FROM paper_native_invalidations WHERE intent_id=?',(ident,))
        if row is not None:
            _need(type(row[0]) is str and re.fullmatch('[A-Z][A-Z0-9_]{0,95}',row[0]) is not None)
            if ident in self._revoked:_need(self._revoked[ident]==row[0])
            if not self.db.in_transaction:self._revoked[ident]=row[0]
        return row[0] if row is not None else self._revoked.get(ident)

    def _invalidate(self,p,reason):
        ident=p['intent_id'];self._revoked.setdefault(ident,reason);reason=self._revoked[ident]
        _need(not self.db.in_transaction,'PAPER_INTENT_TRANSACTION_OPEN')
        row=self.db.execute('SELECT reason FROM paper_native_invalidations WHERE intent_id=?',(ident,)).fetchone()
        if row is not None:_need(row==(reason,));return reason
        with self.db:
            changed=self.db.execute('INSERT INTO paper_native_invalidations VALUES(?,?)',(ident,reason))
            _need(changed.rowcount==1 and self.db.execute('SELECT reason FROM paper_native_invalidations WHERE intent_id=?',(ident,)).fetchone()==(reason,),'PAPER_INTENT_WRITE_UNVERIFIED')
        return reason

    def _clock(self):
        owner=self.parent
        if self._closed or owner._closed or owner._intents is not self or any(a is not b for a,b in zip(self._owners,(owner.store,owner.reserve,owner.health,owner.lease,owner.db))):
            self._reason=self._reason or 'PAPER_INTENT_OWNER_REPLACED'
        _need(self._reason is None,self._reason or 'PAPER_INTENT_INVALIDATED')
        now,mono=_measure();du=(now-self._last).total_seconds();dm=mono-self._last_mono
        if du<0 or dm<0 or abs((now-self._start).total_seconds()-(mono-self._start_mono))>5:self._reason='PAPER_INTENT_CLOCK_CHANGED'
        elif du>15 or dm>15:self._reason='PAPER_INTENT_SERVICE_GAP'
        _need(self._reason is None,self._reason or 'PAPER_INTENT_INVALIDATED')
        self._last,self._last_mono=now,mono;return now,mono

    def _age(self,p):
        now,mono=self._clock();du=(now-timestamp(p['created_at'])).total_seconds();dm=mono-p['created_mono']
        limit=(timestamp(p['expires_at'])-timestamp(p['created_at'])).total_seconds()
        _need(du>=0 and dm>=0 and abs(du-dm)<=5,'PAPER_INTENT_CLOCK_CHANGED')
        _need(du<limit and dm<limit,'PAPER_INTENT_EXPIRED');return now,mono

    def tick(self):
        if self._closed:return
        try:self._clock()
        except RuntimeRefused as error:self._reason=self._reason or error.code

    def _receipt(self,p,c=None):
        value=dict(version=1,scope='NATIVE_PAPER_PROPOSED_INTENT_ONLY',status='INTENT_RECORDED' if c is None else 'CONFIRMATION_RECORDED',
            current_validity='NOT_ASSERTED',intent_id=p['intent_id'],intent_sha256=_sha(p),purpose=p['purpose'],terms=p['terms'],
            account_alias=p['account_alias'],created_at=p['created_at'],expires_at=p['expires_at'],operation_deadline=p['operation_deadline'],
            order_admission='BLOCKED',transport_authorized=False,financial_accepted=False)
        if c is not None:value.update(confirmation_id=c['confirmation_id'],confirmation_sha256=_sha(c),confirmed_at=c['confirmed_at'])
        return value

    def _scan(self,p,c=None):
        protected=load_paper_slot(self.parent.lease,p['account_alias'])
        _need(hashlib.sha256(protected.ciphertext).hexdigest()==p['credential_sha256'],'PAPER_INTENT_CREDENTIAL_CHANGED')
        raw=canonical(dict(intent=p,confirmation=c,receipt=self._receipt(p,c)));_need(len(raw)<=32768,'PAPER_INTENT_RECORD_BOUND')
        with open_paper_credentials(self.parent.lease,protected) as opened:_reject_reflections(raw,tuple(opened.headers().values()))
        _need(self.parent._preflight._account_id.encode() not in raw,'PAPER_READ_PRIVATE_ID_REFLECTION')

    def _records_current(self,p,c):
        self._schema();_need(self._read(p['intent_id'])==p and self._confirmation(p)==c)
        _need(self._reason_for(p['intent_id']) is None,'PAPER_INTENT_INVALIDATED')

    def _proofs(self,p):
        self._age(p);ident=p['intent_id'];issued=self._issued.get(ident)
        _need(issued is not None and issued[0]==_sha(p) and p['component_id']==self.instance,'PAPER_INTENT_OWNER_REPLACED')
        context,presence=issued[1:3]
        _need(self.parent._presence is presence and p['context_sha256']==context._binding,'PAPER_INTENT_INPUT_REPLACED')
        first=context._prepare_proof();second=presence._prepare_proof(subject=p['subject_key'],presence_id=p['presence_id'])
        _need(_sha(json.loads(second._content))==p['presence_sha256'],'PAPER_INTENT_PRESENCE_CHANGED')
        return first,second

    def _prepare(self,packet):
        owner=self.parent;command=packet['command'];purpose=command['purpose'];terms=exact_terms(purpose,command['terms'])
        _need(self.db.execute('SELECT count(*) FROM paper_native_intents').fetchone()[0]<128,'PAPER_INTENT_HISTORY_BOUND')
        _live(owner);self._clock();subject=packet['subject_key'];ident=packet['request_id'];context=None
        try:
            args=dict(subject=subject,packet_id=command['packet_id'])
            context=owner.account_context(**args) if purpose=='CANCEL' else owner.input_context(**args,fresh_job_id=command['fresh_job_id'],capture_id=command['capture_id'])
            diagnostic=context.diagnostic();preflight=owner.preflight(command['packet_id']).diagnostic()
            _need(diagnostic['confirmation_status']=='CONFIRMED_CURRENT_CONTEXT' and diagnostic['account_transport_provenance']=='PAPER_TLS','PAPER_INTENT_ACCOUNT_UNVERIFIED')
            if purpose!='CANCEL':
                _need(diagnostic['quote_valid'] and diagnostic['asset_valid'],'PAPER_INTENT_MARKET_UNVERIFIED')
                _need(owner._market._producer._plan.to_payload()['symbol']==terms['symbol'],'PAPER_INTENT_SYMBOL_CHANGED')
            _need(owner._presence is not None,'PAPER_INTENT_PRESENCE_REQUIRED')
            proofs=(context._prepare_proof(),owner._presence._prepare_proof(subject=subject,presence_id=command['presence_id']))
            presence=json.loads(proofs[1]._content);value=owner._read(command['packet_id'])
            from .paper_account_binding import _stored
            account=_stored(owner,command['packet_id'])
            _need(all(presence[k]==value[k] for k in ('project_id','subject_key','account_alias','credential_sha256','owner_instance','owner_generation')))
            _need(presence['identity_sha256']==account['proposal']['identity_sha256'])
            target=None
            if purpose=='CANCEL':
                rows=[row for _,raw in owner._preflight._records for r in [json.loads(raw)] if r['operation']=='ORDERS' for row in r['observation']['rows'] if row['id']==terms['order_id'] and row['symbol']==terms['symbol'] and row['status'] not in TERMINAL]
                _need(len(rows)==1,'PAPER_INTENT_TARGET_UNVERIFIED');target=_sha(rows[0])
            now,mono=self._clock();end,operation=time_bounds(purpose,terms,now,preflight);end=min(end,timestamp(presence['expires_at']))
            p=dict(version=1,record_type='NativePaperIntent',intent_id=ident,request_sha256=_sha(packet),project_id=value['project_id'],
                subject_key=subject,account_alias=value['account_alias'],packet_id=value['packet_id'],fresh_job_id=command.get('fresh_job_id'),capture_id=command.get('capture_id'),
                purpose=purpose,terms=terms,context_sha256=context._binding,presence_id=presence['presence_id'],presence_sha256=_sha(presence),
                owner_instance=value['owner_instance'],owner_generation=value['owner_generation'],component_id=self.instance,
                credential_sha256=value['credential_sha256'],identity_sha256=presence['identity_sha256'],created_at=now.isoformat(),created_mono=mono,
                expires_at=end.isoformat(),operation_deadline=operation.isoformat() if operation else None,target_observation_sha256=target)
            raw=canonical(p);_need(len(raw)<=16384,'PAPER_INTENT_RECORD_BOUND');receipt=self._receipt(p);self._scan(p)
            def write():
                changed=self.db.execute('INSERT INTO paper_native_intents VALUES(?,?,?)',(ident,_sha(p),raw.decode()))
                _need(changed.rowcount==1,'PAPER_INTENT_WRITE_UNVERIFIED')
            finish_operation(owner,proofs,lambda:self._records_current(p,None),lambda:self._age(p),write)
            self._issued[ident]=(_sha(p),context,owner._presence);return receipt
        except BaseException:
            if context is not None:context.close()
            raise

    def _confirm(self,packet,p):
        command=packet['command'];_need(command['intent_sha256']==_sha(p),'PAPER_INTENT_HASH_MISMATCH')
        _need(self._confirmation(p) is None,'PAPER_INTENT_ALREADY_CONFIRMED')
        _need(self._reason_for(p['intent_id']) is None,'PAPER_INTENT_INVALIDATED')
        try:
            proofs=self._proofs(p);now,mono=self._age(p)
            c=dict(version=1,record_type='NativePaperConfirmation',confirmation_id=packet['request_id'],request_sha256=_sha(packet),
                intent_id=p['intent_id'],intent_sha256=_sha(p),confirmed_at=now.isoformat(),confirmed_mono=mono,**{k:p[k] for k in _COMMON})
            raw=canonical(c);_need(len(raw)<=16384,'PAPER_INTENT_RECORD_BOUND');receipt=self._receipt(p,c);self._scan(p,c)
            def write():
                changed=self.db.execute('INSERT INTO paper_native_confirmations VALUES(?,?,?,?)',(c['confirmation_id'],p['intent_id'],_sha(c),raw.decode()))
                _need(changed.rowcount==1,'PAPER_INTENT_WRITE_UNVERIFIED')
            finish_operation(self.parent,proofs,lambda:self._records_current(p,c),lambda:self._age(p),write)
            self._confirmed[p['intent_id']]=_sha(c);return receipt
        except RuntimeRefused as error:self._invalidate(p,error.code);raise

    def _inspect(self,p):
        c=self._confirmation(p);reason=self._reason_for(p['intent_id'])
        if reason is None:
            try:
                proofs=self._proofs(p);self._scan(p,c)
                finish_operation(self.parent,proofs,lambda:self._records_current(p,c),lambda:self._age(p))
            except RuntimeRefused as error:reason=self._invalidate(p,error.code)
        required={'OWNERSHIP_UNVERIFIED','ECONOMIC_RECONCILIATION_UNVERIFIED','EXACT_CONSUMPTION_UNVERIFIED'}
        required.add('TARGET_RECONCILIATION_UNVERIFIED' if p['purpose']=='CANCEL' else 'RISK_UNVERIFIED')
        result=dict(self._receipt(p,c),intent_status='INVALIDATED' if reason else 'CURRENT_CONFIRMED' if c else 'CURRENT_UNCONFIRMED',
            reason=reason,unverified_requirements=sorted(required))
        _need(len(canonical(result))<=16384,'PAPER_INTENT_RECORD_BOUND');return result

    def _command(self,packet):
        # Caller mistakes must not become sticky corruption of stored evidence.
        try:
            _need(type(packet) is dict and set(packet)=={'request_id','subject_key','command'},'CONTROL_PAYLOAD_DENIED')
            uuid(packet['request_id']);_hash(packet['subject_key']);command=packet['command']
            _need(type(command) is dict and type(command.get('operation')) is str,'CONTROL_PAYLOAD_DENIED');op=command['operation']
            fields={'prepare':{'operation','packet_id','presence_id','purpose','terms'},'confirm':{'operation','intent_id','intent_sha256'},'inspect':{'operation','intent_id'}}
            _need(op in fields,'CONTROL_PAYLOAD_DENIED');expected=fields[op]
            if op=='prepare' and command.get('purpose')!='CANCEL':expected=expected|{'fresh_job_id','capture_id'}
            _need(set(command)==expected,'CONTROL_PAYLOAD_DENIED')
            if op=='prepare':
                _need(type(command['purpose']) is str and command['purpose'] in PURPOSES,'CONTROL_PAYLOAD_DENIED')
                for key in ('packet_id','presence_id','fresh_job_id','capture_id'):
                    if key in command:uuid(command[key])
            else:
                uuid(command['intent_id'])
                if op=='confirm':_hash(command['intent_sha256'])
        except (RuntimeRefused,*_INVALID):raise RuntimeRefused('CONTROL_PAYLOAD_DENIED') from None
        if op=='prepare':
            try:exact_terms(command['purpose'],command['terms'])
            except (RuntimeRefused,*_INVALID):raise RuntimeRefused('PAPER_INTENT_TERMS_INVALID') from None
        return op,command

    def handle(self,packet):
        op,command=self._command(packet)
        try:
            _need(not self.db.in_transaction,'PAPER_INTENT_TRANSACTION_OPEN');self._schema(create=op=='prepare')
            if op!='inspect':
                old=self.db.execute('SELECT intent_id FROM paper_native_intents WHERE intent_id=?',(packet['request_id'],)).fetchone()
                confirmation=self.db.execute('SELECT intent_id FROM paper_native_confirmations WHERE confirmation_id=?',(packet['request_id'],)).fetchone()
                _need(not(old and confirmation))
                if old or confirmation:
                    p=self._read((old or confirmation)[0]);c=self._confirmation(p) if confirmation else None
                    _need((c or p)['request_sha256']==_sha(packet),'REQUEST_CONFLICT');return self._receipt(p,c)
            if op=='prepare':return self._prepare(packet)
            p=self._read(command['intent_id']);_need(p['subject_key']==packet['subject_key'],'READ_OPERATOR_CHANGED')
            return self._confirm(packet,p) if op=='confirm' else self._inspect(p)
        except RuntimeRefused as error:
            if error.code in {'PAPER_INTENT_STATE_CORRUPT','PAPER_INTENT_WRITE_UNVERIFIED'}:self._reason=self._reason or error.code
            raise
        except _INVALID:
            self._reason=self._reason or 'PAPER_INTENT_STATE_CORRUPT';raise RuntimeRefused(self._reason) from None
