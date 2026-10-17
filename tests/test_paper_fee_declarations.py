"""Retained declared sources remain unqualified even when their bytes match."""
from uuid import uuid4
import base64,json,pickle
import pytest
from compertum.data.encoding import canonical
from compertum.runtime.errors import RuntimeRefused
from test_execution_health import pair,connect
from test_paper_read_owner import owner
from test_paper_read_publication import publication
from test_paper_fees import schedule,source,rule,uid


def declared(o, schedules=None):
    from compertum.runtime.paper_fee_declarations import prepare_fee_declaration,publish_fee_declaration
    task,identity=str(uuid4()),str(uuid4())
    record=prepare_fee_declaration(project_id=o.e.lease.project_id,task_id=task,
        declaration_id=identity,schedules=(schedule(),) if schedules is None else schedules)
    grant=o.manager.reserve_bytes(task,'records',len(record.content))
    manifest=publish_fee_declaration(o.manager,grant,record)
    return identity,record,manifest,grant


def test_retained_source_bytes_and_schedules_roundtrip_without_qualification(publication):
    from compertum.runtime.paper_fee_declarations import read_fee_declaration
    o,_,_=publication;identity,record,manifest,_=declared(o)
    payload,schedules,original=read_fee_declaration(o.e.lease,identity,manifest)
    assert payload['purpose']=='DECLARED_FEE_INPUTS' and payload['declaration_id']==identity
    assert base64.b64decode(payload['sources'][0]['raw_base64'],validate=True)==b'Invented fee source'
    assert schedules==(schedule(),) and schedules[0].sources[0].to_payload()['provenance']=='UNVERIFIED_CAPTURE'
    assert manifest['path']==f"artifacts/runs/{manifest['task_id']}/declared-fees-{identity}.json"
    assert original() is None
    assert 'Invented fee source' not in repr(record)
    with pytest.raises(RuntimeRefused):pickle.dumps(record)


def test_repeated_publication_keeps_original_bytes_and_reservation(publication):
    from compertum.runtime.paper_fee_declarations import publish_fee_declaration
    o,_,_=publication;_,record,manifest,grant=declared(o);before=o.manager.store.conn.total_changes
    assert publish_fee_declaration(o.manager,grant,record)==manifest
    assert o.manager.store.conn.total_changes==before


@pytest.mark.parametrize('fault',['declaration','project','manifest','unpublished','bytes','missing'])
def test_foreign_or_changed_published_record_refuses(publication,fault):
    from compertum.runtime.paper_fee_declarations import read_fee_declaration
    o,_,_=publication;identity,_,manifest,grant=declared(o);m=dict(manifest)
    if fault=='declaration':identity=str(uuid4())
    elif fault=='project':m['project_id']='f'*64
    elif fault=='manifest':m['sha256']='0'*64
    elif fault=='unpublished':
        with o.manager.store.conn:o.manager.store.conn.execute("UPDATE reservations SET status='RESERVED' WHERE id=?",(grant.grant_id,))
    elif fault=='bytes':(o.manager.root/m['path']).write_bytes(b'{}')
    else:(o.manager.root/m['path']).rename(o.manager.root/(m['path']+'.preserved'))
    with pytest.raises(RuntimeRefused):read_fee_declaration(o.e.lease,identity,m)


def test_original_check_detects_change_after_capture(publication):
    from compertum.runtime.paper_fee_declarations import read_fee_declaration
    o,_,_=publication;identity,_,manifest,_=declared(o)
    _,_,original=read_fee_declaration(o.e.lease,identity,manifest)
    (o.manager.root/manifest['path']).write_bytes(b'{}')
    with pytest.raises(RuntimeRefused):original()


def test_duplicate_or_undeclared_schedule_sources_refuse(publication):
    from compertum.runtime.paper_fee_declarations import prepare_fee_declaration
    o,_,_=publication;s=schedule()
    with pytest.raises(RuntimeRefused):
        prepare_fee_declaration(project_id=o.e.lease.project_id,task_id=str(uuid4()),declaration_id=str(uuid4()),schedules=(s,s))


def test_large_original_source_is_retained_without_text_conversion(publication):
    from compertum.paper_fees import FeeSource,FeeSchedule
    from compertum.runtime.paper_fee_declarations import read_fee_declaration
    o,_,_=publication
    raw=bytes(range(256))*8192
    public=FeeSource(raw,'https://example.invalid/retained-fee-document','application/pdf','2026-10-01T12:00:00Z')
    value=schedule().to_payload();value['source_sha256']=[public.sha256]
    s=FeeSchedule((public,),canonical(value))
    identity,_,manifest,_=declared(o,(s,))
    _,restored,original=read_fee_declaration(o.e.lease,identity,manifest)
    assert restored[0].sources[0].raw==raw and len(raw)==2*1024**2
    original()


def test_publication_above_twelve_mib_refuses_before_decode(publication):
    from compertum.runtime.paper_fee_declarations import read_fee_declaration
    o,_,_=publication;task,identity=str(uuid4()),str(uuid4())
    raw=b'x'*(12*1024**2+1);grant=o.manager.reserve_bytes(task,'records',len(raw))
    writer=o.manager.open_artifact(grant,f'artifacts/runs/{task}/declared-fees-{identity}.json')
    try:
        for index in range(0,len(raw),65536):writer.write(raw[index:index+65536])
        manifest=writer.publish()
    finally:writer.close()
    with pytest.raises(RuntimeRefused):read_fee_declaration(o.e.lease,identity,manifest)


def test_pending_caller_transaction_refuses_before_publication(publication):
    from compertum.runtime.paper_fee_declarations import prepare_fee_declaration,publish_fee_declaration
    o,_,_=publication;task,identity=str(uuid4()),str(uuid4())
    record=prepare_fee_declaration(project_id=o.e.lease.project_id,task_id=task,
        declaration_id=identity,schedules=(schedule(),))
    grant=o.manager.reserve_bytes(task,'records',len(record.content));db=o.manager.store.conn
    db.execute("INSERT INTO state VALUES('fee-caller-uncommitted','true')")
    with pytest.raises(RuntimeRefused):publish_fee_declaration(o.manager,grant,record)
    assert db.in_transaction
    assert not (o.manager.root/f'artifacts/runs/{task}/declared-fees-{identity}.json').exists()
    assert db.execute('SELECT status FROM reservations WHERE id=?',(grant.grant_id,)).fetchone()==('RESERVED',)
    db.rollback();assert db.execute("SELECT 1 FROM state WHERE key='fee-caller-uncommitted'").fetchone() is None
