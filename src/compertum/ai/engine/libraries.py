"""Read-only Python packages for sandbox jobs (owner, 2 November 2026: "Use NumPy and other robust packages where able")."""
import base64
import csv
import hashlib
import json
from pathlib import Path
import shutil

from compertum.runtime.errors import RuntimeRefused

PACKAGES={'numpy':'2.5.4'}
LIBRARY_NAME='cp314'
CODE_ROOT=Path(__file__).resolve().parents[4]
ENGINE_SITE=CODE_ROOT/'.cache'/'engine-env'/'Lib'/'site-packages'


def library_folder(root):
    return Path(root)/'.cache'/'sandbox-libs'/LIBRARY_NAME


def manifest_path(root):
    return Path(root)/'.cache'/'sandbox-libs'/f'{LIBRARY_NAME}.json'


def file_hash(path):
    digest=hashlib.sha256()
    with open(path,'rb') as stream:
        for block in iter(lambda: stream.read(1<<20),b''): digest.update(block)
    return digest.hexdigest()


def tree_files(folder):
    files={}
    for path in sorted(Path(folder).rglob('*')):
        if path.is_symlink() or (path.is_dir() and path.is_junction()): raise RuntimeRefused('SANDBOX_LIBRARY_LINK')
        if path.is_file(): files[path.relative_to(folder).as_posix()]=file_hash(path)
    return files


def tree_hash(files):
    return hashlib.sha256(json.dumps(files,sort_keys=True,separators=(',',':')).encode('utf-8')).hexdigest()


def record_rows(site,name,version):
    record=Path(site)/f'{name}-{version}.dist-info'/'RECORD'
    if not record.is_file(): raise RuntimeRefused(f'SANDBOX_LIBRARY_MISSING:{name}-{version}')
    with open(record,encoding='utf-8',newline='') as stream:
        for path,hashed,_ in csv.reader(stream):
            if path.startswith('../') or '__pycache__' in path: continue
            yield path,hashed


def build_library(root,site):
    """Copy PACKAGES from site, check every file against its wheel RECORD hash, and write the manifest. Returns the manifest."""
    target=library_folder(root);staging=target.with_name(target.name+'.new')
    if staging.exists(): shutil.rmtree(staging)
    for name,version in PACKAGES.items():
        for path,hashed in record_rows(site,name,version):
            source=Path(site)/path;copy=staging/path;copy.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(source,copy)
            if hashed:
                algorithm,_,expected=hashed.partition('=')
                actual=base64.urlsafe_b64encode(hashlib.new(algorithm,copy.read_bytes()).digest()).rstrip(b'=').decode('ascii')
                if algorithm!='sha256' or actual!=expected: raise RuntimeRefused(f'SANDBOX_LIBRARY_HASH:{path}')
    files=tree_files(staging)
    manifest={'name':LIBRARY_NAME,'packages':PACKAGES,'files':len(files),'tree_sha256':tree_hash(files)}
    if target.exists(): shutil.rmtree(target)
    staging.rename(target)
    manifest_path(root).write_text(json.dumps(manifest,indent=1,sort_keys=True)+'\n',encoding='utf-8',newline='\n')
    return manifest


def check_library(root):
    """Refuse unless the library folder matches its manifest exactly. Returns the manifest for the run record."""
    folder=library_folder(root);path=manifest_path(root)
    if not folder.is_dir() or not path.is_file(): raise RuntimeRefused('SANDBOX_LIBRARY_MISSING')
    manifest=json.loads(path.read_text(encoding='utf-8'))
    if manifest.get('packages')!=PACKAGES or tree_hash(tree_files(folder))!=manifest.get('tree_sha256'): raise RuntimeRefused('SANDBOX_LIBRARY_CHANGED')
    return manifest


if __name__=='__main__':
    print(json.dumps(build_library(CODE_ROOT,ENGINE_SITE),indent=1))
