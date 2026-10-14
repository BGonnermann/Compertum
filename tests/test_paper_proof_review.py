"""Native stores/DPAPI; simulated clocks and original account observations."""
import sqlite3
import pytest
from compertum.runtime.errors import RuntimeRefused
from test_execution_health import pair,connect
from test_paper_read_owner import owner
from test_paper_read_publication import publication,launch
from test_paper_account_binding import invented_paper_origin,propose,confirm,call
from test_paper_presence import account,acknowledge,advance,inspect
from test_paper_account_context import context
from test_paper_account_presence_proofs import presence_proof


@pytest.mark.parametrize('fault',['owner_closed','connection_replaced'])
def test_presence_proof_cannot_commit_pending_original_transaction(account,fault):
    o,_,_=account;_,r=acknowledge(account);proof=presence_proof(o,r);original=o.a.db
    replacement=None
    if fault=='owner_closed':o.a.close()
    else:
        replacement=sqlite3.connect(':memory:');o.a.db=replacement
    original.execute("INSERT INTO state VALUES('invented_pending_original_proof','1')")
    observed={}
    try:
        try:proof._verify()
        except RuntimeRefused as error:observed['refusal']=error.code
        observed['transaction_open']=original.in_transaction
    finally:
        original.rollback();o.a.db=original
        if replacement is not None:replacement.close()
    assert observed.get('transaction_open'),observed
    assert observed.get('refusal')=='PAPER_FINAL_PROOF_TRANSACTION_OPEN',observed
    assert original.execute("SELECT 1 FROM state WHERE key='invented_pending_original_proof'").fetchone() is None


def test_presence_proof_refuses_changed_database_even_without_pending_transaction(account):
    o,_,_=account;_,r=acknowledge(account);proof=presence_proof(o,r);original=o.a.db
    replacement=sqlite3.connect(':memory:');o.a.db=replacement
    try:
        with pytest.raises(RuntimeRefused):proof._verify()
    finally:o.a.db=original;replacement.close()


def test_joint_proofs_check_account_age_after_all_presence_reads(account,monkeypatch):
    import compertum.runtime.paper_presence as presence
    import compertum.runtime.paper_final_proof as final
    o,_,_=account;_,r=acknowledge(account);ctx=context(account)
    cp=ctx._prepare_proof();pp=presence_proof(o,r)
    advance(o,28);original=presence.published_original;fired=[False]
    def delayed(*args,**kwargs):
        result=original(*args,**kwargs)
        if not fired[0]:
            fired[0]=True;o.clock.utc+=3;o.clock.mono+=3
        return result
    monkeypatch.setattr(presence,'published_original',delayed)
    # The old sequential interface reproduces the review defect; the joint
    # interface must refuse the same originals after its last durable read.
    verify=getattr(final,'_verify_proofs',None)
    with pytest.raises(RuntimeRefused,match='PAPER_PREFLIGHT_STALE'):
        if verify is None:cp._verify();pp._verify()
        else:verify(cp,pp)
    assert fired[0] and ctx._closed


def test_preparation_callback_refusal_does_not_commit_callers_pending_write(account,monkeypatch):
    import compertum.runtime.paper_presence as presence
    o,_,_=account;_,r=acknowledge(account);original=presence._reject_reflections;fired=[False]
    def refused(*args,**kwargs):
        original(*args,**kwargs)
        if not fired[0]:
            fired[0]=True
            o.a.db.execute("INSERT INTO state VALUES('invented_callback_pending_proof','1')")
            raise RuntimeRefused('INVENTED_PROOF_CALLBACK_REFUSAL')
    monkeypatch.setattr(presence,'_reject_reflections',refused)
    try:
        with pytest.raises(RuntimeRefused):presence_proof(o,r)
        pending=o.a.db.in_transaction
    finally:o.a.db.rollback();monkeypatch.setattr(presence,'_reject_reflections',original)
    assert fired[0] and pending
    assert o.a.db.execute("SELECT 1 FROM state WHERE key='invented_callback_pending_proof'").fetchone() is None
    assert inspect(o,r)['presence_status']=='INVALIDATED'


@pytest.mark.parametrize('fault',['empty','duplicate','consumed'])
def test_invalid_joint_calls_do_not_consume_other_proofs_or_invalidate_current_inputs(account,fault):
    from compertum.runtime.paper_final_proof import _verify_proofs
    o,_,_=account;_,r=acknowledge(account);ctx=context(account)
    cp=ctx._prepare_proof();pp=presence_proof(o,r)
    if fault=='consumed':cp._verify()
    before=o.a.db.total_changes
    args=() if fault=='empty' else (cp,cp) if fault=='duplicate' else (cp,pp)
    with pytest.raises(RuntimeRefused):_verify_proofs(*args)
    assert o.a.db.total_changes==before
    if fault!='consumed':cp._verify()
    pp._verify()
    assert not ctx._closed and inspect(o,r)['presence_status']=='CURRENT'
