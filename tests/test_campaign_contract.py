"""Fixed synthetic campaign contracts; no durable or financial claims."""
from dataclasses import asdict,replace
from functools import lru_cache
import hashlib,json
import pytest
from compertum.data.encoding import canonical
from compertum.data.errors import DataError
from compertum.modeling.campaign import CampaignInput,FoldInput,UNITS,build_campaign,read_campaign,compute_campaign_unit
from compertum.modeling.registry import VARIANTS
from compertum.simulation.runs import runtime_identity
from helpers.model_campaign_fixture import campaign_fixture,SECTORS

@lru_cache(maxsize=1)
def folds():
    return tuple(FoldInput(c,SECTORS,ts,te,s,e,a) for c,ts,te,s,e,a in (campaign_fixture(y) for y in (2021,2022,2023)))

@lru_cache(maxsize=1)
def bundle():return build_campaign(folds(),identity=runtime_identity())

def test_registry_and_schedule_are_frozen_before_any_fit(monkeypatch):
    import compertum.modeling.checkpoints as module
    def forbidden(*a,**k):raise AssertionError('registration must not fit')
    monkeypatch.setattr(module,'fit_ridge',forbidden)
    c=bundle();v=read_campaign(c.content,expected_sha256=c.sha256,identity=runtime_identity())
    assert len(UNITS)==63 and sum(u.phase=='fit' for u in UNITS)==27
    assert sum(u.phase=='evaluate' for u in UNITS)==36
    assert len({u.key for u in UNITS})==63
    assert v['registered_family']==[asdict(x) for x in VARIANTS]
    assert v['seeds']==dict(campaign=1729,model=1730,bootstrap=1731,counterexample=1732)
    assert v['financial_accepted'] is False and v['full_M2'] is False
    for i,u in enumerate(UNITS):
        if u.fit_unit is not None:
            fit=UNITS[u.fit_unit]
            assert u.fit_unit<i and fit.phase=='fit' and (fit.candidate_id,fit.year)==(u.candidate_id,u.year)

@pytest.mark.parametrize('case',['year','candidate','seed','unit','feature','configuration','identity','market','trial','extra'])
def test_rehashed_manifest_cannot_redefine_registered_contract(case):
    c=bundle();v=json.loads(c.content)
    if case=='year':v['folds'][0]['year']=2024
    elif case=='candidate':v['registered_family'].pop()
    elif case=='seed':v['seeds']['model']=99
    elif case=='unit':v['units'][4]['fit_unit']=0
    elif case=='feature':v['features'].reverse()
    elif case=='configuration':v['resolved_models'][0]['ridge']['solver']='auto'
    elif case=='identity':v['identity']['package_sha256']='0'*64
    elif case=='market':v['folds'][0]['market_sha256']='0'*64
    elif case=='trial':v['trials'][0]['sha256']='0'*64
    else:v['unregistered_metadata']='anything'
    raw=canonical(v)
    with pytest.raises(DataError):read_campaign(raw,expected_sha256=hashlib.sha256(raw).hexdigest(),identity=runtime_identity())

@pytest.mark.parametrize('case',['missing','duplicate','reverse','overlap','provider','chunk_bound','budget','type'])
def test_input_windows_types_and_resource_bounds_are_enforced(case):
    fs=list(folds());kw={}
    if case=='missing':fs.pop()
    elif case=='duplicate':fs[-1]=fs[0]
    elif case=='reverse':fs.reverse()
    elif case=='overlap':fs[0]=replace(fs[0],training_end=fs[0].start)
    elif case=='provider':fs[0]=replace(fs[0],chunks=(object(),))
    elif case=='chunk_bound':fs[0]=replace(fs[0],chunks=fs[0].chunks*6)
    elif case=='budget':kw['maximum_bytes']=129*1024**2
    else:kw['maximum_bytes']=True
    with pytest.raises(DataError):build_campaign(fs,identity=runtime_identity(),**kw)

def test_expected_input_hash_and_canonical_bytes_are_required():
    c=bundle()
    for raw,pin in [(c.content,'0'*64),(c.content+b' ',hashlib.sha256(c.content+b' ').hexdigest()),(b'{}','x')]:
        with pytest.raises(DataError):read_campaign(raw,expected_sha256=pin,identity=runtime_identity())

def test_fit_and_evaluation_separate_without_cold_fitting(monkeypatch):
    c=bundle();i=next(i for i,u in enumerate(UNITS) if u.phase=='fit')
    fit=compute_campaign_unit(c,i,identity=runtime_identity())
    import compertum.modeling.checkpoints as module
    def forbidden(*a,**k):raise AssertionError('campaign evaluation must reuse committed fit')
    monkeypatch.setattr(module,'fit_ridge',forbidden)
    with pytest.raises(DataError):compute_campaign_unit(c,i+1,identity=runtime_identity())
    result=compute_campaign_unit(c,i+1,identity=runtime_identity(),fit_checkpoint=fit,expected_fit_sha256=fit.sha256)
    v=json.loads(result.content);assert v['candidate']['candidate_id']==UNITS[i].candidate_id and v['year']==2021
    with pytest.raises(DataError):compute_campaign_unit(c,i+3,identity=runtime_identity(),fit_checkpoint=fit,expected_fit_sha256=fit.sha256)
    with pytest.raises(DataError):compute_campaign_unit(c,0,identity=runtime_identity(),fit_checkpoint=fit,expected_fit_sha256=fit.sha256)

@pytest.mark.parametrize('index',[-1,63,True,'0'])
def test_unit_index_is_strict(index):
    with pytest.raises(DataError):compute_campaign_unit(bundle(),index,identity=runtime_identity())
