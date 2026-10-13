"""Native owners and atomic fake resume; reserve capacity simulated."""
import json
from uuid import uuid4
import pytest
from test_execution_authority import authority,packet,advance,session
from test_execution_health import pair
from test_saved_plan_controls import ready,prepare,phase,inspect
from test_operation_progression import started,step,broker
from compertum.runtime.errors import RuntimeRefused


def test_healthy_resume_is_disarmed_inert_and_does_not_refresh_supervision(ready):
 a=ready[0];saved=started(a);epoch=a.plan_epoch();before=a._read_state();p=packet('resume')
 result=a.handle(p);assert result['admission']=='DISARMED' and not result['armed'] and not result['effects_enabled'] and not result['financial_accepted']
 assert a.status()['halted'] is False and a.store.get_state('admission')=='DISARMED' and a.store.get_state('approved_plan') is None
 assert a._read_state()['ack_mono']==before['ack_mono'] and a.plan_epoch()==epoch+1
 assert a.handle(p)==result and a.plan_epoch()==epoch+1 and broker(a).snapshot()['calls']==[]
 assert inspect(a,saved)['plan_id']==saved['plan_id']
 with pytest.raises(RuntimeRefused,match='PLAN_CONTEXT_CHANGED'):step(a,saved)


@pytest.mark.parametrize('event',['halt','expiry','session','restart'])
def test_old_resume_receipt_cannot_restore_authority(ready,event):
 from compertum.execution_authority import ExecutionAuthority
 a=ready[0];prepare(a);p=packet('resume');result=a.handle(p)
 if event=='halt':a.handle(packet('halt'))
 elif event=='expiry':advance(*ready,301)
 elif event=='session':session(a)
 else:
  with a.store.conn:
   state=a._read_state();state['owner_instance']=str(uuid4());a.store.conn.execute("UPDATE state SET value=? WHERE key='fake_operator_state'",(json.dumps(state),))
  a=ExecutionAuthority(a.store,a.reserve,a.health)
 before=a._read_state();epoch=a.plan_epoch()
 assert a.handle(p)==result and a._read_state()==before and a.plan_epoch()==epoch
 assert a.status()['halted'] and not a.status()['armed'] and a.store.get_state('admission')=='HALTED'


@pytest.mark.parametrize('fault',['cash','shares','foreign_order','opening','unknown','health','supervision','reserve'])
def test_unresolved_cause_refuses_resume_without_effect(ready,monkeypatch,fault):
 import compertum.execution_authority as module
 a=ready[0];saved=started(a);b=broker(a)
 if fault=='cash':
  with b.db:b.db.execute("UPDATE account SET cash='5500.02'")
 elif fault=='shares':
  with b.db:b.db.execute("UPDATE positions SET quantity=46")
 elif fault=='foreign_order':
  from test_deterministic_broker import request
  b.submit(request())
 elif fault=='opening':(a.store.root/'state/fake-economic-opening.json').rename(a.store.root/'retained-opening.json')
 elif fault=='unknown':
  result=step(a,saved);a.plan_owner.observations.journal.uncertain('fake-account',result['intent_id'],reason='TIMEOUT',now=a.require_supervised()['market_at'])
 elif fault=='health':a.health.halt('PEER_UNAVAILABLE')
 elif fault=='supervision':advance(*ready,301)
 else:
  def fail(*args):raise RuntimeRefused('JOURNAL_UNRESERVED')
  monkeypatch.setattr(module,'execution_durable',fail)
 before=b.snapshot()['calls'];request=packet('resume')
 with pytest.raises(RuntimeRefused):a.handle(request)
 assert a.status()['halted'] and not a.status()['armed'] and b.snapshot()['calls']==before
 assert a.store.conn.execute('SELECT count(*) FROM fake_operator_requests WHERE request_id=?',(request['request_id'],)).fetchone()==(0,)


@pytest.mark.parametrize('fault',['stale','session'])
def test_changed_context_after_observation_refuses_resume(ready,monkeypatch,fault):
 a=ready[0];prepare(a);owner=a.plan_owner.observations;read=owner.read
 def changed():
  value=read()
  if fault=='stale':advance(*ready,31)
  else:session(a);a.handle(packet('supervise'))
  return value
 monkeypatch.setattr(owner,'read',changed)
 with pytest.raises(RuntimeRefused,match='RECONCILIATION_STALE|HEARTBEAT_STALE|SESSION_INPUTS_CHANGED'):a.handle(packet('resume'))
 assert a.status()['halted'] and broker(a).snapshot()['calls']==[]


@pytest.mark.parametrize('target',['state','receipt'])
def test_ignored_resume_write_rolls_back_whole_transition(ready,target):
 a=ready[0];prepare(a);before=a._read_state();epoch=a.plan_epoch();request=packet('resume')
 with a.store.conn:
  if target=='state':a.store.conn.execute("CREATE TRIGGER ignore_resume BEFORE UPDATE ON state WHEN NEW.key='fake_operator_state' BEGIN SELECT RAISE(IGNORE); END")
  else:a.store.conn.execute('CREATE TRIGGER ignore_resume BEFORE INSERT ON fake_operator_requests BEGIN SELECT RAISE(IGNORE); END')
 with pytest.raises(RuntimeRefused,match='OPERATOR_WRITE_UNVERIFIED'):a.handle(request)
 assert a._read_state()==before and a.plan_epoch()==epoch and a.store.get_state('admission')=='HALTED'
 assert a.store.conn.execute('SELECT count(*) FROM fake_operator_requests WHERE request_id=?',(request['request_id'],)).fetchone()==(0,)


@pytest.mark.parametrize('damage',['epoch','table','version'])
def test_partial_saved_plan_schema_cannot_resume(ready,damage):
 a=ready[0];saved=prepare(a);phase(a,'approve_plan',saved)
 with a.store.conn:
  if damage=='epoch':a.store.conn.execute("DELETE FROM state WHERE key='fake_plan_epoch'")
  elif damage=='table':a.store.conn.execute('DROP TABLE fake_saved_plan_phases')
  else:a.store.conn.execute("DELETE FROM state WHERE key='fake_saved_plan_version'")
 request=packet('resume')
 with pytest.raises(RuntimeRefused,match='PLAN_STATE_CORRUPT'):a.handle(request)
 assert a.store.get_state('admission')=='HALTED' and a.status()['halted']
 assert a.store.conn.execute('SELECT count(*) FROM fake_operator_requests WHERE request_id=?',(request['request_id'],)).fetchone()==(0,)


def test_no_prior_plan_can_resume_without_creating_plan_history(ready):
 a=ready[0]
 assert a.store.conn.execute("SELECT 1 FROM sqlite_master WHERE name='fake_saved_plans'").fetchone() is None
 assert a.handle(packet('resume'))['admission']=='DISARMED'
 assert a.store.conn.execute("SELECT 1 FROM sqlite_master WHERE name='fake_saved_plans'").fetchone() is None
 assert a.store.get_state('fake_plan_epoch') is None


@pytest.mark.parametrize('boundary',['supervision','close'])
def test_expiry_during_resume_writes_rolls_back_admission_and_receipt(ready,monkeypatch,boundary):
 from datetime import timedelta
 from test_execution_authority import profile
 from compertum.execution_contracts import instant
 a,e,w,c=ready;prepare(a)
 if boundary=='supervision':advance(*ready,290)
 else:
  p=profile();p['fixture_at']=(instant(p['calendar']['session_close_at'])-timedelta(seconds=1)).isoformat()
  a.handle(packet('open_session',session_id=str(uuid4()),profile=p));a.handle(packet('supervise'))
 before=a._read_state();epoch=a.plan_epoch();save=a.plan_owner._save_request
 def late(*args,**kwargs):
  save(*args,**kwargs);seconds=11 if boundary=='supervision' else 2;c.mono+=seconds;c.utc+=seconds
 monkeypatch.setattr(a.plan_owner,'_save_request',late)
 request=packet('resume')
 with pytest.raises(RuntimeRefused,match='SUPERVISION_EXPIRED|REGULAR_SESSION_REQUIRED'):a.handle(request)
 assert a._read_state()==before and a.plan_epoch()==epoch and a.store.get_state('admission')=='HALTED'
 assert a.store.conn.execute('SELECT count(*) FROM fake_operator_requests WHERE request_id=?',(request['request_id'],)).fetchone()==(0,)
