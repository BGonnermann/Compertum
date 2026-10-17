"""Private original-fill fee observations. Declared fees never prove actual billing."""
from dataclasses import dataclass
import json,sqlite3

from compertum.data.encoding import canonical
from compertum.paper_contracts import identifier,strict_json
from compertum.paper_fee_adapter import build_fee_batches
from compertum.paper_fees import FeeCalculation,calculate_fees
from compertum.paper_reconciliation import validate_fill_history
from .errors import RuntimeRefused
from .owners import _MUTEX,_owner_scope
from .paper_account_context import _PaperAccountContext
from .paper_credentials import open_paper_credentials
from .paper_fee_declarations import _capture_fee_declaration,_manifest
from .paper_portfolio_context import _portfolio_context
from .paper_read_secrecy import _reject_reflections
from .paper_reconciliation_context import _capture_originals,_sha,_INVALID

_FACTORY=object()


def _need(value,code='PAPER_FEE_CONTEXT_CHANGED'):
    if not value:raise RuntimeRefused(code)


def _schedule_signature(schedules):
    return canonical([dict(schedule=s.sha256,sources=sorted(
        (source.sha256,source.body_sha256) for source in s.sources)) for s in schedules])


def _capture(owner,context,portfolio,activity_id,declaration_id,manifest):
    proof,base,arguments,metadata,original,protected,account_id=_capture_originals(
        owner,context,portfolio,activity_id,allow_unsupported=True)
    _need(len(canonical(arguments))<=1024**2)
    input_bytes=canonical(arguments)
    fills=tuple(row for row in arguments['activities'] if row['activity_type']=='FILL')
    unsupported=len(arguments['activities'])-len(fills)
    comparison=validate_fill_history(**dict(arguments,activities=fills))
    declaration,schedules,declared_original,declared_final=_capture_fee_declaration(owner.lease,declaration_id,manifest)
    schedule_signature=_schedule_signature(schedules)
    schedule_hashes=tuple(sorted(s.sha256 for s in schedules))
    batches,mapping=build_fee_batches(project_id=owner.lease.project_id,
        account_identity_sha256=metadata['account_identity_sha256'],account_alias=arguments['account_alias'],
        activities=fills,empty_at=metadata['empty_at'])
    calculations=[]
    for batch in batches:
        batch_bytes=batch.content
        calculation=calculate_fees(batch,schedules)
        _need(type(calculation) is FeeCalculation)
        calculation.__post_init__()
        _need(calculation.batch is batch and batch.content==batch_bytes)
        _need(_schedule_signature(schedules)==schedule_signature)
        _need(tuple(s.sha256 for s in calculation.schedules)==schedule_hashes)
        _need(_schedule_signature(tuple(sorted(schedules,key=lambda s:s.sha256)))==_schedule_signature(calculation.schedules))
        calculations.append(json.loads(calculation.content))
    private=canonical(dict(calculations=calculations,mapping=mapping,fill_history=comparison))
    _need(len(private)<=1024**2 and canonical(arguments)==input_bytes)
    stable=dict(base,declaration=declaration,manifest=manifest,calculation_sha256=_sha(json.loads(private)),
                account_identity_sha256=metadata['account_identity_sha256'],mode='DECLARED_FEE_OBSERVATION')
    pin=_sha(stable)
    complete=all(c['calculation_status']=='DECLARED_BATCH_CALCULATED' for c in calculations)
    missing=['FEE_LIABILITIES_UNVERIFIED','FEE_SOURCE_INTERPRETATION_UNVERIFIED',
        'FEE_EFFECTIVE_INTERVAL_UNVERIFIED','FEE_ACCOUNT_APPLICABILITY_UNVERIFIED',
        'FEE_ACCOUNT_DAY_COVERAGE_UNVERIFIED','FEE_ORDER_LIFETIME_COVERAGE_UNVERIFIED',
        'FEE_CURRENCY_PRODUCT_UNVERIFIED','FEE_BILLING_UNVERIFIED','FEE_REVERSALS_UNVERIFIED',
        'ACTION_EVIDENCE_UNVERIFIED','RISK_UNVERIFIED','DURABLE_CONSUMPTION_UNVERIFIED']
    if unsupported:missing.append('UNSUPPORTED_ACTIVITY')
    result=dict(version=1,record_type='PaperFeeContextDiagnostic',status='BLOCKED',
        declaration_status='DECLARED_BATCH_CALCULATED' if complete else 'INCOMPLETE_DECLARATIONS',
        declared_execution_count=len(fills),declared_day_count=len(batches) if fills else 0,
        calculation_batch_count=len(batches),unsupported_activity_count=unsupported,
        actual_billed_fee=None,actual_flat=None,financial_accepted=False,transport_authorized=False,
        unverified_requirements=missing)
    raw=canonical(result);_need(account_id.encode() not in raw)
    with open_paper_credentials(owner.lease,protected) as credentials:
        _reject_reflections(raw,tuple(credentials.headers().values()))
    def originals():
        declared_original();original();declared_final()
    proof._check();originals();proof._finish()
    return proof,pin,private,result,originals


@dataclass(frozen=True,slots=True,repr=False,init=False)
class _FeeContext:
    _owner:object
    _db:object
    _context:object
    _portfolio:object
    _activity_id:str
    _declaration_id:str
    _manifest:bytes
    _binding:str
    _calculation:bytes
    _closed:bool

    def __init__(self,*,_factory=None,**fields):
        _need(_factory is _FACTORY,'PAPER_FEE_CONTEXT_UNQUALIFIED')
        for key,value in fields.items():object.__setattr__(self,key,value)

    def __repr__(self):return '<PrivatePaperFeeContext redacted>'
    def __reduce_ex__(self,protocol):raise RuntimeRefused('PAPER_FEE_CONTEXT_SERIALIZATION_FORBIDDEN')
    def close(self):
        with _MUTEX:
            object.__setattr__(self,'_closed',True);self._portfolio.close()

    def _prepare_proof(self):
        with _MUTEX:
            _need(not self._closed,'PAPER_FEE_CONTEXT_UNAVAILABLE')
            try:pending=self._db.in_transaction
            except sqlite3.Error:
                self.close();raise RuntimeRefused('PAPER_FEE_DATABASE_CLOSED') from None
            _need(not pending,'PAPER_FEE_TRANSACTION_OPEN')
            try:
                owner=self._owner;declaration_id=self._declaration_id;manifest=self._manifest
                activity_id=self._activity_id;context=self._context;portfolio=self._portfolio
                with _owner_scope(owner.lease),owner.store._live():
                    _need(owner.db is self._db and not owner._closed)
                    proof,pin,calculation,result,original=_capture(owner,context,portfolio,
                        activity_id,declaration_id,json.loads(manifest))
                    _need(pin==self._binding and calculation==self._calculation)
                    check,finish,invalidate=proof._check,proof._finish,proof._invalidate
                    def identity():
                        _need(not self._closed and owner.db is self._db and not context._closed)
                        _need(self._owner is owner and self._context is context and self._portfolio is portfolio)
                        _need(owner._account_context is context and self._binding==pin and self._calculation==calculation)
                        _need(self._declaration_id==declaration_id and self._manifest==manifest and self._activity_id==activity_id)
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
                self.close();raise RuntimeRefused('PAPER_FEE_CONTEXT_INVALID') from None

    def diagnostic(self):return self._prepare_proof()._verify()


def fee_context(owner,*,subject,packet_id,activity_id,declaration_id,manifest):
    with _MUTEX:
        db=owner.db
        try:pending=db.in_transaction
        except sqlite3.Error:raise RuntimeRefused('PAPER_FEE_DATABASE_CLOSED') from None
        _need(not pending,'PAPER_FEE_TRANSACTION_OPEN')
        try:
            identifier(declaration_id);identifier(activity_id)
            m=strict_json(canonical(manifest));_manifest(m,m.get('task_id'),declaration_id)
            context=owner._account_context
            _need(type(context) is _PaperAccountContext and context._owner is owner and not context._closed)
            _need(context._subject==subject and context._packet==packet_id)
            portfolio=_portfolio_context(context)
        except _INVALID:raise RuntimeRefused('PAPER_FEE_CONTEXT_INVALID') from None
        try:
            with _owner_scope(owner.lease),owner.store._live():
                _,pin,calculation,_,_=_capture(owner,context,portfolio,activity_id,declaration_id,m)
                _need(owner.db is db and owner._account_context is context and not context._closed)
                return _FeeContext(_factory=_FACTORY,_owner=owner,_db=db,_context=context,
                    _portfolio=portfolio,_activity_id=activity_id,_declaration_id=declaration_id,
                    _manifest=canonical(m),_binding=pin,_calculation=calculation,_closed=False)
        except (RuntimeRefused,*_INVALID):
            portfolio.close();raise RuntimeRefused('PAPER_FEE_CONTEXT_INVALID') from None
