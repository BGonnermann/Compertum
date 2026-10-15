"""Checked native directory ABI and build identity, using real Windows handles."""
import ctypes as c
import os
from pathlib import Path
import pytest
from compertum.runtime.errors import RuntimeRefused

pytestmark=pytest.mark.skipif(os.name!='nt',reason='NATIVE_WINDOWS_UNAVAILABLE')


def test_native_reader_retains_checked_directory_until_close(tmp_path):
    from compertum._native_storage import Directory
    (tmp_path/'one').write_bytes(b'x')
    with Directory(str(tmp_path)) as directory:
        assert directory.read()
        with pytest.raises(PermissionError):tmp_path.rename(tmp_path.with_name('moved'))
    assert directory.closed


def test_native_reader_refuses_reparse_and_file(tmp_path):
    from compertum._native_storage import Directory
    target=tmp_path/'target';target.mkdir()
    alias=tmp_path/'alias';alias.symlink_to(target,target_is_directory=True)
    file=tmp_path/'file';file.write_bytes(b'x')
    for path in (alias,file,tmp_path/'missing'):
        with pytest.raises(RuntimeRefused):
            with Directory(str(path)):pass


def test_native_reader_rejects_binary_or_source_identity_change(tmp_path):
    from compertum._native_storage import _verify_payload
    from compertum import _native_storage
    source=Path(_native_storage.__file__).parent/'_native'
    for path in source.iterdir():
        if path.is_file():(tmp_path/path.name).write_bytes(path.read_bytes())
    _verify_payload(tmp_path)
    for name in ('storage_scan.dll','storage_scan.c'):
        original=(tmp_path/name).read_bytes()
        (tmp_path/name).write_bytes(original+b'changed')
        with pytest.raises(RuntimeRefused,match='STORAGE_NATIVE_IDENTITY'):_verify_payload(tmp_path)
        (tmp_path/name).write_bytes(original)


def test_native_reader_abi_rejects_wrong_buffer_size(tmp_path):
    from compertum._native_storage import _library,Result
    library=_library();result=Result();buffer=c.create_string_buffer(65536)
    assert library.cs_open_read(str(tmp_path),buffer,65535,c.byref(result))==-1
    assert not result.handle and result.operation==1


def test_native_reader_empty_directory_has_only_dot_rows(tmp_path):
    from compertum._native_storage import Directory
    from compertum.storage import _directory_rows
    with Directory(str(tmp_path)) as directory:
        while (data:=directory.read()) is not None:assert _directory_rows(data)==[]
    assert directory.closed


@pytest.mark.parametrize('code',[-1,2])
def test_native_reader_bad_status_closes_owned_handle(tmp_path,monkeypatch,code):
    import compertum._native_storage as reader
    from types import SimpleNamespace
    real=reader._library();closed=[];owned=tmp_path/'owned';owned.mkdir()
    def opened(path,buffer,length,result):
        assert real.cs_open_read(path,buffer,length,result) in (0,1)
        return code
    def close(handle):
        closed.append(handle);return real.cs_close(handle)
    monkeypatch.setattr(reader,'_library',lambda:SimpleNamespace(cs_open_read=opened,cs_close=close))
    with pytest.raises(RuntimeRefused,match='STORAGE_SCAN_UNVERIFIED'):reader.Directory(str(owned))
    assert len(closed)==1
    owned.rename(tmp_path/'moved')


def test_native_reader_close_failure_refuses_after_real_close(tmp_path,monkeypatch):
    import compertum._native_storage as reader
    from types import SimpleNamespace
    real=reader._library()
    def close(handle):
        assert real.cs_close(handle)==0
        return 5
    monkeypatch.setattr(reader,'_library',lambda:SimpleNamespace(cs_open_read=real.cs_open_read,cs_next=real.cs_next,cs_close=close))
    with pytest.raises(RuntimeRefused,match='STORAGE_DIRECTORY_CLOSE_UNVERIFIED'):
        with reader.Directory(str(tmp_path)):pass


def test_native_reader_rejects_changed_manifest_anchor(tmp_path):
    import compertum._native_storage as reader
    source=Path(reader.__file__).parent/'_native'
    for path in source.iterdir():
        if path.is_file():(tmp_path/path.name).write_bytes(path.read_bytes())
    manifest=tmp_path/'storage_scan.json';manifest.write_bytes(manifest.read_bytes()+b' ')
    with pytest.raises(RuntimeRefused,match='STORAGE_NATIVE_IDENTITY'):reader._verify_payload(tmp_path)


def test_native_loader_rejects_link_before_loading(tmp_path,monkeypatch):
    import compertum._native_storage as reader
    package=tmp_path/'package';native=package/'_native';native.mkdir(parents=True)
    original=Path(reader.__file__).parent/'_native'
    for name in ('storage_scan.c','storage_scan.json'):
        (native/name).write_bytes((original/name).read_bytes())
    (native/'storage_scan.dll').symlink_to(original/'storage_scan.dll')
    monkeypatch.setattr(reader,'__file__',str(package/'_native_storage.py'))
    def unexpected_load(*args,**kwargs):raise AssertionError('linked DLL was loaded')
    monkeypatch.setattr(reader.c,'CDLL',unexpected_load)
    reader._library.cache_clear()
    try:
        with pytest.raises(RuntimeRefused,match='STORAGE_NATIVE_IDENTITY'):reader._library()
    finally:reader._library.cache_clear()


def test_native_loader_refuses_loaded_file_identity_mismatch(tmp_path,monkeypatch):
    import compertum._native_storage as reader
    alternate=tmp_path/'alternate.dll'
    alternate.write_bytes((Path(reader.__file__).parent/'_native/storage_scan.dll').read_bytes())
    real=reader.c.WinDLL
    def filename(handle,buffer,capacity):
        buffer.value=str(alternate);return len(buffer.value)
    class Library:
        def __init__(self,name,**kwargs):self.actual=real(name,**kwargs)
        def __getattr__(self,name):
            return filename if name=='GetModuleFileNameW' else getattr(self.actual,name)
    monkeypatch.setattr(reader.c,'WinDLL',Library)
    reader._library.cache_clear()
    try:
        with pytest.raises(RuntimeRefused,match='STORAGE_NATIVE_IDENTITY'):reader._library()
    finally:reader._library.cache_clear()
