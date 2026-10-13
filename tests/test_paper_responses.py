"""Synthetic wire bytes never establish real account or order evidence."""
import hashlib
import json
from dataclasses import FrozenInstanceError
import pytest
from compertum.domain import ContractError
from compertum.paper_contracts import PAPER_ORIGIN, build_request
from compertum.paper_responses import parse_response

ACCOUNT='11111111-1111-4111-8111-111111111111'
REQUEST='22222222-2222-4222-8222-222222222222'
ORDER='33333333-3333-4333-8333-333333333333'
AT='2023-11-24T14:30:00Z'

def request(op='ACCOUNT', **kw):
    return build_request(origin=PAPER_ORIGIN,account_alias='fixture',account_id=ACCOUNT,request_id=REQUEST,created_at=AT,operation=op,**kw)

def response(r=None, raw=None, status=200, **kw):
    context=dict(origin=PAPER_ORIGIN,account_id=ACCOUNT,received_at='2023-11-24T14:30:01Z')
    context.update(kw)
    if raw is None:raw=json.dumps(account()).encode()
    return parse_response(r or request(),status=status,raw=raw,**context)

def account(**kw):
    p=dict(id=ACCOUNT,status='ACTIVE',currency='USD',cash='100000.00',equity='100000.00',buying_power='200000.00',trading_blocked=False,account_blocked=False,trade_suspended_by_user=False)
    p.update(kw);return p

def order(**kw):
    p=dict(id=ORDER,client_order_id='cmp-fixture-001',symbol='AAPL',qty='2',filled_qty='0',filled_avg_price=None,side='buy',type='market',time_in_force='day',extended_hours=False,status='new',limit_price=None)
    p.update(kw);return p

def submit(**kw):
    body=dict(symbol='AAPL',qty='2',side='buy',type='market',time_in_force='day',extended_hours=False,client_order_id='cmp-fixture-001')
    body.update(kw);return request('SUBMIT_ORDER',body=body)

def test_account_raw_binding_and_detached_copy():
    raw=json.dumps(account(),indent=2).encode();r=request();v=response(r,raw)
    p=v.to_payload()
    assert v.raw==raw and p['raw_sha256']==hashlib.sha256(raw).hexdigest() and p['request_sha256']==r.sha256
    assert p['account_binding']=='CALLER_CONTEXT_UNVERIFIED'
    assert p['scope']=='PAPER_WIRE_FIXTURE' and p['transport_authorized'] is p['financial_accepted'] is p['retry_authorized'] is False
    assert p['outcome']=='SUCCESS_FIXTURE' and p['age_since_request_creation_us']==1000000
    p['observation']['cash']='0'
    assert v.to_payload()['observation']['cash']=='100000.00'
    with pytest.raises((FrozenInstanceError,AttributeError)):v.raw=b'{}'

@pytest.mark.parametrize('kw',[{'origin':'https://api.alpaca.markets'},{'account_id':ORDER},{'received_at':'2023-11-24T14:29:59Z'},{'received_at':'2023-11-24T14:30:01'},{'status':True},{'status':301},{'status':199},{'status':600},{'status':201},{'status':204}])
def test_bad_response_context(kw):
    with pytest.raises(ContractError):response(**kw)

@pytest.mark.parametrize('changes',[{'id':ORDER},{'cash':'NaN'},{'cash':'1e3'},{'equity':100000.0},{'buying_power':True},{'trading_blocked':0},{'account_blocked':'false'},{'trade_suspended_by_user':None},{'currency':'EUR'},{'status':'MADE_UP'}])
def test_bad_account_success(changes):
    with pytest.raises(ContractError):response(raw=json.dumps(account(**changes)).encode())

@pytest.mark.parametrize('raw',[b'{"id":1,"id":2}',b'{"x":Infinity}',b'['*40+b'0'+b']'*40,b'x'*65537,b'\xff',b'null',b'[]'],ids=['duplicate','nonfinite','deep','oversize','utf8','null','array'])
def test_bad_success_bytes(raw):
    with pytest.raises(ContractError):response(raw=raw)

@pytest.mark.parametrize('status,raw',[(None,b''),(None,b'partial body'),(404,b'{"message":"not found"}'),(429,b'rate limit'),(500,b'')])
def test_ambiguous_outcomes_preserve_bytes_and_do_not_retry(status,raw):
    v=response(request('ORDER_BY_CLIENT_ID',parameters={'client_order_id':'cmp-fixture-001'}),raw,status)
    assert v.raw==raw and v.to_payload()['outcome']=='UNCONFIRMED'
    assert v.to_payload()['observation'] is None and v.to_payload()['retry_authorized'] is False


def test_cancel_ack_is_not_order_cancellation():
    r=request('CANCEL_ORDER',parameters={'order_id':ORDER})
    v=response(r,b'',204).to_payload()
    assert v['outcome']=='CANCEL_REQUEST_ACCEPTED_UNCONFIRMED'
    assert v['observation'] is None
    with pytest.raises(ContractError):response(r,b'{}',204)


def test_clock_offsets_and_late_arrival_are_retained():
    raw=json.dumps(dict(timestamp='2023-11-24T09:30:00-05:00',is_open=True,next_open='2023-11-27T09:30:00-05:00',next_close='2023-11-24T13:00:00-05:00')).encode()
    p=response(request('CLOCK'),raw,received_at='2023-11-24T14:30:07Z').to_payload()
    assert p['observation']['timestamp']==AT and p['older_than_5s'] is True and p['age_since_request_creation_us']==7000000
    assert p['raw_sha256']==hashlib.sha256(raw).hexdigest()

@pytest.mark.parametrize('change',[{'is_open':1},{'next_close':'2023-11-24T08:00:00-05:00'},{'timestamp':'2023-11-24T09:30:00'}])
def test_clock_rejects_inconsistent_or_naive_fields(change):
    p=dict(timestamp=AT,is_open=True,next_open='2023-11-27T14:30:00Z',next_close='2023-11-24T18:00:00Z');p.update(change)
    with pytest.raises(ContractError):response(request('CLOCK'),json.dumps(p).encode())


def test_calendar_early_close_and_dst_remain_provider_fixtures():
    r=request('CALENDAR',parameters={'start':'2023-11-01','end':'2023-11-30'})
    rows=[dict(date='2023-11-03',open='09:30',close='16:00'),dict(date='2023-11-06',open='09:30',close='16:00'),dict(date='2023-11-24',open='09:30',close='13:00')]
    p=response(r,json.dumps(rows).encode()).to_payload()
    assert p['observation']==rows and p['calendar_admitted'] is False

@pytest.mark.parametrize('rows',[[dict(date='2023-12-01',open='09:30',close='16:00')],[dict(date='2023-11-24',open='13:00',close='09:30')],[dict(date='2023-11-24',open='09:30',close='13:00')]*2,[dict(date='2023-11-24',open='9:30',close='13:00')]])
def test_bad_calendar(rows):
    with pytest.raises(ContractError):response(request('CALENDAR',parameters={'start':'2023-11-01','end':'2023-11-30'}),json.dumps(rows).encode())

@pytest.mark.parametrize('state,filled,price',[('new','0',None),('partially_filled','1','150.00'),('filled','2','150.00'),('pending_cancel','1','150.00'),('canceled','1','150.00'),('rejected','0',None)])
def test_order_status_and_quantities(state,filled,price):
    p=response(submit(),json.dumps(order(status=state,filled_qty=filled,filled_avg_price=price)).encode()).to_payload()
    assert p['observation']['status']==state

@pytest.mark.parametrize('change',[{'client_order_id':'cmp-wrong'},{'qty':'3'},{'filled_qty':'3'},{'qty':'2.5'},{'filled_qty':'1.5'},{'filled_qty':True},{'status':'filled'},{'status':'new','filled_qty':'1','filled_avg_price':'150'},{'status':'partially_filled','filled_qty':'2','filled_avg_price':'150'},{'filled_avg_price':'NaN'},{'filled_qty':'1','filled_avg_price':None},{'symbol':'MSFT'},{'side':'sell'},{'type':'limit','limit_price':'150'},{'extended_hours':True},{'status':'imaginary'}])
def test_bad_or_mismatched_order(change):
    with pytest.raises(ContractError):response(submit(),json.dumps(order(**change)).encode())


def test_lookup_id_and_client_identity_and_limit_binding():
    with pytest.raises(ContractError):response(request('ORDER_BY_ID',parameters={'order_id':REQUEST}),json.dumps(order()).encode())
    with pytest.raises(ContractError):response(request('ORDER_BY_CLIENT_ID',parameters={'client_order_id':'cmp-other'}),json.dumps(order()).encode())
    r=submit(type='limit',limit_price='150.00')
    assert response(r,json.dumps(order(type='limit',limit_price='150')).encode()).to_payload()['outcome']=='SUCCESS_FIXTURE'
    with pytest.raises(ContractError):response(r,json.dumps(order(type='limit',limit_price='149')).encode())

@pytest.mark.parametrize('state',['accepted','accepted_for_bidding'])
def test_unrouted_order_cannot_claim_any_fill(state):
    with pytest.raises(ContractError):response(submit(),json.dumps(order(status=state,filled_qty='2',filled_avg_price='150')).encode())

@pytest.mark.parametrize('field',['receipt','clock'])
def test_timezone_minute_overflow_is_rejected_at_response_boundaries(field):
    with pytest.raises(ContractError):
        if field=='receipt':response(received_at='2023-11-24T14:30:01+00:99')
        else:
            raw=json.dumps(dict(timestamp='2023-11-24T14:30:00+00:99',is_open=True,next_open='2023-11-27T14:30:00Z',next_close='2023-11-24T18:00:00Z')).encode()
            response(request('CLOCK'),raw)
