"""Independent exact trade-policy audit composed with source/accounting checks."""
from dataclasses import dataclass
from decimal import Decimal as D,DecimalException
import hashlib,json,math
from .data.errors import DataError
from .data.encoding import canonical
from .data.calendar import session_times,utc_time
from .simulation.market import load_market
from .simulation.engine import ReplayResult
from .audit import audit_accounting,_precision,ABS
from .audit_predictions import audit_candidate_predictions,SourceEvidence,_dates,_compare,_exact,_near,_training
from .modeling.registry import variant

@dataclass(frozen=True)
class ExecutionAudit:
    content:bytes
    sha256:str


def _expect(condition):
    if not condition:raise DataError('AUDIT_POLICY_MISMATCH')


def _quantity(budget,reference,cost):
    _expect(budget>=0 and reference>0)
    return int(budget/(reference*(1+cost)*D('1.01')))


def _liquidity(market,symbol,day):
    times=session_times(day);date=times.previous_date;total=D(0)
    for _ in range(20):
        row=market.rows.get((symbol,date,'daily'))
        if row is None or any(utc_time(row[f])>times.decision for f in ('simulated_available_at','simulated_revision_available_at')):raise DataError('LIQUIDITY_UNAVAILABLE')
        total+=D(row['close'])*D(row['volume']);date=session_times(date).previous_date
    return total/20


def _qualified_order(predictions,cost):
    values={s:D(str(p)) for s,p in predictions.items()}
    return sorted((s for s,p in values.items() if p-(2*cost+D('.001'))>ABS),key=lambda s:(-values[s],s))


class _DecisionBook:
    """Reconstruct decisions without consulting reported quantities or balances."""
    def __init__(self,market,name,cost):
        self.market=market;self.name=name;self.strategy=name in ('momentum','strategy');self.cost=cost
        self.cash=D(10000);self.positions={};self.claims={};self.high=D(10000);self.previous=D(10000);self.halt=None
        self.trades=[];self.omissions=[];self.signals=[];self.checkpoints=[];self.intervals=[];self.open_interval=None

    def values(self,day,phase='entry'):
        return {s:q*self.market.reference(s,day,phase) for s,q in self.positions.items()}

    def nav(self,day,phase='entry'):
        return self.cash+sum(self.values(day,phase).values())+sum(a for a,_ in self.claims.values())

    def observe(self,day,phase):
        values=self.values(day,'close' if phase=='close' else 'entry');nav=self.cash+sum(values.values())+sum(a for a,_ in self.claims.values())
        _expect(nav>0);self.high=max(self.high,nav)
        if self.strategy and self.halt is None:
            checks=[('DAILY_LOSS',max(D(0),1-nav/self.previous)>=D('.02')-ABS),('DRAWDOWN',1-nav/self.high>=D('.10')-ABS),('INVALID_NAV',self.cash<0),('GROSS_LIMIT',sum(values.values())/nav>=D('.6')-ABS),('NAME_LIMIT',any(v/nav>=D('.2')-ABS for v in values.values())),('SECTOR_LIMIT',any(sum(v for s,v in values.items() if self.market.sectors[s]==sector)/nav>=D('.4')-ABS for sector in set(self.market.sectors.values())))]
            for reason,violated in checks:
                if violated:self.halt={'session':day,'phase':phase,'reason':reason};break
        return nav

    def actions(self,day):
        for action in self.market.actions:
            symbol=action['symbol'];q=self.positions.get(symbol,0)
            if action['effective_session']!=day or not q:continue
            _expect(utc_time(action['simulated_known_at'])<=session_times(day).decision)
            if action['kind']=='SPLIT':
                quantity=q*D(action['factor']);_expect(quantity==int(quantity));self.positions[symbol]=int(quantity)
            else:self.claims[action['action_id']]=(q*D(action['amount']),action['pay_date'])
        for key,(amount,pay) in list(self.claims.items()):
            if pay<=day:self.cash+=amount;del self.claims[key]

    def omit(self,day,symbol,reason):self.omissions.append({'session':day,'symbol':symbol,'reason':reason})

    def fill(self,day,symbol,side,quantity,terminal):
        reference=self.market.reference(symbol,day,'entry');amount=quantity*reference*(1+self.cost if side=='BUY' else 1-self.cost)
        old=self.positions.get(symbol,0)
        if side=='BUY':self.cash-=amount;self.positions[symbol]=old+quantity
        else:
            _expect(old>=quantity);self.cash+=amount
            if old==quantity:del self.positions[symbol]
            else:self.positions[symbol]=old-quantity
        self.trades.append({'session':day,'at':session_times(day).entry.isoformat(),'symbol':symbol,'side':side,'quantity':quantity,'analytic_terminal':terminal})
        self.observe(day,'post_fill')

    def target(self,day,features,can_enter):
        if not can_enter:return {}
        nav=self.nav(day)
        if self.strategy:
            targets={};sector_counts={}
            for symbol in sorted(features,key=lambda s:(-features[s]['prediction'],s)):
                data=features[symbol]
                if data['prediction']-(2*self.cost+D('.001'))<=ABS:continue
                sector=self.market.sectors[symbol]
                if sector_counts.get(sector,0)==2:self.omit(day,symbol,'SECTOR_TARGET_LIMIT');continue
                ref=self.market.reference(symbol,day,'entry');q=_quantity(nav/5,ref,self.cost)
                feasible=_quantity(min(D(2000),data['dollar_volume']/100),ref,self.cost)
                if not q or not feasible:self.omit(day,symbol,'WHOLE_SHARE_OR_INTENT_LIMIT');continue
                targets[symbol]=q;sector_counts[sector]=sector_counts.get(sector,0)+1
                if len(targets)==3:break
            return targets
        if self.name.startswith('spy'):
            return {'SPY':_quantity(nav*(D('.6') if self.name=='spy60' else 1),self.market.reference('SPY',day,'entry'),self.cost)}
        if self.name=='equal60':
            symbols=[s for s in self.market.symbols if s!='SPY']
            return {s:_quantity(nav*D('.6')/len(symbols),self.market.reference(s,day,'entry'),self.cost) for s in symbols}
        return {}

    def rebalance(self,day,targets,source,terminal=False):
        submissions=0
        for side,symbols in [('SELL',sorted(self.positions)),('BUY',list(targets))]:
            for symbol in symbols:
                desired=targets.get(symbol,0)-self.positions.get(symbol,0)
                remaining=max(0,desired if side=='BUY' else -desired)
                while remaining:
                    if self.strategy and not terminal and (self.halt or submissions==6):
                        self.omit(day,symbol,'HALTED' if self.halt else 'SUBMISSION_LIMIT');break
                    ref=self.market.reference(symbol,day,'entry');q=remaining
                    if self.strategy and not terminal:
                        liquidity=_liquidity(self.market,symbol,day)
                        q=min(q,int(min(D(2000),liquidity/100)/(ref*(1+self.cost))))
                    if side=='BUY':
                        budget=self.cash
                        if self.strategy:
                            nav=self.nav(day);values=self.values(day);sector=sum(v for s,v in values.items() if self.market.sectors[s]==self.market.sectors[symbol])
                            budget=min(budget,max(D(0),self.cash-nav*D('.4')),max(D(0),nav/5-values.get(symbol,D(0))),max(D(0),nav*D('.6')-sum(values.values())),max(D(0),nav*D('.4')-sector))
                        q=min(q,_quantity(budget,ref,self.cost))
                    if not q:self.omit(day,symbol,'INSUFFICIENT_CAPACITY');break
                    self.fill(day,symbol,side,q,terminal);remaining-=q;submissions+=1


def _decision_features(source,day,h,model):
    features={};omissions=[]
    for symbol in source.market.symbols:
        if symbol=='SPY':continue
        try:
            prediction=source.baseline(symbol,day,h);rows=source.history(symbol,day)
            if model is not None:
                f=source.features(symbol,day)
                if not f['raw_eligible']:raise DataError('INELIGIBLE_RAW_PRICE_OR_VOLUME')
                prediction=D(str(math.fsum((x-mean)/scale*coef for x,mean,scale,coef in zip(f['values'],model['scaler']['mean'],model['scaler']['scale'],model['ridge']['coef']))+model['ridge']['intercept']))
            features[symbol]={'prediction':prediction,'dollar_volume':sum(D(r['close'])*D(r['volume']) for r in rows[:20])/20}
        except DataError as exc:omissions.append({'session':day,'symbol':symbol,'reason':exc.code})
    return features,omissions


@_precision
def _policy(market,value,model):
    """Internal exact-decision primitive. Public audit first verifies provenance."""
    return _policy_dates(market,value,model,_dates(value['start'],value['end']))


@_precision
def _policy_dates(market,value,model,dates,source=None):
    """Private arithmetic; generated caller derives dates from the closed recipe."""
    h=value['horizon'];cost=D(value['cost_bps'])/10000
    if source is None:source=SourceEvidence(market)
    strategy='momentum' if value['policy']=='momentum-synthetic-v1' else 'strategy'
    names=(strategy,'spy60','spy100','equal60','zero');books={name:_DecisionBook(market,name,cost) for name in names};anchor=None
    _expect(type(h) is int and h in (1,5,21) and cost in (D('.001'),D('.002')) and set(value['portfolios'])==set(names))
    for index,day in enumerate(dates):
        features,omissions=_decision_features(source,day,h,model)
        if anchor is None and features:anchor=index
        checkpoint=anchor is not None and (index-anchor)%h==0
        for name,book in books.items():
            book.actions(day);book.observe(day,'entry')
            if checkpoint:
                book.checkpoints.append(index)
                if book.strategy:
                    if book.open_interval is not None and book.halt is None:
                        start,symbols=book.open_interval;_expect(index-start==h)
                        book.intervals.extend({'symbol':s,'start_index':start,'end_index':index,'start_session':dates[start],'end_session':day} for s in symbols if book.positions.get(s,0)>0)
                    book.open_interval=None;book.omissions.extend(omissions)
                    book.signals.append({'session':day,'decision_at':session_times(day).decision.isoformat(),'predictions':{s:features[s]['prediction'] for s in sorted(features)}})
                if book.halt is None and (name not in ('spy100','equal60') or index==anchor):
                    book.rebalance(day,book.target(day,features,index+h<len(dates)),source)
                if book.strategy and book.halt is None and index+h<len(dates):book.open_interval=(index,tuple(book.positions))
            if index==len(dates)-1:book.rebalance(day,{},source,terminal=True)
            nav=book.observe(day,'close');book.previous=nav
            actual=value['portfolios'][name]['days'][index]
            _exact(actual['positions'],book.positions);_near(actual['cash'],book.cash);_near(actual['nav'],nav)
    summaries={}
    for name,book in books.items():
        actual=value['portfolios'][name]
        _exact(actual['checkpoints'],book.checkpoints);_exact(actual['completed_intervals'],len(book.intervals));_exact(actual['halt'],book.halt)
        _compare(actual['signals'],book.signals);_exact(actual['omissions'],book.omissions)
        for recorded,expected in zip(actual['signals'],book.signals):
            _exact(_qualified_order(recorded['predictions'],cost),_qualified_order(expected['predictions'],cost))
        fields={'session','at','symbol','side','quantity','analytic_terminal'}
        _exact([{k:t[k] for k in fields} for t in actual['trades']],book.trades)
        summaries[name]={'trades':len(book.trades),'omissions':len(book.omissions),'completed_intervals':len(book.intervals),'ending_cash':str(book.cash),'ending_nav':str(book.previous),'halt':book.halt}
    selected=books[strategy]
    return {'scope':'EXACT_SYNTHETIC_TRADE_POLICY','first_eligible_index':anchor,'checkpoints':selected.checkpoints,'holding_intervals':sorted(selected.intervals,key=lambda r:(r['start_index'],r['end_index'],r['symbol'])),'portfolios':summaries,'decision_tolerance':'EXACT_SYMBOL_QUANTITY_ORDER_GATE_AND_INTERVAL','interval_endpoint':'CHECKPOINT_ENTRY_BEFORE_NEW_REBALANCE'}


@_precision
def audit_execution(chunks,sectors,result,*,candidate_id,year,training_start,training_end,start,end,scoring_as_of):
    """Compose fresh original-source, independent accounting and policy evidence.

    This pure entry point does not accept caller-provided audit pass flags. Native
    auditor identity and complete campaign admission remain separate later gates.
    """
    try:
        prediction=audit_candidate_predictions(chunks,sectors,result,candidate_id=candidate_id,year=year,training_start=training_start,training_end=training_end,start=start,end=end,scoring_as_of=scoring_as_of)
        value=json.loads(result.content);market=load_market(chunks,sectors);costs={};independent_model=None
        candidate=variant(candidate_id)
        if candidate.kind=='ridge':
            _,fit=_training(SourceEvidence(market),candidate,year,training_start,training_end,value)
            independent_model={'scaler':{'mean':fit['mean'],'scale':fit['scale']},'ridge':{'coef':fit['coef'],'intercept':fit['intercept']}}
        for cost in ('10','20'):
            replay=value['replays'][cost];raw=canonical(replay);wrapped=ReplayResult(raw,hashlib.sha256(raw).hexdigest())
            accounting=audit_accounting(chunks,sectors,wrapped)
            policy=_policy(market,replay,independent_model)
            if independent_model is not None:_exact(_policy(market,replay,value['model']),policy)
            costs[cost]={'accounting_sha256':accounting.sha256,'accounting':json.loads(accounting.content),'policy':policy}
        report={'schema':'synthetic-execution-audit-v1','status':'VERIFIED_PASS','scope':'SYNTHETIC_CANDIDATE_SOURCE_ACCOUNTING_AND_POLICY','candidate_sha256':result.sha256,'prediction_audit_sha256':prediction.sha256,'prediction_audit':json.loads(prediction.content),'market_sha256':market.sha256,'costs':costs,'financial_accepted':False,'full_M3':False,
            'gates':{k:'UNVERIFIED' for k in ('independent_native_auditor_identity','clean_locked_campaign_reruns','complete_campaign_history','frozen_shortlist','actual_arrival_accuracy','fit_activation','financial_qualification')},
            'limitations':['SYNTHETIC_PARTIAL_WINDOWS','NO_CONTINUOUS_INTRADAY_RISK','NUMERICALLY_AMBIGUOUS_DISCRETE_DECISIONS_REFUSE_AUDIT','HASHES_DO_NOT_AUTHENTICATE_AUTHOR']}
        raw=canonical(report);_expect(len(raw)<=16*1024**2);return ExecutionAudit(raw,hashlib.sha256(raw).hexdigest())
    except (ValueError,TypeError,KeyError,AttributeError,IndexError,OverflowError,DecimalException,RecursionError) as exc:
        if isinstance(exc,DataError):raise
        raise DataError('AUDIT_EXECUTION_INVALID') from None
