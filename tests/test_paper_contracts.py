"""Inert paper requests: exact routes, bounded parsing, immutable identities."""
import json
from dataclasses import FrozenInstanceError
import pytest
from compertum.domain import ContractError
from compertum.paper_contracts import PAPER_ORIGIN, PaperRequest, build_request, read_request

ACCOUNT='11111111-1111-4111-8111-111111111111'
REQUEST='22222222-2222-4222-8222-222222222222'
ORDER='33333333-3333-4333-8333-333333333333'
AT='2023-11-24T14:30:00Z'

def request(operation='ACCOUNT', **changes):
    args=dict(origin=PAPER_ORIGIN,account_alias='local-paper',account_id=ACCOUNT,request_id=REQUEST,created_at=AT,operation=operation)
    args.update(changes)
    return build_request(**args)

def order_body(**changes):
    body=dict(symbol='AAPL',qty='2',side='buy',type='market',time_in_force='day',extended_hours=False,client_order_id='cmp-fixture-001')
    body.update(changes)
    return body

@pytest.mark.parametrize('op,parameters,method,path',[
 ('ACCOUNT',None,'GET','/v2/account'),('CLOCK',None,'GET','/v2/clock'),
 ('CALENDAR',{'start':'2023-11-01','end':'2023-11-30'},'GET','/v2/calendar'),
 ('ORDER_BY_ID',{'order_id':ORDER},'GET','/v2/orders/'+ORDER),
 ('ORDER_BY_CLIENT_ID',{'client_order_id':'cmp-fixture-001'},'GET','/v2/orders:by_client_order_id'),
 ('CANCEL_ORDER',{'order_id':ORDER},'DELETE','/v2/orders/'+ORDER),
 ('SUBMIT_ORDER',None,'POST','/v2/orders')])
def test_route_roundtrip_and_no_authority(op,parameters,method,path):
    r=request(op,parameters=parameters,body=order_body() if op=='SUBMIT_ORDER' else None)
    p=r.to_payload()
    assert (p['method'],p['path'])==(method,path)
    assert p['scope']=='PAPER_WIRE_FIXTURE' and p['transport_authorized'] is p['financial_accepted'] is False
    assert read_request(r.content).content==r.content and len(r.sha256)==64
    p['account_id']=ORDER
    assert r.to_payload()['account_id']==ACCOUNT
    with pytest.raises((FrozenInstanceError,AttributeError)):r.content=b'{}'

@pytest.mark.parametrize('origin',['http://paper-api.alpaca.markets','https://api.alpaca.markets','https://paper-api.alpaca.markets/','https://PAPER-api.alpaca.markets','https://paper-api.alpaca.markets:443','https://paper-api.alpaca.markets@evil.example','https://paper-api.alpaca.markets?x=1',None,True])
def test_endpoint_spelling_is_not_authority(origin):
    with pytest.raises(ContractError):request(origin=origin)

@pytest.mark.parametrize('field,value',[('account_id',REQUEST.upper()+'x'),('account_id','00000000-0000-0000-0000-000000000000'),('request_id',True),('account_alias','../paper'),('account_alias','x'*65),('created_at','2023-11-24T14:30:00'),('created_at','2023-11-24'),('operation','REPLACE_ORDER'),('parameters',{'headers':{}}),('body',{})])
def test_reject_invalid_envelopes(field,value):
    with pytest.raises(ContractError):request(**{field:value})

@pytest.mark.parametrize('changes',[{'qty':True},{'qty':2},{'qty':'2.5'},{'qty':'0'},{'qty':'02'},{'qty':'1e3'},{'extended_hours':0},{'extended_hours':True},{'side':'SELL'},{'symbol':'aapl'},{'symbol':'AAPL/..'},{'type':'stop'},{'time_in_force':'gtc'},{'client_order_id':'arbitrary'},{'client_order_id':'cmp-'+('a'*125)},{'secret':'never'}, {'limit_price':'1.00'}])
def test_submit_rejects_unsupported_or_confused_body(changes):
    with pytest.raises(ContractError):request('SUBMIT_ORDER',body=order_body(**changes))

def test_limit_and_mutation_and_equivalent_offset():
    body=order_body(type='limit',limit_price='150.25')
    r=request('SUBMIT_ORDER',body=body,created_at='2023-11-24T09:30:00-05:00')
    body['qty']='9'
    assert r.to_payload()['body']['qty']=='2' and r.to_payload()['created_at']==AT
    assert r.content==request('SUBMIT_ORDER',body=order_body(type='limit',limit_price='150.25')).content

@pytest.mark.parametrize('price',['0','-1','NaN','Infinity','1e2',True,1.2])
def test_bad_limit_price(price):
    with pytest.raises(ContractError):request('SUBMIT_ORDER',body=order_body(type='limit',limit_price=price))

@pytest.mark.parametrize('parameters',[{'start':'2023-11-30','end':'2023-11-01'},{'start':'2023-01-01','end':'2023-02-01'},{'start':'2023-02-30','end':'2023-03-01'},{'start':'2023-11-01','end':'2023-11-30','date_type':'SETTLEMENT'}])
def test_calendar_rejects_bad_or_wide_ranges(parameters):
    with pytest.raises(ContractError):request('CALENDAR',parameters=parameters)

@pytest.mark.parametrize('raw',[b'{"x":1,"x":2}',b'{"x":NaN}',b'['*40+b'0'+b']'*40,b' '*65537,b'\xff',b'{}',b'null'], ids=['duplicate','nonfinite','deep','oversize','invalid_utf8','empty','null'])
def test_bad_serialized_request(raw):
    with pytest.raises(ContractError):read_request(raw)

@pytest.mark.parametrize('change',[{'method':'DELETE'},{'path':'/v2/orders'},{'transport_authorized':True},{'financial_accepted':True},{'scope':'PAPER_ACCOUNT'},{'headers':{}},{'created_at':'2023-11-24T09:30:00-05:00'}])
def test_reader_checks_derived_fields_and_canonical_form(change):
    p=request().to_payload();p.update(change)
    raw=json.dumps(p,sort_keys=True,separators=(',',':')).encode()
    with pytest.raises(ContractError):read_request(raw)

@pytest.mark.parametrize('offset',['+00:99','+01:60','-00:99'])
def test_timezone_offset_minutes_must_be_valid(offset):
    with pytest.raises(ContractError):request(created_at='2023-11-24T14:30:00'+offset)
