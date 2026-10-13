"""Readonly lineage readers use committed delta rows, not synthetic full snapshots."""
import json,sqlite3,time
from dataclasses import asdict
from copy import deepcopy
from uuid import uuid4
import pytest
from compertum.data.encoding import canonical
from compertum.data.errors import DataError
from compertum.review_evidence import sha
from compertum.shortlist_evidence import source_state
from compertum.campaign_contract import UNITS
from compertum.simulation.campaign_runs import history_delta


def source_fixture():
    db=sqlite3.connect(':memory:');db.executescript('CREATE TABLE baseline_runs(run_id,body); CREATE TABLE baseline_history(run_id,seq,body,sha256); CREATE TABLE baseline_controls(run_id,request_id,action,receipt);')
    run=str(uuid4());artifact=dict(artifact_id=str(uuid4()),task_id=run,path=f'artifacts/runs/{run}/baseline/inputs.json',sha256='a'*64,size_bytes=2)
    state=dict(run_id=run,state='COMPLETED',input_kind='synthetic-campaign',input_artifact=artifact,request_sha256=artifact['sha256'],protocol_seal={'fixture':'seal'},clean_environment={'fixture':'lane'},attempts=[],outcomes={u.key:dict(unit=i,status='SKIPPED' if u.fit_unit is not None else 'FAILED',identity=asdict(u),reason='DEPENDENCY_FAILED' if u.fit_unit is not None else 'WORKER_FAILED') for i,u in enumerate(UNITS)})
    before=deepcopy(state);before.update(state='READY',outcomes={})
    rows=[]
    for i,(old,new) in enumerate(((None,before),(before,state)),1):
        raw=history_delta(old,new).decode();pin=sha(canonical(new));db.execute('INSERT INTO baseline_history VALUES(?,?,?,?)',(run,i,raw,pin));rows.append(dict(seq=i,body=raw,sha256=pin))
    db.execute('INSERT INTO baseline_runs VALUES(?,?)',(run,canonical(state).decode()))
    lane={k:state[k] for k in ('run_id','input_artifact','protocol_seal','clean_environment')}
    lane.update(source_state_sha256=sha(canonical(state)),source_history_sha256=sha(canonical(rows)),source_controls_sha256=sha(canonical([])))
    return db,lane,state,rows


def test_actual_delta_history_semantics_are_accepted():
    db,lane,state,rows=source_fixture()
    assert all(sha(r['body'].encode())!=r['sha256'] for r in rows)
    assert source_state(db,lane,time.monotonic()+4)==state


@pytest.mark.parametrize('fault',['row_pin','previous','body','missing','state','control','oversize','deadline'])
def test_live_source_changes_cannot_reuse_old_aggregate(fault):
    db,lane,state,rows=source_fixture();deadline=time.monotonic()+4
    if fault=='row_pin':db.execute("UPDATE baseline_history SET sha256=? WHERE seq=1",('f'*64,))
    elif fault=='previous':
        v=json.loads(rows[1]['body']);v['previous_sha256']='f'*64;db.execute('UPDATE baseline_history SET body=? WHERE seq=2',(canonical(v).decode(),))
    elif fault=='body':db.execute("UPDATE baseline_history SET body='{}' WHERE seq=1")
    elif fault=='missing':db.execute('DELETE FROM baseline_history WHERE seq=1')
    elif fault=='state':db.execute("UPDATE baseline_runs SET body='{}'")
    elif fault=='control':db.execute('INSERT INTO baseline_controls VALUES(?,?,?,?)',(state['run_id'],str(uuid4()),'pause','{}'))
    elif fault=='oversize':db.execute('UPDATE baseline_runs SET body=?',('x'*(512*1024+1),))
    else:deadline=time.monotonic()-1
    with pytest.raises(DataError):source_state(db,lane,deadline)


def test_pair_request_growth_is_read_with_a_hard_cap(tmp_path,monkeypatch):
    from types import SimpleNamespace
    from pathlib import Path
    from compertum import shortlist_evidence as module
    run=str(uuid4());task=str(uuid4());relative=f'artifacts/runs/{task}/review/input/request.review';path=tmp_path/relative;path.parent.mkdir(parents=True);path.write_bytes(b'{}')
    artifact=dict(task_id=task,artifact_id=str(uuid4()),path=relative,sha256=sha(b'{}'),size_bytes=2)
    s=dict(task_id=task,source_run_id=run,kind='pair_compare',request_sha256=artifact['sha256'],request_artifact=artifact)
    monkeypatch.setattr(module,'_published',lambda *a,**k:path.write_bytes(b'x'*(129*1024)))
    original=Path.open;reads=[]
    class Bounded:
        def __init__(self,f):self.f=f
        def __enter__(self):return self
        def __exit__(self,*args):self.f.close()
        def read(self,n=-1):
            assert 0<n<=128*1024+1;reads.append(n);return self.f.read(n)
    def opened(self,*a,**k):return Bounded(original(self,*a,**k)) if self.name==path.name and a==('rb',) else original(self,*a,**k)
    monkeypatch.setattr(Path,'open',opened)
    with pytest.raises(DataError):module.request_header(SimpleNamespace(root=tmp_path),s)
    assert reads==[128*1024+1]


def unit_fixture(tmp_path):
    from types import SimpleNamespace
    from test_clean_aggregate_binding import evidence
    source,final=evidence();artifact=final['artifact'];path=tmp_path/artifact['path'];path.parent.mkdir(parents=True);raw=b'unit-audit-fixture';path.write_bytes(raw);artifact.update(sha256=sha(raw),size_bytes=len(raw))
    registered=deepcopy(final);registered.update(state='READY',attempts=[],artifact=None,audit_sha256=None,last_transition='REGISTERED')
    running=deepcopy(registered);attempt=deepcopy(final['attempts'][0]);attempt.update(status='RUNNING');attempt.pop('job_receipt');running.update(state='RUNNING',attempts=[attempt],last_transition='ATTEMPT_STARTED')
    exited=deepcopy(running);exited['attempts'][0]['job_receipt']=deepcopy(final['attempts'][0]['job_receipt']);exited['last_transition']='EXIT_RECORDED'
    records=[];previous=None
    for n,state in enumerate((registered,running,exited,final),1):
        body=canonical(state).decode();pin=sha(body.encode());records.append(dict(seq=n,body=body,sha256=pin,previous_sha256=previous));previous=pin
    db=sqlite3.connect(':memory:');db.executescript('CREATE TABLE audit_runs(task_id,body); CREATE TABLE audit_history(task_id,seq,body,sha256,previous_sha256); CREATE TABLE reservations(id,task,path,status,manifest);')
    task=final['task_id'];db.execute('INSERT INTO audit_runs VALUES(?,?)',(task,canonical(final).decode()))
    for r in records:db.execute('INSERT INTO audit_history VALUES(?,?,?,?,?)',(task,r['seq'],r['body'],r['sha256'],r['previous_sha256']))
    db.execute('INSERT INTO reservations VALUES(?,?,?,?,?)',(final['attempts'][0]['reservation_id'],task,artifact['path'],'PUBLISHED',canonical(artifact).decode()))
    pin=dict(unit=0,task_id=task,artifact_sha256=artifact['sha256'],audit_sha256=final['audit_sha256'],attempts=1,history_sha256=sha(canonical(records)))
    return SimpleNamespace(root=tmp_path,store=SimpleNamespace(conn=db)),source,dict(unit_audits=[pin],required_unit_audits=1),final


def test_successful_unit_audit_remains_a_required_live_dependency(tmp_path):
    from compertum.shortlist_evidence import _unit_dependencies
    storage,source,report,final=unit_fixture(tmp_path)
    assert _unit_dependencies(storage,source,report,time.monotonic()+4)==[final['attempts'][0]['native_execution']]


@pytest.mark.parametrize('fault',['missing_history','changed_history','changed_state','missing_output','changed_output','reservation','extra_audit','report_pin','oversize'])
def test_unit_audit_loss_or_change_blocks_the_frozen_shortlist(tmp_path,fault):
    from compertum.shortlist_evidence import _unit_dependencies
    storage,source,report,final=unit_fixture(tmp_path);db=storage.store.conn
    if fault=='missing_history':db.execute('DELETE FROM audit_history WHERE seq=2')
    elif fault=='changed_history':db.execute("UPDATE audit_history SET body='{}' WHERE seq=2")
    elif fault=='changed_state':db.execute("UPDATE audit_runs SET body='{}'")
    elif fault=='missing_output':(tmp_path/final['artifact']['path']).rename(tmp_path/'preserved-audit')
    elif fault=='changed_output':(tmp_path/final['artifact']['path']).write_bytes(b'changed')
    elif fault=='reservation':db.execute("UPDATE reservations SET status='OPEN'")
    elif fault=='extra_audit':db.execute('INSERT INTO audit_runs VALUES(?,?)',(str(uuid4()),canonical(final).decode()))
    elif fault=='report_pin':report['unit_audits'][0]['audit_sha256']='f'*64
    else:db.execute('UPDATE audit_runs SET body=?',('x'*(32*1024+1),))
    with pytest.raises((DataError,OSError)):_unit_dependencies(storage,source,report,time.monotonic()+4)
