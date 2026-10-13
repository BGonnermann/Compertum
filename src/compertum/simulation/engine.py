"""Deterministic, bounded historical fill assumptions over synthetic snapshots."""
from dataclasses import dataclass,field
from decimal import Decimal as D,localcontext
import hashlib

from compertum.data.calendar import session_times,utc_time
from compertum.data.errors import DataError
from compertum.data.snapshot import canonical
from .market import load_market
from .metrics import metrics
from .policy import EPS,INITIAL,buy_quantity,exposure_reason,number,qualifies,fixed_decimal


@dataclass(frozen=True)
class ReplayResult:
    content:bytes
    sha256:str


@dataclass
class Ledger:
    name:str
    cash:D=INITIAL
    positions:dict=field(default_factory=dict)
    basis:dict=field(default_factory=dict)
    receivables:dict=field(default_factory=dict)
    trades:list=field(default_factory=list)
    actions:list=field(default_factory=list)
    observations:list=field(default_factory=list)
    days:list=field(default_factory=list)
    omissions:list=field(default_factory=list)
    signals:list=field(default_factory=list)
    checkpoints:list=field(default_factory=list)
    halt:dict|None=None
    high:D=INITIAL
    previous_close:D=INITIAL
    interval_symbols:tuple=()
    completed_intervals:int=0

    def marks(self,market,day,reference):
        return {s:market.reference(s,day,reference) for s,q in self.positions.items() if q}

    def nav(self,prices):
        nav=self.cash+sum(q*prices[s] for s,q in self.positions.items() if q)+sum(v['amount'] for v in self.receivables.values())
        if nav<=0:raise DataError('INVALID_NAV')
        return nav

    def observe(self,market,day,phase):
        prices=self.marks(market,day,'close' if phase=='close' else 'entry');nav=self.nav(prices)
        self.high=max(self.high,nav)
        loss=max(D(0),1-nav/self.previous_close);drawdown=1-nav/self.high
        if self.name=='momentum' and self.halt is None:
            reason=('DAILY_LOSS' if loss>=D('.02')-EPS else 'DRAWDOWN' if drawdown>=D('.10')-EPS else exposure_reason(self.positions,prices,market.sectors,nav,self.cash))
            if reason:self.halt={'session':day,'phase':phase,'reason':reason}
        self.observations.append({'session':day,'phase':phase,'nav':number(nav),'daily_loss':number(loss),'drawdown':number(drawdown)})
        return nav

    def apply_actions(self,market,day):
        for a in market.actions:
            s=a['symbol'];q=self.positions.get(s,0)
            if a['effective_session']!=day or not q:continue
            if utc_time(a['simulated_known_at'])>session_times(day).decision:raise DataError('ACTION_UNAVAILABLE')
            if a['kind']=='SPLIT':
                quantity=q*D(a['factor'])
                if quantity!=int(quantity):raise DataError('FRACTIONAL_ENTITLEMENT')
                self.positions[s]=int(quantity)
                self.actions.append({'session':day,'action_id':a['action_id'],'kind':'SPLIT','symbol':s,'quantity':int(quantity),'basis':number(self.basis[s])})
            else:
                amount=q*D(a['amount'])
                self.receivables[a['action_id']]={'amount':amount,'pay_date':a['pay_date']}
                self.actions.append({'session':day,'action_id':a['action_id'],'kind':'DIVIDEND_RECEIVABLE','symbol':s,'amount':number(amount)})
        for key,claim in list(self.receivables.items()):
            if claim['pay_date']<=day:
                self.cash+=claim['amount'];del self.receivables[key]
                self.actions.append({'session':day,'action_id':key,'kind':'DIVIDEND_CASH','amount':number(claim['amount'])})

    def fill(self,market,day,symbol,quantity,side,cost,terminal=False):
        reference=market.reference(symbol,day,'entry');price=reference*(1+cost if side=='BUY' else 1-cost)
        amount=quantity*price;fee=market.trade_fee(day,quantity,price,side);old=self.positions.get(symbol,0)
        before=self.nav(self.marks(market,day,'entry'))
        if side=='BUY':
            if amount+fee>self.cash:raise DataError('CASH_OVERDRAW')
            self.cash-=amount+fee;self.positions[symbol]=old+quantity
            self.basis[symbol]=self.basis.get(symbol,D(0))+amount
        else:
            if quantity>old:raise DataError('SHORT_POSITION')
            self.cash+=amount-fee;self.positions[symbol]=old-quantity
            self.basis[symbol]*=D(old-quantity)/old
            if not self.positions[symbol]:del self.positions[symbol];del self.basis[symbol]
        self.trades.append({'session':day,'at':session_times(day).entry.isoformat(),'symbol':symbol,'side':side,'quantity':quantity,
            'reference':number(reference),'fill_price':number(price),'fee':number(fee),'price_cost':number(quantity*reference*cost),
            'turnover':number(quantity*reference/before),'analytic_terminal':terminal,'fill_assumption':'SAME_FEED_MINUTE_OPEN_ADVERSE'})
        self.observe(market,day,'post_fill')


def _targets(ledger,market,day,features,cost,can_enter):
    if not can_enter:return {}
    nav=ledger.nav(ledger.marks(market,day,'entry'))
    if ledger.name=='momentum':
        selected={};sector_counts={}
        ranked=sorted(features,key=lambda s:(-features[s]['prediction'],s))
        for s in ranked:
            prediction=features[s]['prediction']
            if not qualifies(prediction,cost):continue
            sector=market.sectors[s]
            if sector_counts.get(sector,0)>=2:
                ledger.omissions.append({'session':day,'symbol':s,'reason':'SECTOR_TARGET_LIMIT'});continue
            ref=market.reference(s,day,'entry')
            q=buy_quantity(nav*D('.2'),ref,cost)
            cap=int(min(D(2000),features[s]['dollar_volume']*D('.01'))/(ref*(1+cost)*D('1.01')))
            if q<=0 or cap<=0:
                ledger.omissions.append({'session':day,'symbol':s,'reason':'WHOLE_SHARE_OR_INTENT_LIMIT'});continue
            selected[s]=q;sector_counts[sector]=sector_counts.get(sector,0)+1
            if len(selected)==3:break
        return selected
    if ledger.name in ('spy60','spy100'):
        weight=D('.6') if ledger.name=='spy60' else D(1)
        return {'SPY':buy_quantity(nav*weight,market.reference('SPY',day,'entry'),cost)}
    if ledger.name=='equal60':
        symbols=[s for s in market.symbols if s!='SPY']
        return {s:buy_quantity(nav*D('.6')/len(symbols),market.reference(s,day,'entry'),cost) for s in symbols}
    return {}


def _rebalance(ledger,market,day,targets,cost,terminal=False):
    count=0;strategy=ledger.name=='momentum'
    for side in ('SELL','BUY'):
        symbols=sorted(ledger.positions) if side=='SELL' else list(targets)
        for s in symbols:
            delta=targets.get(s,0)-ledger.positions.get(s,0)
            remaining=max(0,-delta if side=='SELL' else delta)
            while remaining:
                if strategy and not terminal and (ledger.halt or count>=6):
                    ledger.omissions.append({'session':day,'symbol':s,'reason':'HALTED' if ledger.halt else 'SUBMISSION_LIMIT'});break
                ref=market.reference(s,day,'entry')
                # Analytic terminal exits have no broker intents. Ordinary strategy
                # children, including reductions, retain the intent-notional cap.
                cap=int(min(D(2000),market.liquidity(s,day)*D('.01'))/(ref*(1+cost))) if strategy and not terminal else remaining
                q=min(remaining,cap)
                if side=='BUY':
                    nav=ledger.nav(ledger.marks(market,day,'entry'))
                    budget=ledger.cash
                    if strategy:
                        prices=ledger.marks(market,day,'entry');values={k:v*prices[k] for k,v in ledger.positions.items()}
                        sector_value=sum(v for k,v in values.items() if market.sectors[k]==market.sectors[s])
                        budget=min(budget,max(D(0),ledger.cash-nav*D('.4')),max(D(0),nav*D('.2')-values.get(s,D(0))),
                            max(D(0),nav*D('.6')-sum(values.values())),max(D(0),nav*D('.4')-sector_value))
                    q=min(q,buy_quantity(budget,ref,cost))
                if q<=0:
                    ledger.omissions.append({'session':day,'symbol':s,'reason':'INSUFFICIENT_CAPACITY'});break
                ledger.fill(market,day,s,q,side,cost,terminal);count+=1;remaining-=q


@fixed_decimal
def replay(chunks,sectors,start,end,horizon,*,cost_bps=10):
    """Return immutable synthetic results; all dates inclusive and no I/O performed."""
    return _replay_market(load_market(chunks,sectors),start,end,horizon,cost_bps=cost_bps)


@fixed_decimal
def _replay_market(market,start,end,horizon,*,cost_bps=10):
    if type(horizon) is not int or horizon not in (1,5,21) or type(cost_bps) is not int or cost_bps not in (10,20):
        raise DataError('INVALID_PROTOCOL')
    session_times(start);session_times(end)
    if end<start:raise DataError('INVALID_SEGMENT')
    dates=[start]
    while dates[-1]!=end:
        if len(dates)>=1024:raise DataError('INPUT_BOUND')
        dates.append(session_times(dates[-1]).next_date)
    with localcontext() as ctx:
        ctx.prec=28
        cost=D(cost_bps)/10000
        ledgers={name:Ledger(name) for name in ('momentum','spy60','spy100','equal60','zero')};anchor=None
        for index,day in enumerate(dates):
            # Benchmark reference coverage is mandatory even on all-cash days.
            market.reference('SPY',day,'entry');market.reference('SPY',day,'close')
            features={};omissions=[]
            for s in market.symbols:
                if s=='SPY':continue
                f,reason=market.features(s,day,horizon)
                if reason:omissions.append({'session':day,'symbol':s,'reason':reason})
                else:features[s]=f
            if anchor is None and features:anchor=index
            checkpoint=anchor is not None and (index-anchor)%horizon==0
            terminal=index==len(dates)-1
            for name,ledger in ledgers.items():
                ledger.apply_actions(market,day);ledger.observe(market,day,'entry')
                if checkpoint:
                    ledger.checkpoints.append(index)
                    if name=='momentum':
                        if not ledger.halt:ledger.completed_intervals+=sum(ledger.positions.get(s,0)>0 for s in ledger.interval_symbols)
                        ledger.interval_symbols=()
                        ledger.omissions.extend(omissions)
                        ledger.signals.append({'session':day,'decision_at':session_times(day).decision.isoformat(),
                            'predictions':{s:number(f['prediction']) for s,f in sorted(features.items())}})
                    if not ledger.halt and (name not in ('spy100','equal60') or index==anchor):
                        targets=_targets(ledger,market,day,features,cost,index+horizon<len(dates))
                        _rebalance(ledger,market,day,targets,cost)
                    if name=='momentum' and not ledger.halt and index+horizon<len(dates):ledger.interval_symbols=tuple(ledger.positions)
                if terminal:
                    _rebalance(ledger,market,day,{},cost,terminal=True)
                nav=ledger.observe(market,day,'close');ledger.previous_close=nav
                ledger.days.append({'session':day,'nav':number(nav),'cash':number(ledger.cash),
                    'receivables':number(sum(v['amount'] for v in ledger.receivables.values())),
                    'positions':dict(sorted(ledger.positions.items())),'basis':{s:number(b) for s,b in sorted(ledger.basis.items())}})
        benchmark=[INITIAL]+[D(d['nav']) for d in ledgers['spy60'].days]
        portfolios={}
        for name,ledger in ledgers.items():
            portfolios[name]={k:getattr(ledger,k) for k in ('trades','actions','observations','days','signals','omissions','checkpoints','halt','completed_intervals')}
            portfolios[name]['metrics']=metrics([INITIAL]+[D(d['nav']) for d in ledger.days],benchmark)
        value={'schema_version':'1','policy':'momentum-synthetic-v1','financial_status':'SYNTHETIC_UNVERIFIED',
            'market_sha256':market.sha256,'sectors':market.sectors,'start':start,'end':end,'horizon':horizon,'cost_bps':cost_bps,
            'ledger_precision':28,'ledger_rounding':'ROUND_HALF_EVEN',
            'assumptions':['SYNTHETIC_ACTIVE_TRADABLE_ASSETS','SYNTHETIC_SECTORS','ZERO_UNVERIFIED_FEES','NO_INTEREST_OR_FINANCING',
                'HISTORICAL_REFERENCE_FILLS','NO_CONTINUOUS_INTRADAY_RISK','NO_PROVIDER_COVERAGE_ACCEPTANCE','NO_LIVE_PLANNER_PARITY'],
            'portfolios':portfolios}
        value.update(market.replay_metadata())
        content=canonical(value)
        if len(content)>16*1024*1024:raise DataError('OUTPUT_BOUND')
        return ReplayResult(content,hashlib.sha256(content).hexdigest())
