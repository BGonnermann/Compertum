"""Private portfolio observations; missing ownership and risk remain blocking."""
import hashlib,json,sqlite3
from dataclasses import dataclass
from compertum.data.encoding import canonical
from compertum.domain import ContractError
from compertum.attempt_records import validate_pair,is_paper,is_native
from .errors import RuntimeRefused
from .owners import _MUTEX,_owner_scope
from .paper_account_context import _PaperAccountContext
from .paper_input_context import _PaperInputContext
from .paper_opening import _original as original_opening
from .paper_opening_records import cash_matches
from .paper_credential_slot import load_paper_slot
from .paper_credentials import open_paper_credentials
from .paper_read_secrecy import _reject_reflections
from . import paper_account_binding as binding

_FACTORY=object()
_COLUMNS={
    'fake_intents':'account intent_id client_id body decision state order_id filled notional conflict',
    'fake_intent_events':'seq account intent_id kind body',
    'fake_broker_events':'account event_id sha256',
    'fake_event_applications':'account event_id intent_id',
    'fake_incidents':'account intent_id next_index last_elapsed started_at active',
    'fake_execution_session':'singleton owner_instance state',
}
_INVALID=(ContractError,ValueError,TypeError,KeyError,AttributeError,OverflowError,RecursionError,UnicodeError,sqlite3.Error)


def _need(value,code='PAPER_PORTFOLIO_CONTEXT_CHANGED'):
    if not value:raise RuntimeRefused(code)


def _journal_snapshot(owner):
    """Read complete bounded rows, including unattempted and unclassified history."""
    db=owner.db;tables=tuple(_COLUMNS)
    schema=db.execute('SELECT type,name,tbl_name,CASE WHEN length(CAST(sql AS BLOB))<=16384 THEN sql END '
        'FROM sqlite_master WHERE tbl_name IN ('+','.join('?' for _ in tables)+') LIMIT 65',tables).fetchall()
    _need(len(schema)<=64)
    schema.sort(key=lambda row:(row[0],row[1]))
    present={row[1] for row in schema if row[0]=='table'}
    _need(not schema or present==set(tables),'PAPER_PORTFOLIO_SCHEMA_UNVERIFIED')
    _need(all(row[0] in {'table','index','trigger'} for row in schema),'PAPER_PORTFOLIO_SCHEMA_UNVERIFIED')
    _need(all(row[3] is not None or row[0]=='index' and row[1].startswith('sqlite_autoindex_') for row in schema))
    rows={};columns={};used=0
    for table,expected in _COLUMNS.items():
        rows[table]=[]
        if table not in present:continue
        info=db.execute('PRAGMA table_xinfo('+table+')').fetchall();columns[table]=info
        names=expected.split();_need([row[1] for row in info]==names,'PAPER_PORTFOLIO_SCHEMA_UNVERIFIED')
        _need(all(row[6]==0 for row in info),'PAPER_PORTFOLIO_SCHEMA_UNVERIFIED')
        _need(all(row[2]==('INTEGER' if row[1] in {'seq','filled','conflict','next_index','active','singleton'}
            else 'REAL' if row[1]=='last_elapsed' else 'TEXT') for row in info),'PAPER_PORTFOLIO_SCHEMA_UNVERIFIED')
        expressions=','.join('CASE WHEN length(CAST("'+name+'" AS BLOB))<=65536 THEN "'+name+'" END' for name in names)
        lengths=','.join('coalesce(length(CAST("'+name+'" AS BLOB)),0)' for name in names)
        maximum=256 if table=='fake_intents' else 512
        query='SELECT '+expressions+','+lengths+' FROM '+table+' LIMIT '+str(maximum+1)
        for row in db.execute(query):
            values=row[:len(names)];sizes=row[len(names):]
            _need(all(size<=65536 for size in sizes),'PAPER_PORTFOLIO_HISTORY_BOUND')
            used+=sum(sizes);_need(used<=1024**2 and len(rows[table])<maximum,'PAPER_PORTFOLIO_HISTORY_BOUND')
            rows[table].append(values)
        rows[table].sort(key=canonical)
    head=db.execute("SELECT key,CASE WHEN length(CAST(value AS BLOB))<=16384 THEN value END FROM state WHERE key IN ('fake_attempt_guard_head','fake_attempt_conflict','execution_status') ORDER BY key").fetchall()
    _need(all(row[1] is not None for row in head))
    sequence=[]
    if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='sqlite_sequence'").fetchone():
        sequence=db.execute("SELECT seq FROM sqlite_sequence WHERE name='fake_intent_events' LIMIT 2").fetchall()
        _need(len(sequence)<=1 and all(type(row[0]) is int and row[0]>=0 for row in sequence))
    history=binding._history(owner)
    _need(history['status'] in {'VERIFIED_ZERO_PRE_SCHEMA','VERIFIED_HISTORY'},'PAPER_PORTFOLIO_HISTORY_UNVERIFIED')
    pin=hashlib.sha256(canonical(dict(schema=schema,columns=columns,rows=rows,head=head,sequence=sequence,
        external_history=history))).hexdigest()
    classes=dict(fake=0,preparation=0,unknown=0)
    for row in rows['fake_intents']:
        try:
            intent,decision,_=validate_pair(json.loads(row[3]),json.loads(row[4]))
            _need(canonical(intent).decode()==row[3] and canonical(decision).decode()==row[4])
            kind='native' if is_native(intent) else 'preparation' if is_paper(intent) else 'fake'
        except (RuntimeRefused,*_INVALID):kind='unknown'
        classes[kind]=classes.get(kind,0)+1
    return dict(sha256=pin,counts={table:len(values) for table,values in rows.items()},classes=classes,
        retained_sequence=sequence[0][0] if sequence else 0,
        retained_attempts=history['sequence'],guard_empty=history['empty'])


def _diagnostic(context,journal,value):
    owner=context._owner;alias=value['account_alias']
    opening=binding._state(owner,'paper_opening:'+alias)
    initial_cash=None
    if opening is not None:opening,initial_cash=original_opening(owner,alias)
    preflight=owner.preflight(context._packet)
    observation=json.loads(preflight.content)
    account=next(json.loads(raw)['observation'] for _,raw in preflight._records if json.loads(raw)['operation']=='ACCOUNT')
    matches=initial_cash is not None and cash_matches(initial_cash,account['cash'])
    empty=(journal['guard_empty'] and journal['retained_attempts']==0
        and not any(journal['counts'].values()) and journal['retained_sequence']==0)
    clean=(empty and matches and opening['reference']['disposition']=='CLEAN_ZERO_HISTORY'
        and value['confirmation_status']=='CONFIRMED_CURRENT_CONTEXT' and observation['positions']==observation['orders']==0
        and observation['order_coverage']=='OBSERVED_SHORT_TERMINAL_PAGE' and account['status']=='ACTIVE'
        and not any(account[key] for key in ('trading_blocked','account_blocked','trade_suspended_by_user')))
    result=dict(version=1,record_type='PaperPortfolioObservation',status='BLOCKED',
        observation_status='CLEAN_ZERO_OPENING_OBSERVED' if clean else 'BLOCKED',
        history_classification='VERIFIED_EMPTY_LOCAL_HISTORY' if empty else 'NONEMPTY_LOCAL_HISTORY',
        cash_observation='OPENING_UNVERIFIED' if opening is None else 'MATCHES_IMMUTABLE_OPENING' if matches else 'UNEXPLAINED_CASH_CHANGE',
        journal_counts=journal['counts'],record_classes=journal['classes'],retained_attempts=journal['retained_attempts'],
        unverified_requirements=sorted(set(value.get('unverified_requirements',value.get('deficiencies',[])))|{'OWNERSHIP_UNVERIFIED',
            'ECONOMIC_COVERAGE_UNVERIFIED','FEE_ACTION_EVIDENCE_UNVERIFIED','RISK_UNVERIFIED','DURABLE_CONSUMPTION_UNVERIFIED'}),
        financial_accepted=False,transport_authorized=False,research_eligible=False,actual_flat=None)
    raw=canonical(result);_need(len(raw)<=16384)
    protected=load_paper_slot(owner.lease,alias)
    with open_paper_credentials(owner.lease,protected) as credentials:_reject_reflections(raw,tuple(credentials.headers().values()))
    _need(preflight._account_id.encode() not in raw,'PAPER_READ_PRIVATE_ID_REFLECTION')
    return result


@dataclass(frozen=True,slots=True,repr=False,init=False)
class _PortfolioContext:
    _context:object
    _owner:object
    _db:object
    _pin:str
    _closed:bool
    def __init__(self,*,_factory=None,**fields):
        _need(_factory is _FACTORY,'PAPER_PORTFOLIO_UNQUALIFIED')
        for key,value in fields.items():object.__setattr__(self,key,value)
    def __repr__(self):return '<PrivatePaperPortfolioContext redacted>'
    def __reduce_ex__(self,protocol):raise RuntimeRefused('PAPER_PORTFOLIO_SERIALIZATION_FORBIDDEN')
    def close(self):
        with _MUTEX:object.__setattr__(self,'_closed',True)
    def _prepare_proof(self):
        with _MUTEX:
            _need(not self._closed,'PAPER_PORTFOLIO_CONTEXT_UNAVAILABLE')
            # This guard precedes callbacks that would revoke the borrowed context.
            try:pending=self._db.in_transaction
            except sqlite3.Error:
                self.close();self._context.close();raise RuntimeRefused('PAPER_PORTFOLIO_DATABASE_CLOSED') from None
            _need(not pending,'PAPER_PORTFOLIO_TRANSACTION_OPEN')
            context=self._context;owner=self._owner
            try:
                with _owner_scope(owner.lease),owner.store._live():
                    _need(context._owner is owner and owner.db is self._db and not context._closed)
                    journal=_journal_snapshot(owner);_need(journal['sha256']==self._pin)
                    proof=context._prepare_proof()
                    result=_diagnostic(context,journal,json.loads(proof._content))
                    check,finish,invalidate=proof._check,proof._finish,proof._invalidate
                    def checked():
                        _need(not self._closed and context._owner is owner and owner.db is self._db)
                        check();_need(_journal_snapshot(owner)['sha256']==self._pin)
                    def finished():
                        finish();_need(not self._closed and not context._closed)
                    def invalidated(reason):
                        invalidate(reason);self.close()
                    proof._check=checked;proof._finish=finished;proof._invalidate=invalidated
                    proof._content=canonical(result)
                    return proof
            except RuntimeRefused:
                self.close();context.close();raise
            except _INVALID:
                self.close();context.close();raise RuntimeRefused('PAPER_PORTFOLIO_INVALID') from None
    def diagnostic(self):return self._prepare_proof()._verify()


def _portfolio_context(context):
    with _MUTEX:
        _need(type(context) in (_PaperAccountContext,_PaperInputContext),'PAPER_PORTFOLIO_UNQUALIFIED')
        _need(not context._closed and context._owner is not None,'PAPER_PORTFOLIO_CONTEXT_UNAVAILABLE')
        owner=context._owner;db=owner.store.conn
        try:pending=db.in_transaction
        except sqlite3.Error:
            context.close();raise RuntimeRefused('PAPER_PORTFOLIO_DATABASE_CLOSED') from None
        _need(not pending,'PAPER_PORTFOLIO_TRANSACTION_OPEN')
        try:
            with _owner_scope(owner.lease),owner.store._live():
                journal=_journal_snapshot(owner)
                result=_PortfolioContext(_factory=_FACTORY,_context=context,_owner=owner,_db=db,_pin=journal['sha256'],_closed=False)
                result.diagnostic();return result
        except RuntimeRefused:context.close();raise
        except _INVALID:
            context.close();raise RuntimeRefused('PAPER_PORTFOLIO_INVALID') from None
