"""Exact pure pretrade checks for deterministic fake observations only."""
from decimal import Decimal as D
import hashlib
from .data.encoding import canonical
from .domain import ExecutionIntent,ExecutionObservation,ExecutionInputs,ExecutionDecision,ContractError
from .execution_contracts import instant,WATCHLIST,TERMINAL,calendar_reasons,record_sha256
from .simulation.policy import fixed_decimal,number,buy_quantity


def snapshot_sha256(observation):
    if type(observation) is not ExecutionObservation:raise ContractError('INVALID_EXECUTION_RECORD')
    return hashlib.sha256(canonical(observation.to_payload())).hexdigest()


def client_order_id(intent):
    if type(intent) is not ExecutionIntent:raise ContractError('INVALID_EXECUTION_RECORD')
    p=intent.to_payload()
    return 'cmp-'+hashlib.sha256(canonical(dict(scope=p['scope'],account_alias=p['account_alias'],intent_id=p['intent_id']))).hexdigest()[:40]


def control_health(observation,*,now,calendar=None):
    if type(observation) is not ExecutionObservation:raise ContractError('INVALID_EXECUTION_RECORD')
    o=observation.to_payload();at=instant(now);reasons=calendar_reasons(observation,calendar)
    def require(ok,reason):
        if not ok and reason not in reasons:reasons.append(reason)
    def fresh(value,seconds):return 0<=(at-instant(value)).total_seconds()<=seconds
    h=o['health'];a=o['authority'];clock=o['clock'];account=o['account']
    for name,code in [('connected','OFFLINE'),('account_enabled','ACCOUNT_BLOCKED'),('durable','DURABILITY_UNVERIFIED'),('resources_ok','RESOURCE_BLOCKED'),('exclusive_owner','OWNER_UNVERIFIED'),('journal_reserved','JOURNAL_UNRESERVED')]:require(h[name],code)
    for name in ('execution_at','watchdog_at'):require(fresh(h[name],15),'HEARTBEAT_STALE')
    require(fresh(h['supervision_at'],300),'SUPERVISION_EXPIRED')
    require(fresh(o['observed_at'],30) and fresh(account['reconciled_at'],30),'RECONCILIATION_STALE')
    require(clock['calendar_verified'] and fresh(clock['observed_at'],30),'CALENDAR_UNVERIFIED')
    require(abs((instant(clock['broker_at'])-instant(clock['observed_at'])).total_seconds())<=5,'CLOCK_MISMATCH')
    require(a['ownership_complete'] and not a['foreign_activity'],'OWNERSHIP_UNVERIFIED')
    require(not a['unknown_intents'] and all(order['status']!='UNKNOWN' for order in o['orders']),'UNKNOWN_INTENT')
    require(all(order['owned'] for order in o['orders']),'FOREIGN_ORDER')
    require(all(D(p['quantity'])==p['owned_quantity'] for p in o['positions']),'FOREIGN_POSITION')
    return reasons


@fixed_decimal
def assess(intent,observation,*,now,calendar=None,inputs=None):
    if type(intent) is not ExecutionIntent or type(observation) is not ExecutionObservation:raise ContractError('INVALID_EXECUTION_RECORD')
    i=intent.to_payload();o=observation.to_payload();at=instant(now);reasons=[]
    def require(ok,reason):
        if not ok and reason not in reasons:reasons.append(reason)
    def fresh(value,seconds):return 0<=(at-instant(value)).total_seconds()<=seconds
    require(i['account_alias']==o['account_alias'] and i['generation']==o['generation'],'ACCOUNT_OR_GENERATION')
    require(i['snapshot_sha256']==snapshot_sha256(observation),'SNAPSHOT_CHANGED')
    require(instant(i['created_at'])<=at<instant(i['expires_at']),'INTENT_EXPIRED')
    reasons.extend(control_health(observation,now=now,calendar=calendar))
    h=o['health'];a=o['authority'];clock=o['clock'];account=o['account']
    if i['kind']!='STRATEGY':raise ContractError('CONTROL_PLAN_REQUIRED')
    else:
        require(a['armed'] and not a['halted'],'STRATEGY_DISARMED')
        require(a['strategy_admitted'] and i['strategy_sha256']==a['strategy_sha256'],'STRATEGY_UNQUALIFIED')
        require(i['authorization_sha256']==a['authorization_sha256'] and i['rebalance_id']==a['rebalance_id'],'AUTHORIZATION_CHANGED')
        require(instant(clock['strategy_open_at'])<=at<instant(clock['strategy_close_at']),'STRATEGY_WINDOW')
        require(account['submissions']<6,'SUBMISSION_LIMIT')
        require(i['symbol'] in WATCHLIST,'SYMBOL_INELIGIBLE')
        require(type(inputs) is ExecutionInputs,'STRATEGY_INPUTS_REQUIRED')
        if type(inputs) is ExecutionInputs:
            from datetime import timedelta
            facts=inputs.to_payload();pin=record_sha256(inputs);entry=instant(clock['strategy_open_at'])
            require(i['inputs_sha256']==a['inputs_sha256']==pin,'STRATEGY_INPUTS_CHANGED')
            require(all(facts[k]==i[k] for k in ('strategy_sha256','authorization_sha256','rebalance_id')),'STRATEGY_INPUTS_CHANGED')
            require(facts['calendar_sha256']==clock['calendar_sha256'] and facts['session_date']==entry.date().isoformat(),'INPUT_SESSION_CHANGED')
            require(facts['feature_session']==clock['prior_session'] and instant(facts['feature_available_at'])<=entry-timedelta(minutes=10) and instant(facts['decision_at'])==entry-timedelta(minutes=10) and instant(facts['decision_at'])<=instant(facts['bundle_finalized_at'])<entry,'FEATURES_UNQUALIFIED')
            require(instant(facts['arm_expires_at'])==instant(clock['session_close_at']) and at<instant(facts['arm_expires_at']),'ARM_EXPIRED')
            securities={v['symbol']:v for v in facts['securities']};selected=securities.get(i['symbol'])
            require(selected is not None and selected['feature_sessions']>=252 and D(selected['raw_close'])>=5 and D(selected['mean_dollar_volume'])>=1000000 and all(selected[k] for k in ('tradable','actions_verified','mapping_verified')),'SYMBOL_INELIGIBLE')
            require(all(q['symbol'] in securities and q['sector']==securities[q['symbol']]['sector'] for q in o['quotes']),'SECTOR_MAPPING_CHANGED')
    quotes={q['symbol']:q for q in o['quotes']};positions={p['symbol']:p['owned_quantity'] for p in o['positions']}
    orders=[v for v in o['orders'] if v['status'] not in TERMINAL]
    needed=set(positions)|{i['symbol']}|{v['symbol'] for v in orders}
    require(needed<=quotes.keys(),'QUOTE_MISSING')
    for symbol in needed&quotes.keys():
        q=quotes[symbol];require(q['feed']==o['feed'] and fresh(q['observed_at'],30) and D(q['ask'])>=D(q['bid'])>0,'QUOTE_INVALID')
    cash=D(account['sleeve_cash']);broker_cash=D(account['broker_cash']);prior=D(account['prior_close_nav']);peak=D(account['prior_peak_nav'])
    require(cash>=0 and broker_cash>=0 and prior>0 and peak>0,'CAPITAL_UNVERIFIED')
    nav=loss=drawdown=None;maximum=0;reserved=D(0);cap=D(0);exposure={};gross=D(0);cash_free=D(0)
    if needed<=quotes.keys() and all(D(quotes[s]['ask'])>=D(quotes[s]['bid'])>0 for s in needed) and cash>=0 and prior>0 and peak>0:
        exposure={s:D(qty)*D(quotes[s]['bid']) for s,qty in positions.items()};nav=cash+sum(exposure.values(),D(0))+D(account['dividend_receivables'])-D(account['undebited_liabilities'])
        require(nav>0,'INVALID_NAV')
        if nav>0:
            loss=max(D(0),1-nav/prior);drawdown=1-nav/max(peak,nav)
            if i['kind']=='STRATEGY':require(loss<D('.02'),'DAILY_LOSS');require(drawdown<D('.10'),'DRAWDOWN')
            pending_cash=D(0)
            for order in orders:
                if order['side']=='buy':
                    value=D(order['quantity']-order['filled_quantity'])*D(quotes[order['symbol']]['ask'])*D('1.001')*D('1.01')
                    pending_cash+=value;exposure[order['symbol']]=exposure.get(order['symbol'],D(0))+value
            gross=sum(exposure.values(),D(0));sectors={}
            for s,value in exposure.items():sectors[quotes[s]['sector']]=sectors.get(quotes[s]['sector'],D(0))+value
            if i['kind']=='STRATEGY':
                require(gross<=nav*D('.6'),'EXISTING_GROSS_LIMIT');require(all(v<=nav*D('.2') for v in exposure.values()),'EXISTING_NAME_LIMIT');require(all(v<=nav*D('.4') for v in sectors.values()),'EXISTING_SECTOR_LIMIT')
            q=quotes[i['symbol']];volume=D(q['mean_dollar_volume'])
            require(q['liquidity_verified'] and q['liquidity_sessions']==20 and q['liquidity_as_of']==clock['prior_session'] and volume>0,'LIQUIDITY_UNVERIFIED')
            if type(inputs) is ExecutionInputs:
                require(volume>=1000000 and selected is not None and volume==D(selected['mean_dollar_volume']),'LIQUIDITY_UNVERIFIED')
            cap=max(D(0),min(D(2000),volume*D('.01')));cash_free=max(D(0),min(cash,broker_cash)-pending_cash-D(account['undebited_liabilities']))
            if i['side']=='buy':
                unit=D(q['ask'])*D('1.001')*D('1.01');reserved=D(i['quantity'])*unit
                name=exposure.get(i['symbol'],D(0));sector=sectors.get(q['sector'],D(0))
                budget=max(D(0),min(cap,cash_free,nav*D('.6')-gross,nav*D('.2')-name,nav*D('.4')-sector))
                maximum=buy_quantity(budget,D(q['ask']),D('.001'))
                require(reserved<=cash_free,'CASH_LIMIT');require(name+reserved<=nav*D('.2'),'NAME_LIMIT');require(gross+reserved<=nav*D('.6'),'GROSS_LIMIT');require(sector+reserved<=nav*D('.4'),'SECTOR_LIMIT')
            elif i['side']=='sell':
                pending=sum(v['quantity']-v['filled_quantity'] for v in orders if v['side']=='sell' and v['symbol']==i['symbol'])
                available=max(0,positions.get(i['symbol'],0)-pending);reserved=D(i['quantity'])*D(q['bid']);maximum=min(available,int(cap/D(q['bid'])))
                require(i['quantity']<=available,'OWNED_QUANTITY')
            require(reserved<=cap,'INTENT_NOTIONAL_CAP')
    return ExecutionDecision(dict(schema_version='1',record_type='ExecutionDecision',currency='USD',account_alias=o['account_alias'],generation=o['generation'],kind='STRATEGY',evaluated_at=now,dependencies={k:record_sha256(v) for k,v in [('calendar',calendar),('inputs',inputs)] if v is not None},scope='DETERMINISTIC_FAKE',allowed=not reasons,reasons=reasons,maximum_quantity=maximum,reserved_notional=number(reserved),intent_notional_cap=number(cap),risk_nav=None if nav is None else number(nav),daily_loss=None if loss is None else number(loss),drawdown=None if drawdown is None else number(drawdown),existing_projected_exposure={s:number(v) for s,v in sorted(exposure.items())},existing_projected_gross=number(gross),unreserved_cash=number(cash_free),snapshot_sha256=snapshot_sha256(observation),intent_sha256=hashlib.sha256(canonical(i)).hexdigest(),client_order_id=client_order_id(intent),financial_accepted=False))
