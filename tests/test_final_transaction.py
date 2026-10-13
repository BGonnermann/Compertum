"""Native transaction journal tests. Development evidence is explicitly stubbed."""
import json
from uuid import uuid4
import pytest
from test_evaluation_seals import owned, ledger, invalidate
from test_shortlist_ticket import pair_inputs, environment
from test_shortlist_freeze_journal import frozen_setup, freeze_now
from compertum.data.encoding import canonical
from compertum.runtime.errors import RuntimeRefused
from compertum.evaluation_seals import verify_seal_journal, reserve_seal_append
from compertum.consumption import verify_consumption_guard
from compertum.final_transaction import generated_recipe, recipe_sha256, reserve_final, final_receipt


@pytest.fixture
def ready(owned,pair_inputs,monkeypatch):
    pair_inputs[0]['holdout_manifest_sha256']=recipe_sha256()
    seals,p,ticket=frozen_setup.__wrapped__(owned,pair_inputs,monkeypatch)
    freeze_now(seals,p,ticket)
    return seals,p,ticket


def begin(seals,p,evaluation=None):
    evaluation=evaluation or str(uuid4())
    reserve_final(seals.test_storage,p['source']['seal_id'])
    return seals.handle(dict(operation='prepare_final',seal_id=p['source']['seal_id'],evaluation_id=evaluation))


def test_prepare_is_consumed_before_return_and_exact_checkpoint_resumes(ready):
    seals,p,ticket=ready;sid=p['source']['seal_id'];eid=str(uuid4())
    first=begin(seals,p,eid)
    assert first['status']=='CONSUMED_WAITING_FOR_BATCH'
    assert first['price_reads']==0 and not first['financial_accepted'] and not first['full_M3']
    guard=verify_consumption_guard(seals.project);record=guard['consumed'][sid]
    assert record['evaluation_id']==eid
    assert record['inputs']==dict(input_sha256=recipe_sha256(),protocol_sha256=json.loads(ticket.content)['protocol_sha256']['source'],shortlist_sha256=json.loads(ticket.content)['shortlist_sha256'])
    assert first==begin(seals,p,eid)
    assert verify_seal_journal(seals.project)['sequence']==6
    assert guard['sequence']==1
    assert json.loads(seals.store.conn.execute('SELECT body FROM consumption WHERE seal_id=?',(sid,)).fetchone()[0])==record


def test_old_database_mirror_cannot_reset_final_identity(ready):
    seals,p,ticket=ready;first=begin(seals,p)
    with seals.store.conn:
        seals.store.conn.execute('DELETE FROM evaluation_seal_events WHERE sequence=6')
        seals.store.conn.execute('DELETE FROM consumption')
    seals.store.close()
    # Reopen the same owned store; the filesystem journal remains current.
    from compertum.persistence import open_store
    from compertum.evaluation_seals import EvaluationSeals
    restored=EvaluationSeals(open_store(seals.store.lease,'evaluation'))
    restored.test_storage=seals.test_storage
    assert begin(restored,p,first['evaluation_id'])==first
    with pytest.raises(RuntimeRefused,match='FINAL_CONFLICT'):begin(restored,p)


@pytest.mark.parametrize('fault',['source_revoked','wheel_revoked','changed_runtime','lost_guard','lost_final_event','changed_recipe','wheel_authority','no_freeze'])
def test_final_refuses_uncertain_or_changed_authority(ready,monkeypatch,fault):
    from compertum import evaluation_seals as mod
    from compertum import final_transaction as final
    seals,p,ticket=ready;first=begin(seals,p);sid=p['source']['seal_id'];eid=first['evaluation_id']
    if fault.endswith('revoked'):invalidate(seals,p['source' if fault=='source_revoked' else 'wheel']['seal_id'],'INPUT_CHANGED')
    elif fault=='changed_runtime':monkeypatch.setattr(mod,'runtime_identity',lambda:{})
    elif fault=='lost_guard':(seals.project.root_path/'state/evaluation-consumption/head.json').rename(seals.project.root_path/'preserved-consumption-head.json')
    elif fault=='lost_final_event':(seals.project.root_path/'state/evaluation-seals/00000006.json').rename(seals.project.root_path/'preserved-final-event.json')
    elif fault=='changed_recipe':
        from compertum.data.errors import DataError
        def unavailable(pin):raise DataError('GENERATED_RECIPE_UNVERIFIED')
        monkeypatch.setattr(final,'recipe_for_pin',unavailable)
    elif fault=='wheel_authority':sid=p['wheel']['seal_id']
    else:
        # A wheel seal was admitted but never carries a source freeze.
        sid=p['wheel']['seal_id']
    with pytest.raises(RuntimeRefused):seals.handle(dict(operation='prepare_final',seal_id=sid,evaluation_id=eid))


def test_consumption_mirror_failure_never_returns_permission_and_recovers(ready):
    seals,p,ticket=ready;eid=str(uuid4())
    seals.store.conn.execute("CREATE TRIGGER refuse_consumption BEFORE INSERT ON consumption BEGIN SELECT RAISE(IGNORE); END")
    with pytest.raises(RuntimeRefused,match='FINAL_CONSUMPTION_UNVERIFIED'):begin(seals,p,eid)
    assert verify_consumption_guard(seals.project)['sequence']==1
    assert verify_seal_journal(seals.project)['sequence']==6
    seals.store.conn.execute('DROP TRIGGER refuse_consumption')
    assert begin(seals,p,eid)['evaluation_id']==eid
    assert verify_consumption_guard(seals.project)['sequence']==1


def test_prepare_mirror_failure_precedes_consumption_and_exact_retry(ready):
    seals,p,ticket=ready;eid=str(uuid4())
    seals.store.conn.execute("CREATE TRIGGER refuse_final BEFORE INSERT ON evaluation_seal_events WHEN NEW.sequence=6 BEGIN SELECT RAISE(ABORT,'fixture'); END")
    with pytest.raises(RuntimeRefused,match='SEAL_MIRROR_UNVERIFIED'):begin(seals,p,eid)
    assert verify_consumption_guard(seals.project)['sequence']==0
    assert verify_seal_journal(seals.project)['sequence']==6
    seals.store.conn.execute('DROP TRIGGER refuse_final')
    assert begin(seals,p,eid)['evaluation_id']==eid


def test_capacity_is_checked_before_consumption(ready,monkeypatch):
    from compertum import evaluation_seals as mod
    seals,p,ticket=ready;monkeypatch.setattr(mod,'MAX_EVENTS',8)
    with pytest.raises(RuntimeRefused,match='SEAL_COUNT_BOUND'):begin(seals,p)
    assert verify_consumption_guard(seals.project)['sequence']==0
    assert verify_seal_journal(seals.project)['sequence']==5


def test_consumption_storage_must_be_reserved_before_prepare(ready):
    seals,p,ticket=ready
    reserve_seal_append(seals.test_storage)
    with pytest.raises(RuntimeRefused,match='SEAL_STORAGE_UNRESERVED'):
        seals.handle(dict(operation='prepare_final',seal_id=p['source']['seal_id'],evaluation_id=str(uuid4())))
    assert verify_consumption_guard(seals.project)['sequence']==0
    assert verify_seal_journal(seals.project)['sequence']==5


def test_recipe_is_constant_bounded_and_has_no_external_input_surface():
    value=generated_recipe()
    assert value['source']=='BUILTIN_GENERATED_ONLY' and value['years']==[2024,2025]
    assert value['coverage']=='PARTIAL_FIXTURE_UNQUALIFIED'
    assert len(canonical(value))<4096
    value['years'].append(2026)
    assert generated_recipe()['years']==[2024,2025]



def test_empty_shortlist_completes_once_with_committed_evidence_and_no_prices(owned,pair_inputs,monkeypatch):
    from test_shortlist_owner import make_committed
    from compertum import final_transaction as final
    pair_inputs[0]['holdout_manifest_sha256']=recipe_sha256()
    seals,p,ticket,states,reviews=make_committed(owned,pair_inputs,monkeypatch)
    freeze_now(seals,p,ticket);eid=str(uuid4())
    first=begin(seals,p,eid)
    assert first['status']=='NO_CANDIDATE_QUALIFIES'
    assert first['result']['selected']==[] and first['result']['scoring_units']==first['result']['price_reads']==0
    assert first['preparation_sequence']==6 and first['completion_sequence']==7
    with seals.store.conn:
        seals.store.conn.execute('DELETE FROM evaluation_seal_events WHERE sequence>=6')
        seals.store.conn.execute('DELETE FROM consumption')
    assert begin(seals,p,eid)==first
    assert seals.handle(dict(operation='inspect_final',seal_id=p['source']['seal_id']))==first
    assert verify_consumption_guard(seals.project)['sequence']==1
    assert verify_seal_journal(seals.project)['sequence']==7
    with pytest.raises(RuntimeRefused,match='FINAL_CONFLICT'):begin(seals,p)
    # The generated numerical module is never imported for an empty selection.
    import sys
    assert 'compertum.modeling.generated_final' not in sys.modules


def test_consumption_head_published_before_mirror_fault_recovers_original(ready,monkeypatch):
    seals,p,ticket=ready;eid=str(uuid4());original=seals.store.mirror_consumption
    def crash(record):raise OSError('injected after durable consumption')
    monkeypatch.setattr(seals.store,'mirror_consumption',crash)
    with pytest.raises(RuntimeRefused,match='CONSUMPTION_UNVERIFIED'):begin(seals,p,eid)
    assert verify_consumption_guard(seals.project)['consumed'][p['source']['seal_id']]['evaluation_id']==eid
    monkeypatch.setattr(seals.store,'mirror_consumption',original)
    assert begin(seals,p,eid)['evaluation_id']==eid


def test_partial_consumption_event_never_restarts_as_unused(ready,monkeypatch):
    from compertum import consumption
    seals,p,ticket=ready;eid=str(uuid4())
    def partial(path,raw):path.write_bytes(raw[:30]);raise OSError('injected partial')
    monkeypatch.setattr(consumption,'_flush_event',partial)
    with pytest.raises(RuntimeRefused,match='CONSUMPTION_UNVERIFIED'):begin(seals,p,eid)
    assert verify_seal_journal(seals.project)['sequence']==6
    assert verify_consumption_guard(seals.project)['status']=='EVALUATION_COMPROMISED'
    with pytest.raises(RuntimeRefused):begin(seals,p,eid)


def test_matching_consumption_without_retained_initial_checkpoint_is_denied(ready):
    from compertum.consumption import consume_once
    seals,p,ticket=ready;v=json.loads(ticket.content);eid=str(uuid4())
    consume_once(seals.store.lease,p['source']['seal_id'],eid,dict(input_sha256=recipe_sha256(),protocol_sha256=v['protocol_sha256']['source'],shortlist_sha256=v['shortlist_sha256']))
    with pytest.raises(RuntimeRefused,match='FINAL_CHECKPOINT_MISSING'):begin(seals,p,eid)
    assert verify_seal_journal(seals.project)['sequence']==5


def test_rehashed_initial_checkpoint_change_compromises_journal(ready):
    import hashlib
    seals,p,ticket=ready;first=begin(seals,p)
    root=seals.project.root_path/'state/evaluation-seals';path=root/'00000006.json'
    item=json.loads(path.read_bytes());plan=item['record']['plan']
    plan['checkpoint']['position']='AFTER_BATCH'
    item['record']['plan_sha256']=hashlib.sha256(canonical(plan)).hexdigest()
    raw=canonical(item);path.write_bytes(raw)
    (root/'head.json').write_bytes(canonical(dict(sequence=6,sha256=hashlib.sha256(raw).hexdigest())))
    assert verify_seal_journal(seals.project)['status']=='SEAL_JOURNAL_COMPROMISED'
    with pytest.raises(RuntimeRefused):begin(seals,p,first['evaluation_id'])



@pytest.mark.parametrize('fault',['missing_grant','advanced_sequence'])
def test_retry_requires_current_consumption_reservation(ready,fault):
    from compertum.consumption import consume_once
    seals,p,ticket=ready;eid=str(uuid4())
    seals.store.conn.execute("CREATE TRIGGER stop_prepare BEFORE INSERT ON evaluation_seal_events WHEN NEW.sequence=6 BEGIN SELECT RAISE(ABORT,'fixture'); END")
    with pytest.raises(RuntimeRefused,match='SEAL_MIRROR_UNVERIFIED'):begin(seals,p,eid)
    seals.store.conn.execute('DROP TRIGGER stop_prepare')
    if fault=='missing_grant':
        with seals.test_storage.store.conn:seals.test_storage.store.conn.execute("DELETE FROM reservations WHERE path='state/evaluation-consumption/00000001.json'")
    else:
        consume_once(seals.store.lease,str(uuid4()),str(uuid4()),dict(input_sha256='a'*64,protocol_sha256='b'*64,shortlist_sha256='c'*64))
    prior=verify_consumption_guard(seals.project)['sequence']
    with pytest.raises(RuntimeRefused,match='SEAL_STORAGE_UNRESERVED'):
        seals.handle(dict(operation='prepare_final',seal_id=p['source']['seal_id'],evaluation_id=eid))
    assert verify_consumption_guard(seals.project)['sequence']==prior
    assert begin(seals,p,eid)['evaluation_id']==eid


def test_silently_ignored_prepare_mirror_cannot_consume(ready):
    seals,p,ticket=ready;eid=str(uuid4())
    seals.store.conn.execute("CREATE TRIGGER ignore_prepare BEFORE INSERT ON evaluation_seal_events WHEN NEW.sequence=6 BEGIN SELECT RAISE(IGNORE); END")
    with pytest.raises(RuntimeRefused,match='SEAL_MIRROR_UNVERIFIED'):begin(seals,p,eid)
    assert verify_consumption_guard(seals.project)['sequence']==0
    assert verify_seal_journal(seals.project)['sequence']==6
    seals.store.conn.execute('DROP TRIGGER ignore_prepare')
    assert begin(seals,p,eid)['evaluation_id']==eid


def test_silently_ignored_empty_completion_returns_no_success(owned,pair_inputs,monkeypatch):
    from test_shortlist_owner import make_committed
    pair_inputs[0]['holdout_manifest_sha256']=recipe_sha256()
    seals,p,ticket,states,reviews=make_committed(owned,pair_inputs,monkeypatch)
    freeze_now(seals,p,ticket);eid=str(uuid4())
    seals.store.conn.execute("CREATE TRIGGER ignore_complete BEFORE INSERT ON evaluation_seal_events WHEN NEW.sequence=7 BEGIN SELECT RAISE(IGNORE); END")
    with pytest.raises(RuntimeRefused,match='SEAL_MIRROR_UNVERIFIED'):begin(seals,p,eid)
    assert verify_consumption_guard(seals.project)['sequence']==1
    assert verify_seal_journal(seals.project)['sequence']==7
    seals.store.conn.execute('DROP TRIGGER ignore_complete')
    assert begin(seals,p,eid)['status']=='NO_CANDIDATE_QUALIFIES'
    assert verify_seal_journal(seals.project)['sequence']==7



@pytest.mark.parametrize('version',[1,2])
def test_retained_final_journal_resolves_presealed_recipe_not_current_default(owned,pair_inputs,monkeypatch,version):
    from test_shortlist_owner import make_committed
    from compertum import final_transaction as final
    from compertum.final_recipe import recipe,recipe_hash
    pair_inputs[0]['holdout_manifest_sha256']=recipe_hash(version=version)
    seals,p,ticket,states,reviews=make_committed(owned,pair_inputs,monkeypatch)
    freeze_now(seals,p,ticket);eid=str(uuid4());sid=p['source']['seal_id']
    first=begin(seals,p,eid)
    path=seals.project.root_path/'state/evaluation-seals/00000006.json'
    retained=path.read_bytes();plan=json.loads(retained)['record']['plan']
    assert plan['recipe']==recipe(version=version)
    assert plan['inputs']['input_sha256']==recipe_hash(version=version)
    assert plan['schema']=='synthetic-final-plan-v1'
    assert plan['checkpoint']==dict(schema='synthetic-final-checkpoint-v1',position='BEFORE_BATCH',price_reads=0)
    assert first['status']=='NO_CANDIDATE_QUALIFIES'
    # A changed current default must not redefine retained v1 or v2 evidence.
    monkeypatch.setattr(final,'generated_recipe',lambda:recipe(version=2 if version==1 else 1))
    monkeypatch.setattr(final,'recipe_sha256',lambda:recipe_hash(version=2 if version==1 else 1))
    journal=verify_seal_journal(seals.project)
    assert journal['status']=='VERIFIED' and journal['sequence']==7
    assert begin(seals,p,eid)==first
    assert path.read_bytes()==retained
