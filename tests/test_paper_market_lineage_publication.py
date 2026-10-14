"""Local lineage transfer/recovery with real DPAPI and storage, in-process RPC."""
from copy import deepcopy
from uuid import uuid4
import base64,time
import pytest
from compertum.data.encoding import canonical
from compertum.runtime.errors import RuntimeRefused
from compertum.runtime.service_budget import queue_for
from test_paper_market_owner_fresh import history,completed,pair,owner,native_market,publication
from test_paper_market_publication import command


@pytest.fixture
def captured(history):
    o=history;p,_=completed(o)
    assert hasattr(o.pub,'_lineage'), 'Durable lineage transfer is missing'
    reg=o.remote.descriptor.registration
    reg.generation=o.e.lease.generation;reg.identity.process_instance_id=o.e.lease.identity.process_instance_id
    cid=str(uuid4());budget=queue_for(o.e.lease).status()
    result=command(o,'publish_lineage',capture_id=cid,job_id=p['job_id'],grant_sha256=p['grant_sha256'])
    assert result['state']=='CAPTURING'
    return o,p,cid,budget


def status(o,cid):return command(o,'lineage_status',capture_id=cid)


def drive(o,cid,phase):
    deadline=time.monotonic()+8
    while time.monotonic()<deadline:
        if o.pub._lineage.entries[cid]['phase']==phase:return
        start=time.monotonic();o.a.tick();assert time.monotonic()-start<5
        start=time.monotonic();o.pub.tick();assert time.monotonic()-start<5
    raise AssertionError('Lineage phase not reached: '+phase)


def test_publication_seals_once_retries_exactly_and_does_not_issue_http(captured):
    o,p,cid,budget=captured;drive(o,cid,'DONE');s=status(o,cid);held=o.a._market._opened
    assert s['state']==s['publication']['state']=='PUBLISHED' and s['manifest']==s['publication']['manifest']
    assert o.a._market._lineage._cipher is None and held.snapshot()['collection']['mode']=='HISTORY'
    count=o.pub.db.execute('SELECT count(*) FROM reservations').fetchone()
    o.clock.utc+=86400;o.clock.mono+=86400
    assert command(o,'publish_lineage',capture_id=cid,job_id=p['job_id'],grant_sha256=p['grant_sha256'])==s
    assert o.pub.db.execute('SELECT count(*) FROM reservations').fetchone()==count and queue_for(o.e.lease).status()==budget
    assert len(canonical(s))<65536 and all(x not in canonical(s) for x in (b'body_utf8',b'ciphertext'))
    assert all(s[k] is False for k in ('financial_accepted','transport_authorized','research_eligible'))


@pytest.mark.parametrize('fault',['subject','job','grant','extra'])
def test_exact_capture_retry_rejects_identity_substitution(captured,fault):
    o,p,cid,_=captured;before=len(o.rpc);count=o.pub.db.execute('SELECT count(*) FROM reservations').fetchone()
    c=dict(operation='publish_lineage',capture_id=cid,job_id=p['job_id'],grant_sha256=p['grant_sha256']);subject='a'*64
    if fault=='subject':subject='b'*64
    elif fault=='job':c['job_id']=str(uuid4())
    elif fault=='grant':c['grant_sha256']='f'*64
    else:c['reservation_id']=str(uuid4())
    with pytest.raises(RuntimeRefused):o.pub.handle(subject,c)
    assert len(o.rpc)==before and o.pub.db.execute('SELECT count(*) FROM reservations').fetchone()==count


def test_cancel_fresh_does_not_drop_cipher_or_allow_checkpoint(captured):
    o,p,cid,_=captured;drive(o,cid,'COLLECT');cipher=o.a._market._lineage._cipher
    command(o,'cancel',job_id=p['job_id']);assert o.a._market._lineage._cipher is cipher
    with pytest.raises(RuntimeRefused,match='MARKET_CHECKPOINT_BUSY'):o.a.require_checkpoint()
    drive(o,cid,'DONE');assert o.a._market._lineage._cipher is None;o.a.require_checkpoint()


@pytest.mark.parametrize('phase',['WAIT','COLLECT','PUBLISH','ACK','DONE'])
def test_restart_is_ack_only_and_never_recaptures(captured,phase):
    o,p,cid,budget=captured;drive(o,cid,phase);old=status(o,cid)
    o.a.close();o.a=o.module.PaperReadOwner(o.a.store,o.a.reserve,o.e)
    o.pub=o.pub_module.PaperMarketPublication(o.manager,o.remote);o.rpc.clear()
    for _ in range(5):o.a.tick();o.pub.tick()
    result=status(o,cid)
    assert result['publication']['state']==('PUBLISHED' if phase in {'ACK','DONE'} else 'FAILED')
    assert result['state']==('PUBLISHED' if phase in {'ACK','DONE'} else 'INTERRUPTED')
    assert all(op in {'lineage_ack','lineage_status'} for _,op in o.rpc)
    assert queue_for(o.e.lease).status()==budget and o.a._market._fresh_view is None
    assert result['evidence']==old['evidence']


@pytest.mark.parametrize('lost_after_execution',[False,True])
def test_lost_ack_retains_bytes_and_manifest_until_verified_ack(captured,monkeypatch,lost_after_execution):
    o,p,cid,budget=captured;drive(o,cid,'ACK');saved=deepcopy(o.pub._lineage.routes.read(cid));cipher=o.a._market._lineage._cipher;held=o.a._market._opened
    def lost(remote,action,payload):
        if action=='paper_market_transfer' and payload['operation']=='lineage_ack':
            if lost_after_execution:o.call(remote,action,payload)
            raise RuntimeRefused('INJECTED_ACK_LOSS')
        return o.call(remote,action,payload)
    monkeypatch.setattr(o.pub_module,'call_owner',lost);o.pub.tick()
    assert o.pub._lineage.routes.read(cid)['manifest']==saved['manifest']
    assert (o.a._market._lineage._cipher is None) is lost_after_execution
    assert o.pub._lineage.entries[cid]['protected'] is not None
    monkeypatch.setattr(o.pub_module,'call_owner',o.call);o.pub=o.pub_module.PaperMarketPublication(o.manager,o.remote)
    drive(o,cid,'DONE');assert status(o,cid)['manifest']==saved['manifest'] and queue_for(o.e.lease).status()==budget
    for _ in range(4):o.pub.tick()
    assert command(o,'status',job_id=o.history['job_id'])['publication']['state']=='PUBLISHED'
    assert o.a._market._opened is held and held.snapshot()['collection']['mode']=='HISTORY'


def test_committed_artifact_survives_route_save_failure(captured,monkeypatch):
    o,p,cid,_=captured;drive(o,cid,'PUBLISH');save=o.pub._lineage.routes.write
    def fail(v,**kw):
        if v['manifest'] is not None:raise RuntimeRefused('INJECTED_ROUTE_SAVE')
        return save(v,**kw)
    monkeypatch.setattr(o.pub._lineage.routes,'write',fail)
    with pytest.raises(RuntimeRefused,match='INJECTED_ROUTE_SAVE'):o.pub.tick()
    assert o.pub._lineage.routes.read(cid)['manifest'] is None
    o.pub=o.pub_module.PaperMarketPublication(o.manager,o.remote);o.rpc.clear();drive(o,cid,'DONE')
    assert status(o,cid)['state']=='PUBLISHED' and not any(op=='lineage_chunk' for _,op in o.rpc)


@pytest.mark.parametrize('fault',['capture','task','project','alias','grant','offset','total','base64','length','body'])
def test_corrupt_chunk_never_publishes_or_recollects(captured,monkeypatch,fault):
    o,p,cid,budget=captured;drive(o,cid,'COLLECT')
    def corrupt(remote,action,payload):
        reply=o.call(remote,action,payload)
        if action=='paper_market_transfer' and payload['operation']=='lineage_chunk':
            if fault in {'capture','task'}:reply[fault+'_id']=str(uuid4())
            elif fault in {'project','grant'}:reply['project_id' if fault=='project' else 'grant_sha256']='f'*64
            elif fault=='alias':reply['account_alias']='other'
            elif fault=='offset':reply['offset']=True
            elif fault=='total':reply['total_bytes']+=1
            elif fault=='base64':reply['data']='?'
            else:
                raw=base64.b64decode(reply['data']);raw=raw[:-1] if fault=='length' else bytes([raw[0]^255])+raw[1:]
                reply['data']=base64.b64encode(raw).decode()
        return reply
    monkeypatch.setattr(o.pub_module,'call_owner',corrupt)
    for _ in range(100):
        if o.pub._lineage.entries[cid]['phase']=='FAILED':break
        o.pub.tick()
    assert status(o,cid)['publication']['state']=='FAILED' and queue_for(o.e.lease).status()==budget
    assert o.pub._lineage.routes.read(cid)['manifest'] is None and o.a._market._lineage._cipher is not None


def test_multichunk_and_only_immediate_previous_retry(captured):
    o,p,cid,_=captured;drive(o,cid,'COLLECT');s=status(o,cid);size=s['evidence']['size_bytes']
    assert size>32768
    payload=dict(operation='lineage_chunk',capture_id=cid,offset=0,sha256=s['evidence']['sha256'])
    first=o.a.market_transfer(payload);assert o.a.market_transfer(payload)==first
    second=o.a.market_transfer(dict(payload,offset=32768));assert len(base64.b64decode(first['data']))==32768
    assert o.a.market_transfer(dict(payload,offset=32768))==second
    with pytest.raises(RuntimeRefused):o.a.market_transfer(payload)


def test_orphan_reservation_after_failed_route_insert_is_not_reallocated(history,monkeypatch):
    o=history;p,_=completed(o);assert hasattr(o.pub,'_lineage'), 'Durable lineage transfer is missing'
    reg=o.remote.descriptor.registration;reg.generation=o.e.lease.generation;reg.identity.process_instance_id=o.e.lease.identity.process_instance_id
    cid=str(uuid4());count=o.pub.db.execute('SELECT count(*) FROM reservations').fetchone()[0]
    def fail(*a,**kw):raise RuntimeRefused('INJECTED_ROUTE_INSERT')
    monkeypatch.setattr(o.pub._lineage.routes,'write',fail)
    with pytest.raises(RuntimeRefused):command(o,'publish_lineage',capture_id=cid,job_id=p['job_id'],grant_sha256=p['grant_sha256'])
    assert o.pub.db.execute('SELECT count(*) FROM reservations').fetchone()[0]==count+1
    with pytest.raises(RuntimeRefused):command(o,'publish_lineage',capture_id=cid,job_id=p['job_id'],grant_sha256=p['grant_sha256'])
    assert o.pub.db.execute('SELECT count(*) FROM reservations').fetchone()[0]==count+1


@pytest.mark.parametrize('after_delivery',[False,True])
def test_first_request_loss_retries_same_live_identity_without_reallocation(history,monkeypatch,after_delivery):
    o=history;p,_=completed(o);reg=o.remote.descriptor.registration
    reg.generation=o.e.lease.generation;reg.identity.process_instance_id=o.e.lease.identity.process_instance_id
    cid=str(uuid4());count=o.pub.db.execute('SELECT count(*) FROM reservations').fetchone()[0];lost=[]
    def first_loss(remote,action,payload):
        if action=='paper_market_read' and payload['command']['operation']=='publish_lineage' and not lost:
            lost.append(True)
            if after_delivery:o.call(remote,action,payload)
            raise RuntimeRefused('INJECTED_FIRST_REQUEST_LOSS')
        return o.call(remote,action,payload)
    monkeypatch.setattr(o.pub_module,'call_owner',first_loss)
    with pytest.raises(RuntimeRefused,match='INJECTED_FIRST_REQUEST_LOSS'):
        command(o,'publish_lineage',capture_id=cid,job_id=p['job_id'],grant_sha256=p['grant_sha256'])
    before=deepcopy(o.pub._lineage.routes.read(cid));o.pub.tick()
    result=command(o,'publish_lineage',capture_id=cid,job_id=p['job_id'],grant_sha256=p['grant_sha256'])
    assert result['state']=='CAPTURING' and o.pub._lineage.routes.read(cid)==before
    assert o.pub.db.execute('SELECT count(*) FROM reservations').fetchone()[0]==count+1
    drive(o,cid,'DONE');assert status(o,cid)['state']=='PUBLISHED'


def test_protection_context_failure_invalidates_fresh_and_preserves_consumption(captured,monkeypatch):
    import compertum.runtime.paper_market_lineage_evidence as evidence
    o,p,cid,_=captured;m=o.a._market;proof=m.consumptions.read(p['job_id']);scan=evidence._scan_generated
    def changed(*args,**kwargs):
        scan(*args,**kwargs)
        from compertum.runtime.paper_credentials import seal_paper_credentials
        from test_paper_read_preparation import KEY,SECRET
        other=seal_paper_credentials(o.e.lease,'fixture',bytearray(KEY.encode()),bytearray(SECRET.encode()))
        monkeypatch.setattr(o.market_module,'load_paper_slot',lambda *a:other)
    monkeypatch.setattr(evidence,'_scan_generated',changed);o.a.tick()
    assert m._lineage.records.read(cid)['state']=='FAILED' and m.records.read(p['job_id'])['state']=='INTERRUPTED'
    assert m._producer is None and m._opened is None and m._fresh_view is None
    assert m.consumptions.read(p['job_id'])==proof


def test_protection_failure_with_uncertain_cleanup_retains_owner_capacity(captured,monkeypatch):
    import compertum.runtime.paper_market_lineage_evidence as evidence
    o,p,cid,_=captured;m=o.a._market;producer=m._producer;scan=evidence._scan_generated;close=type(producer).close
    def changed(*args,**kwargs):
        scan(*args,**kwargs)
        from compertum.runtime.paper_credentials import seal_paper_credentials
        from test_paper_read_preparation import KEY,SECRET
        other=seal_paper_credentials(o.e.lease,'fixture',bytearray(KEY.encode()),bytearray(SECRET.encode()))
        monkeypatch.setattr(o.market_module,'load_paper_slot',lambda *a:other)
    def refuse(value):
        if value is producer:raise RuntimeRefused('HTTP_CLEANUP_UNVERIFIED')
        return close(value)
    with monkeypatch.context() as patch:
        patch.setattr(evidence,'_scan_generated',changed);patch.setattr(type(producer),'close',refuse);o.a.tick()
        assert m.records.read(p['job_id'])['state']=='INTERRUPTED' and m._cleanup_failed and m._producer is producer
        with pytest.raises(RuntimeRefused):m.require_checkpoint()
        with pytest.raises(RuntimeRefused):m._capacity()
    m.close();assert m._producer is None and not m._cleanup_failed


def test_protection_preserves_capture_time_without_restoring_clock_authority(captured,monkeypatch):
    import compertum.runtime.paper_market_lineage_evidence as evidence
    o,p,cid,_=captured;scan=evidence._scan_generated;saved=[]
    def changed(value,secrets):
        scan(value,secrets);saved.append(deepcopy(value['lineage']));o.clock.utc+=6
    monkeypatch.setattr(evidence,'_scan_generated',changed);o.a.tick();drive(o,cid,'DONE');s=status(o,cid)
    with evidence.open_market_lineage(o.a._market,account_alias='fixture',capture_id=cid,manifest=s['manifest']) as opened:
        v=opened.snapshot();assert v['lineage']==saved[0] and v['freshness']=='NOT_RESTORED' and not v['transport_authorized']
    with pytest.raises(RuntimeRefused):command(o,'compose',job_id=p['job_id'])
    assert o.a._market.records.read(p['job_id'])['state']=='INTERRUPTED'


@pytest.mark.parametrize('fault',['duplicate','status','category','parent','bytes'])
def test_invalid_recovery_ledger_refuses_before_ack(captured,fault):
    o,p,cid,budget=captured;drive(o,cid,'ACK');r=o.pub._lineage.routes.read(cid);db=o.pub.db;path=r['manifest']['path']
    with db:
        if fault=='duplicate':db.execute('INSERT INTO reservations SELECT ?,task,category,maximum,written,status,path,manifest FROM reservations WHERE path=?',(str(uuid4()),path))
        elif fault=='parent':db.execute("UPDATE reservations SET status='ABANDONED' WHERE id=?",(r['reservation_id'],))
        elif fault=='bytes':
            file=o.manager.root/path;raw=file.read_bytes();file.write_bytes(bytes([raw[0]^255])+raw[1:])
        else:db.execute('UPDATE reservations SET '+fault+'=? WHERE path=?',('ABANDONED' if fault=='status' else 'data',path))
    o.pub=o.pub_module.PaperMarketPublication(o.manager,o.remote);o.rpc.clear()
    for _ in range(5):o.pub.tick()
    assert status(o,cid)['publication']['state']=='FAILED' and o.a._market._lineage._cipher is not None
    assert not any(op in {'lineage_ack','lineage_chunk','publish_lineage'} for _,op in o.rpc) and queue_for(o.e.lease).status()==budget


@pytest.mark.parametrize('fault',['parent','route_subject','route_history'])
def test_changed_reservation_or_route_refuses_capture_without_revoking_valid_fresh(captured,fault):
    o,p,cid,budget=captured;r=o.pub._lineage.routes.read(cid);db=o.pub.db;held=o.a._market._opened
    with db:
        if fault=='parent':db.execute('UPDATE reservations SET maximum=1 WHERE id=?',(r['reservation_id'],))
        else:
            if fault=='route_subject':r['subject_key']='f'*64
            else:r['history']['grant_sha256']='f'*64
            db.execute('UPDATE state SET value=? WHERE key=?',(canonical(r).decode(),'paper_market_lineage_route:'+cid))
    o.a.tick();m=o.a._market
    assert m._lineage.records.read(cid)['state']=='FAILED' and m.records.read(p['job_id'])['state']=='COMPLETE'
    assert m._opened is held and m._lineage._cipher is None and queue_for(o.e.lease).status()==budget


@pytest.mark.parametrize('stage',['READY','PUBLISHED'])
def test_ignored_capture_commit_retains_cipher_and_cannot_claim_ack(captured,stage):
    o,p,cid,_=captured
    if stage=='PUBLISHED':drive(o,cid,'ACK')
    db=o.a.db
    db.execute("CREATE TRIGGER ignore_capture_progress BEFORE UPDATE ON state WHEN NEW.key LIKE 'paper_market_lineage_capture:%' AND NEW.value LIKE '%\"state\":\""+stage+"\"%' BEGIN SELECT RAISE(IGNORE); END")
    if stage=='READY':o.a.tick()
    else:o.pub.tick()
    assert o.a._market._lineage._cipher is not None
    assert o.a._market._lineage.records.read(cid)['state']==('FAILED' if stage=='READY' else 'READY')
    with pytest.raises(RuntimeRefused):o.a.require_checkpoint()
    db.execute('DROP TRIGGER ignore_capture_progress')
    if stage=='PUBLISHED':
        o.pub=o.pub_module.PaperMarketPublication(o.manager,o.remote);drive(o,cid,'DONE')
        assert o.a._market._lineage._cipher is None


def test_second_capture_is_refused_before_reservation_while_cipher_is_retained(captured):
    o,p,cid,_=captured;drive(o,cid,'COLLECT');count=o.pub.db.execute('SELECT count(*) FROM reservations').fetchone()
    with pytest.raises(RuntimeRefused):command(o,'publish_lineage',capture_id=str(uuid4()),job_id=p['job_id'],grant_sha256=p['grant_sha256'])
    assert o.pub.db.execute('SELECT count(*) FROM reservations').fetchone()==count
    command(o,'cancel',job_id=p['job_id'])
    with pytest.raises(RuntimeRefused,match='MARKET_OWNER_CAPACITY'):o.a._market._capacity()


@pytest.mark.parametrize('fault',['offset_bool','extra','wrong_hash','old_ack'])
def test_private_transfer_shape_and_ack_binding_are_checked(captured,fault):
    o,p,cid,_=captured;drive(o,cid,'COLLECT');s=status(o,cid)
    payload=dict(operation='lineage_chunk',capture_id=cid,offset=0,sha256=s['evidence']['sha256'])
    if fault=='offset_bool':payload['offset']=False
    elif fault=='extra':payload['manifest']={}
    elif fault=='wrong_hash':payload['sha256']='f'*64
    else:payload=dict(operation='lineage_ack',capture_id=cid,manifest=command(o,'status',job_id=o.history['job_id'])['manifest'])
    with pytest.raises(RuntimeRefused):o.a.market_transfer(payload)
    assert o.a._market._lineage._cipher is not None and o.a._market._lineage.records.read(cid)['state']=='READY'
