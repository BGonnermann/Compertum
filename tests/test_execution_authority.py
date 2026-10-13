"""Native store/owners; reserve capacity alone is simulated in these small tests."""
import json
from types import SimpleNamespace
from uuid import uuid4
import pytest
from test_execution_health import pair,connect
from test_execution_risk import observation,bind,calendar,NOW
from compertum.persistence import open_store
from compertum.storage import create_journal_reserve
from compertum.runtime.errors import RuntimeRefused

@pytest.fixture
def authority(pair,monkeypatch):
 import compertum.execution_authority as module
 e,w,c,stops=pair;connect(e,w);store=open_store(e.lease,'execution');reserve=create_journal_reserve(e.lease,65536)
 monkeypatch.setattr(module,'execution_durable',lambda *args:reserve.receipt())
 monkeypatch.setattr(module,'time',SimpleNamespace(monotonic=lambda:c.mono,time=lambda:c.utc))
 a=module.ExecutionAuthority(store,reserve,e)
 return a,e,w,c

def packet(operation,**kwargs):return dict(request_id=str(uuid4()),subject_key='a'*64,command=dict(operation=operation,**kwargs))
def profile():return dict(calendar=calendar().to_payload(),inputs=bind(observation()).to_payload(),fixture_at=NOW,account_alias='fake-account')
def session(a):
 sid=str(uuid4());a.handle(packet('open_session',session_id=sid,profile=profile()));return sid

def advance(a,e,w,c,seconds):
 while seconds:
  step=min(seconds,10);c.mono+=step;c.utc+=step;seconds-=step
  e.receive(w.receipt());w.receive(e.receipt());a.tick()

def test_profile_is_immutable_and_session_starts_disarmed(authority):
 a,e,w,c=authority;sid=session(a);s=a.status();assert s['session_id']==sid and not s['armed'] and not s['supervised'] and s['scope']=='DETERMINISTIC_FAKE'
 with pytest.raises(RuntimeRefused,match='SUPERVISION_REQUIRED'):a.require_supervised()
 p=profile();p['account_alias']='fake-other'
 with pytest.raises(RuntimeRefused,match='SESSION_CONFLICT'):a.handle(packet('open_session',session_id=sid,profile=p))

@pytest.mark.parametrize('extra',['health','authorization','generation','supervision_at'])
def test_public_command_cannot_supply_authority(authority,extra):
 a,e,w,c=authority;p=packet('supervise');p['command'][extra]=True
 with pytest.raises(RuntimeRefused,match='CONTROL_PAYLOAD_DENIED'):a.handle(p)

def test_ack_retry_does_not_extend_five_minute_presence(authority):
 a,e,w,c=authority;session(a);p=packet('supervise');first=a.handle(p);advance(a,e,w,c,299)
 assert a.handle(p)==first and a.require_supervised()['session_id']==a.status()['session_id']
 advance(a,e,w,c,2)
 assert not a.status()['supervised'] and not a.status()['armed']
 with pytest.raises(RuntimeRefused,match='SUPERVISION_EXPIRED'):a.require_supervised()

def test_same_request_cannot_change_subject_or_payload(authority):
 a,e,w,c=authority;session(a);p=packet('supervise');a.handle(p)
 p['subject_key']='b'*64
 with pytest.raises(RuntimeRefused,match='REQUEST_CONFLICT'):a.handle(p)

def test_new_session_cannot_inherit_prior_supervision(authority):
 a,e,w,c=authority;session(a);a.handle(packet('supervise'));session(a)
 assert not a.status()['supervised']

def test_market_time_advances_from_native_elapsed_not_caller_stamp(authority):
 from compertum.execution_contracts import instant
 a,e,w,c=authority;session(a);a.handle(packet('supervise'));before=a.require_supervised()['market_at'];advance(a,e,w,c,10)
 assert (instant(a.require_supervised()['market_at'])-instant(before)).total_seconds()==10

def test_lost_health_disarms_and_invalidates_presence(authority):
 a,e,w,c=authority;session(a);a.handle(packet('supervise'));e.halt('PEER_UNAVAILABLE');a.tick()
 assert not a.status()['supervised'] and not a.status()['armed']
 with pytest.raises(RuntimeRefused,match='EXECUTION_HEALTH_UNVERIFIED'):a.handle(packet('supervise'))

def test_restart_invalidates_retained_presence_and_prior_request(authority):
 from compertum.execution_authority import ExecutionAuthority
 a,e,w,c=authority;sid=session(a);p=packet('supervise');old=a.handle(p)
 # Represent a restored/prior native instance. Actual separate-process case follows in integration.
 with a.store.conn:
  state=json.loads(a.store.conn.execute("SELECT value FROM state WHERE key='fake_operator_state'").fetchone()[0]);state['owner_instance']=str(uuid4())
  a.store.conn.execute("UPDATE state SET value=? WHERE key='fake_operator_state'",(json.dumps(state),))
 b=ExecutionAuthority(a.store,a.reserve,e)
 assert not b.status()['supervised'] and b.status()['session_id']==sid and b.handle(p)==old
 assert not b.status()['supervised']

def test_halt_never_submits_or_requires_healthy_peer(authority):
 a,e,w,c=authority;session(a);e.halt('PEER_UNAVAILABLE');r=a.handle(packet('halt'))
 assert r['operation']=='halt' and not a.status()['armed'] and a.status()['halted']

def test_profile_requires_matching_calendar_and_input_pin(authority):
 a,e,w,c=authority;p=profile();p['inputs']['calendar_sha256']='f'*64
 with pytest.raises(RuntimeRefused,match='SESSION_INPUTS_CHANGED'):a.handle(packet('open_session',session_id=str(uuid4()),profile=p))


@pytest.mark.parametrize('missing',['requests','profiles','state','head'])
def test_partial_authority_history_is_never_reinitialized(authority,missing):
 from compertum.execution_authority import ExecutionAuthority
 a,e,w,c=authority;session(a);request=packet('supervise');a.handle(request)
 with a.store.conn:
  if missing in {'requests','profiles'}:a.store.conn.execute('DROP TABLE fake_operator_'+missing)
  else:a.store.conn.execute('DELETE FROM state WHERE key=?',('fake_operator_state' if missing=='state' else 'fake_operator_version',))
 with pytest.raises(RuntimeRefused,match='OPERATOR_STATE_CORRUPT'):ExecutionAuthority(a.store,a.reserve,e)


def test_session_close_disarms_but_preserves_supervision_for_permitted_cancellation(authority):
 a,e,w,c=authority;p=profile();p['fixture_at']='2023-10-17T19:59:59+00:00'
 a.handle(packet('open_session',session_id=str(uuid4()),profile=p));a.handle(packet('supervise'));advance(a,e,w,c,2)
 status=a.status();assert status['reason']=='SESSION_CLOSED' and status['supervised'] and not status['armed'] and status['halted']
 assert a.require_supervised()['session_id']==status['session_id']
 a.handle(packet('supervise'));assert a.status()['supervised'] and not a.status()['armed']
 # After-hours cancellation still cannot bypass the native five-minute gate.
 advance(a,e,w,c,301)
 assert not a.status()['supervised'] and not a.status()['armed']
 with pytest.raises(RuntimeRefused,match='SUPERVISION_EXPIRED'):a.require_supervised()
 a.handle(packet('supervise'));assert a.require_supervised()['session_id']==status['session_id']


def test_fake_routing_retains_authenticated_identity_without_research_gate(monkeypatch):
 from types import SimpleNamespace
 from compertum.runtime.supervisor import Supervisor,ACTIONS
 import compertum.runtime.supervisor as module
 from compertum.runtime.bootstrap import validate_worker_commands
 s=object.__new__(Supervisor);s.partial_fixture=False;s.execution=SimpleNamespace(remote=object());s.health={'status':'RESEARCH_BLOCKED'}
 decision=SimpleNamespace(request_id=str(uuid4()),subject_key='b'*64);seen=[]
 monkeypatch.setattr(module,'call_owner',lambda r,act,p:seen.append((r,act,p)) or {'scope':'DETERMINISTIC_FAKE'})
 assert s._dispatch(decision,'fake_operator',{'operation':'halt'})=={'scope':'DETERMINISTIC_FAKE'}
 assert seen==[(s.execution.remote,'fake_operator',dict(request_id=decision.request_id,subject_key=decision.subject_key,command={'operation':'halt'}))]
 assert 'fake_operator' in ACTIONS and 'owner_heartbeat' not in ACTIONS
 for role in ('execution','watchdog','evaluation'):
  with pytest.raises(RuntimeRefused,match='WORKER_COMMAND_DENIED'):validate_worker_commands(role,frozenset({'fake_operator'}))
 s.partial_fixture=True
 with pytest.raises(RuntimeRefused,match='EXECUTION_UNAVAILABLE'):s._dispatch(decision,'fake_operator',{'operation':'status'})


@pytest.mark.parametrize('target',['requests','state'])
def test_ignored_write_rolls_back_operator_acknowledgment(authority,target):
 a,e,w,c=authority;session(a)
 with a.store.conn:
  if target=='requests':a.store.conn.execute("CREATE TRIGGER discard_ack BEFORE INSERT ON fake_operator_requests BEGIN SELECT RAISE(IGNORE); END")
  else:a.store.conn.execute("CREATE TRIGGER discard_ack BEFORE INSERT ON state WHEN NEW.key='fake_operator_state' BEGIN SELECT RAISE(IGNORE); END")
 with pytest.raises(RuntimeRefused,match='OPERATOR_WRITE_UNVERIFIED'):a.handle(packet('supervise'))
 assert not a.status()['supervised']
 assert a.store.conn.execute('SELECT count(*) FROM fake_operator_requests').fetchone()[0]==1


def test_oversize_state_is_refused(authority):
 from compertum.execution_authority import ExecutionAuthority
 a,e,w,c=authority
 with a.store.conn:a.store.conn.execute("UPDATE state SET value=? WHERE key='fake_operator_state'",('x'*65537,))
 with pytest.raises(RuntimeRefused,match='OPERATOR_STATE_CORRUPT'):ExecutionAuthority(a.store,a.reserve,e)
