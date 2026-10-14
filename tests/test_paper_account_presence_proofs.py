"""Native stores/DPAPI; simulated origins, clocks and reserve capacity."""
import hashlib,json,pickle
import pytest
from compertum.runtime.errors import RuntimeRefused
from test_execution_health import pair,connect
from test_paper_read_owner import owner
from test_paper_read_publication import publication,launch
from test_paper_account_binding import invented_paper_origin,propose,confirm,call
from test_paper_presence import account,packet,acknowledge,inspect
from test_paper_account_context import context


def presence_proof(o,r):
    return o.a._presence._prepare_proof(subject='a'*64,presence_id=r['presence_id'])


@pytest.mark.parametrize('kind',['account','presence'])
def test_private_proof_is_single_use_and_grants_no_authority(account,kind):
    o,_,_=account;_,r=acknowledge(account);c=context(account)
    p=c._prepare_proof() if kind=='account' else presence_proof(o,r)
    with pytest.raises(RuntimeRefused):pickle.dumps(p)
    before=o.a.db.total_changes
    p._verify()
    assert o.a.db.total_changes==before
    with pytest.raises(RuntimeRefused):p._verify()
    assert c.diagnostic()['transport_authorized'] is False
    assert inspect(o,r)['order_admission']=='BLOCKED'


@pytest.mark.parametrize('kind',['account','presence'])
def test_final_proof_does_not_repeat_decryption_diagnostic_or_health_callbacks(account,monkeypatch,kind):
    import compertum.runtime.paper_account_context as ac
    import compertum.runtime.paper_presence as pr
    o,_,_=account;_,r=acknowledge(account);c=context(account)
    p=c._prepare_proof() if kind=='account' else presence_proof(o,r)
    def forbidden(*args,**kwargs):raise AssertionError('Callback after final proof boundary')
    for module in (ac,pr):
        for name in ('load_paper_slot','open_paper_credentials','open_read_evidence','_reject_reflections'):
            monkeypatch.setattr(module,name,forbidden)
    monkeypatch.setattr(type(o.e),'status',forbidden)
    monkeypatch.setattr(type(o.a._preflight),'diagnostic',forbidden)
    monkeypatch.setattr(ac,'original_opening',forbidden)
    p._verify()


@pytest.mark.parametrize('fault',['artifact','first_artifact','slot','alias','history','context_close','context_replace'])
def test_presence_callbacks_cannot_invalidate_an_already_prepared_account_proof(account,monkeypatch,fault):
    import compertum.runtime.paper_presence as module
    from compertum.runtime.paper_credential_slot import SLOT_PATH
    from test_paper_account_presence_integrity import replacement_slot
    o,pub,p=account;first=pub._route(p['packet_id'])['publication']['manifest']
    if fault=='first_artifact':
        later=launch((o,pub,None))
        for _ in range(10):pub.tick()
        proposal=call(pub,later,'account_propose');confirm(pub,later,proposal)
        assert later['packet_id']!=p['packet_id'];p=later;account=(o,pub,p)
    _,r=acknowledge(account);c=context(account);proof=c._prepare_proof()
    path=o.manager.root/(SLOT_PATH if fault=='slot' else (first if fault=='first_artifact' else pub._route(p['packet_id'])['publication']['manifest'])['path'])
    original=path.read_bytes();replacement=replacement_slot(o)
    key='paper_account_alias:fixture' if fault=='alias' else 'fake_attempt_guard_head'
    row=o.a.db.execute('SELECT value FROM state WHERE key=?',(key,)).fetchone()[0]
    scan=module._reject_reflections;fired=[False]
    def changed(*args):
        scan(*args)
        if fired[0]:return
        fired[0]=True
        if fault in ('artifact','first_artifact','slot'):path.write_bytes(replacement if fault=='slot' else b'invented late proof corruption')
        elif fault in ('alias','history'):
            with o.a.db:o.a.db.execute("UPDATE state SET value='{}' WHERE key=?",(key,))
        elif fault=='context_close':c.close()
        else:context(account)
    monkeypatch.setattr(module,'_reject_reflections',changed)
    try:
        try:presence_proof(o,r)
        except RuntimeRefused:pass
        assert fired[0]
        with pytest.raises(RuntimeRefused):proof._verify()
        assert c._closed
    finally:
        (o.a.store.root/'injected-proof-fault.json').write_text(json.dumps(dict(fault=fault,fired=fired[0],observed_file_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),observed_row=o.a.db.execute('SELECT value FROM state WHERE key=?',(key,)).fetchone()[0])))
        path.write_bytes(original)
        with o.a.db:o.a.db.execute('UPDATE state SET value=? WHERE key=?',(row,key))
    with pytest.raises(RuntimeRefused):c.diagnostic()


@pytest.mark.parametrize('fault',['revoked','replaced','closed','missing'])
def test_account_callbacks_cannot_hide_a_changed_prepared_presence(account,monkeypatch,fault):
    import compertum.runtime.paper_account_context as module
    import compertum.runtime.paper_presence as presence
    o,_,_=account;_,r=acknowledge(account);c=context(account);proof=presence_proof(o,r)
    original=o.a._presence;row=o.a.db.execute('SELECT * FROM paper_presence_records').fetchone()
    scan=module._reject_reflections;fired=[False]
    def changed(*args):
        scan(*args)
        if fired[0]:return
        fired[0]=True
        if fault=='replaced':o.a._presence=presence._PresenceOwner(o.a)
        elif fault=='closed':original.close()
        elif fault=='missing':
            with o.a.db:o.a.db.execute('DELETE FROM paper_presence_records')
        else:
            with o.a.db:o.a.db.execute("UPDATE paper_presence_records SET reason='INVENTED_LATE_REVOKE'")
    monkeypatch.setattr(module,'_reject_reflections',changed)
    try:
        c._prepare_proof();assert fired[0]
        with pytest.raises(RuntimeRefused):proof._verify()
    finally:
        (o.a.store.root/'injected-presence-proof-fault.json').write_text(json.dumps(dict(fault=fault,fired=fired[0],observed_rows=o.a.db.execute('SELECT presence_id,sha256,reason FROM paper_presence_records').fetchall())))
        with o.a.db:o.a.db.execute('INSERT OR REPLACE INTO paper_presence_records VALUES(?,?,?,?)',row)
        o.a._presence=original
    try:value=inspect(o,r)
    except RuntimeRefused:return
    assert value['presence_status']=='INVALIDATED'


@pytest.mark.parametrize('kind',['account','presence'])
def test_final_proof_rechecks_original_age_and_owner_lifetime(account,kind):
    from test_paper_presence import advance
    o,_,_=account;_,r=acknowledge(account);c=context(account)
    p=c._prepare_proof() if kind=='account' else presence_proof(o,r)
    advance(o,31 if kind=='account' else 300)
    with pytest.raises(RuntimeRefused):p._verify()
    if kind=='account':assert c._closed
    else:assert inspect(o,r)['presence_status']=='INVALIDATED'


def test_joint_account_and_presence_proofs_finish_inside_one_owner_scope(account,monkeypatch):
    from compertum.runtime.owners import _owner_scope
    import compertum.runtime.paper_account_context as ac
    import compertum.runtime.paper_presence as pr
    o,_,_=account;_,r=acknowledge(account);c=context(account)
    with _owner_scope(o.a.lease),o.a.store._live():
        cp=c._prepare_proof();pp=presence_proof(o,r)
        def forbidden(*args,**kwargs):raise AssertionError('Callback during joint final proofs')
        for module in (ac,pr):
            for name in ('load_paper_slot','open_paper_credentials','open_read_evidence','_reject_reflections'):
                monkeypatch.setattr(module,name,forbidden)
        monkeypatch.setattr(ac,'original_opening',forbidden)
        monkeypatch.setattr(type(o.e),'status',forbidden)
        monkeypatch.setattr(type(o.a._preflight),'diagnostic',forbidden)
        from compertum.runtime.paper_final_proof import _verify_proofs
        _verify_proofs(cp,pp)


@pytest.mark.parametrize('field',['subject','presence_id'])
def test_private_presence_proof_authentication_cannot_revoke_valid_presence(account,field):
    from uuid import uuid4
    o,_,_=account;_,r=acknowledge(account)
    args=dict(subject='a'*64,presence_id=r['presence_id']);args[field]='b'*64 if field=='subject' else str(uuid4())
    with pytest.raises(RuntimeRefused):o.a._presence._prepare_proof(**args)
    assert inspect(o,r)['presence_status']=='CURRENT'


@pytest.mark.parametrize('kind',['account','presence'])
def test_owner_restart_cannot_revive_prepared_proof(account,kind):
    o,_,_=account;_,r=acknowledge(account);c=context(account)
    proof=c._prepare_proof() if kind=='account' else presence_proof(o,r)
    o.a.close();o.a=o.module.PaperReadOwner(o.a.store,o.a.reserve,o.e)
    with pytest.raises(RuntimeRefused):proof._verify()
    if kind=='account':assert c._closed
    else:assert inspect(o,r)['presence_status']=='INVALIDATED'


def test_account_proof_preserves_verified_nonempty_history(publication,invented_paper_origin):
    from compertum.fake_execution_journal import FakeIntentJournal
    from test_fake_execution_journal import checked_records
    o,pub,_=publication;journal=FakeIntentJournal(o.a.store)
    intent,decision=checked_records(o.a.lease);journal.record_checked(intent,decision)
    _,_,p,proposal=propose(publication);confirm(pub,p,proposal)
    c=context((o,pub,p));proof=c._prepare_proof();before=o.a.db.total_changes
    proof._verify();assert o.a.db.total_changes==before
    assert 'NONEMPTY_LOCAL_HISTORY_REQUIRES_RECONCILIATION' in c.diagnostic()['observed_deficiencies']


@pytest.mark.parametrize('kind',['account','presence'])
def test_proof_refuses_an_open_caller_transaction_without_committing_it(account,kind):
    o,_,_=account;_,r=acknowledge(account);c=context(account)
    proof=c._prepare_proof() if kind=='account' else presence_proof(o,r)
    o.a.db.execute("INSERT INTO state VALUES('invented_pending_proof_caller','1')")
    assert o.a.db.in_transaction
    try:
        with pytest.raises(RuntimeRefused,match='TRANSACTION_OPEN'):proof._verify()
        assert o.a.db.in_transaction
    finally:o.a.db.rollback()
    assert o.a.db.execute("SELECT 1 FROM state WHERE key='invented_pending_proof_caller'").fetchone() is None
    proof._verify()
