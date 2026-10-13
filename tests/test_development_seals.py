"""Native owner-held seal admission; earlier diagnostics cannot be relabeled."""
import json
from uuid import uuid4
import pytest
from test_persistence import owned
from test_storage import manager
from helpers.saved_campaign_fixture import campaign_folds
from compertum.storage import reserve_runtime_paths
from compertum.persistence import open_store
from compertum.evaluation_seals import EvaluationSeals,reserve_seal_append,verify_seal_journal
from compertum.development_seals import create_campaign,check_campaign_seal
from compertum.simulation.runs import SavedRuns
from compertum.data.errors import DataError
from compertum.runtime.errors import RuntimeRefused


def setup(owned):
    storage=manager(owned);reserve_runtime_paths(storage)
    seals=EvaluationSeals(open_store(owned[1]['evaluation'],'evaluation'))
    return SavedRuns(storage),seals


def create(runs,seals,run=None,seal=None,**kwargs):
    return create_campaign(runs,run or str(uuid4()),campaign_folds(),seal_id=seal or str(uuid4()),
        evaluation=seals,data_manifest_sha256='a'*64,holdout_manifest_sha256='b'*64,**kwargs)


def test_fresh_campaign_requires_and_retains_owner_admission(owned):
    runs,seals=setup(owned);run,sid=str(uuid4()),str(uuid4());created=create(runs,seals,run,sid)
    state=runs._load(run);binding=check_campaign_seal(runs.store,state)
    assert state['protocol_seal']==binding and created['protocol_status']=='SEALED_SYNTHETIC_DEVELOPMENT'
    assert seals.inspect(sid)['development_admitted'] is True and verify_seal_journal(owned[0])['sequence']==2
    assert created==create(runs,seals,run,sid)
    runs.control(run,str(uuid4()),'resume');result=runs.step(run)
    assert result['completed_units']==1 and result['financial_acceptance']=='UNVERIFIED'
    assert len(verify_seal_journal(owned[0])['events'])==2


@pytest.mark.parametrize('started',[False,True])
def test_existing_diagnostic_cannot_be_retroactively_sealed(owned,started):
    runs,seals=setup(owned);run=str(uuid4());runs.create_campaign(run,campaign_folds())
    if started:runs.control(run,str(uuid4()),'resume');runs.step(run)
    before=runs._load(run)
    with pytest.raises(DataError,match='RUN_ALREADY_UNSEALED'):create(runs,seals,run)
    assert runs._load(run)==before and verify_seal_journal(owned[0])['sequence']==0
    assert runs.summary(run)['protocol_status']=='UNSEALED_DIAGNOSTIC'


@pytest.mark.parametrize('boundary',['before_create','after_create','after_admit'])
def test_remote_failure_retries_original_ticket_and_receipt(owned,monkeypatch,boundary):
    runs,seals=setup(owned);run,sid=str(uuid4()),str(uuid4());handle=seals.handle
    def crash(payload):
        if boundary=='before_create' and payload['operation']=='create':raise OSError('fixture before create')
        result=handle(payload)
        if payload['operation']=={'after_create':'create','after_admit':'admit'}.get(boundary):raise OSError('fixture lost reply')
        return result
    monkeypatch.setattr(seals,'handle',crash)
    with pytest.raises(DataError,match='SEAL_ADMISSION_UNVERIFIED'):create(runs,seals,run,sid)
    assert runs.store.conn.execute('SELECT 1 FROM baseline_runs WHERE run_id=?',(run,)).fetchone() is None
    with pytest.raises(DataError,match='SEAL_ADMISSION_REQUIRED'):runs.create_campaign(run,campaign_folds())
    old=verify_seal_journal(owned[0]);monkeypatch.setattr(seals,'handle',handle)
    result=create(runs,seals,run,sid);assert result['state']=='PAUSED'
    fresh=verify_seal_journal(owned[0]);assert fresh['sequence']==2
    assert fresh['events'][:len(old['events'])]==old['events']


def test_receipt_committed_before_registration_can_resume(owned,monkeypatch):
    runs,seals=setup(owned);run,sid=str(uuid4()),str(uuid4());register=runs._register
    monkeypatch.setattr(runs,'_register',lambda *a,**k:(_ for _ in ()).throw(OSError('fixture before register')))
    with pytest.raises(OSError):create(runs,seals,run,sid)
    assert seals.inspect(sid)['development_admitted']
    monkeypatch.setattr(runs,'_register',register);assert create(runs,seals,run,sid)['state']=='PAUSED'
    assert verify_seal_journal(owned[0])['sequence']==2


@pytest.mark.parametrize('mutation',['state_binding','receipt','ticket_hash','mirror','journal','consumption'])
def test_missing_or_changed_binding_cannot_dispatch(owned,mutation):
    runs,seals=setup(owned);run,sid=str(uuid4()),str(uuid4());create(runs,seals,run,sid)
    runs.control(run,str(uuid4()),'resume')
    if mutation=='state_binding':
        state=runs._load(run);state.pop('protocol_seal')
        with runs.store.conn:runs._save(state,'INJECTED_REMOVAL')
    elif mutation=='receipt':
        with runs.store.conn:runs.store.conn.execute("UPDATE sealed_campaigns SET receipt='{}' WHERE run_id=?",(run,))
    elif mutation=='ticket_hash':
        with runs.store.conn:runs.store.conn.execute("UPDATE sealed_campaigns SET sha256=? WHERE run_id=?",('f'*64,run))
    elif mutation=='mirror':
        with seals.store.conn:seals.store.conn.execute('DELETE FROM evaluation_seal_events WHERE sequence=2')
    elif mutation=='consumption':(owned[0].root_path/'state/evaluation-consumption/head.json').rename(owned[0].root_path/'preserved-consumption-head.json')
    else:(owned[0].root_path/'state/evaluation-seals/head.json').rename(owned[0].root_path/'preserved-seal-head.json')
    with pytest.raises((DataError,RuntimeRefused)):runs.step(run)
    assert runs.summary(run)['attempts']==[]


def test_invalidation_after_prepare_denies_begin_without_attempt(owned):
    runs,seals=setup(owned);run,sid=str(uuid4()),str(uuid4());create(runs,seals,run,sid);runs.control(run,str(uuid4()),'resume')
    prepared=runs.prepare_campaign(run);reserve_seal_append(runs.storage);seals.invalidate(sid,'POLICY_CHANGED')
    with pytest.raises(DataError,match='SEAL_INVALIDATED'):runs.begin_campaign(run,prepared)
    assert runs.summary(run)['attempts']==[]


def test_omitted_binding_cannot_take_existing_registration_shortcut(owned):
    runs,seals=setup(owned);run,sid=str(uuid4()),str(uuid4());create(runs,seals,run,sid)
    with pytest.raises(DataError,match='SEAL_ADMISSION_REQUIRED'):runs.create_campaign(run,campaign_folds())
    assert create(runs,seals,run,sid)['state']=='PAUSED'


def test_missing_ticket_with_surviving_admission_cannot_become_diagnostic(owned):
    runs,seals=setup(owned);run,sid=str(uuid4()),str(uuid4());create(runs,seals,run,sid)
    with runs.store.conn:runs.store.conn.execute('DELETE FROM sealed_campaigns WHERE run_id=?',(run,))
    state=runs._load(run);state.pop('protocol_seal')
    with runs.store.conn:runs._save(state,'INJECTED_DOWNGRADE')
    with pytest.raises(DataError,match='SEAL_ADMISSION_REQUIRED'):runs.create_campaign(run,campaign_folds())


def test_impostor_owner_cannot_commit_a_ticket(owned):
    runs,seals=setup(owned)
    class Impostor:
        def handle(self,payload):return {'development_admitted':True}
    with pytest.raises(DataError,match='SEAL_OWNER_UNVERIFIED'):create(runs,Impostor())
    assert verify_seal_journal(owned[0])['sequence']==0


def test_owner_admit_requires_real_coordinator_ticket(owned):
    from test_evaluation_seals import protocol
    runs,seals=setup(owned);p=protocol();sid=str(uuid4());reserve_seal_append(runs.storage);seals.create(sid,p.content,p.sha256)
    reserve_seal_append(runs.storage)
    with pytest.raises(RuntimeRefused,match='DEVELOPMENT_TICKET_UNVERIFIED'):
        seals.handle({'operation':'admit','seal_id':sid,'ticket_sha256':'f'*64})
    assert not seals.inspect(sid)['development_admitted'] and verify_seal_journal(owned[0])['sequence']==1


def test_admission_keeps_room_for_irreversible_invalidation(owned,monkeypatch):
    import compertum.evaluation_seals as module
    runs,seals=setup(owned);monkeypatch.setattr(module,'MAX_EVENTS',2);run,sid=str(uuid4()),str(uuid4())
    with pytest.raises(DataError,match='SEAL_ADMISSION_UNVERIFIED'):create(runs,seals,run,sid)
    assert not seals.inspect(sid)['development_admitted']
    reserve_seal_append(runs.storage);assert seals.invalidate(sid,'OPERATOR_INVALIDATED')['status']=='INVALIDATED'
    assert verify_seal_journal(owned[0])['sequence']==2

@pytest.mark.parametrize('mutation',['run','protocol','input','runtime','receipt_copy','provider_kind'])
def test_changed_immutable_pins_are_denied(owned,mutation):
    import hashlib
    from compertum.data.encoding import canonical
    runs,seals=setup(owned);run,sid=str(uuid4()),str(uuid4());create(runs,seals,run,sid)
    state=runs._load(run)
    if mutation=='run':state['run_id']=str(uuid4())
    elif mutation=='protocol':state['protocol_seal']['protocol_sha256']='f'*64
    elif mutation=='input':state['request_sha256']='f'*64
    elif mutation=='runtime':state['identity']['package_sha256']='f'*64
    elif mutation=='provider_kind':state['input_kind']='provider-diagnostic'
    else:
        other=str(uuid4());create(runs,seals,other)
        receipt=runs.store.conn.execute('SELECT receipt FROM sealed_campaigns WHERE run_id=?',(other,)).fetchone()[0]
        with runs.store.conn:runs.store.conn.execute('UPDATE sealed_campaigns SET receipt=? WHERE run_id=?',(receipt,run))
    with pytest.raises(DataError):check_campaign_seal(runs.store,state)


def test_other_seals_do_not_revoke_current_admission(owned):
    runs,seals=setup(owned);run,sid=str(uuid4()),str(uuid4());create(runs,seals,run,sid)
    original=check_campaign_seal(runs.store,runs._load(run));other=str(uuid4());create(runs,seals,seal=other)
    reserve_seal_append(runs.storage);seals.invalidate(other,'OPERATOR_INVALIDATED')
    assert check_campaign_seal(runs.store,runs._load(run))==original


def test_mirror_failure_retains_remote_commit_and_recovers_original_ticket(owned,monkeypatch):
    runs,seals=setup(owned);run,sid=str(uuid4()),str(uuid4());mirror=seals._mirror
    def fail(evidence):
        if any(r['admission'] for r in evidence['seals'].values()):raise RuntimeRefused('SEAL_MIRROR_UNVERIFIED')
        return mirror(evidence)
    monkeypatch.setattr(seals,'_mirror',fail)
    with pytest.raises(DataError,match='SEAL_ADMISSION_UNVERIFIED'):create(runs,seals,run,sid)
    old=verify_seal_journal(owned[0]);assert old['sequence']==2
    monkeypatch.setattr(seals,'_mirror',mirror);assert create(runs,seals,run,sid)['state']=='PAUSED'
    assert verify_seal_journal(owned[0])==old


def test_input_publication_failure_never_admits_an_unsealed_replacement(owned,monkeypatch):
    runs,seals=setup(owned);run,sid=str(uuid4()),str(uuid4());publish=runs._publish
    def failed(*args):
        publish(*args);raise OSError('fixture lost publication reply')
    monkeypatch.setattr(runs,'_publish',failed)
    with pytest.raises(DataError,match='RUN_PREPARATION_FAILED'):create(runs,seals,run,sid)
    assert runs.summary(run)['state']=='FAILED' and seals.inspect(sid)['development_admitted']
    with pytest.raises(DataError,match='SEAL_ADMISSION_REQUIRED'):runs.create_campaign(run,campaign_folds())
    monkeypatch.setattr(runs,'_publish',publish)
    with pytest.raises(DataError,match='RUN_INPUT_INCOMPLETE'):create(runs,seals,run,sid)
    assert verify_seal_journal(owned[0])['sequence']==2


def test_durable_compromise_marker_blocks_acceptance(owned):
    from compertum.data.encoding import canonical
    runs,seals=setup(owned);run=str(uuid4());create(runs,seals,run)
    with seals.store.conn:seals.store.conn.execute('INSERT INTO state VALUES(?,?)',('evaluation_status',canonical('EVALUATION_COMPROMISED').decode()))
    with pytest.raises(DataError,match='SEAL_MIRROR_UNVERIFIED'):check_campaign_seal(runs.store,runs._load(run))


def test_owner_rejects_admission_after_diagnostic_registration(owned):
    from test_evaluation_seals import protocol
    runs,seals=setup(owned);run,sid=str(uuid4()),str(uuid4())
    # Ticket is prepared normally; injection stops before any owner effect.
    handle=seals.handle;seals.handle=lambda payload:(_ for _ in ()).throw(OSError('fixture pending ticket'))
    with pytest.raises(DataError):create(runs,seals,run,sid)
    seals.handle=handle
    ticket=runs.store.conn.execute('SELECT protocol,sha256 FROM sealed_campaigns WHERE run_id=?',(run,)).fetchone()
    import hashlib
    reserve_seal_append(runs.storage);seals.create(sid,ticket[0].encode(),hashlib.sha256(ticket[0].encode()).hexdigest())
    with runs.store.conn:runs.store.conn.execute('INSERT INTO baseline_runs VALUES(?,?)',(run,'{}'))
    reserve_seal_append(runs.storage)
    with pytest.raises(RuntimeRefused,match='DEVELOPMENT_TICKET_UNVERIFIED'):seals.admit(sid,ticket[1])
    assert verify_seal_journal(owned[0])['sequence']==1


def test_surviving_consumption_guard_prevents_unused_project_inference(owned):
    from compertum.development_seals import _evidence
    runs,seals=setup(owned)
    seals.store.close()
    root=owned[0].root_path
    (root/'state/evaluation-seals').rename(root/'preserved-seal-journal')
    (root/'state/evaluation.sqlite').rename(root/'preserved-evaluation.sqlite')
    assert (root/'state/evaluation-consumption').is_dir()
    with pytest.raises(DataError,match='SEAL_JOURNAL_COMPROMISED'):_evidence(owned[0])
