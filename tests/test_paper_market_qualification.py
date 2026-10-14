"""Execution-owned market privacy: invented DPAPI credentials/local HTTP only."""
import base64,json,pickle,threading
from dataclasses import FrozenInstanceError,replace
from decimal import Decimal
import pytest
from compertum.data.encoding import canonical
from compertum.paper_market_inputs import _body,prepare_market_plan,prepare_market_request,MarketObservation
from compertum.paper_action_inputs import CurrentActionPage
from compertum.runtime.errors import RuntimeRefused
from compertum.runtime.owners import _LEASES,release_owner
from compertum.runtime.paper_credentials import seal_paper_credentials
from compertum.runtime.paper_market_qualification import (prepare_market_exchange,start_market_exchange,qualify_market_reply,_PreparedMarketExchange,_PrivateMarketReply)
from test_winhttp_get import owner,server,finish
from test_winhttp_data import request,AT,args,plan
from test_paper_read_preparation import KEY,SECRET

AFTER='2026-10-09T13:20:01Z'
RAW=b'{ "quotes": {"AAPL": {"bp":123.123456789012,"ap":123.123456789013}} }'

@pytest.fixture
def credentials(owner):return seal_paper_credentials(owner,'paper-primary',bytearray(KEY.encode()),bytearray(SECRET.encode()))

def prepared(owner,credentials,kind='QUOTE',req=None):return prepare_market_exchange(owner,credentials,request(owner,kind) if req is None else req,**args(kind))
def qualify(owner,credentials,exchange,raw=RAW,**edit):
 values=dict(status=200,received_at=AFTER);values.update(edit)
 return qualify_market_reply(owner,credentials,exchange,raw,**values)

@pytest.mark.parametrize('kind',['QUOTE','HISTORY','ACTION'])
def test_private_exact_bytes_decimal_and_injected_provenance(owner,credentials,kind):
 x=prepared(owner,credentials,kind);r=qualify(owner,credentials,x);p=r.to_payload()
 assert r.raw==RAW and _body(r.observation().raw)['quotes']['AAPL']['bp']==Decimal('123.123456789012')
 assert type(r.observation()) is (CurrentActionPage if kind=='ACTION' else MarketObservation)
 assert p['transport_provenance']=='UNVERIFIED' and p['credential_dispatch_binding']=='UNVERIFIED'
 assert p['outcome']=='HTTP_RESPONSE_OBSERVED' and p['age_ns']==10**9
 assert p['financial_accepted'] is p['transport_authorized'] is p['research_eligible'] is False
 assert p['semantic_qualification']=='NOT_PERFORMED' and p['timestamps']=='DECLARED'
 for obj in (x,r):
  assert all(s not in repr(obj) for s in (KEY,SECRET))
  with pytest.raises(RuntimeRefused):pickle.dumps(obj)
  with pytest.raises((FrozenInstanceError,AttributeError)):obj.content=b'{}'
 p['status']=500;assert r.to_payload()['status']==200
 with pytest.raises(RuntimeRefused):qualify(owner,credentials,x)

@pytest.mark.parametrize('token',[KEY,SECRET,base64.b64encode(KEY.encode()).decode(),base64.urlsafe_b64encode(SECRET.encode()).decode().rstrip('='),'APCA-API-KEY-ID','APCA-API-SECRET-KEY'])
@pytest.mark.parametrize('location',['key','value','escaped','error'])
def test_reflections_never_return_retained_reply(owner,credentials,token,location):
 if location=='key':raw=json.dumps({token:'unknown'}).encode()
 elif location=='escaped':raw=('{"unknown":"'+''.join('\\u%04x'%ord(c) for c in token)+'"}').encode()
 else:raw=json.dumps({'unknown':[{'value':token}]}).encode()
 x=prepared(owner,credentials)
 with pytest.raises(RuntimeRefused,match='^PAPER_READ_SECRET_REFLECTION$'):qualify(owner,credentials,x,raw,status=403 if location=='error' else 200)
 assert x._reply is None and x._closed

@pytest.mark.parametrize('raw',[b'',b'null',b'[]',b'{',b'\xff',b'{"x":1,"x":2}',b'{"x":NaN}',b'{"x":1e1000}',b'{"x":1234567890123456789}',b'x'*65537,b'{"x":'+b'['*20+b'0'+b']'*20+b'}'],ids=['empty','null','array','truncated','utf8','duplicate','nan','large_exponent','large_integer','oversize','deep'])
def test_malformed_or_unbounded_body_is_fixed_refusal(owner,credentials,raw):
 x=prepared(owner,credentials)
 with pytest.raises(RuntimeRefused,match='^PAPER_MARKET_RESPONSE_INVALID$'):qualify(owner,credentials,x,raw)
 assert x._reply is None and x._closed

@pytest.mark.parametrize('status',[True,None,201,204,302,399,600,'200'])
def test_bad_status_refuses(owner,credentials,status):
 with pytest.raises(RuntimeRefused):qualify(owner,credentials,prepared(owner,credentials),status=status)

@pytest.mark.parametrize('at,ok',[('2026-10-09T13:20:00Z',True),('2026-10-09T13:20:10Z',True),('2026-10-09T13:20:10.000000001Z',False),('2026-10-09T13:19:59.999999999Z',False),('2026-10-10T13:20:01Z',False)])
def test_exact_nanosecond_receipt_bounds(owner,credentials,at,ok):
 x=prepared(owner,credentials,'ACTION')
 if ok:assert qualify(owner,credentials,x,received_at=at).to_payload()['received_at']==at
 else:
  with pytest.raises(RuntimeRefused):qualify(owner,credentials,x,received_at=at)

@pytest.mark.parametrize('field,value',[('_content',b'{}'),('_plan_bytes',b'{}'),('_credential_sha256','0'*64),('_owner_generation',99),('_owner_instance','changed')])
def test_mutated_context_cannot_qualify(owner,credentials,field,value):
 x=prepared(owner,credentials);object.__setattr__(x,field,value)
 with pytest.raises(RuntimeRefused):qualify(owner,credentials,x)


def test_wrong_envelope_alias_project_and_request_mutation(owner,credentials):
 x=prepared(owner,credentials)
 other=seal_paper_credentials(owner,'paper-primary',bytearray(KEY.encode()),bytearray(SECRET.encode()))
 with pytest.raises(RuntimeRefused):qualify(owner,other,x)
 for p in (replace(credentials,account_alias='other'),replace(credentials,project_id='a'*64)):
  with pytest.raises(RuntimeRefused):prepared(owner,p)
 req=request(owner);x=prepared(owner,credentials,req=req);object.__setattr__(req,'content',b'{}')
 with pytest.raises(RuntimeRefused):qualify(owner,credentials,x)


def test_secret_plan_alias_and_request_cursor_are_rejected_before_context(owner):
 protected=seal_paper_credentials(owner,KEY,bytearray(KEY.encode()),bytearray(SECRET.encode()))
 p=prepare_market_plan(project_id=owner.project_id,account_alias=KEY,symbol='AAPL',session_date='2026-10-09',created_at=AT)
 req=prepare_market_request(p,operation='QUOTE',request_id='00000000-0000-0000-0000-000000000001',created_at=AT)
 with pytest.raises(RuntimeRefused,match='PAPER_READ_SECRET_REFLECTION'):prepared(owner,protected,req=req)
 protected=seal_paper_credentials(owner,'paper-primary',bytearray(KEY.encode()),bytearray(SECRET.encode()))
 with pytest.raises(RuntimeRefused,match='PAPER_READ_SECRET_REFLECTION'):prepared(owner,protected,'HISTORY',request(owner,'HISTORY',SECRET))


def test_context_budget_close_and_owner_revocation(owner,credentials):
 initial=list(_LEASES[owner].resources);xs=[prepared(owner,credentials) for _ in range(4)]
 with pytest.raises(RuntimeRefused,match='PAPER_MARKET_CONTEXT_LIMIT'):prepared(owner,credentials)
 xs[0].close();xs[0].close();x=prepared(owner,credentials);r=qualify(owner,credentials,x)
 release_owner(owner)
 for get in (lambda:r.raw,lambda:r.content,r.to_payload,r.observation,lambda:x.content):
  with pytest.raises(RuntimeRefused):get()
 assert x._closed and x._reply is None and all(a._closed for a in xs)


def test_forged_constructors_and_unregistered_context_refused(owner,credentials):
 for cls in (_PreparedMarketExchange,_PrivateMarketReply):
  with pytest.raises(RuntimeRefused):cls()
 x=object.__new__(_PreparedMarketExchange)
 with pytest.raises(RuntimeRefused):qualify(owner,credentials,x)

@pytest.mark.parametrize('kind',['QUOTE','HISTORY','ACTION'])
@pytest.mark.parametrize('status',[200,403])
def test_owned_loopback_exact_result_and_credentials_not_sent(owner,credentials,kind,status):
 x=prepared(owner,credentials,kind)
 with server(body=RAW,status=status) as (port,_,seen):
  t=start_market_exchange(x,_test_port=port);result=finish(t)
  r=qualify(owner,credentials,x,result.body,status=result.status_code,result=result);p=r.to_payload()
  assert p['transport_provenance']=='LOOPBACK_FIXTURE' and p['credential_dispatch_binding']=='NOT_SENT_FIXTURE'
  assert p['outcome']==('HTTP_RESPONSE_OBSERVED' if status==200 else 'HTTP_REFUSED')
  assert t.native_closed and len(seen)==1 and 'APCA-API-KEY-ID' not in seen[0][1]
  assert seen[0][1]['X-Compertum-Test']=='synthetic'
  with pytest.raises(RuntimeRefused):start_market_exchange(x,_test_port=port)
 x.close();assert t._result is None

@pytest.mark.parametrize('mutation',['result','target','origin','body','missing_result','request','plan','lease'])
def test_native_result_or_context_substitution_cannot_gain_provenance(owner,credentials,mutation):
 x=prepared(owner,credentials)
 with server(body=RAW) as (port,_,seen):
  t=start_market_exchange(x,_test_port=port);r=finish(t);raw=r.body
  if mutation=='result':r=replace(r)
  elif mutation=='target':t._wire_path='/other'
  elif mutation=='origin':t._origin=('data.alpaca.markets',443,True)
  elif mutation=='body':raw=b'{}'
  elif mutation=='missing_result':r=None
  elif mutation=='request':t._request_bytes=b'{}'
  elif mutation=='plan':t._plan_sha256='0'*64
  elif mutation=='lease':t._lease=object()
  with pytest.raises(RuntimeRefused):qualify(owner,credentials,x,raw,result=r)
  assert x._closed and x._reply is None and len(seen)==1


def test_pinned_envelope_is_preserved_before_fixture_tls_refusal(owner,credentials,monkeypatch):
 import compertum.runtime._winhttp_get as native
 import compertum.runtime.paper_market_qualification as module
 real=module._OwnedDataGet.__init__;seen=[]
 class Boundary(Exception):pass
 monkeypatch.setattr(native,'_API',lambda:(_ for _ in ()).throw(Boundary()))
 def capture(self,*a,**kw):
  assert kw['headers']=={'APCA-API-KEY-ID':KEY,'APCA-API-SECRET-KEY':SECRET};seen.append(True);return real(self,*a,**kw)
 monkeypatch.setattr(module._OwnedDataGet,'__init__',capture)
 x=prepared(owner,credentials)
 with pytest.raises(RuntimeRefused,match='HTTP_FIXTURE_QUEUE_TLS_FORBIDDEN'):start_market_exchange(x)
 assert seen==[True] and x._closed


def test_concurrent_close_cancels_native_and_revokes_private_access(owner,credentials):
 x=prepared(owner,credentials)
 with server(stall=True) as (port,arrived,_):
  t=start_market_exchange(x,_test_port=port);assert arrived.wait(1)
  errors=[]
  def close():
   try:x.close()
   except BaseException as e:errors.append(type(e).__name__)
  thread=threading.Thread(target=close);thread.start();thread.join(2)
  assert not thread.is_alive() and not errors and x._closed and t.native_closed
  with pytest.raises(RuntimeRefused):qualify(owner,credentials,x)


def test_final_diagnostic_reflection_is_rejected(owner):
 protected=seal_paper_credentials(owner,'paper-primary',bytearray(b'HTTP_REFUSED'),bytearray(SECRET.encode()))
 x=prepared(owner,protected)
 with pytest.raises(RuntimeRefused,match='PAPER_READ_SECRET_REFLECTION'):qualify(owner,protected,x,b'{"message":"denied"}',status=403)
 assert x._reply is None and x._closed


def test_node_count_bound_and_reply_mutation(owner,credentials):
 x=prepared(owner,credentials)
 with pytest.raises(RuntimeRefused):qualify(owner,credentials,x,b'{"x":['+b'0,'*10000+b'0]}')
 x=prepared(owner,credentials);r=qualify(owner,credentials,x);object.__setattr__(r,'_raw',b'{}')
 with pytest.raises(RuntimeRefused):r.raw


def test_revoked_exchange_cannot_move_to_another_owner(owner,credentials,tmp_path):
 from compertum.runtime.owners import acquire_owner
 from compertum.runtime.identity import resolve_project
 x=prepared(owner,credentials);r=qualify(owner,credentials,x)
 release_owner(owner);other=tmp_path/'other';other.mkdir();new=acquire_owner(resolve_project(other),'execution')
 try:
  with pytest.raises(RuntimeRefused):qualify(new,credentials,x)
  with pytest.raises(RuntimeRefused):r.observation()
 finally:release_owner(new)
