"""Independent numeric oracles and fail-closed synthetic qualification contracts."""
import base64
from dataclasses import replace
from decimal import Decimal as D,localcontext,ROUND_UP,Inexact
import hashlib,json,math
import numpy as np
import pytest
from compertum.data.calendar import session_times
from compertum.data.errors import DataError
from compertum.data.encoding import canonical
from compertum.simulation.metrics import metrics
from compertum.modeling.qualification import (QualificationInput,HoldingInterval,EvaluationSegment,PredictionRow,
    bootstrap_excess,qualify_synthetic,_draw_means)


def dates(n=None):
    result=['2024-01-02']
    while result[-1]!='2025-12-31' and (n is None or len(result)<n):
        result.append(session_times(result[-1]).next_date)
    return tuple(result)


def nav(returns):
    values=[D(10000)]
    for r in returns:values.append(values[-1]*(1+r))
    return tuple(values)


def fixture(n=None,mode='HISTORICAL',candidate='momentum-h01'):
    days=dates(n);h=int(candidate.split('-h')[1][:2]);n=len(days)
    boundaries=[0]+([i for i in range(1,n) if days[i][:4]!=days[i-1][:4]] if mode=='HISTORICAL' else [])+[n]
    segments=tuple(EvaluationSegment(a,b-1,a) for a,b in zip(boundaries,boundaries[1:]))
    points=tuple(i for s in segments for i in range(s.anchor,s.end+1,h))
    intervals=tuple(HoldingInterval(symbol,i,i+h) for i in points[:10] for symbol in ('AAPL','MSFT','AMZN') if any(s.start<=i<i+h<=s.end for s in segments))
    positive=nav([D('.001') if i%2 else D('.002') for i in range(n)]);cash=(D(10000),)*(n+1)
    return QualificationInput('a'*64,candidate,mode,days,positive,cash,positive,cash,segments,points,intervals)


def read(value):return json.loads(qualify_synthetic(value).content)


def test_independent_nav_arithmetic():
    got=metrics([D(10000),D(11000),D(9900)],[D(10000)]*3)
    assert got['returns']==['0.1','-0.1']
    assert D(got['annual_mean_excess'])==D(0) and D(got['sharpe'])==D(0)
    assert D(got['max_drawdown'])==D('.1')


def test_known_wrapping_and_truncation():
    starts=np.tile(np.array([[20,7]],dtype=np.int64),(10000,1))
    means=_draw_means(np.arange(22,dtype=np.float64),starts)
    # 20+21+(0+...+18)+7=219; only first entry from second block survives.
    assert np.all(means==219/22)


def test_bootstrap_independent_indices_means_and_linear_quantile():
    r=tuple(D(i%7-3)/1000 for i in range(43));b=tuple(D(i%3-1)/1000 for i in range(43))
    result=bootstrap_excess(r,b);v=json.loads(result.content)
    assert hashlib.sha256(result.content).hexdigest()==result.sha256
    raw=base64.b64decode(v['indices']['base64'],validate=True)
    assert hashlib.sha256(raw).hexdigest()==v['indices']['sha256']
    assert v['indices']['shape']==[10000,3] and len(raw)==60000
    starts=np.frombuffer(raw,dtype='<u2').reshape(10000,3)
    expected_starts=np.random.Generator(np.random.PCG64(1731)).integers(0,43,size=(10000,3),dtype=np.int64)
    assert np.array_equal(starts,expected_starts)
    excess=[float(x-y) for x,y in zip(r,b)]
    oracle=[]
    for row in starts:
        path=[(int(start)+offset)%43 for start in row for offset in range(21)][:43]
        oracle.append(math.fsum(excess[i] for i in path)/43)
    means=[float.fromhex(x) for x in v['draw_means_hex']]
    assert np.allclose(means,oracle,atol=1e-18,rtol=1e-14)
    ordered=sorted(means);position=(10000-1)*(.05/12);lo=math.floor(position)
    expected=ordered[lo]+(position-lo)*(ordered[lo+1]-ordered[lo])
    assert lo==41 and position-lo==pytest.approx(.6625)
    assert float(v['lower_daily'])==pytest.approx(expected,abs=1e-18)
    assert float(v['lower_annual'])==252*float(v['lower_daily'])
    assert v['draws']==10000 and v['block_sessions']==21 and v['family_size']==12
    assert v['seed']==1731 and v['numpy_version']==np.__version__
    assert v['coverage']=='APPROXIMATE_NOT_GUARANTEED'
    assert bootstrap_excess(r,b)==result


def test_paired_common_noise_and_strict_zero_bound():
    common=tuple(D(i%9-4)/100 for i in range(43));r=tuple(x+D('.001') for x in common)
    v=json.loads(bootstrap_excess(r,common).content)
    assert all(float.fromhex(x)==pytest.approx(.001,abs=1e-18) for x in v['draw_means_hex'])
    assert float(v['lower_daily'])==pytest.approx(.001) and v['positive_bound']
    zero=json.loads(bootstrap_excess(common,common).content)
    assert zero['lower_daily']=='0.0' and not zero['positive_bound']


def test_maximum_bootstrap_evidence_is_bounded():
    v=bootstrap_excess((D('.001'),)*1024,(D(0),)*1024)
    parsed=json.loads(v.content)
    assert len(base64.b64decode(parsed['indices']['base64']))==980000
    assert len(v.content)<2*1024**2


@pytest.mark.parametrize('strategy,benchmark',[
    ((),()),((D(0),),(D(0),D(0))),([D(0)],(D(0),)),((True,),(D(0),)),
    ((D('NaN'),),(D(0),)),((D('Infinity'),),(D(0),)),((D(-1),),(D(0),)),
    ((D('.01'),)*1025,(D(0),)*1025),((D('1e-100'),),(D(0),)),((D('1e1000000'),),(D(0),)),
])
def test_bootstrap_rejects_invalid_input(strategy,benchmark):
    with pytest.raises(DataError):bootstrap_excess(strategy,benchmark)


def test_full_positive_fixture_never_grants_financial_authority():
    v=read(fixture())
    assert v['trading_arithmetic_pass'] and all(v['numeric_gates'].values())
    assert v['status']=='SYNTHETIC_ENGINEERING' and not v['financial_accepted']
    assert not v['paper_eligible'] and not v['strategy_accepted']
    assert set(v['external_gates'].values())=={'UNVERIFIED'}
    assert v['ml_contribution_gate']=='NOT_APPLICABLE'
    assert hashlib.sha256(canonical(v['inputs'])).hexdigest()==v['input_sha256']
    assert hashlib.sha256(canonical(v['bootstrap'])).hexdigest()==v['bootstrap_sha256']


@pytest.mark.parametrize('n,passes',[(399,False),(400,True)])
def test_daily_threshold_does_not_excuse_incomplete_calendar(n,passes):
    v=read(fixture(n));assert v['numeric_gates']['daily_observations']==passes
    assert not v['numeric_gates']['complete_window'] and not v['trading_arithmetic_pass']


@pytest.mark.parametrize('count,passes',[(11,False),(12,True)])
def test_checkpoint_threshold(count,passes):
    value=fixture(252,'FORWARD');anchor=252-count;points=tuple(range(anchor,252))
    intervals=tuple(HoldingInterval(symbol,i,i+1) for i in points[:10] for symbol in ('AAPL','MSFT','AMZN'))
    v=read(replace(value,segments=(EvaluationSegment(0,251,anchor),),checkpoints=points,intervals=intervals))
    assert v['numeric_gates']['scheduled_checkpoints']==passes


@pytest.mark.parametrize('count,passes',[(29,False),(30,True)])
def test_interval_threshold(count,passes):
    value=fixture();v=read(replace(value,intervals=value.intervals[:count]))
    assert v['numeric_gates']['completed_holding_intervals']==passes


def test_cash_and_zero_variance_fail_without_threshold_changes():
    value=fixture();cash=value.benchmark
    v=read(replace(value,navs=cash,stress_navs=cash))
    assert v['metrics']['sharpe'] is None
    assert not v['numeric_gates']['sharpe'] and not v['numeric_gates']['confidence_lower_bound']
    assert not v['trading_arithmetic_pass']
    two=metrics([D(10000),D(10010),D('10020.01')],[D(10000)]*3)
    assert two['sharpe'] is None


def test_historical_year_boundary_has_no_nav_reset():
    value=fixture();r=[D('.003') if d[:4]=='2024' else D('-.001') for d in value.sessions]
    v=read(replace(value,navs=nav(r)))
    assert D(v['metrics']['annual_mean_excess'])>0
    assert D(v['period_mean_daily_excess']['2025'])==pytest.approx(D('-.001'),abs=D('1e-25'))
    assert not v['numeric_gates']['period_excess']


def test_stress_failure_is_independent_and_cost_matched():
    value=fixture();n=len(value.sessions)
    v=read(replace(value,stress_benchmark=nav([D('.003')]*n)))
    assert v['numeric_gates']['annual_mean_excess'] and not v['numeric_gates']['stress_excess']
    damaged=(D(10000),D(7900))+(D(7900),)*(n-1)
    v=read(replace(value,stress_navs=damaged))
    assert not v['numeric_gates']['stress_drawdown']


def test_forward_exact_halves_and_unchanged_count_gates():
    value=fixture(252,'FORWARD');v=read(value)
    assert v['trading_arithmetic_pass']
    negative_second=nav([D('.003')]*126+[D('-.001')]*126)
    v=read(replace(value,navs=negative_second))
    assert D(v['metrics']['annual_mean_excess'])>0 and not v['numeric_gates']['period_excess']
    assert set(v['period_mean_daily_excess'])=={'first_126','second_126'}


@pytest.mark.parametrize('n',[251,253])
def test_forward_does_not_select_or_truncate_a_window(n):
    with pytest.raises(DataError):qualify_synthetic(fixture(n,'FORWARD'))


@pytest.mark.parametrize('prediction,gate',[(D(1),'PASS'),(D('.5'),'FAIL')])
def test_ridge_one_percent_gate_separate_from_trading(prediction,gate):
    value=fixture(candidate='ridge-h01-a001')
    rows=tuple(PredictionRow(d,'AAPL',prediction if i==0 else D(0),D(0),D(1)) for i,d in enumerate(value.sessions[:100]))
    v=read(replace(value,predictions=rows));assert v['ml_contribution_gate']==gate
    assert v['trading_arithmetic_pass'] and D(v['prediction']['zero_mse'])==1
    assert D(v['prediction']['mse_improvement'])==(D('.01') if prediction==1 else D('.0075'))


def test_zero_prediction_baseline_is_undefined_not_pass():
    value=fixture(candidate='ridge-h01-a001')
    row=PredictionRow(value.sessions[0],'AAPL',D(0),D(0),D(0))
    v=read(replace(value,predictions=(row,)))
    assert v['ml_contribution_gate']=='UNDEFINED' and v['prediction']['mse_improvement'] is None
    assert v['trading_arithmetic_pass']


@pytest.mark.parametrize('change',[
    lambda v:replace(v,protocol_sha256='x'*64),lambda v:replace(v,mode='PAPER_ELIGIBLE'),
    lambda v:replace(v,sessions=v.sessions[::-1]),lambda v:replace(v,sessions=v.sessions[1:]),
    lambda v:replace(v,navs=(D(0),)+v.navs[1:]),lambda v:replace(v,navs=(D(10001),)+v.navs[1:]),
    lambda v:replace(v,navs=(D(10000),D('NaN'))+v.navs[2:]),
    lambda v:replace(v,benchmark=v.benchmark[:-1]),lambda v:replace(v,stress_navs=v.stress_navs[:-1]),
    lambda v:replace(v,checkpoints=(False,1,2,3)),lambda v:replace(v,checkpoints=(0,0,1,2,3)),
    lambda v:replace(v,intervals=v.intervals+(v.intervals[0],)),
    lambda v:replace(v,intervals=(HoldingInterval('AAPL',0,len(v.sessions)),)),
    lambda v:replace(v,intervals=(HoldingInterval('SPY',0,1),)),
    lambda v:replace(v,intervals=(HoldingInterval('AAPL',True,2),)),
    lambda v:replace(v,intervals=(HoldingInterval('AAPL',0,2),)),
    lambda v:replace(v,predictions=(PredictionRow(v.sessions[0],'AAPL',D('Infinity'),D(0),D(1)),)),
    lambda v:replace(v,predictions=(PredictionRow(v.sessions[0],'AAPL',D(0),D(0),D(1)),)*2),
])
def test_invalid_evidence_is_rejected(change):
    with pytest.raises(DataError):qualify_synthetic(change(fixture()))


def test_horizon21_retains_same_evidence_thresholds():
    v=read(fixture(candidate='momentum-h21'));assert v['trading_arithmetic_pass']


def test_decimal_ambient_context_cannot_change_results():
    value=fixture();expected=qualify_synthetic(value)
    with localcontext() as ctx:
        ctx.prec=9;ctx.rounding=ROUND_UP;ctx.traps[Inexact]=True
        assert qualify_synthetic(value)==expected

@pytest.mark.parametrize('loss,passed',[(D('.15'),True),(D('.1500001'),False)])
def test_base_drawdown_boundary_is_inclusive(loss,passed):
    value=fixture(252,'FORWARD');series=(D(10000),)+(D(10000)*(1-loss),)*252
    v=read(replace(value,navs=series));assert v['numeric_gates']['max_drawdown']==passed


@pytest.mark.parametrize('loss,passed',[(D('.20'),True),(D('.2000001'),False)])
def test_stress_drawdown_boundary_is_inclusive(loss,passed):
    value=fixture(252,'FORWARD');series=(D(10000),)+(D(10000)*(1-loss),)*252
    v=read(replace(value,stress_navs=series));assert v['numeric_gates']['stress_drawdown']==passed


@pytest.mark.parametrize('single_return,passed',[(D('.02'),True),(D('.0199999'),False)])
def test_annual_arithmetic_excess_boundary_is_inclusive(single_return,passed):
    value=fixture(252,'FORWARD');series=(D(10000),)+(D(10000)*(1+single_return),)*252
    v=read(replace(value,navs=series));assert v['numeric_gates']['annual_mean_excess']==passed
    assert D(v['metrics']['annual_mean_excess'])==single_return


def test_zero_year_and_zero_stress_excess_are_inclusive():
    value=fixture();r=[D('.001') if day[:4]=='2024' else D(0) for day in value.sessions]
    v=read(replace(value,navs=nav(r),stress_navs=value.stress_benchmark))
    assert v['numeric_gates']['period_excess'] and v['numeric_gates']['stress_excess']
    assert v['period_mean_daily_excess']['2025']=='0'


def test_annual_horizon5_schedule_restarts_at_year_boundary():
    value=fixture(candidate='momentum-h05');boundary=value.sessions.index('2025-01-02')
    assert boundary==252 and boundary in value.checkpoints and boundary%5!=0
    assert read(value)['trading_arithmetic_pass']


def test_boundary_crossing_holding_is_not_a_full_interval():
    value=fixture(candidate='momentum-h01');boundary=value.sessions.index('2025-01-02')
    # Both endpoints are otherwise in range; this holding crosses annual segments.
    with pytest.raises(DataError):qualify_synthetic(replace(value,intervals=(HoldingInterval('AAPL',boundary-1,boundary),)))


def test_no_eligible_anchor_and_impossible_four_names():
    value=fixture(252,'FORWARD')
    empty=replace(value,segments=(EvaluationSegment(0,251,None),),checkpoints=(),intervals=())
    v=read(empty);assert not v['numeric_gates']['scheduled_checkpoints'] and not v['numeric_gates']['completed_holding_intervals']
    with pytest.raises(DataError):qualify_synthetic(replace(value,intervals=value.intervals+(HoldingInterval('XOM',0,1),)))


@pytest.mark.parametrize('target',[D(-1),D(-2)])
def test_impossible_price_labels_are_rejected(target):
    value=fixture();row=PredictionRow(value.sessions[0],'AAPL',D(0),D(0),target)
    with pytest.raises(DataError):qualify_synthetic(replace(value,predictions=(row,)))


def test_momentum_candidate_cannot_disagree_with_its_comparator():
    value=fixture();row=PredictionRow(value.sessions[0],'AAPL',D(1),D(0),D('.1'))
    with pytest.raises(DataError):qualify_synthetic(replace(value,predictions=(row,)))


def test_linear_quantile_interpolation_with_distinct_adjacent_draws(monkeypatch):
    # Distinct means isolate the predeclared quantile convention from sampling ties.
    draws=np.arange(10000,dtype=np.float64)
    monkeypatch.setattr('compertum.modeling.qualification._draw_means',lambda *_:draws)
    v=json.loads(bootstrap_excess((D('.01'),),(D(0),)).content)
    assert float(v['lower_daily'])==pytest.approx(41.6625,abs=1e-13)


def test_analytical_sharpe_boundary():
    # 252 observations with mean m and sample variance 448*m*m give Sharpe3/4.
    value=fixture(252,'FORWARD');m=D('.00001')
    deviations=[228,-228,44,-44,48,-48]+[0]*246
    assert sum(deviations)==0 and sum(d*d for d in deviations)==251*448
    with localcontext() as ctx:
        ctx.prec=5000
        series=nav([m*(1+d) for d in deviations])
    v=read(replace(value,navs=series))
    assert abs(D(v['metrics']['sharpe'])-D('.75'))<=D('1e-26')
    assert v['numeric_gates']['sharpe']


@pytest.mark.parametrize('shift,passed',[(D('1e-12'),True),(D('-1e-12'),False)])
def test_sharpe_gate_either_side_has_no_added_tolerance(shift,passed):
    value=fixture(252,'FORWARD');m=D('.00001');deviations=[228,-228,44,-44,48,-48]+[0]*246
    with localcontext() as ctx:
        ctx.prec=5000;series=nav([m*(1+d)+shift for d in deviations])
    v=read(replace(value,navs=series));assert v['numeric_gates']['sharpe']==passed


def test_squared_sharpe_gate_does_not_admit_negative_mean():
    value=fixture(252,'FORWARD')
    negative=nav([D('-.001') if i%2 else D('-.002') for i in range(252)])
    v=read(replace(value,navs=negative))
    assert D(v['metrics']['sharpe'])<0 and not v['numeric_gates']['sharpe']
