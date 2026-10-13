"""Pure, immutable fake-account cancellation and finite long-close plans."""
from datetime import timedelta
from decimal import Decimal as D
from uuid import uuid4
import hashlib
from .domain import ExecutionObservation,ExecutionPlan,ExecutionAuthorization,ExecutionStart,ExecutionIntent,ExecutionDecision,ContractError
from .data.encoding import canonical
from .execution_contracts import instant,TERMINAL
from .simulation.policy import fixed_decimal,number
from .execution_risk import snapshot_sha256,control_health


def digest(record):
    return hashlib.sha256(canonical(record.to_payload())).hexdigest()


def economic_sha256(observation):
    """Ignore freshness timestamps, but bind balances, holdings and order state."""
    o=observation.to_payload()
    return hashlib.sha256(canonical(dict(account_alias=o['account_alias'],generation=o['generation'],
        cash={k:o['account'][k] for k in ('sleeve_cash','broker_cash','dividend_receivables','undebited_liabilities')},
        positions=sorted(o['positions'],key=lambda v:v['symbol']),orders=sorted(o['orders'],key=lambda v:v['order_id'])))).hexdigest()


def _fail(reasons):
    if reasons:raise ContractError(reasons[0])


def _quote(o,symbol,at):
    matches=[q for q in o['quotes'] if q['symbol']==symbol]
    if not matches:raise ContractError('QUOTE_MISSING')
    q=matches[0]
    if not(0<=(at-instant(q['observed_at'])).total_seconds()<=30 and q['feed']==o['feed'] and D(q['ask'])>=D(q['bid'])>0):raise ContractError('QUOTE_INVALID')
    if not(q['liquidity_verified'] and q['liquidity_sessions']==20 and q['liquidity_as_of']==o['clock']['prior_session'] and D(q['mean_dollar_volume'])>0):raise ContractError('LIQUIDITY_UNVERIFIED')
    return q,min(D(2000),D('.01')*D(q['mean_dollar_volume']))


@fixed_decimal
def build_plan(observation,*,kind,now,calendar=None):
    if type(observation) is not ExecutionObservation or kind not in ('CANCEL','CLOSE_LONG'):raise ContractError('INVALID_EXECUTION_RECORD')
    o=observation.to_payload();at=instant(now);_fail(control_health(observation,now=now,calendar=calendar))
    if not o['authority']['halted']:raise ContractError('HALT_REQUIRED')
    end=at+timedelta(minutes=10)
    if kind=='CLOSE_LONG':
        if not instant(o['clock']['session_open_at'])<=at<instant(o['clock']['session_close_at']):raise ContractError('REGULAR_SESSION_REQUIRED')
        end=min(end,instant(o['clock']['session_close_at']))
    positions=[];children=[]
    for position in sorted(o['positions'],key=lambda v:v['symbol']) if kind=='CLOSE_LONG' else []:
        quantity=position['owned_quantity']
        if not quantity:continue
        q,cap=_quote(o,position['symbol'],at);unit=D(q['ask'])*D('1.01');maximum=int(cap/unit);remaining=quantity
        while maximum and remaining and len(children)<12:
            take=min(remaining,maximum);index=len(children)
            children.append(dict(intent_id=str(uuid4()),index=index,symbol=q['symbol'],maximum_quantity=take,maximum_notional=number(cap),planned_notional=number(take*unit)))
            remaining-=take
        positions.append(dict(symbol=q['symbol'],quantity=quantity,cap=number(cap),bid=q['bid'],ask=q['ask'],planned_quantity=quantity-remaining,residual_quantity=remaining))
    return ExecutionPlan(dict(schema_version='1',record_type='ExecutionPlan',scope='DETERMINISTIC_FAKE',currency='USD',account_alias=o['account_alias'],generation=o['generation'],plan_id=str(uuid4()),kind=kind,created_at=at.isoformat(),start_expires_at=min(at+timedelta(seconds=60),end).isoformat(),deadline=end.isoformat(),snapshot_sha256=snapshot_sha256(observation),economic_sha256=economic_sha256(observation),calendar_sha256=o['clock']['calendar_sha256'],positions=positions,children=children,cancel_orders=[dict(intent_id=str(uuid4()),order_id=v['order_id'],symbol=v['symbol'],filled_quantity=v['filled_quantity']) for v in sorted(o['orders'],key=lambda v:v['order_id']) if v['status'] not in TERMINAL]))


def authorize_fake_plan(plan,observation,*,now,calendar=None,current_observation=None):
    """Retain reviewed evidence; check current authority at actual approval time."""
    current=observation if current_observation is None else current_observation
    if type(plan) is not ExecutionPlan or type(observation) is not ExecutionObservation or type(current) is not ExecutionObservation:raise ContractError('INVALID_EXECUTION_RECORD')
    p=plan.to_payload();o=observation.to_payload();live=current.to_payload();at=instant(now)
    _fail(control_health(current,now=now,calendar=calendar))
    if not all(v['authority']['halted'] and p['account_alias']==v['account_alias'] and p['generation']==v['generation'] for v in (o,live)):raise ContractError('PLAN_BINDING_CHANGED')
    if not instant(p['created_at'])<=at<instant(p['start_expires_at']):raise ContractError('PLAN_EXPIRED')
    if any(p['economic_sha256']!=economic_sha256(record) or p['calendar_sha256']!=record.to_payload()['clock']['calendar_sha256'] for record in (observation,current)):raise ContractError('PLAN_SNAPSHOT_CHANGED')
    if p['snapshot_sha256']!=snapshot_sha256(observation):raise ContractError('PLAN_SNAPSHOT_CHANGED')
    expected=build_plan(observation,kind=p['kind'],now=p['created_at'],calendar=calendar).to_payload()
    expected['plan_id']=p['plan_id']
    if len(expected['children'])==len(p['children']):
        for old,new in zip(p['children'],expected['children']):new['intent_id']=old['intent_id']
    if len(expected['cancel_orders'])==len(p['cancel_orders']):
        for old,new in zip(p['cancel_orders'],expected['cancel_orders']):new['intent_id']=old['intent_id']
    if expected!=p:raise ContractError('PLAN_ENVELOPE_CHANGED')
    return ExecutionAuthorization(dict(schema_version='1',record_type='ExecutionAuthorization',scope='DETERMINISTIC_FAKE',currency='USD',account_alias=p['account_alias'],generation=p['generation'],authorization_id=str(uuid4()),plan_id=p['plan_id'],plan_sha256=digest(plan),authorized_at=now,start_expires_at=p['start_expires_at'],snapshot_sha256=snapshot_sha256(observation),economic_sha256=p['economic_sha256']))


def start_operation(plan,authorization,observation,*,now,calendar=None):
    if not(type(plan) is ExecutionPlan and type(authorization) is ExecutionAuthorization and type(observation) is ExecutionObservation):raise ContractError('INVALID_EXECUTION_RECORD')
    p=plan.to_payload();a=authorization.to_payload();o=observation.to_payload();at=instant(now)
    _fail(control_health(observation,now=now,calendar=calendar))
    if not(o['authority']['halted'] and all(v['account_alias']==p['account_alias'] and v['generation']==p['generation'] for v in (a,o))):raise ContractError('PLAN_BINDING_CHANGED')
    if not(a['plan_id']==p['plan_id'] and a['plan_sha256']==digest(plan) and a['economic_sha256']==p['economic_sha256'] and a['start_expires_at']==p['start_expires_at']):raise ContractError('PLAN_AUTHORIZATION_CHANGED')
    if not instant(p['created_at'])<=instant(a['authorized_at'])<=at<instant(p['start_expires_at']):raise ContractError('PLAN_EXPIRED')
    if economic_sha256(observation)!=p['economic_sha256'] or o['clock']['calendar_sha256']!=p['calendar_sha256']:raise ContractError('PLAN_SNAPSHOT_CHANGED')
    return ExecutionStart(dict(schema_version='1',record_type='ExecutionStart',scope='DETERMINISTIC_FAKE',currency='USD',account_alias=p['account_alias'],generation=p['generation'],start_id=str(uuid4()),plan_id=p['plan_id'],plan_sha256=digest(plan),authorization_sha256=digest(authorization),started_at=now,deadline=p['deadline'],snapshot_sha256=snapshot_sha256(observation),economic_sha256=p['economic_sha256']))


@fixed_decimal
def assess_control(intent,observation,plan,authorization,*,start,now,calendar=None):
    """Owner supplies its durably retained operation start and prior order history."""
    if not(type(intent) is ExecutionIntent and type(observation) is ExecutionObservation and type(plan) is ExecutionPlan and type(authorization) is ExecutionAuthorization and type(start) is ExecutionStart):raise ContractError('INVALID_EXECUTION_RECORD')
    i=intent.to_payload();o=observation.to_payload();p=plan.to_payload();a=authorization.to_payload();started=start.to_payload();started_at=started['started_at'];at=instant(now);reasons=control_health(observation,now=now,calendar=calendar)
    def require(ok,reason):
        if not ok and reason not in reasons:reasons.append(reason)
    require(i['kind']==p['kind'] or (i['kind']=='CANCEL' and p['kind']=='CLOSE_LONG'),'PLAN_KIND_CHANGED')
    require(started['plan_id']==p['plan_id'] and started['plan_sha256']==digest(plan) and started['authorization_sha256']==digest(authorization) and started['deadline']==p['deadline'] and started['economic_sha256']==p['economic_sha256'],'OPERATION_START_CHANGED')
    require(all(v['account_alias']==p['account_alias'] and v['generation']==p['generation'] for v in (i,o,a,started)),'PLAN_BINDING_CHANGED')
    require(i['plan_id']==p['plan_id']==a['plan_id'] and a['plan_sha256']==digest(plan) and i['authorization_sha256']==digest(authorization),'PLAN_AUTHORIZATION_CHANGED')
    require(a['economic_sha256']==p['economic_sha256'] and a['start_expires_at']==p['start_expires_at'],'PLAN_AUTHORIZATION_CHANGED')
    require(instant(p['created_at'])<=instant(a['authorized_at'])<=instant(started_at)<instant(p['start_expires_at']) and instant(started_at)<=at<instant(p['deadline']),'PLAN_EXPIRED')
    require(instant(i['created_at'])<=at<instant(i['expires_at'])<=instant(p['deadline']),'INTENT_EXPIRED')
    require(i['snapshot_sha256']==snapshot_sha256(observation),'SNAPSHOT_CHANGED')
    require(o['authority']['halted'],'HALT_REQUIRED')
    require(p['calendar_sha256']==o['clock']['calendar_sha256'],'CALENDAR_CHANGED')
    orders={v['order_id']:v for v in o['orders']};maximum=0;notional=D(0)
    if i['kind']=='CANCEL':
        require(o['health']['broker_cancel_allowed'],'CANCELLATION_NOT_PERMITTED')
        targets={v['order_id']:v for v in p['cancel_orders']}
        target=orders.get(i['order_id'])
        require(i['order_id'] in targets and target is not None and target['symbol']==i['symbol'],'CANCEL_TARGET_CHANGED')
        if target is not None:
            require(target['status'] not in TERMINAL,'ORDER_ALREADY_TERMINAL')
            require(i['order_id'] in targets and targets[i['order_id']]['symbol']==target['symbol'] and targets[i['order_id']]['intent_id']==i['intent_id'],'CANCEL_TARGET_CHANGED')
    elif i['kind']=='CLOSE_LONG':
        require(instant(o['clock']['session_open_at'])<=at<instant(o['clock']['session_close_at']),'REGULAR_SESSION_REQUIRED')
        for prerequisite in p['cancel_orders']:
            current=orders.get(prerequisite['order_id'])
            require(current is not None and current['status'] in TERMINAL,'CANCELLATION_UNCONFIRMED')
            require(current is not None and current['filled_quantity']==prerequisite['filled_quantity'],'PLAN_QUANTITY_CHANGED')
        children=p['children'];index=i['child_index']
        child=children[index] if index is not None and 0<=index<len(children) else None
        require(child is not None and child['intent_id']==i['intent_id'] and child['symbol']==i['symbol'],'CHILD_IDENTITY_CHANGED')
        # Every earlier child must be terminal; any pending order conflicts.
        from .execution_risk import client_order_id
        by_client={v['client_order_id']:v for v in o['orders']};fills={v['symbol']:0 for v in p['positions']}
        for preceding in children:
            identity=dict(i,intent_id=preceding['intent_id'],symbol=preceding['symbol'],child_index=preceding['index'])
            existing=by_client.get(client_order_id(ExecutionIntent(identity)))
            if index is not None and preceding['index']<index:
                require(existing is not None and existing['status'] in TERMINAL,'PRIOR_CHILD_UNCONFIRMED')
            elif existing is not None:require(False,'CHILD_ALREADY_OBSERVED')
            if existing is not None:
                require(existing['side']=='sell' and existing['symbol']==preceding['symbol'] and existing['quantity']<=preceding['maximum_quantity'],'CHILD_OBSERVATION_CHANGED')
                require(D(existing['filled_notional'])<=D(preceding['maximum_notional']),'REALIZED_NOTIONAL_BREACH')
                fills[preceding['symbol']]+=existing['filled_quantity']
        require(all(v['status'] in TERMINAL for v in o['orders']),'CONFLICTING_ORDER')
        owned={v['symbol']:v['owned_quantity'] for v in o['positions'] if v['owned_quantity']}
        expected={v['symbol']:v['quantity']-fills[v['symbol']] for v in p['positions'] if v['quantity']-fills[v['symbol']]}
        require(owned==expected,'PLAN_QUANTITY_CHANGED')
        try:
            q,cap=_quote(o,i['symbol'],at)
            if child:
                unit=D(q['ask'])*D('1.01');cap=min(cap,D(child['maximum_notional']));maximum=max(0,min(child['maximum_quantity'],owned.get(i['symbol'],0),int(cap/unit)));notional=i['quantity']*unit
                require(i['quantity']<=maximum,'CHILD_ENVELOPE_EXCEEDED')
        except ContractError as exc:require(False,str(exc))
    else:require(False,'CONTROL_KIND_REQUIRED')
    return ExecutionDecision(dict(schema_version='1',record_type='ExecutionDecision',currency='USD',account_alias=o['account_alias'],generation=o['generation'],kind='CONTROL',evaluated_at=now,intent_sha256=digest(intent),snapshot_sha256=snapshot_sha256(observation),dependencies={k:digest(v) for k,v in [('calendar',calendar),('plan',plan),('authorization',authorization),('start',start)] if v is not None},scope='DETERMINISTIC_FAKE',allowed=not reasons,reasons=reasons,maximum_quantity=maximum,reserved_notional=number(notional),plan_sha256=digest(plan),authorization_sha256=digest(authorization),financial_accepted=False))
