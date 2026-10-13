import json
from decimal import Decimal as D, localcontext
import pytest

from compertum.data.errors import DataError
from compertum.simulation import replay
from compertum.simulation.policy import buy_quantity
from compertum.simulation.metrics import metrics
from helpers.simulation_fixture import fixture,changed,with_action,SECTORS
from compertum.simulation.policy import qualifies


def run(h=1,**kwargs):
    chunks,start,end,_=fixture()
    return json.loads(replay(chunks,SECTORS,start,end,h,**kwargs).content)


def test_hand_sizing_and_buffer():
    assert buy_quantity(D('2000'),D('100'),D('.001'))==19
    assert buy_quantity(D('100'),D('100'),D('.001'))==0


@pytest.mark.parametrize('h',[1,5,21])
def test_all_horizons_hand_cash_costs_and_schedule(h):
    value=run(h);p=value['portfolios']['momentum'];trades=p['trades']
    assert value['financial_status']=='SYNTHETIC_UNVERIFIED'
    assert [(x['symbol'],x['quantity']) for x in trades[:3]]==[('AAPL',19),('JPM',19),('MSFT',19)]
    assert D(p['days'][0]['cash'])==D('4294.3')
    assert D(p['days'][0]['nav'])==D('9994.3')
    assert p['days'][-1]['positions']=={}
    assert D(p['days'][-1]['nav'])==D('9988.6')
    assert all(b-a==h for a,b in zip(p['checkpoints'],p['checkpoints'][1:]))
    assert all(x['quantity']>0 and D(x['fee'])==0 for x in trades)
    assert value['portfolios']['zero']['metrics']['sharpe'] is None
    assert value['portfolios']['zero']['metrics']['cagr']=='0'


def test_cost_stress_changes_fills_not_horizon():
    a=run(5);b=run(5,cost_bps=20)
    assert a['horizon']==b['horizon']==5
    assert D(b['portfolios']['momentum']['days'][-1]['nav'])==D('9977.2')


def test_reproducible_input_order_and_decimal_context():
    chunks,start,end,_=fixture()
    a=replay(chunks,SECTORS,start,end,21)
    with localcontext() as ctx:
        ctx.prec=8
        b=replay(tuple(reversed(chunks)),dict(reversed(list(SECTORS.items()))),start,end,21)
    assert a==b


def test_replay_pins_decimal_rounding_and_traps():
    from decimal import ROUND_UP,ROUND_DOWN,Inexact
    chunks,start,end,_=fixture(scored=8)
    a=replay(chunks,SECTORS,start,end,5)
    for rounding in (ROUND_UP,ROUND_DOWN):
        with localcontext() as ctx:
            ctx.rounding=rounding;ctx.traps[Inexact]=True
            assert replay(chunks,SECTORS,start,end,5)==a


def test_duplicate_chunk_and_bad_horizon_refused():
    chunks,start,end,_=fixture()
    for c,h,code in [(chunks+chunks[:1],1,'DUPLICATE_BAR'),(chunks,2,'INVALID_PROTOCOL'),(chunks,True,'INVALID_PROTOCOL')]:
        with pytest.raises(DataError,match=code):replay(c,SECTORS,start,end,h)


def test_short_boundary_stays_cash():
    chunks,start,end,dates=fixture()
    p=json.loads(replay(chunks,SECTORS,start,dates[256],21).content)['portfolios']['momentum']
    assert p['trades']==[] and p['completed_intervals']==0
    assert all(D(x['nav'])==10000 for x in p['days'])


def test_late_revision_prohibits_prediction():
    chunks,start,end,_=fixture()
    def edit(v):
        for b in v['bars']:
            if b['reference']=='daily' and b['asset_id']=='AAPL':b['simulated_revision_available_at']='2026-10-09T00:00:00Z'
    p=json.loads(replay(changed(chunks,edit),SECTORS,start,end,5).content)['portfolios']['momentum']
    assert not any(x['symbol']=='AAPL' for x in p['trades'])
    assert any(x['reason']=='FEATURE_UNAVAILABLE' for x in p['omissions'])


def test_close_loss_halt_keeps_holdings_until_terminal():
    chunks,start,end,dates=fixture()
    def edit(v):
        for b in v['bars']:
            if b['reference']=='close' and b['session_date']==start and b['asset_id']!='SPY':
                for key in ('open','high','low','close'):b[key]='90'
    p=json.loads(replay(changed(chunks,edit),SECTORS,start,end,5).content)['portfolios']['momentum']
    assert p['halt']['reason']=='DAILY_LOSS'
    assert len(p['days'][1]['positions'])==3
    assert all(t['analytic_terminal'] for t in p['trades'][3:])
    assert p['completed_intervals']==0


def test_missing_held_mark_refuses_replay():
    chunks,start,end,dates=fixture()
    # Remove a complete feature-session block so the existing validator still agrees.
    def edit(v):
        if v['assets'][0]['symbol']=='AAPL' and dates[254] in v['feature_sessions']:
            v['feature_sessions'].remove(dates[254])
            v['bars']=[b for b in v['bars'] if not (b['session_date']==dates[254] and b['reference']!='entry') and not (b['session_date']==dates[255] and b['reference']=='entry')]
    with pytest.raises(DataError,match='MISSING_REFERENCE'):
        replay(changed(chunks,edit),SECTORS,start,end,21)


def test_metrics_hand_values_cash_days_and_zero_variance():
    m=metrics([D('100'),D('110'),D('99')],[D('100'),D('100'),D('100')])
    assert list(map(D,m['returns']))==[D('.1'),D('-.1')]
    assert D(m['annual_mean_excess'])==0
    assert D(m['max_drawdown'])==D('.1')
    assert metrics([D(100),D(100)],[D(100),D(100)])['sharpe'] is None
    with pytest.raises(DataError,match='INVALID_NAV'):metrics([D(100),D(0)],[D(100),D(100)])


@pytest.mark.parametrize('prediction,expected',[('.003',False),('.00300000005',False),('.0030000002',True),('-.1',False)])
def test_signal_boundary_is_conservative(prediction,expected):
    assert qualifies(D(prediction),D('.001')) is expected


def test_sector_limit_skips_ranked_name_and_uses_next():
    symbols=('AAPL','AMZN','GOOGL','JPM','SPY');chunks,start,end,_=fixture(symbols)
    sectors={s:'tech' if s in ('AAPL','AMZN','GOOGL') else s for s in symbols}
    p=json.loads(replay(chunks,sectors,start,end,21).content)['portfolios']['momentum']
    assert [x['symbol'] for x in p['trades'][:3]]==['AAPL','AMZN','JPM']
    assert any(x['symbol']=='GOOGL' and x['reason']=='SECTOR_TARGET_LIMIT' for x in p['omissions'])


def test_exact_warmup_and_anchor():
    chunks,start,end,dates=fixture()
    p=json.loads(replay(chunks,SECTORS,dates[250],dates[256],1).content)['portfolios']['momentum']
    assert p['checkpoints'][0]==2
    assert p['days'][0]['positions']==p['days'][1]['positions']=={}
    assert D(p['signals'][0]['predictions']['AAPL'])==D('.25')/21


def test_dividend_receivable_and_pay_date_no_double_count():
    chunks,start,end,dates=fixture()
    p=json.loads(replay(with_action(chunks,dates[254],pay_date=dates[257]),SECTORS,start,end,21).content)['portfolios']['momentum']
    assert D(p['days'][2]['receivables'])==19
    assert D(p['days'][2]['cash'])==D('4294.3')
    assert D(p['days'][5]['receivables'])==0
    assert D(p['days'][5]['cash'])==D('4313.3')
    assert D(p['days'][-1]['nav'])==D('10007.6')


def test_split_preserves_basis_and_economic_nav():
    chunks,start,end,dates=fixture()
    p=json.loads(replay(with_action(chunks,dates[254],kind='SPLIT'),SECTORS,start,end,21).content)['portfolios']['momentum']
    assert p['days'][2]['positions']['AAPL']==38
    assert D(p['days'][2]['basis']['AAPL'])==D('1901.9')
    assert D(p['days'][2]['nav'])==D('9994.3')
    assert D(p['days'][-1]['nav'])==D('9988.6')


def test_fractional_reverse_split_and_late_action_refused():
    chunks,start,end,dates=fixture()
    with pytest.raises(DataError,match='FRACTIONAL_ENTITLEMENT'):
        replay(with_action(chunks,dates[254],kind='SPLIT',factor='0.5'),SECTORS,start,end,21)
    with pytest.raises(DataError,match='ACTION_UNAVAILABLE'):
        replay(with_action(chunks,dates[254],known='2026-10-09T00:00:00Z'),SECTORS,start,end,21)


def test_gap_exposure_breach_halts_without_automatic_sell():
    chunks,start,end,dates=fixture()
    def edit(v):
        for b in v['bars']:
            if b['reference'] in ('entry','close') and b['session_date']==dates[253] and b['asset_id']!='SPY':
                for k in ('open','high','low','close'):b[k]='300'
    p=json.loads(replay(changed(chunks,edit),SECTORS,start,end,1).content)['portfolios']['momentum']
    assert p['halt']==dict(session=dates[253],phase='entry',reason='GROSS_LIMIT')
    assert p['days'][1]['positions']==p['days'][0]['positions']
    assert all(t['analytic_terminal'] for t in p['trades'][3:])


def test_missing_benchmark_and_late_reference_refused():
    chunks,start,end,dates=fixture()
    with pytest.raises(DataError,match='BENCHMARK_COVERAGE'):
        replay(tuple(c for c in chunks if json.loads(c.content)['assets'][0]['symbol']!='SPY'),{k:v for k,v in SECTORS.items() if k!='SPY'},start,end,1)
    def edit(v):
        for b in v['bars']:
            if b['reference']=='entry' and b['session_date']==start:b['simulated_revision_available_at']='2026-10-09T00:00:00Z'
    with pytest.raises(DataError,match='REFERENCE_UNAVAILABLE'):replay(changed(chunks,edit),SECTORS,start,end,1)


def test_orders_whole_bounded_and_benchmarks_use_same_days():
    r=run(5);p=r['portfolios']['momentum'];counts={}
    for t in p['trades']:
        assert type(t['quantity']) is int
        if not t['analytic_terminal']:
            assert t['quantity']*D(t['reference'])*D('1.001')<=2000
            counts[t['session']]=counts.get(t['session'],0)+1
    assert max(counts.values())<=6
    sessions=[x['session'] for x in p['days']]
    for name,v in r['portfolios'].items():
        assert [x['session'] for x in v['days']]==sessions
        assert v['days'][-1]['positions']=={}
    assert len(r['portfolios']['spy100']['trades'])==2
    assert D(r['portfolios']['spy60']['days'][0]['nav'])==D('9994.1')


def test_bounds_and_source_identity_refused():
    chunks,start,end,_=fixture()
    with pytest.raises(DataError,match='INPUT_BOUND'):replay(chunks[:1]*65,SECTORS,start,end,1)
    def edit(v):v['source']['vintage']='other'
    with pytest.raises(DataError,match='MIXED_SOURCE'):replay(changed(chunks[:1],edit)+chunks[1:],SECTORS,start,end,1)


def test_later_split_does_not_change_earlier_signal():
    chunks,start,end,dates=fixture()
    a=json.loads(replay(chunks,SECTORS,start,end,21).content)
    b=json.loads(replay(with_action(chunks,dates[280],kind='SPLIT'),SECTORS,start,end,21).content)
    assert a['portfolios']['momentum']['signals'][0]==b['portfolios']['momentum']['signals'][0]


@pytest.mark.parametrize('h',[1,5,21])
def test_full_proposed_universe_uses_bounded_chunks(h):
    from compertum.simulation.market import WATCHLIST
    symbols=WATCHLIST+('SPY',)
    chunks,start,end,_=fixture(symbols,scored=23)
    sectors={s:'fixture-'+str(i//2) for i,s in enumerate(symbols)}
    result=json.loads(replay(chunks,sectors,start,end,h).content)
    assert set(result['sectors'])==set(symbols)
    assert len(result['portfolios']['momentum']['trades'])>=6
    assert result['financial_status']=='SYNTHETIC_UNVERIFIED'


def test_shared_functions_ignore_ambient_decimal_settings():
    from decimal import ROUND_UP,Inexact
    args=([D(100),D(110),D(99)],[D(100),D(100),D(100)])
    expected=metrics(*args)
    with localcontext() as ctx:
        ctx.prec=3;ctx.rounding=ROUND_UP;ctx.traps[Inexact]=True
        assert buy_quantity(D(2000),D(100),D('.001'))==19
        assert metrics(*args)==expected
