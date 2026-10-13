"""Closed generated fits: causal cutoffs, whole-date purge and independent math."""
import hashlib,json
from datetime import timedelta
import numpy as np
import pytest
from compertum.data.encoding import canonical
from compertum.data.errors import DataError
from compertum.data.calendar import session_times,utc_time
from compertum.final_recipe import recipe,recipe_hash
from compertum.modeling.generated_fits import prepare_generated_fits


@pytest.fixture(scope='module')
def fitted():
    return prepare_generated_fits(canonical(recipe()),expected_sha256=recipe_hash(),
        candidate_ids=('ridge-h01-a001','ridge-h05-a010','ridge-h21-a100'))


def test_generated_fits_expand_with_fixed_start_and_exact_causal_purge(fitted):
    report=json.loads(fitted.content)
    assert hashlib.sha256(fitted.content).hexdigest()==fitted.sha256
    assert report['financial_accepted'] is False and report['full_M3'] is False
    assert len(report['fits'])==6
    for item in report['fits']:
        rows=item['rows'];manifest=item['manifest'];year=item['year'];h=item['horizon']
        cutoff=utc_time(manifest['cutoff']);assert cutoff.isoformat()==f'{year}-01-02T12:00:00+00:00';entry=session_times(f'{year}-01-02').entry
        assert item['training_start']=='2023-10-26'
        assert item['training_end']==('2023-12-29' if year==2024 else '2024-12-31')
        assert min(r['decision_at'][:10] for r in rows)=='2023-10-26'
        assert len(manifest['included'])==(44-h)*3 if year==2024 else len(manifest['included'])>600
        assert len(item['omissions'])==item['training_sessions']*9
        included={e['index'] for e in manifest['included']}
        excluded={e['index'] for e in manifest['excluded']}
        assert included.isdisjoint(excluded) and included|excluded==set(range(len(rows)))
        assert len(excluded)==3*(h+1)
        for i in included:
            row=rows[i]
            assert utc_time(row['decision_at'])<cutoff
            assert utc_time(row['label_end_at'])<entry
            assert utc_time(row['simulated_feature_available_at'])<=utc_time(row['decision_at'])
            assert all(utc_time(row[f])<=cutoff for f in ('simulated_feature_available_at','simulated_label_available_at','simulated_revision_available_at'))
        assert all('SAME_DATE_PURGE' in r['reasons'] for r in manifest['excluded'])
        assert item['model']['observations']==len(included)


def test_generated_coefficients_match_independent_normal_equations(fitted):
    from compertum.modeling.registry import variant
    report=json.loads(fitted.content)
    for item in report['fits']:
        model=item['model'];selected=[item['rows'][r['index']] for r in item['manifest']['included']]
        x=np.array([r['features'] for r in selected]);y=np.array([r['target'] for r in selected])
        mean=x.mean(axis=0);scale=x.std(axis=0);scale[scale==0]=1
        z=(x-mean)/scale;alpha=variant(item['candidate_id']).alpha
        coef=np.linalg.solve(z.T@z+alpha*np.eye(x.shape[1]),z.T@(y-y.mean()))
        assert model['scaler']['mean']==pytest.approx(mean,rel=1e-11,abs=1e-12)
        assert model['scaler']['scale']==pytest.approx(scale,rel=1e-11,abs=1e-12)
        assert model['ridge']['coef']==pytest.approx(coef,rel=1e-9,abs=1e-11)
        assert model['ridge']['intercept']==pytest.approx(y.mean(),rel=1e-10,abs=1e-12)
        # Hand label from the fixed arithmetic price recipe.
        for row in selected[::max(1,len(selected)//7)]:
            day=row['decision_at'][:10];end=row['label_end_at'][:10]
            dates=report['market']['sessions'];j=recipe()['symbols'].index(row['symbol'])+1
            start_price=80+dates.index(day)*j/20;end_price=80+dates.index(end)*j/20
            assert row['target']==pytest.approx(end_price/start_price-1,rel=1e-11,abs=1e-12)


@pytest.mark.parametrize('candidates',[(),('ridge-h01-a001','ridge-h01-a010'),('invented',),('momentum-h01',)*4])
def test_generated_fit_selection_remains_bounded(candidates):
    with pytest.raises(DataError):prepare_generated_fits(canonical(recipe()),expected_sha256=recipe_hash(),candidate_ids=candidates)


def test_shared_partition_purges_all_assets_when_one_revision_is_late():
    from test_ridge import row
    from compertum.modeling.ridge import _partition_rows
    from compertum.modeling.registry import _calendar_cutoff
    cutoff=_calendar_cutoff(2025)
    a=row('2024-11-01',1,2);b=row('2024-11-01',2,3,symbol='MSFT')
    a['simulated_revision_available_at']=(cutoff+timedelta(seconds=1)).isoformat()
    included,excluded=_partition_rows([a,b],cutoff)
    assert not included and len(excluded)==2
    assert all('SIMULATED_REVISION_AVAILABLE_AT_AFTER_CUTOFF' in r['reasons'] and 'SAME_DATE_PURGE' in r['reasons'] for r in excluded)


def test_generated_rows_cannot_enter_public_development_fitting(fitted):
    from compertum.modeling.ridge import freeze_rows,prepare_fit
    from compertum.modeling.registry import FEATURES
    future=next(f for f in json.loads(fitted.content)['fits'] if f['year']==2025)
    with pytest.raises(DataError,match='DEVELOPMENT_ROWS_ONLY'):
        freeze_rows(future['rows'],horizon=future['horizon'],feature_names=FEATURES)
