"""Real native leases and SQLite durability; no broker or protected inputs."""
import importlib
import json
import os
from pathlib import Path
import sqlite3
from uuid import uuid4
import pytest
from compertum.runtime.errors import RuntimeRefused
from compertum.runtime.identity import resolve_project
from compertum.runtime.owners import acquire_owner, release_owner

pytestmark = pytest.mark.skipif(os.name != 'nt', reason='NATIVE_WINDOWS_UNAVAILABLE')

@pytest.fixture
def owned(tmp_path):
    project = resolve_project(tmp_path)
    leases = {role: acquire_owner(project, role) for role in ('coordinator','evaluation','execution')}
    try: yield project, leases
    finally:
        from compertum.runtime.owners import _LEASES
        for lease in leases.values():
            if lease in _LEASES: release_owner(lease)


def api(): return importlib.import_module('compertum.persistence')


def event(kind='FIXTURE_TRANSITION', target='evaluation', payload=None):
    return {'event_id':str(uuid4()), 'kind':kind, 'target_role':target,
            'payload': payload or {'key':'fixture', 'value':'READY'}}


def test_wrong_owner_cannot_create_or_mutate_store(owned):
    project, leases = owned
    with pytest.raises(RuntimeRefused, match='WRONG_OWNER_ROLE'):
        api().open_store(leases['coordinator'], 'evaluation')
    assert not (project.root_path/'state/evaluation.sqlite').exists()
    store = api().open_store(leases['coordinator'], 'coordinator')
    assert store.inspect()['journal_mode'] == 'wal'
    assert store.inspect()['synchronous'] == 2
    assert store.inspect()['foreign_keys'] == 1
    release_owner(leases['coordinator'])
    with pytest.raises(RuntimeRefused): store.commit_event(event())


def test_event_and_local_transition_are_atomic_and_deduplicated(owned):
    _, leases = owned
    store = api().open_store(leases['coordinator'], 'coordinator')
    item = event(); first = store.commit_event(item)
    assert store.commit_event(item) == first
    assert store.inspect()['event_count'] == 1
    assert store.get_state('fixture') == 'READY'
    with pytest.raises(RuntimeRefused, match='EVENT_CONFLICT'):
        store.commit_event({**item,'payload':{'key':'fixture','value':'CHANGED'}})
    assert store.get_state('fixture') == 'READY'


def test_lost_ack_redelivery_changes_receiver_once(owned):
    _, leases = owned
    sender = api().open_store(leases['coordinator'],'coordinator')
    receiver = api().open_store(leases['evaluation'],'evaluation')
    first = sender.commit_event(event())
    message = sender.pending()[0]
    ack = receiver.accept_message(message)
    assert len(sender.pending()) == 1  # lost acknowledgement
    assert receiver.accept_message(message) == ack
    assert receiver.inspect()['inbox_count'] == 1
    assert receiver.get_state('fixture') == 'READY'
    sender.acknowledge(first.event_id, ack)
    assert sender.pending() == []
    sender.close()
    reopened = api().open_store(leases['coordinator'],'coordinator')
    assert reopened.inspect()['event_count'] == 1 and reopened.pending() == []


def test_side_effect_record_is_retained_but_never_replayed(owned):
    _, leases = owned
    sender = api().open_store(leases['coordinator'],'coordinator')
    receiver = api().open_store(leases['execution'],'execution')
    sender.commit_event(event('BROKER_SIDE_EFFECT','execution'))
    message = sender.pending()[0]
    assert message['replayable'] is False
    with pytest.raises(RuntimeRefused, match='NONREPLAYABLE_MESSAGE'):
        receiver.accept_message(message)
    assert receiver.inspect()['inbox_count'] == 0 and len(sender.pending()) == 1


def test_checkpoint_has_real_snapshot_pending_and_dedup_records(owned):
    project, leases = owned
    store = api().open_store(leases['coordinator'],'coordinator')
    store.commit_event(event())
    destination = project.root_path/'checkpoints/one.sqlite'
    receipt = store.checkpoint(str(uuid4()),destination)
    assert receipt['event_high_water'] == 1 and len(receipt['pending']) == 1
    import hashlib
    assert hashlib.sha256(destination.read_bytes()).hexdigest() == receipt['sha256']
    with sqlite3.connect(destination) as conn:
        assert conn.execute('select count(*) from events').fetchone()[0] == 1
        assert conn.execute('pragma integrity_check').fetchone()[0] == 'ok'
    with pytest.raises(RuntimeRefused): store.checkpoint(str(uuid4()),destination)
    with pytest.raises(RuntimeRefused): store.checkpoint(str(uuid4()),project.root_path.parent/'escape.sqlite')


def test_attempt_lineage_and_restart_interruption_are_retained(owned):
    _, leases = owned
    store = api().open_store(leases['coordinator'],'coordinator')
    run_id, task_id = str(uuid4()),str(uuid4())
    store.record_attempt(run_id,task_id,1,'RUNNING',{'code_sha256':'a'*64})
    store.close()
    store = api().open_store(leases['coordinator'],'coordinator')
    assert store.attempts()[0]['status'] == 'INTERRUPTED'
    assert store.attempts()[0]['lineage']['code_sha256'] == 'a'*64


def test_unrecognized_database_is_rejected_without_schema_changes(owned):
    project,leases=owned
    path=project.root_path/'state/research.sqlite'
    with sqlite3.connect(path) as conn:
        conn.execute('CREATE TABLE unrelated(value TEXT)')
        conn.execute("INSERT INTO unrelated VALUES('preserve')")
    before=path.read_bytes()
    with pytest.raises(RuntimeRefused,match='STORE_IDENTITY_MISMATCH'):
        api().open_store(leases['coordinator'],'coordinator')
    assert path.read_bytes()==before


def test_transaction_failure_leaves_no_state_or_outbox(owned):
    project,leases=owned
    store=api().open_store(leases['coordinator'],'coordinator')
    # Inject a real SQLite failure after the local transition, before commit.
    store.conn.execute("CREATE TRIGGER reject_event BEFORE INSERT ON events BEGIN SELECT RAISE(ABORT,'fixture'); END")
    with pytest.raises(sqlite3.IntegrityError): store.commit_event(event())
    assert store.get_state('fixture') is None
    assert store.inspect()['event_count']==0 and store.pending()==[]


def test_checkpoint_export_and_file_size_are_bounded(owned,monkeypatch):
    project,leases=owned
    module=api(); store=module.open_store(leases['coordinator'],'coordinator')
    store.commit_event(event()); store.commit_event(event())
    monkeypatch.setattr(module,'MAX_EXPORT_ROWS',1)
    destination=project.root_path/'bounded/snapshot.sqlite'
    with pytest.raises(RuntimeRefused,match='CHECKPOINT_BOUND_EXCEEDED'):
        store.checkpoint(str(uuid4()),destination)
    assert not destination.exists()


def test_replaced_message_and_wrong_ack_are_rejected(owned):
    _,leases=owned; sender=api().open_store(leases['coordinator'],'coordinator')
    receiver=api().open_store(leases['evaluation'],'evaluation')
    receipt=sender.commit_event(event()); message=sender.pending()[0]
    ack=receiver.accept_message(message)
    with pytest.raises(RuntimeRefused,match='EVENT_CONFLICT'):
        receiver.accept_message({**message,'payload':{'key':'fixture','value':'other'}})
    with pytest.raises(RuntimeRefused,match='ACK_DENIED'):
        sender.acknowledge(receipt.event_id,receipt)
    assert len(sender.pending())==1


@pytest.mark.parametrize('key',['evaluation_status','armed','approved_plan','research_state'])
def test_fixture_message_cannot_change_authority(owned,key):
    _,leases=owned;store=api().open_store(leases['coordinator'],'coordinator')
    with pytest.raises(RuntimeRefused,match='TRANSITION_AUTHORITY_DENIED'):
        store.commit_event(event(payload={'key':key,'value':'VERIFIED'}))
    assert store.get_state(key) is None
    assert store.pending()==[]


def test_saved_snapshot_read_creates_no_files_and_preserves_live_durability(owned):
    from contextlib import closing
    import hashlib
    project, leases = owned
    store = api().open_store(leases['coordinator'], 'coordinator')
    store.commit_event(event(payload={'key': 'fixture.snapshot', 'value': 'RETAINED'}))
    destination = project.root_path / 'checkpoints' / 'standalone.sqlite'
    receipt = store.checkpoint(str(uuid4()), destination)
    before = set(destination.parent.iterdir())
    with closing(sqlite3.connect(destination.as_uri() + '?mode=ro', uri=True)) as reader:
        assert reader.execute('SELECT count(*) FROM events').fetchone()[0] == 1
        assert reader.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert set(destination.parent.iterdir()) == before
        assert reader.execute('PRAGMA journal_mode').fetchone()[0] == 'delete'
    assert set(destination.parent.iterdir()) == before
    assert hashlib.sha256(destination.read_bytes()).hexdigest() == receipt['sha256']
    assert store.inspect()['journal_mode'] == 'wal'
    assert store.inspect()['synchronous'] == 2
    assert store.get_state('fixture.snapshot') == 'RETAINED'