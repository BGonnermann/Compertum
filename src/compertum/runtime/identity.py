from dataclasses import dataclass
from pathlib import Path
import ctypes as C
import os
from . import win32 as w
from ..domain import digest

@dataclass(frozen=True)
class ProjectIdentity:
    root_path:Path
    project_id:str
    operator_sid:str
    volume:int
    root_file_id:int

def resolve_project(root):
    root=Path(root).resolve(strict=True)
    handle=w.CreateFile(str(root),0,7,None,3,0x02000000,None)
    if handle==w.INVALID: raise w.error('ROOT_IDENTITY_UNVERIFIED')
    try:
        buf=C.create_unicode_buffer(32768)
        length=w.GetPath(handle,buf,len(buf),0)
        if not length or length>=len(buf): raise w.error('ROOT_PATH_UNVERIFIED')
        info=w.FileInfo()
        if not w.GetFileInfo(handle,C.byref(info)): raise w.error('ROOT_IDENTITY_UNVERIFIED')
        name=buf.value
        prefix=chr(92)*2+'?'+chr(92)
        if name.startswith(prefix): name=name[4:]
        number=(info.index_hi<<32)|info.index_lo
        return ProjectIdentity(Path(name),digest({'volume':info.volume,'file':number}),w.identity(os.getpid())['sid'],info.volume,number)
    finally: w.CloseHandle(handle)
