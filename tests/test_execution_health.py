"""Native peer identity and monotonic/UTC liveness; no broker effects."""
from copy import deepcopy
from types import SimpleNamespace
import pytest
from compertum.runtime.identity import resolve_project
from compertum.runtime.owners import acquire_owner,release_owner
from compertum.runtime.errors import RuntimeRefused

@pytest.fixture
def pair(tmp_path,monkeypatch):
 import compertum.runtime.execution_health as module
 clock=SimpleNamespace(mono=100.,utc=1000.)
 monkeypatch.setattr(module,'time',SimpleNamespace(monotonic=lambda:clock.mono,time=lambda:clock.utc))
 project=resolve_project(tmp_path);e=acquire_owner(project,'execution');w=acquire_owner(project,'watchdog');stops=[]
 try:
  execution=module.MutualHealth(e,lambda r:stops.append(('execution',r)),required=True)
  watchdog=module.MutualHealth(w,lambda r:stops.append(('watchdog',r)),required=False)
  yield execution,watchdog,clock,stops
 finally:release_owner(w);release_owner(e)

def connect(e,w):
 e.receive(w.receipt());w.receive(e.receipt())

def test_unbound_owner_cannot_admit_then_exact_native_peers_qualify(pair):
 e,w,c,stops=pair
 assert not e.status()['verified']
 connect(e,w)
 assert e.status()['verified'] and w.status()['verified'] and stops==[]

@pytest.mark.parametrize('field,value',[('generation',999),('project_id','0'*64),('sequence',True),('observed_monotonic',float('nan')),('observed_utc',float('inf'))])
def test_forged_or_unbounded_observations_halt(pair,field,value):
 e,w,c,stops=pair;p=w.receipt();p[field]=value
 with pytest.raises(RuntimeRefused):e.receive(p)
 assert not e.status()['verified'] and stops

@pytest.mark.parametrize('field,value',[('role','evaluation'),('pid',1),('creation_filetime',1),('process_instance_id','00000000-0000-4000-8000-000000000001')])
def test_changed_native_peer_identity_halts(pair,field,value):
 e,w,c,stops=pair;p=w.receipt();p['identity'][field]=value
 with pytest.raises(RuntimeRefused):e.receive(p)
 assert not e.status()['verified']

def test_replayed_packet_cannot_refresh_health(pair):
 e,w,c,stops=pair;p=w.receipt();e.receive(p);c.mono+=1;c.utc+=1
 with pytest.raises(RuntimeRefused,match='HEARTBEAT_REPLAY'):e.receive(p)
 assert not e.status()['verified']

def test_expired_heartbeat_halts_and_fresh_packet_does_not_rearm(pair):
 e,w,c,stops=pair;connect(e,w)
 for _ in range(16):c.mono+=1;c.utc+=1;e.tick()
 assert e.status()['reason']=='PEER_HEARTBEAT_STALE'
 e.receive(w.receipt());assert not e.status()['verified']
 assert len([s for s in stops if s[0]=='execution'])==1

@pytest.mark.parametrize('mono,utc,reason',[(16,16,'ELAPSED_CLOCK_GAP'),(-1,-1,'CLOCK_REVERSED'),(1,7,'CLOCK_MISMATCH')])
def test_clock_gap_or_reversal_is_sticky(pair,mono,utc,reason):
 e,w,c,stops=pair;connect(e,w);c.mono+=mono;c.utc+=utc;e.tick()
 assert e.status()['reason']==reason and not e.status()['verified']

def test_unhealthy_peer_halts_without_using_research_status(pair):
 e,w,c,stops=pair;p=w.receipt(healthy=False);e.receive(p)
 assert e.status()['reason']=='PEER_UNHEALTHY'

def test_stale_original_observation_cannot_be_retimed_by_relay(pair):
 e,w,c,stops=pair;p=w.receipt()
 for _ in range(16):c.mono+=1;c.utc+=1;e.tick()
 with pytest.raises(RuntimeRefused):e.receive(p)
 assert not e.status()['verified']


def test_cumulative_clock_drift_is_detected(pair):
 e,w,c,stops=pair;connect(e,w)
 for _ in range(2):c.mono+=1;c.utc+=5;e.tick()
 assert e.status()['reason']=='CLOCK_MISMATCH' and not e.status()['verified']

def test_float_pid_is_not_a_native_identity(pair):
 e,w,c,stops=pair;p=w.receipt();p['identity']['pid']=float(p['identity']['pid'])
 with pytest.raises(RuntimeRefused,match='PEER_IDENTITY_CHANGED'):e.receive(p)
 assert not e.status()['verified']

def test_out_of_order_fresh_packet_cannot_rewind_measurement_time(pair):
 e,w,c,stops=pair;p=w.receipt();e.receive(p);c.mono+=1;c.utc+=1;p=w.receipt();p['observed_monotonic']-=2;p['observed_utc']-=2
 with pytest.raises(RuntimeRefused,match='HEARTBEAT_REORDERED'):e.receive(p)
 assert not e.status()['verified']


@pytest.mark.parametrize('failed_peer',['execution','watchdog'])
def test_supervisor_rejects_negative_relay_ack(monkeypatch,failed_peer):
 from contextlib import nullcontext
 import compertum.runtime.supervisor as module
 s=object.__new__(module.Supervisor);s.partial_fixture=False;s.watchdog='watchdog';s.execution=SimpleNamespace(remote='execution');s.evaluation=SimpleNamespace(remote='evaluation');stops=[]
 s.halt=lambda reason:stops.append(reason);s.store=SimpleNamespace(conn=nullcontext());s.coordinator=SimpleNamespace(_state=lambda *args:None)
 def call(remote,action,payload):
  if action=='status':return dict(status='HEALTHY',heartbeat={'role':remote},observed_monotonic=module.time.monotonic())
  return dict(verified=remote!=failed_peer,reason='PEER_HEARTBEAT_STALE' if remote==failed_peer else None)
 monkeypatch.setattr(module,'call_owner',call);monkeypatch.setattr(module,'available_physical_memory',lambda:10*1024**3)
 s.poll_health()
 assert s.health['status']=='RESEARCH_BLOCKED' and stops==['health']

def test_full_watchdog_requires_first_execution_heartbeat(pair,tmp_path):
 from compertum.runtime.managed_owner import StorageMonitor
 e,w,c,stops=pair;monitor=StorageMonitor(w.lease,resolve_project(tmp_path))
 assert monitor.mutual.required is True
 monitor.mutual.started-=16;monitor.mutual.tick()
 assert monitor.reason=='PEER_HEARTBEAT_STALE'


def test_explicit_partial_watchdog_does_not_expect_execution(pair,tmp_path):
 from compertum.runtime.managed_owner import StorageMonitor
 e,w,c,stops=pair;monitor=StorageMonitor(w.lease,resolve_project(tmp_path),expect_execution=False)
 monitor.mutual.started-=16;monitor.mutual.tick()
 assert monitor.reason is None and not monitor.mutual.status()['verified']


def test_small_native_reserve_is_never_full_capacity_acceptance(pair):
 from compertum.persistence import open_store
 from compertum.storage import create_journal_reserve
 from compertum.runtime.execution_health import execution_durable
 e,w,c,stops=pair;store=open_store(e.lease,'execution');reserve=create_journal_reserve(e.lease,65536)
 assert reserve.receipt()['allocated_bytes']>=65536
 with pytest.raises(RuntimeRefused,match='JOURNAL_UNRESERVED'):execution_durable(store,reserve)

def test_native_sqlite_sync_downgrade_blocks_simulated_capacity_receipt(pair):
 from compertum.persistence import open_store
 from compertum.runtime.execution_health import execution_durable
 e,w,c,stops=pair;store=open_store(e.lease,'execution')
 reserve=SimpleNamespace(receipt=lambda:dict(capacity_bytes=1024**3,unused_bytes=1024**3,allocated_bytes=1024**3,sparse=False))
 store.conn.execute('PRAGMA synchronous=NORMAL')
 with pytest.raises(RuntimeRefused,match='DURABILITY_UNVERIFIED'):execution_durable(store,reserve)
