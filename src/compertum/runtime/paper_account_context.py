"""Private account observations without market prerequisites or broker authority."""
from dataclasses import dataclass
import hashlib,re,sqlite3
from compertum.data.encoding import canonical
from compertum.domain import ContractError
from compertum.events import uuid
from .errors import RuntimeRefused
from .paper_final_proof import _final_proof
from .owners import _MUTEX,_owner_scope
from .paper_preflight import _live as live_owner,_MISSING as _PREFLIGHT_MISSING
from .paper_input_context import _account_manifest,_account,_final_account
from . import paper_account_binding as binding
from .paper_credential_slot import load_paper_slot,_slot,_payload as slot_payload
from .paper_credentials import open_paper_credentials
from .paper_read_evidence import open_read_evidence
from .paper_market_lineage_evidence import _published as published_original
from .paper_opening import _original as original_opening
from .paper_read_secrecy import _reject_reflections

_FACTORY=object()
_REQUIRED={'ACCOUNT_CONFIRMATION_UNVERIFIED','OWNERSHIP_UNVERIFIED','ECONOMIC_RECONCILIATION_UNVERIFIED',
           'SUPERVISION_UNVERIFIED','EXACT_PLAN_GRANT_REQUIRED','TARGET_RECONCILIATION_UNVERIFIED'}
_INVALID=(ContractError,ValueError,TypeError,KeyError,AttributeError,OverflowError,RecursionError,UnicodeError,sqlite3.Error)


def _need(value,code='PAPER_ACCOUNT_CONTEXT_CHANGED'):
    if not value:raise RuntimeRefused(code)


def _sha(value):return hashlib.sha256(canonical(value)).hexdigest()


def _resources(owner):return owner.store,owner.reserve,owner.health,owner.lease,owner.db


def _preflight_state(p):
    return (p.content,p._account_id,p._credential_sha,p._generation,p._instance,p._content_sha,
            p._private_sha,p._records,p._captured_utc,p._captured_mono)


def _opening_sources(owner,opening):
    if opening is None:return None
    reference=opening['reference'];packet=reference['first_packet_id'];value=owner._read(packet)
    manifest=_account_manifest(owner,value)
    _need(manifest==reference['manifest'])
    return value,binding._stored(owner,packet),manifest


def _originals(owner,value,manifest,facts,record,alias,opening,opening_sources):
    # History verification may perform guarded reads; finish with original rows.
    history=binding._history(owner)
    _need(history['status'] in {'VERIFIED_ZERO_PRE_SCHEMA','VERIFIED_HISTORY'},'PAPER_ACCOUNT_HISTORY_UNVERIFIED')
    _need(_sha(history)==facts['history_sha256'])
    _need(owner._read(value['packet_id'])==value and _account_manifest(owner,value)==manifest)
    _need(binding._stored(owner,value['packet_id'])==record)
    _need(binding._alias(owner,value['account_alias'],facts['identity_sha256'])==alias)
    _need(binding._state(owner,'paper_opening:'+value['account_alias'])==opening)
    _need(_opening_sources(owner,opening)==opening_sources)


def _snapshot(owner,subject,packet_id):
    resources=_resources(owner);live_owner(owner)
    _need(not owner.db.in_transaction,'PAPER_ACCOUNT_CONTEXT_TRANSACTION_OPEN')
    value=owner._read(packet_id);preflight=owner.preflight(packet_id)
    _need(value['subject_key']==subject and value['state']=='PUBLISHED' and value['consumed'])
    _need(value['owner_generation']==owner.lease.generation and value['owner_instance']==owner.lease.identity.process_instance_id)
    manifest=_account_manifest(owner,value)
    facts,p,record,proposal,opening_record,confirmation,opening,reference,reasons=_account(owner,preflight,value,manifest)
    alias=binding._alias(owner,value['account_alias'],facts['identity_sha256'])
    _need(confirmation!='CONFIRMED_CURRENT_CONTEXT' or alias is not None)
    opening_sources=_opening_sources(owner,opening_record)
    private_state=_preflight_state(preflight)
    required=set(_REQUIRED)
    if confirmation=='CONFIRMED_CURRENT_CONTEXT':required.discard('ACCOUNT_CONFIRMATION_UNVERIFIED')
    if p['transport_provenance']!='PAPER_TLS':required.add('NATIVE_PAPER_TRANSPORT_UNVERIFIED')
    observations=(set(p['deficiencies'])|set(reasons))-set(_PREFLIGHT_MISSING)
    result=dict(version=1,record_type='PaperAccountInputDiagnostic',scope='CURRENT_ACCOUNT_OBSERVATIONS_ONLY',status='BLOCKED',
        project_id=owner.lease.project_id,account_alias=value['account_alias'],packet_id=packet_id,
        account_manifest_sha256=_sha(manifest),confirmation_status=confirmation,opening_status=opening,
        opening_reference_sha256=reference,checked_at=p['checked_at'],account_transport_provenance=p['transport_provenance'],
        calendar_agreement=p['calendar_agreement'],positions=p['positions'],orders=p['orders'],order_coverage=p['order_coverage'],
        observed_deficiencies=sorted(observations),unverified_requirements=sorted(required),
        financial_accepted=False,transport_authorized=False,research_eligible=False,actual_flat=None)
    raw=canonical(result);_need(len(raw)<=16384)
    protected=load_paper_slot(owner.lease,value['account_alias'])
    _need(hashlib.sha256(protected.ciphertext).hexdigest()==preflight._credential_sha==value['credential_sha256'])
    with open_paper_credentials(owner.lease,protected) as credentials:_reject_reflections(raw,tuple(credentials.headers().values()))
    _need(preflight._account_id.encode() not in raw,'PAPER_READ_PRIVATE_ID_REFLECTION')

    # Diagnostic/decryption callbacks finish before the final durable and pure checks.
    preflight.diagnostic()
    if opening_record is not None:_need(original_opening(owner,value['account_alias'])[0]==opening_record)
    with open_read_evidence(owner.lease,value['account_alias'],packet_id,manifest):pass
    live_owner(owner)
    protected=load_paper_slot(owner.lease,value['account_alias'])
    _need(hashlib.sha256(protected.ciphertext).hexdigest()==value['credential_sha256'])
    # Slot validation decrypts and scans. Finish it before proving original bytes
    # and rows; the last slot comparison must not invoke those callbacks again.
    def final():
        with _owner_scope(owner.lease) as guard:
            published_original(guard,manifest)
            if opening_record is not None:published_original(guard,opening_sources[2])
        _originals(owner,value,manifest,facts,record,alias,opening_record,opening_sources)
        with _slot(owner.lease) as (guard,path):
            _need(guard.api.read_regular(path,maximum=16384)==slot_payload(protected),'PAPER_ACCOUNT_CREDENTIAL_CHANGED')
    def finish():
        _need(all(a is b for a,b in zip(_resources(owner),resources)))
        _need(not owner._closed and owner.health.reason is None,'EXECUTION_HEALTH_UNVERIFIED')
        _need(owner._preflight is preflight and not preflight._closed and preflight._owner is owner)
        _need(_preflight_state(preflight)==private_state and owner._account_proposal is proposal)
        if proposal is not None:
            _need(not proposal._closed and proposal._context is preflight and proposal.content==canonical(facts)
                  and proposal._confirmed_at==record['confirmed_at'])
        _final_account(preflight)
    final();finish()
    stable=dict(account=value,manifest=manifest,facts=facts,confirmation=record,alias=alias,opening=opening_record,opening_sources=opening_sources)
    return result,_sha(stable),(*resources,preflight,proposal),final,finish


@dataclass(frozen=True,slots=True,repr=False,init=False)
class _PaperAccountContext:
    _owner:object
    _subject:str
    _packet:str
    _generation:int
    _instance:str
    _binding:str
    _identities:tuple
    _closed:bool
    def __init__(self,*,_factory=None,**fields):
        _need(_factory is _FACTORY,'PAPER_ACCOUNT_CONTEXT_UNQUALIFIED')
        for key,value in fields.items():object.__setattr__(self,key,value)
    def __repr__(self):return '<PrivatePaperAccountContext redacted>'
    def __reduce_ex__(self,protocol):raise RuntimeRefused('PAPER_ACCOUNT_CONTEXT_SERIALIZATION_FORBIDDEN')
    def close(self):
        with _MUTEX:
            object.__setattr__(self,'_closed',True);object.__setattr__(self,'_owner',None);object.__setattr__(self,'_identities',())
    def _prepare_proof(self):
        owner=self._owner;_need(not self._closed and owner is not None,'PAPER_FINAL_PROOF_CONTEXT_UNAVAILABLE')
        try:
            with _owner_scope(owner.lease),owner.store._live():
                _need(owner._account_context is self)
                resources=(owner.store,owner.reserve,owner.health,owner.lease,owner.db)
                result,pin,identities,final,finish=_snapshot(owner,self._subject,self._packet)
                def identity():
                    _need(not self._closed and self._owner is owner and owner._account_context is self)
                    _need(all(a is b for a,b in zip(resources,(owner.store,owner.reserve,owner.health,owner.lease,owner.db))))
                    _need(self._generation==owner.lease.generation and self._instance==owner.lease.identity.process_instance_id)
                    _need(pin==self._binding and len(identities)==len(self._identities)
                          and all(a is b for a,b in zip(identities,self._identities)))
                def check():
                    identity();final()
                def last():
                    identity();finish()
                    _need(not self._closed and self._owner is owner and owner._account_context is self)
                check();last()
                return _final_proof(owner,check,last,lambda reason:self.close(),result)
        except RuntimeRefused:
            self.close();raise
        except _INVALID:
            self.close();raise RuntimeRefused('PAPER_FINAL_PROOF_CONTEXT_INVALID') from None

    def diagnostic(self):
        owner=self._owner;_need(not self._closed and owner is not None,'PAPER_ACCOUNT_CONTEXT_UNAVAILABLE')
        try:
            with _owner_scope(owner.lease),owner.store._live():
                _need(not self._closed and self._owner is owner and owner._account_context is self)
                _need(self._generation==owner.lease.generation and self._instance==owner.lease.identity.process_instance_id)
                result,pin,identities,_,_=_snapshot(owner,self._subject,self._packet)
                _need(not self._closed and self._owner is owner and owner._account_context is self)
                _need(pin==self._binding and len(identities)==len(self._identities)
                      and all(a is b for a,b in zip(identities,self._identities)))
                return result
        except RuntimeRefused:
            self.close();raise
        except _INVALID:
            self.close();raise RuntimeRefused('PAPER_ACCOUNT_CONTEXT_INVALID') from None


def account_context(owner,*,subject,packet_id):
    try:
        with _owner_scope(owner.lease),owner.store._live():
            _need(type(subject) is str and re.fullmatch('[0-9a-f]{64}',subject) is not None);uuid(packet_id)
            _,pin,identities,_,_=_snapshot(owner,subject,packet_id)
            result=_PaperAccountContext(_factory=_FACTORY,_owner=owner,_subject=subject,_packet=packet_id,
                _generation=owner.lease.generation,_instance=owner.lease.identity.process_instance_id,
                _binding=pin,_identities=identities,_closed=False)
            if owner._account_context is not None:owner._account_context.close()
            owner._account_context=result;return result
    except _INVALID:raise RuntimeRefused('PAPER_ACCOUNT_CONTEXT_INVALID') from None
