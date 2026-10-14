"""Private lineage reconstruction using native owners and invented loopback data."""
import copy,json,pickle
import pytest
from compertum.data.encoding import canonical
from compertum.runtime.errors import RuntimeRefused
from compertum.runtime.paper_market_grants import MarketGrant
from test_paper_market_owner_fresh import history,completed,pair,owner,native_market,publication
from test_paper_market_publication import command


def inputs(o):
    p,_=completed(o)
    command(o,'compose',job_id=p['job_id'])
    market=o.a._market
    fresh=MarketGrant(canonical(market.records.read(p['job_id'])['grant']))
    prior=market.records.read(o.history['job_id'])
    return market._combined,fresh,MarketGrant(canonical(prior['grant'])),prior['manifest']


def capture(o,args):
    from compertum.runtime.paper_market_lineage import capture_market_lineage
    return capture_market_lineage(o.e.lease,args[0],fresh_grant=args[1],history_grant=args[2],history_manifest=args[3])


def test_capture_reconstructs_original_inputs_and_retains_no_authority(history):
    from compertum.runtime.paper_market_lineage import validate_market_lineage
    o=history;args=inputs(o);before=o.manager.store.conn.execute('SELECT count(*) FROM reservations').fetchone()
    value=capture(o,args);raw=value.content;p=json.loads(raw)
    result=validate_market_lineage(raw,history=o.a._market._opened.snapshot())
    assert result['diagnostic']==p['combined']['diagnostic']
    assert result['use']=='HISTORICAL_ONLY' and result['freshness']=='NOT_RESTORED'
    assert all(result[k] is False for k in ('financial_accepted','transport_authorized','research_eligible'))
    assert p['fresh']['records'][0]['request']['operation']=='ASSET'
    assert p['fresh']['records'][1]['request']['operation']=='QUOTE'
    assert 'collection' not in p and len(raw)<1024**2
    assert o.manager.store.conn.execute('SELECT count(*) FROM reservations').fetchone()==before
    assert value.content==raw and 'body_utf8' not in repr(value)
    with pytest.raises(RuntimeRefused):pickle.dumps(value)


def test_capture_reads_fresh_once_even_when_each_read_advances_clock(history,monkeypatch):
    import compertum.runtime.paper_market_fresh as module
    from compertum.runtime.paper_market_lineage import validate_market_lineage
    o=history;args=inputs(o);calls=[];original=module._MarketFresh._capture_at_use
    def advancing(pair):
        result=original(pair);calls.append(result)
        o.clock.utc+=1;o.clock.mono+=1
        return result
    monkeypatch.setattr(module._MarketFresh,'_capture_at_use',advancing)
    raw=capture(o,args).content
    assert len(calls)==1 and canonical(json.loads(raw)['fresh'])==calls[0][0]
    assert validate_market_lineage(raw,history=o.a._market._opened.snapshot())['use']=='HISTORICAL_ONLY'


@pytest.mark.parametrize('field',['body','reply','age','elapsed','combined','authority','extra','grant','history'])
def test_altered_originals_are_refused_after_outer_hashes_are_recomputed(history,field):
    import hashlib
    from compertum.runtime.paper_market_lineage import validate_market_lineage
    o=history;args=inputs(o);p=json.loads(capture(o,args).content)
    if field=='body':p['fresh']['records'][1]['body_utf8']='{}'
    elif field=='reply':p['fresh']['records'][0]['diagnostic']['raw_bytes']+=1
    elif field=='age':p['fresh']['age_basis_at']='2026-10-09T13:35:40+00:00'
    elif field=='elapsed':p['timing']['elapsed_ns']+=6000000000
    elif field=='combined':p['combined']['diagnostic']['quote']['valid']=False
    elif field=='authority':p['transport_authorized']=True
    elif field=='extra':p['extra']=True
    elif field=='grant':p['fresh_grant']['subject_key']='f'*64
    else:p['history']['snapshot_sha256']='f'*64
    p['fresh_sha256']=hashlib.sha256(canonical(p['fresh'])).hexdigest()
    p['combined']['fresh']['snapshot_sha256']=p['fresh_sha256']
    p['combined_sha256']=hashlib.sha256(canonical(p['combined'])).hexdigest()
    p['fresh_grant_sha256']=hashlib.sha256(canonical(p['fresh_grant'])).hexdigest()
    with pytest.raises(RuntimeRefused):validate_market_lineage(canonical(p),history=o.a._market._opened.snapshot())


@pytest.mark.parametrize('field',['subject_key','credential_sha256','owner_instance','owner_generation'])
def test_substituted_capture_grant_refused(history,field):
    from uuid import uuid4
    o=history;args=list(inputs(o));p=args[1].to_payload()
    p[field]=p[field]+1 if field=='owner_generation' else str(uuid4()) if field=='owner_instance' else 'f'*64
    args[1]=MarketGrant(canonical(p))
    with pytest.raises(RuntimeRefused):capture(o,args)


def test_stale_capture_reconstructs_original_blocked_diagnostic(history):
    from compertum.runtime.paper_market_lineage import validate_market_lineage
    o=history;args=inputs(o);o.clock.utc+=31;o.clock.mono+=31
    raw=capture(o,args).content
    result=validate_market_lineage(raw,history=o.a._market._opened.snapshot())
    assert not result['diagnostic']['quote']['valid'] and not result['diagnostic']['asset']['valid']


@pytest.mark.parametrize('fault',['closed','backward','history_manifest'])
def test_capture_requires_current_bound_sources(history,fault):
    o=history;args=list(inputs(o))
    if fault=='closed':args[0].close()
    elif fault=='backward':o.clock.utc-=1;o.clock.mono-=1
    else:args[3]=copy.deepcopy(args[3]);args[3]['sha256']='f'*64
    with pytest.raises(RuntimeRefused):capture(o,args)


def test_consistently_substituted_manifest_cannot_replace_opened_publication(history):
    o=history;args=list(inputs(o));g=args[1].to_payload();g['history']['manifest']['sha256']='f'*64
    args[1]=MarketGrant(canonical(g));args[3]=copy.deepcopy(g['history']['manifest'])
    with pytest.raises(RuntimeRefused):capture(o,args)


def test_completion_uses_monotonic_deadline_with_permitted_wall_clock_skew(history,monkeypatch):
    import compertum.runtime.paper_market_fresh as module
    from compertum.runtime.paper_market_lineage import validate_market_lineage
    o=history;original=module.qualify_market_inputs;advanced=[]
    def qualify(plan,observations,**kw):
        result=original(plan,observations,**kw)
        if len(observations)==2 and not advanced:
            o.clock.utc+=23;o.clock.mono+=19;advanced.append(True)
        return result
    monkeypatch.setattr(module,'qualify_market_inputs',qualify)
    args=inputs(o);raw=capture(o,args).content
    assert advanced and validate_market_lineage(raw,history=o.a._market._opened.snapshot())['use']=='HISTORICAL_ONLY'
    assert json.loads(raw)['timing']['completion']['monotonic_elapsed_seconds']==19


@pytest.mark.parametrize('stage',['reconstruct','scan'])
def test_mutation_during_lineage_validation_is_refused(history,monkeypatch,stage):
    import compertum.runtime.paper_market_lineage as module
    o=history;args=inputs(o);name='validate_market_lineage' if stage=='reconstruct' else '_scan_generated';original=getattr(module,name)
    def mutate(*a,**kw):
        result=original(*a,**kw);o.a._market._producer._records.clear();return result
    monkeypatch.setattr(module,name,mutate)
    with pytest.raises(RuntimeRefused):capture(o,args)


def test_lineage_secret_scan_refusal_is_preserved(history,monkeypatch):
    import compertum.runtime.paper_market_lineage as module
    o=history;args=inputs(o);original=module._scan_generated
    def scan(value,secrets):return original(value,(*secrets,'PrivateMarketInputLineage'))
    monkeypatch.setattr(module,'_scan_generated',scan)
    with pytest.raises(RuntimeRefused):capture(o,args)


def test_oversized_and_constructed_lineage_are_refused():
    from compertum.runtime.paper_market_lineage import validate_market_lineage,_CapturedMarketLineage
    with pytest.raises(RuntimeRefused):validate_market_lineage(b' '*(1024**2+1),history={})
    with pytest.raises(RuntimeRefused):_CapturedMarketLineage(b'{}')
