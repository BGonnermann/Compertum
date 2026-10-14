"""Private frozen-history/current-quote composition; never admission authority."""
import json
from compertum.data.encoding import canonical
from compertum.domain import ContractError
from compertum.paper_market_inputs import OperationalMarketPlan,OperationalMarketRequest,MarketObservation,qualify_market_inputs,_ns,_sha
from .errors import RuntimeRefused
from .owners import _MUTEX,_owner_scope,require_live_owner
from .paper_credentials import open_paper_credentials
from .paper_market_collection import _PrivateCollectionSnapshot,_MarketCollection,_scan_generated
from .paper_market_evidence import _OpenedMarketEvidence
from .paper_market_attempts import validate_attempt_chain
from .paper_market_fresh import _PrivateFreshView,_MarketFresh

_FACTORY=object()
_INVALID=(ContractError,ValueError,TypeError,KeyError,UnicodeError,RecursionError,AttributeError,OverflowError)


def _need(value,code='PAPER_COMPOSITION_INVALID'):
    if not value:raise RuntimeRefused(code)


def _history_source(lease,state,source):
    if type(source) is _PrivateCollectionSnapshot:
        c=source._collection
        _need(type(c) is _MarketCollection and c._lease is lease and c._owner_state is state and c in state.resources and not c._closed)
        _need(c.private_snapshot() is source);raw=source.content;v=json.loads(raw)
        expected=c._snapshot_value()
        _need(canonical(expected)==raw,'PAPER_COMPOSITION_EVIDENCE_CHANGED')
        meta=dict(project_id=lease.project_id,account_alias=c._protected.account_alias,collection_id=c._collection_id,
                  execution_generation=c._generation,credential_sha256=c._credential_sha,snapshot_sha256=_sha(raw))
        provenance='LIVE_OWNER_ASSERTION';freshness='FROZEN_BY_PRODUCER'
    else:
        _need(type(source) is _OpenedMarketEvidence and source._lease is lease and source._state is state
              and source in state.resources and not source._closed)
        opened=source.snapshot();meta=opened['metadata'];v=opened['collection'];raw=canonical(v)
        _need(opened['use']=='HISTORICAL_ONLY' and opened['freshness']=='NOT_RESTORED')
        provenance='HISTORICAL_PRODUCER_ASSERTION';freshness='NOT_RESTORED'
    plan=OperationalMarketPlan(canonical(v['plan']));pp=plan.to_payload();cutoff=_ns(pp['history_cutoff_at'])
    _need(v['mode']=='HISTORY' and v['state']=='PAGINATION_COMPLETE' and v['complete_by_cutoff'] is True and v['aggregate'] is not None)
    _need(v['collection_id']==meta['collection_id'] and pp['project_id']==lease.project_id==meta['project_id']
          and pp['account_alias']==meta['account_alias'] and _sha(raw)==meta['snapshot_sha256'])
    records=_history_records(v)
    _need(0<len(records)<=8 and _ns(v['validated_at'])<=cutoff)
    for r in records:
        _need(r['request']['operation']=='HISTORY' and r['validated_at'] is not None
              and _ns(r['diagnostic']['received_at'])<=_ns(r['validated_at'])<=cutoff)
    reference=dict(collection_id=meta['collection_id'],snapshot_sha256=_sha(raw),producer_generation=meta['execution_generation'],
                   provenance=provenance,freshness=freshness,native_provenance=v['native_provenance'],clock_basis=v['clock_basis'],
                   task_id=meta.get('task_id'),validated_at=v['validated_at'])
    identity=_sha(canonical(dict(metadata=meta,reference=reference)))
    return plan,raw,v,meta,reference,identity


def _history_records(value):
    if value['version']==1:return value['records']
    _need(value['version']==2)
    plan=OperationalMarketPlan(canonical(value['plan']))
    projection=validate_attempt_chain(plan,mode=value['mode'],chain=value['attempt_chain'],selected_requests=value['selected_requests'],
        started_at=value['started_at'],started_ns=value['started_monotonic_ns'],deadline_ns=value['deadline_monotonic_ns'],clock_basis=value['clock_basis'])
    _need(projection['aggregate']==canonical(value['aggregate']) and projection['validated_at']==value['validated_at']
          and projection['native_provenance']==value['native_provenance'])
    return projection['records']


def _fresh_source(lease,source):
    _need(type(source) is _PrivateFreshView and type(source._pair) is _MarketFresh)
    pair=source._pair;_need(pair._lease is lease and pair.private_snapshot() is source)
    raw,timing=source._capture();v=json.loads(raw)
    _need(v['state']=='PAIR_COMPLETE' and v['diagnostic'] is not None and len(v['records'])==2
          and [r['request']['operation'] for r in v['records']]==['ASSET','QUOTE'])
    _need(all(r['validated_at'] is not None for r in v['records']))
    return pair,raw,v,pair._binding(),pair._state_sha,timing


def _observations(plan,records):
    return tuple(MarketObservation(OperationalMarketRequest(plan,canonical(r['request'])),r['body_utf8'].encode('utf-8'),
                                   r['diagnostic']['status'],r['diagnostic']['received_at']) for r in records)


class _PrivateCombinedMarketInputs:
    __slots__=('_lease','_state','_history','_fresh','_plan','_history_identity','_history_sha','_credential_sha','_pair_binding','_closed','_binding_sha')
    def __init__(self,lease,state,history,fresh,plan,history_identity,history_sha,credential_sha,pair_binding,*,_factory=None):
        _need(_factory is _FACTORY)
        self._lease=lease;self._state=state;self._history=history;self._fresh=fresh;self._plan=plan
        self._history_identity=history_identity;self._history_sha=history_sha;self._credential_sha=credential_sha;self._pair_binding=pair_binding
        self._closed=False;self._binding_sha=self._binding()
    def _binding(self):
        return _sha(canonical(dict(lease=id(self._lease),state=id(self._state),history=id(self._history),fresh=id(self._fresh),
            generation=self._lease.generation,instance=self._lease.identity.process_instance_id,plan=self._plan.sha256,
            history_identity=self._history_identity,history_sha=self._history_sha,credential_sha=self._credential_sha,pair_binding=self._pair_binding)))
    def _context(self):
        require_live_owner(self._lease,'execution')
        _need(not self._closed and self in self._state.resources and self._binding()==self._binding_sha,'PAPER_COMPOSITION_CONTEXT_CHANGED')
    def __repr__(self):return '<PrivateCombinedInputs original data redacted>'
    def __reduce_ex__(self,protocol):raise RuntimeRefused('PAPER_COMPOSITION_SERIALIZATION_FORBIDDEN')
    @property
    def content(self):
        return self._capture()['combined']
    def _capture(self):
        try:
            with _owner_scope(self._lease):
                self._context();binding=self._binding_sha
                plan,hraw,hv,hm,href,hidentity=_history_source(self._lease,self._state,self._history)
                _need(hidentity==self._history_identity and _sha(hraw)==self._history_sha and plan.content==self._plan.content)
                pair,fraw,fv,pbinding,pstate,timing=_fresh_source(self._lease,self._fresh)
                _need(pbinding==self._pair_binding and pair._credential_sha==self._credential_sha==hm['credential_sha256']
                      and pair._plan.content==plan.content)
                observations=_observations(plan,_history_records(hv)+fv['records'])
                diagnostic=qualify_market_inputs(plan,observations,as_of=fv['age_basis_at']).to_payload()
                value=dict(version=1,record_type='PrivateCombinedMarketInputs',purpose='OPERATIONAL_ONLY',plan_sha256=plan.sha256,
                    execution_generation=self._lease.generation,history=href,
                    fresh=dict(pair_id=fv['pair_id'],snapshot_sha256=_sha(fraw),provenance=[r['diagnostic']['transport_provenance'] for r in fv['records']]),
                    observed_at=fv['observed_at'],age_basis_at=fv['age_basis_at'],age_basis=fv['age_basis'],clock_basis=fv['clock_basis'],
                    diagnostic=diagnostic,financial_accepted=False,transport_authorized=False,research_eligible=False)
                content=canonical(value);_need(len(content)<=131072,'PAPER_COMPOSITION_RETENTION_LIMIT')
                with open_paper_credentials(self._lease,pair._protected) as opened:_scan_generated(value,tuple(opened.headers().values()))
                # Validation and scanning may execute code: neither source can change during them.
                self._context();_need(self._binding_sha==binding)
                after=_history_source(self._lease,self._state,self._history)
                _need(after[1]==hraw and after[5]==hidentity,'PAPER_COMPOSITION_EVIDENCE_CHANGED')
                pair._context();_need(pair._binding()==pbinding and pair._state_sha==pstate and pair._view is self._fresh,'PAPER_COMPOSITION_EVIDENCE_CHANGED')
                return dict(combined=content,fresh=fraw,timing=timing,history=hraw,history_metadata=hm)
        except _INVALID:raise RuntimeRefused('PAPER_COMPOSITION_INVALID') from None
    def to_payload(self):return json.loads(self.content)
    def close(self):
        with _MUTEX:
            self._closed=True
            if self in self._state.resources:self._state.resources.remove(self)


def compose_market_inputs(lease,history,fresh):
    try:
        with _owner_scope(lease) as state:
            require_live_owner(lease,'execution')
            _need(not any(type(r) is _PrivateCombinedMarketInputs and not r._closed for r in state.resources),'PAPER_COMPOSITION_CAPACITY')
            plan,raw,v,meta,reference,identity=_history_source(lease,state,history)
            pair,_,_,binding,_,_=_fresh_source(lease,fresh)
            _need(pair._plan.content==plan.content and pair._credential_sha==meta['credential_sha256'])
            result=_PrivateCombinedMarketInputs(lease,state,history,fresh,plan,identity,_sha(raw),meta['credential_sha256'],binding,_factory=_FACTORY)
            state.resources.append(result);return result
    except _INVALID:raise RuntimeRefused('PAPER_COMPOSITION_INVALID') from None
