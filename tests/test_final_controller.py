"""Controller orchestration; worker receipts are simulated, not native acceptance."""
import json
from types import SimpleNamespace
import pytest
from test_final_dispatch import dispatch,owned,pair_inputs,environment,native
from test_final_completion import start
from test_final_recovery import observation
from compertum.runtime.errors import RuntimeRefused
from compertum.final_completion import record_exit,propose_close
from compertum.evaluation_seals import verify_seal_journal


def controller(dispatch):
 from compertum.final_controller import FinalController
 runs,seals,*_=dispatch
 coordinator=SimpleNamespace(status=lambda:dict(research_state='RUNNING'),require_health=lambda:None)
 return FinalController(coordinator,runs.storage,seals)


def fake_job(receipt,*,active=False):
 state=dict(active=active,closed=False)
 def terminate(*args):state['active']=False;return True
 def close():state['closed']=True;state['active']=False
 api=SimpleNamespace(active=lambda job:int(state['active']),TerminateJobObject=terminate,checked=lambda result,name:result)
 return SimpleNamespace(api=api,job=SimpleNamespace(get=lambda:1),pid=receipt['pid'],wait=lambda:receipt,close=close,state=state)


def test_prepared_without_start_is_invalidated_and_cannot_redispatch(dispatch):
 c=controller(dispatch);sid=dispatch[3]['seal_id']
 assert c.recover(sid)['status']=='INVALIDATED'
 assert c.recover(sid)['status']=='INVALIDATED'
 with pytest.raises(RuntimeRefused):c.step(sid)


@pytest.mark.parametrize('saved',['unknown','exit','closure'])
def test_restart_uses_retained_evidence_and_never_launches(dispatch,monkeypatch,saved):
 import compertum.final_completion as fc
 runs,seals,p,d,task,out=dispatch;n,r=start(dispatch,monkeypatch)
 monkeypatch.setattr(fc,'observe_exited',observation)
 if saved in ('exit','closure'):record_exit(runs,d,r)
 if saved=='closure':propose_close(runs,d,'STOPPED')
 c=controller(dispatch);before=len(verify_seal_journal(seals.project)['seals'][d['seal_id']]['final_attempts'])
 done=c.recover(d['seal_id'])
 assert done['status']=={'unknown':'EXHAUSTED','exit':'REJECTED','closure':'STOPPED'}[saved]
 assert c.recover(d['seal_id'])==done and c.active is None
 assert len(verify_seal_journal(seals.project)['seals'][d['seal_id']]['final_attempts'])==before


@pytest.mark.parametrize('terminal,exit_code,status',[(False,125,'BATCH_INTERRUPTED'),(True,125,'STOPPED'),(False,4,'REJECTED')])
def test_pause_waits_for_exit_then_closes_owner(dispatch,monkeypatch,terminal,exit_code,status):
 import compertum.final_controller as module
 runs,seals,p,d,task,out=dispatch;n,r=start(dispatch,monkeypatch);r['exit_code']=exit_code
 c=controller(dispatch);job=fake_job(r,active=True);c.active=(d,out,job)
 monkeypatch.setattr(module,'adopt_fixture_bytes',lambda writer,job:writer.written)
 with pytest.raises(RuntimeRefused):c.recover(d['seal_id'])
 done=c.pause(terminal=terminal)
 assert done['status']==status and c.active is None and job.state['closed']
 assert c.status(d['seal_id'])==done


def test_finished_job_publishes_only_a_bound_frame(dispatch,monkeypatch):
 import compertum.final_controller as module
 from compertum.review_frame import pack_review,result_binding
 from compertum.runtime.startup_record import expected_proof
 from compertum.runtime.campaign_environment import observed_from_native
 runs,seals,p,d,task,out=dispatch;n,r=start(dispatch,monkeypatch)
 body=b'opaque controller fixture; not financial evidence'
 out.write(pack_review(body,result_binding('final',task.to_payload()['task_id'],p['source']['run_id'],d['request_artifact']['sha256'],p['runtime'],n['process']['pid'],startup=expected_proof(n),environment=observed_from_native(n))))
 c=controller(dispatch);job=fake_job(r);c.active=(d,out,job)
 monkeypatch.setattr(module,'adopt_fixture_bytes',lambda writer,job:writer.written)
 done=c.tick()
 assert done['status']=='COMPLETED' and done['result']['publication']['payload_bytes']==len(body)
 assert c.active is None and job.state['closed']
 assert c.tick() is None


def test_bad_frame_is_rejected_without_publishing(dispatch,monkeypatch):
 import compertum.final_controller as module
 runs,seals,p,d,task,out=dispatch;n,r=start(dispatch,monkeypatch);out.write(b'bad frame')
 c=controller(dispatch);job=fake_job(r);c.active=(d,out,job)
 monkeypatch.setattr(module,'adopt_fixture_bytes',lambda writer,job:writer.written)
 assert c.tick()['status']=='REJECTED'
 assert runs.store.conn.execute('SELECT status FROM reservations WHERE id=?',(d['attempt']['reservation_id'],)).fetchone()==('ABANDONED',)


def test_owner_outage_preserves_exact_closure_for_recovery(dispatch,monkeypatch):
 import compertum.final_controller as module
 runs,seals,p,d,task,out=dispatch;n,r=start(dispatch,monkeypatch);r['exit_code']=4
 c=controller(dispatch);job=fake_job(r);c.active=(d,out,job)
 monkeypatch.setattr(module,'adopt_fixture_bytes',lambda writer,job:writer.written)
 real=module.close_through_owner
 def unavailable(*args,**kwargs):raise RuntimeRefused('OWNER_UNAVAILABLE')
 monkeypatch.setattr(module,'close_through_owner',unavailable)
 assert c.tick() is None and c.active is None and c.errors[d['seal_id']]=='OWNER_UNAVAILABLE'
 assert runs.store.conn.execute('SELECT count(*) FROM final_closures').fetchone()==(1,)
 monkeypatch.setattr(module,'close_through_owner',real)
 assert c.recover(d['seal_id'])['status']=='REJECTED' and not c.errors


def test_preflight_refusal_does_not_prepare_or_consume_attempt(dispatch,monkeypatch):
 import compertum.final_controller as module
 c=controller(dispatch);sid=dispatch[3]['seal_id'];called=[]
 def refused(*args):raise RuntimeRefused('AVAILABLE_RAM_FLOOR')
 monkeypatch.setattr(module,'preflight_campaign',refused)
 monkeypatch.setattr(module,'job_slot_busy',lambda lease:False)
 monkeypatch.setattr(c.runs,'prepare',lambda *args,**kw:called.append('prepare'))
 before=verify_seal_journal(dispatch[1].project)
 with pytest.raises(RuntimeRefused,match='AVAILABLE_RAM_FLOOR'):c.step(sid)
 assert not called and verify_seal_journal(dispatch[1].project)==before


def test_orphan_preparation_is_invalidated_without_another_publication(dispatch):
 runs,seals,p,d,task,out=dispatch
 with runs.store.conn:runs.store.conn.execute('DELETE FROM final_dispatches')
 c=controller(dispatch)
 before=runs.store.conn.execute('SELECT count(*) FROM reservations WHERE status=\'PUBLISHED\'').fetchone()
 assert c.recover(d['seal_id'])['status']=='INVALIDATED'
 assert runs.store.conn.execute('SELECT count(*) FROM reservations WHERE status=\'PUBLISHED\'').fetchone()==before


def test_terminal_close_replay_does_not_reobserve_unrelated_reused_pid(dispatch,monkeypatch):
 import compertum.final_completion as module
 from compertum.final_completion import close_through_owner
 runs,seals,p,d,task,out=dispatch;n,r=start(dispatch,monkeypatch);record_exit(runs,d,r)
 pin=propose_close(runs,d,'STOPPED');done=close_through_owner(runs,d,pin,evaluation=seals)
 def unavailable(native):raise RuntimeRefused('FINAL_PROCESS_EXIT_UNVERIFIED')
 monkeypatch.setattr(module,'require_exited',unavailable)
 assert close_through_owner(runs,d,pin,evaluation=seals)==done


def test_supervisor_routes_final_and_halts_it_with_other_research():
 from compertum.runtime.supervisor import Supervisor,ACTIONS
 from uuid import uuid4
 s=object.__new__(Supervisor);calls=[];sid=str(uuid4())
 s.fixtures=SimpleNamespace(active=None,pause=lambda reason:calls.append(('fixture',reason)))
 from compertum.research import ResearchController
 s.research=object.__new__(ResearchController);s.research.active=None;s.research.pending=None;s.research.last_operation_error=None
 s.research.pause=lambda reason:calls.append(('research',reason))
 s.final=SimpleNamespace(active=None,control=lambda seal,operation:calls.append((seal,operation)) or {'status':'BATCH_INTERRUPTED'},pause=lambda reason,terminal=False:calls.append(('final',reason,terminal)))
 assert 'final' in ACTIONS
 assert s._dispatch(SimpleNamespace(request_id=str(uuid4())),'final',dict(seal_id=sid,operation='pause'))=={'status':'BATCH_INTERRUPTED'}
 s.halt('checkpoint');assert ('final','checkpoint',False) in calls
 s.halt('stop_research');assert ('final','stop_research',True) in calls
 s.research.active=('other',)
 with pytest.raises(RuntimeRefused,match='JOB_SLOT_BUSY'):s._dispatch(None,'final',dict(seal_id=sid,operation='step'))
 s.research.active=None;s.research.pending=SimpleNamespace(run_id='pending')
 with pytest.raises(RuntimeRefused,match='JOB_SLOT_BUSY'):s._dispatch(None,'final',dict(seal_id=sid,operation='resume'))
 s.research.pending=None;s.research.last_operation_error={'recovery_required':True}
 with pytest.raises(RuntimeRefused,match='JOB_SLOT_BUSY'):s._dispatch(None,'final',dict(seal_id=sid,operation='step'))
 s.final=None
 with pytest.raises(RuntimeRefused,match='FINAL_UNAVAILABLE'):s._dispatch(None,'final',dict(seal_id=sid,operation='status'))


def test_failed_cleanup_detaches_closed_handles_and_retains_recovery_error(dispatch,monkeypatch):
 import compertum.final_controller as module
 runs,seals,p,d,task,out=dispatch;n,r=start(dispatch,monkeypatch);r['exit_code']=4
 c=controller(dispatch);job=fake_job(r);c.active=(d,out,job);cleaned=[];original=out.close
 monkeypatch.setattr(module,'adopt_fixture_bytes',lambda writer,job:writer.written)
 def cleanup():cleaned.append('writer');original()
 monkeypatch.setattr(out,'close',cleanup)
 def closed_then_failed():job.state['closed']=True;raise RuntimeRefused('JOB_EXIT_UNVERIFIED')
 job.close=closed_then_failed
 assert c.tick() is None
 assert cleaned==['writer'] and c.active is None and c.errors[d['seal_id']]=='JOB_EXIT_UNVERIFIED'
 def closed_handle(job):raise RuntimeRefused('HANDLE_CLOSED')
 job.api.active=closed_handle
 assert c.tick() is None


def test_stale_health_cannot_publish_valid_final_frame(dispatch,monkeypatch):
 import compertum.final_controller as module
 from compertum.review_frame import pack_review,result_binding
 from compertum.runtime.startup_record import expected_proof
 from compertum.runtime.campaign_environment import observed_from_native
 runs,seals,p,d,task,out=dispatch;n,r=start(dispatch,monkeypatch)
 out.write(pack_review(b'valid framing, stale health',result_binding('final',task.to_payload()['task_id'],p['source']['run_id'],d['request_artifact']['sha256'],p['runtime'],n['process']['pid'],startup=expected_proof(n),environment=observed_from_native(n))))
 c=controller(dispatch);c.active=(d,out,fake_job(r))
 def unhealthy():raise RuntimeRefused('HEALTH_UNVERIFIED')
 c.coordinator.require_health=unhealthy
 monkeypatch.setattr(module,'adopt_fixture_bytes',lambda writer,job:writer.written)
 assert c.tick()['status']=='REJECTED'
 assert runs.store.conn.execute('SELECT status FROM reservations WHERE id=?',(d['attempt']['reservation_id'],)).fetchone()==('ABANDONED',)


def test_process_observation_cannot_overrun_owner_close_deadline(dispatch,monkeypatch):
 import compertum.final_completion as module
 from compertum.final_completion import close_through_owner
 runs,seals,p,d,task,out=dispatch;n,r=start(dispatch,monkeypatch);record_exit(runs,d,r);pin=propose_close(runs,d,'STOPPED')
 clock=[100.0];monkeypatch.setattr(module,'time',SimpleNamespace(monotonic=lambda:clock[0]))
 monkeypatch.setattr(module,'require_exited',lambda native:clock.__setitem__(0,105.0))
 before=verify_seal_journal(seals.project)
 with pytest.raises((RuntimeRefused,__import__('compertum.data.errors',fromlist=['DataError']).DataError)):close_through_owner(runs,d,pin,evaluation=seals)
 assert verify_seal_journal(seals.project)==before


@pytest.mark.parametrize('failure',['none','before_start','after_start','after_launch'])
def test_launch_commits_before_resume_and_failures_require_original_recovery(dispatch,monkeypatch,failure):
 import compertum.final_controller as module
 import compertum.final_completion as completion
 runs,seals,p,d,task,out=dispatch;n=native(seals,d['seal_id'],d);c=controller(dispatch);sid=d['seal_id']
 receipt=dict(pid=n['process']['pid'],exit_code=125,timed_out=False,active_processes=0,assigned_before_resume=True,affinity=15,memory_limit=4*1024**3,peak_job_memory=1024**2,observed_child_pids=[],observed_children_exited=True,execution_identity=n)
 job=fake_job(receipt,active=True);real_recover=c.recover;real_status=c.status
 monkeypatch.setattr(c,'recover',lambda sid:dict(status='CONSUMED_WAITING_FOR_BATCH'))
 monkeypatch.setattr(c.runs,'prepare',lambda *args,**kw:(d,task,out))
 monkeypatch.setattr(module,'preflight_campaign',lambda lease:None)
 monkeypatch.setattr(module,'job_slot_busy',lambda lease:False)
 monkeypatch.setattr(module,'adopt_fixture_bytes',lambda writer,job:writer.written)
 monkeypatch.setattr(completion,'observe_exited',observation)
 monkeypatch.setattr(completion,'require_exited',lambda native:None)
 def launch(lease,actual,args,**kw):
  assert actual==task and kw['final_request']==d and args[1]=='final'
  if failure=='before_start':raise RuntimeRefused('LAUNCH_FAILED')
  kw['before_resume'](n)
  assert real_status(sid)['status']=='BATCH_RUNNING' and c.active is None
  if failure=='after_start':raise RuntimeRefused('LAUNCH_FAILED')
  if failure=='after_launch':monkeypatch.setattr(c,'status',lambda sid:(_ for _ in ()).throw(RuntimeRefused('OWNER_UNAVAILABLE')))
  return job
 monkeypatch.setattr(module,'launch_bounded',launch)
 if failure=='none':
  assert c.step(sid)['status']=='BATCH_RUNNING'
  assert c.pause()['status']=='BATCH_INTERRUPTED'
 else:
  with pytest.raises(RuntimeRefused):c.step(sid)
  assert c.active is None
  if failure=='after_launch':assert job.state['closed']
  monkeypatch.setattr(c,'status',real_status)
  assert real_recover(sid)['status']==('INVALIDATED' if failure=='before_start' else 'EXHAUSTED')
