"""Predeclared engineering model tests; every number is invented."""
from dataclasses import replace
from datetime import timedelta
import json
import numpy as np
import pytest
from compertum.data.calendar import session_times
from compertum.data.errors import DataError
from compertum.modeling.registry import FEATURES, VARIANTS, variant, annual_cutoff
from compertum.modeling.ridge import freeze_rows, prepare_fit, fit_ridge, predict, RidgeArtifact


def row(day,x,y,*,symbol='AAPL',horizon=1):
    times=session_times(day);end=day
    for _ in range(horizon):end=session_times(end).next_date
    endtimes=session_times(end)
    return dict(symbol=symbol,feature_session=times.previous_date,decision_at=times.decision.isoformat(),entry_at=times.entry.isoformat(),label_end_at=endtimes.entry.isoformat(),
        simulated_feature_available_at=times.decision.isoformat(),simulated_label_available_at=session_times(endtimes.next_date).decision.isoformat(),
        simulated_revision_available_at=session_times(endtimes.next_date).decision.isoformat(),label_revision_id='fixture-v1',features=[x]+[2.]*14,target=y)


def rows(horizon=1):return [row(d,x,2*x+3,horizon=horizon) for d,x in [('2020-11-02',-1.),('2020-11-03',0.),('2020-11-04',1.)]]

def fitted(alpha=1,horizon=1,extra=()):
    bundle=freeze_rows(rows(horizon)+list(extra),horizon=horizon,feature_names=FEATURES)
    manifest=prepare_fit(bundle,2021)
    return fit_ridge(bundle,manifest,f'ridge-h{horizon:02}-a{alpha:03}'),manifest


def test_registry_is_exact_and_immutable():
    assert len(VARIANTS)==12 and len({v.candidate_id for v in VARIANTS})==12
    assert sum(v.kind=='momentum' for v in VARIANTS)==3
    assert {(v.horizon,v.alpha) for v in VARIANTS if v.kind=='ridge'}=={(h,a) for h in [1,5,21] for a in [1,10,100]}
    assert len(FEATURES)==len(set(FEATURES))==15
    assert annual_cutoff(2021).isoformat()=='2021-01-04T12:00:00+00:00'
    assert annual_cutoff(2022).isoformat()=='2022-01-03T12:00:00+00:00'
    with pytest.raises(DataError):variant('ridge-h01-a002')


@pytest.mark.parametrize('year',[2020,2024,2026,True,'2021'])
def test_non_development_fit_year_refused(year):
    with pytest.raises(DataError):annual_cutoff(year)


@pytest.mark.parametrize('alpha',[1,10,100])
@pytest.mark.parametrize('horizon',[1,5,21])
def test_nine_fixed_fits_match_independent_hand_solution(alpha,horizon):
    artifact,manifest=fitted(alpha,horizon)
    inputs=[r['features'] for r in rows(horizon)]
    expected=[3+2*x*3/(3+alpha) for x in [-1,0,1]]
    assert predict(artifact,inputs,feature_names=FEATURES)==pytest.approx(expected,rel=1e-12,abs=1e-12)
    saved=json.loads(artifact.content)
    assert saved['scaler']['mean']==[0.]+[2.]*14
    assert saved['scaler']['scale'][1:]==[1.]*14
    assert saved['ridge']['coef'][1:]==[0.]*14
    assert saved['ridge']['intercept']==pytest.approx(3.)
    assert saved['resolved']['ridge']['solver']=='svd' and saved['resolved']['ridge']['fit_intercept'] is True
    assert saved['status']=='SYNTHETIC_ENGINEERING' and saved['financial_accepted'] is False
    assert saved['fit_manifest_sha256']==manifest.sha256
    individual=[predict(artifact,[x],feature_names=FEATURES)[0] for x in inputs]
    assert individual==pytest.approx(expected,rel=1e-12,abs=1e-12)


@pytest.mark.parametrize('field', ['simulated_feature_available_at','simulated_label_available_at','simulated_revision_available_at'])
def test_one_unavailable_asset_purges_whole_decision_date(field):
    extra=row('2020-12-01',10,10);extra[field]='2021-01-04T12:00:01Z'
    other=row('2020-12-01',20,20,symbol='MSFT')
    artifact,manifest=fitted(extra=[extra,other]);value=json.loads(manifest.content)
    assert len(value['included'])==3 and len(value['excluded'])==2
    assert all('SAME_DATE_PURGE' in e['reasons'] for e in value['excluded'])
    assert predict(artifact,[[0.]+[2.]*14],feature_names=FEATURES)==pytest.approx([3.])


def test_future_feature_at_original_decision_is_rejected_from_fit():
    late=row('2020-12-01',100,100);late['simulated_feature_available_at']=(session_times('2020-12-01').decision+timedelta(seconds=1)).isoformat()
    _,manifest=fitted(extra=[late]);assert 'FEATURE_AFTER_DECISION' in json.loads(manifest.content)['excluded'][0]['reasons']


def test_overlap_and_late_label_never_enter_training_scaler():
    future=row('2020-12-31',1e9,-1e9,horizon=21)
    first,manifest=fitted(horizon=21,extra=[future]);future['features'][0]=-1e9;future['target']=1e9
    second,_=fitted(horizon=21,extra=[future])
    a=json.loads(first.content);b=json.loads(second.content)
    assert a['scaler']==b['scaler'] and a['ridge']==b['ridge']
    assert 'EVALUATION_OVERLAP' in json.loads(manifest.content)['excluded'][0]['reasons']


def test_cutoff_equality_is_allowed():
    equal=row('2020-12-01',0,3);equal['simulated_label_available_at']='2021-01-04T12:00:00Z';equal['simulated_revision_available_at']='2021-01-04T12:00:00Z'
    _,manifest=fitted(extra=[equal]);assert len(json.loads(manifest.content)['included'])==4


def test_rows_sorted_canonically_and_inputs_immutable():
    original=rows();before=json.dumps(original,sort_keys=True)
    a=freeze_rows(original,horizon=1,feature_names=FEATURES);b=freeze_rows(list(reversed(original)),horizon=1,feature_names=FEATURES)
    assert a.content==b.content and json.dumps(original,sort_keys=True)==before


@pytest.mark.parametrize('mutation',[
 lambda r:r.update(decision_at='2020-11-02T00:00:00Z'),
 lambda r:r.update(entry_at=r['decision_at']),
 lambda r:r.update(label_end_at=r['entry_at']),
 lambda r:r.update(simulated_label_available_at=r['label_end_at']),
 lambda r:r.update(feature_session='2020-11-02'),
 lambda r:r.update(symbol='SPY'),
 lambda r:r.update(features=[1.]*14),
 lambda r:r.update(features=[float('nan')]*15),
 lambda r:r.update(features=np.ma.array([1.]*15,mask=[True]+[False]*14)),
 lambda r:r.update(features=[True]*15),
 lambda r:r.update(target=float('inf')),
 lambda r:r.update(target=True),
 lambda r:r.update(label_revision_id=''),
 lambda r:r.update(extra='unregistered'),
])
def test_invalid_row_fails_before_fitting(mutation):
    value=rows();mutation(value[0])
    with pytest.raises(DataError):freeze_rows(value,horizon=1,feature_names=FEATURES)


def test_duplicate_row_and_protected_date_refused():
    with pytest.raises(DataError):freeze_rows(rows()+[rows()[0]],horizon=1,feature_names=FEATURES)
    with pytest.raises(DataError):freeze_rows([row('2024-01-02',0,0)],horizon=1,feature_names=FEATURES)


def test_wrong_feature_order_and_masked_serving_refused():
    with pytest.raises(DataError):freeze_rows(rows(),horizon=1,feature_names=tuple(reversed(FEATURES)))
    artifact,_=fitted()
    with pytest.raises(DataError):predict(artifact,[[0.]*15],feature_names=tuple(reversed(FEATURES)))
    with pytest.raises(DataError):predict(artifact,[np.ma.array([0.]*15,mask=[True]+[False]*14)],feature_names=FEATURES)


def test_tampered_bundle_manifest_artifact_refused():
    bundle=freeze_rows(rows(),horizon=1,feature_names=FEATURES);manifest=prepare_fit(bundle,2021)
    with pytest.raises(DataError):prepare_fit(replace(bundle,content=bundle.content+b' '),2021)
    with pytest.raises(DataError):fit_ridge(bundle,replace(manifest,content=manifest.content+b' '),'ridge-h01-a001')
    artifact=fit_ridge(bundle,manifest,'ridge-h01-a001')
    with pytest.raises(DataError):predict(replace(artifact,content=artifact.content+b' '),[[0.]*15],feature_names=FEATURES)
    with pytest.raises(DataError):fit_ridge(bundle,manifest,'ridge-h05-a001')
    with pytest.raises(DataError):fit_ridge(bundle,manifest,'momentum-h01')
