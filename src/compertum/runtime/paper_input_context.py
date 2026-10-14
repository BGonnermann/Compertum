"""Private current account/market observations. No plan, grant or dispatch authority."""
from dataclasses import dataclass
from datetime import datetime,timezone
import hashlib,json,math,re
from compertum.data.encoding import canonical
from compertum.domain import ContractError
from compertum.events import uuid
from compertum.paper_contracts import strict_json,timestamp
from compertum.paper_market_inputs import qualify_market_inputs,_ns,_day
from .errors import RuntimeRefused
from .owners import _MUTEX,_owner_scope
from .paper_preflight import _live as live_owner,_measure
from . import paper_account_binding as binding
from .paper_credential_slot import _coordinator_records,load_paper_slot,_slot,_payload as slot_payload
from .paper_credentials import open_paper_credentials
from .paper_read_secrecy import _reject_reflections
from .paper_read_evidence import _path as read_path,open_read_evidence
from .paper_opening import _original as original_opening
from .paper_market_lineage_evidence import open_market_lineage,_published as published_original
from .paper_market_compose import _observations,_history_records

_FACTORY=object()
_MISSING={'SUPERVISION_UNVERIFIED','EXACT_PLAN_GRANT_REQUIRED','OWNERSHIP_UNVERIFIED',
          'ECONOMIC_RECONCILIATION_UNVERIFIED','FEED_ENTITLEMENT_UNVERIFIED','ELIGIBILITY_UNVERIFIED',
          'ACTION_EVIDENCE_UNVERIFIED','HALT_EVIDENCE_UNVERIFIED','FEE_EVIDENCE_UNVERIFIED'}
_INVALID=(ContractError,ValueError,TypeError,KeyError,AttributeError,OverflowError,RecursionError,UnicodeError)


def _need(value,code='PAPER_INPUT_CONTEXT_CHANGED'):
    if not value:raise RuntimeRefused(code)


def _sha(value):return hashlib.sha256(canonical(value)).hexdigest()


def _account_manifest(owner,value):
    path=read_path(value['task_id'],value['packet_id'])
    with _owner_scope(owner.lease) as guard,_coordinator_records(guard) as db:
        rows=db.execute('SELECT task,category,status,written,CASE WHEN length(CAST(manifest AS BLOB))<=8192 THEN manifest END FROM reservations WHERE path=? LIMIT 2',(path,)).fetchall()
        _need(len(rows)==1,'PAPER_INPUT_PUBLICATION_UNVERIFIED')
        task,category,status,written,raw=rows[0]
        _need(task==value['task_id'] and category=='records' and status=='PUBLISHED' and type(raw) is str)
        manifest=strict_json(raw.encode());_need(canonical(manifest).decode()==raw)
        _need(manifest['path']==path and manifest['task_id']==task and manifest['size_bytes']==written)
        _need(all(manifest[k]==value['evidence'][k] for k in ('size_bytes','sha256')))
        return manifest


def _account(owner,preflight,value,manifest):
    facts,p,history,reasons=binding._facts(owner,preflight,value,manifest)
    record=binding._stored(owner,value['packet_id']);proposal=owner._account_proposal
    confirmation='UNCONFIRMED';opening='UNVERIFIED';reference=None
    opening_record=binding._state(owner,'paper_opening:'+value['account_alias'])
    if opening_record is not None:owner.opening_history(value['account_alias'])
    if record is None:
        _need(proposal is None)
    else:
        actual,again,p,history,reasons=binding._live(owner,value,manifest)
        _need(actual is proposal and again==record and record['proposal']==facts)
        if record['confirmed_at'] is not None:
            _need(p['transport_provenance']=='PAPER_TLS','PAPER_INPUT_NATIVE_ORIGIN_REQUIRED')
            confirmation='CONFIRMED_CURRENT_CONTEXT'
            try:
                current=owner.opening(value['packet_id'],manifest)
                opening=current['opening_status'];reference=current['opening_reference_sha256']
                reasons=list(reasons)+current['deficiencies']
            except RuntimeRefused as error:
                if error.code!='PAPER_OPENING_UNRECORDED':raise
                opening='UNRECORDED';reasons=list(reasons)+[error.code]
    return facts,p,record,proposal,opening_record,confirmation,opening,reference,reasons


def _current_market(market,fresh):
    # Account health/credentials can refuse observation without disposing the
    # borrowed historical market resources. Only market evidence faults own that
    # invalidation below.
    market._fresh_current(fresh)
    try:
        _need(market._producer is market._fresh_view._pair and market._combined._fresh is market._fresh_view)
        _need(market._combined._history is market._opened)
        return market._combined.to_payload()
    except RuntimeRefused as error:
        market._invalidate_fresh(fresh['grant']['job_id'],error.code);raise


def _opening_sources(owner,opening):
    if opening is None:return None
    reference=opening['reference'];packet=reference['first_packet_id'];value=owner._read(packet)
    manifest=_account_manifest(owner,value);_need(manifest==reference['manifest'])
    return value,binding._stored(owner,packet),manifest


def _final_live(owner,preflight,market):
    """Live callbacks precede final original records and pure clocks."""
    live_owner(owner);producer=market._producer;producer._context()
    protected=load_paper_slot(owner.lease,producer._plan.to_payload()['account_alias'])
    _need(hashlib.sha256(protected.ciphertext).hexdigest()==preflight._credential_sha==producer._credential_sha)
    _need(owner.health.status()['verified'] is True,'EXECUTION_HEALTH_UNVERIFIED')


def _final_clocks(preflight,market,producer,observations,diagnostic):
    _final_account(preflight)
    try:_final_market(producer,observations,diagnostic)
    except RuntimeRefused as error:
        market._invalidate_fresh(producer._pair_id,error.code);raise
    _final_account(preflight)


def _final_account(preflight):
    now,mono=_measure();du=(now-preflight._captured_utc).total_seconds();dm=mono-preflight._captured_mono
    _need(0<=du<=30 and 0<=dm<=30,'PAPER_PREFLIGHT_STALE');_need(abs(du-dm)<=5,'PAPER_PREFLIGHT_CLOCK_CHANGED')
    _need(all(0<=(now-timestamp(json.loads(raw)['created_at'])).total_seconds()<=30 for raw,_ in preflight._records),'PAPER_PREFLIGHT_STALE')


def _final_market(producer,observations,diagnostic):
    # Recompute only from already verified originals: no decryption, scan, I/O or
    # lifetime renewal after measuring the final owner clocks.
    at=producer._clock();monotonic=producer._monotonic()
    _need(type(monotonic) in (int,float) and math.isfinite(monotonic) and monotonic>=producer._last_mono,'PAPER_FRESH_CLOCK_INVALID')
    elapsed=monotonic-producer._start_mono;wall=(_ns(at)-_ns(producer._started_at))/10**9
    _need(_ns(at)>=_ns(producer._last_clock) and abs(wall-elapsed)<=5,'PAPER_FRESH_CLOCK_INVALID')
    age=max(_ns(at),_ns(producer._started_at)+math.ceil(elapsed*10**9));seconds,nanos=divmod(age,10**9)
    stamp=datetime.fromtimestamp(seconds,timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')+f'.{nanos:09d}Z'
    _need(_day(stamp)==producer._plan.to_payload()['session_date'],'PAPER_FRESH_CLOCK_INVALID')
    final=qualify_market_inputs(producer._plan,observations,as_of=stamp).to_payload()
    _need(final['asset']==diagnostic['asset'] and final['quote']['valid']==diagnostic['quote']['valid']
          and final['observed_conditions_met']==diagnostic['observed_conditions_met'] and final['deficiencies']==diagnostic['deficiencies'],
          'PAPER_INPUT_OBSERVATION_CHANGED')


def _snapshot(owner,subject,packet_id,fresh_job_id,capture_id):
    """Resolve originals; all temporary plaintext resources close before return."""
    live_owner(owner);_need(not owner.db.in_transaction,'PAPER_INPUT_TRANSACTION_OPEN')
    value=owner._read(packet_id);preflight=owner.preflight(packet_id);market=owner._market
    _need(value['subject_key']==subject and value['state']=='PUBLISHED' and value['consumed'])
    _need(value['owner_generation']==owner.lease.generation and value['owner_instance']==owner.lease.identity.process_instance_id)
    _need(market is not None and market.parent is owner and market.lease is owner.lease)
    fresh=market.records.read(fresh_job_id);g=fresh['grant'];capture=market._lineage.records.read(capture_id)
    _need(g['mode']=='FRESH' and fresh['state']=='COMPLETE' and fresh['consumed'] and market._fresh_job==fresh_job_id)
    _need(all(g[k]==value[k] for k in ('project_id','subject_key','account_alias','credential_sha256','owner_generation','owner_instance')))
    _need(capture['state']=='PUBLISHED' and capture['job_id']==fresh_job_id and capture['grant_sha256']==fresh['grant_sha256'])
    _need(market._fresh_view is not None and market._producer is not None and market._opened is not None and market._combined is not None)
    manifest=_account_manifest(owner,value)
    facts,p,record,proposal,opening_record,confirmation,opening,reference,reasons=_account(owner,preflight,value,manifest)
    alias_record=binding._alias(owner,g['account_alias'],facts['identity_sha256'])
    opening_sources=_opening_sources(owner,opening_record)
    producer=market._producer;view=market._fresh_view;held=market._opened;combined=market._combined
    composition=_current_market(market,fresh)
    try:
        market._lineage._route(capture,capture['manifest'])
        with open_market_lineage(market,account_alias=g['account_alias'],capture_id=capture_id,manifest=capture['manifest']) as opened:
            snapshot=opened.snapshot();original=snapshot['lineage'];inner=original['lineage']
            _need(snapshot['metadata']['lineage_sha256']==capture['lineage_sha256']==_sha(original))
            _need(inner['fresh_grant']==g and inner['fresh_grant_sha256']==fresh['grant_sha256'])
            _need(inner['fresh']['records']==producer._wire_records())
            _need(inner['history']['manifest']==g['history']['manifest']==held.publication())
            proofs=original['consumption']
            _need(proofs['fresh']==market.consumptions.read(fresh_job_id) and proofs['history']==market.consumptions.read(g['history']['job_id']))
            prior=market.records.read(g['history']['job_id'])
            history_snapshot=held.snapshot()
            observations=_observations(producer._plan,_history_records(history_snapshot['collection'])+producer._wire_records())
    except RuntimeRefused as error:
        market._invalidate_fresh(fresh_job_id,error.code);raise
    # Historical diagnostic age is deliberately not compared with current age.
    composition=_current_market(market,fresh);p=preflight.diagnostic()
    deficiencies=set(p['deficiencies'])|set(reasons)|_MISSING|set(composition['diagnostic']['deficiencies'])
    if confirmation=='CONFIRMED_CURRENT_CONTEXT':deficiencies.discard('ACCOUNT_CONFIRMATION_UNVERIFIED')
    if opening!='CURRENT_CLEAN_OPENING':deficiencies.add('OPENING_BASELINE_UNVERIFIED')
    diagnostic=composition['diagnostic']
    result=dict(version=1,record_type='PaperInputDiagnostic',scope='CURRENT_OBSERVATIONS_ONLY',status='BLOCKED',
        project_id=owner.lease.project_id,account_alias=g['account_alias'],packet_id=packet_id,fresh_job_id=fresh_job_id,capture_id=capture_id,
        account_manifest_sha256=_sha(manifest),lineage_manifest_sha256=_sha(capture['manifest']),lineage_sha256=capture['lineage_sha256'],
        confirmation_status=confirmation,opening_status=opening,opening_reference_sha256=reference,
        checked_at=p['checked_at'],market_age_basis_at=composition['age_basis_at'],asset_valid=diagnostic['asset']['valid'],quote_valid=diagnostic['quote']['valid'],
        account_transport_provenance=p['transport_provenance'],market_clock_basis=composition['clock_basis'],
        deficiencies=sorted(deficiencies),financial_accepted=False,transport_authorized=False,research_eligible=False,actual_flat=None)
    raw=canonical(result);_need(len(raw)<=16384)
    protected=load_paper_slot(owner.lease,g['account_alias'])
    with open_paper_credentials(owner.lease,protected) as credentials:_reject_reflections(raw,tuple(credentials.headers().values()))
    _need(preflight._account_id.encode() not in raw,'PAPER_READ_PRIVATE_ID_REFLECTION')
    # No diagnostic escapes a clock/credential/identity change during verification.
    _current_market(market,fresh);preflight.diagnostic()
    if opening_record is not None:_need(original_opening(owner,g['account_alias'])[0]==opening_record)
    with open_read_evidence(owner.lease,g['account_alias'],packet_id,manifest):pass
    try:
        market._lineage._route(capture,capture['manifest'])
        with open_market_lineage(market,account_alias=g['account_alias'],capture_id=capture_id,manifest=capture['manifest']) as opened:
            _need(opened.snapshot()==snapshot)
    except RuntimeRefused as error:
        market._invalidate_fresh(fresh_job_id,error.code);raise
    _final_live(owner,preflight,market)
    protected=load_paper_slot(owner.lease,g['account_alias'])
    _need(hashlib.sha256(protected.ciphertext).hexdigest()==preflight._credential_sha==producer._credential_sha)
    # These manifests were resolved and decrypted above. Recheck their durable
    # publication bytes without another decryption or secrecy callback.
    with _owner_scope(owner.lease) as guard:
        published_original(guard,manifest)
        if opening_record is not None:published_original(guard,opening_sources[2])
        market._lineage._route(capture,capture['manifest'])
        published_original(guard,capture['manifest']);published_original(guard,prior['manifest'])
    producer._context();combined._context()
    _need(held.publication()==prior['manifest'] and held.snapshot()==history_snapshot)
    _need(view._pair is producer and producer._view is view and combined._fresh is view and combined._history is held)
    _need(producer._wire_records()==inner['fresh']['records'])
    history=binding._history(owner)
    _need(history['status'] in {'VERIFIED_ZERO_PRE_SCHEMA','VERIFIED_HISTORY'},'PAPER_INPUT_HISTORY_UNVERIFIED')
    _need(_sha(history)==facts['history_sha256'])
    _need(owner._preflight is preflight and owner._market is market and owner._account_proposal is proposal)
    _need(market._producer is producer and market._fresh_view is view and market._opened is held and market._combined is combined)
    _need(owner._read(packet_id)==value and _account_manifest(owner,value)==manifest)
    _need(binding._stored(owner,packet_id)==record and binding._state(owner,'paper_opening:'+g['account_alias'])==opening_record)
    _need(binding._alias(owner,g['account_alias'],facts['identity_sha256'])==alias_record)
    _need(_opening_sources(owner,opening_record)==opening_sources)
    if proposal is not None:
        _need(not proposal._closed and proposal._context is preflight and proposal.content==canonical(facts)
              and proposal._confirmed_at==record['confirmed_at'])
    _need(market.records.read(fresh_job_id)==fresh and market.records.read(g['history']['job_id'])==prior)
    _need(market._lineage.records.read(capture_id)==capture and market.consumptions.read(fresh_job_id)==proofs['fresh']
          and market.consumptions.read(g['history']['job_id'])==proofs['history'])
    with _slot(owner.lease) as (guard,path):
        _need(guard.api.read_regular(path,maximum=16384)==slot_payload(protected),'PAPER_INPUT_CREDENTIAL_CHANGED')
    _need(not owner._closed and owner.health.reason is None,'EXECUTION_HEALTH_UNVERIFIED')
    _final_clocks(preflight,market,producer,observations,diagnostic)
    _need(owner._preflight is preflight and not preflight._closed and owner._account_proposal is proposal
          and owner._market is market and market._producer is producer and market._fresh_view is view and market._opened is held
          and market._combined is combined and not producer._closed and not combined._closed and not held._closed
          and producer in producer._owner_state.resources and combined in combined._state.resources and held in held._state.resources)
    stable=dict(account=value,manifest=manifest,facts=facts,confirmation=record,alias=alias_record,opening=opening_record,
                opening_sources=opening_sources,fresh=fresh,capture=capture,history=prior,consumption=proofs)
    identities=(preflight,proposal,market,producer,view,held,combined)
    return result,_sha(stable),identities


@dataclass(frozen=True,slots=True,repr=False,init=False)
class _PaperInputContext:
    _owner:object
    _subject:str
    _packet:str
    _fresh:str
    _capture:str
    _generation:int
    _instance:str
    _binding:str
    _identities:tuple
    _closed:bool
    def __init__(self,*,_factory=None,**fields):
        _need(_factory is _FACTORY,'PAPER_INPUT_CONTEXT_UNQUALIFIED')
        for key,value in fields.items():object.__setattr__(self,key,value)
    def __repr__(self):return '<PrivatePaperInputContext redacted>'
    def __reduce_ex__(self,protocol):raise RuntimeRefused('PAPER_INPUT_PRIVATE_SERIALIZATION_FORBIDDEN')
    def close(self):
        with _MUTEX:
            object.__setattr__(self,'_closed',True);object.__setattr__(self,'_owner',None);object.__setattr__(self,'_identities',())
    def diagnostic(self):
        owner=self._owner;_need(not self._closed and owner is not None,'PAPER_INPUT_CONTEXT_UNAVAILABLE')
        try:
            with _owner_scope(owner.lease),owner.store._live():
                _need(not self._closed and self._owner is owner and owner._input_context is self)
                _need(self._generation==owner.lease.generation and self._instance==owner.lease.identity.process_instance_id)
                result,binding_hash,identities=_snapshot(owner,self._subject,self._packet,self._fresh,self._capture)
                _need(not self._closed and self._owner is owner and owner._input_context is self)
                _need(binding_hash==self._binding and len(identities)==len(self._identities) and all(a is b for a,b in zip(identities,self._identities)))
                return result
        except RuntimeRefused:
            self.close();raise
        except _INVALID:
            self.close();raise RuntimeRefused('PAPER_INPUT_CONTEXT_INVALID') from None


def input_context(owner,*,subject,packet_id,fresh_job_id,capture_id):
    try:
        with _owner_scope(owner.lease),owner.store._live():
            _need(type(subject) is str and re.fullmatch('[0-9a-f]{64}',subject) is not None)
            for ident in (packet_id,fresh_job_id,capture_id):uuid(ident)
            _,binding_hash,identities=_snapshot(owner,subject,packet_id,fresh_job_id,capture_id)
            result=_PaperInputContext(_factory=_FACTORY,_owner=owner,_subject=subject,_packet=packet_id,_fresh=fresh_job_id,
                _capture=capture_id,_generation=owner.lease.generation,_instance=owner.lease.identity.process_instance_id,
                _binding=binding_hash,_identities=identities,_closed=False)
            if owner._input_context is not None:owner._input_context.close()
            owner._input_context=result;return result
    except _INVALID:raise RuntimeRefused('PAPER_INPUT_CONTEXT_INVALID') from None
