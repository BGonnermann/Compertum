"""Feature checks against retained synthetic raw prices and explicit timing."""
import copy,math
from datetime import timedelta
import numpy as np
import pytest
from compertum.data.calendar import session_times
from compertum.data.errors import DataError
from compertum.modeling.features import feature_vector
from compertum.modeling.registry import FEATURES
from compertum.simulation.market import load_market
from helpers.simulation_fixture import fixture,SECTORS,with_action


def market():
    chunks,start,end,dates=fixture()
    return load_market(chunks,SECTORS),start,dates


def test_fixed_feature_order_and_hand_values():
    m,day,_=market();r=feature_vector(m,'AAPL',day)
    expected=[0,0,.25,.25,math.sqrt(252*.25**2/20),math.sqrt(252*.25**2/63),100/91-1,100/(5260/63)-1,1,0,0,0,0,0,0]
    assert r.names==FEATURES and r.values==pytest.approx(expected,rel=1e-12,abs=1e-12)
    assert r.feature_session==session_times(day).previous_date
    assert r.decision_at==session_times(day).decision.isoformat()
    assert r.available_at==r.decision_at and r.availability_basis=='SIMULATED_AVAILABILITY'
    assert r.raw_eligible and r.raw_close==100 and r.raw_mean_dollar_volume_20==1820000
    assert r.financial_accepted is False


def test_split_correction_preserves_scale_invariant_features():
    chunks,day,_,dates=fixture();normal=feature_vector(load_market(chunks,SECTORS),'AAPL',day)
    changed=with_action(chunks,dates[240],kind='SPLIT');adjusted=feature_vector(load_market(changed,SECTORS),'AAPL',day)
    assert adjusted.values==pytest.approx(normal.values,rel=1e-12,abs=1e-12)
    assert adjusted.raw_close==50 and adjusted.raw_mean_dollar_volume_20==normal.raw_mean_dollar_volume_20
    assert adjusted.input_sha256!=normal.input_sha256


def test_future_split_and_raw_rows_cannot_rewrite_prior_vector():
    chunks,day,_,dates=fixture();normal=feature_vector(load_market(chunks,SECTORS),'AAPL',day)
    future=load_market(with_action(chunks,dates[260],kind='SPLIT'),SECTORS)
    for (symbol,date,kind),r in future.rows.items():
        if date>=day:
            r['close']='1000000';r['volume']='1000000'
    changed=feature_vector(future,'AAPL',day)
    assert changed.values==normal.values and changed.input_sha256==normal.input_sha256


@pytest.mark.parametrize('symbol',['AAPL','SPY'])
@pytest.mark.parametrize('field',['simulated_available_at','simulated_revision_available_at'])
def test_future_feature_or_revision_refused(symbol,field):
    m,day,_=market();m=copy.deepcopy(m);previous=session_times(day).previous_date
    m.rows[(symbol,previous,'daily')][field]=(session_times(day).decision+timedelta(seconds=1)).isoformat()
    with pytest.raises(DataError,match='FEATURE_UNAVAILABLE'):feature_vector(m,'AAPL',day)


@pytest.mark.parametrize('symbol',['AAPL','SPY'])
def test_missing_warmup_row_refused_even_outside_short_features(symbol):
    m,day,dates=market();m=copy.deepcopy(m);del m.rows[(symbol,dates[0],'daily')]
    with pytest.raises(DataError,match='FEATURE_COVERAGE'):feature_vector(m,'AAPL',day)


def test_late_applied_split_is_not_used():
    chunks,day,_,dates=fixture();known=(session_times(day).decision+timedelta(seconds=1)).isoformat()
    m=load_market(with_action(chunks,dates[240],kind='SPLIT',known=known),SECTORS)
    with pytest.raises(DataError,match='ACTION_UNAVAILABLE'):feature_vector(m,'AAPL',day)


def test_later_correction_changes_digest_without_mutating_input():
    m,day,_=market();m=copy.deepcopy(m);before=feature_vector(m,'AAPL',day)
    previous=session_times(day).previous_date;m.rows[('AAPL',previous,'daily')]['revision_id']='v2'
    old=copy.deepcopy(m.rows);after=feature_vector(m,'AAPL',day)
    assert after.values==before.values and after.input_sha256!=before.input_sha256 and m.rows==old


@pytest.mark.parametrize('field,value',[('close','0'),('close','NaN'),('close','Infinity'),('close','-1'),('volume','-1'),('volume','NaN')])
def test_invalid_raw_values_refused(field,value):
    m,day,_=market();m=copy.deepcopy(m);m.rows[('AAPL',session_times(day).previous_date,'daily')][field]=value
    with pytest.raises(DataError):feature_vector(m,'AAPL',day)


def test_zero_volume_denominator_refused():
    m,day,_=market();m=copy.deepcopy(m)
    for (symbol,date,kind),r in m.rows.items():
        if symbol=='AAPL' and kind=='daily':r['volume']='0'
    with pytest.raises(DataError,match='NONPOSITIVE_DENOMINATOR'):feature_vector(m,'AAPL',day)


def test_raw_eligibility_is_separate_from_adjusted_feature_values():
    chunks,day,_,dates=fixture();m=load_market(with_action(chunks,dates[240],kind='SPLIT',factor='100'),SECTORS)
    r=feature_vector(m,'AAPL',day)
    assert not r.raw_eligible and r.raw_close==1 and r.values[2]==pytest.approx(.25)


def test_spy_reference_is_aligned_and_has_own_split_correction():
    m,day,dates=market();m=copy.deepcopy(m);effective=dates[240]
    for (symbol,date,kind),r in m.rows.items():
        if symbol=='SPY' and kind=='daily' and date>=effective:r['close']='50';r['volume']='40000'
    m.actions=tuple(m.actions)+({'symbol':'SPY','kind':'SPLIT','effective_session':effective,'factor':'2','simulated_known_at':'2020-01-01T00:00:00Z','action_id':'spy-split'},)
    assert feature_vector(m,'AAPL',day).values[9:]==pytest.approx([0]*6)
