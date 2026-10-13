"""Paper planning fixtures are inspectable proposals, never authority."""
from dataclasses import FrozenInstanceError
from decimal import localcontext
import json
from uuid import UUID
import pytest
from compertum.domain import ContractError
from compertum.paper_portfolio import build_portfolio_bundle
from compertum.paper_fixture_plans import build_fixture_inputs,build_fixture_proposal
from test_paper_portfolio import reply,position,order,parameters,ACCOUNT

AT='2023-11-24T14:35:00Z'
NOW='2023-11-24T14:35:08Z'
INTENT='44444444-4444-4444-8444-444444444444'

def portfolio(*,positions=(),orders=(),cash='1000',now=NOW):
    return build_portfolio_bundle(account=reply('ACCOUNT',dict(id=ACCOUNT,status='ACTIVE',currency='USD',cash=cash,equity='1000',buying_power='4000',trading_blocked=False,account_blocked=False,trade_suspended_by_user=False),created_at=AT,received_at='2023-11-24T14:35:01Z',index=1),
        positions=reply('POSITIONS',list(positions),created_at=AT,received_at='2023-11-24T14:35:01Z',index=2),
        orders=(reply('ORDERS',list(orders),parameters(),created_at=AT,received_at='2023-11-24T14:35:01Z',index=3),),
        clock=reply('CLOCK',dict(timestamp='2023-11-24T14:35:05Z',is_open=True,next_open='2023-11-27T14:30:00Z',next_close='2023-11-24T18:00:00Z'),created_at='2023-11-24T14:35:05Z',received_at='2023-11-24T14:35:06Z',index=4),
        calendar=reply('CALENDAR',[dict(date='2023-11-24',open='09:30',close='13:00')],dict(start='2023-11-24',end='2023-11-24'),created_at=AT,received_at='2023-11-24T14:35:01Z',index=5),as_of=now)

def facts(*,ask='100',bid='99',quote_change=None,security_change=None,**kw):
    q=dict(symbol='AAPL',bid=bid,ask=ask,observed_at='2023-11-24T14:35:01Z',feed='sip');q.update(quote_change or {})
    s=dict(symbol='AAPL',feature_sessions=252,raw_close='100',liquidity_sessions=20,mean_dollar_volume='1000000',feature_session='2023-11-22',tradable=True,actions_verified=True,mapping_verified=True);s.update(security_change or {})
    args=dict(quotes=[q],securities=[s],feed='sip',feature_session='2023-11-22',created_at='2023-11-24T14:35:02Z',supervision_at=AT);args.update(kw)
    return build_fixture_inputs(**args)

def proposal(kind='OPEN_BUY',**kw):
    args=dict(portfolio=portfolio(),inputs=facts(),kind=kind,symbol='AAPL',intent_id=INTENT,now=NOW);args.update(kw)
    return build_fixture_proposal(**args)


def test_open_draft_and_ungranted_approval_are_bound_and_immutable():
    v=proposal();p=v.to_payload();r=p['requests'][0]
    assert p['kind']=='OPEN_BUY' and p['scope']=='ENGINEERING_FIXTURE'
    assert r['body']['qty']=='1' and r['body']['type']=='market' and r['body']['side']=='buy'
    assert p['planned_notional']=='101.101' and p['projected_exposure']=='101.101'
    assert p['transport_authorized'] is p['financial_accepted'] is False and p['actual_ownership']=='UNVERIFIED'
    envelope=v.approval_request()
    assert envelope['status']=='NOT_GRANTED' and envelope['proposal_sha256']==v.sha256 and envelope['transport_authorized'] is False
    envelope['status']='GRANTED'
    assert v.approval_request()['status']=='NOT_GRANTED'
    assert proposal().content==v.content and len(r['body']['client_order_id'])==44
    with pytest.raises((FrozenInstanceError,AttributeError)):v.content=b'{}'


def test_decimal_context_cannot_change_sizing_or_hashes():
    original=proposal().content
    with localcontext() as ctx:
        ctx.prec=3
        assert proposal().content==original

@pytest.mark.parametrize('changes',[{'ask':'NaN'},{'bid':'0'},{'ask':'98'},{'ask':True},{'feed':'unknown'},{'symbol':'AAPL/..'},{'observed_at':'2023-11-24'}])
def test_bad_quote_shape(changes):
    with pytest.raises(ContractError):facts(quote_change=changes)

@pytest.mark.parametrize('changes',[{'feature_sessions':True},{'liquidity_sessions':True},{'raw_close':'Infinity'},{'tradable':1},{'symbol':'aapl'},{'mean_dollar_volume':-1}])
def test_bad_security_shape(changes):
    with pytest.raises(ContractError):facts(security_change=changes)

@pytest.mark.parametrize('changes',[{'feature_sessions':251},{'raw_close':'4.99'},{'mean_dollar_volume':'999999'},{'liquidity_sessions':19},{'tradable':False},{'actions_verified':False},{'mapping_verified':False},{'feature_session':'2023-11-23'}])
def test_unsupported_eligibility_does_not_produce_open_plan(changes):
    with pytest.raises(ContractError):proposal(inputs=facts(security_change=changes))

@pytest.mark.parametrize('kind',['future_quote','stale_quote','future_supervision','expired_supervision','stale_portfolio','wrong_feature_date','duplicate_quotes'])
def test_time_identity_and_duplicate_gates(kind):
    with pytest.raises(ContractError):
        if kind=='future_quote':proposal(inputs=facts(quote_change={'observed_at':'2023-11-24T14:36:00Z'}))
        elif kind=='stale_quote':proposal(inputs=facts(quote_change={'observed_at':'2023-11-24T14:34:00Z'}))
        elif kind=='future_supervision':proposal(inputs=facts(supervision_at='2023-11-24T14:36:00Z'))
        elif kind=='expired_supervision':proposal(inputs=facts(supervision_at='2023-11-24T14:29:00Z'))
        elif kind=='stale_portfolio':proposal(now='2023-11-24T14:36:00Z')
        elif kind=='wrong_feature_date':proposal(inputs=facts(feature_session='2023-11-23'))
        else:
            p=facts().to_payload();build_fixture_inputs(quotes=p['quotes']*2,securities=p['securities'],feed=p['feed'],feature_session=p['feature_session'],created_at=AT,supervision_at=AT)


def test_open_holding_cash_and_fixture_caps():
    for kw in ({'portfolio':portfolio(positions=[position()])},{'portfolio':portfolio(orders=[order()])},{'portfolio':portfolio(cash='101')},{'inputs':facts(ask='250',bid='249')}):
        with pytest.raises(ContractError):proposal(**kw)


def test_resting_limit_includes_holding_and_needs_separate_hash():
    p=proposal('RESTING_BUY',portfolio=portfolio(positions=[position()]),limit_price='80').to_payload()
    assert p['requests'][0]['body']['type']=='limit' and p['planned_notional']=='80.8808'
    assert p['projected_exposure']=='180.8808'
    for limit in ('80.01','0','NaN'):
        with pytest.raises(ContractError):proposal('RESTING_BUY',portfolio=portfolio(positions=[position()]),limit_price=limit)
    with pytest.raises(ContractError):proposal('RESTING_BUY',portfolio=portfolio(positions=[position(qty='2')]),limit_price='80')


def test_cancel_binds_individual_order_without_claiming_effect():
    target=order(status='pending_cancel',filled_qty='1',filled_avg_price='100')
    p=proposal('CANCEL',portfolio=portfolio(positions=[position()],orders=[target]),order_id=target['id']).to_payload()
    assert p['requests'][0]['method']=='DELETE' and p['requests'][0]['path'].endswith(target['id'])
    assert p['confirmed_effect'] is False and p['actual_flat'] is None
    with pytest.raises(ContractError):proposal('CANCEL',portfolio=portfolio(orders=[target]),order_id=str(UUID(int=999)))


def test_close_preserves_excess_exposure_and_serial_children():
    p=proposal('CLOSE_LONG',portfolio=portfolio(positions=[position(qty='5')]),inputs=facts(ask='1000',bid='999')).to_payload()
    assert [v['maximum_quantity'] for v in p['children']]==[1,1,1,1,1]
    assert all(r['body']['side']=='sell' for r in p['requests']) and p['residual_quantity']==0
    assert len({r['body']['client_order_id'] for r in p['requests']})==5
    assert p['transport_authorized'] is False


def test_close_conflicts_child_cap_and_bounded_residual():
    with pytest.raises(ContractError):proposal('CLOSE_LONG',portfolio=portfolio(positions=[position()],orders=[order()]))
    p=proposal('CLOSE_LONG',portfolio=portfolio(positions=[position()]),inputs=facts(ask='2000',bid='1999')).to_payload()
    assert p['requests']==[] and p['residual_quantity']==1 and p['proposal_status']=='BLOCKED_RESIDUAL'
    p=proposal('CLOSE_LONG',portfolio=portfolio(positions=[position(qty='20')]),inputs=facts(ask='1000',bid='999')).to_payload()
    assert len(p['children'])==12 and p['residual_quantity']==8


def test_intent_and_price_changes_cannot_reuse_an_approval_envelope():
    old=proposal();new=proposal(inputs=facts(ask='101',bid='100'))
    assert old.sha256!=new.sha256 and old.approval_request()['proposal_sha256']!=new.approval_request()['proposal_sha256']
    assert old.to_payload()['requests'][0]['body']['client_order_id']==new.to_payload()['requests'][0]['body']['client_order_id']
    assert proposal(intent_id=str(UUID(int=777))).to_payload()['requests'][0]['body']['client_order_id']!=old.to_payload()['requests'][0]['body']['client_order_id']

# New records use fresh request and receipt times; boundary failures must not be
# accidental stale-portfolio failures.
def at_portfolio(at, *, positions=(), orders=(), calendar_close='13:00', is_open=True,
                 next_open='2023-11-27T14:30:00Z', next_close='2023-11-24T18:00:00Z'):
    from datetime import timedelta
    from compertum.paper_contracts import timestamp
    from compertum.paper_responses import parse_response
    from compertum.paper_contracts import build_request
    old=portfolio(positions=positions,orders=orders)
    now=timestamp(at)
    def shifted(response,clock=False):
        p=response.request.to_payload(); body=json.loads(response.raw)
        p['created_at']=(now-timedelta(seconds=2)).isoformat()
        if clock:body.update(timestamp=p['created_at'],is_open=is_open,next_open=next_open,next_close=next_close)
        if p['operation']=='CALENDAR':body[0]['close']=calendar_close
        r=build_request(**{key:p[key] for key in ('origin','account_alias','account_id','request_id','created_at','operation','parameters','body')})
        return parse_response(r,origin=p['origin'],account_id=p['account_id'],status=200,raw=json.dumps(body).encode(),received_at=(now-timedelta(seconds=1)).isoformat())
    return build_portfolio_bundle(account=shifted(old.account),positions=shifted(old.positions),orders=tuple(shifted(r) for r in old.orders),clock=shifted(old.clock,True),calendar=shifted(old.calendar),as_of=at)


def at_facts(at,**kw):
    return facts(created_at=at,supervision_at=at,quote_change={'observed_at':at},**kw)


@pytest.mark.parametrize('at,allowed',[('2023-11-24T14:34:59Z',False),('2023-11-24T14:35:00Z',True),('2023-11-24T15:04:59Z',True),('2023-11-24T15:05:00Z',False)])
def test_opening_window_uses_fresh_observations(at,allowed):
    args=dict(portfolio=at_portfolio(at),inputs=at_facts(at),now=at)
    if allowed:
        p=proposal(**args).to_payload()
        assert p['start_expires_at']<=('2023-11-24T15:05:00Z')
    else:
        with pytest.raises(ContractError,match='FIXTURE_OPENING_WINDOW'):proposal(**args)


def test_closing_is_allowed_after_opening_window_and_capped_at_early_close():
    at='2023-11-24T17:59:50Z'
    p=proposal('CLOSE_LONG',portfolio=at_portfolio(at,positions=[position()]),inputs=at_facts(at),now=at).to_payload()
    assert p['operation_deadline']==p['start_expires_at']=='2023-11-24T18:00:00Z'
    assert p['requests'][0]['body']['side']=='sell'


@pytest.mark.parametrize('kwargs',[{'calendar_close':'16:00'},{'next_close':'2023-11-24T21:00:00Z'},{'next_open':'2023-11-28T14:30:00Z'}])
def test_calendar_and_clock_disagreement(kwargs):
    with pytest.raises(ContractError,match='FIXTURE_(CALENDAR|CLOCK)_MISMATCH'):
        proposal(portfolio=at_portfolio(NOW,**kwargs))


def test_close_does_not_require_alpha_or_buy_eligibility():
    inputs=facts(feature_session='2023-11-01',security_change={'feature_sessions':0,'raw_close':'1','tradable':False,'actions_verified':False,'mapping_verified':False,'mean_dollar_volume':'101000'})
    p=proposal('CLOSE_LONG',portfolio=portfolio(positions=[position(qty='2')]),inputs=inputs).to_payload()
    assert p['children'][0]['maximum_quantity']==2 and p['per_intent_cap']=='1010'


def test_cancellation_needs_no_quote_or_alpha_and_can_be_outside_hours():
    at='2023-11-24T13:00:00Z'; target=order(submitted_at='2023-11-22T14:30:00Z')
    empty=build_fixture_inputs(quotes=[],securities=[],feed='sip',feature_session='2023-11-01',created_at=at,supervision_at=at)
    p=proposal('CANCEL',portfolio=at_portfolio(at,orders=[target],is_open=False,next_open='2023-11-24T14:30:00Z'),inputs=empty,order_id=target['id'],now=at).to_payload()
    assert p['requests'][0]['method']=='DELETE' and p['quote'] is None


def test_inputs_are_detached_strict_and_cannot_assert_authority():
    from compertum.data.encoding import canonical
    from compertum.paper_fixture_plans import PaperFixtureInputs
    original=facts(); p=original.to_payload();p['quotes'][0]['ask']='1'
    assert original.to_payload()['quotes'][0]['ask']=='100'
    for key,value in [('transport_authorized',True),('unknown',1),('version',True)]:
        p=original.to_payload();p[key]=value
        with pytest.raises(ContractError):PaperFixtureInputs(canonical(p))
    with pytest.raises((FrozenInstanceError,AttributeError)):original.content=b'{}'


@pytest.mark.parametrize('kwargs',[{'kind':True},{'kind':'CLOSE_ALL'},{'intent_id':str(UUID(int=0))},{'symbol':'SPY'},{'limit_price':'80'},{'order_id':str(UUID(int=1))},{'inputs':{}},{'portfolio':{}}])
def test_invalid_plan_inputs_cannot_escape_boundary(kwargs):
    with pytest.raises(ContractError):proposal(**kwargs)


def test_other_symbols_and_pending_buys_count_toward_cash_and_exposure():
    q=facts().to_payload()['quotes'][0]
    q2=dict(q,symbol='MSFT',ask='200',bid='199')
    inputs=facts(quotes=[q,q2])
    with pytest.raises(ContractError,match='FIXTURE_EXPOSURE_CAP'):
        proposal('RESTING_BUY',portfolio=portfolio(positions=[position(),position(asset_id=str(UUID(int=44)),symbol='MSFT')]),inputs=inputs,limit_price='80')
    pending=order(symbol='MSFT',qty='1',type='limit',limit_price='10')
    with pytest.raises(ContractError,match='FIXTURE_INSUFFICIENT_CASH'):
        proposal('RESTING_BUY',portfolio=portfolio(positions=[position()],orders=[pending],cash='90'),inputs=inputs,limit_price='80')
    p=proposal('RESTING_BUY',portfolio=portfolio(positions=[position()],orders=[pending]),inputs=inputs,limit_price='80').to_payload()
    assert p['projected_exposure']=='190.9909'


def test_bounded_decimal_inputs_cannot_round_a_child_above_its_cap():
    with pytest.raises(ContractError):
        proposal('CLOSE_LONG',portfolio=portfolio(positions=[position()]),inputs=facts(security_change={'mean_dollar_volume':'10099.999999999999999999999999999999'}))


@pytest.mark.parametrize('which',['quotes','securities'])
def test_missing_current_symbol_facts_are_not_inferred(which):
    with pytest.raises(ContractError):proposal(inputs=facts(**{which:[]}))


def test_start_expiry_respects_short_remaining_presence():
    p=proposal(inputs=facts(supervision_at='2023-11-24T14:30:10Z')).to_payload()
    assert p['start_expires_at']=='2023-11-24T14:35:10Z'
    with pytest.raises(ContractError):proposal(inputs=facts(supervision_at='2023-11-24T14:30:08Z'))

@pytest.mark.parametrize('volume',['1000000000000000000.01','1000000.000000001'])
def test_liquidity_arithmetic_bounds(volume):
    with pytest.raises(ContractError):facts(security_change={'mean_dollar_volume':volume})


def test_input_unknown_fields_and_duplicates_are_rejected():
    p=facts().to_payload()
    with pytest.raises(ContractError):facts(quote_change={'trusted':True})
    with pytest.raises(ContractError):facts(security_change={'trusted':True})
    with pytest.raises(ContractError):facts(securities=p['securities']*2)
    with pytest.raises(ContractError):facts(created_at='2023-11-24T14:35:09Z',quote_change={'observed_at':'2023-11-24T14:35:09Z'});proposal(inputs=facts(created_at='2023-11-24T14:35:09Z'))


def test_closed_market_does_not_allow_a_close_order():
    at='2023-11-24T18:00:03Z'
    with pytest.raises(ContractError,match='FIXTURE_MARKET_CLOSED'):
        proposal('CLOSE_LONG',portfolio=at_portfolio(at,positions=[position()],is_open=False,next_close='2023-11-27T21:00:00Z'),inputs=at_facts(at),now=at)



def test_explicit_iex_fixture_preserves_feed_and_ungranted_authority():
 inputs=facts(feed='iex',quote_change={'feed':'iex'})
 p=proposal(inputs=inputs).to_payload()
 assert inputs.to_payload()['feed']=='iex' and p['financial_accepted'] is False and p['transport_authorized'] is False
 assert proposal(inputs=inputs).content==proposal(inputs=inputs).content
 with pytest.raises(ContractError):facts(feed='iex')
 with pytest.raises(ContractError):facts(quote_change={'feed':'iex'})


@pytest.mark.parametrize('feed',[None,[],True,'delayed_sip','unknown'])
def test_unsupported_fixture_feed_is_a_fixed_refusal(feed):
 with pytest.raises(ContractError):facts(feed=feed)
