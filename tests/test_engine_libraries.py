import base64
import hashlib
import json
import os
import pytest
from compertum.ai.engine import libraries
from compertum.runtime.errors import RuntimeRefused


def fake_site(site,text='VALUE = 1\n',stated=None):
    package=site/'numpy';package.mkdir(parents=True);(package/'__init__.py').write_text(text,encoding='utf-8',newline='\n')
    (package/'__pycache__').mkdir();(package/'__pycache__'/'x.pyc').write_bytes(b'cache')
    info=site/'numpy-2.5.4.dist-info';info.mkdir()
    digest=base64.urlsafe_b64encode(hashlib.sha256((stated or text).encode('utf-8')).digest()).rstrip(b'=').decode('ascii')
    (info/'METADATA').write_text('Name: numpy\n',encoding='utf-8')
    (info/'RECORD').write_text(f'numpy/__init__.py,sha256={digest},{len(text)}\nnumpy/__pycache__/x.pyc,,\n../../Scripts/f2py.exe,,\n'
                               'numpy-2.5.4.dist-info/METADATA,,\nnumpy-2.5.4.dist-info/RECORD,,\n',encoding='utf-8')
    return site


def test_build_library(tmp_path):
    """The build copies the RECORD files except caches and files outside site-packages, checks hashes, and writes a manifest."""
    manifest=libraries.build_library(tmp_path,fake_site(tmp_path/'site'))
    folder=libraries.library_folder(tmp_path)
    assert sorted(p.relative_to(folder).as_posix() for p in folder.rglob('*') if p.is_file())==['numpy-2.5.4.dist-info/METADATA','numpy-2.5.4.dist-info/RECORD','numpy/__init__.py']
    assert manifest['files']==3 and manifest['packages']=={'numpy':'2.5.4'} and libraries.check_library(tmp_path)==manifest
    assert json.loads(libraries.manifest_path(tmp_path).read_text(encoding='utf-8'))==manifest


def test_library_refusals(tmp_path):
    """A wrong hash, a missing package, a changed or added file, and a missing manifest are refused."""
    with pytest.raises(RuntimeRefused,match='^SANDBOX_LIBRARY_HASH:numpy/__init__.py$'): libraries.build_library(tmp_path,fake_site(tmp_path/'bad',stated='other\n'))
    assert not libraries.library_folder(tmp_path).exists()
    with pytest.raises(RuntimeRefused,match='^SANDBOX_LIBRARY_MISSING:numpy-2.5.4$'): libraries.build_library(tmp_path,tmp_path/'nothing')
    with pytest.raises(RuntimeRefused,match='^SANDBOX_LIBRARY_MISSING$'): libraries.check_library(tmp_path)
    libraries.build_library(tmp_path,fake_site(tmp_path/'site'));folder=libraries.library_folder(tmp_path)
    (folder/'numpy'/'__init__.py').write_text('VALUE = 2\n',encoding='utf-8',newline='\n')
    with pytest.raises(RuntimeRefused,match='^SANDBOX_LIBRARY_CHANGED$'): libraries.check_library(tmp_path)
    libraries.build_library(tmp_path,tmp_path/'site');libraries.check_library(tmp_path)
    (folder/'numpy'/'extra.py').write_text('',encoding='utf-8')
    with pytest.raises(RuntimeRefused,match='^SANDBOX_LIBRARY_CHANGED$'): libraries.check_library(tmp_path)
    os.remove(folder/'numpy'/'extra.py');libraries.check_library(tmp_path)
