"""Private original posted-fee observations. Posting times and liabilities stay unknown."""
from dataclasses import dataclass
import json,sqlite3

from compertum.data.encoding import canonical
from compertum.paper_contracts import identifier
from compertum.paper_posted_fees import PostedFeeCalculation,calculate_posted_fees
from .errors import RuntimeRefused
from .owners import _MUTEX,_owner_scope
from .paper_account_context import _PaperAccountContext
from .paper_credentials import open_paper_credentials
from .paper_portfolio_context import _portfolio_context
from .paper_read_secrecy import _reject_reflections
from .paper_reconciliation_context import _capture_originals,_sha,_INVALID

_FACTORY=object()


def _need(value,code='PAPER_POSTED_FEE_CONTEXT_CHANGED'):
    if not value:raise RuntimeRefused(code)


def _capture(owner,context,portfolio,activity_id):
    proof,base,arguments,metadata,original,protected,account_id=_capture_originals(
        owner,context,portfolio,activity_id,allow_unsupported=True)
    input_bytes=canonical(arguments);_need(len(input_bytes)<=1024**2)
    calculation=calculate_posted_fees(**arguments)
    _need(type(calculation) is PostedFeeCalculation)
    calculation.__post_init__()
    _need(calculation.arguments==input_bytes and canonical(arguments)==input_bytes)
    private=calculation.content;value=calculation.to_payload()
    _need(calculation.content==private and calculation.arguments==input_bytes)
    stable=dict(base,calculation_sha256=_sha(value),account_identity_sha256=metadata['account_identity_sha256'],
        mode='POSTED_USD_FEE_OBSERVATION')
    pin=_sha(stable)
    result=dict(version=1,record_type='PaperPostedFeeContextDiagnostic',status='BLOCKED',
        observation_status='MATCHING_LOOPBACK_OBSERVATIONS' if metadata['provenance']=='LOOPBACK_FIXTURE'
            else 'MATCHING_ORIGINAL_OBSERVATIONS',
        cash_comparison='MATCHING_OBSERVED_CASH' if value['calculation_matches'] else 'CASH_DIFFERENCE_UNEXPLAINED',
        posted_fee_count=value['posted_fee_count'],posted_debit_count=value['posted_debit_count'],
        posted_credit_count=value['posted_credit_count'],posted_zero_count=value['posted_zero_count'],
        order_count=value['order_count'],fill_count=value['fill_count'],position_count=len(value['owned_positions']),
        actual_billed_fee=None,actual_flat=None,financial_accepted=False,transport_authorized=False,
        unverified_requirements=['FEE_POSTING_INTERVAL_UNVERIFIED','FEE_LIABILITIES_UNVERIFIED',
            'FEE_REVERSALS_UNVERIFIED','FEE_BILLING_COVERAGE_UNVERIFIED','FEE_ACCOUNT_APPLICABILITY_UNVERIFIED',
            'FEE_ACCOUNT_DAY_COVERAGE_UNVERIFIED','FEE_ORDER_LIFETIME_COVERAGE_UNVERIFIED',
            'ACTION_EVIDENCE_UNVERIFIED','RISK_UNVERIFIED','DURABLE_CONSUMPTION_UNVERIFIED'])
    raw=canonical(result);_need(account_id.encode() not in raw)
    with open_paper_credentials(owner.lease,protected) as credentials:
        _reject_reflections(raw,tuple(credentials.headers().values()))
    proof._check();original();proof._finish()
    return proof,pin,private,result,original


@dataclass(frozen=True,slots=True,repr=False,init=False)
class _PostedFeeContext:
    _owner:object
    _db:object
    _context:object
    _portfolio:object
    _activity_id:str
    _binding:str
    _calculation:bytes
    _closed:bool

    def __init__(self,*,_factory=None,**fields):
        _need(_factory is _FACTORY,'PAPER_POSTED_FEE_CONTEXT_UNQUALIFIED')
        for key,value in fields.items():object.__setattr__(self,key,value)

    def __repr__(self):return '<PrivatePostedFeeContext redacted>'
    def __reduce_ex__(self,protocol):raise RuntimeRefused('PAPER_POSTED_FEE_SERIALIZATION_FORBIDDEN')
    def close(self):
        with _MUTEX:
            object.__setattr__(self,'_closed',True);self._portfolio.close()

    def _prepare_proof(self):
        with _MUTEX:
            _need(not self._closed,'PAPER_POSTED_FEE_CONTEXT_UNAVAILABLE')
            try:pending=self._db.in_transaction
            except sqlite3.Error:
                self.close();raise RuntimeRefused('PAPER_POSTED_FEE_DATABASE_CLOSED') from None
            _need(not pending,'PAPER_POSTED_FEE_TRANSACTION_OPEN')
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
                self.close();raise RuntimeRefused('PAPER_POSTED_FEE_CONTEXT_INVALID') from None

    def diagnostic(self):return self._prepare_proof()._verify()


def posted_fee_context(owner,*,subject,packet_id,activity_id):
    with _MUTEX:
        db=owner.db
        try:pending=db.in_transaction
        except sqlite3.Error:raise RuntimeRefused('PAPER_POSTED_FEE_DATABASE_CLOSED') from None
        _need(not pending,'PAPER_POSTED_FEE_TRANSACTION_OPEN')
        try:
            identifier(packet_id);identifier(activity_id)
            context=owner._account_context
            _need(type(context) is _PaperAccountContext and context._owner is owner and not context._closed)
            _need(type(subject) is str and context._subject==subject and context._packet==packet_id)
            portfolio=_portfolio_context(context)
        except _INVALID:raise RuntimeRefused('PAPER_POSTED_FEE_CONTEXT_INVALID') from None
        try:
            with _owner_scope(owner.lease),owner.store._live():
                _,pin,calculation,_,_=_capture(owner,context,portfolio,activity_id)
                _need(owner.db is db and owner._account_context is context and not context._closed)
                return _PostedFeeContext(_factory=_FACTORY,_owner=owner,_db=db,_context=context,
                    _portfolio=portfolio,_activity_id=activity_id,_binding=pin,_calculation=calculation,_closed=False)
        except (RuntimeRefused,*_INVALID):
            portfolio.close();raise RuntimeRefused('PAPER_POSTED_FEE_CONTEXT_INVALID') from None
