"""Pure read plans and execution-owned synthetic response privacy; no dispatch."""
from dataclasses import replace,FrozenInstanceError
import hashlib,json,pickle
import pytest
from compertum.domain import ContractError
from compertum.runtime.errors import RuntimeRefused
from compertum.runtime.identity import resolve_project
from compertum.runtime.owners import acquire_owner,release_owner
from compertum.runtime.paper_credentials import seal_paper_credentials
from compertum.paper_read_preparation import PreparedReadPlan,PreparedReadRequest,prepare_read_plan,prepare_read_request
from compertum.runtime.paper_read_secrecy import qualify_read_reply
from test_paper_responses import account,ACCOUNT
from test_paper_portfolio import position,order

AT='2023-11-24T14:30:00Z';END='2023-11-24T14:31:00Z';RID='22222222-2222-4222-8222-222222222222'
KEY='DUMMY_KEY_123456789';SECRET='DUMMY_SECRET_123456789'

@pytest.fixture
def owner(tmp_path):
    project=resolve_project(tmp_path);lease=acquire_owner(project,'execution')
    p=seal_paper_credentials(lease,'fixture',bytearray(KEY.encode()),bytearray(SECRET.encode()))
    try:yield project,lease,p
    finally:release_owner(lease)


def plan(project_id='a'*64,**kw):
    args=dict(project_id=project_id,account_alias='fixture',created_at=AT,start_expires_at=END,session_date='2023-11-24');args.update(kw)
    return prepare_read_plan(**args)


def req(owner,op='ACCOUNT',**kw):
    project,_,p=owner;args=dict(request_id=RID,operation=op,created_at=AT,packet_started_at=AT,expected_account_id=None if op=='ACCOUNT' else ACCOUNT,credential_sha256=hashlib.sha256(p.ciphertext).hexdigest(),after_order_id=None);args.update(kw)
    return prepare_read_request(plan(project.project_id),**args)


def qualify(owner,request=None,raw=None,received_at='2023-11-24T14:30:01Z'):
    _,lease,p=owner
    return qualify_read_reply(lease,p,request or req(owner),json.dumps(account()).encode() if raw is None else raw,received_at=received_at)


def test_frozen_plan_has_fixed_bounds_alias_and_no_authority():
    p=plan();v=p.to_payload()
    assert v['origin']=='https://paper-api.alpaca.markets' and v['maximum_gets']==13 and v['maximum_order_pages']==8
    assert v['orders_per_page']==25 and v['packet_timeout_seconds']==30 and v['request_timeout_seconds']==10
    assert v['approval_status']=='NOT_GRANTED' and v['financial_accepted'] is False
    assert 'account_id' not in v
    assert PreparedReadPlan(p.content)==p
    v['maximum_gets']=14
    with pytest.raises(ContractError):PreparedReadPlan(json.dumps(v,sort_keys=True,separators=(',',':')).encode())
    with pytest.raises((FrozenInstanceError,AttributeError)):p.content=b'{}'


@pytest.mark.parametrize('change',[{'project_id':'x'},{'account_alias':'bad\nname'},{'start_expires_at':AT},{'start_expires_at':'2023-11-24T14:31:01Z'},{'session_date':'2023-11-25'},{'created_at':'2023-11-24T14:30:00'}])
def test_invalid_plan_is_rejected(change):
    with pytest.raises(ContractError):plan(**change)


@pytest.mark.parametrize('operation,target',[('ACCOUNT','/v2/account'),('CLOCK','/v2/clock'),('POSITIONS','/v2/positions'),('CALENDAR','/v2/calendar?start=2023-11-24&end=2023-11-24'),('ORDERS','/v2/orders?status=all&direction=asc&nested=false&limit=25')])
def test_only_frozen_read_routes_and_alias_public_context(owner,operation,target):
    r=req(owner,operation);v=r.to_payload()
    assert v['method']=='GET' and v['target']==target and v['timeout_ms']==10000
    assert ACCOUNT.encode() not in r.content and ACCOUNT not in repr(r)
    assert r.expected_account_id==(None if operation=='ACCOUNT' else ACCOUNT)
    with pytest.raises(RuntimeRefused):pickle.dumps(r)


@pytest.mark.parametrize('change',[{'operation':'SUBMIT_ORDER'},{'operation':'CANCEL_ORDER'},{'operation':'ORDER_BY_ID'},{'operation':'ORDERS','expected_account_id':None},{'operation':'CLOCK','after_order_id':RID},{'after_order_id':'bad'},{'created_at':'2023-11-24T14:29:59Z'},{'packet_started_at':END},{'created_at':'2023-11-24T14:30:30Z'},{'credential_sha256':'bad'}])
def test_request_scope_and_deadline_fail_closed(owner,change):
    with pytest.raises(ContractError):req(owner,**change)


def test_started_packet_can_finish_after_start_expiry_within_own_deadline(owner):
    r=req(owner,'CLOCK',packet_started_at='2023-11-24T14:30:59Z',created_at='2023-11-24T14:31:20Z')
    assert r.to_payload()['timeout_ms']==9000


def test_midnight_cannot_reuse_previous_calendar(owner):
    project,_,p=owner
    pp=plan(project.project_id,created_at='2023-11-25T04:59:50Z',start_expires_at='2023-11-25T05:00:50Z')
    with pytest.raises(ContractError):prepare_read_request(pp,request_id=RID,operation='ACCOUNT',created_at='2023-11-25T05:00:01Z',packet_started_at='2023-11-25T04:59:55Z',expected_account_id=None,credential_sha256=hashlib.sha256(p.ciphertext).hexdigest())


def test_account_discovery_is_private_and_unconfirmed(owner):
    result=qualify(owner);v=result.to_payload()
    assert result.private_account_id==ACCOUNT and result.raw==json.dumps(account()).encode()
    assert v['account_identity']=='DISCOVERED_UNCONFIRMED' and v['native_transport_verified'] is False
    assert ACCOUNT.encode() not in result.content and ACCOUNT not in repr(result)
    assert 'id' not in v['observation'] and v['actual_flat'] is None
    with pytest.raises(RuntimeRefused):pickle.dumps(result)
    assert v['raw_sha256']==hashlib.sha256(result.raw).hexdigest()


def test_expected_account_mismatch_is_not_discovery(owner):
    with pytest.raises(RuntimeRefused,match='^PAPER_READ_RESPONSE_INVALID$'):qualify(owner,req(owner,expected_account_id=RID))


@pytest.mark.parametrize('where',['known','unknown','key','unicode','mixed','base64','malformed'])
def test_secret_reflection_is_never_returned_or_hashed(owner,where,monkeypatch):
    import base64
    import compertum.paper_portfolio as portfolio
    def forbidden(*a,**k):raise AssertionError('row hashed before secrecy check')
    monkeypatch.setattr(portfolio,'_sha',forbidden)
    body=[position()]
    if where=='known':body[0]['symbol']=KEY
    elif where=='key':body[0][KEY]='value'
    elif where=='base64':body[0]['extra']=base64.b64encode(SECRET.encode()).decode()
    else:body[0]['extra']=SECRET
    raw=json.dumps(body).encode()
    if where=='unicode':raw=raw.replace(SECRET.encode(),''.join('\\u%04x'%ord(x) for x in SECRET).encode())
    elif where=='mixed':raw=raw.replace(SECRET.encode(),b'\\u0044UMMY_SECRET_123456789')
    elif where=='malformed':raw=raw[:-1]
    with pytest.raises(RuntimeRefused) as caught:qualify(owner,req(owner,'POSITIONS'),raw)
    assert str(caught.value) in {'PAPER_READ_SECRET_REFLECTION','PAPER_READ_RESPONSE_INVALID'}
    assert KEY not in str(caught.value) and SECRET not in str(caught.value)


@pytest.mark.parametrize('raw',[b'{"x":1,"x":2}',b'null',b'\xff',b'['*40+b'0'+b']'*40,b'x'*65537],ids=['duplicate','null','utf8','deep','oversize'])
def test_malformed_response_is_fixed_refusal(owner,raw):
    with pytest.raises(RuntimeRefused,match='^PAPER_READ_RESPONSE_INVALID$'):qualify(owner,raw=raw)


def test_credential_instance_swap_is_rejected_even_under_same_alias(owner):
    project,lease,p=owner;r=req(owner)
    other=seal_paper_credentials(lease,'fixture',bytearray(KEY.encode()),bytearray(SECRET.encode()))
    with pytest.raises(RuntimeRefused,match='^PAPER_READ_CONTEXT_MISMATCH$'):qualify_read_reply(lease,other,r,json.dumps(account()).encode(),received_at='2023-11-24T14:30:01Z')


@pytest.mark.parametrize('at',['2023-11-24T14:29:59Z','2023-11-24T14:30:11Z'])
def test_response_arrival_must_match_request_bound(owner,at):
    with pytest.raises(RuntimeRefused,match='^PAPER_READ_RESPONSE_INVALID$'):qualify(owner,received_at=at)


def test_order_unknown_rows_remain_explicit_not_empty(owner):
    result=qualify(owner,req(owner,'ORDERS'),json.dumps([order(order_class='bracket'),{'unexpected':'row'}]).encode())
    v=result.to_payload();assert len(v['observation']['rows'])==2 and v['observation']['deficiencies']
    assert v['actual_flat'] is None and v['native_transport_verified'] is False


def test_received_reply_cannot_cross_frozen_new_york_date(owner):
    project,_,p=owner
    pp=plan(project.project_id,created_at='2023-11-25T04:59:50Z',start_expires_at='2023-11-25T05:00:50Z')
    r=prepare_read_request(pp,request_id=RID,operation='ACCOUNT',created_at='2023-11-25T04:59:59Z',packet_started_at='2023-11-25T04:59:55Z',expected_account_id=None,credential_sha256=hashlib.sha256(p.ciphertext).hexdigest())
    with pytest.raises(RuntimeRefused,match='^PAPER_READ_RESPONSE_INVALID$'):qualify(owner,r,received_at='2023-11-25T05:00:01Z')


def test_boundary_revalidates_damaged_request_with_fixed_refusal(owner):
    r=req(owner);object.__setattr__(r,'content',b'{}')
    with pytest.raises(RuntimeRefused,match='^PAPER_READ_RESPONSE_INVALID$'):qualify(owner,r)


def test_parsed_result_cannot_be_constructed_as_qualified_by_caller():
    from compertum.runtime.paper_read_secrecy import _PrivateParsedRead
    with pytest.raises(RuntimeRefused,match='^PAPER_READ_UNQUALIFIED_RESULT$'):
        _PrivateParsedRead(b'{"native_transport_verified":true,"financial_accepted":true}',bytearray(b'anything'),'not-a-uuid')
