"""Private controlled-source economics. Actual financial and broker gates stay closed."""
import json
from compertum.data.encoding import canonical
from compertum.fixture_economics import FixtureEconomicCalculation,calculate_fixture_economics
from .errors import RuntimeRefused
from .owners import _owner_scope
from .paper_read_evidence import open_read_evidence
from .paper_input_context import _account_manifest
from .paper_read_packet import _nanoseconds
from .fixture_source_binding import native_source_peer,source_file,order_source_file
from .paper_reconciliation_context import _sha

def _need(value,code='PAPER_FIXTURE_ECONOMICS_UNVERIFIED'):
    if not value:raise RuntimeRefused(code)

def _account_original(owner,alias,packet):
    value=owner._read(packet);manifest=_account_manifest(owner,value)
    with open_read_evidence(owner.lease,alias,packet,manifest) as opened:
        rows=opened.snapshot()['records']
    rows=[r for r in rows if r['request']['operation']=='ACCOUNT'];_need(len(rows)==1)
    row=rows[0];request_sha=_sha(row['request']);raw=row['raw'];body=json.loads(raw)
    embedded=body['compertum_fixture_source']
    saved=owner.db.execute('SELECT body FROM fixture_source_witnesses WHERE request_sha256=?',(request_sha,)).fetchone()
    _need(saved is not None and len(saved[0].encode())<=8192)
    witness=json.loads(saved[0]);_need(canonical(witness).decode()==saved[0])
    _need(witness['version']==1 and witness['scope']=='CONTROLLED_NATIVE_SOURCE' and witness['project_id']==owner.lease.project_id)
    _need(witness['request_sha256']==request_sha and witness['raw_sha256']==row['parsed']['raw_sha256'])
    _need(witness['source_sha256']==_sha(embedded) and witness['peer']==embedded['served_by'])
    _need(witness['producer_id']==embedded['producer_id'] and witness['genesis_sha256']==embedded['genesis_sha256'])
    _need(_nanoseconds(row['request']['created_at'])<=_nanoseconds(row['parsed']['received_at'])<=_nanoseconds(witness['captured_at']))
    return row,embedded,witness,saved[0],manifest

def _source_snapshot(owner,context,base,originals):
    _need(not owner.db.in_transaction)
    alias=originals['account_alias'];first_packet=base['opening']['reference']['first_packet_id']
    first,first_source,first_witness,first_raw,first_manifest=_account_original(owner,alias,first_packet)
    current,source,witness,saved_raw,manifest=_account_original(owner,alias,context._packet)
    journal,identity=source_file(owner.lease)
    orders,order_identity=order_source_file(owner.lease)
    descriptor={k:orders[k] for k in ('producer_id','genesis_sha256','journal_sha256')}
    beginning=first_source['order_source']
    _need(set(beginning)==set(descriptor) and all(beginning[k]==descriptor[k] for k in ('producer_id','genesis_sha256')))
    _need(beginning['journal_sha256'] in orders['prefix_sha256'])
    _need(source['order_source']==witness['order_source']==descriptor and first_witness['order_source']==beginning)
    _need(first_witness['order_source_file_identity']==witness['order_source_file_identity']==order_identity)
    _need(all(attempt in originals['attempts'] for attempt in orders['attempts']))
    inventory=orders['inventory']
    same=lambda left,right:sorted(canonical(row) for row in left)==sorted(canonical(row) for row in right)
    _need(same(originals['orders'],inventory['orders']) and same(originals['positions'],inventory['positions']))
    _need(same([row for row in originals['activities'] if row['activity_type']=='FILL'],inventory['fills']))
    _need(orders['origin']['economic_producer_id']==journal['producer_id'] and orders['origin']['economic_genesis_sha256']==journal['genesis_sha256'])
    _need(_nanoseconds(orders['origin']['created_at'])<=_nanoseconds(first['request']['created_at']))
    _need(first_witness['source_file_identity']==witness['source_file_identity']==identity)
    _need(first_source['producer_id']==source['producer_id']==journal['producer_id'])
    _need(first_source['genesis_sha256']==source['genesis_sha256']==journal['genesis_sha256'])
    ledger=source['ledger'];live=journal['ledger'];old=first_source['ledger']
    _need(ledger['opening_sha256']==ledger['history_sha256']==old['opening_sha256']==old['history_sha256']=='0'*64)
    _need(set(ledger)==set(live) and all(ledger[k]==live[k] for k in ledger if k!='covered_until'))
    _need(old['events']==ledger['events'][:old['event_count']])
    header_keys=set(ledger)-{'events','event_count','ledger_head_sha256','covered_until','opening_sha256','history_sha256'}
    _need(all(old[k]==ledger[k] for k in header_keys))
    after=first['request']['created_at'];until=ledger['covered_until']
    _need(_nanoseconds(ledger['covered_after'])<=_nanoseconds(after)<_nanoseconds(until)<=_nanoseconds(current['parsed']['received_at']))
    _need(all(_nanoseconds(transaction['at'])<=_nanoseconds(until) for transaction in orders['transactions']))
    _need(_nanoseconds(until)<=_nanoseconds(live['covered_until']))
    _need(native_source_peer(owner.lease,witness['port'])==witness['peer'])
    bound=dict(ledger,opening_sha256=base['opening']['sha256'],history_sha256=base['journal'])
    values=dict(originals=originals,ledger=bound,opening_sha256=bound['opening_sha256'],history_sha256=bound['history_sha256'],
                asset_id=bound['asset_id'],symbol=bound['symbol'],required_after=after,required_until=until)
    binding=_sha(dict(journal=journal,orders=orders,witness=witness,first=first_witness,manifest=manifest,first_manifest=first_manifest))
    def check():
        actual,file_identity=source_file(owner.lease)
        _need(file_identity==identity and actual==journal)
        actual_orders,actual_order_identity=order_source_file(owner.lease)
        _need(actual_order_identity==order_identity and canonical(actual_orders)==canonical(orders))
        _need(native_source_peer(owner.lease,witness['port'])==witness['peer'])
        for request,raw in ((first_witness['request_sha256'],first_raw),(witness['request_sha256'],saved_raw)):
            _need(owner.db.execute('SELECT body FROM fixture_source_witnesses WHERE request_sha256=?',(request,)).fetchone()==(raw,))
    check();return values,binding,check

def _capture(owner,context,portfolio,activity_id):
    from .paper_reconciliation_context import _capture_originals
    from .paper_credentials import open_paper_credentials
    from .paper_read_secrecy import _reject_reflections
    proof,base,originals,metadata,original,protected,account_id=_capture_originals(owner,context,portfolio,activity_id,allow_unsupported=True)
    _need(metadata['provenance']=='LOOPBACK_FIXTURE')
    values,source_binding,source_check=_source_snapshot(owner,context,base,originals)
    expected_arguments=canonical(values)
    calculation=calculate_fixture_economics(**values);_need(type(calculation) is FixtureEconomicCalculation)
    calculation.__post_init__();private=calculation.content;value=calculation.to_payload()
    _need(calculation.arguments==expected_arguments and canonical(values)==expected_arguments
          and calculation.content==private and value['cash_matches'])
    pin=_sha(dict(base,source=source_binding,calculation_sha256=_sha(value)))
    result=dict(version=1,record_type='FixtureEconomicContextDiagnostic',scope='ENGINEERING_FIXTURE_ECONOMICS',
        status='BLOCKED',source_status='CONTROLLED_LOCAL_SOURCE_VERIFIED',source_qualified=True,
        fee_liability_status='ZERO_FROM_COMPLETE_CONTROLLED_LEDGER' if value['outstanding_fees']=='0' else 'OUTSTANDING_CONTROLLED_FEES',
        event_count=value['event_count'],action_status='COMPLETE_ACTION_FREE_CONTROLLED_INTERVAL',
        financial_accepted=False,transport_authorized=False,actual_flat=None,
        unverified_requirements=['ACTUAL_BILLING_UNVERIFIED','ACTUAL_ACTION_COVERAGE_UNVERIFIED','RISK_UNVERIFIED','DURABLE_DISPATCH_UNVERIFIED'])
    raw=canonical(result);_need(account_id.encode() not in raw)
    with open_paper_credentials(owner.lease,protected) as credentials:_reject_reflections(raw,tuple(credentials.headers().values()))
    def originals_checked():original();source_check()
    proof._check();originals_checked();proof._finish()
    return proof,pin,private,result,originals_checked

from dataclasses import dataclass
import sqlite3
from compertum.paper_contracts import identifier
from .owners import _MUTEX
from .paper_account_context import _PaperAccountContext
from .paper_portfolio_context import _portfolio_context
from .paper_reconciliation_context import _INVALID
_FACTORY=object()

@dataclass(frozen=True,slots=True,repr=False,init=False)
class _FixtureEconomicContext:
    _owner:object
    _db:object
    _context:object
    _portfolio:object
    _activity_id:str
    _binding:str
    _calculation:bytes
    _closed:bool

    def __init__(self,*,_factory=None,**fields):
        _need(_factory is _FACTORY,'PAPER_FIXTURE_ECONOMICS_CONTEXT_UNQUALIFIED')
        for key,value in fields.items():object.__setattr__(self,key,value)

    def __repr__(self):return '<PrivateFixtureEconomicContext redacted>'
    def __reduce_ex__(self,protocol):raise RuntimeRefused('PAPER_FIXTURE_ECONOMICS_SERIALIZATION_FORBIDDEN')
    def close(self):
        with _MUTEX:
            object.__setattr__(self,'_closed',True);self._portfolio.close()

    def _prepare_proof(self):
        with _MUTEX:
            _need(not self._closed,'PAPER_FIXTURE_ECONOMICS_CONTEXT_UNAVAILABLE')
            try:pending=self._db.in_transaction
            except sqlite3.Error:
                self.close();raise RuntimeRefused('PAPER_FIXTURE_ECONOMICS_DATABASE_CLOSED') from None
            _need(not pending,'PAPER_FIXTURE_ECONOMICS_TRANSACTION_OPEN')
            try:
                owner=self._owner;context=self._context;portfolio=self._portfolio;activity_id=self._activity_id
                with _owner_scope(owner.lease),owner.store._live():
                    _need(owner.db is self._db and not owner._closed)
                    proof,pin,calculation,result,original=_capture(owner,context,portfolio,activity_id)
                    _need(pin==self._binding and calculation==self._calculation)
                    check,finish,invalidate=proof._check,proof._finish,proof._invalidate
                    def identity():
                        _need(not self._closed and owner.db is self._db and not context._closed)
                        _need(self._owner is owner and self._context is context and self._portfolio is portfolio)
                        _need(owner._account_context is context and self._binding==pin and self._calculation==calculation)
                        _need(self._activity_id==activity_id)
                    def checked():
                        identity()
                        try:check()
                        except RuntimeRefused as error:
                            invalidate(error.code);raise
                        original();identity()
                    def finished():
                        identity()
                        try:finish()
                        except RuntimeRefused as error:
                            invalidate(error.code);raise
                        identity()
                    def invalidated(reason):self.close()
                    identity()
                    proof._check=checked;proof._finish=finished;proof._invalidate=invalidated
                    proof._final_identity=identity;proof._content=canonical(result)
                    return proof
            except RuntimeRefused:
                self.close();raise
            except _INVALID:
                self.close();raise RuntimeRefused('PAPER_FIXTURE_ECONOMICS_CONTEXT_INVALID') from None

    def diagnostic(self):return self._prepare_proof()._verify()


def fixture_economic_context(owner,*,subject,packet_id,activity_id):
    with _MUTEX:
        db=owner.db
        try:pending=db.in_transaction
        except sqlite3.Error:raise RuntimeRefused('PAPER_FIXTURE_ECONOMICS_DATABASE_CLOSED') from None
        _need(not pending,'PAPER_FIXTURE_ECONOMICS_TRANSACTION_OPEN')
        try:
            identifier(packet_id);identifier(activity_id)
            context=owner._account_context
            _need(type(context) is _PaperAccountContext and context._owner is owner and not context._closed)
            _need(type(subject) is str and context._subject==subject and context._packet==packet_id)
            portfolio=_portfolio_context(context)
        except _INVALID:raise RuntimeRefused('PAPER_FIXTURE_ECONOMICS_CONTEXT_INVALID') from None
        try:
            with _owner_scope(owner.lease),owner.store._live():
                _,pin,calculation,_,_=_capture(owner,context,portfolio,activity_id)
                _need(owner.db is db and owner._account_context is context and not context._closed)
                return _FixtureEconomicContext(_factory=_FACTORY,_owner=owner,_db=db,_context=context,
                    _portfolio=portfolio,_activity_id=activity_id,_binding=pin,_calculation=calculation,_closed=False)
        except (RuntimeRefused,*_INVALID):
            portfolio.close();raise RuntimeRefused('PAPER_FIXTURE_ECONOMICS_CONTEXT_INVALID') from None
