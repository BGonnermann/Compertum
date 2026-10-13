"""Native historical read evidence with invented account replies only."""
import hashlib,json,pickle,os
from dataclasses import replace
from uuid import uuid4
import pytest
from compertum.runtime.errors import RuntimeRefused
from compertum.runtime.paper_read_evidence import protect_read_evidence,publish_read_evidence,open_read_evidence
from compertum.runtime.paper_credentials import seal_paper_credentials
from compertum.runtime.owners import release_owner
from test_persistence import owned
from test_storage import manager
from test_paper_read_packet import packet,step,prefix,order,KEY,SECRET,ACCOUNT

@pytest.fixture
def evidence(owned):
    project,leases=owned;m=manager(owned);e=leases['execution']
    protected=seal_paper_credentials(e,'fixture',bytearray(KEY.encode()),bytearray(SECRET.encode()))
    p=packet((project,e,protected))
    for i in range(6):step(p,i)
    task=str(uuid4());packet_id=str(uuid4());sealed=protect_read_evidence(e,p,task_id=task,packet_id=packet_id)
    return project,leases,m,p,sealed

def publish(evidence):
    _,_,m,_,sealed=evidence;g=m.reserve_bytes(sealed.task_id,'records',len(sealed.ciphertext))
    return g,publish_read_evidence(m,g,sealed)

def opened(evidence,receipt):
    return open_read_evidence(evidence[1]['execution'],'fixture',evidence[4].packet_id,receipt)


def test_native_publish_reopen_retains_exact_private_frames(evidence):
    project,leases,m,p,sealed=evidence;grant,receipt=publish(evidence);raw=(project.root_path/receipt['path']).read_bytes()
    assert raw==sealed.ciphertext and 0<len(raw)<=3*1024**2
    assert all(x.encode() not in raw for x in (KEY,SECRET,ACCOUNT))
    assert all(x not in json.dumps(receipt) for x in (KEY,SECRET,ACCOUNT))
    with opened(evidence,receipt) as private:
        snap=private.snapshot();assert snap['metadata']['status']==p.status() and len(snap['records'])==6
        assert [x['raw'] for x in snap['records']]==[x.raw for x in p.private_evidence()]
        assert [x['request'] for x in snap['records']]==[x.request.to_payload() for x in p.private_evidence()]
        assert snap['metadata']['status']['financial_accepted'] is False
        buffer=private._buffer;assert any(buffer)
        with pytest.raises(RuntimeRefused):pickle.dumps(private)
    assert not any(buffer)
    with pytest.raises(RuntimeRefused):private.snapshot()
    assert m.reservations()[0]['status']=='PUBLISHED'


def test_exact_ciphertext_is_idempotent_and_reseal_conflicts(evidence):
    _,leases,m,p,sealed=evidence;g,r=publish(evidence);assert publish_read_evidence(m,g,sealed)==r
    again=protect_read_evidence(leases['execution'],p,task_id=sealed.task_id,packet_id=sealed.packet_id)
    assert again.ciphertext!=sealed.ciphertext
    with pytest.raises(RuntimeRefused):publish_read_evidence(m,g,again)
    assert (m.root/r['path']).read_bytes()==sealed.ciphertext


@pytest.mark.parametrize('role',['coordinator','evaluation'])
def test_wrong_role_cannot_seal_or_load(evidence,role):
    _,leases,_,p,sealed=evidence;_,r=publish(evidence)
    with pytest.raises(RuntimeRefused):protect_read_evidence(leases[role],p,task_id=sealed.task_id,packet_id=sealed.packet_id)
    with pytest.raises(RuntimeRefused):
        with open_read_evidence(leases[role],'fixture',sealed.packet_id,r):pass


@pytest.mark.parametrize('fault',['alias','packet','path','hash','size','task'])
def test_changed_context_or_manifest_is_refused(evidence,fault):
    _,_,_,_,sealed=evidence;_,r=publish(evidence);alias='fixture';packet_id=sealed.packet_id
    if fault=='alias':alias='other'
    elif fault=='packet':packet_id=str(uuid4())
    elif fault=='path':r['path']='state/paper-credentials.bin'
    elif fault=='hash':r['sha256']='f'*64
    elif fault=='size':r['size_bytes']+=1
    else:r['task_id']=str(uuid4())
    with pytest.raises(RuntimeRefused):
        with open_read_evidence(evidence[1]['execution'],alias,packet_id,r):pass


@pytest.mark.parametrize('fault',['truncated','corrupt','trailing','oversize'])
def test_corrupted_ciphertext_never_exposes_data(evidence,fault):
    project,_,_,_,_=evidence;_,r=publish(evidence);path=project.root_path/r['path'];raw=path.read_bytes()
    if fault=='truncated':raw=raw[:40]
    elif fault=='corrupt':raw=raw[:90]+bytes([raw[90]^255])+raw[91:]
    elif fault=='trailing':raw+=b'trailing'
    else:raw=b'x'*(3*1024**2+1)
    path.write_bytes(raw);r['sha256']=hashlib.sha256(raw).hexdigest();r['size_bytes']=len(raw)
    with pytest.raises(RuntimeRefused):
        with opened(evidence,r):pass


def test_owner_release_wipes_open_private_buffer(evidence):
    _,r=publish(evidence)
    with opened(evidence,r) as private:
        buffer=private._buffer;release_owner(evidence[1]['execution']);assert not any(buffer)
        with pytest.raises(RuntimeRefused):private.snapshot()


def test_credential_wrapper_still_refuses_more_than_8192_bytes():
    from compertum.runtime.paper_credentials import _crypt
    with pytest.raises(RuntimeRefused):_crypt(bytearray(8193),b'fixture',decrypt=False)


def test_unfinished_or_closed_packet_cannot_be_sealed(evidence):
    _,leases,_,p,sealed=evidence;p.close()
    with pytest.raises(RuntimeRefused):protect_read_evidence(leases['execution'],p,task_id=sealed.task_id,packet_id=sealed.packet_id)


@pytest.mark.parametrize('state',['INCOMPLETE','ABORTED'])
def test_terminal_failure_state_is_retained_as_historical_only(evidence,state):
    project,leases,m,p,old=evidence;p.close();e=leases['execution']
    protected=seal_paper_credentials(e,'fixture',bytearray(KEY.encode()),bytearray(SECRET.encode()));p=packet((project,e,protected));prefix(p)
    if state=='INCOMPLETE':step(p,4,data=[order(1),order(1)])
    else:p.issue(now='2023-11-24T14:30:00Z',request_id=str(uuid4()));p.fail_pending()
    sealed=protect_read_evidence(e,p,task_id=str(uuid4()),packet_id=str(uuid4()));g=m.reserve_bytes(sealed.task_id,'records',len(sealed.ciphertext));r=publish_read_evidence(m,g,sealed)
    with open_read_evidence(e,'fixture',sealed.packet_id,r) as private:
        status=private.snapshot()['metadata']['status'];assert status['state']==state and status['financial_accepted'] is False and status['actual_flat'] is None


@pytest.mark.parametrize('field',['task_id','packet_id'])
def test_new_metadata_cannot_reflect_a_credential(evidence,field):
    project,leases,m,p,_=evidence;p.close();key=str(uuid4());e=leases['execution']
    protected=seal_paper_credentials(e,'fixture',bytearray(key.encode()),bytearray(SECRET.encode()));p=packet((project,e,protected))
    for i in range(6):step(p,i)
    ids=dict(task_id=str(uuid4()),packet_id=str(uuid4()));ids[field]=key
    with pytest.raises(RuntimeRefused,match='SECRET_REFLECTION'):protect_read_evidence(e,p,**ids)
    assert not (m.root/'artifacts').exists()


def test_native_maximum_evidence_crypto_and_unchanged_credential_limit():
    from compertum.runtime.paper_read_evidence import _crypt_evidence
    from compertum.runtime.paper_credentials import _wipe
    plain=bytearray(b'x'*(2*1024**2));encrypted=bytearray();restored=bytearray()
    try:
        encrypted=_crypt_evidence(plain,b'private evidence fixture',decrypt=False)
        assert 2*1024**2<len(encrypted)<=3*1024**2
        restored=_crypt_evidence(encrypted,b'private evidence fixture',decrypt=True);assert restored==plain
        for n,decrypt in ((2*1024**2+1,False),(3*1024**2+1,True)):
            with pytest.raises(RuntimeRefused):_crypt_evidence(bytearray(n),b'fixture',decrypt=decrypt)
    finally:_wipe(plain);_wipe(encrypted);_wipe(restored)


@pytest.mark.parametrize('fault',['count','length','missing','trailing','digest','order','duplicate','account','financial','state'])
def test_authenticated_framing_and_semantic_inconsistency_are_rejected(evidence,fault):
    import compertum.runtime.paper_read_evidence as module
    from compertum.data.encoding import canonical
    s=evidence[4];entropy=module._context(s.project_id,s.account_alias,s.task_id,s.packet_id)
    plain=module._crypt_evidence(bytearray(s.ciphertext),entropy,decrypt=True)
    try:
        if fault in ('count','length','missing','trailing','digest'):
            if fault=='count':plain[72:74]=(42).to_bytes(2,'big')
            elif fault=='length':plain[78:82]=(65537).to_bytes(4,'big')
            elif fault=='missing':plain.pop()
            elif fault=='trailing':plain.extend(b'extra')
            else:plain[40]^=255
            if fault!='digest':
                h=hashlib.sha256(entropy);h.update(memoryview(plain)[72:]);plain[40:72]=h.digest()
            with pytest.raises(RuntimeRefused):module._frames(plain,entropy)
        else:
            frames=module._frames(plain,entropy);meta=json.loads(frames[0])
            if fault=='order':frames[2:5],frames[5:8]=frames[5:8],frames[2:5]
            elif fault=='duplicate':frames[5:8]=frames[2:5]
            elif fault=='account':meta['contexts'][1]['expected_account_id']=str(uuid4())
            elif fault=='financial':meta['status']['financial_accepted']=True
            else:meta['status']['state']='READY'
            frames[0]=canonical(meta)
            with pytest.raises((RuntimeRefused,ValueError)):
                module._validate(frames,s.project_id,s.account_alias,s.task_id,s.packet_id)
    finally:module._wipe(plain)


@pytest.mark.parametrize('phase',['write','rename','index'])
def test_interrupted_publication_retains_ciphertext_and_refuses_blind_retry(evidence,monkeypatch,phase):
    from compertum.storage import BoundedWriter
    _,_,m,_,s=evidence;g=m.reserve_bytes(s.task_id,'records',len(s.ciphertext));original_write=BoundedWriter.write;original_publish=BoundedWriter.publish
    def failed_write(w,chunk):original_write(w,chunk);raise RuntimeRefused('INJECTED_WRITE')
    def failed_publish(w):
        if phase=='index':original_publish(w)
        else:w.stream.close();w.path.rename(w.destination)
        raise RuntimeRefused('INJECTED_PUBLICATION')
    monkeypatch.setattr(BoundedWriter,'write' if phase=='write' else 'publish',failed_write if phase=='write' else failed_publish)
    with pytest.raises(RuntimeRefused):publish_read_evidence(m,g,s)
    monkeypatch.setattr(BoundedWriter,'write',original_write);monkeypatch.setattr(BoundedWriter,'publish',original_publish)
    files=list((m.root/'artifacts/runs'/s.task_id).iterdir());assert len(files)==1 and files[0].read_bytes()==s.ciphertext
    if phase=='index':assert publish_read_evidence(m,g,s)['sha256']==hashlib.sha256(s.ciphertext).hexdigest()
    else:
        with pytest.raises(RuntimeRefused):publish_read_evidence(m,g,s)
        assert m.reservations()[0]['status']=='ABANDONED'


@pytest.mark.parametrize('kind',['hardlink','symlink','directory'])
def test_evidence_path_substitution_is_denied(evidence,kind):
    project,_,_,_,_=evidence;_,r=publish(evidence);path=project.root_path/r['path'];other=path.with_name('preserved.bin');path.rename(other)
    if kind=='hardlink':os.link(other,path)
    elif kind=='symlink':path.symlink_to(other)
    else:path.mkdir()
    with pytest.raises(RuntimeRefused):
        with opened(evidence,r):pass


def test_published_encrypted_artifact_is_included_in_backup_lineage(evidence):
    from test_recovery_lineage import setup,collect
    from compertum.data.encoding import canonical
    from compertum.runtime.paper_credential_slot import SLOT_PATH
    _,r=publish(evidence);c,e,a=setup()
    c.execute('INSERT INTO reservations VALUES(?,?,?,?,?,?)',(r['task_id'],r['path'],canonical(r).decode(),'records','PUBLISHED',str(uuid4())))
    c.execute('INSERT INTO reservations VALUES(?,?,?,?,?,?)',(str(uuid4()),SLOT_PATH,None,'records','RUNTIME',str(uuid4())))
    result=collect(c,e);entry=next(x for x in result['artifacts'] if x['artifact_id']==r['artifact_id'])
    assert all(entry[k]==r[k] for k in ('artifact_id','path','size_bytes','sha256')) and SLOT_PATH not in json.dumps(result)


def test_thirteen_large_raw_replies_roundtrip_in_one_bounded_artifact(evidence):
    project,leases,m,p,_=evidence;p.close();e=leases['execution']
    protected=seal_paper_credentials(e,'fixture',bytearray(KEY.encode()),bytearray(SECRET.encode()));p=packet((project,e,protected));prefix(p)
    for page in range(8):
        rows=[order(page*25+i) for i in range(25 if page<7 else 24)];rows[0]['unknown_padding']='x'*35000;step(p,4+page,data=rows)
    step(p,12);s=protect_read_evidence(e,p,task_id=str(uuid4()),packet_id=str(uuid4()));g=m.reserve_bytes(s.task_id,'records',len(s.ciphertext));r=publish_read_evidence(m,g,s)
    with open_read_evidence(e,'fixture',s.packet_id,r) as private:
        snap=private.snapshot();assert len(snap['records'])==13 and sum(len(x['raw']) for x in snap['records'])>280000


def test_grant_must_match_task_category_and_exact_cipher_bound(evidence):
    _,_,m,_,s=evidence
    for task,category,size in ((str(uuid4()),'records',len(s.ciphertext)),(s.task_id,'data',len(s.ciphertext)),(s.task_id,'records',len(s.ciphertext)+1)):
        g=m.reserve_bytes(task,category,size)
        with pytest.raises(RuntimeRefused):publish_read_evidence(m,g,s)
    assert not (m.root/'artifacts').exists()


def test_native_child_exit_reopens_without_credential_slot_or_key_input(tmp_path):
    import subprocess
    from compertum.runtime.identity import resolve_project
    from compertum.runtime.owners import acquire_owner
    from compertum.runtime.paper_credential_slot import SLOT_PATH
    code="""
from pathlib import Path
import sys,json
sys.path.insert(0,str(Path('tests').resolve()))
from uuid import uuid4
from test_paper_read_packet import packet,step,KEY,SECRET
from compertum.runtime.identity import resolve_project
from compertum.runtime.owners import acquire_owner,release_owner
from compertum.runtime.paper_credentials import seal_paper_credentials
from compertum.runtime.paper_read_evidence import protect_read_evidence,publish_read_evidence
from compertum.config import load_config
from compertum.storage import StorageManager
root=Path(sys.argv[1]);project=resolve_project(root);c=acquire_owner(project,'coordinator');e=acquire_owner(project,'execution')
try:
 config=root/'config.toml';config.write_bytes(Path('config/default.toml').read_bytes());m=StorageManager(c,load_config(config,root))
 credential=seal_paper_credentials(e,'fixture',bytearray(KEY.encode()),bytearray(SECRET.encode()));p=packet((project,e,credential))
 for i in range(6):step(p,i)
 sealed=protect_read_evidence(e,p,task_id=str(uuid4()),packet_id=str(uuid4()));g=m.reserve_bytes(sealed.task_id,'records',len(sealed.ciphertext));receipt=publish_read_evidence(m,g,sealed)
 print(json.dumps(dict(packet_id=sealed.packet_id,manifest=receipt)))
finally:release_owner(e);release_owner(c)
"""
    from test_fixture_processes import fixture_module
    child=fixture_module().python_process(['-B','-c',code,str(tmp_path)],env={k:v for k,v in os.environ.items() if k.upper() in {'SYSTEMROOT','WINDIR','PYTHONPATH','PYTHONDONTWRITEBYTECODE','PYTHONNOUSERSITE'}},stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    try:out,err=child.communicate(timeout=20)
    except subprocess.TimeoutExpired:child.kill();child.communicate();raise
    assert child.returncode==0,err
    result=json.loads(out);e=acquire_owner(resolve_project(tmp_path),'execution')
    try:
        assert e.generation==2 and not (tmp_path/SLOT_PATH).exists() and all(x not in out for x in (KEY,SECRET,ACCOUNT))
        with open_read_evidence(e,'fixture',result['packet_id'],result['manifest']) as private:
            data=private.snapshot();assert data['metadata']['execution_generation']==1 and len(data['records'])==6
    finally:release_owner(e)


def test_sealing_holds_owner_lock_against_concurrent_packet_cleanup(evidence,monkeypatch):
    import threading
    import compertum.runtime.paper_read_evidence as module
    _,leases,_,p,s=evidence;original=module._crypt_evidence;attempt=threading.Event();done=threading.Event();threads=[]
    def close():attempt.set();p.close();done.set()
    def seal(buffer,entropy,**kwargs):
        if not threads:
            thread=threading.Thread(target=close);threads.append(thread);thread.start();assert attempt.wait(2) and not done.is_set()
        return original(buffer,entropy,**kwargs)
    monkeypatch.setattr(module,'_crypt_evidence',seal)
    protected=protect_read_evidence(leases['execution'],p,task_id=s.task_id,packet_id=s.packet_id)
    for thread in threads:thread.join(2)
    assert done.is_set() and protected.ciphertext


def test_wrong_project_and_credential_purpose_do_not_decrypt(evidence,tmp_path):
    import compertum.runtime.paper_read_evidence as module
    from compertum.runtime.paper_credentials import _crypt,_context
    s=evidence[4];entropy=module._context('f'*64,s.account_alias,s.task_id,s.packet_id)
    with pytest.raises(RuntimeRefused):module._crypt_evidence(bytearray(s.ciphertext),entropy,decrypt=True)
    with pytest.raises(RuntimeRefused):_crypt(bytearray(s.ciphertext[:8192]),_context(s.project_id,s.account_alias),decrypt=True)


def test_changed_artifact_identity_cannot_load_published_bytes(evidence):
    _,r=publish(evidence);r['artifact_id']=str(uuid4())
    with pytest.raises(RuntimeRefused):
        with opened(evidence,r):pass


def test_unindexed_renamed_ciphertext_cannot_be_adopted_by_made_up_manifest(evidence,monkeypatch):
    from compertum.storage import BoundedWriter
    _,_,m,_,s=evidence;g=m.reserve_bytes(s.task_id,'records',len(s.ciphertext))
    def incomplete(w):w.stream.close();w.path.rename(w.destination);raise RuntimeRefused('INJECTED_RENAME')
    monkeypatch.setattr(BoundedWriter,'publish',incomplete)
    with pytest.raises(RuntimeRefused):publish_read_evidence(m,g,s)
    path=next((m.root/'artifacts/runs'/s.task_id).iterdir())
    r=dict(artifact_id=str(uuid4()),task_id=s.task_id,path=path.relative_to(m.root).as_posix(),size_bytes=len(s.ciphertext),sha256=hashlib.sha256(s.ciphertext).hexdigest())
    with pytest.raises(RuntimeRefused):
        with open_read_evidence(evidence[1]['execution'],'fixture',s.packet_id,r):pass


def test_maximum_unsupported_pages_preserve_every_deficiency(evidence):
    project,leases,m,p,_=evidence;p.close();e=leases['execution']
    protected=seal_paper_credentials(e,'fixture',bytearray(KEY.encode()),bytearray(SECRET.encode()));p=packet((project,e,protected));prefix(p)
    for page in range(8):
        rows=[order(page*25+i,asset_class='crypto',order_class='bracket',client_order_id='foreign-'+str(page*25+i)) for i in range(25 if page<7 else 24)]
        step(p,4+page,data=rows)
    step(p,12);status=p.status();assert len(status['deficiencies'])==597
    s=protect_read_evidence(e,p,task_id=str(uuid4()),packet_id=str(uuid4()));g=m.reserve_bytes(s.task_id,'records',len(s.ciphertext));r=publish_read_evidence(m,g,s)
    with open_read_evidence(e,'fixture',s.packet_id,r) as private:assert private.snapshot()['metadata']['status']==status


def test_native_trailing_ciphertext_is_rejected_by_authenticated_length(evidence):
    import compertum.runtime.paper_read_evidence as module
    s=evidence[4];entropy=module._context(s.project_id,s.account_alias,s.task_id,s.packet_id)
    appended=bytearray(s.ciphertext+b'trailing');plain=module._crypt_evidence(appended,entropy,decrypt=True)
    try:
        with pytest.raises(RuntimeRefused):module._frames(plain,entropy,cipher_size=len(appended))
    finally:module._wipe(plain)


@pytest.mark.parametrize('fault',['missing','status','written','category','task','duplicate'])
def test_exact_durable_publication_is_required_for_loading(evidence,fault):
    _,_,m,_,s=evidence;g,r=publish(evidence);db=m.store.conn
    with db:
        if fault=='missing':db.execute('DELETE FROM reservations WHERE id=?',(g.grant_id,))
        elif fault=='duplicate':db.execute('INSERT INTO reservations SELECT ?,task,category,maximum,written,status,path,manifest FROM reservations WHERE id=?',(str(uuid4()),g.grant_id))
        else:
            value={'status':'ABANDONED','written':0,'category':'data','task':str(uuid4())}[fault]
            db.execute('UPDATE reservations SET '+fault+'=? WHERE id=?',(value,g.grant_id))
    with pytest.raises(RuntimeRefused):
        with opened(evidence,r):pass


def test_consumer_exception_is_preserved_and_private_buffer_is_wiped(evidence):
    _,r=publish(evidence);failure=ValueError('invented consumer failure')
    with pytest.raises(ValueError) as caught:
        with opened(evidence,r) as private:
            buffer=private._buffer
            raise failure
    assert caught.value is failure and not any(buffer)
