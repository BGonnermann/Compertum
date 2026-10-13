"""Bounded archive and installed payload evidence; this grants no run authority.

Owners consume compact pins. Full scans belong in a bounded worker. Source
bytecode caches may remain on disk only with separately enforced fresh-prefix
startup isolation; this module does not assert that a process used that policy.
"""
from dataclasses import dataclass
from email.parser import BytesParser
import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat
import time
import zipfile
from .data.encoding import canonical
from .data.errors import DataError

MIB=1024**2
MAX_ARCHIVE_BYTES=64*MIB
MAX_WHEEL_BYTES=128*MIB
MAX_FILE_BYTES=32*MIB
MAX_FILES=16384
MAX_TOTAL_BYTES=512*MIB
MAX_MANIFEST_BYTES=4*MIB
SCHEMES=frozenset({'purelib','platlib','data','scripts','headers'})
ENTRY_FIELDS={'scheme','path','sha256','size_bytes'}
MANIFEST_FIELDS={'schema','name','version','archive_sha256','archive_size_bytes','files'}


@dataclass(frozen=True)
class WheelPayloadManifest:
    content:bytes
    sha256:str


def _check(value):
    if not value:raise DataError('ENVIRONMENT_PAYLOAD_UNVERIFIED')


def _digest(value):
    _check(type(value) is str and re.fullmatch('[0-9a-f]{64}',value) is not None)
    return value


def _name(value):
    _check(type(value) is str and re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]{0,95}',value) is not None)
    return re.sub('[-_.]+','-',value).lower()


def _version(value):
    _check(type(value) is str and re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.!+-]{0,95}',value) is not None)
    return value


def _path(value):
    _check(type(value) is str and 0<len(value)<=512 and '\\' not in value)
    parts=value.split('/')
    for part in parts:
        _check(part not in {'','.','..'} and not any(ord(c)<32 or c in '<>:"|?*' for c in part)
            and not part.endswith((' ','.')) and part.split('.')[0].upper() not in {'CON','PRN','AUX','NUL',*(f'COM{i}' for i in range(1,10)),*(f'LPT{i}' for i in range(1,10))})
    return value


def _entry(entry,*,kind=False):
    _check(type(entry) is dict and set(entry)==ENTRY_FIELDS|({'kind'} if kind else set()))
    _check(entry['scheme'] in SCHEMES);_path(entry['path']);_digest(entry['sha256'])
    _check(type(entry['size_bytes']) is int and 0<=entry['size_bytes']<=MAX_FILE_BYTES)
    if kind:_check(entry['kind'] in {'payload','record'})


def _hash_stream(stream,maximum,deadline):
    total=0;digest=hashlib.sha256()
    while True:
        _check(time.monotonic()<deadline)
        block=stream.read(min(MIB,maximum-total+1))
        if not block:break
        total+=len(block);_check(total<=maximum);digest.update(block)
    return digest.hexdigest(),total


def _headers(raw):
    _check(len(raw)<=MIB)
    result=BytesParser().parsebytes(raw)
    _check(not result.defects)
    return result


def _one(headers,key):
    values=headers.get_all(key,[]);_check(len(values)==1)
    return str(values[0])


def _validate(value):
    _check(type(value) is dict and set(value)==MANIFEST_FIELDS and value['schema']=='locked-wheel-payloads-v1')
    _check(_name(value['name'])==value['name']);_version(value['version']);_digest(value['archive_sha256'])
    _check(type(value['archive_size_bytes']) is int and 0<value['archive_size_bytes']<=MAX_ARCHIVE_BYTES)
    files=value['files'];_check(type(files) is list and 1<=len(files)<=MAX_FILES)
    keys=set();records=[];total=0
    for entry in files:
        _entry(entry,kind=True);key=(entry['scheme'],entry['path'].casefold());_check(key not in keys);keys.add(key)
        total+=entry['size_bytes']
        if entry['kind']=='record':records.append(entry)
    _check(total<=MAX_WHEEL_BYTES and len(records)==1 and records[0]['scheme'] in {'purelib','platlib'})
    record=records[0];parts=record['path'].split('/');_check(len(parts)==2 and parts[1]=='RECORD' and parts[0].endswith('.dist-info'))
    base=parts[0][:-len('.dist-info')];expected=value['name'].replace('-','_')+'-'+value['version']
    _check(base.casefold()==expected.casefold())
    _check(all(any(f['scheme']==record['scheme'] and f['path']==parts[0]+'/'+name and f['kind']=='payload' for f in files) for name in ('METADATA','WHEEL')))
    _check(files==sorted(files,key=lambda f:(f['scheme'],f['path'])))
    return value


def read_wheel_manifest(raw,*,expected_sha256):
    try:
        _check(type(raw) is bytes and 0<len(raw)<=MAX_MANIFEST_BYTES and hashlib.sha256(raw).hexdigest()==_digest(expected_sha256))
        value=json.loads(raw);_check(canonical(value)==raw)
        return _validate(value)
    except (ValueError,TypeError,KeyError,AttributeError,RecursionError):raise DataError('ENVIRONMENT_PAYLOAD_UNVERIFIED') from None


def wheel_payload_manifest(path,*,expected_sha256,expected_size,name,version):
    """Hash every archive member; no extraction, import, installation or writes."""
    try:
        deadline=time.monotonic()+120;name=_name(name);version=_version(version);_digest(expected_sha256)
        _check(type(expected_size) is int and 0<expected_size<=MAX_ARCHIVE_BYTES)
        path=Path(path);_check(path.is_file() and not path.is_symlink() and path.stat().st_size==expected_size)
        with path.open('rb') as stream:
            immutable=stream.read(expected_size+1)
        digest=hashlib.sha256(immutable).hexdigest();size=len(immutable)
        _check(size==expected_size and digest==expected_sha256 and time.monotonic()<deadline)
        with io.BytesIO(immutable) as stream:
            with zipfile.ZipFile(stream) as archive:
                members=archive.infolist();_check(1<=len(members)<=MAX_FILES)
                seen=set();files=[];total=0
                for info in members:
                    _check(info.orig_filename==info.filename)
                    member=_path(info.filename.rstrip('/') if info.is_dir() else info.filename)
                    mode=stat.S_IFMT(info.external_attr>>16)
                    _check(mode in {0,stat.S_IFREG,stat.S_IFDIR} and info.flag_bits&1==0)
                    key=member.casefold();_check(key not in seen);seen.add(key)
                    if info.is_dir():continue
                    _check(0<=info.file_size<=MAX_FILE_BYTES);total+=info.file_size;_check(total<=MAX_WHEEL_BYTES);files.append(info)
                metadata=[i for i in files if len(i.filename.split('/'))==2 and i.filename.endswith('.dist-info/METADATA')]
                _check(len(metadata)==1);info_dir=metadata[0].filename.rsplit('/',1)[0]
                expected_dir=name.replace('-','_')+'-'+version+'.dist-info';_check(info_dir.casefold()==expected_dir.casefold())
                meta=_headers(archive.read(metadata[0]));_check(_name(_one(meta,'Name'))==name and _one(meta,'Version')==version)
                wheel=_headers(archive.read(info_dir+'/WHEEL'));_check(_one(wheel,'Wheel-Version')=='1.0')
                pure=_one(wheel,'Root-Is-Purelib');_check(pure in {'true','false'});root_scheme='purelib' if pure=='true' else 'platlib'
                entries=[];data_dir=info_dir[:-len('.dist-info')]+'.data'
                for info in files:
                    parts=info.filename.split('/');scheme=root_scheme;relative=info.filename
                    if parts[0].endswith('.data'):
                        _check(parts[0]==data_dir and len(parts)>=3 and parts[1] in SCHEMES);scheme=parts[1];relative='/'.join(parts[2:])
                    with archive.open(info) as payload:pin,amount=_hash_stream(payload,info.file_size,deadline)
                    _check(amount==info.file_size)
                    # Rewritten #!python scripts need an installer-specific receipt.
                    # The fixed dependency set has none; never infer new script bytes.
                    if scheme=='scripts':
                        with archive.open(info) as payload:_check(not payload.read(9).startswith(b'#!python'))
                    entries.append({'scheme':scheme,'path':relative,'sha256':pin,'size_bytes':amount,'kind':'record' if info.filename==info_dir+'/RECORD' else 'payload'})
        value={'schema':'locked-wheel-payloads-v1','name':name,'version':version,'archive_sha256':digest,'archive_size_bytes':size,'files':sorted(entries,key=lambda f:(f['scheme'],f['path']))}
        _validate(value);raw=canonical(value);_check(len(raw)<=MAX_MANIFEST_BYTES)
        return WheelPayloadManifest(raw,hashlib.sha256(raw).hexdigest())
    except (OSError,ValueError,TypeError,KeyError,AttributeError,zipfile.BadZipFile,RuntimeError):raise DataError('ENVIRONMENT_PAYLOAD_UNVERIFIED') from None


def _regular(root,relative):
    path=root.joinpath(*relative.split('/'))
    _check(path.resolve()==path.absolute() and path.is_file())
    for part in (path,*path.parents):
        _check(not part.is_symlink() and not (part.stat().st_file_attributes if hasattr(part.stat(),'st_file_attributes') else 0)&getattr(stat,'FILE_ATTRIBUTE_REPARSE_POINT',0x400))
        if part==root:break
    return path


def _walk_error(error):
    raise DataError('ENVIRONMENT_PAYLOAD_UNVERIFIED') from None


def verify_installed_payloads(manifests,schemes,*,additional_files=()):
    """Check original bytes and exact import-root inventory without executing it.

    Additional bootstrap/installer files need independently pinned expected bytes.
    A passing result still requires native startup, origin and cache-policy proof.
    """
    try:
        deadline=time.monotonic()+120
        _check(type(manifests) in (list,tuple) and 1<=len(manifests)<=64 and type(schemes) is dict and set(schemes)==SCHEMES)
        roots={k:Path(v).absolute() for k,v in schemes.items()}
        _check(all(p.resolve()==p for p in roots.values()))
        entries=[];names=set();total=0
        for manifest in manifests:
            _validate(manifest);_check(manifest['name'] not in names);names.add(manifest['name']);entries.extend(manifest['files'])
        _check(type(additional_files) in (list,tuple) and len(additional_files)<=1024)
        for entry in additional_files:_entry(entry)
        extra=[{**entry,'kind':'additional'} for entry in additional_files];entries+=extra
        _check(len(entries)<=MAX_FILES)
        expected={};payload_files=0;payload_bytes=0
        for entry in entries:
            root=roots[entry['scheme']];path=_regular(root,entry['path']);key=path
            _check(key not in expected);expected[key]=entry
            if entry['kind']=='record':
                _check(path.stat().st_size<=4*MIB);continue
            total+=entry['size_bytes'];_check(total<=MAX_TOTAL_BYTES)
            before=path.stat();_check(before.st_size==entry['size_bytes'])
            with path.open('rb') as stream:pin,size=_hash_stream(stream,entry['size_bytes'],deadline)
            after=path.stat();_check((before.st_size,before.st_mtime_ns,before.st_ino)==(after.st_size,after.st_mtime_ns,after.st_ino))
            _check(size==entry['size_bytes'] and pin==entry['sha256'])
            if entry['kind']=='payload':payload_files+=1;payload_bytes+=size
        cache_count=0;scanned=0
        for root in set(roots[k] for k in ('purelib','platlib')):
            _check(root.is_dir() and not root.is_symlink())
            for directory,dirs,files in os.walk(root,followlinks=False,onerror=_walk_error):
                _check(time.monotonic()<deadline)
                scanned+=len(dirs);_check(scanned<=MAX_FILES)
                for name in dirs:
                    child=Path(directory)/name;_check(not child.is_symlink() and child.resolve()==child.absolute())
                for name in files:
                    scanned+=1;_check(scanned<=MAX_FILES);path=_regular(root,(Path(directory)/name).relative_to(root).as_posix())
                    if path in expected:continue
                    match=re.fullmatch(r'(.+)\.cpython-314(?:\.opt-[12])?\.pyc',name)
                    _check(path.parent.name=='__pycache__' and match is not None)
                    source=path.parent.parent/(match[1]+'.py')
                    _check(source in expected and expected[source]['kind']!='record' and path.stat().st_size<=MAX_FILE_BYTES)
                    cache_count+=1
        return {'schema':'installed-payload-check-v1','status':'LOCKED_PAYLOAD_BYTES_VERIFIED','distributions':len(manifests),
            'payload_files':payload_files,'payload_bytes':payload_bytes,'additional_files':len(extra),'inactive_cache_files':cache_count,
            'required_cache_policy':'ISOLATED_EMPTY_PREFIX_NO_WRITE','campaign_admitted':False}
    except (OSError,ValueError,TypeError,KeyError,AttributeError,RecursionError):raise DataError('ENVIRONMENT_PAYLOAD_UNVERIFIED') from None
