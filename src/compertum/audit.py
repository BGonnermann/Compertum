"""Independent accounting equations over synthetic inputs and recorded fills.

This entry point never calls the replay ledger or its metrics implementation.
Reconciliation does not establish strategy choice, model provenance or authority.
"""
from dataclasses import dataclass
from decimal import Decimal as D,Context,localcontext,ROUND_HALF_EVEN,InvalidOperation,DivisionByZero,Overflow,DecimalException
from functools import wraps
import hashlib,json
from .data.encoding import canonical
from .data.errors import DataError
from .data.calendar import session_times,utc_time
from .simulation.market import load_market

INITIAL=D(10000)
ABS=D('1e-10')
REL=D('1e-8')
RETURN_ABS=D('1e-8')
MAX_BYTES=16*1024**2

@dataclass(frozen=True)
class AccountingAudit:
    content:bytes
    sha256:str


def _precision(function):
    @wraps(function)
    def run(*args,**kwargs):
        with localcontext(Context(prec=28,rounding=ROUND_HALF_EVEN,traps=[InvalidOperation,DivisionByZero,Overflow])):
            return function(*args,**kwargs)
    return run


def _require(condition,code='AUDIT_ACCOUNTING_MISMATCH'):
    if not condition:raise DataError(code)


def _number(value):
    s=format(value,'f')
    return (s.rstrip('0').rstrip('.') if '.' in s else s) if value else '0'


def _decimal(value):
    _require(type(value) is str,'AUDIT_INPUT_INVALID')
    try:v=D(value)
    except DecimalException:raise DataError('AUDIT_INPUT_INVALID') from None
    _require(v.is_finite() and abs(v)<=D('1e32'),'AUDIT_INPUT_INVALID')
    return v


def _near(actual,expected,*,returns=False):
    value=_decimal(actual)
    tolerance=RETURN_ABS if returns else ABS+REL*abs(expected)
    _require(abs(value-expected)<=tolerance)


@_precision
def reconstruct_metrics(navs,benchmark):
    """Independent closing-NAV equations, with fixed predeclared tolerances."""
    _require(isinstance(navs,(list,tuple)) and isinstance(benchmark,(list,tuple)) and 2<=len(navs)<=1025 and len(navs)==len(benchmark),'AUDIT_INPUT_INVALID')
    _require(all(type(x) is D and x.is_finite() and 0<x<=D('1e32') for x in (*navs,*benchmark)),'AUDIT_INPUT_INVALID')
    returns=[navs[i]/navs[i-1]-1 for i in range(1,len(navs))]
    bench=[benchmark[i]/benchmark[i-1]-1 for i in range(1,len(benchmark))]
    n=D(len(returns));mean=sum(returns)/n
    variance=sum((v-mean)*(v-mean) for v in returns)/(n-1) if n>1 else None
    volatility=(252*variance).sqrt() if variance is not None else None
    sharpe=252*mean/volatility if volatility else None
    peak=navs[0];drawdown=D(0)
    for value in navs[1:]:
        peak=max(peak,value);drawdown=max(drawdown,(peak-value)/peak)
    result={'returns':list(map(_number,returns)),'benchmark_returns':list(map(_number,bench)),
        'annual_mean_excess':_number(sum(a-b for a,b in zip(returns,bench))*252/n),
        'annual_volatility':_number(volatility) if volatility is not None else None,
        'sharpe':_number(sharpe) if sharpe is not None else None,'sharpe_status':'DEFINED' if sharpe is not None else 'UNDEFINED',
        'cagr':_number((navs[-1]/navs[0])**(252/n)-1),'max_drawdown':_number(drawdown)}
    return result


def _metrics(record,expected):
    _require(type(record) is dict and set(record)==set(expected))
    for key,value in expected.items():
        actual=record[key]
        if value is None or key=='sharpe_status':_require(type(actual) is type(value) and actual==value)
        elif isinstance(value,list):
            _require(type(actual) is list and len(actual)==len(value))
            for a,b in zip(actual,value):_near(a,D(b),returns=True)
        else:_near(actual,D(value))


def _portfolio(book,market,dates,cost,strategy):
    _require(type(book) is dict and set(book)=={'trades','actions','observations','days','signals','omissions','checkpoints','halt','completed_intervals','metrics'})
    for key in ('trades','actions','observations','days','signals','omissions','checkpoints'):
        _require(type(book[key]) is list and len(book[key])<=16384,'AUDIT_INPUT_INVALID')
    _require(len(book['days'])==len(dates))
    _require(type(book['completed_intervals']) is int and book['completed_intervals']>=0)
    _require(all(type(i) is int and 0<=i<len(dates) for i in book['checkpoints']) and book['checkpoints']==sorted(set(book['checkpoints'])))
    cash=INITIAL;positions={};basis={};claims={};high=INITIAL;previous=INITIAL;halt=None;navs=[INITIAL];turnover=D(0);price_cost=D(0)
    trades=iter(book['trades']);trade=next(trades,None);observations=iter(book['observations']);actions=[]
    def marked(day,reference):return {s:market.reference(s,day,reference) for s in positions}
    def nav(prices):return cash+sum(positions[s]*prices[s] for s in positions)+sum(v[0] for v in claims.values())
    def observe(day,phase):
        nonlocal high,halt
        prices=marked(day,'close' if phase=='close' else 'entry');value=nav(prices);_require(value>0)
        high=max(high,value);loss=max(D(0),1-value/previous);drawdown=1-value/high
        if strategy and halt is None:
            amounts={s:positions[s]*prices[s] for s in positions}
            reason=None
            if loss>=D('.02')-ABS:reason='DAILY_LOSS'
            elif drawdown>=D('.10')-ABS:reason='DRAWDOWN'
            elif cash<0:reason='INVALID_NAV'
            elif sum(amounts.values())/value>=D('.6')-ABS:reason='GROSS_LIMIT'
            elif any(a/value>=D('.2')-ABS for a in amounts.values()):reason='NAME_LIMIT'
            elif any(sum(a for s,a in amounts.items() if market.sectors[s]==sector)/value>=D('.4')-ABS for sector in set(market.sectors.values())):reason='SECTOR_LIMIT'
            if reason:halt={'session':day,'phase':phase,'reason':reason}
        recorded=next(observations,None)
        _require(type(recorded) is dict and set(recorded)=={'session','phase','nav','daily_loss','drawdown'} and recorded['session']==day and recorded['phase']==phase)
        for field,expected in [('nav',value),('daily_loss',loss),('drawdown',drawdown)]:_near(recorded[field],expected)
        return value
    for index,day in enumerate(dates):
        # Original actions are authoritative; recorded action rows cannot invent claims.
        for action in market.actions:
            symbol=action['symbol'];quantity=positions.get(symbol,0)
            if action['effective_session']!=day or not quantity:continue
            _require(utc_time(action['simulated_known_at'])<=session_times(day).decision)
            if action['kind']=='SPLIT':
                new=quantity*D(action['factor']);_require(new==int(new) and new>0)
                positions[symbol]=int(new)
                actions.append({'session':day,'action_id':action['action_id'],'kind':'SPLIT','symbol':symbol,'quantity':int(new),'basis':_number(basis[symbol])})
            else:
                amount=quantity*D(action['amount']);_require(action['action_id'] not in claims)
                claims[action['action_id']]=(amount,action['pay_date'])
                actions.append({'session':day,'action_id':action['action_id'],'kind':'DIVIDEND_RECEIVABLE','symbol':symbol,'amount':_number(amount)})
        for key,(amount,pay) in list(claims.items()):
            if pay<=day:
                cash+=amount;del claims[key]
                actions.append({'session':day,'action_id':key,'kind':'DIVIDEND_CASH','amount':_number(amount)})
        observe(day,'entry')
        while trade is not None and trade['session']==day:
            _require(type(trade) is dict and set(trade)=={'session','at','symbol','side','quantity','reference','fill_price','fee','price_cost','turnover','analytic_terminal','fill_assumption'})
            symbol=trade['symbol'];quantity=trade['quantity'];side=trade['side'];terminal=trade['analytic_terminal']
            _require(symbol in market.symbols and type(quantity) is int and 0<quantity<=10**12 and side in ('BUY','SELL'))
            _require(type(terminal) is bool and (not terminal or (index==len(dates)-1 and side=='SELL')))
            _require(trade['at']==session_times(day).entry.isoformat() and trade['fill_assumption']=='SAME_FEED_MINUTE_OPEN_ADVERSE')
            _require(not strategy or halt is None or terminal)
            before=nav(marked(day,'entry'));reference=market.reference(symbol,day,'entry')
            _require(_decimal(trade['reference'])==reference and _decimal(trade['fee'])==0)
            fill=reference*(1+cost if side=='BUY' else 1-cost);amount=quantity*fill
            for field,expected in [('reference',reference),('fill_price',fill),('fee',D(0)),('price_cost',quantity*reference*cost),('turnover',quantity*reference/before)]:_near(trade[field],expected)
            if side=='BUY':
                _require(amount<=cash);cash-=amount;positions[symbol]=positions.get(symbol,0)+quantity;basis[symbol]=basis.get(symbol,D(0))+amount
            else:
                old=positions.get(symbol,0);_require(quantity<=old)
                cash+=amount;positions[symbol]=old-quantity;basis[symbol]=basis[symbol]*D(old-quantity)/old
                if not positions[symbol]:del positions[symbol];del basis[symbol]
            turnover+=quantity*reference/before;price_cost+=quantity*reference*cost
            observe(day,'post_fill');trade=next(trades,None)
        value=observe(day,'close');previous=value;navs.append(value)
        record=book['days'][index]
        _require(type(record) is dict and set(record)=={'session','nav','cash','positions','basis','receivables'} and record['session']==day)
        _require(type(record['positions']) is dict and all(type(q) is int and q>0 for q in record['positions'].values()) and record['positions']==positions)
        _require(type(record['basis']) is dict and set(record['basis'])==set(basis))
        for symbol,total in basis.items():_near(record['basis'][symbol],total)
        for key,expected in [('nav',value),('cash',cash),('receivables',sum(v[0] for v in claims.values()))]:_near(record[key],expected)
    _require(trade is None and next(observations,None) is None and positions=={})
    _require(book['halt']==halt and len(book['actions'])==len(actions))
    for actual,expected in zip(book['actions'],actions):
        _require(type(actual) is dict and set(actual)==set(expected))
        for key,value in expected.items():
            if key in ('amount','basis'):_near(actual[key],D(value))
            else:_require(type(actual[key]) is type(value) and actual[key]==value)
    return navs,{'trades':len(book['trades']),'actions':len(actions),'observations':len(book['observations']),'daily_records':len(dates),
        'ending_cash':_number(cash),'ending_receivables':_number(sum(v[0] for v in claims.values())),
        'ending_nav':_number(navs[-1]),'turnover':_number(turnover),'price_cost':_number(price_cost)}


@_precision
def audit_accounting(chunks,sectors,result):
    """Read bounded immutable synthetic records; produce evidence, never approval."""
    try:
        raw=result.content
        _require(type(raw) is bytes and 0<len(raw)<=MAX_BYTES and hashlib.sha256(raw).hexdigest()==result.sha256,'AUDIT_INPUT_INVALID')
        value=json.loads(raw);_require(canonical(value)==raw,'AUDIT_INPUT_INVALID')
        _require(value['policy'] in ('momentum-synthetic-v1','registered-candidate-synthetic-v1') and value['schema_version']=='1'
            and value['financial_status']=='SYNTHETIC_UNVERIFIED' and value.get('financial_accepted',False) is False,'AUDIT_INPUT_INVALID')
        _require(type(value['horizon']) is int and value['horizon'] in (1,5,21) and type(value['cost_bps']) is int and value['cost_bps'] in (10,20),'AUDIT_INPUT_INVALID')
        _require(value['ledger_precision']==28 and value['ledger_rounding']=='ROUND_HALF_EVEN','AUDIT_INPUT_INVALID')
        start,end=value['start'],value['end'];_require('2016-01-01'<=start<=end<'2024-01-01','AUDIT_INPUT_INVALID')
        session_times(start);session_times(end);dates=[start]
        while dates[-1]!=end:
            _require(len(dates)<1024,'AUDIT_INPUT_INVALID');dates.append(session_times(dates[-1]).next_date)
        market=load_market(chunks,sectors);_require(market.sha256==value['market_sha256'] and value['sectors']==sectors,'AUDIT_INPUT_INVALID')
        strategy='momentum' if value['policy']=='momentum-synthetic-v1' else 'strategy'
        if strategy=='strategy':
            from .modeling.registry import variant
            c=variant(value['candidate_id']);_require(c.horizon==value['horizon'],'AUDIT_INPUT_INVALID')
        names={strategy,'spy60','spy100','equal60','zero'};_require(type(value['portfolios']) is dict and set(value['portfolios'])==names,'AUDIT_INPUT_INVALID')
        for day in dates:
            market.reference('SPY',day,'entry');market.reference('SPY',day,'close')
        navs={};summaries={};counts={'portfolios':5,'trades':0,'actions':0,'observations':0,'daily_records':0}
        for name in sorted(names):
            navs[name],summaries[name]=_portfolio(value['portfolios'][name],market,dates,D(value['cost_bps'])/10000,name==strategy)
            for key in counts.keys()-{'portfolios'}:counts[key]+=summaries[name][key]
        recorded_navs={name:[INITIAL]+[_decimal(d['nav']) for d in value['portfolios'][name]['days']] for name in names}
        for name in sorted(names):
            independent=reconstruct_metrics(navs[name],navs['spy60']);_metrics(value['portfolios'][name]['metrics'],independent)
            recorded=reconstruct_metrics(recorded_navs[name],recorded_navs['spy60'])
            _metrics(recorded,independent);_metrics(value['portfolios'][name]['metrics'],recorded)
            summaries[name]['metrics']=independent
        report={'schema':'synthetic-accounting-audit-v1','status':'VERIFIED_PASS','scope':'SYNTHETIC_RECORDED_FILL_ACCOUNTING',
            'financial_accepted':False,'full_M3':False,'replay_sha256':result.sha256,'market_sha256':market.sha256,'counts':counts,'portfolios':summaries,
            'tolerances':{'scalar_atol':'0.0000000001','scalar_rtol':'0.00000001','daily_return_atol':'0.00000001','quantities_dates_action_ids_raw_references_zero_fees':'EXACT'},
            'gates':{'recorded_fill_accounting':'VERIFIED_PASS','strategy_selection':'UNVERIFIED','feature_label_model_provenance':'UNVERIFIED',
                'checkpoint_and_holding_intervals':'UNVERIFIED','real_data_qualification':'UNVERIFIED','independent_native_auditor_identity':'UNVERIFIED','clean_locked_rerun':'UNVERIFIED','complete_campaign_and_shortlist':'UNVERIFIED'},
            'assumptions':['SYNTHETIC_ONLY','SIMULATED_AVAILABILITY','ZERO_FEES','HISTORICAL_REFERENCE_FILLS','NO_CONTINUOUS_INTRADAY_RISK','HASH_BINDING_NOT_AUTHENTICATED_ORIGIN']}
        body=canonical(report);_require(len(body)<=MAX_BYTES,'AUDIT_OUTPUT_BOUND');return AccountingAudit(body,hashlib.sha256(body).hexdigest())
    except (ValueError,TypeError,KeyError,AttributeError,IndexError,DecimalException,RecursionError) as exc:
        if isinstance(exc,DataError) and exc.code.startswith('AUDIT_'):raise
        raise DataError('AUDIT_INPUT_INVALID') from None
