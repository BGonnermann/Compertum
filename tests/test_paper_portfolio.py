"""Account-wide fixture coverage cannot become an actual clean-account claim."""
from dataclasses import FrozenInstanceError
import hashlib
import json
from uuid import UUID
import pytest
from compertum.domain import ContractError
from compertum.paper_contracts import PAPER_ORIGIN,build_request,read_request
from compertum.paper_responses import parse_response
from compertum.paper_portfolio import build_portfolio_bundle

ACCOUNT='11111111-1111-4111-8111-111111111111'
ASSET='22222222-2222-4222-8222-222222222222'
AT='2023-11-24T14:30:00Z'
NOW='2023-11-24T14:30:08Z'

def req(op,parameters=None,created_at=AT,index=1,account=ACCOUNT):
    return build_request(origin=PAPER_ORIGIN,account_alias='fixture',account_id=account,request_id=str(UUID(int=index)),created_at=created_at,operation=op,parameters=parameters)

def reply(op,body,parameters=None,created_at=AT,received_at='2023-11-24T14:30:01Z',index=1,status=200,account=ACCOUNT):
    r=req(op,parameters,created_at,index,account)
    return parse_response(r,origin=PAPER_ORIGIN,account_id=account,status=status,raw=json.dumps(body).encode(),received_at=received_at)

def parameters(**kw):
    p=dict(status='all',direction='asc',nested=False,limit=25);p.update(kw);return p

def position(**kw):
    p=dict(asset_id=ASSET,symbol='AAPL',asset_class='us_equity',qty='1',side='long',avg_entry_price='150',cost_basis='150');p.update(kw);return p

def order(index=1,**kw):
    p=dict(id=str(UUID(int=100+index)),client_order_id='cmp-fixture-'+str(index),asset_id=ASSET,asset_class='us_equity',order_class='simple',symbol='AAPL',qty='2',filled_qty='0',filled_avg_price=None,side='buy',type='market',time_in_force='day',extended_hours=False,status='new',limit_price=None,submitted_at='2023-11-24T14:29:00Z',legs=None)
    p.update(kw);return p

def inputs():
    return dict(account=reply('ACCOUNT',dict(id=ACCOUNT,status='ACTIVE',currency='USD',cash='1000',equity='1000',buying_power='4000',trading_blocked=False,account_blocked=False,trade_suspended_by_user=False),index=1),
                positions=reply('POSITIONS',[],index=2),orders=(reply('ORDERS',[],parameters(),index=3),),
                clock=reply('CLOCK',dict(timestamp='2023-11-24T14:30:05Z',is_open=True,next_open='2023-11-27T14:30:00Z',next_close='2023-11-24T18:00:00Z'),created_at='2023-11-24T14:30:05Z',received_at='2023-11-24T14:30:06Z',index=4),
                calendar=reply('CALENDAR',[dict(date='2023-11-24',open='09:30',close='13:00')],dict(start='2023-11-24',end='2023-11-24'),index=5),as_of=NOW)

def bundle(**kw):
    args=inputs();args.update(kw);return build_portfolio_bundle(**args)

@pytest.mark.parametrize('op,path,p',[('POSITIONS','/v2/positions',None),('ORDERS','/v2/orders',parameters()),('ORDERS','/v2/orders',parameters(after_order_id=str(UUID(int=9))))])
def test_exact_read_only_routes(op,path,p):
    r=req(op,p);v=r.to_payload()
    assert (v['method'],v['path'])==('GET',path) and read_request(r.content).content==r.content

@pytest.mark.parametrize('change',[{'limit':True},{'limit':0},{'limit':26},{'status':'open'},{'direction':'desc'},{'nested':True},{'nested':0},{'symbols':'AAPL'},{'side':'buy'},{'after':AT},{'until':NOW},{'after_order_id':True}])
def test_no_filter_or_unbounded_listing(change):
    with pytest.raises(ContractError):req('ORDERS',parameters(**change))


def test_empty_complete_fixture_is_explicitly_unverified_and_immutable():
    v=bundle();p=v.to_payload()
    assert p['fixture_complete'] is True and p['deficiencies']==[]
    assert p['fixture_empty_positions_and_open_orders'] is True
    assert p['actual_flat'] is None and p['transport_authorized'] is p['financial_accepted'] is False
    assert p['account_binding']=='UNVERIFIED' and p['ownership']=='UNVERIFIED' and p['fill_event_coverage']=='UNVERIFIED'
    assert p['account_cash']=='1000' and p['buying_power']=='4000'
    p['orders'].append({'id':'injected'})
    assert v.to_payload()['orders']==[]
    with pytest.raises((FrozenInstanceError,AttributeError)):v.content=b'{}'

@pytest.mark.parametrize('field',['account','positions','clock','calendar'])
def test_missing_evidence_is_not_empty(field):
    p=bundle(**{field:None}).to_payload()
    assert p['fixture_complete'] is False and p['fixture_empty_positions_and_open_orders'] is None and p['deficiencies']


def test_no_pages_and_error_are_not_complete():
    for pages in ((),(reply('ORDERS',{'message':'missing'},parameters(),status=404,index=3),)):
        p=bundle(orders=pages).to_payload();assert not p['fixture_complete'] and p['deficiencies']


def test_full_page_requires_continuation_then_accepts_exact_cursor_with_tied_times():
    first=reply('ORDERS',[order(1),order(2)],parameters(limit=2),index=3)
    p=bundle(orders=(first,)).to_payload();assert 'ORDERS_TRUNCATED' in p['deficiencies']
    last=reply('ORDERS',[order(3)],parameters(limit=2,after_order_id=order(2)['id']),created_at='2023-11-24T14:30:02Z',received_at='2023-11-24T14:30:03Z',index=6)
    p=bundle(orders=(first,last)).to_payload()
    assert p['fixture_complete'] and len(p['orders'])==3 and p['order_cursor']==order(3)['id']
    assert p['cursor_kind']=='SUBMISSION_LIST_POSITION_ONLY' and p['actual_flat'] is None

@pytest.mark.parametrize('kind',['wrong_cursor','repeat_row','changed_limit','early_next','extra_after_short','first_cursor'])
def test_broken_chain_blocks_completeness(kind):
    first=reply('ORDERS',[order(1)],parameters(limit=1),index=3)
    second_args=dict(parameters=parameters(limit=1,after_order_id=order(1)['id']),created_at='2023-11-24T14:30:02Z',received_at='2023-11-24T14:30:03Z',index=6)
    rows=[]
    if kind=='wrong_cursor':second_args['parameters']['after_order_id']=order(9)['id']
    elif kind=='repeat_row':rows=[order(1)]
    elif kind=='changed_limit':second_args['parameters']['limit']=2
    elif kind=='early_next':second_args.update(created_at=AT,received_at='2023-11-24T14:30:01Z')
    elif kind=='extra_after_short':first=reply('ORDERS',[],parameters(limit=1),index=3)
    else:first=reply('ORDERS',[order(1)],parameters(limit=1,after_order_id=order(9)['id']),index=3)
    last=reply('ORDERS',rows,**second_args)
    assert not bundle(orders=(first,last)).to_payload()['fixture_complete']

@pytest.mark.parametrize('change',[{'side':'short','qty':'-1'},{'qty':'0.5'},{'asset_class':'crypto','symbol':'BTC/USD'},{'qty':'NaN'},{'asset_id':'unknown'},{'cost_basis':True}])
def test_unsupported_position_remains_visible(change):
    raw=[position(**change)];r=reply('POSITIONS',raw,index=2)
    p=bundle(positions=r).to_payload()
    assert len(p['positions'])==1 and p['deficiencies'] and not p['fixture_complete']
    assert r.raw==json.dumps(raw).encode() and r.to_payload()['raw_sha256']==hashlib.sha256(r.raw).hexdigest()

@pytest.mark.parametrize('change',[{'qty':'1.5'},{'asset_class':'us_option'},{'order_class':'bracket','legs':[{'id':str(UUID(int=12))}]},{'time_in_force':'gtc'},{'client_order_id':'external-app'},{'extended_hours':True},{'qty':None,'notional':'100'},{'status':'provider_new_state'}])
def test_unsupported_or_foreign_order_is_not_filtered(change):
    r=reply('ORDERS',[order(**change)],parameters(),index=3)
    p=bundle(orders=(r,)).to_payload()
    assert len(p['orders'])==1 and p['deficiencies'] and not p['fixture_complete']


def test_partial_fill_and_pending_cancel_stay_visible_and_not_flat():
    rows=[order(status='pending_cancel',filled_qty='1',filled_avg_price='150')]
    p=bundle(positions=reply('POSITIONS',[position()],index=2),orders=(reply('ORDERS',rows,parameters(),index=3),)).to_payload()
    assert p['fixture_complete'] and p['orders'][0]['filled_qty']=='1' and p['orders'][0]['status']=='pending_cancel'
    assert not p['fixture_empty_positions_and_open_orders'] and p['actual_flat'] is None

@pytest.mark.parametrize('kind',['positions','orders','client_ids','account','stale','future','clock_stale','duplicate_request'])
def test_conflicts_identity_and_time_block(kind):
    args=inputs()
    if kind=='positions':args['positions']=reply('POSITIONS',[position(),position(qty='2')],index=2)
    elif kind=='orders':args['orders']=(reply('ORDERS',[order(),order(qty='3')],parameters(),index=3),)
    elif kind=='client_ids':args['orders']=(reply('ORDERS',[order(1),order(2,client_order_id=order(1)['client_order_id'])],parameters(),index=3),)
    elif kind=='account':args['positions']=reply('POSITIONS',[],index=2,account=ASSET)
    elif kind=='stale':args['as_of']='2023-11-24T14:31:00Z'
    elif kind=='future':args['as_of']='2023-11-24T14:30:00Z'
    elif kind=='clock_stale':args['clock']=reply('CLOCK',dict(timestamp=AT,is_open=True,next_open='2023-11-27T14:30:00Z',next_close='2023-11-24T18:00:00Z'),index=4)
    else:args['positions']=reply('POSITIONS',[],index=1)
    p=build_portfolio_bundle(**args).to_payload();assert not p['fixture_complete'] and p['deficiencies']


def test_no_caller_completeness_or_ownership_override():
    with pytest.raises(TypeError):build_portfolio_bundle(**inputs(),complete=True)
    with pytest.raises(TypeError):build_portfolio_bundle(**inputs(),owned=True)
    with pytest.raises(ContractError):bundle(orders=list(inputs()['orders']))
    with pytest.raises(ContractError):bundle(orders=inputs()['orders']*9)

def test_wrong_operation_still_binds_every_raw_response():
    data=inputs()['account'].to_payload()['observation']
    first=reply('ACCOUNT',data,index=2)
    other=dict(data,cash='2000');second=reply('ACCOUNT',other,index=2)
    left=bundle(positions=first);right=bundle(positions=second)
    assert left.content!=right.content
    assert first.to_payload()['raw_sha256'] in [v['raw_sha256'] for v in left.to_payload()['evidence']]
    assert not left.to_payload()['fixture_complete']


def test_embedded_clock_age_is_not_replaced_by_request_freshness():
    r=reply('CLOCK',dict(timestamp=AT,is_open=True,next_open='2023-11-27T14:30:00Z',next_close='2023-11-24T18:00:00Z'),created_at='2023-11-24T14:30:05Z',received_at='2023-11-24T14:30:06Z',index=4)
    assert not bundle(clock=r).to_payload()['fixture_complete']


def test_calendar_query_must_cover_snapshot_market_date():
    r=reply('CALENDAR',[],dict(start='2023-11-22',end='2023-11-22'),index=5)
    assert not bundle(calendar=r).to_payload()['fixture_complete']


def test_empty_calendar_is_not_itself_missing_evidence():
    r=reply('CALENDAR',[],dict(start='2023-11-24',end='2023-11-24'),index=5)
    assert bundle(calendar=r).to_payload()['fixture_complete']


def test_calendar_range_uses_new_york_date_at_utc_midnight():
    r=reply('CALENDAR',[],dict(start='2023-11-24',end='2023-11-24'),created_at='2023-11-25T00:00:00Z',received_at='2023-11-25T00:00:01Z',index=5)
    p=bundle(calendar=r,as_of='2023-11-25T00:00:08Z').to_payload()
    assert 'CALENDAR_RANGE_GAP' not in p['deficiencies']
