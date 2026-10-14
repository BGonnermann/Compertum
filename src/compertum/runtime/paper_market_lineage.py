"""Coherent private input capture and inert historical reconstruction.

This component neither publishes evidence nor verifies the caller's durable
owner records. Those are separate integration boundaries. Serialized provenance
is a historical producer assertion and grants no live authority.
"""
from dataclasses import dataclass
import json,math
from compertum.data.encoding import canonical
from compertum.domain import ContractError
from compertum.paper_market_inputs import OperationalMarketPlan,OperationalMarketRequest,MarketObservation,qualify_market_inputs,_ns,_day,_sha
from .errors import RuntimeRefused
from .owners import _owner_scope,require_live_owner
from .paper_credentials import open_paper_credentials
from .paper_market_collection import _scan_generated
from .paper_market_compose import _PrivateCombinedMarketInputs,_history_source,_history_records,_observations
from .paper_market_evidence import _OpenedMarketEvidence,_validate as validate_history
from .paper_market_grants import MarketGrant

_MAX=1024**2
_FACTORY=object()
_INVALID=(ContractError,ValueError,TypeError,KeyError,UnicodeError,RecursionError,AttributeError,OverflowError)
_FLAGS=('financial_accepted','transport_authorized','research_eligible')
_FIELDS={'version','record_type','purpose','fresh_grant','fresh_grant_sha256','history_grant','history_grant_sha256',
         'history','fresh','fresh_sha256','combined','combined_sha256','timing','use','freshness','provenance',*_FLAGS}
_FRESH_FIELDS={'version','record_type','purpose','pair_id','plan','state','reason','attempts','started_at','validated_at',
               'clock_basis','records','observed_at','age_basis_at','age_basis','diagnostic','diagnostic_error',*_FLAGS}


def _need(value):
    if not value:raise RuntimeRefused('MARKET_LINEAGE_INVALID')


def _fresh(value,timing,grant):
    _need(type(value) is dict and set(value)==_FRESH_FIELDS)
    _need(type(value['version']) is int and value['version']==1 and value['record_type']=='PrivateFreshInputs')
    _need(value['purpose']=='OPERATIONAL_ONLY' and all(value[k] is False for k in _FLAGS))
    _need(value['state']=='PAIR_COMPLETE' and value['reason'] is None and type(value['attempts']) is int and value['attempts']==2)
    _need(value['pair_id']==grant['job_id'] and value['plan']==grant['plan'] and value['diagnostic_error'] is None)
    _need(value['clock_basis'] in ('LOCAL_CLOCK','SYNTHETIC_FIXTURE') and value['age_basis']=='MAX_WALL_MONOTONIC')
    _need(type(timing) is dict and set(timing)=={'elapsed_seconds','elapsed_ns','completion'})
    elapsed=timing['elapsed_seconds']
    _need(type(elapsed) in (int,float) and math.isfinite(elapsed) and 0<=elapsed<=10**12)
    _need(type(timing['elapsed_ns']) is int and timing['elapsed_ns']==math.ceil(elapsed*10**9))
    completion=timing['completion'];_need(type(completion) is dict and set(completion)=={'monotonic_elapsed_seconds','native_elapsed_seconds'})
    _need(all(type(v) in (int,float) and math.isfinite(v) and 0<=v<20 for v in completion.values()))
    _need(completion['monotonic_elapsed_seconds']<=elapsed)
    start=_ns(value['started_at']);observed=_ns(value['observed_at']);age=_ns(value['age_basis_at'])
    _need(abs((observed-start)/10**9-elapsed)<=5 and observed>=start)
    _need(age==max(observed,start+timing['elapsed_ns']))
    # Consumption precedes producer construction. Grant expiry is retained but
    # cannot prove a consumption time absent from this historical contract.
    _need(_ns(grant['created_at'])<=start)
    plan=OperationalMarketPlan(canonical(grant['plan']));day=plan.to_payload()['session_date']
    for k in ('started_at','validated_at','observed_at','age_basis_at'):_need(_day(value[k])==day)
    records=value['records'];_need(type(records) is list and len(records)==2)
    observations=[];last=start
    for operation,row in zip(('ASSET','QUOTE'),records):
        _need(type(row) is dict and set(row)=={'request','body_utf8','diagnostic','dispatched_at','validated_at'})
        request=OperationalMarketRequest(plan,canonical(row['request']));r=request.to_payload();d=row['diagnostic']
        _need(r['operation']==operation and type(row['body_utf8']) is str and type(d) is dict)
        raw=row['body_utf8'].encode();_need(0<len(raw)<=65536 and type(d['status']) is int and d['status']==200)
        created=_ns(r['created_at']);sent=_ns(row['dispatched_at']);received=_ns(d['received_at']);validated=_ns(row['validated_at'])
        _need(last<=created<=sent<=received<=validated<=observed)
        for stamp in (r['created_at'],row['dispatched_at'],d['received_at'],row['validated_at']):_need(_day(stamp)==day)
        provenance='LOOPBACK_FIXTURE' if value['clock_basis']=='SYNTHETIC_FIXTURE' else 'PAPER_TLS' if operation=='ASSET' else 'DATA_TLS'
        expected=dict(version=1,record_type='PrivateMarketReply',scope='PREPARATION_ONLY',request_sha256=_sha(request.content),
            plan_sha256=plan.sha256,request_id=r['request_id'],operation=operation,status=200,received_at=d['received_at'],age_ns=received-created,
            raw_bytes=len(raw),raw_sha256=_sha(raw),transport_provenance=provenance,
            credential_dispatch_binding='NOT_SENT_FIXTURE' if provenance=='LOOPBACK_FIXTURE' else 'PINNED_ENVELOPE',
            outcome='HTTP_RESPONSE_OBSERVED',semantic_qualification='NOT_PERFORMED',timestamps='DECLARED',
            transport_authorized=False,financial_accepted=False,research_eligible=False,entitlement='UNVERIFIED',coverage='UNVERIFIED')
        _need(canonical(d)==canonical(expected));last=validated
        observations.append(MarketObservation(request,raw,200,d['received_at']))
    _need(value['validated_at']==records[-1]['validated_at'])
    _need(qualify_market_inputs(plan,tuple(observations),as_of=value['age_basis_at']).content==canonical(value['diagnostic']))
    return plan


def validate_market_lineage(raw,*,history):
    """Reconstruct against original history; this is not publication authentication."""
    try:
        _need(type(raw) is bytes and 0<len(raw)<=_MAX)
        value=json.loads(raw);_need(canonical(value)==raw and type(value) is dict and set(value)==_FIELDS)
        _need(type(value['version']) is int and value['version']==1 and value['record_type']=='PrivateMarketInputLineage')
        _need(value['purpose']=='OPERATIONAL_ONLY' and value['use']=='HISTORICAL_ONLY' and value['freshness']=='NOT_RESTORED')
        _need(value['provenance']=='HISTORICAL_PRODUCER_ASSERTION' and all(value[k] is False for k in _FLAGS))
        fg=MarketGrant(canonical(value['fresh_grant']));hg=MarketGrant(canonical(value['history_grant']))
        g=fg.to_payload();h=hg.to_payload()
        _need(fg.sha256==value['fresh_grant_sha256'] and hg.sha256==value['history_grant_sha256'])
        _need(g['mode']=='FRESH' and h['mode']=='HISTORY')
        _need(all(g[k]==h[k] for k in ('project_id','account_alias','subject_key','credential_sha256','plan','plan_sha256')))
        _need(g['history']==dict(job_id=h['job_id'],task_id=h['task_id'],grant_sha256=hg.sha256,manifest=value['history']['manifest']))
        meta=history['metadata'];collection=history['collection']
        verified=validate_history([canonical(meta),canonical(collection)],g['project_id'],g['account_alias'],h['task_id'],h['job_id'])
        _need(collection['mode']=='HISTORY' and collection['state']=='PAGINATION_COMPLETE' and collection['complete_by_cutoff'] is True)
        _need(collection['plan']==g['plan'] and meta['credential_sha256']==g['credential_sha256'] and meta['execution_generation']==h['owner_generation'])
        _need(value['history']==dict(manifest=g['history']['manifest'],metadata_sha256=_sha(canonical(meta)),snapshot_sha256=_sha(canonical(collection))))
        fresh=value['fresh'];plan=_fresh(fresh,value['timing'],g)
        _need(value['fresh_sha256']==_sha(canonical(fresh)) and value['combined_sha256']==_sha(canonical(value['combined'])))
        diagnostic=qualify_market_inputs(plan,_observations(plan,_history_records(collection)+fresh['records']),as_of=fresh['age_basis_at']).to_payload()
        href=dict(collection_id=meta['collection_id'],snapshot_sha256=meta['snapshot_sha256'],producer_generation=meta['execution_generation'],
            provenance='HISTORICAL_PRODUCER_ASSERTION',freshness='NOT_RESTORED',native_provenance=collection['native_provenance'],
            clock_basis=collection['clock_basis'],task_id=meta['task_id'],validated_at=collection['validated_at'])
        expected=dict(version=1,record_type='PrivateCombinedMarketInputs',purpose='OPERATIONAL_ONLY',plan_sha256=plan.sha256,
            execution_generation=g['owner_generation'],history=href,
            fresh=dict(pair_id=g['job_id'],snapshot_sha256=value['fresh_sha256'],provenance=[r['diagnostic']['transport_provenance'] for r in fresh['records']]),
            observed_at=fresh['observed_at'],age_basis_at=fresh['age_basis_at'],age_basis=fresh['age_basis'],clock_basis=fresh['clock_basis'],
            diagnostic=diagnostic,financial_accepted=False,transport_authorized=False,research_eligible=False)
        _need(canonical(expected)==canonical(value['combined']))
        return dict(use='HISTORICAL_ONLY',freshness='NOT_RESTORED',provenance=verified['provenance'],diagnostic=diagnostic,
                    financial_accepted=False,transport_authorized=False,research_eligible=False)
    except _INVALID:raise RuntimeRefused('MARKET_LINEAGE_INVALID') from None


@dataclass(frozen=True,slots=True,repr=False,init=False)
class _CapturedMarketLineage:
    _content:bytes
    _sha256:str
    def __init__(self,raw,*,_factory=None):
        _need(_factory is _FACTORY and type(raw) is bytes and 0<len(raw)<=_MAX)
        object.__setattr__(self,'_content',raw);object.__setattr__(self,'_sha256',_sha(raw))
    @property
    def content(self):
        _need(type(self._content) is bytes and _sha(self._content)==self._sha256);return self._content
    def __repr__(self):return '<HistoricalMarketInputLineage private data redacted>'
    def __reduce_ex__(self,protocol):raise RuntimeRefused('MARKET_LINEAGE_SERIALIZATION_FORBIDDEN')


def capture_market_lineage(lease,combined,*,fresh_grant,history_grant,history_manifest):
    """Capture one live composition; original grants remain inert assertions."""
    try:
        with _owner_scope(lease) as state:
            require_live_owner(lease,'execution')
            _need(type(combined) is _PrivateCombinedMarketInputs and combined._lease is lease and combined._state is state)
            _need(type(combined._history) is _OpenedMarketEvidence)
            _need(type(fresh_grant) is MarketGrant and type(history_grant) is MarketGrant)
            fresh_grant.__post_init__();history_grant.__post_init__();g=fresh_grant.to_payload();h=history_grant.to_payload()
            pair=combined._fresh._pair
            _need(g['owner_instance']==lease.identity.process_instance_id and g['owner_generation']==lease.generation)
            _need(g['job_id']==pair._pair_id and g['credential_sha256']==pair._credential_sha and g['plan']==pair._plan.to_payload())
            _need(g['history']['manifest']==history_manifest==combined._history.publication())
            captured=combined._capture();pstate=pair._state_sha;binding=combined._binding_sha
            value=dict(version=1,record_type='PrivateMarketInputLineage',purpose='OPERATIONAL_ONLY',fresh_grant=g,fresh_grant_sha256=fresh_grant.sha256,
                history_grant=h,history_grant_sha256=history_grant.sha256,
                history=dict(manifest=history_manifest,metadata_sha256=_sha(canonical(captured['history_metadata'])),snapshot_sha256=_sha(captured['history'])),
                fresh=json.loads(captured['fresh']),fresh_sha256=_sha(captured['fresh']),combined=json.loads(captured['combined']),combined_sha256=_sha(captured['combined']),
                timing=captured['timing'],use='HISTORICAL_ONLY',freshness='NOT_RESTORED',provenance='HISTORICAL_PRODUCER_ASSERTION',
                financial_accepted=False,transport_authorized=False,research_eligible=False)
            raw=canonical(value);_need(len(raw)<=_MAX)
            validate_market_lineage(raw,history=dict(metadata=captured['history_metadata'],collection=json.loads(captured['history'])))
            with open_paper_credentials(lease,pair._protected) as opened:_scan_generated(value,tuple(opened.headers().values()))
            combined._context();pair._context()
            _need(combined._binding_sha==binding and pair._state_sha==pstate and pair._view is combined._fresh)
            after=_history_source(lease,state,combined._history)
            _need(after[1]==captured['history'] and after[5]==combined._history_identity)
            return _CapturedMarketLineage(raw,_factory=_FACTORY)
    except _INVALID:raise RuntimeRefused('MARKET_LINEAGE_INVALID') from None
