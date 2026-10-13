"""Real readonly SQL/files/journal with explicitly simulated worker receipts.

These prove committed-evidence refusal boundaries, not native campaign execution.
"""
import json,time
from dataclasses import asdict
from types import SimpleNamespace
from uuid import uuid4
from copy import deepcopy
import pytest
from test_evaluation_seals import owned,ledger,create
from test_clean_pair import pair_inputs,environment
from test_shortlist import fixture as card_fixture
from compertum.data.encoding import canonical
from compertum.data.errors import DataError
from compertum.review_evidence import sha
from compertum.review_runs import ReviewRuns
from compertum.review_bundle import build_bundle
from compertum.review_frame import result_binding,pack_review
from compertum.shortlist_ticket import review_pin,build_ticket
from compertum.shortlist_evidence import history
from compertum.evaluation_protocol import build_protocol
from compertum.evaluation_seals import reserve_seal_append,verify_seal_journal
from compertum.development_seals import _ticket,_protocol_expected
from compertum.clean_pair import build_pair
from compertum.clean_registration import initialize,register_pair
from compertum.runtime.identity import PeerObservation
from compertum.runtime.job_identity import capture_execution_identity
from compertum.runtime.startup_record import expected_proof
from compertum.runtime.campaign_environment import observed_from_native
from compertum.runtime.errors import RuntimeRefused
from compertum.campaign_contract import UNITS
from compertum.campaign_comparison import build_index,compare_indices
from compertum.shortlist import project_scorecard
from compertum.simulation.campaign_runs import history_delta
from compertum import shortlist_freeze


def make_committed(owned,pair_inputs,monkeypatch,*,real_runtime=False):
    args,_=pair_inputs;args['project_id']=owned[0].project_id;pair=build_pair(**args);p=json.loads(pair.content)
    if real_runtime:
        # The native RPC test observes the real owner/runtime. Worker receipts
        # and environment expectations remain explicitly simulated fixture data.
        from compertum.runtime.identity_pins import runtime_identity
        from compertum.clean_pair import PairRecord
        p['runtime']=json.loads(canonical(runtime_identity()));raw=canonical(p);pair=PairRecord(raw,sha(raw))
    monkeypatch.setattr('compertum.evaluation_seals.runtime_identity',lambda:p['runtime'])
    monkeypatch.setattr('compertum.clean_registration.runtime_identity',lambda:p['runtime'])
    seals=ledger(owned);storage=seals.test_storage;reviews=ReviewRuns(storage);db=storage.store.conn
    db.executescript('CREATE TABLE baseline_runs(run_id TEXT PRIMARY KEY,body TEXT); CREATE TABLE baseline_history(run_id,seq,body,sha256); CREATE TABLE baseline_controls(run_id,request_id,action,receipt); CREATE TABLE sealed_campaigns(run_id TEXT PRIMARY KEY,seal_id TEXT UNIQUE,body TEXT,sha256 TEXT,protocol TEXT,receipt TEXT);')
    initialize(storage.store);register_pair(SimpleNamespace(store=storage.store),pair)
    card,_=card_fixture()
    for slot in card['search_history']:slot.update(state='FAILED',artifact_sha256=None,failure_reason='DEPENDENCY_FAILED' if slot['candidate_id'].startswith('ridge') else 'WORKER_FAILED')
    outcomes={u.key:dict(unit=i,identity=asdict(u),status='SKIPPED' if u.fit_unit is not None else 'FAILED',reason='DEPENDENCY_FAILED' if u.fit_unit is not None else 'WORKER_FAILED') for i,u in enumerate(UNITS)}
    # Match exactly the model registry's candidate IDs, independent of naming.
    lookup={(u.candidate_id,u.year):outcomes[u.key] for u in UNITS if u.phase=='evaluate'}
    for slot in card['search_history']:slot['failure_reason']=lookup[(slot['candidate_id'],slot['year'])]['reason']
    for row in card['candidates']:
        row.update(state='FAILED',completed_years=[],failed_folds=[dict(year=s['year'],reason=s['failure_reason']) for s in card['search_history'] if s['candidate_id']==row['candidate_id']])
    card['counts']=dict(completed=0,failed=36,pending=0);card_raw=canonical(card)
    index=build_index(dict(state='COMPLETED',outcomes=outcomes),scorecard_sha256=sha(card_raw),unit_audits=[],selection_projection=project_scorecard(card_raw,expected_sha256=sha(card_raw)))
    states={};lanes=[];protocols={};pid=700
    def publish(task,path,raw):return reviews._publish(task,path,raw)
    def finish(kind,run,seal,expected,metadata,records,payload):
        nonlocal pid
        task=str(uuid4());raw=build_bundle(kind=kind,task_id=task,source_run_id=run,identity=p['runtime'],protocol_seal=seal,metadata=canonical(metadata),records=records)
        s=dict(task_id=task,source_run_id=run,kind=kind,identity=p['runtime'],registration_sha256=sha(raw) if kind!='aggregate' else 'a'*64,preparation_artifacts=[],request_sha256=sha(raw) if kind!='aggregate' else None,request_artifact=None,state='REGISTERING',owner=reviews.owner,attempts=[],artifact=None,payload_sha256=None,payload_bytes=None,financial_accepted=False,last_transition=None,updated_at=None)
        with db:reviews._save(s,'REGISTERED')
        if kind=='aggregate':
            s['preparation_artifacts']=[r['artifact'] for r in records if r['kind']=='audit_history']
            with db:reviews._save(s,'EXPORT_PUBLISHED')
            s['request_sha256']=sha(raw)
            with db:reviews._save(s,'BUNDLE_BOUND')
        s.update(request_artifact=publish(task,f'artifacts/runs/{task}/review/input/request.review',raw),state='READY')
        with db:reviews._save(s,'INPUTS_PUBLISHED')
        s['attempts']=[dict(number=1,status='PREPARING',owner=reviews.owner,output_path=f'artifacts/runs/{task}/review/{kind}-attempt-1.review',task_artifact=None,reservation_id=None,native_execution=None,job_receipt=None,reason=None)];s['state']='PREPARING'
        with db:reviews._save(s,'ATTEMPT_PREPARED')
        artifacts=[s['request_artifact']]+[r['artifact'] for r in records];role='experiment_runner' if kind=='scorecard' else 'experiment_auditor'
        spec=dict(task_id=task,role=role,parent_task_id=run,campaign_id=run,code_sha256=p['runtime']['package_sha256'],lock_sha256=p['runtime']['lock_sha256'],input_hashes=[a['sha256'] for a in artifacts],permissions=dict(filesystem_bundle=[a['path'] for a in artifacts],output_directory=f'artifacts/runs/{task}/review'),budget=dict(wall_seconds=120,cpu_threads=4,ram_bytes=4*1024**3,output_bytes=16*1024**2,max_attempts=2))
        a=s['attempts'][-1];a['task_artifact']=publish(task,f'artifacts/runs/{task}/review/input/task-attempt-1.json',canonical(spec))
        with db:reviews._save(s,'TASK_BOUND')
        pid+=1;n=capture_execution_identity(PeerObservation(pid,123456789+pid,'S-1-5-21-1-2-3-1001','S-1-5-5-100-200'),spec,'compertum.runtime.campaign_worker' if role=='experiment_runner' else 'compertum.runtime.audit_worker',startup=dict(image_sha256='e'*64,volume_serial=123,file_id='f'*32,plan_sha256='1'*64),clean_environment=expected)
        if callable(payload):payload=payload(task,s['request_sha256'])
        frame=pack_review(payload,result_binding(kind,task,run,s['request_sha256'],p['runtime'],pid,startup=expected_proof(n),environment=observed_from_native(n)))
        artifact=publish(task,a['output_path'],frame);reservation=db.execute('SELECT id FROM reservations WHERE task=? AND path=?',(task,artifact['path'])).fetchone()[0]
        a.update(status='RUNNING',native_execution=n,reservation_id=reservation);s['state']='RUNNING'
        with db:reviews._save(s,'NATIVE_EXECUTION_BOUND')
        a['job_receipt']=dict(pid=pid,exit_code=0,timed_out=False,active_processes=0,assigned_before_resume=True,affinity=15,memory_limit=4*1024**3,peak_job_memory=1024**2,observed_child_pids=[],observed_children_exited=True,execution_identity=n)
        with db:reviews._save(s,'EXIT_RECORDED')
        a['status']='COMPLETED';s.update(state='COMPLETED',artifact=artifact,payload_sha256=sha(payload),payload_bytes=len(payload))
        with db:reviews._save(s,'COMPLETED')
        return s,spec
    for lane in ('source','wheel'):
        run=p[lane]['run_id'];sid=p[lane]['seal_id'];primary=b'{}'
        protocol=build_protocol(development_run_id=run,development_sha256=sha(primary),data_manifest_sha256=p['data_manifest_sha256'],holdout_manifest_sha256=p['holdout_manifest_sha256'],runtime=p['runtime'],clean_pair=dict(record=p,sha256=pair.sha256,lane=lane));pv=json.loads(protocol.content);body=canonical(_ticket(owned[0].project_id,run,sid,pv));protocols[lane]=protocol.sha256
        with db:db.execute('INSERT INTO sealed_campaigns VALUES(?,?,?,?,?,NULL)',(run,sid,body.decode(),sha(body),protocol.content.decode()))
        create(seals,sid,protocol.content,protocol.sha256);reserve_seal_append(storage);receipt=seals.admit(sid,sha(body))
        with db:db.execute('UPDATE sealed_campaigns SET receipt=? WHERE run_id=?',(canonical(receipt).decode(),run))
        seal=dict(seal_id=sid,protocol_sha256=protocol.sha256,ticket_sha256=sha(body),admission_event_sha256=receipt['admission_event_sha256']);expected=_protocol_expected(pv)
        source=dict(run_id=run,state='COMPLETED',input_kind='synthetic-campaign',identity=p['runtime'],input_artifact=publish(run,f'artifacts/runs/{run}/baseline/inputs.json',primary),request_sha256=sha(primary),protocol_seal=seal,clean_environment=expected,attempts=[],outcomes=outcomes)
        source_raw=canonical(source);delta=history_delta(None,source).decode();hist=[dict(seq=1,body=delta,sha256=sha(source_raw))]
        with db:
            db.execute('INSERT INTO baseline_runs VALUES(?,?)',(run,source_raw.decode()));db.execute('INSERT INTO baseline_history VALUES(?,?,?,?)',(run,1,delta,sha(source_raw)))
        metadata=dict(final_state=source_raw.decode(),history=hist,controls=[]);base=[dict(kind='campaign',index=None,artifact=source['input_artifact'])]
        scorecard,spec=finish('scorecard',run,seal,expected,metadata,base,card_raw);states[lane+'_card']=scorecard
        # Aggregate output independently carries the scorecard history pin.
        cardpin=review_pin(scorecard,history(db,scorecard['task_id']))
        # Aggregate preparation uses a real published export path, with an explicit
        # placeholder task patched before the request is constructed below.
        def aggregate_finish():
            # Let finish choose the task, then publish its correctly owned export.
            original=globals()['build_bundle']
            def bundle(**kwargs):
                task=kwargs['task_id'];export=canonical(dict(schema='synthetic-native-audit-evidence-v1',index=0,scorecard=dict(state=scorecard,history=history(db,scorecard['task_id']),task=spec),unit_audits=[]))
                exported=publish(task,f'artifacts/runs/{task}/review/input/unit-audits-0.json',export)
                kwargs['records'].insert(-1,dict(kind='audit_history',index=0,artifact=exported));return original(**kwargs)
            globals()['build_bundle']=bundle
            try:
                return finish('aggregate',run,seal,expected,metadata,base+[dict(kind='scorecard',index=None,artifact=scorecard['artifact'])],lambda task,digest:canonical(dict(schema='synthetic-native-campaign-audit-v1',status='VERIFIED_PASS',scope='HISTORY_AGGREGATE_AND_COMMITTED_UNIT_AUDIT_CONSISTENCY',source_run_id=run,request_sha256=digest,scorecard_sha256=sha(card_raw),scorecard_task_id=scorecard['task_id'],scorecard_review=cardpin,comparison_index=index,history_audit=dict(history=dict(final_state_sha256=sha(source_raw),history_sha256=sha(canonical(hist)),controls_sha256=sha(canonical([])))),unit_audits=[],required_unit_audits=0,financial_accepted=False,full_M3=False)))
            finally:globals()['build_bundle']=original
        aggregate,_=aggregate_finish();states[lane+'_aggregate']=aggregate;a=aggregate['attempts'][-1]
        lanes.append(dict(lane=lane,run_id=run,protocol_seal=seal,input_artifact=source['input_artifact'],clean_environment=expected,source_state_sha256=sha(source_raw),source_history_sha256=sha(canonical(hist)),source_controls_sha256=sha(canonical([])),aggregate=dict(task_id=aggregate['task_id'],request_sha256=aggregate['request_sha256'],artifact=aggregate['artifact'],payload_sha256=aggregate['payload_sha256'],payload_bytes=aggregate['payload_bytes'],native_execution=a['native_execution'],job_receipt=a['job_receipt'],history_sha256=sha(canonical(history(db,aggregate['task_id']))))))
    meta=dict(schema='synthetic-pair-review-metadata-v1',pair=p,pair_sha256=pair.sha256,lanes=lanes);comparison=compare_indices(index,index);comparison.update(pair_sha256=pair.sha256,source_run_id=p['source']['run_id'],wheel_run_id=p['wheel']['run_id'],aggregate_payloads={lane:states[lane+'_aggregate']['payload_sha256'] for lane in ('source','wheel')})
    comparison_raw=canonical(comparison);compare,_=finish('pair_compare',p['source']['run_id'],lanes[0]['protocol_seal'],lanes[0]['clean_environment'],meta,[dict(kind='campaign',index=None,artifact=lanes[0]['input_artifact'])]+[dict(kind='aggregate',index=i,artifact=v['aggregate']['artifact']) for i,v in enumerate(lanes)],comparison_raw);states['comparison']=compare
    pins={key:review_pin(states['source_card' if key=='scorecard' else key],history(db,states['source_card' if key=='scorecard' else key]['task_id'])) for key in ('scorecard','source_aggregate','wheel_aggregate','comparison')}
    ticket=build_ticket(project_id=owned[0].project_id,pair=p,pair_sha256=pair.sha256,protocol_sha256=protocols,reviews=pins,comparison=comparison_raw)
    with db:
        db.execute('CREATE TABLE shortlist_tickets(pair_id TEXT PRIMARY KEY,seal_id TEXT UNIQUE,body TEXT,sha256 TEXT,receipt TEXT)');db.execute('INSERT INTO shortlist_tickets VALUES(?,?,?,?,NULL)',(p['pair_id'],p['source']['seal_id'],ticket.content.decode(),ticket.sha256))
    return seals,p,ticket,states,reviews


@pytest.fixture
def committed(owned,pair_inputs,monkeypatch):
    return make_committed(owned,pair_inputs,monkeypatch)


def test_committed_empty_shortlist_freezes_with_real_sql_file_and_journal_checks(committed):
    seals,p,ticket,states,reviews=committed;reserve_seal_append(seals.test_storage)
    start=time.monotonic();receipt=seals.freeze(p['source']['seal_id'],ticket.sha256)
    assert time.monotonic()-start<5 and receipt['status']=='FROZEN'
    assert json.loads(ticket.content)['comparison']['selection_projection']['selected']==[]
    assert seals.freeze(p['source']['seal_id'],ticket.sha256)==receipt


@pytest.mark.parametrize('fault',['missing_ticket','ticket_body','registration','source_history','source_controls','wheel_card_history','aggregate_history','comparison_history','request_file','task_file','output_file','reservation','oversize_row'])
def test_changed_committed_evidence_refuses_freeze_before_append(committed,fault):
    seals,p,ticket,states,reviews=committed;db=reviews.store.conn;compare=states['comparison'];root=seals.project.root_path
    with db:
        if fault=='missing_ticket':db.execute('DELETE FROM shortlist_tickets')
        elif fault=='ticket_body':db.execute("UPDATE shortlist_tickets SET body='{}'")
        elif fault=='registration':db.execute('DELETE FROM clean_campaign_members WHERE member_id=?',(p['wheel']['seal_id'],))
        elif fault=='source_history':db.execute('DELETE FROM baseline_history WHERE run_id=?',(p['wheel']['run_id'],))
        elif fault=='source_controls':db.execute('INSERT INTO baseline_controls VALUES(?,?,?,?)',(p['source']['run_id'],str(uuid4()),'pause','{}'))
        elif fault.endswith('_history'):
            key={'wheel_card_history':'wheel_card','aggregate_history':'wheel_aggregate','comparison_history':'comparison'}[fault];db.execute('DELETE FROM campaign_review_history WHERE task_id=? AND seq=2',(states[key]['task_id'],))
        elif fault in ('request_file','task_file','output_file'):
            artifact=compare['request_artifact'] if fault=='request_file' else compare['attempts'][-1]['task_artifact'] if fault=='task_file' else compare['artifact'];(root/artifact['path']).write_bytes(b'{}')
        elif fault=='reservation':db.execute("UPDATE reservations SET status='OPEN' WHERE id=?",(states['wheel_card']['attempts'][-1]['reservation_id'],))
        else:db.execute('UPDATE campaign_reviews SET body=? WHERE task_id=?',('x'*(16*1024+1),compare['task_id']))
    reserve_seal_append(seals.test_storage)
    with pytest.raises((DataError,RuntimeRefused)):seals.freeze(p['source']['seal_id'],ticket.sha256)
    assert verify_seal_journal(seals.project)['sequence']==4


def test_coordinator_ticket_is_immutable_and_calls_all_committed_reviews(committed,monkeypatch):
    seals,p,ticket,states,reviews=committed;calls=[];lookup={s['task_id']:s for s in states.values()}
    # This test isolates coordinator preparation; real full current() scans are
    # covered by paired campaign acceptance, not these simulated worker receipts.
    def completed(task):calls.append(task);return deepcopy(lookup[task])
    monkeypatch.setattr(reviews,'completed',completed)
    assert shortlist_freeze.prepare_shortlist(reviews,states['comparison']['task_id'])==ticket
    expected={states[k]['task_id'] for k in ('source_card','source_aggregate','wheel_aggregate','comparison')}
    assert set(calls)==expected and len(calls)==4
    with reviews.store.conn:reviews.store.conn.execute("UPDATE shortlist_tickets SET sha256=?",('f'*64,))
    with pytest.raises(DataError):shortlist_freeze.prepare_shortlist(reviews,states['comparison']['task_id'])


def test_real_evaluation_rpc_freeze_restart_barrier_and_limits(tmp_path):
    import subprocess,sys,os
    from pathlib import Path
    from test_fixture_processes import fixture_module
    python_process=fixture_module().python_process
    from compertum.runtime.owners import release_owner,acquire_owner
    from compertum.runtime.managed import launch_owner
    from compertum.runtime.owner_rpc import call_owner
    from compertum.runtime.identity import resolve_project
    from compertum.storage import StorageManager
    from compertum.config import load_config
    # Ownership transfer requires the actual prior process to exit. Prepare the
    # committed fixture in a bounded helper, then launch the separate owner.
    root=tmp_path/'prepared';root.mkdir()
    code="""import sys,json
from pathlib import Path
sys.path.insert(0,str(Path('tests').resolve()))
import pytest
from test_shortlist_owner import make_committed,owned,pair_inputs,environment
from compertum.data.encoding import canonical
root=Path(sys.argv[1]);generator=owned.__wrapped__(root);ownership=next(generator)
try:
 with pytest.MonkeyPatch.context() as patch:
  pair=pair_inputs.__wrapped__(environment.__wrapped__(root,patch))
  seals,p,ticket,states,reviews=make_committed(ownership,pair,patch,real_runtime=True)
  (root/'prepared-freeze.json').write_bytes(canonical(dict(pair=p,ticket_sha256=ticket.sha256,wheel_card_task=states['wheel_card']['task_id'])))
  seals.store.close();reviews.store.close()
finally:generator.close()
"""
    child=python_process(['-B','-c',code,str(root)],env={k:v for k,v in os.environ.items() if k.upper() in {'SYSTEMROOT','WINDIR','PYTHONPATH','PYTHONDONTWRITEBYTECODE','PYTHONNOUSERSITE'}},stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    out,err=child.communicate(timeout=30);assert child.returncode==0,(out,err)
    v=json.loads((root/'prepared-freeze.json').read_bytes());p=v['pair'];project=resolve_project(root)
    coordinator=acquire_owner(project,'coordinator');supervisor=acquire_owner(project,'supervisor');jobs=[];remotes=[]
    try:
        storage=StorageManager(coordinator,load_config(root/'config.toml',root))
        job,remote=launch_owner(supervisor,'evaluation');jobs.append(job);remotes.append(remote)
        limits=job.api.limits(job.job);assert limits.job_memory==256*1024**2 and limits.basic.active_limit==1 and limits.basic.affinity.bit_count()==1
        request=dict(operation='freeze',seal_id=p['source']['seal_id'],ticket_sha256=v['ticket_sha256']);reserve_seal_append(storage)
        started=time.monotonic();first=call_owner(remote,'synthetic_protocol',request);elapsed=time.monotonic()-started
        assert elapsed<5 and first['status']=='FROZEN'
        barrier=str(uuid4());call_owner(remote,'checkpoint',dict(operation='snapshot',barrier_id=barrier,destination='backups/freeze-fixture.sqlite',maximum_bytes=2*1024**2))
        with pytest.raises(RuntimeRefused,match='BARRIER_HELD'):call_owner(remote,'synthetic_protocol',request)
        call_owner(remote,'checkpoint',dict(operation='end',barrier_id=barrier))
        remote.close();job.close();job,remote=launch_owner(supervisor,'evaluation');jobs.append(job);remotes.append(remote)
        assert call_owner(remote,'synthetic_protocol',request)==first
        peak=job.api.limits(job.job).peak_job_memory;assert 0<peak<=256*1024**2
        record=dict(scope='NATIVE_OWNER_WITH_SIMULATED_WORKER_RECEIPTS',freeze_seconds=elapsed,owner_peak_bytes=peak,owner_limit_bytes=256*1024**2,receipt=first,full_M3=False,financial_accepted=False)
        (root/'native-freeze-measurement.json').write_bytes(canonical(record))
        with storage.store.conn:storage.store.conn.execute('DELETE FROM campaign_review_history WHERE task_id=? AND seq=2',(v['wheel_card_task'],))
        with pytest.raises(RuntimeRefused):call_owner(remote,'synthetic_protocol',request)
        assert verify_seal_journal(project)['sequence']==5
    finally:
        for remote in remotes:remote.close()
        for job in jobs:job.close()
        release_owner(supervisor);release_owner(coordinator)


def test_freeze_receipt_commit_failure_is_repairable_without_second_event(committed,monkeypatch):
    seals,p,ticket,states,reviews=committed;db=reviews.store.conn
    monkeypatch.setattr(shortlist_freeze,'prepare_shortlist',lambda *a:ticket)
    db.execute("CREATE TRIGGER ignore_freeze_receipt BEFORE UPDATE ON shortlist_tickets BEGIN SELECT RAISE(IGNORE); END")
    with pytest.raises(DataError):shortlist_freeze.freeze_shortlist(reviews,states['comparison']['task_id'],evaluation=seals)
    assert verify_seal_journal(seals.project)['sequence']==5
    assert db.execute('SELECT receipt FROM shortlist_tickets').fetchone()[0] is None
    db.execute('DROP TRIGGER ignore_freeze_receipt')
    receipt=shortlist_freeze.freeze_shortlist(reviews,states['comparison']['task_id'],evaluation=seals)
    assert db.execute('SELECT receipt FROM shortlist_tickets').fetchone()[0]==canonical(receipt).decode()
    assert verify_seal_journal(seals.project)['sequence']==5
