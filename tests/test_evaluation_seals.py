"""Actual evaluation leases, durable sealed rules and rollback/guard failures."""
import hashlib
import json
from pathlib import Path
import sqlite3
from uuid import uuid4
import pytest
from test_persistence import owned,event
from compertum.data.encoding import canonical
from compertum.evaluation_protocol import build_protocol
from compertum.evaluation_seals import EvaluationSeals,verify_seal_journal,reserve_seal_append
from compertum.persistence import open_store
from compertum.runtime.errors import RuntimeRefused
from compertum.runtime.identity_pins import runtime_identity


def protocol(run_id=None,**changes):
    args=dict(development_run_id=run_id or str(uuid4()),development_sha256='a'*64,data_manifest_sha256='b'*64,
        holdout_manifest_sha256='c'*64,runtime=runtime_identity())
    args.update(changes);return build_protocol(**args)


def ledger(owned):
    from test_storage import manager
    from compertum.storage import reserve_runtime_paths
    storage=manager(owned);reserve_runtime_paths(storage)
    seals=EvaluationSeals(open_store(owned[1]['evaluation'],'evaluation'));seals.test_storage=storage
    return seals


def create(seals,*args):
    # Explicit fixture grant; the product owner cannot reserve for itself.
    reserve_seal_append(seals.test_storage)
    return seals.create(*args)


def invalidate(seals,*args):
    reserve_seal_append(seals.test_storage)
    return seals.invalidate(*args)


def test_native_seal_immutable_idempotent_and_restart(owned):
    seals=ledger(owned);p=protocol();sid=str(uuid4());first=create(seals,sid,p.content,p.sha256)
    assert first==create(seals,sid,p.content,p.sha256)==seals.inspect(sid)
    assert first['status']=='SEALED' and not first['development_admitted'] and not first['financial_accepted']
    seals.store.close();other=ledger(owned)
    assert other.inspect(sid)==first and len(verify_seal_journal(owned[0])['events'])==1


def test_wrong_owner_and_closed_lease_denied(owned):
    with pytest.raises(RuntimeRefused,match='WRONG_OWNER_ROLE'):
        EvaluationSeals(open_store(owned[1]['coordinator'],'coordinator'))
    assert not (owned[0].root_path/'state/evaluation-seals').exists()
    seals=ledger(owned);seals.store.close()
    with pytest.raises(RuntimeRefused,match='STORE_CLOSED'):seals.inspect(str(uuid4()))


def test_changed_protocol_same_id_and_duplicate_run_denied(owned):
    seals=ledger(owned);p=protocol();sid=str(uuid4());create(seals,sid,p.content,p.sha256)
    changed=protocol(json.loads(p.content)['development_run_id'],data_manifest_sha256='d'*64)
    with pytest.raises(RuntimeRefused,match='SEAL_CONFLICT'):create(seals,sid,changed.content,changed.sha256)
    with pytest.raises(RuntimeRefused,match='SEAL_RUN_CONFLICT'):create(seals,str(uuid4()),p.content,p.sha256)
    assert len(verify_seal_journal(owned[0])['events'])==1


def test_changed_runtime_denied_without_record(owned):
    seals=ledger(owned);runtime=runtime_identity();runtime['package_sha256']='f'*64;p=protocol(runtime=runtime)
    with pytest.raises(RuntimeRefused,match='SEAL_RUNTIME_CHANGED'):create(seals,str(uuid4()),p.content,p.sha256)
    assert verify_seal_journal(owned[0])['sequence']==0


def test_invalidation_is_sticky_after_old_sqlite_rows_restored(owned):
    seals=ledger(owned);p=protocol();sid=str(uuid4());create(seals,sid,p.content,p.sha256)
    invalid=invalidate(seals,sid,'POLICY_CHANGED')
    with seals.store.conn:seals.store.conn.execute('DELETE FROM evaluation_seal_events WHERE sequence=2')
    seals.store.close();again=ledger(owned)
    assert again.inspect(sid)==invalid and invalid['status']=='INVALIDATED'
    assert again.store.conn.execute('SELECT count(*) FROM evaluation_seal_events').fetchone()[0]==2
    with pytest.raises(RuntimeRefused,match='SEAL_INVALIDATED'):create(again,sid,p.content,p.sha256)
    assert invalidate(again,sid,'POLICY_CHANGED')==invalid
    with pytest.raises(RuntimeRefused,match='SEAL_CONFLICT'):invalidate(again,sid,'INPUT_CHANGED')


@pytest.mark.parametrize('failure',['missing_head','missing_event','partial','changed_event','changed_head','missing_directory'])
def test_guard_uncertainty_never_reprovisions(owned,failure):
    seals=ledger(owned);p=protocol();sid=str(uuid4());create(seals,sid,p.content,p.sha256)
    directory=owned[0].root_path/'state/evaluation-seals'
    # Rename preserves each deliberate corruption fixture for inspection.
    if failure=='missing_head':(directory/'head.json').rename(directory.parent/'preserved-head.json')
    elif failure=='missing_event':(directory/'00000001.json').rename(directory.parent/'preserved-event.json')
    elif failure=='partial':(directory/'partial').write_bytes(b'partial')
    elif failure=='changed_event':(directory/'00000001.json').write_bytes(b'{}')
    elif failure=='changed_head':(directory/'head.json').write_bytes(canonical({'sequence':0,'sha256':'0'*64}))
    else:directory.rename(directory.parent/'preserved-journal')
    assert verify_seal_journal(owned[0])['status']=='SEAL_JOURNAL_COMPROMISED'
    with pytest.raises(RuntimeRefused,match='SEAL_JOURNAL_COMPROMISED'):seals.inspect(sid)
    seals.store.close()
    with pytest.raises(RuntimeRefused,match='SEAL_JOURNAL_COMPROMISED'):ledger(owned)


def test_partial_append_preserved_and_denied(owned,monkeypatch):
    import compertum.evaluation_seals as module
    seals=ledger(owned);p=protocol();sid=str(uuid4());original=module._flush
    def partial(path,raw):
        if path.name=='00000001.json':path.write_bytes(raw[:40]);raise OSError('injected')
        return original(path,raw)
    monkeypatch.setattr(module,'_flush',partial)
    with pytest.raises(RuntimeRefused,match='SEAL_APPEND_UNVERIFIED'):create(seals,sid,p.content,p.sha256)
    assert (owned[0].root_path/'state/evaluation-seals/00000001.json').stat().st_size==40
    with pytest.raises(RuntimeRefused,match='SEAL_JOURNAL_COMPROMISED'):create(seals,sid,p.content,p.sha256)


def test_failed_mirror_blocks_call_but_durable_original_recovers(owned):
    seals=ledger(owned);p=protocol();sid=str(uuid4())
    seals.store.conn.execute("CREATE TRIGGER reject_seal BEFORE INSERT ON evaluation_seal_events BEGIN SELECT RAISE(ABORT,'fixture'); END")
    with pytest.raises(RuntimeRefused,match='SEAL_MIRROR_UNVERIFIED'):create(seals,sid,p.content,p.sha256)
    evidence=verify_seal_journal(owned[0]);assert evidence['sequence']==1
    seals.store.conn.execute('DROP TRIGGER reject_seal')
    receipt=create(seals,sid,p.content,p.sha256)
    assert receipt['created_at']==evidence['seals'][sid]['creation']['created_at'] and verify_seal_journal(owned[0])['sequence']==1


def test_generic_event_cannot_create_or_replace_seal(owned):
    seals=ledger(owned)
    with pytest.raises(RuntimeRefused,match='TRANSITION_AUTHORITY_DENIED'):
        seals.store.commit_event(event(payload={'key':'evaluation_seal','value':'SEALED'}))
    assert verify_seal_journal(owned[0])['sequence']==0


@pytest.mark.parametrize('payload',[{},None,{'operation':'reset'},{'operation':'inspect','seal_id':'bad'},
    {'operation':'create','seal_id':str(uuid4()),'protocol_utf8':False,'protocol_sha256':'a'*64},
    {'operation':'invalidate','seal_id':str(uuid4()),'reason':'secret text'},
    {'operation':'inspect','seal_id':str(uuid4()),'authority':True}])
def test_malformed_rpc_has_typed_refusal(owned,payload):
    seals=ledger(owned)
    with pytest.raises(RuntimeRefused):seals.handle(payload)
    assert verify_seal_journal(owned[0])['sequence']==0


def test_mirror_corruption_does_not_become_fresh_authority(owned):
    seals=ledger(owned);p=protocol();sid=str(uuid4());create(seals,sid,p.content,p.sha256)
    with seals.store.conn:seals.store.conn.execute("UPDATE evaluation_seal_events SET body='{}'")
    with pytest.raises(RuntimeRefused,match='SEAL_JOURNAL_COMPROMISED'):seals.inspect(sid)


def test_count_bound_before_append(owned,monkeypatch):
    import compertum.evaluation_seals as module
    seals=ledger(owned);p=protocol();create(seals,str(uuid4()),p.content,p.sha256)
    monkeypatch.setattr(module,'MAX_SEALS',1);p=protocol()
    with pytest.raises(RuntimeRefused,match='SEAL_COUNT_BOUND'):create(seals,str(uuid4()),p.content,p.sha256)
    assert verify_seal_journal(owned[0])['sequence']==1


def test_pre_registry_database_plus_lost_journal_cannot_reset_seals(owned):
    original=open_store(owned[1]['evaluation'],'evaluation')
    before=owned[0].root_path/'pre-registry.sqlite'
    with sqlite3.connect(before) as snapshot:original.conn.backup(snapshot)
    seals=ledger(owned);p=protocol();sid=str(uuid4());create(seals,sid,p.content,p.sha256);invalidate(seals,sid,'POLICY_CHANGED')
    destination=seals.store.path;seals.store.close()
    (owned[0].root_path/'state/evaluation-seals').rename(owned[0].root_path/'preserved-later-journal')
    with sqlite3.connect(before) as snapshot,sqlite3.connect(destination) as restored:snapshot.backup(restored)
    with pytest.raises(RuntimeRefused,match='SEAL_JOURNAL_COMPROMISED'):ledger(owned)
    assert not (owned[0].root_path/'state/evaluation-seals').exists()


def test_surviving_seals_cannot_regenerate_lost_consumption_evidence(owned):
    from compertum.consumption import consume_once
    seals=ledger(owned);p=protocol();sid=str(uuid4());create(seals,sid,p.content,p.sha256)
    consume_once(owned[1]['evaluation'],sid,str(uuid4()),{'input_sha256':'a'*64,'protocol_sha256':p.sha256,'shortlist_sha256':'b'*64})
    path=seals.store.path;seals.store.close()
    path.rename(owned[0].root_path/'preserved-evaluation.sqlite')
    for suffix in ('-wal','-shm'):
        side=Path(str(path)+suffix)
        if side.exists():side.rename(owned[0].root_path/('preserved-evaluation.sqlite'+suffix))
    (owned[0].root_path/'state/evaluation-consumption').rename(owned[0].root_path/'preserved-consumption')
    with pytest.raises(RuntimeRefused,match='EVALUATION_COMPROMISED'):open_store(owned[1]['evaluation'],'evaluation')
    assert not (owned[0].root_path/'state/evaluation-consumption').exists()
    assert verify_seal_journal(owned[0])['sequence']==1


@pytest.mark.parametrize('fault',[None,'head','event','ordering','excess'])
def test_frozen_mirror_uses_identical_journal_replay(owned,fault):
 from copy import deepcopy
 from compertum.evaluation_seals import replay_seal_events
 seals=ledger(owned);p=protocol();sid=str(uuid4());create(seals,sid,p.content,p.sha256);invalidate(seals,sid,'STATUS_UNCERTAIN')
 actual=verify_seal_journal(seals.project);events=deepcopy(actual['events']);head={k:actual[k] for k in ('sequence','sha256')}
 if fault=='head':head['sha256']='f'*64
 elif fault=='event':events[-1]['record']['reason']='invented'
 elif fault=='ordering':events.reverse()
 elif fault=='excess':events*=129;head['sequence']=len(events)
 replay=replay_seal_events(seals.project.project_id,events,head)
 if fault:assert replay['status']=='SEAL_JOURNAL_COMPROMISED'
 else:assert replay==actual
