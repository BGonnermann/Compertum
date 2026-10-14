"""Coordinator route identity and publication history; no storage authority."""
from copy import deepcopy
from uuid import uuid4
import importlib.util
import pytest
from compertum.data.encoding import canonical
from compertum.runtime.errors import RuntimeRefused
from test_paper_market_records import records
from test_paper_market_lineage_records import setup,initial


def api():
    assert importlib.util.find_spec('compertum.runtime.paper_market_lineage_routes'), 'Durable lineage routes are missing'
    from compertum.runtime import paper_market_lineage_routes
    return paper_market_lineage_routes


def route_store(records):
    captures,db,grant=setup(records);v=initial(grant)
    v.update(purpose='COMPERTUM_MARKET_LINEAGE_ROUTE_V1',state='WAITING')
    return api().LineageRoutes(db,captures.project_id),db,v


def transferring(s,db,v):
    with db:s.write(v,new=True)
    v.update(state='TRANSFERRING',lineage_sha256='c'*64,evidence=dict(size_bytes=65540,sha256='d'*64))
    with db:s.write(v)
    return v


def manifest(v):
    return dict(artifact_id=str(uuid4()),task_id=v['task_id'],path=f'artifacts/runs/{v["task_id"]}/market-lineage-{v["capture_id"]}.bin',**v['evidence'])


def test_manifest_is_saved_before_ack_and_failed_ack_preserves_recovery(records):
    s,db,v=route_store(records);transferring(s,db,v);v['manifest']=manifest(v)
    with db:s.write(v)
    v.update(state='FAILED',reason='LOST_ACK')
    with db:s.write(v)
    restarted=api().LineageRoutes(db,s.project_id);assert restarted.read(v['capture_id'])==v
    v.update(state='PUBLISHED',reason=None)
    with db:restarted.write(v)
    assert restarted.read(v['capture_id'])==v


@pytest.mark.parametrize('field',['capture_id','task_id','reservation_id','project_id','subject_key','account_alias','job_id','grant_sha256','owner_instance','owner_generation','history','evidence','lineage_sha256','manifest'])
def test_route_binding_and_retained_proof_cannot_change(records,field):
    s,db,v=route_store(records);transferring(s,db,v);v['manifest']=manifest(v)
    with db:s.write(v)
    bad=deepcopy(v)
    if field=='owner_generation':bad[field]+=1
    elif field in {'evidence','history'}:bad[field]['sha256' if field=='evidence' else 'grant_sha256']='f'*64
    elif field=='manifest':bad[field]['artifact_id']=str(uuid4())
    elif field in {'lineage_sha256','project_id','subject_key','grant_sha256'}:bad[field]='f'*64
    elif field=='account_alias':bad[field]='other'
    else:bad[field]=str(uuid4())
    with pytest.raises(RuntimeRefused),db:s.write(bad)
    assert s.read(v['capture_id'])==v


@pytest.mark.parametrize('phase',['insert','update','lock'])
def test_ignored_route_writes_roll_back(records,phase):
    s,db,v=route_store(records)
    if phase!='insert':
        with db:s.write(v,new=True)
    event='INSERT' if phase=='insert' else 'UPDATE'
    where="NEW.key='paper_market_lineage_route_version'" if phase=='lock' else "NEW.key LIKE 'paper_market_lineage_route:%'"
    db.execute(f'CREATE TRIGGER ignore_route BEFORE {event} ON state WHEN {where} BEGIN SELECT RAISE(IGNORE); END')
    bad=dict(v,state='FAILED',reason='INJECTED_FAILURE')
    with pytest.raises(RuntimeRefused),db:s.write(v if phase=='insert' else bad,new=phase=='insert')
    assert not s.all() if phase=='insert' else s.read(v['capture_id'])==v


@pytest.mark.parametrize('fault',['version','missing_version','wrong_key','oversize','json','extra','history','task','published_without_manifest','evidence_half'])
def test_corrupt_routes_refuse_reopen(records,fault):
    s,db,v=route_store(records)
    with db:s.write(v,new=True)
    key='paper_market_lineage_route:'+v['capture_id']
    with db:
        if fault=='version':db.execute("UPDATE state SET value='2' WHERE key='paper_market_lineage_route_version'")
        elif fault=='missing_version':db.execute("DELETE FROM state WHERE key='paper_market_lineage_route_version'")
        elif fault=='wrong_key':db.execute('UPDATE state SET key=? WHERE key=?',('paper_market_lineage_route:'+str(uuid4()),key))
        else:
            if fault=='extra':v['extra']=False
            elif fault=='history':v['history']['manifest']['task_id']=str(uuid4())
            elif fault=='task':v['task_id']=str(uuid4())
            elif fault=='published_without_manifest':v['state']='PUBLISHED'
            elif fault=='evidence_half':v['lineage_sha256']='c'*64
            raw='x'*16385 if fault=='oversize' else '{' if fault=='json' else canonical(v).decode()
            db.execute('UPDATE state SET value=? WHERE key=?',(raw,key))
    with pytest.raises(RuntimeRefused):api().LineageRoutes(db,s.project_id)


def test_route_capacity_terminal_history_and_reservation_reuse(records):
    s,db,v=route_store(records)
    with db:s.write(v,new=True)
    from compertum.runtime.paper_market_lineage_records import task_id
    def another():
        r=deepcopy(v);r.update(capture_id=str(uuid4()),reservation_id=str(uuid4()),state='WAITING',reason=None)
        r['task_id']=task_id(r['project_id'],r['capture_id']);return r
    with pytest.raises(RuntimeRefused),db:s.write(another(),new=True)
    v.update(state='FAILED',reason='INJECTED_FAILURE')
    with db:s.write(v)
    bad=another();bad['reservation_id']=v['reservation_id']
    with pytest.raises(RuntimeRefused),db:s.write(bad,new=True)
    for _ in range(31):
        r=another()
        with db:s.write(r,new=True);r.update(state='FAILED',reason='INJECTED_FAILURE');s.write(r)
    with pytest.raises(RuntimeRefused),db:s.write(another(),new=True)
    assert len(s.all())==32 and s.read(v['capture_id'])==v


def test_routes_do_not_commit_or_restore_transfer_after_restart(records):
    s,db,v=route_store(records);s.write(v,new=True);assert db.in_transaction;db.rollback();assert s.all()==[]
    transferring(s,db,v);v.update(state='FAILED',reason='COORDINATOR_RESTARTED')
    with db:s.write(v)
    before=deepcopy(v);v.update(state='TRANSFERRING',reason=None)
    with pytest.raises(RuntimeRefused),db:s.write(v)
    assert s.read(v['capture_id'])==before
