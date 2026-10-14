"""Real local DPAPI/ledger evidence, original owner records, no provider calls."""
from uuid import uuid4
import hashlib,json,pickle
import pytest
from compertum.data.encoding import canonical
from compertum.runtime.errors import RuntimeRefused
from compertum.runtime.service_budget import queue_for
from test_paper_market_lineage_owner import capture
from test_paper_market_owner_fresh import history,completed,pair,owner,native_market,publication


def api():
    import importlib.util
    assert importlib.util.find_spec('compertum.runtime.paper_market_lineage_evidence'), 'Encrypted owner lineage is not implemented'
    from compertum.runtime import paper_market_lineage_evidence
    return paper_market_lineage_evidence


@pytest.fixture
def lineage(history):
    o=history;p,_=completed(o);v=capture(o,p);a=api()
    protected=a.protect_market_lineage(o.a._market,v,task_id=str(uuid4()),capture_id=str(uuid4()))
    return o,p,v,protected,a


def publish(f):
    o,_,_,s,a=f;g=o.manager.reserve_bytes(s.task_id,'records',len(s.ciphertext))
    return g,a.publish_market_lineage(o.manager,g,s)


def opening(f,r,**changes):
    o,_,_,s,a=f;args=dict(account_alias=s.account_alias,capture_id=s.capture_id,manifest=r);args.update(changes)
    return a.open_market_lineage(o.a._market,**args)


def test_encrypted_roundtrip_borrows_history_without_new_io(history):
    o=history;p,_=completed(o);v=capture(o,p);a=api();budget=queue_for(o.e.lease).status()
    s=a.protect_market_lineage(o.a._market,v,task_id=str(uuid4()),capture_id=str(uuid4()));f=(o,p,v,s,a)
    held=o.a._market._opened;g,r=publish(f)
    assert r['path']==f'artifacts/runs/{s.task_id}/market-lineage-{s.capture_id}.bin'
    assert v.content not in s.ciphertext and b'body_utf8' not in s.ciphertext
    with opening(f,r) as opened:
        result=opened.snapshot();assert result['lineage']==json.loads(v.content)
        assert result['use']=='HISTORICAL_ONLY' and result['freshness']=='NOT_RESTORED'
        assert all(result[k] is False for k in ('financial_accepted','transport_authorized','research_eligible'))
        buffer=opened._buffer;assert any(buffer)
        with pytest.raises(RuntimeRefused):pickle.dumps(opened)
        with pytest.raises(RuntimeRefused):pickle.dumps(s)
    assert not any(buffer) and held is o.a._market._opened and held.snapshot()['collection']['mode']=='HISTORY'
    with pytest.raises(RuntimeRefused):opened.snapshot()
    assert a.publish_market_lineage(o.manager,g,s)==r and queue_for(o.e.lease).status()==budget


def test_reopen_after_owner_recreation_retains_original_proof_and_never_authority(lineage):
    o,p,v,s,a=lineage;_,r=publish(lineage);o.a.close();o.a=o.module.PaperReadOwner(o.a.store,o.a.reserve,o.e)
    from test_paper_market_publication import command
    assert command(o,'status',job_id=p['job_id'])['state']=='INTERRUPTED'
    o.clock.utc+=86400;o.clock.mono+=86400
    with opening(lineage,r) as opened:
        result=opened.snapshot();assert result['lineage']==json.loads(v.content)
        assert result['freshness']=='NOT_RESTORED' and not result['transport_authorized']
    assert o.a._market._opened is None and o.a._market._fresh_view is None
    with pytest.raises(RuntimeRefused):a.protect_market_lineage(o.a._market,v,task_id=s.task_id,capture_id=s.capture_id)


@pytest.mark.parametrize('fault',['alias','capture','task','artifact','path','hash','size'])
def test_context_or_manifest_substitution_refuses(lineage,fault):
    _,r=publish(lineage);args={}
    if fault=='alias':args['account_alias']='other'
    elif fault=='capture':args['capture_id']=str(uuid4())
    elif fault=='task':r['task_id']=str(uuid4())
    elif fault=='artifact':r['artifact_id']=str(uuid4())
    elif fault=='path':r['path']='state/credentials.bin'
    elif fault=='hash':r['sha256']='f'*64
    else:r['size_bytes']+=1
    with pytest.raises(RuntimeRefused):
        with opening(lineage,r,**args):pass


@pytest.mark.parametrize('fault',['missing','status','written','category','task','duplicate'])
def test_unique_exact_ledger_required(lineage,fault):
    o,_,_,_,_=lineage;g,r=publish(lineage);db=o.manager.store.conn
    with db:
        if fault=='missing':db.execute('DELETE FROM reservations WHERE id=?',(g.grant_id,))
        elif fault=='duplicate':db.execute('INSERT INTO reservations SELECT ?,task,category,maximum,written,status,path,manifest FROM reservations WHERE id=?',(str(uuid4()),g.grant_id))
        else:db.execute('UPDATE reservations SET '+fault+'=? WHERE id=?',({'status':'ABANDONED','written':0,'category':'data','task':str(uuid4())}[fault],g.grant_id))
    with pytest.raises(RuntimeRefused):
        with opening(lineage,r):pass


@pytest.mark.parametrize('fault',['fresh_proof','history_proof','fresh_grant','history_manifest'])
def test_original_owner_record_substitution_refuses(lineage,fault):
    o,p,_,_,_=lineage;_,r=publish(lineage);m=o.a._market
    prefix='paper_market_consumption:' if fault.endswith('proof') else 'paper_market_job:'
    job=p['job_id'] if fault.startswith('fresh') else o.history['job_id']
    original=None
    if fault.endswith('proof'):
        with m.db:m.db.execute('DELETE FROM state WHERE key=?',(prefix+job,))
    else:
        value=m.records.read(job)
        original=canonical(value).decode()
        if fault=='fresh_grant':value['grant']['owner_instance']=str(uuid4())
        else:value['manifest']['sha256']='f'*64
        from compertum.runtime.paper_market_records import PREFIX
        with m.db:m.db.execute('UPDATE state SET value=? WHERE key=?',(canonical(value).decode(),PREFIX+job))
    try:
        with pytest.raises(RuntimeRefused):
            with opening(lineage,r):pass
    finally:
        # Undo this test's direct corruption so unrelated owner teardown can close.
        if original is not None:
            with m.db:m.db.execute('UPDATE state SET value=? WHERE key=?',(original,PREFIX+job))


@pytest.mark.parametrize('fault',['truncated','corrupt','trailing','oversize'])
def test_ciphertext_tamper_even_with_rewritten_ledger_refuses(lineage,fault):
    o,_,_,_,_=lineage;g,r=publish(lineage);path=o.manager.root/r['path'];raw=path.read_bytes()
    raw={'truncated':raw[:40],'corrupt':raw[:90]+bytes([raw[90]^255])+raw[91:],'trailing':raw+b'extra','oversize':b'x'*(3*1024**2+1)}[fault]
    path.write_bytes(raw);r.update(sha256=hashlib.sha256(raw).hexdigest(),size_bytes=len(raw))
    with o.manager.store.conn:o.manager.store.conn.execute('UPDATE reservations SET written=?,manifest=? WHERE id=?',(len(raw),canonical(r).decode(),g.grant_id))
    with pytest.raises(RuntimeRefused):
        with opening(lineage,r):pass


def test_history_encryption_cannot_be_relabelled_as_lineage(lineage):
    o,_,_,s,_=lineage;g,r=publish(lineage);m=o.a._market;h=m.records.read(o.history['job_id'])['manifest']
    raw=(o.manager.root/h['path']).read_bytes();(o.manager.root/r['path']).write_bytes(raw)
    r.update(sha256=hashlib.sha256(raw).hexdigest(),size_bytes=len(raw))
    with o.manager.store.conn:o.manager.store.conn.execute('UPDATE reservations SET written=?,manifest=? WHERE id=?',(len(raw),canonical(r).decode(),g.grant_id))
    with pytest.raises(RuntimeRefused):
        with opening(lineage,r):pass


def test_protection_rejects_changed_original_and_wipes_on_crypto_failure(lineage,monkeypatch):
    o,p,v,s,a=lineage;buffers=[]
    def fail(buffer,entropy,*,decrypt):buffers.append(buffer);raise RuntimeRefused('INJECTED_ENCRYPT_FAILURE')
    monkeypatch.setattr(a,'_crypt',fail)
    with pytest.raises(RuntimeRefused):a.protect_market_lineage(o.a._market,v,task_id=s.task_id,capture_id=s.capture_id)
    assert buffers and all(not any(b) for b in buffers)
    m=o.a._market
    with m.db:m.db.execute('DELETE FROM state WHERE key=?',('paper_market_consumption:'+p['job_id'],))
    buffers.clear()
    with pytest.raises(RuntimeRefused):a.protect_market_lineage(m,v,task_id=s.task_id,capture_id=s.capture_id)
    assert not buffers


@pytest.mark.parametrize('phase',['write','rename','index'])
def test_publication_retry_requires_committed_exact_bytes(lineage,monkeypatch,phase):
    from compertum.storage import BoundedWriter
    o,_,_,s,a=lineage;g=o.manager.reserve_bytes(s.task_id,'records',len(s.ciphertext));ow=BoundedWriter.write;op=BoundedWriter.publish
    def write(w,b):ow(w,b);raise RuntimeRefused('INJECTED_WRITE')
    def pub(w):
        if phase=='index':op(w)
        else:w.stream.close();w.path.rename(w.destination)
        raise RuntimeRefused('INJECTED_PUBLICATION')
    monkeypatch.setattr(BoundedWriter,'write' if phase=='write' else 'publish',write if phase=='write' else pub)
    with pytest.raises(RuntimeRefused):a.publish_market_lineage(o.manager,g,s)
    monkeypatch.setattr(BoundedWriter,'write',ow);monkeypatch.setattr(BoundedWriter,'publish',op)
    if phase=='index':
        r=a.publish_market_lineage(o.manager,g,s)
        with opening(lineage,r) as opened:assert opened.snapshot()['use']=='HISTORICAL_ONLY'
    else:
        with pytest.raises(RuntimeRefused):a.publish_market_lineage(o.manager,g,s)


@pytest.mark.parametrize('fault',['ledger','file','membership','closed'])
def test_held_history_is_revalidated_and_never_replaced(lineage,fault):
    o,_,_,_,_=lineage;_,r=publish(lineage);m=o.a._market;held=m._opened;h=held.publication();saved=None
    if fault=='ledger':
        with o.manager.store.conn:o.manager.store.conn.execute("UPDATE reservations SET status='ABANDONED' WHERE path=?",(h['path'],))
    elif fault=='file':
        path=o.manager.root/h['path'];saved=path.read_bytes();path.write_bytes(saved[:-1])
    elif fault=='membership':held._state.resources.remove(held)
    else:held.close()
    try:
        with pytest.raises(RuntimeRefused):
            with opening(lineage,r):pass
        assert m._opened is held
        if fault!='closed':assert not held._closed and any(held._buffer)
    finally:
        if fault=='membership':held._state.resources.append(held)
        elif fault=='file':path.write_bytes(saved)


@pytest.mark.parametrize('fault',['purpose','metadata','consumption','length','digest','trailing'])
def test_reencrypted_semantic_and_frame_tampering_refuses(lineage,fault):
    o,_,_,s,a=lineage;g,r=publish(lineage);entropy=a._context(s.project_id,s.account_alias,s.task_id,s.capture_id)
    plain=a._crypt(bytearray(s.ciphertext),entropy,decrypt=True);changed=bytearray();encrypted=bytearray()
    try:
        frames=a._frames(plain,entropy,cipher_size=len(s.ciphertext));meta=json.loads(frames[0]);value=json.loads(frames[1])
        if fault=='purpose':meta['purpose']='RESEARCH'
        elif fault=='metadata':meta['execution_generation']+=1
        elif fault=='consumption':value['consumption']['fresh']['elapsed_seconds']+=1
        frames=[canonical(meta),canonical(value)];changed=a._pack(frames,entropy)
        encrypted=a._crypt(changed,entropy,decrypt=False);size=len(encrypted);a._wipe(encrypted)
        changed[72:76]=(size+1 if fault=='length' else size).to_bytes(4,'big');a._digest(changed,entropy)
        if fault=='digest':changed[40]^=255
        elif fault=='trailing':changed.extend(b'x');a._digest(changed,entropy)
        encrypted=a._crypt(changed,entropy,decrypt=False);raw=bytes(encrypted)
        (o.manager.root/r['path']).write_bytes(raw);r.update(sha256=hashlib.sha256(raw).hexdigest(),size_bytes=len(raw))
        with o.manager.store.conn:o.manager.store.conn.execute('UPDATE reservations SET written=?,manifest=? WHERE id=?',(len(raw),canonical(r).decode(),g.grant_id))
        with pytest.raises(RuntimeRefused):
            with opening(lineage,r):pass
    finally:a._wipe(plain);a._wipe(changed);a._wipe(encrypted)


@pytest.mark.parametrize('borrowed',[True,False])
def test_consumer_exception_wipes_only_owned_resources(lineage,borrowed):
    o,_,_,_,_=lineage;_,r=publish(lineage);held=o.a._market._opened
    if not borrowed:
        o.a.close();o.a=o.module.PaperReadOwner(o.a.store,o.a.reserve,o.e)
        from test_paper_market_publication import command
        command(o,'status',job_id=o.history['job_id'])
    with pytest.raises(ValueError,match='CONSUMER_FAILURE'):
        with opening(lineage,r) as opened:
            buffer=opened._buffer;hbuffer=opened._history._buffer
            raise ValueError('CONSUMER_FAILURE')
    assert not any(buffer)
    if borrowed:assert not held._closed and any(hbuffer)
    else:assert not any(hbuffer)


@pytest.mark.parametrize('field',['artifact_id','path','sha256'])
def test_opened_reader_rejects_publication_identity_mutation(lineage,field):
    _,r=publish(lineage)
    with opening(lineage,r) as opened:
        opened._manifest[field]={'artifact_id':str(uuid4()),'path':'state/credentials.bin','sha256':'f'*64}[field]
        with pytest.raises(RuntimeRefused):opened.snapshot()
