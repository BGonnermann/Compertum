"""Native stores/DPAPI and local replies; simulated origins, clocks and reserves."""
import hashlib,json,pickle
import pytest
from compertum.runtime.errors import RuntimeRefused
from test_paper_input_context import inputs,confirmed,context
from test_paper_market_owner_fresh import history,completed,pair,owner,native_market,publication
from test_paper_account_binding import invented_paper_origin,call,confirm
from test_paper_presence import acknowledge


@pytest.mark.parametrize('fault',['account','lineage','history','producer','combined','history_view'])
def test_later_presence_callbacks_cannot_hide_changed_combined_inputs(confirmed,monkeypatch,fault):
    import compertum.runtime.paper_presence as presence
    o,packet,fresh,capture,pub=confirmed;_,r=acknowledge((o,pub,packet))
    ctx=context(confirmed);proof=ctx._prepare_proof();market=o.a._market
    manifests=dict(account=pub._route(packet['packet_id'])['publication']['manifest'],
        lineage=market._lineage.records.read(capture)['manifest'],history=market.records.read(fresh['job_id'])['grant']['history']['manifest'])
    path=o.manager.root/manifests[fault]['path'] if fault in manifests else None
    before=path.read_bytes() if path else None;scan=presence._reject_reflections;fired=[False]
    def changed(*args):
        scan(*args)
        if fired[0]:return
        fired[0]=True
        if path:path.write_bytes(b'invented late combined proof corruption')
        elif fault=='producer':market._producer.close()
        elif fault=='combined':market._combined.close()
        else:market._opened.close()
    monkeypatch.setattr(presence,'_reject_reflections',changed)
    try:
        try:o.a._presence._prepare_proof(subject='a'*64,presence_id=r['presence_id'])
        except RuntimeRefused:pass
        assert fired[0]
        with pytest.raises(RuntimeRefused):proof._verify()
        assert ctx._closed
    finally:
        (o.a.store.root/'injected-combined-proof-fault.json').write_text(json.dumps(dict(fault=fault,fired=fired[0],observed_sha256=hashlib.sha256(path.read_bytes()).hexdigest() if path else None)))
        if path:path.write_bytes(before)
    with pytest.raises(RuntimeRefused):ctx.diagnostic()


def test_combined_final_proof_is_private_single_use_and_callback_free(confirmed,monkeypatch):
    import compertum.runtime.paper_input_context as module
    o,*_=confirmed;ctx=context(confirmed);proof=ctx._prepare_proof()
    with pytest.raises(RuntimeRefused):pickle.dumps(proof)
    def forbidden(*args,**kwargs):raise AssertionError('Callback after combined final proof boundary')
    for name in ('load_paper_slot','open_paper_credentials','open_read_evidence','open_market_lineage','_reject_reflections','_final_live','_current_market'):
        monkeypatch.setattr(module,name,forbidden)
    monkeypatch.setattr(type(o.e),'status',forbidden)
    monkeypatch.setattr(type(o.a._preflight),'diagnostic',forbidden)
    before=o.a.db.total_changes;proof._verify();assert before==o.a.db.total_changes
    with pytest.raises(RuntimeRefused):proof._verify()


@pytest.mark.parametrize('fault',['expiry','context_replace','health','health_replaced','market_parent'])
def test_combined_proof_keeps_original_age_and_lifetime(confirmed,fault):
    from copy import copy
    o,*_=confirmed;ctx=context(confirmed);proof=ctx._prepare_proof();health=o.a.health;market=o.a._market
    if fault=='expiry':o.clock.utc+=31;o.clock.mono+=31
    elif fault=='context_replace':context(confirmed)
    elif fault=='health_replaced':o.a.health=copy(health)
    elif fault=='market_parent':market.parent=object()
    else:o.e.halt('INVENTED_PROOF_HEALTH_HALT')
    try:
        with pytest.raises(RuntimeRefused):proof._verify()
        assert ctx._closed
    finally:o.a.health=health;market.parent=o.a


def test_combined_proof_account_refusal_keeps_borrowed_history(confirmed,monkeypatch):
    from datetime import timedelta
    import compertum.runtime.paper_input_context as module
    o,*_=confirmed;ctx=context(confirmed);proof=ctx._prepare_proof();market=o.a._market
    original=module._measure
    def stale():
        now,mono=original();return now+timedelta(seconds=31),mono+31
    monkeypatch.setattr(module,'_measure',stale)
    with pytest.raises(RuntimeRefused):proof._verify()
    assert ctx._closed and not market._opened._closed and not market._combined._closed
    assert market._opened.snapshot()['collection']['mode']=='HISTORY'
    assert market._combined.to_payload()['diagnostic']['quote']['valid']


def test_joint_combined_and_presence_proofs_finish_without_callbacks(confirmed,monkeypatch):
    from compertum.runtime.owners import _owner_scope
    import compertum.runtime.paper_input_context as module
    import compertum.runtime.paper_presence as presence
    o,packet,_,_,pub=confirmed;_,r=acknowledge((o,pub,packet));ctx=context(confirmed)
    with _owner_scope(o.a.lease),o.a.store._live():
        cp=ctx._prepare_proof();pp=o.a._presence._prepare_proof(subject='a'*64,presence_id=r['presence_id'])
        def forbidden(*args,**kwargs):raise AssertionError('Callback during joint final proofs')
        for m in (module,presence):
            for name in ('load_paper_slot','open_paper_credentials','open_read_evidence','_reject_reflections'):
                monkeypatch.setattr(m,name,forbidden)
        monkeypatch.setattr(module,'original_opening',forbidden)
        monkeypatch.setattr(module,'open_market_lineage',forbidden)
        monkeypatch.setattr(type(o.e),'status',forbidden)
        monkeypatch.setattr(type(o.a._preflight),'diagnostic',forbidden)
        from compertum.runtime.paper_final_proof import _verify_proofs
        _verify_proofs(cp,pp)
