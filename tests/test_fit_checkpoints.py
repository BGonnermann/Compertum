import hashlib,json
from dataclasses import replace
from functools import lru_cache
import pytest
from compertum.data.encoding import canonical
from compertum.data.errors import DataError
from compertum.modeling.candidate import evaluate_candidate
from compertum.modeling.checkpoints import FitCheckpoint,prepare_fit_checkpoint
from helpers.model_campaign_fixture import campaign_fixture,SECTORS
from helpers.simulation_fixture import changed

@lru_cache(maxsize=3)
def checkpoint(h=1):
    c,ts,te,_,_,_=campaign_fixture()
    return prepare_fit_checkpoint(c,SECTORS,ts,te,2021,f'ridge-h{h:02}-a001')

def evaluate(fit=None,**kwargs):
    c,ts,te,s,e,a=campaign_fixture()
    args=dict(chunks=c,sectors=SECTORS,training_start=ts,training_end=te,start=s,end=e,candidate_id='ridge-h01-a001',scoring_as_of=a)
    if fit is not None:args.update(fit_checkpoint=fit,expected_fit_sha256=fit.sha256)
    args.update(kwargs);return evaluate_candidate(**args)

@pytest.mark.parametrize('h',[1,5,21])
def test_reuse_saved_fit_has_exact_candidate_output_and_never_refits(h,monkeypatch):
    id=f'ridge-h{h:02}-a001';fit=checkpoint(h);cold=evaluate(candidate_id=id)
    import compertum.modeling.checkpoints as module
    def forbidden(*a,**kw):raise AssertionError('checkpoint resume must not fit')
    monkeypatch.setattr(module,'fit_ridge',forbidden)
    resumed=evaluate(fit,candidate_id=id)
    assert resumed.content==cold.content and resumed.sha256==cold.sha256

@pytest.mark.parametrize('kw',[{'candidate_id':'ridge-h01-a010'},{'candidate_id':'momentum-h01'},{'expected_fit_sha256':'0'*64},{'training_end':'2020-12-30'}])
def test_changed_checkpoint_binding_is_refused(kw):
    with pytest.raises(DataError):evaluate(checkpoint(),**kw)

def test_corruption_missing_expected_hash_and_nested_tampering_refused():
    fit=checkpoint()
    with pytest.raises(DataError):evaluate(replace(fit,content=fit.content+b' '))
    with pytest.raises(DataError):evaluate(fit,expected_fit_sha256=None)
    v=json.loads(fit.content);v['model']['ridge']['intercept']+=1
    raw=canonical(v);fake=FitCheckpoint(raw,hashlib.sha256(raw).hexdigest())
    with pytest.raises(DataError):evaluate(fake)

def test_changed_market_refused_even_when_training_dates_match():
    chunks,*_=campaign_fixture()
    def edit(v):
        for b in v['bars']:b['volume']='50001'
    with pytest.raises(DataError):evaluate(checkpoint(),chunks=changed(chunks,edit))

def test_provider_and_protected_price_sources_are_refused():
    from compertum.data.calendar import session_times
    from compertum.data.snapshot import validate_snapshot
    from datetime import timedelta
    c,ts,te,_,_,_=campaign_fixture()
    with pytest.raises(DataError):prepare_fit_checkpoint([object()],SECTORS,ts,te,2021,'ridge-h01-a001')
    with pytest.raises(DataError):prepare_fit_checkpoint(c,SECTORS,ts,te,2024,'ridge-h01-a001')
    v=json.loads(c[0].content);v['feature_sessions']=['2024-01-02'];v['bars']=list({(b['reference'],b['adjustment']):b for b in v['bars']}.values())
    t=session_times('2024-01-02');n=session_times(t.next_date)
    for b in v['bars']:
        ref=b['reference'];label=t.open.replace(hour=5,minute=0) if ref=='daily' else t.close_reference if ref=='close' else n.entry
        available=n.decision if ref=='daily' else t.close+timedelta(minutes=15) if ref=='close' else n.entry+timedelta(minutes=16)
        b.update(session_date=n.previous_date if ref!='entry' else t.next_date,bar_label_time=label.isoformat(),provider_timestamp=label.isoformat(),simulated_available_at=available.isoformat(),simulated_revision_available_at=available.isoformat())
    extra=validate_snapshot(canonical(v))
    with pytest.raises(DataError,match='DEVELOPMENT_PRICES_ONLY'):prepare_fit_checkpoint(c+(extra,),SECTORS,ts,te,2021,'ridge-h01-a001')

@pytest.mark.parametrize('case',['horizon','observations'])
def test_nested_rehashed_fit_identity_cannot_contradict_manifest(case):
    fit=checkpoint(5 if case=='horizon' else 1);v=json.loads(fit.content)
    if case=='horizon':
        v['candidate_id']='ridge-h01-a001';v['model']['candidate_id']='ridge-h01-a001'
        v['model']['horizon']=1;v['dataset_assembly']['horizon']=1
    else:v['model']['observations']+=1
    v['model_sha256']=hashlib.sha256(canonical(v['model'])).hexdigest()
    raw=canonical(v);fake=FitCheckpoint(raw,hashlib.sha256(raw).hexdigest())
    with pytest.raises(DataError):evaluate(fake)

@pytest.mark.parametrize('case',['window','provenance'])
def test_checkpoint_coverage_and_provenance_match_declared_training_window(case):
    from compertum.data.calendar import session_times
    v=json.loads(checkpoint().content);kwargs={}
    if case=='window':
        start=session_times(v['training_start']).next_date
        v['training_start']=v['dataset_assembly']['start']=start;kwargs['training_start']=start
    else:
        v['dataset_assembly']['row_provenance'][0]['symbol']='NVDA'
    raw=canonical(v);fake=FitCheckpoint(raw,hashlib.sha256(raw).hexdigest())
    with pytest.raises(DataError):evaluate(fake,**kwargs)
