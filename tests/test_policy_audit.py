"""Exact strategy decisions and completed intervals, independent of replay."""
import json,hashlib,copy
from decimal import Decimal as D
from functools import lru_cache
import pytest
from compertum.data.errors import DataError
from compertum.data.calendar import session_times
from compertum.data.encoding import canonical
from compertum.simulation import replay
from compertum.simulation.market import load_market
from compertum.modeling.candidate import evaluate_candidate
from compertum.modeling.registry import VARIANTS
from compertum.audit_execution import audit_execution,_policy
from helpers.simulation_fixture import fixture,changed,with_action,SECTORS
from helpers.model_campaign_fixture import campaign_fixture


def policy(chunks,sectors,start,end,horizon=21,cost=10,mutate=None):
    result=json.loads(replay(chunks,sectors,start,end,horizon,cost_bps=cost).content)
    if mutate:mutate(result)
    return _policy(load_market(chunks,sectors),result,None),result

@pytest.mark.parametrize('horizon',[1,5,21])
@pytest.mark.parametrize('cost',[10,20])
def test_hand_whole_shares_cash_costs_and_intervals(horizon,cost):
    chunks,start,end,_=fixture();report,result=policy(chunks,SECTORS,start,end,horizon,cost)
    p=result['portfolios']['momentum']
    assert [(r['symbol'],r['quantity']) for r in p['trades'][:3]]==[('AAPL',19),('JPM',19),('MSFT',19)]
    assert D(p['days'][-1]['nav'])==D('9988.6') if cost==10 else D(p['days'][-1]['nav'])==D('9977.2')
    assert report['checkpoints']==p['checkpoints'] and len(report['holding_intervals'])==p['completed_intervals']
    assert all(r['end_index']-r['start_index']==horizon for r in report['holding_intervals'])

@pytest.mark.parametrize('mutation',[
 lambda v:v['portfolios']['momentum']['checkpoints'].pop(),
 lambda v:v['portfolios']['momentum'].__setitem__('completed_intervals',99),
 lambda v:v['portfolios']['momentum']['signals'].pop(),
 lambda v:v['portfolios']['momentum']['signals'][0]['predictions'].__setitem__('AAPL','0'),
 lambda v:v['portfolios']['momentum']['omissions'].append({'session':v['start'],'symbol':'AAPL','reason':'MADE_UP'}),
 lambda v:v['portfolios'].__setitem__('momentum',copy.deepcopy(v['portfolios']['zero'])),
 lambda v:v['portfolios'].__setitem__('spy60',copy.deepcopy(v['portfolios']['zero'])),
 lambda v:v['portfolios']['momentum']['trades'].reverse(),
 lambda v:v['portfolios']['momentum']['trades'][0].__setitem__('quantity',18),
])
def test_policy_corruption_cannot_hide_behind_balanced_arithmetic(mutation):
    chunks,start,end,_=fixture()
    with pytest.raises(DataError):policy(chunks,SECTORS,start,end,mutate=mutation)


def test_first_eligible_anchor_includes_cash_days_and_late_start():
    chunks,start,end,days=fixture()
    report,_=policy(chunks,SECTORS,days[250],days[256],1)
    assert report['checkpoints'][0]==2
    report,_=policy(chunks,SECTORS,start,days[256],21)
    assert report['holding_intervals']==[] and report['checkpoints']==[0]


def test_no_eligible_anchor_has_no_benchmark_trades():
    chunks,start,end,_=fixture()
    def edit(v):
        for row in v['bars']:
            if row['reference']=='daily' and row['asset_id']!='SPY':row.update(open='1',high='1',low='1',close='1')
    report,result=policy(changed(chunks,edit),SECTORS,start,end)
    assert report['checkpoints']==[] and all(p['trades']==[] for p in result['portfolios'].values())


def test_sector_tie_skips_third_name_then_uses_next_sector():
    chunks,start,end,_=fixture(('AAPL','AMZN','GOOGL','JPM','SPY'))
    sectors={s:'tech' if s in ('AAPL','AMZN','GOOGL') else s for s in ('AAPL','AMZN','GOOGL','JPM','SPY')}
    report,result=policy(chunks,sectors,start,end)
    assert [r['symbol'] for r in result['portfolios']['momentum']['trades'][:3]]==['AAPL','AMZN','JPM']
    assert any(r['reason']=='SECTOR_TARGET_LIMIT' for r in result['portfolios']['momentum']['omissions'])


def test_close_halt_excludes_intervals_and_preserves_analytic_exit():
    chunks,start,end,_=fixture()
    def edit(v):
        for row in v['bars']:
            if row['reference']=='close' and row['session_date']==start and row['asset_id']!='SPY':row.update(open='90',high='90',low='90',close='90')
    report,result=policy(changed(chunks,edit),SECTORS,start,end,5)
    assert report['holding_intervals']==[]
    assert all(t['analytic_terminal'] for t in result['portfolios']['momentum']['trades'][3:])

@pytest.mark.parametrize('kind',['split','unpaid_dividend'])
def test_actions_do_not_create_extra_holding_intervals(kind):
    chunks,start,end,dates=fixture()
    if kind=='split':
        chunks=with_action(chunks,dates[254],kind='SPLIT')
    else:chunks=with_action(chunks,dates[254],pay_date='2022-01-03')
    report,result=policy(chunks,SECTORS,start,end,21)
    assert len(report['holding_intervals'])==result['portfolios']['momentum']['completed_intervals']==3
    assert len({(r['symbol'],r['start_index'],r['end_index']) for r in report['holding_intervals']})==len(report['holding_intervals'])

@pytest.mark.parametrize('candidate',[c.candidate_id for c in VARIANTS])
def test_complete_candidate_audit_combines_source_accounting_and_policy(candidate):
    chunks,ts,te,start,end,asof=campaign_fixture();result=evaluate_candidate(chunks,SECTORS,ts,te,start,end,candidate,scoring_as_of=asof)
    report=audit_execution(chunks,SECTORS,result,candidate_id=candidate,year=2021,training_start=ts,training_end=te,start=start,end=end,scoring_as_of=asof)
    v=json.loads(report.content)
    assert v['status']=='VERIFIED_PASS' and not v['financial_accepted'] and not v['full_M3']
    assert set(v['costs'])=={'10','20'} and v['candidate_sha256']==result.sha256
    assert v['gates']['independent_native_auditor_identity']=='UNVERIFIED'


def test_six_child_limit_leaves_residual_for_terminal_liquidation():
    chunks,start,end,dates=fixture(scored=22);action_day=dates[253]
    chunks=with_action(chunks,action_day)
    def edit(v):
        for action in v['actions']:action['amount']='500'
        for row in v['bars']:
            if row['reference'] in ('entry','close') and row['asset_id']!='SPY' and row['session_date']>=action_day:row.update(open='250',high='250',low='250',close='250')
    report,result=policy(changed(chunks,edit),SECTORS,start,end,21)
    book=result['portfolios']['momentum'];last=[r for r in book['trades'] if r['session']==end]
    assert len([r for r in last if not r['analytic_terminal']])==6
    assert any(r['analytic_terminal'] for r in last)
    assert any(r['reason']=='SUBMISSION_LIMIT' for r in book['omissions'])
    assert book['days'][-1]['positions']=={} and book['halt'] is None


def test_first_sale_can_halt_remaining_ordinary_children():
    chunks,start,end,_=fixture(scored=22)
    def edit(v):
        for row in v['bars']:
            if row['reference'] in ('entry','close') and row['asset_id']!='SPY' and row['session_date']==end:row.update(open='96.5',high='96.5',low='96.5',close='96.5')
    report,result=policy(changed(chunks,edit),SECTORS,start,end,21)
    p=result['portfolios']['momentum'];last=[r for r in p['trades'] if r['session']==end]
    assert p['halt']=={'session':end,'phase':'post_fill','reason':'DAILY_LOSS'}
    assert len([r for r in last if not r['analytic_terminal']])==1
    assert len([r for r in last if r['analytic_terminal']])==2
    assert p['completed_intervals']==len(report['holding_intervals'])==3

@pytest.mark.parametrize('prediction,qualifies',[(D('.003'),False),(D('.0030000001'),False),(D('.0030000002'),True)])
def test_exact_signal_threshold_does_not_use_numeric_tolerance(prediction,qualifies):
    chunks,start,end,dates=fixture(scored=2);boundary=dates[251-21];price=str(100*(1+21*prediction))
    def edit(v):
        for row in v['bars']:
            if row['reference']=='daily' and row['asset_id']!='SPY':
                value=price if row['session_date']>boundary else '100';row.update(open=value,high=value,low=value,close=value)
    report,result=policy(changed(chunks,edit),SECTORS,start,end,1)
    assert bool([r for r in result['portfolios']['momentum']['trades'] if r['session']==start]) is qualifies


def test_zero_whole_share_capacity_is_recorded():
    chunks,start,end,_=fixture(scored=2)
    def edit(v):
        for row in v['bars']:
            if row['reference'] in ('entry','close'):row.update(open='100000',high='100000',low='100000',close='100000')
    report,result=policy(changed(chunks,edit),SECTORS,start,end,1)
    assert result['portfolios']['momentum']['trades']==[]
    assert any(r['reason']=='WHOLE_SHARE_OR_INTENT_LIMIT' for r in result['portfolios']['momentum']['omissions'])


def test_reductions_need_twenty_liquidity_rows_not_252_feature_rows():
    chunks,start,end,_=fixture(scored=22)
    def edit(v):
        for row in v['bars']:
            if row['reference']=='daily' and row['asset_id']!='SPY' and row['session_date']==start:row['simulated_revision_available_at']='2026-10-09T00:00:00Z'
    # Entry day uses prior features. By checkpoint21 the unavailable daily row
    # is outside the20-session liquidity window but still inside252 features.
    report,result=policy(changed(chunks,edit),SECTORS,start,end,21)
    assert result['portfolios']['momentum']['days'][-1]['positions']=={}
    assert len(report['holding_intervals'])==3


def test_recorded_signal_cannot_cross_trade_threshold_within_tolerance():
    chunks,start,end,dates=fixture(scored=2);boundary=dates[230];price=str(100*(1+21*D('.0030000001')))
    def edit(v):
        for row in v['bars']:
            if row['reference']=='daily' and row['asset_id']!='SPY':
                value=price if row['session_date']>boundary else '100';row.update(open=value,high=value,low=value,close=value)
    def corrupt(v):v['portfolios']['momentum']['signals'][0]['predictions']['AAPL']='0.00300000015'
    with pytest.raises(DataError):policy(changed(chunks,edit),SECTORS,start,end,1,mutate=corrupt)


def test_tolerated_model_shift_cannot_change_exact_trade_decisions():
    from dataclasses import replace
    from compertum.modeling.checkpoints import prepare_fit_checkpoint
    from compertum.audit_predictions import audit_candidate_predictions
    chunks,ts,te,start,end,asof=campaign_fixture();market=load_market(chunks,SECTORS)
    dates=sorted({d for _,d,r in market.rows if r=='entry'});prices={d:format((D(100)*(1+D('.00300000005'))**i).quantize(D('0.000000000001')),'f') for i,d in enumerate(dates)}
    def edit(v):
        for row in v['bars']:
            if row['reference']=='entry':
                price=prices[row['session_date']];row.update(open=price,high=price,low=price,close=price)
    original=changed(chunks,edit);fit=prepare_fit_checkpoint(original,SECTORS,ts,te,2021,'ridge-h01-a001');v=json.loads(fit.content)
    before=D(str(v['model']['ridge']['intercept']));assert before<D('.0030000001')<before+D('8e-11')
    v['model']['ridge']['intercept']+=8e-11;v['model_sha256']=hashlib.sha256(canonical(v['model'])).hexdigest();raw=canonical(v);bad=replace(fit,content=raw,sha256=hashlib.sha256(raw).hexdigest())
    result=evaluate_candidate(original,SECTORS,ts,te,start,end,'ridge-h01-a001',scoring_as_of=asof,fit_checkpoint=bad,expected_fit_sha256=bad.sha256)
    args=dict(candidate_id='ridge-h01-a001',year=2021,training_start=ts,training_end=te,start=start,end=end,scoring_as_of=asof)
    assert json.loads(audit_candidate_predictions(original,SECTORS,result,**args).content)['status']=='VERIFIED_PASS'
    assert any(t['side']=='BUY' for t in json.loads(result.content)['replays']['10']['portfolios']['strategy']['trades'])
    with pytest.raises(DataError):audit_execution(original,SECTORS,result,**args)
