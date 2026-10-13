"""Immutable local environment evidence; registration and startup are separate.

The expected manifest is frozen before use. This verifier reads only pinned
local paths, performs no imports from artifacts, and grants no campaign rights.
"""
from dataclasses import dataclass
import hashlib,io,json,os,platform,re,stat,sys,sysconfig,time,tomllib,zipfile
from pathlib import Path
from urllib.parse import urlsplit,unquote
from compertum.data.encoding import canonical
from compertum.data.errors import DataError
from compertum import environment_payloads as payloads

MIB=1024**2
MAX_MANIFEST_BYTES=4*MIB
MAX_SOURCE_ARCHIVE_BYTES=16*MIB
POLICY={'cache':'ISOLATED_EMPTY_PREFIX_NO_WRITE','installed_record':'BOUNDED_UNTRUSTED_INVENTORY','verifier':'locked-environment-v1','maximum_seconds':120,'maximum_payload_bytes':512*MIB,'maximum_entries':16384}
FIELDS={'schema','environment_id','lane','runtime','origins','schemes','executables','venv_config','source_archive','project_archive','dependency_root','dependencies','project_payload','additional_files','source_root','source_files','policy'}
ORIGIN_PATHS={'executable','base_executable','prefix','base_prefix','package_root','lock_path'}
ORIGIN_FIELDS=ORIGIN_PATHS|{'python','cache_tag','platform'}
EGG_FILES={'dependency_links.txt','entry_points.txt','PKG-INFO','requires.txt','SOURCES.txt','top_level.txt'}
INSTALLER_FILES={'INSTALLER','REQUESTED','direct_url.json','uv_cache.json','uv_build.json'}


@dataclass(frozen=True)
class EnvironmentManifest:
    content:bytes
    sha256:str


def _check(ok):
    if not ok:raise DataError('ENVIRONMENT_MANIFEST_UNVERIFIED')
def _sha(raw):return hashlib.sha256(raw).hexdigest()
def _digest(value):payloads._digest(value);return value
def _absolute(value):
    _check(type(value) is str and 0<len(value)<=1024 and not any(ord(c)<32 for c in value))
    p=Path(value);_check(p.is_absolute() and len(p.drive)==2 and p.drive[1]==':' and '..' not in p.parts and str(p)==value)
    return p

def _pin(value,maximum):
    _check(type(value) is dict and set(value)=={'path','sha256','size_bytes'})
    _absolute(value['path']);_digest(value['sha256']);_check(type(value['size_bytes']) is int and 0<value['size_bytes']<=maximum)

def _runtime(value):
    _check(type(value) is dict and set(value)=={'package_sha256','lock_sha256','python','distributions'})
    _digest(value['package_sha256']);_digest(value['lock_sha256']);_check(value['python']=='3.14.7')
    versions=value['distributions'];_check(type(versions) is list and 2<=len(versions)<=64)
    seen=set()
    for pair in versions:
        _check(type(pair) is list and len(pair)==2);name=payloads._name(pair[0]);payloads._version(pair[1]);_check(name not in seen);seen.add(name)
    _check(versions==sorted(versions));return {payloads._name(k):v for k,v in versions}


def _validate(value):
    _check(type(value) is dict and set(value)==FIELDS and value['schema']=='locked-environment-v1')
    _check(type(value['environment_id']) is str and re.fullmatch('[A-Za-z0-9][A-Za-z0-9_-]{0,95}',value['environment_id']))
    _check(value['lane'] in {'source','wheel'} and canonical(value['policy'])==canonical(POLICY))
    versions=_runtime(value['runtime']);origins=value['origins']
    _check(type(origins) is dict and set(origins)==ORIGIN_FIELDS)
    for key in ORIGIN_PATHS:_absolute(origins[key])
    _check(origins['python']=='3.14.7' and origins['cache_tag']=='cpython-314' and origins['platform']=='win32')
    schemes=value['schemes'];_check(type(schemes) is dict and set(schemes)==payloads.SCHEMES)
    for p in schemes.values():_absolute(p)
    prefix=Path(origins['prefix']);site=prefix/'Lib/site-packages'
    _check(schemes['purelib']==schemes['platlib']==str(site) and schemes['data']==str(prefix) and schemes['scripts']==str(prefix/'Scripts'))
    _check(Path(origins['executable']).parent==prefix/'Scripts' and Path(origins['base_executable']).parent==Path(origins['base_prefix']))
    _check(type(value['executables']) is list and len(value['executables'])==2)
    for item in value['executables']:_pin(item,16*MIB)
    _check([p['path'] for p in value['executables']]==[origins['executable'],origins['base_executable']])
    _pin(value['venv_config'],16384);_check(value['venv_config']['path']==str(prefix/'pyvenv.cfg'))
    _pin(value['source_archive'],MAX_SOURCE_ARCHIVE_BYTES);_pin(value['project_archive'],payloads.MAX_ARCHIVE_BYTES)
    _absolute(value['dependency_root']);deps=value['dependencies'];_check(type(deps) is list and 1<=len(deps)<=63)
    manifests=[];names=[]
    for entry in deps:
        _check(type(entry) is dict and set(entry)=={'filename','payload'})
        name=entry['filename'];payloads._path(name);_check('/' not in name and name.endswith('.whl'))
        manifest=payloads._validate(entry['payload']);_check(manifest['name']!='compertum');names.append(manifest['name']);manifests.append(manifest)
    _check(names==sorted(set(names)))
    project=payloads._validate(value['project_payload']);_check(project['name']=='compertum')
    _check(project['archive_sha256']==value['project_archive']['sha256'] and project['archive_size_bytes']==value['project_archive']['size_bytes'])
    locks=[e for e in project['files'] if e['scheme']=='data' and e['path']=='share/compertum/uv.lock']
    _check(len(locks)==1 and locks[0]['sha256']==value['runtime']['lock_sha256'])
    manifests.append(project)
    _check({p['name']:p['version'] for p in manifests}==versions)
    _check(sum(len(p['files']) for p in manifests)<=payloads.MAX_FILES and sum(f['size_bytes'] for p in manifests for f in p['files'])<=payloads.MAX_TOTAL_BYTES)
    records={next(f['path'].split('/')[0] for f in p['files'] if f['kind']=='record'):p['name'] for p in manifests}
    project_dir=next(k for k,v in records.items() if v=='compertum');extra=value['additional_files'];_check(type(extra) is list and len(extra)<=1024)
    keys=[];bootstrap=[];editable=[]
    for entry in extra:
        _check(type(entry) is dict and set(entry)==payloads.ENTRY_FIELDS|{'purpose'})
        payloads._entry({k:v for k,v in entry.items() if k!='purpose'});_check(entry['scheme']=='purelib')
        path=entry['path'];keys.append(path.casefold());parts=path.split('/');purpose=entry['purpose']
        if purpose=='bootstrap':_check(path in {'_virtualenv.py','_virtualenv.pth'});bootstrap.append(path)
        elif purpose=='installer':_check(len(parts)==2 and parts[0] in records and parts[1] in INSTALLER_FILES)
        elif purpose=='editable':_check(value['lane']=='source' and path=='__editable__.compertum-'+project['version']+'.pth');editable.append(path)
        elif purpose=='editable_metadata':_check(value['lane']=='source' and len(parts)==2 and parts[0]==project_dir and parts[1] in INSTALLER_FILES|{'METADATA','WHEEL','RECORD','entry_points.txt','top_level.txt'})
        else:_check(False)
    _check(len(set(keys))==len(keys) and extra==sorted(extra,key=lambda e:e['path']) and set(bootstrap)=={'_virtualenv.py','_virtualenv.pth'})
    sources=value['source_files'];_check(type(sources) is list and len(sources)<=4096)
    if value['lane']=='wheel':
        _check(value['source_root'] is None and not sources and not editable and origins['package_root']==str(site/'compertum') and origins['lock_path']==str(prefix/'share/compertum/uv.lock'))
    else:
        source=_absolute(value['source_root']);_check(source.name=='src' and len(editable)==1 and origins['package_root']==str(source/'compertum') and origins['lock_path']==str(source.parent/'uv.lock'))
        names=[];metadata=set();packages=[]
        for entry in sources:
            _check(type(entry) is dict and set(entry)=={'path','sha256','size_bytes','purpose'})
            payloads._path(entry['path']);_digest(entry['sha256']);_check(type(entry['size_bytes']) is int and 0<=entry['size_bytes']<=payloads.MAX_FILE_BYTES)
            names.append(entry['path'].casefold());parts=entry['path'].split('/')
            if entry['purpose']=='metadata':_check(len(parts)==2 and parts[0]=='compertum.egg-info' and parts[1] in EGG_FILES);metadata.add(parts[1])
            else:_check(entry['purpose']=='package' and parts[0]=='compertum');packages.append(entry)
        _check(len(set(names))==len(names) and metadata==EGG_FILES and sources==sorted(sources,key=lambda e:e['path']))
        expected=[{k:e[k] for k in ('path','sha256','size_bytes')} for e in project['files'] if e['scheme'] in {'purelib','platlib'} and e['path'].startswith('compertum/')]
        _check([{k:e[k] for k in ('path','sha256','size_bytes')} for e in packages]==expected)
    installed=[e for p in (manifests if value['lane']=='wheel' else manifests[:-1]) for e in p['files']]+extra+sources
    _check(len(installed)<=payloads.MAX_FILES and sum(e['size_bytes'] for e in installed)<=payloads.MAX_TOTAL_BYTES)
    return value


def read_manifest(raw,*,expected_sha256):
    try:
        _check(type(raw) is bytes and 0<len(raw)<=MAX_MANIFEST_BYTES and _sha(raw)==_digest(expected_sha256))
        value=json.loads(raw);_check(canonical(value)==raw);return _validate(value)
    except (ValueError,TypeError,KeyError,AttributeError,RecursionError,OverflowError):raise DataError('ENVIRONMENT_MANIFEST_UNVERIFIED') from None


def build_manifest(value):
    try:
        raw=canonical(value);pin=_sha(raw);read_manifest(raw,expected_sha256=pin);return EnvironmentManifest(raw,pin)
    except (ValueError,TypeError,KeyError,AttributeError,RecursionError,OverflowError):raise DataError('ENVIRONMENT_MANIFEST_UNVERIFIED') from None


def _file(pin,deadline):
    path=_absolute(pin['path']);payloads._regular(path.parent,path.name);before=path.stat()
    _check(before.st_size==pin['size_bytes'] and time.monotonic()<deadline)
    with path.open('rb') as stream:raw=stream.read(pin['size_bytes']+1)
    after=path.stat();_check((before.st_size,before.st_mtime_ns,before.st_ino)==(after.st_size,after.st_mtime_ns,after.st_ino))
    _check(len(raw)==pin['size_bytes'] and _sha(raw)==pin['sha256'] and time.monotonic()<deadline);return raw


def _native_spelling(value):
    # CreateProcessW may report the same drive path through Win32's extended
    # spelling. Normalize observations only; frozen manifest paths stay strict.
    if type(value) is str and value.startswith('\\\\?\\') and len(value)>=7 and value[4].isalpha() and value[5:7]==':\\':
        return value[4:]
    return value


def _observed_path(value):return _native_spelling(str(Path(value).resolve()))


def _current_origins():
    import compertum
    package=Path(_observed_path(compertum.__file__)).parent
    lock=package.parents[1]/'uv.lock'
    if not lock.is_file():lock=Path(sysconfig.get_path('data'))/'share/compertum/uv.lock'
    return {'executable':_observed_path(sys.executable),'base_executable':_observed_path(sys._base_executable),'prefix':_observed_path(sys.prefix),'base_prefix':_observed_path(sys.base_prefix),'package_root':str(package),'lock_path':_observed_path(lock),'python':platform.python_version(),'cache_tag':sys.implementation.cache_tag,'platform':sys.platform}


def _current_schemes():
    paths=sysconfig.get_paths()
    return {k:_observed_path(paths['include' if k=='headers' else k]) for k in payloads.SCHEMES}


def _current_runtime():
    from compertum.runtime.identity_pins import runtime_identity
    return json.loads(canonical(runtime_identity()))


def _loaded_origins():
    result=[]
    for module in tuple(sys.modules.values()):
        spec=getattr(module,'__spec__',None);origin=getattr(spec,'origin',None)
        if origin not in (None,'built-in','frozen'):result.append(origin)
        elif spec is None:
            origin=getattr(module,'__file__',None)
            if origin:result.append(origin)
    return result


def _source_archive(value,deadline):
    raw=_file(value['source_archive'],deadline)
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        members=z.infolist();_check(1<=len(members)<=4096)
        seen=set();total=0
        for item in members:
            _check(item.filename==item.orig_filename and not item.is_dir() and not item.flag_bits&1)
            payloads._path(item.filename);key=item.filename.casefold();_check(key not in seen);seen.add(key)
            _check(stat.S_IFMT(item.external_attr>>16) in {0,stat.S_IFREG} and 0<=item.file_size<=payloads.MAX_FILE_BYTES)
            total+=item.file_size;_check(total<=MAX_SOURCE_ARCHIVE_BYTES)
        expected_members={'src/'+e['path'] for e in value['project_payload']['files'] if e['scheme'] in {'purelib','platlib'} and e['path'].startswith('compertum/')} 
        _check({i.filename for i in members if i.filename.casefold().startswith('src/compertum/')}==expected_members)
        for entry in value['project_payload']['files']:
            if entry['scheme'] in {'purelib','platlib'} and entry['path'].startswith('compertum/'):
                raw=z.read('src/'+entry['path']);_check(len(raw)==entry['size_bytes'] and _sha(raw)==entry['sha256'])
        _check(_sha(z.read('uv.lock'))==value['runtime']['lock_sha256'] and time.monotonic()<deadline)


def _archive_payload(path,manifest,deadline):
    payloads._regular(path.parent,path.name)
    observed=payloads.wheel_payload_manifest(path,expected_sha256=manifest['archive_sha256'],expected_size=manifest['archive_size_bytes'],name=manifest['name'],version=manifest['version'])
    _check(observed.content==canonical(manifest) and time.monotonic()<deadline)


def _lock(value,raw):
    _check(len(raw)<=MIB and _sha(raw)==value['runtime']['lock_sha256']);lock=tomllib.loads(raw.decode())
    packages=lock['package'];_check(type(packages) is list and len(packages)<=64)
    indexed={payloads._name(p['name']):p for p in packages};_check(len(indexed)==len(packages))
    versions=_runtime(value['runtime']);_check({k:p['version'] for k,p in indexed.items()}==versions)
    for entry in value['dependencies']:
        p=entry['payload'];choices=indexed[p['name']]['wheels']
        _check(any(w['hash']=='sha256:'+p['archive_sha256'] and type(w['size']) is int and w['size']==p['archive_size_bytes'] and unquote(urlsplit(w['url']).path.rsplit('/',1)[-1])==entry['filename'] for w in choices))


def _source_inventory(value,deadline):
    root=Path(value['source_root']);expected={}
    for entry in value['source_files']:
        path=payloads._regular(root,entry['path']);_file({'path':str(path),'sha256':entry['sha256'],'size_bytes':entry['size_bytes']},deadline);expected[path]=entry
    seen=0;cache=0
    for directory,dirs,files in os.walk(root,followlinks=False,onerror=payloads._walk_error):
        _check(time.monotonic()<deadline);seen+=len(dirs)+len(files);_check(seen<=payloads.MAX_FILES)
        for name in dirs:
            p=Path(directory)/name;_check(not p.is_symlink() and p.resolve()==p.absolute() and not p.stat().st_file_attributes&stat.FILE_ATTRIBUTE_REPARSE_POINT)
        for name in files:
            path=payloads._regular(root,(Path(directory)/name).relative_to(root).as_posix())
            if path in expected:continue
            match=re.fullmatch(r'(.+)\.cpython-314(?:\.opt-[12])?\.pyc',name)
            _check(path.parent.name=='__pycache__' and match is not None)
            origin=path.parent.parent/(match[1]+'.py');_check(origin in expected and expected[origin]['purpose']=='package' and path.stat().st_size<=payloads.MAX_FILE_BYTES);cache+=1
    return cache


def _extra_content(value,deadline):
    site=Path(value['schemes']['purelib']);version=value['project_payload']['version']
    for entry in value['additional_files']:
        path=payloads._regular(site,entry['path']);raw=_file({'path':str(path),'sha256':entry['sha256'],'size_bytes':entry['size_bytes']},deadline)
        if entry['purpose']=='editable':_check(raw in {(value['source_root']+'\n').encode(),(value['source_root']+'\r\n').encode()})
        if entry['path'].endswith('/direct_url.json'):
            document=json.loads(raw);editable=document.get('dir_info',{}).get('editable',False)
            if value['lane']=='wheel':_check(editable is False)
            elif entry['path'].startswith('compertum-'+version+'.dist-info/'):
                _check(editable is True and document.get('url')==Path(value['source_root']).parent.as_uri())


def verify_environment(raw,*,expected_sha256):
    """Fresh observations against frozen expectations; never discover extra pins."""
    try:
        deadline=time.monotonic()+120;value=read_manifest(raw,expected_sha256=expected_sha256)
        _check(canonical(_current_schemes())==canonical(value['schemes']) and canonical(_current_origins())==canonical(value['origins']))
        for entry in value['executables']:_file(entry,deadline)
        config=_file(value['venv_config'],deadline).decode();rows={}
        for row in config.splitlines():
            key,sep,val=row.partition('=');_check(bool(sep));key=key.strip();_check(key not in rows);rows[key]=val.strip()
        _check(rows.get('include-system-site-packages')=='false' and rows.get('version_info')=='3.14.7')
        lockpath=Path(value['origins']['lock_path']);payloads._regular(lockpath.parent,lockpath.name);_check(lockpath.stat().st_size<=MIB)
        with lockpath.open('rb') as stream:lock_raw=stream.read(MIB+1)
        _lock(value,lock_raw)
        for entry in value['dependencies']:_archive_payload(Path(value['dependency_root'])/entry['filename'],entry['payload'],deadline)
        _archive_payload(Path(value['project_archive']['path']),value['project_payload'],deadline);_source_archive(value,deadline);_extra_content(value,deadline)
        manifests=[e['payload'] for e in value['dependencies']]
        if value['lane']=='wheel':manifests.append(value['project_payload'])
        extras=[{k:v for k,v in e.items() if k!='purpose'} for e in value['additional_files']]
        payloads.verify_installed_payloads(manifests,value['schemes'],additional_files=extras)
        cache=_source_inventory(value,deadline) if value['lane']=='source' else 0
        expected={Path(value['schemes'][e['scheme']])/e['path'] for p in manifests for e in p['files'] if e['kind']=='payload'}
        expected.update(Path(value['schemes'][e['scheme']])/e['path'] for e in extras)
        if value['lane']=='source':expected.update(Path(value['source_root'])/e['path'] for e in value['source_files'] if e['purpose']=='package')
        base=Path(value['origins']['base_prefix'])
        for origin in _loaded_origins():
            path=_absolute(_native_spelling(origin));_check(path.is_file() and path.resolve()==path and path.suffix not in {'.pyc','.zip','.egg'})
            _check(path in expected or path.is_relative_to(base/'Lib') and not path.is_relative_to(base/'Lib/site-packages') or path.is_relative_to(base/'DLLs'))
        _check(canonical(_current_runtime())==canonical(value['runtime']) and time.monotonic()<deadline)
        return {'schema':'environment-byte-check-v1','status':'ENVIRONMENT_BYTES_VERIFIED','manifest_sha256':expected_sha256,'environment_id':value['environment_id'],'lane':value['lane'],'campaign_admitted':False,'installed_record':POLICY['installed_record'],'required_cache_policy':POLICY['cache'],'inactive_source_cache_files':cache}
    except (OSError,ValueError,TypeError,KeyError,AttributeError,RecursionError,OverflowError,zipfile.BadZipFile,RuntimeError):raise DataError('ENVIRONMENT_MANIFEST_UNVERIFIED') from None
