import json
from decimal import Decimal as D,localcontext,ROUND_UP,Inexact
import pytest
from compertum.data.calendar import session_times
from compertum.data.errors import DataError
from compertum.simulation.prediction import score_predictions,error_metrics,rank_correlation
from helpers.simulation_fixture import fixture,changed,with_action,SECTORS


def cutoff(day):return session_times(session_times(day).next_date).decision.isoformat()


def test_error_metrics_hand_calculations_and_zero_baseline():
    m=error_metrics([D('.1'),D('-.1')],[D('.2'),D('-.2')])
    assert D(m['mse'])==D('.01') and D(m['mae'])==D('.1')
    assert D(m['mean_signed_error'])==0 and D(m['zero_mse'])==D('.04')
    assert D(m['mse_improvement'])==D('.75')
    assert error_metrics([D('.1')],[D(0)])['mse_improvement'] is None
    assert error_metrics([],[])['mse'] is None


def test_tied_rank_correlations_and_undefined_cases():
    assert rank_correlation([D(1),D(1),D(3)],[D(2),D(2),D(4)])=='1'
    assert rank_correlation([D(1),D(2),D(3)],[D(3),D(2),D(1)])=='-1'
    assert rank_correlation([D(1),D(1)],[D(1),D(2)]) is None
    assert rank_correlation([D(1)],[D(2)]) is None


@pytest.mark.parametrize('h',[1,5,21])
def test_horizon_timestamps_targets_and_coverage(h):
    chunks,start,end,dates=fixture(scored=23)
    value=json.loads(score_predictions(chunks,SECTORS,start,end,h,scoring_as_of=cutoff(end)).content)
    assert value['financial_status']=='SYNTHETIC_UNVERIFIED'
    first=value['rows'][0]
    assert first['decision_at']==session_times(start).decision.isoformat()
    assert first['entry_at']==session_times(start).entry.isoformat()
    assert first['exit_at']==session_times(dates[252+h]).entry.isoformat()
    assert first['label_available_at']==cutoff(dates[252+h])
    assert D(first['target'])==0 and D(first['prediction'])==D(h)*D('.25')/21
    assert value['coverage']=={'candidate_rows':69,'feature_eligible_rows':69,'eligible_rows':(23-h)*3,'scored_rows':(23-h)*3,'omitted_rows':h*3}
    assert len(value['daily_rank_correlation'])==23
    assert sum(r['observations']>0 for r in value['daily_rank_correlation'])==23-h


def test_price_label_adjusts_splits_and_excludes_dividends():
    chunks,start,end,dates=fixture(scored=8)
    a=score_predictions(chunks,SECTORS,start,end,5,scoring_as_of=cutoff(end))
    split=score_predictions(with_action(chunks,dates[254],kind='SPLIT'),SECTORS,start,end,5,scoring_as_of=cutoff(end))
    dividend=score_predictions(with_action(chunks,dates[254]),SECTORS,start,end,5,scoring_as_of=cutoff(end))
    for result in (a,split,dividend):assert all(D(r['target'])==0 for r in json.loads(result.content)['rows'])


def test_late_label_is_omitted_then_available_without_backdating():
    chunks,start,end,dates=fixture(scored=8);late='2026-10-09T00:00:00Z'
    def edit(v):
        for b in v['bars']:
            if b['asset_id']=='AAPL' and b['reference']=='entry' and b['session_date']==dates[257]:b['simulated_revision_available_at']=late
    chunks=changed(chunks,edit)
    early=json.loads(score_predictions(chunks,SECTORS,start,end,5,scoring_as_of=cutoff(end)).content)
    assert any(r['reason']=='LABEL_UNAVAILABLE' and r['symbol']=='AAPL' for r in early['omissions'])
    later=json.loads(score_predictions(chunks,SECTORS,start,end,5,scoring_as_of=late).content)
    row=next(r for r in later['rows'] if r['session']==start and r['symbol']=='AAPL')
    assert row['label_available_at']==late.replace('Z','+00:00')
    assert D(row['target'])==0


def test_entry_minute_open_not_close_and_future_features_not_used():
    chunks,start,end,dates=fixture(scored=8)
    def edit(v):
        for b in v['bars']:
            if b['asset_id']=='AAPL' and b['reference']=='entry' and b['session_date']==dates[257]:
                b.update(open='110',high='120',low='100',close='120')
    scored=json.loads(score_predictions(changed(chunks,edit),SECTORS,start,end,5,scoring_as_of=cutoff(end)).content)
    row=next(r for r in scored['rows'] if r['symbol']=='AAPL' and r['session']==start)
    assert D(row['target'])==D('.1') and D(row['prediction'])==D(5)*D('.25')/21


def test_no_eligible_features_and_boundary_rows_are_not_zero_labels():
    chunks,start,end,dates=fixture(scored=3)
    def edit(v):
        for b in v['bars']:
            if b['reference']=='daily':b['simulated_revision_available_at']='2026-10-09T00:00:00Z'
    value=json.loads(score_predictions(changed(chunks,edit),SECTORS,start,end,1,scoring_as_of=cutoff(end)).content)
    assert value['rows']==[] and value['metrics']['mse'] is None
    assert value['coverage']['omitted_rows']==9


def test_exact_reproduction_under_hostile_decimal_context():
    chunks,start,end,_=fixture(scored=8)
    a=score_predictions(chunks,SECTORS,start,end,5,scoring_as_of=cutoff(end))
    with localcontext() as ctx:
        ctx.prec=3;ctx.rounding=ROUND_UP;ctx.traps[Inexact]=True
        b=score_predictions(tuple(reversed(chunks)),SECTORS,start,end,5,scoring_as_of=cutoff(end))
    assert a==b


def test_scoring_before_decision_never_creates_future_rows():
    chunks,start,end,_=fixture(scored=3)
    value=json.loads(score_predictions(chunks,SECTORS,start,end,1,scoring_as_of='2020-01-01T00:00:00Z').content)
    assert value['coverage']['eligible_rows']==0 and value['rows']==[]
    assert {r['reason'] for r in value['omissions']}=={'DECISION_UNAVAILABLE'}


def test_missing_exit_reference_is_an_omission_not_zero_label():
    chunks,start,end,dates=fixture(scored=8)
    def edit(v):
        if v['assets'][0]['symbol']=='AAPL' and dates[256] in v['feature_sessions']:
            v['feature_sessions'].remove(dates[256])
            v['bars']=[b for b in v['bars'] if not (b['session_date']==dates[256] and b['reference']!='entry') and not (b['session_date']==dates[257] and b['reference']=='entry')]
    value=json.loads(score_predictions(changed(chunks,edit),SECTORS,start,end,5,scoring_as_of=cutoff(end)).content)
    assert {'session':start,'symbol':'AAPL','reason':'LABEL_REFERENCE_MISSING'} in value['omissions']
    assert not any(r['session']==start and r['symbol']=='AAPL' for r in value['rows'])


def test_split_effective_on_exit_counts_and_entry_day_split_does_not():
    chunks,start,end,dates=fixture(scored=8)
    for date in (start,dates[257]):
        value=json.loads(score_predictions(with_action(chunks,date,kind='SPLIT'),SECTORS,start,end,5,scoring_as_of=cutoff(end)).content)
        row=next(r for r in value['rows'] if r['symbol']=='AAPL' and r['session']==start)
        assert D(row['target'])==0
        assert row['split_actions']==(['action-fixture-1'] if date!=start else [])


def test_action_knowledge_controls_label_availability_not_earlier_features():
    chunks,start,end,dates=fixture(scored=8);late='2026-10-09T00:00:00Z'
    chunks=with_action(chunks,dates[254],kind='SPLIT',known=late)
    early=json.loads(score_predictions(chunks,SECTORS,start,end,5,scoring_as_of=cutoff(end)).content)
    assert {'session':start,'symbol':'AAPL','reason':'LABEL_UNAVAILABLE'} in early['omissions']
    later=json.loads(score_predictions(chunks,SECTORS,start,end,5,scoring_as_of=late).content)
    row=next(r for r in later['rows'] if r['symbol']=='AAPL' and r['session']==start)
    assert D(row['prediction'])==D(5)*D('.25')/21 and D(row['target'])==0


@pytest.mark.parametrize('bad',[D('NaN'),D('Infinity'),'1',D('1e100')])
def test_invalid_numeric_metrics_rejected(bad):
    with pytest.raises(DataError,match='INVALID_PREDICTION_NUMBER'):error_metrics([bad],[D(0)])


def test_metric_bounds_mismatch_and_invalid_horizon():
    with pytest.raises(DataError,match='INVALID_PREDICTION_ROWS'):error_metrics([D(0)],[])
    with pytest.raises(DataError,match='INVALID_PREDICTION_ROWS'):rank_correlation([D(0)]*12289,[D(0)]*12289)
    chunks,start,end,_=fixture(scored=3)
    for h in (0,2,True):
        with pytest.raises(DataError,match='INVALID_PROTOCOL'):score_predictions(chunks,SECTORS,start,end,h,scoring_as_of=cutoff(end))


@pytest.mark.parametrize('h',[1,5,21])
def test_full_watchlist_and_daily_coverage(h):
    from compertum.simulation.market import WATCHLIST
    symbols=WATCHLIST+('SPY',);chunks,start,end,_=fixture(symbols,scored=23)
    sectors={s:'fixture-'+str(i//2) for i,s in enumerate(symbols)}
    value=json.loads(score_predictions(chunks,sectors,start,end,h,scoring_as_of=cutoff(end)).content)
    assert value['coverage']['candidate_rows']==23*12
    assert value['coverage']['scored_rows']==(23-h)*12


def test_short_horizon_reports_no_eligible_labels_and_explicit_daily_nulls():
    chunks,start,end,_=fixture(scored=3)
    value=json.loads(score_predictions(chunks,SECTORS,start,end,5,scoring_as_of=cutoff(end)).content)
    assert value['coverage']['feature_eligible_rows']==9 and value['coverage']['eligible_rows']==0
    assert len(value['daily_rank_correlation'])==3
    assert all(r['observations']==0 and r['spearman'] is None and r['status']=='NO_SCORED_ROWS' for r in value['daily_rank_correlation'])


def test_tiny_metric_input_cannot_underflow_into_zero_error():
    with pytest.raises(DataError,match='INVALID_PREDICTION_NUMBER'):error_metrics([D(0)],[D('1e-600000')])
