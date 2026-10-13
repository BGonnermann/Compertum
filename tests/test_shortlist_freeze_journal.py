"""Native seal journal tests with explicit committed-review authority stubs.

These exercise append/replay and refusal boundaries, not campaign acceptance.
"""
import json
from uuid import uuid4
import pytest
from test_evaluation_seals import owned,ledger,create,invalidate
from test_shortlist_ticket import inputs,pair_inputs,environment
from compertum.data.encoding import canonical
from compertum.data.errors import DataError
from compertum.evaluation_protocol import build_protocol
from compertum.evaluation_seals import reserve_seal_append,verify_seal_journal
from compertum.runtime.errors import RuntimeRefused
from compertum.shortlist_ticket import build_ticket


@pytest.fixture
def frozen_setup(owned,pair_inputs,monkeypatch):
    import compertum.evaluation_seals as module
    import compertum.clean_registration as registration
    import compertum.development_seals as admission
    import compertum.shortlist_freeze as freeze
    args,_=pair_inputs;args['project_id']=owned[0].project_id
    values=inputs(pair_inputs,monkeypatch);p=values['pair'];seals=ledger(owned)
    monkeypatch.setattr(module,'runtime_identity',lambda:p['runtime'])
    monkeypatch.setattr(registration,'owner_protocol',lambda *a:None)
    monkeypatch.setattr(admission,'owner_ticket',lambda *a,**k:None)
    for lane in ('source','wheel'):
        protocol=build_protocol(development_run_id=p[lane]['run_id'],development_sha256='a'*64,data_manifest_sha256=p['data_manifest_sha256'],holdout_manifest_sha256=p['holdout_manifest_sha256'],runtime=p['runtime'],clean_pair=dict(record=p,sha256=values['pair_sha256'],lane=lane))
        values['protocol_sha256'][lane]=protocol.sha256
        sid=p[lane]['seal_id'];create(seals,sid,protocol.content,protocol.sha256)
        reserve_seal_append(seals.test_storage);seals.admit(sid,'e'*64)
    ticket=build_ticket(**values)
    monkeypatch.setattr(freeze,'owner_ticket',lambda *a,**k:json.loads(ticket.content))
    return seals,p,ticket


def freeze_now(seals,p,ticket):
    reserve_seal_append(seals.test_storage)
    return seals.handle(dict(operation='freeze',seal_id=p['source']['seal_id'],ticket_sha256=ticket.sha256))


def test_freeze_is_distinct_write_once_receipt_and_admission_unchanged(frozen_setup):
    seals,p,ticket=frozen_setup;sid=p['source']['seal_id'];admission=seals.inspect(sid)
    first=freeze_now(seals,p,ticket)
    assert first==freeze_now(seals,p,ticket)==seals.handle(dict(operation='inspect_shortlist',seal_id=sid))
    assert first['schema']=='synthetic-shortlist-receipt-v1' and first['status']=='FROZEN'
    assert first['shortlist_sha256']==json.loads(ticket.content)['shortlist_sha256'] and first['financial_accepted'] is False
    assert seals.inspect(sid)==admission and verify_seal_journal(seals.project)['sequence']==5


def test_restored_old_mirror_recovers_frozen_receipt(frozen_setup):
    seals,p,ticket=frozen_setup;first=freeze_now(seals,p,ticket)
    with seals.store.conn:seals.store.conn.execute('DELETE FROM evaluation_seal_events WHERE sequence=5')
    assert seals.inspect_shortlist(p['source']['seal_id'])==first
    assert seals.store.conn.execute('SELECT count(*) FROM evaluation_seal_events').fetchone()[0]==5


def test_event_before_mirror_failure_does_not_allow_second_freeze(frozen_setup):
    seals,p,ticket=frozen_setup
    seals.store.conn.execute("CREATE TRIGGER reject_freeze BEFORE INSERT ON evaluation_seal_events WHEN NEW.sequence=5 BEGIN SELECT RAISE(ABORT,'fixture'); END")
    with pytest.raises(RuntimeRefused,match='SEAL_MIRROR_UNVERIFIED'):freeze_now(seals,p,ticket)
    evidence=verify_seal_journal(seals.project);assert evidence['sequence']==5
    seals.store.conn.execute('DROP TRIGGER reject_freeze')
    assert freeze_now(seals,p,ticket)['freeze_sequence']==5
    assert verify_seal_journal(seals.project)['sequence']==5


@pytest.mark.parametrize('fault',['wheel','changed_ticket','counterpart_revoked','source_revoked','consumed','missing_committed_ticket','lost_journal'])
def test_freeze_refuses_missing_or_changed_authority(frozen_setup,monkeypatch,fault):
    from compertum import shortlist_freeze
    from compertum.consumption import consume_once
    seals,p,ticket=frozen_setup;sid=p['source']['seal_id'];freeze_now(seals,p,ticket)
    pin=ticket.sha256
    if fault=='wheel':sid=p['wheel']['seal_id']
    elif fault=='changed_ticket':pin='f'*64
    elif fault in ('counterpart_revoked','source_revoked'):invalidate(seals,p['wheel' if fault=='counterpart_revoked' else 'source']['seal_id'],'INPUT_CHANGED')
    elif fault=='consumed':consume_once(seals.store.lease,sid,str(uuid4()),dict(input_sha256='a'*64,protocol_sha256=json.loads(ticket.content)['protocol_sha256']['source'],shortlist_sha256=json.loads(ticket.content)['shortlist_sha256']))
    elif fault=='missing_committed_ticket':
        def missing(*a,**k):raise DataError('SHORTLIST_TICKET_UNVERIFIED')
        monkeypatch.setattr(shortlist_freeze,'owner_ticket',missing)
    else:(seals.project.root_path/'state/evaluation-seals/head.json').rename(seals.project.root_path/'preserved-head.json')
    with pytest.raises(RuntimeRefused):seals.handle(dict(operation='freeze',seal_id=sid,ticket_sha256=pin))


def test_pending_freeze_reserves_capacity_without_consuming_invalidation_slot(frozen_setup,monkeypatch):
    import compertum.evaluation_seals as module
    seals,p,ticket=frozen_setup
    monkeypatch.setattr(module,'MAX_EVENTS',6)
    with pytest.raises(RuntimeRefused,match='SEAL_COUNT_BOUND'):freeze_now(seals,p,ticket)
    assert verify_seal_journal(seals.project)['sequence']==4
    monkeypatch.setattr(module,'MAX_EVENTS',7)
    assert freeze_now(seals,p,ticket)['status']=='FROZEN'
    invalidate(seals,p['source']['seal_id'],'INPUT_CHANGED');invalidate(seals,p['wheel']['seal_id'],'INPUT_CHANGED')
    assert verify_seal_journal(seals.project)['sequence']==7
    assert seals.inspect_shortlist(p['source']['seal_id'])['status']=='INVALIDATED'


def test_new_seal_cannot_spend_a_pending_source_freeze_slot(frozen_setup,monkeypatch):
    import compertum.evaluation_seals as module
    seals,p,ticket=frozen_setup;monkeypatch.setattr(module,'MAX_EVENTS',8)
    protocol=build_protocol(development_run_id=str(uuid4()),development_sha256='a'*64,data_manifest_sha256='b'*64,holdout_manifest_sha256='c'*64,runtime=p['runtime'])
    with pytest.raises(RuntimeRefused,match='SEAL_COUNT_BOUND'):create(seals,str(uuid4()),protocol.content,protocol.sha256)
    assert verify_seal_journal(seals.project)['sequence']==4
