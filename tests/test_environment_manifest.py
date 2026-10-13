"""Immutable clean-environment inventory, archive links and lane refusals."""
import copy,hashlib,json,sys,zipfile
from pathlib import Path
import pytest
from compertum.data.encoding import canonical
from compertum.data.errors import DataError
from compertum.environment_payloads import wheel_payload_manifest
import compertum.environment_manifest as m


def sha(raw):return hashlib.sha256(raw).hexdigest()
def pin(path):return {'path':str(path),'sha256':sha(path.read_bytes()),'size_bytes':path.stat().st_size}
def put(path,raw):path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw);return path


def wheel(root,name,files):
    members={**files,f'{name}-1.0.dist-info/METADATA':f'Name: {name}\nVersion: 1.0\n'.encode(),f'{name}-1.0.dist-info/WHEEL':b'Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n',f'{name}-1.0.dist-info/RECORD':b'original record'}
    path=root/f'{name}-1.0-py3-none-any.whl'
    with zipfile.ZipFile(path,'w') as archive:
        for k,v in members.items():archive.writestr(k,v)
    value=wheel_payload_manifest(path,expected_sha256=sha(path.read_bytes()),expected_size=path.stat().st_size,name=name,version='1.0')
    return path,json.loads(value.content),members


@pytest.fixture
def environment(tmp_path,monkeypatch):
    def build(lane='source'):
        root=tmp_path/lane;root.mkdir();prefix=root/'venv';site=prefix/'Lib/site-packages';site.mkdir(parents=True)
        source=root/'src';package=source/'compertum';base=root/'python';base.mkdir()
        exe=put(prefix/'Scripts/python.exe',b'venv launcher');baseexe=put(base/'python.exe',b'base interpreter')
        cfg=put(prefix/'pyvenv.cfg',b'include-system-site-packages = false\nversion_info = 3.14.7\n')
        dep,dm,df=wheel(root,'example',{'example/__init__.py':b'VALUE = 1\n'})
        lock=('[\n]' if False else 'version = 1\n[[package]]\nname = "compertum"\nversion = "1.0"\nsource = { editable = "." }\n[[package]]\nname = "example"\nversion = "1.0"\nwheels = [{url = "https://example.invalid/'+dep.name+'", hash = "sha256:'+sha(dep.read_bytes())+'", size = '+str(dep.stat().st_size)+'}]\n').encode()
        pmfiles={'compertum/__init__.py':b'VALUE = 2\n','compertum-1.0.data/data/share/compertum/uv.lock':lock}
        project,pm,pf=wheel(root,'compertum',pmfiles)
        for k,v in df.items():put(site/k,v)
        extras=[]
        def extra(path,purpose):
            extras.append({'purpose':purpose,'scheme':'purelib','path':path.relative_to(site).as_posix(),'sha256':sha(path.read_bytes()),'size_bytes':path.stat().st_size})
        for name,raw in [('_virtualenv.py',b'# registered bootstrap\n'),('_virtualenv.pth',b'import _virtualenv\n')]:extra(put(site/name,raw),'bootstrap')
        sourcepins=[]
        if lane=='source':
            packagefile=put(package/'__init__.py',pmfiles['compertum/__init__.py'])
            sourcepins.append({'path':'compertum/__init__.py','sha256':sha(packagefile.read_bytes()),'size_bytes':packagefile.stat().st_size,'purpose':'package'})
            for name in ('dependency_links.txt','entry_points.txt','PKG-INFO','requires.txt','SOURCES.txt','top_level.txt'):
                p=put(source/'compertum.egg-info'/name,b'pinned generated metadata\n');sourcepins.append({'path':'compertum.egg-info/'+name,'sha256':sha(p.read_bytes()),'size_bytes':p.stat().st_size,'purpose':'metadata'})
            for k,v in pf.items():
                if '.dist-info/' in k:extra(put(site/k,v),'editable_metadata')
            extra(put(site/'compertum-1.0.dist-info/direct_url.json',canonical({'url':root.as_uri(),'dir_info':{'editable':True}})),'editable_metadata')
            extra(put(site/'__editable__.compertum-1.0.pth',(str(source)+'\n').encode()),'editable')
            lockpath=put(root/'uv.lock',lock)
        else:
            package=site/'compertum'
            for k,v in pf.items():
                p=prefix/k.split('.data/data/',1)[1] if '.data/data/' in k else site/k;put(p,v)
            lockpath=prefix/'share/compertum/uv.lock'
        archive=root/'source.zip'
        with zipfile.ZipFile(archive,'w') as z:z.writestr('src/compertum/__init__.py',pmfiles['compertum/__init__.py']);z.writestr('uv.lock',lock)
        origins={'executable':str(exe),'base_executable':str(baseexe),'prefix':str(prefix),'base_prefix':str(base),'package_root':str(package),'lock_path':str(lockpath),'python':'3.14.7','cache_tag':'cpython-314','platform':'win32'}
        runtime={'package_sha256':sha(b'__init__.py'+pmfiles['compertum/__init__.py']),'lock_sha256':sha(lock),'python':'3.14.7','distributions':[['compertum','1.0'],['example','1.0']]}
        value={'schema':'locked-environment-v1','environment_id':'fixture-'+lane,'lane':lane,'runtime':runtime,'origins':origins,'schemes':{k:str(p) for k,p in {'purelib':site,'platlib':site,'data':prefix,'scripts':prefix/'Scripts','headers':prefix/'Include'}.items()},'executables':[pin(exe),pin(baseexe)],'venv_config':pin(cfg),'source_archive':pin(archive),'project_archive':pin(project),'dependency_root':str(root),'dependencies':[{'filename':dep.name,'payload':dm}],'project_payload':pm,'additional_files':sorted(extras,key=lambda x:x['path']),'source_root':str(source) if lane=='source' else None,'source_files':sorted(sourcepins,key=lambda x:x['path']),'policy':m.POLICY}
        monkeypatch.setattr(m,'_current_origins',lambda:copy.deepcopy(origins));monkeypatch.setattr(m,'_current_runtime',lambda:copy.deepcopy(runtime));monkeypatch.setattr(m,'_current_schemes',lambda:copy.deepcopy(value['schemes']));monkeypatch.setattr(m,'_loaded_origins',lambda:[])
        return value
    return build


def check(value):
    record=m.build_manifest(value);return m.verify_environment(record.content,expected_sha256=record.sha256)


@pytest.mark.parametrize('lane',['source','wheel'])
def test_both_lanes_verify_pinned_bytes_without_admitting_campaign(environment,lane):
    value=environment(lane);record=m.build_manifest(value);value['environment_id']='changed'
    assert m.read_manifest(record.content,expected_sha256=record.sha256)['environment_id']=='fixture-'+lane
    report=m.verify_environment(record.content,expected_sha256=record.sha256)
    assert report['status']=='ENVIRONMENT_BYTES_VERIFIED' and report['campaign_admitted'] is False


@pytest.mark.parametrize('fault',['bootstrap','generated','editable_target','editable_code','source_pyd','source_pyc','source_module','venv','base_exe','origin','archive'])
def test_registered_environment_changes_refused(environment,fault,monkeypatch):
    value=environment();record=m.build_manifest(value);site=Path(value['schemes']['purelib']);source=Path(value['source_root'])
    paths={'bootstrap':site/'_virtualenv.py','generated':site/'compertum-1.0.dist-info/METADATA','editable_target':site/'__editable__.compertum-1.0.pth','editable_code':site/'__editable__.compertum-1.0.pth','source_pyd':source/'compertum/extra.pyd','source_pyc':source/'compertum/extra.pyc','source_module':source/'compertum/extra.py','venv':Path(value['venv_config']['path']),'base_exe':Path(value['executables'][1]['path']),'archive':Path(value['project_archive']['path'])}
    if fault=='origin':monkeypatch.setattr(m,'_current_origins',lambda:{**value['origins'],'package_root':str(source/'foreign')})
    else:put(paths[fault],b'changed bytes\n')
    with pytest.raises(DataError):m.verify_environment(record.content,expected_sha256=record.sha256)


@pytest.mark.parametrize('fault',['self_pin_hook','fabricate_payload','omit_dependency','duplicate_dependency','duplicate_extra','wheel_editable','editable_code','system_site','source_inventory','record_claim'])
def test_rehashed_manifest_cannot_bypass_fixed_contract(environment,fault):
    value=environment('wheel' if fault=='wheel_editable' else 'source');site=Path(value['schemes']['purelib'])
    if fault in {'self_pin_hook','wheel_editable'}:
        p=put(site/'foreign.pth',b'import foreign\n');value['additional_files'].append({'purpose':'bootstrap','scheme':'purelib','path':p.name,'sha256':sha(p.read_bytes()),'size_bytes':p.stat().st_size})
    elif fault=='fabricate_payload':value['dependencies'][0]['payload']['files'][0]['sha256']='0'*64
    elif fault=='omit_dependency':value['dependencies']=[]
    elif fault=='duplicate_dependency':value['dependencies']*=2
    elif fault=='duplicate_extra':value['additional_files'].append(value['additional_files'][0])
    elif fault=='editable_code':
        p=site/'__editable__.compertum-1.0.pth';p.write_text(str(Path(value['source_root']))+'\nimport foreign\n');entry=next(e for e in value['additional_files'] if e['purpose']=='editable');entry.update(sha256=sha(p.read_bytes()),size_bytes=p.stat().st_size)
    elif fault=='system_site':
        p=Path(value['venv_config']['path']);p.write_text('include-system-site-packages = true\n');value['venv_config']=pin(p)
    elif fault=='source_inventory':
        p=put(Path(value['source_root'])/'compertum/extra.py',b'bad\n');value['source_files'].append({'path':'compertum/extra.py','sha256':sha(p.read_bytes()),'size_bytes':p.stat().st_size,'purpose':'package'})
    elif fault=='record_claim':value['policy']={**m.POLICY,'installed_record':'ORIGINAL_ARCHIVE_VERIFIED'}
    with pytest.raises(DataError):check(value)


def test_rewritten_record_is_explicit_exception(environment):
    value=environment('wheel');p=Path(value['schemes']['purelib'])/'example-1.0.dist-info/RECORD';p.write_text('installer rewriting')
    assert check(value)['installed_record']=='BOUNDED_UNTRUSTED_INVENTORY'


def test_valid_old_source_cache_is_inactive_evidence_only(environment):
    value=environment();put(Path(value['source_root'])/'compertum/__pycache__/__init__.cpython-314.pyc',b'old cache')
    assert check(value)['required_cache_policy']=='ISOLATED_EMPTY_PREFIX_NO_WRITE'


def test_loaded_foreign_module_refused(environment,monkeypatch):
    value=environment();monkeypatch.setattr(m,'_loaded_origins',lambda:[str(Path(value['source_root']).parent/'foreign.py')])
    with pytest.raises(DataError):check(value)


@pytest.mark.parametrize('fault',['whole_bound','wrong_pin','boolean_size','noncanonical','unknown_field'])
def test_manifest_boundary_contract(environment,fault,monkeypatch):
    value=environment();record=m.build_manifest(value);raw=record.content;digest=record.sha256
    if fault=='whole_bound':monkeypatch.setattr(m,'MAX_MANIFEST_BYTES',len(raw)-1)
    elif fault=='wrong_pin':digest='0'*64
    else:
        if fault=='boolean_size':value['venv_config']['size_bytes']=True
        elif fault=='unknown_field':value['admitted']=True
        raw=json.dumps(value).encode() if fault=='noncanonical' else canonical(value);digest=sha(raw)
    with pytest.raises(DataError):m.read_manifest(raw,expected_sha256=digest)

@pytest.mark.parametrize('fault',['extra_archived_module','different_wheel_lock'])
def test_source_and_wheel_archives_have_exact_common_inputs(environment,fault):
    value=environment();archive=Path(value['source_archive']['path'])
    if fault=='extra_archived_module':
        with zipfile.ZipFile(archive,'a') as z:z.writestr('src/compertum/foreign.py',b'foreign = True\n')
        value['source_archive']=pin(archive)
    else:
        path,payload,_=wheel(Path(value['project_archive']['path']).parent,'compertum',{'compertum/__init__.py':b'VALUE = 2\n','compertum-1.0.data/data/share/compertum/uv.lock':b'different locked dependencies'})
        value['project_archive']=pin(path);value['project_payload']=payload
    with pytest.raises(DataError):check(value)


def test_unregistered_global_site_module_is_not_a_standard_library_origin(environment,monkeypatch):
    value=environment();p=put(Path(value['origins']['base_prefix'])/'Lib/site-packages/foreign.py',b'foreign = True\n')
    monkeypatch.setattr(m,'_loaded_origins',lambda:[str(p)])
    with pytest.raises(DataError):check(value)


def test_total_including_additions_is_checked_before_file_reads(environment,monkeypatch):
    value=environment();record=m.build_manifest(value)
    archive_total=sum(e['size_bytes'] for p in [value['dependencies'][0]['payload'],value['project_payload']] for e in p['files'])
    for entry in value['additional_files']:
        if entry['purpose']=='bootstrap':entry['size_bytes']+=archive_total
    raw=canonical(value);reads=[]
    monkeypatch.setattr(m.payloads,'MAX_TOTAL_BYTES',archive_total+1)
    monkeypatch.setattr(m,'_file',lambda *a:reads.append(a))
    with pytest.raises(DataError):m.verify_environment(raw,expected_sha256=sha(raw))
    assert reads==[]


def test_changed_install_scheme_origin_is_refused(environment,monkeypatch):
    value=environment();monkeypatch.setattr(m,'_current_schemes',lambda:{**value['schemes'],'headers':str(Path(value['origins']['prefix'])/'other')})
    with pytest.raises(DataError):check(value)


def test_archive_package_prefix_is_case_insensitive(environment):
    value=environment();archive=Path(value['source_archive']['path'])
    with zipfile.ZipFile(archive,'a') as z:z.writestr('SRC/Compertum/foreign.py',b'foreign = True\n')
    value['source_archive']=pin(archive)
    with pytest.raises(DataError):check(value)


def test_unknown_source_is_rejected_before_legacy_runtime_rescan(environment,monkeypatch):
    value=environment();put(Path(value['source_root'])/'compertum/foreign.py',b'unregistered source\n');calls=[]
    def runtime():calls.append(1);return value['runtime']
    monkeypatch.setattr(m,'_current_runtime',runtime)
    with pytest.raises(DataError):check(value)
    assert calls==[]


def test_runtime_comparison_cannot_finish_after_shared_deadline(environment,monkeypatch):
    value=environment();clock=[0]
    def runtime():clock[0]=121;return value['runtime']
    monkeypatch.setattr(m.time,'monotonic',lambda:clock[0]);monkeypatch.setattr(m,'_current_runtime',runtime)
    with pytest.raises(DataError):check(value)


def test_native_extended_drive_origins_equal_frozen_ordinary_spelling(monkeypatch):
    before=m._current_origins()
    for key in ('executable','_base_executable','prefix','base_prefix'):
        value=getattr(sys,key)
        assert not value.startswith('\\\\?\\')
        monkeypatch.setattr(sys,key,'\\\\?\\'+value)
    assert m._current_origins()==before


def test_native_extended_drive_schemes_equal_frozen_ordinary_spelling(monkeypatch):
    before=m._current_schemes();paths=m.sysconfig.get_paths()
    monkeypatch.setattr(m.sysconfig,'get_paths',lambda:{k:'\\\\?\\'+v for k,v in paths.items()})
    assert m._current_schemes()==before


def test_loaded_extended_drive_origin_preserves_payload_check(environment,monkeypatch):
    value=environment();record=m.build_manifest(value)
    package=Path(value['origins']['package_root'])/'__init__.py'
    monkeypatch.setattr(m,'_loaded_origins',lambda:['\\\\?\\'+str(package)])
    assert m.verify_environment(record.content,expected_sha256=record.sha256)['status']=='ENVIRONMENT_BYTES_VERIFIED'
    foreign=put(package.parent/'foreign.py',b'foreign')
    monkeypatch.setattr(m,'_loaded_origins',lambda:['\\\\?\\'+str(foreign)])
    with pytest.raises(DataError):m.verify_environment(record.content,expected_sha256=record.sha256)
