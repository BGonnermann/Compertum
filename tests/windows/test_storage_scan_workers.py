"""Native inventory readers retain path locks and leave no work behind."""
from contextlib import contextmanager
import os
import struct
import threading
from pathlib import Path
import pytest
import compertum.storage as storage
from compertum.runtime.errors import RuntimeRefused
from compertum.runtime.identity import resolve_project

pytestmark=pytest.mark.skipif(os.name!='nt',reason='NATIVE_WINDOWS_UNAVAILABLE')


def readers():
    return [t for t in threading.enumerate() if t.name.startswith('CompertumStorageScan-')]


def test_native_reads_overlap_but_volume_callbacks_stay_on_caller(tmp_path,monkeypatch):
    for i in range(12):
        p=tmp_path/str(i);p.mkdir();(p/'one.bin').write_bytes(b'x')
    project=resolve_project(tmp_path)
    caller=threading.get_ident();seen=set();callbacks=[]
    original=storage.WindowsAPI.open_directory
    @contextmanager
    def opened(self,path,**kwargs):
        seen.add(threading.get_ident())
        with original(self,path,**kwargs) as handle:yield handle
    monkeypatch.setattr(storage.WindowsAPI,'open_directory',opened)
    observed=storage.sample_storage(project,volume_probe=lambda:callbacks.append(threading.get_ident()))
    assert len(observed['files'])==12
    assert 1<len(seen)<=4 and caller not in seen
    assert callbacks and set(callbacks)=={caller}
    assert not readers()


def test_directory_lock_survives_until_reparse_validation(tmp_path,monkeypatch):
    directory=tmp_path/'locked';directory.mkdir()
    target=tmp_path/'data';target.mkdir();(target/'one').write_bytes(b'x')
    alias=directory/'alias';alias.symlink_to(target,target_is_directory=True)
    original=Path.resolve;checked=[]
    def resolve(path,*args,**kwargs):
        if path.name=='alias' and path.parent.name=='locked':
            with pytest.raises(PermissionError):directory.rename(tmp_path/'replaced')
            checked.append(True)
        return original(path,*args,**kwargs)
    monkeypatch.setattr(Path,'resolve',resolve)
    observed=storage.sample_storage(resolve_project(tmp_path))
    assert checked and observed['reparse_paths']==['locked/alias']
    assert not readers()


@pytest.mark.parametrize('failure',['native','callback','deadline'])
def test_failure_closes_every_reader_and_directory(tmp_path,monkeypatch,failure):
    for i in range(12):(tmp_path/str(i)).mkdir()
    project=resolve_project(tmp_path);handles=[];original=storage.WindowsAPI.open_directory
    @contextmanager
    def opened(self,path,**kwargs):
        with original(self,path,**kwargs) as handle:
            handles.append(handle)
            if failure=='native':raise RuntimeRefused('INJECTED_NATIVE_FAILURE')
            yield handle
    monkeypatch.setattr(storage.WindowsAPI,'open_directory',opened)
    calls=0;clock=storage.time.monotonic;start=clock()
    def probe():
        nonlocal calls
        calls+=1
        if calls>=2:
            if failure=='callback':raise RuntimeRefused('INJECTED_CALLBACK_FAILURE')
            if failure=='deadline':monkeypatch.setattr(storage.time,'monotonic',lambda:start+6)
    expected={'native':'INJECTED_NATIVE_FAILURE','callback':'INJECTED_CALLBACK_FAILURE','deadline':'STORAGE_SCAN_DEADLINE'}[failure]
    with pytest.raises(RuntimeRefused,match=expected):storage.sample_storage(project,volume_probe=probe)
    assert handles and all(h.closed for h in handles)
    assert not readers()


def test_final_directory_close_failure_never_reports_complete(tmp_path,monkeypatch):
    project=resolve_project(tmp_path);original=storage.WindowsAPI.open_directory
    original_event=storage.Event;events=[];handles=[]
    def event():
        value=original_event();events.append(value);return value
    @contextmanager
    def opened(self,path,**kwargs):
        with original(self,path,**kwargs) as handle:
            handles.append(handle);yield handle
        assert events[0].wait(2),'caller did not start teardown'
        raise RuntimeRefused('INJECTED_DIRECTORY_CLOSE_FAILURE')
    monkeypatch.setattr(storage,'Event',event)
    monkeypatch.setattr(storage.WindowsAPI,'open_directory',opened)
    with pytest.raises(RuntimeRefused,match='INJECTED_DIRECTORY_CLOSE_FAILURE'):
        storage.sample_storage(project)
    assert handles and all(h.closed for h in handles) and not readers()


@pytest.mark.parametrize('damage',['header','odd_name','name_overrun','short_step','unaligned_step','oversized_step','negative_allocation'])
def test_malformed_native_rows_refuse_before_inventory(tmp_path,monkeypatch,damage):
    from types import SimpleNamespace
    project=resolve_project(tmp_path);data=bytearray(70)
    struct.pack_into('<IIqqqqqqIII',data,0,0,0,0,0,0,0,1,4096,0,2,0)
    data[68:70]='a'.encode('utf-16-le')
    if damage=='header':data=data[:60]
    elif damage=='odd_name':struct.pack_into('<I',data,60,1)
    elif damage=='name_overrun':struct.pack_into('<I',data,60,4)
    elif damage=='short_step':struct.pack_into('<I',data,0,8)
    elif damage=='unaligned_step':struct.pack_into('<I',data,0,69)
    elif damage=='oversized_step':struct.pack_into('<I',data,0,80)
    else:struct.pack_into('<q',data,48,-1)
    original=storage.c.WinDLL;calls=0
    def query(handle,event,apc,context,status,buffer,length,kind,single,name,restart):
        nonlocal calls
        calls+=1
        if calls>1:return -2147483642
        storage.c.memmove(buffer,bytes(data),len(data))
        storage.c.cast(status,storage.c.POINTER(storage.IOStatus)).contents.information=len(data)
        return 0
    def load(name,**kwargs):
        return SimpleNamespace(NtQueryDirectoryFile=query) if name=='ntdll' else original(name,**kwargs)
    monkeypatch.setattr(storage.c,'WinDLL',load)
    with pytest.raises(RuntimeRefused,match='STORAGE_SCAN_UNVERIFIED'):storage.sample_storage(project)
    assert not readers()
