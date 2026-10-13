"""Independent equations over original synthetic prices and recorded fills."""
import hashlib,json
from decimal import Decimal as D,localcontext,ROUND_UP
import pytest
from helpers.simulation_fixture import fixture,changed,with_action,SECTORS
from compertum.simulation import replay
from compertum.simulation.engine import ReplayResult
from compertum.data.encoding import canonical
from compertum.data.errors import DataError
from compertum.audit import audit_accounting,reconstruct_metrics


def edited(result,change):
    value=json.loads(result.content);change(value);raw=canonical(value)
    return ReplayResult(raw,hashlib.sha256(raw).hexdigest())


@pytest.mark.parametrize('horizon',[1,5,21])
@pytest.mark.parametrize('cost',[10,20])
def test_original_ledgers_reconcile_to_independent_accounting(horizon,cost):
    chunks,start,end,_=fixture();result=replay(chunks,SECTORS,start,end,horizon,cost_bps=cost)
    audit=audit_accounting(chunks,SECTORS,result);value=json.loads(audit.content)
    assert value['status']=='VERIFIED_PASS' and value['financial_accepted'] is False and value['full_M3'] is False
    assert value['scope']=='SYNTHETIC_RECORDED_FILL_ACCOUNTING' and value['replay_sha256']==result.sha256
    assert value['counts']['portfolios']==5 and value['counts']['daily_records']==5*44
    assert value['gates']['strategy_selection']=='UNVERIFIED' and value['gates']['real_data_qualification']=='UNVERIFIED'
    assert hashlib.sha256(audit.content).hexdigest()==audit.sha256
    with localcontext() as ctx:
        ctx.prec=8;ctx.rounding=ROUND_UP
        assert audit_accounting(tuple(reversed(chunks)),dict(reversed(list(SECTORS.items()))),result)==audit


def test_metric_hand_values_and_undefined_variance():
    result=reconstruct_metrics([D(100),D(110),D(99)],[D(100),D(100),D(100)])
    assert list(map(D,result['returns']))==[D('.1'),D('-.1')]
    assert D(result['annual_mean_excess'])==0 and D(result['max_drawdown'])==D('.1')
    assert D(result['annual_volatility'])==D('5.04').sqrt() and D(result['sharpe'])==0
    assert reconstruct_metrics([D(100),D(100)],[D(100),D(100)])['sharpe'] is None
    with pytest.raises(DataError):reconstruct_metrics([D(100),D(0)],[D(100),D(100)])


@pytest.mark.parametrize('action',['dividend','split','unpaid_dividend'])
def test_actions_reconstruct_pretrade_entitlement_and_basis(action):
    chunks,start,end,dates=fixture()
    if action=='split':chunks=with_action(chunks,dates[254],kind='SPLIT')
    else:chunks=with_action(chunks,dates[254],pay_date=dates[257] if action=='dividend' else '2022-12-30')
    result=replay(chunks,SECTORS,start,end,21)
    audit=json.loads(audit_accounting(chunks,SECTORS,result).content)
    assert audit['counts']['actions']>0 and audit['status']=='VERIFIED_PASS'
    def erase(v):v['portfolios']['momentum']['actions'].pop(0)
    with pytest.raises(DataError,match='AUDIT_'):audit_accounting(chunks,SECTORS,edited(result,erase))


@pytest.mark.parametrize('mutation',['cash','nav','positions','basis','receivable','quantity','fill','reference','price_cost','turnover','fee','time','observation','loss','drawdown','missing_observation','duplicate_day','metric','undefined_sharpe','extra_trade'])
def test_rehashed_wrong_accounting_fails_independent_checks(mutation):
    chunks,start,end,_=fixture(scored=8);result=replay(chunks,SECTORS,start,end,5)
    def change(v):
        p=v['portfolios']['momentum'];d=p['days'][0];t=p['trades'][0];o=p['observations'][0]
        if mutation=='cash':d['cash']='4295.3'
        elif mutation=='nav':d['nav']='9995.3'
        elif mutation=='positions':d['positions']['AAPL']+=1
        elif mutation=='basis':d['basis']['AAPL']='1'
        elif mutation=='receivable':d['receivables']='1'
        elif mutation=='quantity':t['quantity']=True
        elif mutation=='fill':t['fill_price']='101'
        elif mutation=='reference':t['reference']='101'
        elif mutation=='price_cost':t['price_cost']='1'
        elif mutation=='turnover':t['turnover']='1'
        elif mutation=='fee':t['fee']='1'
        elif mutation=='time':t['at']='2021-01-04T00:00:00Z'
        elif mutation=='observation':o['nav']='9999'
        elif mutation=='loss':o['daily_loss']='.1'
        elif mutation=='drawdown':o['drawdown']='.1'
        elif mutation=='missing_observation':p['observations'].pop()
        elif mutation=='duplicate_day':p['days'][1]=dict(p['days'][0])
        elif mutation=='metric':p['metrics']['returns'][0]='.1'
        elif mutation=='undefined_sharpe':v['portfolios']['zero']['metrics']['sharpe']='99'
        else:p['trades'].append(dict(t))
    with pytest.raises(DataError,match='AUDIT_'):audit_accounting(chunks,SECTORS,edited(result,change))


def test_risk_halt_uses_entry_post_fill_and_close_high_water():
    chunks,start,end,_=fixture(scored=8)
    def gap(v):
        for b in v['bars']:
            if b['reference']=='close' and b['session_date']==start and b['asset_id']!='SPY':
                for field in ('open','high','low','close'):b[field]='90'
    chunks=changed(chunks,gap);result=replay(chunks,SECTORS,start,end,5)
    assert json.loads(audit_accounting(chunks,SECTORS,result).content)['status']=='VERIFIED_PASS'
    with pytest.raises(DataError,match='AUDIT_'):
        audit_accounting(chunks,SECTORS,edited(result,lambda v:v['portfolios']['momentum'].update(halt=None)))


def test_hash_and_canonical_bounds_are_not_bypassed():
    chunks,start,end,_=fixture(scored=8);result=replay(chunks,SECTORS,start,end,5)
    for forged in (ReplayResult(result.content,'f'*64),ReplayResult(b' '+result.content,hashlib.sha256(b' '+result.content).hexdigest())):
        with pytest.raises(DataError,match='AUDIT_'):audit_accounting(chunks,SECTORS,forged)

@pytest.mark.parametrize('field,value',[('reference','100.0000001'),('fee','0.00000000001')])
def test_raw_reference_and_declared_zero_fee_are_exact(field,value):
    chunks,start,end,_=fixture(scored=8);result=replay(chunks,SECTORS,start,end,5)
    def change(v):v['portfolios']['momentum']['trades'][0][field]=value
    with pytest.raises(DataError,match='AUDIT_'):audit_accounting(chunks,SECTORS,edited(result,change))


def test_independent_buy_split_dividend_sell_hand_ledger():
    from compertum.data.calendar import session_times
    from compertum.simulation.metrics import metrics
    chunks,start,end,dates=fixture(scored=8);days=dates[252:260]
    chunks=with_action(chunks,days[1],kind='SPLIT')
    def split_id(v):
        for a in v['actions']:a['action_id']='hand-split'
    chunks=changed(chunks,split_id)
    chunks=with_action(chunks,days[2],pay_date='2022-12-30')
    def jump(v):
        if v['assets'][0]['symbol']=='AAPL':
            for b in v['bars']:
                if b['reference'] in ('entry','close') and b['session_date']>=days[3]:
                    for key in ('open','high','low','close'):b[key]='55'
    chunks=changed(chunks,jump);result=replay(chunks,SECTORS,start,end,21)
    value=json.loads(result.content);book=value['portfolios']['momentum']
    def num(v):return format(v,'f')
    trades=[dict(session=days[0],at=session_times(days[0]).entry.isoformat(),symbol='AAPL',side='BUY',quantity=2,reference='100',fill_price='100.1',fee='0',price_cost='.2',turnover='.02',analytic_terminal=False,fill_assumption='SAME_FEED_MINUTE_OPEN_ADVERSE'),
        dict(session=days[3],at=session_times(days[3]).entry.isoformat(),symbol='AAPL',side='SELL',quantity=4,reference='55',fill_price='54.945',fee='0',price_cost='.22',turnover=num(D(220)/D('10023.8')),analytic_terminal=False,fill_assumption='SAME_FEED_MINUTE_OPEN_ADVERSE')]
    observations=[];records=[];high=D(10000);prior=D(10000)
    close_values=list(map(D,['9999.8','9999.8','10003.8','10023.58','10023.58','10023.58','10023.58','10023.58']))
    for i,day in enumerate(days):
        entries=[('entry',D(10000) if i==0 else D('10023.8') if i==3 else close_values[i])]
        if i in (0,3):entries.append(('post_fill',close_values[i]))
        entries.append(('close',close_values[i]))
        for phase,nav in entries:
            high=max(high,nav);observations.append(dict(session=day,phase=phase,nav=num(nav),daily_loss=num(max(D(0),1-nav/prior)),drawdown=num(1-nav/high)))
        records.append(dict(session=day,nav=num(close_values[i]),cash='9799.8' if i<3 else '10019.58',receivables='0' if i<2 else '4',positions={'AAPL':2 if i==0 else 4} if i<3 else {},basis={'AAPL':'200.2'} if i<3 else {}));prior=close_values[i]
    book.update(trades=trades,actions=[dict(session=days[1],action_id='hand-split',kind='SPLIT',symbol='AAPL',quantity=4,basis='200.2'),dict(session=days[2],action_id='action-fixture-1',kind='DIVIDEND_RECEIVABLE',symbol='AAPL',amount='4')],observations=observations,days=records,signals=[],omissions=[],checkpoints=[],completed_intervals=0,halt=None)
    benchmark=[D(10000)]+[D(d['nav']) for d in value['portfolios']['spy60']['days']]
    book['metrics']=metrics([D(10000)]+close_values,benchmark)
    raw=canonical(value);audit=json.loads(audit_accounting(chunks,SECTORS,ReplayResult(raw,hashlib.sha256(raw).hexdigest())).content)
    checked=audit['portfolios']['momentum']
    assert D(checked['ending_cash'])==D('10019.58') and D(checked['ending_receivables'])==4
    assert D(checked['ending_nav'])==D('10023.58') and D(checked['price_cost'])==D('.42')


def test_reported_nav_returns_cannot_exceed_daily_tolerance():
    chunks,start,end,_=fixture(scored=8);result=replay(chunks,SECTORS,start,end,5)
    def change(v):
        days=v['portfolios']['zero']['days'];days[0]['nav']='10000.00009';days[1]['nav']='9999.99991'
    with pytest.raises(DataError,match='AUDIT_'):audit_accounting(chunks,SECTORS,edited(result,change))
