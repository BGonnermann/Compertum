"""Locked archive bytes, relocated payloads and complete import inventories."""
import hashlib,json,stat,zipfile
from pathlib import Path
import pytest
from compertum.data.encoding import canonical
from compertum.data.errors import DataError
from compertum.environment_payloads import wheel_payload_manifest,read_wheel_manifest,verify_installed_payloads


def make_wheel(tmp_path,*,members=None,metadata='Name: example\nVersion: 1.0\n',wheel='Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n'):
    path=tmp_path/'example-1.0-py3-none-any.whl'
    entries={'example/__init__.py':b'VALUE = 7\n','example/native.pyd':b'synthetic native payload',
        'example-1.0.dist-info/METADATA':metadata.encode(),'example-1.0.dist-info/WHEEL':wheel.encode(),'example-1.0.dist-info/RECORD':b'installer rewrites this inventory\n'}
    entries.update(members or {})
    with zipfile.ZipFile(path,'w') as z:
        for name,raw in entries.items():
            info=zipfile.ZipInfo(name);info.filename=name;info.orig_filename=name;z.writestr(info,raw)
    return path,entries


def manifest(path,**kwargs):
    return wheel_payload_manifest(path,expected_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),expected_size=path.stat().st_size,name='example',version='1.0',**kwargs)


def install(tmp_path,entries):
    prefix=tmp_path/'environment';site=prefix/'Lib/site-packages';site.mkdir(parents=True)
    schemes={'purelib':site,'platlib':site,'data':prefix,'scripts':prefix/'Scripts','headers':prefix/'Include'}
    for name,raw in entries.items():
        parts=name.split('/')
        target=schemes[parts[1]]/Path(*parts[2:]) if parts[0].endswith('.data') else site/Path(*parts)
        target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
    return schemes


def test_payloads_match_actual_archive_and_installed_bytes(tmp_path):
    path,entries=make_wheel(tmp_path);value=manifest(path);decoded=read_wheel_manifest(value.content,expected_sha256=value.sha256)
    schemes=install(tmp_path,entries);(schemes['purelib']/'example-1.0.dist-info/RECORD').write_text('rewritten by installer')
    report=verify_installed_payloads([decoded],schemes)
    assert report['status']=='LOCKED_PAYLOAD_BYTES_VERIFIED' and report['payload_files']==4
    assert report['payload_bytes']==sum(len(v) for k,v in entries.items() if not k.endswith('/RECORD'))
    assert report['required_cache_policy']=='ISOLATED_EMPTY_PREFIX_NO_WRITE'
    assert report['campaign_admitted'] is False


@pytest.mark.parametrize('field,value',[('expected_sha256','0'*64),('expected_size',1),('expected_size',True),('name','wrong'),('version','2.0')])
def test_wrong_archive_or_distribution_is_refused(tmp_path,field,value):
    path,_=make_wheel(tmp_path);args=dict(expected_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),expected_size=path.stat().st_size,name='example',version='1.0');args[field]=value
    with pytest.raises(DataError):wheel_payload_manifest(path,**args)


@pytest.mark.parametrize('name',['../escape.py','/absolute.py','C:/drive.py','example\\escape.py','example/../escape.py','example/CON.py','example/space.py ','EXAMPLE/__INIT__.PY'])
def test_unsafe_or_case_colliding_wheel_members_refused(tmp_path,name):
    path,_=make_wheel(tmp_path,members={name:b'bad'})
    with pytest.raises(DataError):manifest(path)


def test_duplicate_archive_member_refused(tmp_path):
    path,_=make_wheel(tmp_path)
    with zipfile.ZipFile(path,'a') as z:
        with pytest.warns(UserWarning):z.writestr('example/__init__.py',b'replaced')
    with pytest.raises(DataError):manifest(path)


def test_link_member_refused(tmp_path):
    path,_=make_wheel(tmp_path)
    with zipfile.ZipFile(path,'a') as z:
        info=zipfile.ZipInfo('example/link.py');info.create_system=3;info.external_attr=(stat.S_IFLNK|0o777)<<16;z.writestr(info,'../elsewhere')
    with pytest.raises(DataError):manifest(path)


@pytest.mark.parametrize('wheel',['Wheel-Version: 2.0\nRoot-Is-Purelib: true\n','Wheel-Version: 1.0\nRoot-Is-Purelib: maybe\n','Wheel-Version: 1.0\nRoot-Is-Purelib: true\nRoot-Is-Purelib: false\n'])
def test_ambiguous_install_scheme_refused(tmp_path,wheel):
    path,_=make_wheel(tmp_path,wheel=wheel)
    with pytest.raises(DataError):manifest(path)


def test_data_relocation_preserves_payload_pin(tmp_path):
    name='example-1.0.data/data/share/man/example.1';path,entries=make_wheel(tmp_path,members={name:b'manual'})
    value=manifest(path);decoded=read_wheel_manifest(value.content,expected_sha256=value.sha256)
    assert any(f['scheme']=='data' and f['path']=='share/man/example.1' for f in decoded['files'])
    report=verify_installed_payloads([decoded],install(tmp_path,entries));assert report['payload_files']==5


@pytest.mark.parametrize('change',['corrupt','missing','added_import','added_pth','sourceless','archive'])
def test_actual_payload_and_inventory_changes_refused(tmp_path,change):
    path,entries=make_wheel(tmp_path);value=manifest(path);decoded=read_wheel_manifest(value.content,expected_sha256=value.sha256);schemes=install(tmp_path,entries);site=schemes['purelib']
    if change=='corrupt':(site/'example/native.pyd').write_bytes(b'changed bytes')
    elif change=='missing':(site/'example/native.pyd').unlink()
    else:(site/{'added_import':'foreign.py','added_pth':'foreign.pth','sourceless':'foreign.pyc','archive':'foreign.zip'}[change]).write_bytes(b'extra')
    with pytest.raises(DataError):verify_installed_payloads([decoded],schemes)


def test_generated_bootstrap_requires_exact_extra_pin(tmp_path):
    path,entries=make_wheel(tmp_path);value=manifest(path);decoded=read_wheel_manifest(value.content,expected_sha256=value.sha256);schemes=install(tmp_path,entries)
    payload=b'import _virtualenv\n';target=schemes['purelib']/'_virtualenv.pth';target.write_bytes(payload)
    pin={'scheme':'purelib','path':'_virtualenv.pth','sha256':hashlib.sha256(payload).hexdigest(),'size_bytes':len(payload)}
    with pytest.raises(DataError):verify_installed_payloads([decoded],schemes)
    assert verify_installed_payloads([decoded],schemes,additional_files=[pin])['additional_files']==1
    target.write_bytes(b'import foreign\n')
    with pytest.raises(DataError):verify_installed_payloads([decoded],schemes,additional_files=[pin])


def test_existing_source_cache_is_inventory_only_and_requires_isolation(tmp_path):
    path,entries=make_wheel(tmp_path);value=manifest(path);decoded=read_wheel_manifest(value.content,expected_sha256=value.sha256);schemes=install(tmp_path,entries)
    cache=schemes['purelib']/'example/__pycache__';cache.mkdir();(cache/'__init__.cpython-314.pyc').write_bytes(b'old cache must never be loaded')
    report=verify_installed_payloads([decoded],schemes)
    assert report['inactive_cache_files']==1 and report['required_cache_policy']=='ISOLATED_EMPTY_PREFIX_NO_WRITE'
    (cache/'foreign.cpython-314.pyc').write_bytes(b'no corresponding pinned source')
    with pytest.raises(DataError):verify_installed_payloads([decoded],schemes)


def test_rehashed_manifest_cannot_escape_or_misstate_types(tmp_path):
    path,_=make_wheel(tmp_path);value=manifest(path);original=json.loads(value.content)
    for field,bad in [('path','../escape.py'),('size_bytes',True),('sha256','bad'),('scheme','arbitrary')]:
        changed=json.loads(value.content);changed['files'][0][field]=bad;raw=canonical(changed)
        with pytest.raises(DataError):read_wheel_manifest(raw,expected_sha256=hashlib.sha256(raw).hexdigest())
    assert original==read_wheel_manifest(value.content,expected_sha256=value.sha256)


def test_installed_parent_link_escape_refused(tmp_path):
    path,entries=make_wheel(tmp_path);value=manifest(path);decoded=read_wheel_manifest(value.content,expected_sha256=value.sha256);schemes=install(tmp_path,entries)
    directory=schemes['purelib']/'example';outside=tmp_path/'outside';directory.rename(outside);directory.symlink_to(outside,target_is_directory=True)
    with pytest.raises(DataError):verify_installed_payloads([decoded],schemes)



def test_archive_mutation_cannot_change_payloads_after_pin(tmp_path,monkeypatch):
    import compertum.environment_payloads as module
    path,_=make_wheel(tmp_path);original=path.read_bytes();other=tmp_path/'other';other.mkdir()
    replacement,_=make_wheel(other,members={'example/__init__.py':b'VALUE = 8\n'});changed=replacement.read_bytes()
    assert len(changed)==len(original)
    constructor=module.zipfile.ZipFile
    def mutate_then_open(*args,**kwargs):
        path.write_bytes(changed)
        return constructor(*args,**kwargs)
    monkeypatch.setattr(module.zipfile,'ZipFile',mutate_then_open)
    result=wheel_payload_manifest(path,expected_sha256=hashlib.sha256(original).hexdigest(),expected_size=len(original),name='example',version='1.0')
    decoded=read_wheel_manifest(result.content,expected_sha256=result.sha256)
    entry=next(f for f in decoded['files'] if f['path']=='example/__init__.py')
    assert entry['sha256']==hashlib.sha256(b'VALUE = 7\n').hexdigest()


def test_inventory_enumeration_failure_refuses_partial_result(tmp_path,monkeypatch):
    import compertum.environment_payloads as module
    path,entries=make_wheel(tmp_path);value=manifest(path);decoded=read_wheel_manifest(value.content,expected_sha256=value.sha256);schemes=install(tmp_path,entries)
    hidden=schemes['purelib']/'hidden';hidden.mkdir();(hidden/'foreign.py').write_text('VALUE=9')
    scan=module.os.scandir
    def unavailable(directory):
        if Path(directory)==hidden:raise PermissionError('INJECTED_UNREADABLE_SUBTREE')
        return scan(directory)
    monkeypatch.setattr(module.os,'scandir',unavailable)
    with pytest.raises(DataError):verify_installed_payloads([decoded],schemes)


def test_data_relocation_collision_refused(tmp_path):
    path,_=make_wheel(tmp_path,members={'example-1.0.data/purelib/example/__init__.py':b'VALUE = 8\n'})
    with pytest.raises(DataError):manifest(path)


@pytest.mark.parametrize('bound',['MAX_ARCHIVE_BYTES','MAX_WHEEL_BYTES','MAX_FILE_BYTES','MAX_FILES'])
def test_archive_resource_overflow_refused(tmp_path,monkeypatch,bound):
    import compertum.environment_payloads as module
    path,_=make_wheel(tmp_path);monkeypatch.setattr(module,bound,1)
    with pytest.raises(DataError):manifest(path)


def test_install_total_bytes_overflow_refused(tmp_path,monkeypatch):
    import compertum.environment_payloads as module
    path,entries=make_wheel(tmp_path);value=manifest(path);decoded=read_wheel_manifest(value.content,expected_sha256=value.sha256);schemes=install(tmp_path,entries)
    monkeypatch.setattr(module,'MAX_TOTAL_BYTES',1)
    with pytest.raises(DataError):verify_installed_payloads([decoded],schemes)


def test_archive_deadline_refuses_late_result(tmp_path,monkeypatch):
    import compertum.environment_payloads as module
    path,_=make_wheel(tmp_path);calls=[]
    def clock():calls.append(1);return 0 if len(calls)==1 else 121
    monkeypatch.setattr(module.time,'monotonic',clock)
    with pytest.raises(DataError):manifest(path)
