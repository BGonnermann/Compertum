"""Pinned native directory reader. Build explicitly; never compile at runtime."""
import ctypes as c
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
import sys
from .runtime.errors import RuntimeRefused
from .runtime._windows import WindowsAPI

_MANIFEST_SHA256='db3b9925e787ab3773994e3676cfb0ceb1ba862f4abcfa79dfc87927963f6440'


class Result(c.Structure):
    _fields_=[('handle',c.c_void_p),('bytes',c.c_uint32),('status',c.c_int32),
              ('error',c.c_uint32),('operation',c.c_uint32)]


def _verify_payload(directory):
    try:
        raw=(directory/'storage_scan.json').read_bytes()
        if hashlib.sha256(raw).hexdigest()!=_MANIFEST_SHA256:raise ValueError()
        manifest=json.loads(raw)
        if manifest['abi']!=1 or manifest['platform']!='win_amd64':raise ValueError()
        for name in ('storage_scan.c','storage_scan.dll'):
            if hashlib.sha256((directory/name).read_bytes()).hexdigest()!=manifest['files'][name]:raise ValueError()
    except (OSError,ValueError,KeyError,TypeError):
        raise RuntimeRefused('STORAGE_NATIVE_IDENTITY') from None
    return manifest


@lru_cache(maxsize=1)
def _library():
    if os.name!='nt' or sys.platform!='win32' or c.sizeof(c.c_void_p)!=8:
        raise RuntimeRefused('NATIVE_WINDOWS_UNAVAILABLE')
    package=Path(__file__).parent;directory=package/'_native';api=WindowsAPI()
    # Deny replacement and writes through verification/loading. The Python hash
    # anchor also brings this payload into existing runtime/recovery identities.
    with api.open_directory(package),api.open_directory(directory),api.open_file(directory/'storage_scan.dll',0x80000000,1) as binary:
        if api.file_info(binary).attributes&0x410:
            raise RuntimeRefused('STORAGE_NATIVE_IDENTITY')
        expected_identity=api.file_identity(binary)
        _verify_payload(directory)
        library=c.CDLL(str(directory/'storage_scan.dll'),winmode=0x800,use_last_error=True)
        kernel=c.WinDLL('kernel32',use_last_error=True)
        filename=kernel.GetModuleFileNameW
        filename.argtypes=[c.c_void_p,c.c_wchar_p,c.c_uint32];filename.restype=c.c_uint32
        path=c.create_unicode_buffer(32768);count=filename(library._handle,path,len(path))
        if not 0<count<len(path) or not Path(path.value).is_absolute():
            raise RuntimeRefused('STORAGE_NATIVE_IDENTITY')
        with api.open_file(path.value,0x80000000,1) as loaded:
            if api.file_info(loaded).attributes&0x410 or api.file_identity(loaded)!=expected_identity:
                raise RuntimeRefused('STORAGE_NATIVE_IDENTITY')
    library.cs_abi.argtypes=[];library.cs_abi.restype=c.c_uint32
    if c.sizeof(Result)!=24 or library.cs_abi()!=1:raise RuntimeRefused('STORAGE_NATIVE_ABI')
    library.cs_open_read.argtypes=[c.c_wchar_p,c.c_void_p,c.c_uint32,c.POINTER(Result)]
    library.cs_open_read.restype=c.c_int
    library.cs_next.argtypes=[c.c_void_p,c.c_void_p,c.c_uint32,c.POINTER(Result)]
    library.cs_next.restype=c.c_int
    library.cs_close.argtypes=[c.c_void_p];library.cs_close.restype=c.c_uint32
    return library


class Directory:
    """Own one non-inheritable handle without delete sharing until checked close."""
    def __init__(self,path,buffer=None):
        self.library=_library();self.closed=False;self.handle=None
        self.buffer=c.create_string_buffer(65536) if buffer is None else buffer
        self.result=Result();self.first=True
        try:
            self.code=self.library.cs_open_read(path,self.buffer,len(self.buffer),c.byref(self.result))
            self.handle=self.result.handle
            self._checked(self.code)
        except BaseException:
            self.close();raise

    def _checked(self,code):
        if code not in (0,1) or code==0 and not 0<self.result.bytes<=len(self.buffer):
            raise RuntimeRefused('STORAGE_SCAN_UNVERIFIED')

    def read(self):
        if self.closed:raise RuntimeRefused('HANDLE_CLOSED')
        if self.first:self.first=False
        else:
            self.code=self.library.cs_next(self.handle,self.buffer,len(self.buffer),c.byref(self.result))
            self._checked(self.code)
        return None if self.code==1 else c.string_at(self.buffer,self.result.bytes)

    def close(self):
        if not self.closed:
            self.closed=True
            if self.handle is not None and self.library.cs_close(self.handle)!=0:
                raise RuntimeRefused('STORAGE_DIRECTORY_CLOSE_UNVERIFIED')

    def __enter__(self):return self
    def __exit__(self,*args):self.close()
