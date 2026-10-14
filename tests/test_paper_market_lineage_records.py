"""Durable capture identity; SQLite only, no provider or transport authority."""
from copy import deepcopy
from uuid import uuid4,uuid5,NAMESPACE_URL
import importlib.util
import pytest
from compertum.data.encoding import canonical
from compertum.runtime.errors import RuntimeRefused
from compertum.runtime.paper_market_grants import build_grant,initial_record
from test_paper_market_grants import fresh_values,PROJECT
from test_paper_market_records import records


def api():
    assert importlib.util.find_spec('compertum.runtime.paper_market_lineage_records'), 'Durable lineage capture records are missing'
    from compertum.runtime import paper_market_lineage_records
    return paper_market_lineage_records


def setup(records):
    r,db,_=records;grant=build_grant(**fresh_values());v=initial_record(grant)
    v.update(state='COMPLETE',consumed=True,summary=dict(state='PAIR_COMPLETE',reason=None,attempts=2,responses=2))
    with db:r.write(v,new=True)
    return api().LineageCaptureRecords(r),db,grant


def initial(grant,**changes):
    args=dict(capture_id=str(uuid4()),reservation_id=str(uuid4()));args.update(changes)
    return api().initial_capture(grant,**args)


def ready(store,db,v):
    with db:store.write(v,new=True)
    v.update(state='READY',lineage_sha256='c'*64,evidence=dict(size_bytes=65540,sha256='d'*64))
    with db:store.write(v)
    return v


def test_capture_identity_commits_before_evidence_and_survives_interruption(records):
    s,db,g=setup(records);v=initial(g)
    with db:s.write(v,new=True)
    cid=v['capture_id'];original=s.read(cid)
    assert original['state']=='CAPTURING' and original['evidence'] is original['lineage_sha256'] is original['manifest'] is None
    assert original['task_id']==str(uuid5(NAMESPACE_URL,PROJECT+'/paper-market-lineage/'+cid))
    s.interrupt_unfinished();after=s.read(cid)
    assert after==dict(original,state='INTERRUPTED',reason='OWNER_RESTARTED')
    with pytest.raises(RuntimeRefused),db:s.write(original)
    assert api().LineageCaptureRecords(s.records).read(cid)==after


@pytest.mark.parametrize('field',['capture_id','task_id','reservation_id','project_id','subject_key','account_alias','job_id','grant_sha256','owner_instance','owner_generation','history'])
def test_capture_identity_is_immutable(records,field):
    s,db,g=setup(records);v=ready(s,db,initial(g));changed=deepcopy(v)
    if field=='owner_generation':changed[field]+=1
    elif field=='history':changed[field]['grant_sha256']='f'*64
    elif field in {'project_id','subject_key','grant_sha256'}:changed[field]='f'*64
    elif field=='account_alias':changed[field]='other'
    else:changed[field]=str(uuid4())
    with pytest.raises(RuntimeRefused),db:s.write(changed)
    assert s.read(v['capture_id'])==v


@pytest.mark.parametrize('field',['lineage_sha256','evidence','state'])
def test_ready_evidence_cannot_be_replaced_or_erased(records,field):
    s,db,g=setup(records);v=ready(s,db,initial(g));changed=deepcopy(v)
    if field=='lineage_sha256':changed[field]='f'*64
    elif field=='evidence':changed[field]['sha256']='f'*64
    else:changed.update(state='CAPTURING',lineage_sha256=None,evidence=None)
    with pytest.raises(RuntimeRefused),db:s.write(changed)
    assert s.read(v['capture_id'])==v


def test_interrupted_ready_capture_can_only_ack_exact_retained_evidence(records):
    s,db,g=setup(records);v=ready(s,db,initial(g));s.interrupt_unfinished();v=s.read(v['capture_id'])
    assert v['state']=='INTERRUPTED' and v['lineage_sha256']=='c'*64
    manifest=dict(artifact_id=str(uuid4()),task_id=v['task_id'],path=f'artifacts/runs/{v["task_id"]}/market-lineage-{v["capture_id"]}.bin',**v['evidence'])
    published=dict(v,state='PUBLISHED',reason=None,manifest=manifest)
    with db:s.write(published)
    assert s.read(v['capture_id'])==published
    with pytest.raises(RuntimeRefused),db:s.write(v)
    changed=deepcopy(published);changed['manifest']['artifact_id']=str(uuid4())
    with pytest.raises(RuntimeRefused),db:s.write(changed)


@pytest.mark.parametrize('phase',['insert','update','lock'])
def test_ignored_writes_are_detected_without_claiming_progress(records,phase):
    s,db,g=setup(records);v=initial(g)
    if phase!='insert':
        with db:s.write(v,new=True)
    if phase=='insert':sql="CREATE TRIGGER ignore_capture BEFORE INSERT ON state WHEN NEW.key LIKE 'paper_market_lineage_capture:%' BEGIN SELECT RAISE(IGNORE); END"
    elif phase=='update':sql="CREATE TRIGGER ignore_capture BEFORE UPDATE ON state WHEN NEW.key LIKE 'paper_market_lineage_capture:%' BEGIN SELECT RAISE(IGNORE); END"
    else:sql="CREATE TRIGGER ignore_capture BEFORE UPDATE ON state WHEN NEW.key='paper_market_lineage_capture_version' BEGIN SELECT RAISE(IGNORE); END"
    db.execute(sql)
    changed=dict(v,state='FAILED',reason='INJECTED_CAPTURE_FAILURE')
    with pytest.raises(RuntimeRefused),db:s.write(v if phase=='insert' else changed,new=phase=='insert')
    assert not s.all() if phase=='insert' else s.read(v['capture_id'])==v


def test_one_pending_capture_and_bounded_history_without_eviction(records):
    s,db,g=setup(records);v=initial(g)
    with db:s.write(v,new=True)
    with pytest.raises(RuntimeRefused),db:s.write(initial(g),new=True)
    v.update(state='FAILED',reason='INJECTED_FAILURE')
    with db:s.write(v)
    first=deepcopy(v)
    for _ in range(31):
        v=initial(g)
        with db:s.write(v,new=True);v.update(state='FAILED',reason='INJECTED_FAILURE');s.write(v)
    with pytest.raises(RuntimeRefused),db:s.write(initial(g),new=True)
    assert len(s.all())==32 and s.read(first['capture_id'])==first


@pytest.mark.parametrize('fault',['oversize','invalid_json','wrong_key','version','missing_version','missing_job'])
def test_corrupt_or_orphan_capture_refuses_reopen(records,fault):
    s,db,g=setup(records);v=initial(g);key='paper_market_lineage_capture:'+v['capture_id']
    with db:s.write(v,new=True)
    with db:
        if fault=='oversize':db.execute('UPDATE state SET value=? WHERE key=?',('x'*16385,key))
        elif fault=='invalid_json':db.execute('UPDATE state SET value=? WHERE key=?',('{',key))
        elif fault=='wrong_key':db.execute('UPDATE state SET key=? WHERE key=?',('paper_market_lineage_capture:'+str(uuid4()),key))
        elif fault=='version':db.execute("UPDATE state SET value='2' WHERE key='paper_market_lineage_capture_version'")
        elif fault=='missing_version':db.execute("DELETE FROM state WHERE key='paper_market_lineage_capture_version'")
        else:db.execute('DELETE FROM state WHERE key=?',('paper_market_job:'+g.to_payload()['job_id'],))
    with pytest.raises(RuntimeRefused):api().LineageCaptureRecords(s.records)


def test_storage_identity_cannot_be_reused_after_failure(records):
    s,db,g=setup(records);v=initial(g)
    with db:s.write(v,new=True);v.update(state='FAILED',reason='INJECTED_FAILURE');s.write(v)
    duplicate=initial(g,reservation_id=v['reservation_id'])
    with pytest.raises(RuntimeRefused),db:s.write(duplicate,new=True)
    assert len(s.all())==1


def test_real_restart_order_preserves_ack_but_refuses_new_capture(records):
    s,db,g=setup(records);v=ready(s,db,initial(g));s.records.interrupt_unfinished()
    restarted=api().LineageCaptureRecords(s.records);restarted.interrupt_unfinished()
    after=restarted.read(v['capture_id']);assert after['evidence']==v['evidence']
    with pytest.raises(RuntimeRefused),db:restarted.write(initial(g),new=True)
    manifest=dict(artifact_id=str(uuid4()),task_id=v['task_id'],path=f'artifacts/runs/{v["task_id"]}/market-lineage-{v["capture_id"]}.bin',**v['evidence'])
    after.update(state='PUBLISHED',reason=None,manifest=manifest)
    with db:restarted.write(after)
    assert restarted.read(v['capture_id'])==after


@pytest.mark.parametrize('state',['READY','PUBLISHED','FAILED','INTERRUPTED'])
def test_new_record_cannot_manufacture_capture_or_publication(records,state):
    s,db,g=setup(records);v=initial(g);v.update(state=state)
    if state in {'READY','PUBLISHED'}:v.update(lineage_sha256='c'*64,evidence=dict(size_bytes=5,sha256='d'*64))
    else:v['reason']='INJECTED_FAILURE'
    if state=='PUBLISHED':v['manifest']=dict(artifact_id=str(uuid4()),task_id=v['task_id'],path=f'artifacts/runs/{v["task_id"]}/market-lineage-{v["capture_id"]}.bin',**v['evidence'])
    with pytest.raises(RuntimeRefused),db:s.write(v,new=True)
    assert s.all()==[]


@pytest.mark.parametrize('state',['CAPTURING','FAILED','INTERRUPTED'])
def test_no_publication_without_prior_ready_evidence(records,state):
    s,db,g=setup(records);v=initial(g)
    with db:s.write(v,new=True)
    if state!='CAPTURING':
        v.update(state=state,reason='INJECTED_FAILURE')
        with db:s.write(v)
    forged=dict(v,state='PUBLISHED',reason=None,lineage_sha256='c'*64,evidence=dict(size_bytes=5,sha256='d'*64))
    forged['manifest']=dict(artifact_id=str(uuid4()),task_id=v['task_id'],path=f'artifacts/runs/{v["task_id"]}/market-lineage-{v["capture_id"]}.bin',**forged['evidence'])
    with pytest.raises(RuntimeRefused),db:s.write(forged)
    assert s.read(v['capture_id'])==v


@pytest.mark.parametrize('fault',['purpose','version','extra','hash','size_bool','size_bound','no_hash','no_evidence','reason','manifest_task','manifest_path','manifest_size','manifest_hash'])
def test_invalid_record_shapes_refuse_without_mutation(records,fault):
    s,db,g=setup(records);v=ready(s,db,initial(g));bad=deepcopy(v)
    if fault=='purpose':bad['purpose']='OTHER'
    elif fault=='version':bad['version']=True
    elif fault=='extra':bad['extra']=False
    elif fault=='hash':bad['lineage_sha256']='NOT_A_HASH'
    elif fault=='size_bool':bad['evidence']['size_bytes']=True
    elif fault=='size_bound':bad['evidence']['size_bytes']=3*1024**2+1
    elif fault=='no_hash':bad['lineage_sha256']=None
    elif fault=='no_evidence':bad['evidence']=None
    elif fault=='reason':bad.update(state='FAILED',reason=None)
    else:
        bad.update(state='PUBLISHED',manifest=dict(artifact_id=str(uuid4()),task_id=v['task_id'],path=f'artifacts/runs/{v["task_id"]}/market-lineage-{v["capture_id"]}.bin',**v['evidence']))
        key=fault.removeprefix('manifest_');key={'task':'task_id','size':'size_bytes','hash':'sha256'}.get(key,key)
        bad['manifest'][key]=1 if key=='size_bytes' else 'f'*64 if key=='sha256' else str(uuid4())
    with pytest.raises(RuntimeRefused),db:s.write(bad)
    assert s.read(v['capture_id'])==v


def test_ready_capacity_and_ignored_restart_update_are_atomic(records):
    s,db,g=setup(records);v=ready(s,db,initial(g))
    with pytest.raises(RuntimeRefused),db:s.write(initial(g),new=True)
    db.execute("CREATE TRIGGER ignore_restart BEFORE UPDATE ON state WHEN NEW.key LIKE 'paper_market_lineage_capture:%' BEGIN SELECT RAISE(IGNORE); END")
    with pytest.raises(RuntimeRefused):s.interrupt_unfinished()
    assert s.read(v['capture_id'])==v and not db.in_transaction
    db.execute('DROP TRIGGER ignore_restart');s.interrupt_unfinished();after=s.read(v['capture_id']);s.interrupt_unfinished()
    assert s.read(v['capture_id'])==after


def test_capture_write_does_not_commit_its_callers_transaction(records):
    s,db,g=setup(records);v=initial(g);s.write(v,new=True)
    assert db.in_transaction and s.read(v['capture_id'])==v
    db.rollback();assert s.all()==[]


@pytest.mark.parametrize('operation',['read','write','all'])
def test_live_version_change_is_rechecked(records,operation):
    s,db,g=setup(records);v=initial(g)
    with db:s.write(v,new=True);db.execute("UPDATE state SET value='2' WHERE key='paper_market_lineage_capture_version'")
    with pytest.raises(RuntimeRefused):
        if operation=='read':s.read(v['capture_id'])
        elif operation=='write':s.write(v)
        else:s.all()


def test_consistently_replaced_original_grant_refuses_capture_reopen(records):
    s,db,g=setup(records);v=initial(g)
    with db:s.write(v,new=True)
    original=s.records.read(v['job_id']);original['grant']['subject_key']='f'*64
    from compertum.runtime.paper_market_grants import MarketGrant
    original['grant_sha256']=MarketGrant(canonical(original['grant'])).sha256
    with db:db.execute('UPDATE state SET value=? WHERE key=?',(canonical(original).decode(),'paper_market_job:'+v['job_id']))
    with pytest.raises(RuntimeRefused):api().LineageCaptureRecords(s.records)
