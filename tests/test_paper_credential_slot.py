"""One native protected slot with invented keys; no credential discovery."""
import json,os,subprocess
from pathlib import Path
import pytest
from compertum.runtime.errors import RuntimeRefused
from compertum.runtime.paper_credential_slot import provision_paper_slot,load_paper_slot,SLOT_PATH
from compertum.runtime.paper_credentials import seal_paper_credentials,open_paper_credentials
from compertum.runtime.owners import acquire_owner,release_owner
from compertum.runtime.identity import resolve_project
from compertum.storage import reserve_runtime_paths
from test_persistence import owned
from test_storage import manager
from test_paper_read_preparation import KEY,SECRET

@pytest.fixture
def slot(owned):
    project,leases=owned;m=manager(owned);reserve_runtime_paths(m);lease=leases['execution']
    p=seal_paper_credentials(lease,'fixture',bytearray(KEY.encode()),bytearray(SECRET.encode()))
    return project,leases,m,p

def target(slot):return slot[0].root_path/SLOT_PATH
def store(slot):return provision_paper_slot(slot[1]['execution'],slot[3])


def test_native_slot_roundtrip_keeps_plaintext_out_of_file_and_database(slot):
    r=store(slot);raw=target(slot).read_bytes();p=load_paper_slot(slot[1]['execution'],'fixture')
    assert p==slot[3] and r['status']=='CREATED' and r['size_bytes']==len(raw)<=8192
    assert KEY.encode() not in raw and SECRET.encode() not in raw and 'ciphertext' not in r
    assert slot[2].store.conn.execute('SELECT maximum,status,category FROM reservations WHERE path=?',(SLOT_PATH,)).fetchall()==[(16384,'RUNTIME','records')]
    assert all(KEY not in str(row) and SECRET not in str(row) for row in slot[2].reservations())
    with open_paper_credentials(slot[1]['execution'],p) as opened:assert opened.headers()['APCA-API-SECRET-KEY']==SECRET


def test_exact_repeated_provision_does_not_rewrite(slot):
    r=store(slot);stamp=target(slot).stat().st_mtime_ns;again=store(slot)
    assert again['status']=='ALREADY_PRESENT' and again['ciphertext_sha256']==r['ciphertext_sha256'] and target(slot).stat().st_mtime_ns==stamp


def test_different_envelope_conflicts_without_rotation(slot):
    store(slot);raw=target(slot).read_bytes();lease=slot[1]['execution']
    other=seal_paper_credentials(lease,'fixture',bytearray(KEY.encode()),bytearray(SECRET.encode()))
    with pytest.raises(RuntimeRefused,match='CREDENTIAL_SLOT_CONFLICT'):provision_paper_slot(lease,other)
    assert target(slot).read_bytes()==raw


@pytest.mark.parametrize('role',['coordinator','evaluation'])
def test_wrong_owner_role_cannot_provision_or_load(slot,role):
    with pytest.raises(RuntimeRefused,match='WRONG_OWNER_ROLE'):provision_paper_slot(slot[1][role],slot[3])
    with pytest.raises(RuntimeRefused,match='WRONG_OWNER_ROLE'):load_paper_slot(slot[1][role],'fixture')


@pytest.mark.parametrize('fault',['missing','maximum','status','category','project'])
def test_exact_coordinator_reservation_is_required(slot,fault):
    db=slot[2].store.conn
    with db:
        if fault=='missing':db.execute('DELETE FROM reservations WHERE path=?',(SLOT_PATH,))
        elif fault=='project':db.execute("UPDATE metadata SET value=? WHERE key='project_id'",('f'*64,))
        else:db.execute('UPDATE reservations SET '+{'maximum':'maximum=8192','status':"status='PUBLISHED'",'category':"category='data'"}[fault]+' WHERE path=?',(SLOT_PATH,))
    with pytest.raises(RuntimeRefused):store(slot)
    assert not target(slot).exists()


@pytest.mark.parametrize('fault',['truncated','oversize','unknown','alias','cipher'])
def test_bad_or_changed_slot_is_refused(slot,fault):
    store(slot);path=target(slot);raw=path.read_bytes()
    if fault=='truncated':raw=raw[:-1]
    elif fault=='oversize':raw=b'x'*8193
    else:
        p=json.loads(raw)
        if fault=='unknown':p['extra']=True
        elif fault=='alias':p['account_alias']='other'
        else:p['ciphertext']='eA=='
        raw=json.dumps(p,sort_keys=True,separators=(',',':')).encode()
    path.write_bytes(raw)
    with pytest.raises(RuntimeRefused):load_paper_slot(slot[1]['execution'],'fixture')


@pytest.mark.parametrize('after',[False,True])
def test_retained_staging_blocks_load_and_further_publication(slot,after):
    if after:store(slot)
    staged=target(slot).with_name(target(slot).name+'.incoming-retained');staged.write_bytes(b'invented retained ciphertext')
    with pytest.raises(RuntimeRefused,match='CREDENTIAL_SLOT_STAGING_UNRESOLVED'):store(slot)
    with pytest.raises(RuntimeRefused,match='CREDENTIAL_SLOT_STAGING_UNRESOLVED'):load_paper_slot(slot[1]['execution'],'fixture')
    assert staged.read_bytes()==b'invented retained ciphertext'


@pytest.mark.parametrize('kind',['symlink','hardlink','directory'])
def test_slot_path_substitution_is_denied(slot,kind):
    path=target(slot)
    if kind=='directory':path.mkdir()
    else:
        source=path.with_name('synthetic-target.bin');source.write_bytes(b'synthetic')
        if kind=='symlink':path.symlink_to(source)
        else:os.link(source,path)
    with pytest.raises(RuntimeRefused):store(slot)
    with pytest.raises(RuntimeRefused):load_paper_slot(slot[1]['execution'],'fixture')


def test_metadata_alias_cannot_reflect_a_credential(slot):
    lease=slot[1]['execution'];p=seal_paper_credentials(lease,KEY,bytearray(KEY.encode()),bytearray(SECRET.encode()))
    with pytest.raises(RuntimeRefused,match='CREDENTIAL_SLOT_SECRET_REFLECTION'):provision_paper_slot(lease,p)
    assert not target(slot).exists()


@pytest.mark.parametrize('after_publish',[False,True])
def test_interrupted_publication_is_retained_without_blind_rewrite(slot,monkeypatch,after_publish):
    from compertum.runtime._windows import WindowsAPI
    original=WindowsAPI.publish_metadata
    def interrupted(api,path,data,**kwargs):
        if after_publish:original(api,path,data,**kwargs)
        else:path.with_name(path.name+'.incoming-interrupted').write_bytes(data)
        raise RuntimeRefused('INJECTED_PUBLICATION_FAILURE')
    monkeypatch.setattr(WindowsAPI,'publish_metadata',interrupted)
    with pytest.raises(RuntimeRefused):store(slot)
    monkeypatch.setattr(WindowsAPI,'publish_metadata',original)
    if after_publish:assert store(slot)['status']=='ALREADY_PRESENT'
    else:
        with pytest.raises(RuntimeRefused,match='CREDENTIAL_SLOT_STAGING_UNRESOLVED'):store(slot)
        assert len(list(target(slot).parent.glob(target(slot).name+'.incoming-*')))==1


def test_backup_lineage_excludes_runtime_slot_and_keeps_published_artifacts():
    from test_recovery_lineage import setup,collect
    from uuid import uuid4
    c,e,a=setup();c.execute('INSERT INTO reservations VALUES(?,?,?,?,?,?)',(str(uuid4()),SLOT_PATH,None,'records','RUNTIME',str(uuid4())))
    result=collect(c,e);assert [x['artifact_id'] for x in result['artifacts']]==[a['artifact_id']]
    assert SLOT_PATH not in json.dumps(result)


def test_native_new_execution_process_loads_existing_slot(tmp_path):
    code="""
from pathlib import Path
import sys,json
from compertum.runtime.identity import resolve_project
from compertum.runtime.owners import acquire_owner,release_owner
from compertum.config import load_config
from compertum.storage import StorageManager,reserve_runtime_paths
from compertum.runtime.paper_credentials import seal_paper_credentials
from compertum.runtime.paper_credential_slot import provision_paper_slot
root=Path(sys.argv[1]);project=resolve_project(root);c=acquire_owner(project,'coordinator');e=acquire_owner(project,'execution')
try:
 config=root/'config.toml';config.write_bytes(Path('config/default.toml').read_bytes());manager=StorageManager(c,load_config(config,root));reserve_runtime_paths(manager)
 p=seal_paper_credentials(e,'fixture',bytearray(b'DUMMY_KEY_123456789'),bytearray(b'DUMMY_SECRET_123456789'));print(json.dumps(provision_paper_slot(e,p)))
finally:release_owner(e);release_owner(c)
"""
    from test_fixture_processes import fixture_module
    child=fixture_module().python_process(['-B','-c',code,str(tmp_path)],env={k:v for k,v in os.environ.items() if k.upper() in {'SYSTEMROOT','WINDIR','PYTHONPATH','PYTHONDONTWRITEBYTECODE','PYTHONNOUSERSITE'}},stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    try:out,err=child.communicate(timeout=20)
    except subprocess.TimeoutExpired:child.kill();child.communicate();raise
    assert child.returncode==0,err
    lease=acquire_owner(resolve_project(tmp_path),'execution')
    try:
        p=load_paper_slot(lease,'fixture');assert lease.generation==2
        with open_paper_credentials(lease,p) as opened:assert opened.headers()['APCA-API-SECRET-KEY']==SECRET
        assert KEY not in out and SECRET not in out and json.loads(out)['status']=='CREATED'
    finally:release_owner(lease)


def test_missing_slot_is_explicit_without_side_effect(slot):
    with pytest.raises(RuntimeRefused,match='CREDENTIAL_SLOT_MISSING'):load_paper_slot(slot[1]['execution'],'fixture')
    assert not target(slot).exists()


def test_wrong_requested_alias_does_not_load_existing_credentials(slot):
    store(slot)
    with pytest.raises(RuntimeRefused):load_paper_slot(slot[1]['execution'],'other')


def test_staging_allocation_is_charged_together_with_target(slot):
    from compertum.watchdog import check_storage
    m=slot[2];before=m.observation();store(slot);path=target(slot)
    first=path.with_name(path.name+'.incoming-first');first.write_bytes(b'x'*8192)
    observed=m.observation();assert check_storage(observed,m.reservations(),previous=before)['status']=='STORAGE_OBSERVED'
    path.with_name(path.name+'.incoming-second').write_bytes(b'x'*8192)
    observed=m.observation();assert check_storage(observed,m.reservations(),previous=before)['reason']=='UNACCOUNTED_GROWTH'


def test_late_different_slot_is_never_overwritten(slot,monkeypatch):
    from compertum.runtime._windows import WindowsAPI
    from compertum.runtime.paper_credential_slot import _payload
    other=seal_paper_credentials(slot[1]['execution'],'fixture',bytearray(KEY.encode()),bytearray(SECRET.encode()))
    late=_payload(other);original=WindowsAPI.publish_metadata
    def appear(api,path,data,**kwargs):
        path.write_bytes(late)
        return original(api,path,data,**kwargs)
    monkeypatch.setattr(WindowsAPI,'publish_metadata',appear)
    with pytest.raises(RuntimeRefused):store(slot)
    assert target(slot).read_bytes()==late
    staged=list(target(slot).parent.glob(target(slot).name+'.incoming-*'))
    assert len(staged)==1 and staged[0].read_bytes()==_payload(slot[3])
    with pytest.raises(RuntimeRefused,match='CREDENTIAL_SLOT_STAGING_UNRESOLVED'):store(slot)


def test_database_pin_blocks_late_path_substitution_after_coordinator_release(slot,monkeypatch):
    import sqlite3
    import compertum.runtime.paper_credential_slot as module
    database=slot[2].store.path
    release_owner(slot[1]['coordinator'])
    source=database.with_name('replacement-source.sqlite');source.write_bytes(database.read_bytes())
    replacement=database.with_name('replacement.sqlite');os.link(source,replacement)
    original=sqlite3.connect;attempts=[]
    def late_connect(path,*args,**kwargs):
        if str(path).startswith(database.as_uri()):
            try:
                os.rename(database,database.with_name('displaced-original.sqlite'))
                os.rename(replacement,database)
            except PermissionError:attempts.append('BLOCKED')
            else:attempts.append('REPLACED')
        return original(path,*args,**kwargs)
    monkeypatch.setattr(module.sqlite3,'connect',late_connect)
    assert store(slot)['status']=='CREATED'
    assert attempts==['BLOCKED']
    assert database.stat().st_nlink==1



def test_restored_generation_parents_stay_pinned_during_database_read(slot,monkeypatch):
    from uuid import uuid4
    import compertum.runtime.paper_credential_slot as module
    database=slot[2].store.path;release_owner(slot[1]['coordinator'])
    generation=str(uuid4());directory=database.parent/'generations'/generation;directory.mkdir(parents=True)
    restored=directory/database.name;restored.write_bytes(database.read_bytes())
    (database.parent/'active-generation.json').write_text(json.dumps(dict(schema_version=1,project_id=slot[0].project_id,generation=generation,operation_id=str(uuid4()))))
    original=module.sqlite3.connect;attempts=[]
    def late_connect(path,*args,**kwargs):
        if str(path).startswith(restored.as_uri()):
            for parent in (directory,directory.parent):
                try:os.rename(parent,parent.with_name(parent.name+'-displaced'))
                except PermissionError:attempts.append('BLOCKED')
                else:attempts.append('MOVED')
        return original(path,*args,**kwargs)
    monkeypatch.setattr(module.sqlite3,'connect',late_connect)
    assert store(slot)['status']=='CREATED'
    assert load_paper_slot(slot[1]['execution'],'fixture')==slot[3]
    assert attempts==['BLOCKED']*4
