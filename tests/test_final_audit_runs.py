"""Simulated owner/ledger checks. Native Windows acceptance is separate."""
from copy import deepcopy
from datetime import datetime,timezone
import json
from types import SimpleNamespace
from uuid import uuid4
import pytest
from test_completed_final_evidence import saved
from test_environment_manifest import environment
from compertum.data.encoding import canonical
from compertum.data.errors import DataError
from compertum.environment_manifest import build_manifest
from compertum.runtime.identity_pins import runtime_identity
from compertum.review_evidence import sha
from compertum.review_frame import result_binding,pack_review
from compertum.runtime.startup_record import expected_proof
from compertum.runtime.auditor_environment import observed_from_native
from compertum import final_audit_runs as m


@pytest.fixture
def owner(saved,environment,monkeypatch):
    s=saved;storage=s.storage;db=s.db
    storage.lease=SimpleNamespace(identity=SimpleNamespace(process_instance_id=str(uuid4())))
    monkeypatch.setattr(m,'require_live_owner',lambda *a:None)
    def reserve(task,category,maximum):
        g=SimpleNamespace(grant_id=str(uuid4()),task_id=task,category=category,maximum=maximum)
        db.execute('INSERT INTO reservations VALUES(?,?,?,?,?,?,?,?)',(g.grant_id,task,category,maximum,0,'RESERVED',None,None));db.commit();return g
    class Writer:
        def __init__(self,g,path):
            self.grant=g;self.destination=storage.root/path;self.path=self.destination.with_name(self.destination.name+'.partial-'+g.grant_id);self.path.parent.mkdir(parents=True,exist_ok=True)
            assert not self.destination.exists();self.stream=self.path.open('xb');self.written=0;self.closed=False;self.manifest=None
            db.execute("UPDATE reservations SET status='OPEN',path=? WHERE id=?",(self.path.relative_to(storage.root).as_posix(),g.grant_id));db.commit()
        def write(self,raw):
            assert self.written+len(raw)<=self.grant.maximum;self.stream.write(raw);self.stream.flush();self.written+=len(raw)
            db.execute('UPDATE reservations SET written=? WHERE id=?',(self.written,self.grant.grant_id));db.commit()
        def publish(self):
            self.stream.close();raw=self.path.read_bytes();self.path.rename(self.destination)
            a=dict(artifact_id=str(uuid4()),task_id=self.grant.task_id,path=self.destination.relative_to(storage.root).as_posix(),size_bytes=len(raw),sha256=sha(raw))
            db.execute("UPDATE reservations SET status='PUBLISHED',path=?,written=?,manifest=? WHERE id=?",(a['path'],len(raw),canonical(a).decode(),self.grant.grant_id));db.commit();self.closed=True;self.manifest=a;return a
        def close(self):
            if not self.closed:self.stream.close();self.closed=True;db.execute("UPDATE reservations SET status='ABANDONED' WHERE id=?",(self.grant.grant_id,));db.commit()
    storage.reserve_bytes=reserve;storage.open_artifact=lambda g,p:Writer(g,p)
    runs=m.FinalAuditRuns(storage);task=str(uuid4());v=environment('wheel');manifest=build_manifest(v).content
    monkeypatch.setattr(m,'runtime_identity',lambda:deepcopy(v['runtime']))
    from compertum import foundation
    from compertum.domain import TaskSpec
    original_spec=foundation.fixture_spec
    def fixture_spec(root,task):
        p=original_spec(root,task).to_payload();p.update(code_sha256=v['runtime']['package_sha256'],lock_sha256=v['runtime']['lock_sha256']);return TaskSpec(p,project_root=root)
    monkeypatch.setattr(foundation,'fixture_spec',fixture_spec)
    a=runs.publish_manifest(task,manifest);state=runs.register(task,s.sid,a['artifact_id'])
    result=SimpleNamespace(saved=s,runs=runs,storage=storage,db=db,task=task,manifest=manifest,manifest_artifact=a,state=state,writers=[])
    yield result
    for w in result.writers:w.close()


def prepare(o):
    p,t,w=o.runs.prepare(o.task,now=datetime.now(timezone.utc));o.writers.append(w);return p,t.to_payload(),w


def native(o,payload):
    return dict(schema='native-template-final-auditor-v1',process=dict(pid=321,creation_filetime=654,operator_sid='S-1-5-21-1'),task_id=o.task,role='experiment_auditor',entrypoint='compertum.runtime.audit_worker',code_sha256=payload['code_sha256'],lock_sha256=payload['lock_sha256'],task_sha256=sha(canonical(payload)),startup=dict(image_sha256='0'*64,volume_serial=1,file_id='1'*32,plan_sha256='2'*64),auditor_environment=o.state['auditor_environment'])


def bound(o):
    p,t,w=prepare(o);n=native(o,t);o.runs.verify_launch(p,t,p['reservation_id']);o.runs.bind_native(p,n);o.runs.verify_launch(p,t,p['reservation_id'],execution_identity=n);return p,t,w,n


def receipt(n,code=0,timed_out=False):
    return dict(pid=n['process']['pid'],exit_code=code,timed_out=timed_out,active_processes=0,assigned_before_resume=True,affinity=15,memory_limit=4*1024**3,peak_job_memory=32000000,observed_child_pids=[],observed_children_exited=True,execution_identity=n)


def report(o,p,n):
    request=json.loads((o.storage.root/p['request_artifact']['path']).read_bytes());old=request['original']
    inner=dict(schema='generated-final-independent-audit-v1',status='VERIFIED_PASS',evaluation_id=old['evaluation_id'],plan_sha256=old['plan_sha256'],payload_sha256=old['payload_sha256'],financial_accepted=False,full_M3=False)
    body=canonical(dict(schema='consumed-final-independent-report-v1',original_evidence_sha256=o.state['original_sha256'],audit_sha256=sha(canonical(inner)),audit=inner,financial_accepted=False,full_M3=False))
    b=result_binding('final_audit',o.task,old['evaluation_id'],p['request_artifact']['sha256'],o.state['auditor_runtime'],n['process']['pid'],startup=expected_proof(n),auditor_environment=observed_from_native(n));return pack_review(body,b)


def test_registration_is_exact_replay_and_status_never_reads_heavy_inputs(owner,monkeypatch):
    o=owner;assert o.runs.register(o.task,o.saved.sid,o.manifest_artifact['artifact_id'])==o.state
    monkeypatch.setattr(m,'completed_final',lambda *a:pytest.fail('heavy status read'))
    assert o.runs.records()[0]['state']=='READY' and o.runs.status(o.task)==o.state


def test_another_task_or_manifest_cannot_reset_attempt_budget(owner):
    o=owner;task=str(uuid4());a=o.runs.publish_manifest(task,o.manifest)
    with pytest.raises(DataError):o.runs.register(task,o.saved.sid,a['artifact_id'])


def test_prepared_task_is_durable_before_native_binding(owner):
    o=owner;p,t,w=prepare(o);s=o.runs.status(o.task)
    assert s['state']=='PREPARED' and s['attempts'][0]['native_execution'] is None
    assert (o.storage.root/s['attempts'][0]['task_artifact']['path']).read_bytes()==canonical(t)
    with pytest.raises(DataError):o.runs.barrier()
    n=native(o,t);o.runs.bind_native(p,n);o.runs.verify_launch(p,t,p['reservation_id'],execution_identity=n)
    with pytest.raises(DataError):o.runs.bind_native(p,n)


def test_success_requires_exit_publication_and_original_continuity(owner):
    o=owner;p,t,w,n=bound(o);out=report(o,p,n);w.write(out)
    with pytest.raises(DataError):o.runs.inspect_output(o.runs.status(o.task),out)
    o.runs.record_exit(o.task,receipt(n));o.runs.inspect_output(o.runs.status(o.task),out);a=w.publish();result=o.runs.accept(o.task,a)
    assert result['state']=='COMPLETED' and o.runs.completed(o.task)==result
    o.runs.barrier();assert result['financial_accepted'] is False
    o.saved.guard['sha256']='a'*64
    with pytest.raises(DataError):o.runs.completed(o.task)


@pytest.mark.parametrize('where',['prepared','running'])
def test_restart_without_exit_remains_blocking_never_retry(owner,where):
    o=owner
    if where=='prepared':prepare(o)
    else:bound(o)
    o.storage.lease.identity.process_instance_id=str(uuid4());again=m.FinalAuditRuns(o.storage)
    assert again.status(o.task)['state']=='EXIT_UNVERIFIED'
    with pytest.raises(DataError):again.resume(o.task)
    with pytest.raises(DataError):again.barrier()
    with pytest.raises(DataError):again.prepare(o.task,now=datetime.now(timezone.utc))


def test_uncertain_live_exit_can_be_resolved_only_by_matching_closed_receipt(owner):
    o=owner;p,t,w,n=bound(o);o.runs.uncertain(o.task,'BOOKKEEPING_FAILED')
    bad=receipt(n);bad['active_processes']=1
    with pytest.raises(DataError):o.runs.record_exit(o.task,bad)
    assert o.runs.status(o.task)['state']=='EXIT_UNVERIFIED'
    o.runs.record_exit(o.task,receipt(n,125));o.runs.interrupt(o.task,'OPERATOR_PAUSE');o.runs.barrier()
    o.runs.resume(o.task);assert o.runs.status(o.task)['state']=='READY'


@pytest.mark.parametrize('code,timeout,cause,state',[(4,False,'AUDIT_REJECTED','FAILED'),(6,False,'AUDIT_INTEGRITY_FAILURE','BLOCKED'),(5,False,'WORKER_IO_FAILURE','INTERRUPTED'),(124,True,'JOB_TIMEOUT','INTERRUPTED'),(125,False,'OPERATOR_PAUSE','INTERRUPTED')])
def test_exit_classification_and_maximum_two_attempts(owner,code,timeout,cause,state):
    o=owner;p,t,w,n=bound(o);o.runs.record_exit(o.task,receipt(n,code,timeout));r=o.runs.interrupt(o.task,cause);assert r['state']==state
    if state!='INTERRUPTED':
        with pytest.raises(DataError):o.runs.resume(o.task)
        return
    o.runs.resume(o.task);p,t,w,n=bound(o);o.runs.record_exit(o.task,receipt(n,code,timeout));assert o.runs.interrupt(o.task,cause)['state']=='FAILED'
    with pytest.raises(DataError):o.runs.resume(o.task)


@pytest.mark.parametrize('fault',['original','manifest','request','task','reservation','author'])
def test_dispatch_rechecks_exact_committed_inputs(owner,fault):
    o=owner;p,t,w=prepare(o);n=native(o,t)
    if fault=='original':o.saved.guard['sha256']='a'*64
    elif fault=='manifest':(o.storage.root/o.manifest_artifact['path']).write_bytes(b'changed')
    elif fault=='request':(o.storage.root/p['request_artifact']['path']).write_bytes(b'changed')
    elif fault=='task':t['budget']['cpu_threads']=3
    elif fault=='reservation':o.db.execute('UPDATE reservations SET maximum=1 WHERE id=?',(p['reservation_id'],))
    else:n['process']=deepcopy(o.saved.row['final_attempts'][0]['start']['attempt']['native_execution']['process'])
    if fault=='author':
        o.runs.bind_native(p,n)
        with pytest.raises(DataError):o.runs.verify_launch(p,t,p['reservation_id'],execution_identity=n)
    else:
        with pytest.raises(DataError):o.runs.verify_launch(p,t,p['reservation_id'])


@pytest.mark.parametrize('fault',['unpublished','wrong_grant','maximum','written','false_success','frame','report_pin'])
def test_output_cannot_supply_its_own_authority(owner,fault):
    o=owner;p,t,w,n=bound(o);r=receipt(n);out=report(o,p,n)
    if fault=='false_success':r['exit_code']=5
    if fault=='frame':out=out[:-1]+b'x'
    if fault=='report_pin':
        head,body=out.split(b'\n',1);v=json.loads(body);v['original_evidence_sha256']='9'*64;head=json.loads(head);b={k:v for k,v in head.items() if k not in ('schema','payload_bytes','payload_sha256')};out=pack_review(canonical(v),b)
    o.runs.record_exit(o.task,r);w.write(out);a=w.publish()
    if fault=='unpublished':o.db.execute("UPDATE reservations SET status='OPEN' WHERE id=?",(p['reservation_id'],))
    elif fault=='wrong_grant':o.db.execute('UPDATE reservations SET id=? WHERE id=?',(str(uuid4()),p['reservation_id']))
    elif fault=='maximum':o.db.execute('UPDATE reservations SET maximum=1 WHERE id=?',(p['reservation_id'],))
    elif fault=='written':o.db.execute('UPDATE reservations SET written=1 WHERE id=?',(p['reservation_id'],))
    with pytest.raises((DataError,ValueError)):o.runs.accept(o.task,a)


def test_exit_observation_allows_barrier_but_never_success_or_retry(owner,monkeypatch):
    from compertum import final_completion
    o=owner;p,t,w,n=bound(o);o.runs.uncertain(o.task,'OWNER_RESTART')
    proof=dict(schema='final-root-exit-v1',process=n['process'],status='VERIFIED_ABSENT',observed_at=datetime.now(timezone.utc).isoformat(),observed_creation_filetime=None,wait_result=None)
    monkeypatch.setattr(final_completion,'observe_exited',lambda value:deepcopy(proof))
    assert o.runs.recover_exit(o.task)['state']=='BLOCKED';o.runs.barrier()
    with pytest.raises(DataError):o.runs.resume(o.task)
    with pytest.raises(DataError):o.runs.completed(o.task)


def test_rehashed_history_cannot_change_registration(owner):
    o=owner;p,t,w,n=bound(o)
    row=o.db.execute('SELECT seq,body FROM final_audit_history WHERE task_id=? ORDER BY seq DESC LIMIT 1',(o.task,)).fetchone();v=json.loads(row[1]);v['original_sha256']='9'*64;raw=canonical(v)
    o.db.execute('UPDATE final_audit_history SET body=?,sha256=? WHERE task_id=? AND seq=?',(raw.decode(),sha(raw),o.task,row[0]));o.db.execute('UPDATE final_audit_runs SET body=? WHERE task_id=?',(raw.decode(),o.task))
    with pytest.raises(DataError):o.runs.status(o.task)

@pytest.mark.parametrize('phase',['before_accept','after_complete'])
@pytest.mark.parametrize('fault',['task_bytes','task_missing','task_unpublished'])
def test_task_publication_continuity_is_required(owner,phase,fault):
    o=owner;p,t,w,n=bound(o);o.runs.record_exit(o.task,receipt(n));w.write(report(o,p,n));a=w.publish()
    if phase=='after_complete':o.runs.accept(o.task,a)
    task=p['task_artifact'];path=o.storage.root/task['path']
    if fault=='task_bytes':path.write_bytes(b'changed')
    elif fault=='task_missing':path.unlink()
    else:o.db.execute("UPDATE reservations SET status='ABANDONED' WHERE task=? AND path=?",(o.task,task['path']))
    with pytest.raises((DataError,OSError)):
        if phase=='before_accept':o.runs.accept(o.task,a)
        else:o.runs.completed(o.task)


def test_historical_completed_auditor_does_not_require_new_current_runtime(owner,monkeypatch):
    o=owner;p,t,w,n=bound(o);o.runs.record_exit(o.task,receipt(n));w.write(report(o,p,n));a=w.publish();o.runs.accept(o.task,a)
    monkeypatch.setattr(m,'runtime_identity',lambda:{**o.state['auditor_runtime'],'package_sha256':'9'*64})
    from compertum import foundation
    monkeypatch.setattr(foundation,'fixture_spec',lambda *args:pytest.fail('historical read used current launch template'))
    assert o.runs.completed(o.task)['state']=='COMPLETED'


def test_restart_finishes_existing_published_output_without_redispatch(owner):
    o=owner;p,t,w,n=bound(o);o.runs.record_exit(o.task,receipt(n));w.write(report(o,p,n));a=w.publish()
    o.storage.lease.identity.process_instance_id=str(uuid4());again=m.FinalAuditRuns(o.storage)
    assert again.status(o.task)['state']=='RUNNING';assert again.accept(o.task,a)['state']=='COMPLETED';assert len(again.status(o.task)['attempts'])==1
