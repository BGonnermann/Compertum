"""Owner-resolved capture with original durable consumption observations."""
from dataclasses import dataclass
import json
from compertum.data.encoding import canonical
from compertum.domain import ContractError
from compertum.paper_market_inputs import _ns,_sha
from .errors import RuntimeRefused
from .owners import _owner_scope,require_live_owner
from .paper_market_grants import MarketGrant
from .paper_market_consumption import validate_consumption
from .paper_market_lineage import capture_market_lineage,validate_market_lineage
from .paper_market_compose import compose_market_inputs
from .paper_market_collection import _scan_generated
from .paper_credentials import open_paper_credentials

_MAX=1024**2+16384
_FACTORY=object()
_FIELDS={'version','record_type','purpose','lineage','lineage_sha256','consumption','use','freshness',
         'financial_accepted','transport_authorized','research_eligible'}
_INVALID=(ContractError,ValueError,TypeError,KeyError,AttributeError,OverflowError,RecursionError,UnicodeError)


def _need(value):
    if not value:raise RuntimeRefused('MARKET_OWNER_LINEAGE_INVALID')


def validate_owner_lineage(raw,*,history):
    """Reconstruct historical claims; publication authenticates their provenance."""
    try:
        _need(type(raw) is bytes and 0<len(raw)<=_MAX)
        value=json.loads(raw);_need(type(value) is dict and set(value)==_FIELDS and canonical(value)==raw)
        _need(type(value['version']) is int and value['version']==1 and value['record_type']=='PrivateOwnerMarketLineage')
        _need(value['purpose']=='OPERATIONAL_ONLY' and value['use']=='HISTORICAL_ONLY' and value['freshness']=='NOT_RESTORED')
        _need(all(value[k] is False for k in ('financial_accepted','transport_authorized','research_eligible')))
        inner=canonical(value['lineage']);_need(_sha(inner)==value['lineage_sha256'])
        result=validate_market_lineage(inner,history=history)
        proofs=value['consumption'];_need(type(proofs) is dict and set(proofs)=={'fresh','history'})
        for mode,started in [('fresh',value['lineage']['fresh']['started_at']),('history',history['collection']['started_at'])]:
            grant=MarketGrant(canonical(value['lineage'][mode+'_grant']))
            validate_consumption(proofs[mode],grant)
            _need(_ns(proofs[mode]['consumed_at'])<=_ns(started))
        return result
    except _INVALID:raise RuntimeRefused('MARKET_OWNER_LINEAGE_INVALID') from None


@dataclass(frozen=True,slots=True,repr=False,init=False)
class _OwnerMarketLineage:
    _content:bytes
    _sha256:str
    def __init__(self,raw,*,_factory=None):
        _need(_factory is _FACTORY and type(raw) is bytes and 0<len(raw)<=_MAX)
        object.__setattr__(self,'_content',raw);object.__setattr__(self,'_sha256',_sha(raw))
    @property
    def content(self):
        _need(type(self._content) is bytes and _sha(self._content)==self._sha256);return self._content
    def __repr__(self):return '<HistoricalOwnerMarketLineage private data redacted>'
    def __reduce_ex__(self,protocol):raise RuntimeRefused('MARKET_LINEAGE_SERIALIZATION_FORBIDDEN')


def capture_owner_lineage(owner,*,subject,job_id,grant_sha256):
    """Internal owner entry point; callers cannot supply grants or publications."""
    with _owner_scope(owner.lease):
        require_live_owner(owner.lease,'execution')
        _need(not owner.db.in_transaction)
        fresh=owner.records.read(job_id);g=fresh['grant']
        _need(g['subject_key']==subject and fresh['grant_sha256']==grant_sha256 and g['mode']=='FRESH')
        _need(fresh['state']=='COMPLETE' and fresh['consumed'] and owner._fresh_job==job_id)
        _need(owner._fresh_view is not None and owner._opened is not None and owner._producer is owner._fresh_view._pair)
        prior=owner._history(subject,g['account_alias'],g['plan']['symbol'],g['history'],g['credential_sha256'])
        proofs=dict(fresh=owner.consumptions.read(job_id),history=owner.consumptions.read(prior['grant']['job_id']))
        try:
            owner._fresh_current(fresh)
            if owner._combined is None:owner._combined=compose_market_inputs(owner.lease,owner._opened,owner._fresh_view)
            combined=owner._combined
            captured=capture_market_lineage(owner.lease,combined,fresh_grant=MarketGrant(canonical(g)),
                                          history_grant=MarketGrant(canonical(prior['grant'])),history_manifest=prior['manifest'])
            inner=captured.content
            value=dict(version=1,record_type='PrivateOwnerMarketLineage',purpose='OPERATIONAL_ONLY',lineage=json.loads(inner),lineage_sha256=_sha(inner),
                       consumption=proofs,use='HISTORICAL_ONLY',freshness='NOT_RESTORED',financial_accepted=False,transport_authorized=False,research_eligible=False)
            raw=canonical(value);_need(len(raw)<=_MAX)
            history=owner._opened.snapshot();validate_owner_lineage(raw,history=history)
            with open_paper_credentials(owner.lease,owner._producer._protected) as opened:_scan_generated(value,tuple(opened.headers().values()))
            owner._fresh_current(fresh);combined._context();owner._producer._context()
            _need(owner._combined is combined and owner._fresh_job==job_id and owner._fresh_view is combined._fresh)
            _need(owner.records.read(job_id)==fresh and owner.records.read(prior['grant']['job_id'])==prior)
            _need(owner.consumptions.read(job_id)==proofs['fresh'] and owner.consumptions.read(prior['grant']['job_id'])==proofs['history'])
            _need(owner._opened.snapshot()==history)
            return _OwnerMarketLineage(raw,_factory=_FACTORY)
        except RuntimeRefused as error:
            owner._invalidate_fresh(job_id,error.code)
            raise
