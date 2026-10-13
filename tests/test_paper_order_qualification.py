"""Execution-private order qualification with invented credentials/replies."""
import base64
import hashlib
import json
import pickle
from dataclasses import FrozenInstanceError
import pytest
from compertum.runtime.errors import RuntimeRefused
from compertum.runtime.paper_credentials import seal_paper_credentials
from compertum.runtime.paper_order_qualification import prepare_order_exchange,qualify_order_reply,_PreparedOrderExchange,_PrivateOrderReply
from compertum.runtime.owners import acquire_owner,release_owner,_LEASES
from compertum.runtime.identity import resolve_project
from test_paper_responses import ACCOUNT,REQUEST,ORDER,order
from test_paper_read_preparation import KEY,SECRET

AT='2023-11-24T14:30:00Z';AFTER='2023-11-24T14:30:01Z';INTENT='44444444-4444-4444-8444-444444444444'
BODY=dict(symbol='AAPL',qty='2',side='buy',type='market',time_in_force='day',extended_hours=False,client_order_id='cmp-fixture-001')

@pytest.fixture
def owner(tmp_path):
    lease=acquire_owner(resolve_project(tmp_path),'execution')
    protected=seal_paper_credentials(lease,'fixture',bytearray(KEY.encode()),bytearray(SECRET.encode()))
    try:yield lease,protected
    finally:
        if lease in _LEASES:release_owner(lease)

def request(owner,**changes):
    lease,protected=owner
    args=dict(account_id=ACCOUNT,request_id=REQUEST,intent_id=INTENT,operation='SUBMIT_ORDER',body=BODY.copy(),created_at=AT)
    args.update(changes)
    return prepare_order_exchange(lease,protected,**args)

def reply(owner,prepared=None,raw=None,**changes):
    lease,protected=owner
    args=dict(status=200,received_at=AFTER);args.update(changes)
    return qualify_order_reply(lease,protected,prepared or request(owner),json.dumps(order()).encode() if raw is None else raw,**args)


def test_native_private_context_and_exact_validated_order_reply(owner):
    req=request(owner);raw=json.dumps(order(),indent=2).encode();r=reply(owner,req,raw)
    p=r.to_payload();assert r.raw==raw and p['raw_sha256']==hashlib.sha256(raw).hexdigest()
    assert p['request_sha256']==req.sha256 and p['request_id']==REQUEST and p['intent_id']==INTENT
    assert p['observation']['id']==ORDER and p['outcome']=='ORDER_REPLY_QUALIFIED'
    assert p['account_binding']=='PRIVATE_REQUEST_CONTEXT_ONLY'
    assert p['actual_flat'] is None and p['financial_accepted'] is p['retry_authorized'] is p['transport_authorized'] is False
    assert p['age_since_request_creation_us']==1000000
    assert all(secret not in json.dumps(p) and secret not in repr(r) and secret not in req.content.decode() and secret not in repr(req) for secret in (ACCOUNT,KEY,SECRET))
    assert req.wire()==('POST','/v2/orders',json.dumps(BODY,sort_keys=True,separators=(',',':')).encode())
    p['observation']['qty']='999';assert r.to_payload()['observation']['qty']=='2'
    for obj in (req,r):
        with pytest.raises(RuntimeRefused):pickle.dumps(obj)
        with pytest.raises((FrozenInstanceError,AttributeError)):obj.content=b'{}'

@pytest.mark.parametrize('operation,parameters',[
 ('ORDER_BY_ID',{'order_id':ORDER}),('ORDER_BY_CLIENT_ID',{'client_order_id':BODY['client_order_id']})])
def test_lookup_requires_exact_requested_identity(owner,operation,parameters):
    req=request(owner,operation=operation,parameters=parameters,body=None)
    assert reply(owner,req).to_payload()['observation']['id']==ORDER
    changed=order(id=REQUEST) if operation=='ORDER_BY_ID' else order(client_order_id='cmp-other')
    with pytest.raises(RuntimeRefused,match='^PAPER_ORDER_RESPONSE_INVALID$'):reply(owner,req,json.dumps(changed).encode())

@pytest.mark.parametrize('status',[None,400,401,403,404,408,422,429,500,503,599])
def test_error_is_unconfirmed_and_never_authorizes_retry(owner,status):
    r=reply(owner,raw=b'{"message":"unknown"}',status=status);p=r.to_payload()
    assert p['outcome']=='UNCONFIRMED' and p['observation'] is None and p['retry_authorized'] is False
    assert p['status']==status and p['actual_flat'] is None


def test_cancel_204_is_only_request_acceptance(owner):
    req=request(owner,operation='CANCEL_ORDER',parameters={'order_id':ORDER},body=None)
    p=reply(owner,req,b'',status=204).to_payload()
    assert p['outcome']=='CANCEL_REQUEST_ACCEPTED_UNCONFIRMED' and p['observation'] is None and p['actual_flat'] is None
    for status,raw in [(200,b'{}'),(204,b'{}')]:
        with pytest.raises(RuntimeRefused):reply(owner,req,raw,status=status)

@pytest.mark.parametrize('changes',[{'status':True},{'status':201},{'status':204},{'status':302},{'status':600},
 {'received_at':'2023-11-24T14:29:59Z'},{'received_at':'2023-11-24T14:30:10.000001Z'},
 {'received_at':'2023-11-24T14:30:10.000000001Z'},{'received_at':'2023-11-24T14:30:01'}])
def test_invalid_or_late_reply_context_refuses(owner,changes):
    with pytest.raises(RuntimeRefused):reply(owner,**changes)

@pytest.mark.parametrize('raw',[b'{}',b'null',b'[]',b'{"id":1,"id":2}',b'{"x":NaN}',b'x'*65537,b'\xff',b'['*40+b'0'+b']'*40],ids=['shape','null','array','duplicate','nonfinite','oversize','utf8','deep'])
def test_bad_success_never_retains_qualified_result(owner,raw):
    with pytest.raises(RuntimeRefused):reply(owner,raw=raw)

@pytest.mark.parametrize('change',[{'symbol':'MSFT'},{'qty':'3'},{'client_order_id':'cmp-other'},{'filled_qty':'3','filled_avg_price':'10','status':'filled'}, {'side':'sell'},{'time_in_force':'gtc'}])
def test_submit_reply_is_bound_to_exact_order(owner,change):
    with pytest.raises(RuntimeRefused):reply(owner,raw=json.dumps(order(**change)).encode())

@pytest.mark.parametrize('secret',[KEY,SECRET,base64.b64encode(SECRET.encode()).decode(),'APCA-API-KEY-ID'])
@pytest.mark.parametrize('escaped',[False,True])
def test_secret_reflections_refuse_before_retention_or_hash(owner,secret,escaped,monkeypatch):
    req=request(owner);raw=json.dumps(dict(order(),provider_message=secret)).encode()
    if escaped:raw=raw.replace(secret.encode(),''.join('\\u%04x'%ord(c) for c in secret).encode())
    import compertum.runtime.paper_order_qualification as mod
    original=mod._sha
    def watched(value):
        assert value!=raw, 'unqualified reply hashed before reflection check'
        return original(value)
    monkeypatch.setattr(mod,'_sha',watched)
    with pytest.raises(RuntimeRefused,match='^PAPER_READ_SECRET_REFLECTION$'):reply(owner,req,raw)

@pytest.mark.parametrize('status',[200,500])
def test_raw_private_account_reflection_is_rejected(owner,status):
    with pytest.raises(RuntimeRefused,match='^PAPER_ORDER_PRIVATE_ID_REFLECTION$'):
        reply(owner,raw=json.dumps(dict(order(),metadata=ACCOUNT)).encode(),status=status)


def test_non_json_errors_are_safe_fixed_refusals(owner):
    with pytest.raises(RuntimeRefused,match='^PAPER_ORDER_RESPONSE_INVALID$'):reply(owner,raw=b'<html>error</html>',status=503)
    p=reply(owner,raw=b'',status=500).to_payload();assert p['outcome']=='UNCONFIRMED' and p['raw_bytes']==0


def test_request_secret_reflection_is_refused_before_hash(owner,monkeypatch):
    import compertum.runtime.paper_order_qualification as mod
    seen=[];actual=mod._sha
    def watched(value):
        assert KEY.encode() not in value
        seen.append(True);return actual(value)
    monkeypatch.setattr(mod,'_sha',watched)
    with pytest.raises(RuntimeRefused,match='^PAPER_READ_SECRET_REFLECTION$'):
        request(owner,body=dict(BODY,client_order_id='cmp-'+KEY))


def test_other_credential_envelope_cannot_qualify_request(owner):
    req=request(owner);lease,_=owner
    other=seal_paper_credentials(lease,'fixture',bytearray(b'OTHER_INVENTED_KEY_123'),bytearray(b'OTHER_INVENTED_SECRET_123'))
    with pytest.raises(RuntimeRefused,match='^PAPER_ORDER_CONTEXT_MISMATCH$'):reply((lease,other),req)


def test_owner_revocation_prevents_reusing_private_context(owner):
    req=request(owner);lease,_=owner;release_owner(lease)
    with pytest.raises(RuntimeRefused):reply(owner,req)
    with pytest.raises(RuntimeRefused):req.wire()


def test_private_results_require_factory_and_mutation_is_detected(owner):
    with pytest.raises(RuntimeRefused):_PreparedOrderExchange()
    with pytest.raises(RuntimeRefused):_PrivateOrderReply()
    req=request(owner);object.__setattr__(req,'content',b'{}')
    with pytest.raises(RuntimeRefused):reply(owner,req)

@pytest.mark.parametrize('change',[{'account_id':'bad'},{'request_id':'bad'},{'intent_id':'bad'}, {'body':dict(BODY,qty='1.5')},{'created_at':'2023-11-24T14:30:00.000000001Z'}, {'operation':'CLOSE_ALL'}])
def test_invalid_prepared_request_is_refused(owner,change):
    with pytest.raises(RuntimeRefused):request(owner,**change)


def test_private_account_identity_is_integrity_bound(owner):
    req=request(owner);object.__setattr__(req,'private_account_id',INTENT)
    with pytest.raises(RuntimeRefused,match='^PAPER_ORDER_CONTEXT_MISMATCH$'):reply(owner,req)


def test_damaged_private_request_wire_returns_only_a_fixed_reason(owner):
    req=request(owner);object.__setattr__(req,'content',b'{not json')
    with pytest.raises(RuntimeRefused,match='^PAPER_ORDER_CONTEXT_MISMATCH$'):req.wire()
