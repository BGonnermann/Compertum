"""Private live read context; invented replies never establish actual admission."""
import json,pickle
from types import SimpleNamespace
from uuid import uuid4
import pytest
from test_execution_health import pair
from test_paper_read_owner import owner,prepare,approve,start,command
from test_paper_read_preparation import ACCOUNT,KEY,SECRET
from compertum.runtime.errors import RuntimeRefused
from compertum.runtime.paper_preflight import _PaperPreflight,capture_preflight,native_read_provenance


def complete(o):
 p=prepare(o);approve(o,p);start(o,p)
 for _ in range(20):o.a.tick()
 assert command(o,'status',packet_id=p['packet_id'])['state']=='EVIDENCE_READY'
 return p,o.a.preflight(p['packet_id'])


def test_live_completed_reader_stays_private_and_blocked(owner):
 p,context=complete(owner);r=context.diagnostic()
 assert r['preflight_status']=='BLOCKED' and r['transport_authorized'] is r['financial_accepted'] is False
 assert r['transport_provenance']=='UNVERIFIED_TRANSPORT' and r['actual_flat'] is None
 assert r['response_count']==6 and r['positions']==r['orders']==0
 assert r['calendar_agreement']=='MATCHES_PINNED_CALENDAR'
 assert {'ACCOUNT_CONFIRMATION_UNVERIFIED','OWNERSHIP_UNVERIFIED','QUOTE_EVIDENCE_UNVERIFIED','SUPERVISION_UNVERIFIED'}<=set(r['deficiencies'])
 raw=json.dumps(r)
 assert all(secret not in raw+repr(context) for secret in (KEY,SECRET,ACCOUNT))
 with pytest.raises(RuntimeRefused):pickle.dumps(context)
 r['deficiencies'].clear();assert context.diagnostic()['deficiencies']
 assert len(owner.calls)==6


def test_no_context_before_complete_and_no_public_route(owner):
 o=owner;p=prepare(o)
 with pytest.raises(RuntimeRefused,match='PREFLIGHT_UNAVAILABLE'):o.a.preflight(p['packet_id'])
 with pytest.raises(RuntimeRefused):command(o,'preflight',packet_id=p['packet_id'])
 with pytest.raises(RuntimeRefused):capture_preflight(SimpleNamespace(),{})
 with pytest.raises(RuntimeRefused):_PaperPreflight()


@pytest.mark.parametrize('change',['wrong_packet','close','restart','new_packet','new_credentials','owner_generation','content','account','empty_records'])
def test_lifetime_and_binding_substitutions_refused(owner,monkeypatch,change):
 o=owner;p,c=complete(o)
 if change=='wrong_packet':
  with pytest.raises(RuntimeRefused):o.a.preflight(str(uuid4()))
  return
 if change=='close':o.a.close()
 elif change=='restart':o.a.close();o.a=o.module.PaperReadOwner(o.a.store,o.a.reserve,o.e)
 elif change=='new_packet':
  from compertum.runtime.paper_read_evidence import publish_read_evidence
  child=o.manager.split_grant(o.grant,len(o.a._cipher.ciphertext))
  manifest=publish_read_evidence(o.manager,child,o.a._cipher)
  o.a.transfer(dict(operation='ack',packet_id=p['packet_id'],manifest=manifest))
  o.task=str(uuid4());o.grant=o.manager.reserve_bytes(o.task,'records',3*1024**2)
  prepare(o)
 elif change=='new_credentials':
  from compertum.runtime.paper_credentials import seal_paper_credentials
  import compertum.runtime.paper_preflight as module
  other=seal_paper_credentials(o.a.lease,'fixture',bytearray(b'DIFFERENTKEY'),bytearray(b'DIFFERENTSECRET'))
  monkeypatch.setattr(module,'load_paper_slot',lambda *a:other)
 elif change=='owner_generation':object.__setattr__(c,'_generation',o.a.lease.generation+1)
 elif change=='content':object.__setattr__(c,'content',b'{}')
 elif change=='empty_records':object.__setattr__(c,'_records',())
 elif change=='account':object.__setattr__(c,'_account_id','22222222-2222-4222-8222-222222222222')
 with pytest.raises(RuntimeRefused):c.diagnostic()


@pytest.mark.parametrize('utc_delta,mono_delta',[(31,31),(-1,1),(1,-1),(6,0)])
def test_retrieval_never_renews_freshness_or_accepts_clock_jump(owner,utc_delta,mono_delta):
 o=owner;p,c=complete(o);o.clock.utc+=utc_delta;o.clock.mono+=mono_delta
 with pytest.raises(RuntimeRefused):c.diagnostic()


def test_original_request_age_matters_even_with_recent_capture(owner,monkeypatch):
 o=owner;p=prepare(o);approve(o,p);start(o,p)
 for _ in range(8):o.a.tick()
 o.clock.utc+=20;o.clock.mono+=20
 import test_paper_read_owner as fixture
 from datetime import datetime,timezone
 original=fixture.body
 def changed(op):
  value=original(op)
  if op=='CLOCK':value=dict(value,timestamp=datetime.fromtimestamp(o.clock.utc,timezone.utc).isoformat())
  return value
 monkeypatch.setattr(fixture,'body',changed)
 for _ in range(12):o.a.tick()
 c=o.a.preflight(p['packet_id']);o.clock.utc+=11;o.clock.mono+=11
 with pytest.raises(RuntimeRefused,match='PREFLIGHT_STALE'):c.diagnostic()


@pytest.mark.parametrize('change',['health','reserve','wrong_reserve_lease'])
def test_live_controls_rechecked_after_capture(owner,monkeypatch,change):
 o=owner;p,c=complete(o)
 if change=='health':o.e.halt('FIXTURE_HEALTH_LOST')
 elif change=='reserve':o.a.reserve=SimpleNamespace(lease=o.a.lease,receipt=lambda:{})
 else:monkeypatch.setattr(o.a.reserve,'lease',o.w.lease)
 with pytest.raises(RuntimeRefused):c.diagnostic()


def test_changed_calendar_preserves_exact_blocker(owner,monkeypatch):
 import test_paper_read_owner as fixture
 original=fixture.body
 def changed(op):
  value=original(op)
  if op=='CALENDAR':value=[dict(date='2023-11-24',open='09:30',close='16:00')]
  return value
 monkeypatch.setattr(fixture,'body',changed)
 p,c=complete(owner);assert 'CALENDAR_DISAGREEMENT' in c.diagnostic()['deficiencies']


def test_incomplete_packet_never_produces_preflight(owner,monkeypatch):
 import test_paper_read_owner as fixture
 original=fixture.body
 def changed(op):
  value=original(op)
  if op=='CLOCK':value=dict(value,timestamp='2023-11-24T14:29:00Z')
  return value
 monkeypatch.setattr(fixture,'body',changed)
 p=prepare(owner);approve(owner,p);start(owner,p)
 for _ in range(20):owner.a.tick()
 with pytest.raises(RuntimeRefused,match='PREFLIGHT_UNAVAILABLE'):owner.a.preflight(p['packet_id'])


def test_caller_transport_label_cannot_establish_native_provenance(owner):
 o=owner;p=prepare(o);approve(o,p);start(o,p);o.a.tick();request=o.calls[0].request
 fake=SimpleNamespace(_lease=o.a.lease,_origin=('paper-api.alpaca.markets',443,True),_wire_path=request.to_payload()['target'],_method='GET',native_closed=True)
 result=SimpleNamespace(status_code=200,body=b'{}');fake._result=result
 assert native_read_provenance(fake,result,o.a.lease,request)['origin']=='UNVERIFIED_TRANSPORT'


def test_no_history_is_not_empty_verified_ownership(owner):
 p,c=complete(owner);r=c.diagnostic()
 assert r['local_history']['status']=='UNAVAILABLE' and 'OWNERSHIP_UNVERIFIED' in r['deficiencies']
 assert owner.a.store.conn.execute("SELECT 1 FROM sqlite_master WHERE name='fake_intents'").fetchone() is None


def test_private_context_close_serializes_with_owner_scope(owner):
 from threading import Event,Thread
 from compertum.runtime.owners import _MUTEX
 p,c=complete(owner);started=Event();closed=Event()
 def close():
  started.set();c.close();closed.set()
 t=Thread(target=close)
 try:
  with _MUTEX:
   t.start();assert started.wait(1)
   assert not closed.wait(.05)
   assert c.diagnostic()['preflight_status']=='BLOCKED'
 finally:t.join(2)
 assert not t.is_alive() and closed.is_set()
 with pytest.raises(RuntimeRefused):c.diagnostic()


@pytest.mark.parametrize('at,is_open,next_open,next_close',[
 ('2023-11-24T14:29:00Z',False,'2023-11-24T14:30:00Z','2023-11-24T18:00:00Z'),
 ('2023-11-24T14:30:00Z',True,'2023-11-27T14:30:00Z','2023-11-24T18:00:00Z'),
 ('2023-11-24T18:00:00Z',False,'2023-11-27T14:30:00Z','2023-11-27T21:00:00Z')],ids=['preopen','opening','closed'])
@pytest.mark.parametrize('changed',[None,'next_open','next_close'],ids=['correct','wrong_open','wrong_close'])
def test_clock_successors_match_pinned_early_close_and_weekend(at,is_open,next_open,next_close,changed):
 from compertum.runtime.paper_preflight import _calendar
 clock=dict(timestamp=at,is_open=is_open,next_open=next_open,next_close=next_close)
 if changed:clock[changed]='2023-11-28T14:30:00Z'
 records=[dict(operation='CALENDAR',observation=[dict(date='2023-11-24',open='09:30',close='13:00')]),
          dict(operation='CLOCK',observation=clock,received_at=at)]
 agreement,reasons=_calendar(records,'2023-11-24')
 assert agreement=='MATCHES_PINNED_CALENDAR'
 expected=[] if is_open else ['MARKET_NOT_OPEN']
 if changed:expected.append('CLOCK_OPEN_DISAGREEMENT' if changed=='next_open' else 'CLOCK_CLOSE_DISAGREEMENT')
 assert set(reasons)==set(expected)
