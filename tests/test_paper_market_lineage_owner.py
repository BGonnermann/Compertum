"""Owner-resolved lineage uses committed consumption records, without new I/O."""
import json,pickle
from uuid import uuid4
import pytest
from compertum.data.encoding import canonical
from compertum.runtime.errors import RuntimeRefused
from test_paper_market_owner_fresh import history,completed,fresh_prepare,bodies,finish,pair,owner,native_market,publication
from test_paper_market_publication import command,start
from test_paper_market_collection import pages
from compertum.runtime.service_budget import queue_for


def capture(o,p,**changes):
    v=o.a._market.records.read(p['job_id']);args=dict(subject=v['grant']['subject_key'],job_id=p['job_id'],grant_sha256=p['grant_sha256']);args.update(changes)
    return o.a._market._capture_lineage(**args)


def test_capture_resolves_both_original_records_and_consumption_without_new_io(history):
    from compertum.runtime.paper_market_lineage_owner import validate_owner_lineage
    o=history;p,_=completed(o);m=o.a._market
    reservations=o.manager.store.conn.execute('SELECT count(*) FROM reservations').fetchone();budget=queue_for(o.e.lease).status()
    value=capture(o,p);v=json.loads(value.content)
    for mode,job in [('fresh',p['job_id']),('history',o.history['job_id'])]:assert v['consumption'][mode]==m.consumptions.read(job)
    result=validate_owner_lineage(value.content,history=m._opened.snapshot())
    assert result['use']=='HISTORICAL_ONLY' and result['freshness']=='NOT_RESTORED'
    assert all(result[k] is False for k in ('financial_accepted','transport_authorized','research_eligible'))
    assert queue_for(o.e.lease).status()==budget
    assert o.manager.store.conn.execute('SELECT count(*) FROM reservations').fetchone()==reservations
    assert 'body_utf8' not in repr(value)
    with pytest.raises(RuntimeRefused):pickle.dumps(value)


def test_both_consumption_writes_commit_before_producer_construction(history,monkeypatch):
    o=history;p=fresh_prepare(o);original=o.market_module._MarketFresh;seen=[]
    def constructor(*args,**kwargs):
        m=o.a._market;v=m.records.read(p['job_id']);proof=m.consumptions.read(p['job_id'])
        assert not m.db.in_transaction and v['state']=='RUNNING' and v['consumed']
        assert proof['grant_sha256']==p['grant_sha256'];seen.append(proof)
        return original(*args,**kwargs)
    monkeypatch.setattr(o.market_module,'_MarketFresh',constructor)
    with pages(bodies(o)) as (port,requests):
        o.market_port=port;start(o,p);assert finish(o,p)['state']=='COMPLETE'
        assert start(o,p)['state']=='COMPLETE' and len(requests)==2 and len(seen)==1
    assert o.a._market.consumptions.read(p['job_id'])==seen[0]


def test_delay_after_initial_admission_is_rechecked_before_consumption(history,monkeypatch):
    o=history;p=fresh_prepare(o);command(o,'authorize',job_id=p['job_id'],grant_sha256=p['grant_sha256'])
    m=o.a._market;original=m._capacity
    def delayed():original();o.clock.utc+=60;o.clock.mono+=60
    monkeypatch.setattr(m,'_capacity',delayed)
    with pytest.raises(RuntimeRefused):command(o,'start',job_id=p['job_id'],grant_sha256=p['grant_sha256'])
    assert not m.records.read(p['job_id'])['consumed'] and m._producer is None
    assert m.db.execute('SELECT 1 FROM state WHERE key=?',('paper_market_consumption:'+p['job_id'],)).fetchone() is None


def test_constructor_failure_retains_committed_consumption(history,monkeypatch):
    o=history;p=fresh_prepare(o)
    def refused(*args,**kwargs):raise RuntimeRefused('INJECTED_CONSTRUCTOR_FAILURE')
    monkeypatch.setattr(o.market_module,'_MarketFresh',refused)
    s=start(o,p);assert s['state']=='ABORTED'
    saved=o.a._market.consumptions.read(p['job_id']);assert saved['grant_sha256']==p['grant_sha256']
    assert start(o,p)['state']=='ABORTED' and o.a._market.consumptions.read(p['job_id'])==saved


def test_ignored_proof_prevents_producer_and_rolls_back_job(history,monkeypatch):
    o=history;p=fresh_prepare(o);command(o,'authorize',job_id=p['job_id'],grant_sha256=p['grant_sha256']);m=o.a._market
    m.db.execute("CREATE TRIGGER ignore_proof BEFORE INSERT ON state WHEN NEW.key LIKE 'paper_market_consumption:%' BEGIN SELECT RAISE(IGNORE); END")
    seen=[];monkeypatch.setattr(o.market_module,'_MarketFresh',lambda *a,**kw:seen.append(True))
    with pytest.raises(RuntimeRefused):command(o,'start',job_id=p['job_id'],grant_sha256=p['grant_sha256'])
    assert not seen and m.records.read(p['job_id'])['state']=='GRANTED' and not m.records.read(p['job_id'])['consumed']


@pytest.mark.parametrize('field',['subject','job_id','grant_sha256'])
def test_capture_rejects_untrusted_request_identity(history,field):
    o=history;p,_=completed(o)
    with pytest.raises(RuntimeRefused):capture(o,p,**{field:str(uuid4()) if field=='job_id' else 'f'*64})
    assert o.a._market.records.read(p['job_id'])['state']=='COMPLETE'


@pytest.mark.parametrize('mode',['fresh','history'])
def test_legacy_missing_proof_stays_readable_but_cannot_claim_consumption(history,mode):
    o=history;p,_=completed(o);m=o.a._market;job=p['job_id'] if mode=='fresh' else o.history['job_id']
    with m.db:m.db.execute('DELETE FROM state WHERE key=?',('paper_market_consumption:'+job,))
    assert m.records.read(job)['consumed']
    with pytest.raises(RuntimeRefused):capture(o,p)
    assert m.records.read(p['job_id'])['state']=='COMPLETE'


def test_restart_keeps_historical_proofs_but_never_restores_fresh_capture(history):
    from compertum.runtime.paper_market_lineage_owner import validate_owner_lineage
    o=history;p,_=completed(o);m=o.a._market;value=capture(o,p);original=m._opened.snapshot();saved=m.consumptions.read(p['job_id'])
    o.a.close();o.a=o.module.PaperReadOwner(o.a.store,o.a.reserve,o.e)
    assert command(o,'status',job_id=p['job_id'])['state']=='INTERRUPTED'
    assert o.a._market.consumptions.read(p['job_id'])==saved
    with pytest.raises(RuntimeRefused):capture(o,p)
    assert validate_owner_lineage(value.content,history=original)['freshness']=='NOT_RESTORED'


@pytest.mark.parametrize('field',['fresh','history','lineage','extra'])
def test_historical_proof_substitution_is_rejected(history,field):
    from compertum.runtime.paper_market_lineage_owner import validate_owner_lineage
    o=history;p,_=completed(o);value=json.loads(capture(o,p).content)
    if field in {'fresh','history'}:value['consumption'][field]['grant_sha256']='f'*64
    elif field=='lineage':value['lineage']['fresh_grant']['subject_key']='f'*64
    else:value[field]=True
    with pytest.raises(RuntimeRefused):validate_owner_lineage(canonical(value),history=o.a._market._opened.snapshot())


def test_consumption_changed_during_capture_is_detected(history,monkeypatch):
    import compertum.runtime.paper_market_lineage_owner as module
    o=history;p,_=completed(o);original=module.capture_market_lineage
    def changed(*args,**kwargs):
        value=original(*args,**kwargs)
        with o.a.db:o.a.db.execute('DELETE FROM state WHERE key=?',('paper_market_consumption:'+p['job_id'],))
        return value
    monkeypatch.setattr(module,'capture_market_lineage',changed)
    with pytest.raises(RuntimeRefused):capture(o,p)


@pytest.mark.parametrize('fault',['clock_divergence','clock_rollback','health','credential'])
def test_live_capture_refusal_revokes_views_and_preserves_consumption(history,monkeypatch,fault):
    import compertum.runtime.paper_market_lineage_owner as module
    o=history;p,_=completed(o);m=o.a._market;saved=m.consumptions.read(p['job_id'])
    if fault.startswith('clock'):
        o.clock.utc+=6 if fault=='clock_divergence' else -1
    else:
        scan=module._scan_generated
        def changed(*args,**kwargs):
            scan(*args,**kwargs)
            if fault=='health':o.e.halt('INJECTED_HEALTH_LOSS')
            else:
                from compertum.runtime.paper_credentials import seal_paper_credentials
                from test_paper_read_preparation import KEY,SECRET
                changed=seal_paper_credentials(o.e.lease,'fixture',bytearray(KEY.encode()),bytearray(SECRET.encode()))
                monkeypatch.setattr(o.market_module,'load_paper_slot',lambda *a:changed)
        monkeypatch.setattr(module,'_scan_generated',changed)
    with pytest.raises(RuntimeRefused):capture(o,p)
    assert m.records.read(p['job_id'])['state']=='INTERRUPTED'
    assert m._producer is None and m._opened is None and m._fresh_view is None
    assert m.consumptions.read(p['job_id'])==saved


def test_uncertain_cleanup_after_capture_refusal_retains_producer_and_blocks_capacity(history,monkeypatch):
    o=history;p,_=completed(o);m=o.a._market;producer=m._producer;saved=m.consumptions.read(p['job_id'])
    original=type(producer).close
    def refused(value):
        if value is producer:raise RuntimeRefused('HTTP_CLEANUP_UNVERIFIED')
        return original(value)
    with monkeypatch.context() as patch:
        patch.setattr(type(producer),'close',refused);o.clock.utc+=6
        with pytest.raises(RuntimeRefused,match='HTTP_CLEANUP_UNVERIFIED'):capture(o,p)
        assert m._producer is producer and m._cleanup_failed
        with pytest.raises(RuntimeRefused):m.require_checkpoint()
        with pytest.raises(RuntimeRefused):fresh_prepare(o)
        assert m.consumptions.read(p['job_id'])==saved
    m.close();assert m._producer is None and not m._cleanup_failed
