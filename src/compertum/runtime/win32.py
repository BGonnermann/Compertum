import ctypes as C
from ctypes import wintypes as W

K=C.WinDLL('kernel32',use_last_error=True)
A=C.WinDLL('advapi32',use_last_error=True)
INVALID=C.c_void_p(-1).value
def bind(dll,name,args,result):
    fn=getattr(dll,name); fn.argtypes=args; fn.restype=result; return fn
CreateFile=bind(K,'CreateFileW',[W.LPCWSTR,W.DWORD,W.DWORD,C.c_void_p,W.DWORD,W.DWORD,W.HANDLE],W.HANDLE)
CloseHandle=bind(K,'CloseHandle',[W.HANDLE],W.BOOL)
GetCurrentProcess=bind(K,'GetCurrentProcess',[],W.HANDLE)
OpenProcess=bind(K,'OpenProcess',[W.DWORD,W.BOOL,W.DWORD],W.HANDLE)
Wait=bind(K,'WaitForSingleObject',[W.HANDLE,W.DWORD],W.DWORD)
GetTimes=bind(K,'GetProcessTimes',[W.HANDLE,C.POINTER(W.FILETIME),C.POINTER(W.FILETIME),C.POINTER(W.FILETIME),C.POINTER(W.FILETIME)],W.BOOL)
GetPath=bind(K,'GetFinalPathNameByHandleW',[W.HANDLE,W.LPWSTR,W.DWORD,W.DWORD],W.DWORD)
class FileInfo(C.Structure):
    _fields_=[('attrs',W.DWORD),('created',W.FILETIME),('accessed',W.FILETIME),('written',W.FILETIME),('volume',W.DWORD),('size_hi',W.DWORD),('size_lo',W.DWORD),('links',W.DWORD),('index_hi',W.DWORD),('index_lo',W.DWORD)]
GetFileInfo=bind(K,'GetFileInformationByHandle',[W.HANDLE,C.POINTER(FileInfo)],W.BOOL)
OpenToken=bind(A,'OpenProcessToken',[W.HANDLE,W.DWORD,C.POINTER(W.HANDLE)],W.BOOL)
GetToken=bind(A,'GetTokenInformation',[W.HANDLE,C.c_int,C.c_void_p,W.DWORD,C.POINTER(W.DWORD)],W.BOOL)
SidString=bind(A,'ConvertSidToStringSidW',[C.c_void_p,C.POINTER(W.LPWSTR)],W.BOOL)
LocalFree=bind(K,'LocalFree',[C.c_void_p],C.c_void_p)
Snapshot=bind(K,'CreateToolhelp32Snapshot',[W.DWORD,W.DWORD],W.HANDLE)
class ProcessEntry(C.Structure):
    _fields_=[('size',W.DWORD),('usage',W.DWORD),('pid',W.DWORD),('heap',C.c_size_t),('module',W.DWORD),('threads',W.DWORD),('parent',W.DWORD),('priority',W.LONG),('flags',W.DWORD),('exe',W.WCHAR*260)]
First=bind(K,'Process32FirstW',[W.HANDLE,C.POINTER(ProcessEntry)],W.BOOL)
Next=bind(K,'Process32NextW',[W.HANDLE,C.POINTER(ProcessEntry)],W.BOOL)

def error(reason): return OSError(C.get_last_error(),reason)
def identity(pid):
    process=OpenProcess(0x1000|0x100000,False,pid)
    if not process: raise error('PROCESS_IDENTITY_UNVERIFIED')
    try:
        times=[W.FILETIME() for _ in range(4)]
        if not GetTimes(process,*[C.byref(t) for t in times]): raise error('PROCESS_TIMES_UNVERIFIED')
        token=W.HANDLE()
        if not OpenToken(process,8,C.byref(token)): raise error('TOKEN_IDENTITY_UNVERIFIED')
        try:
            length=W.DWORD(); GetToken(token,1,None,0,C.byref(length)); buf=C.create_string_buffer(length.value)
            if not GetToken(token,1,buf,length,C.byref(length)): raise error('TOKEN_IDENTITY_UNVERIFIED')
            sid=C.cast(buf,C.POINTER(C.c_void_p))[0]; text=W.LPWSTR()
            if not SidString(sid,C.byref(text)): raise error('SID_UNVERIFIED')
            try: sid_text=text.value
            finally: LocalFree(C.cast(text,C.c_void_p))
        finally: CloseHandle(token)
        return {'pid':pid,'creation_time':(times[0].dwHighDateTime<<32)|times[0].dwLowDateTime,'sid':sid_text,'exited':Wait(process,0)==0}
    finally: CloseHandle(process)

def process_absent(pid):
    snapshot=Snapshot(2,0)
    if snapshot==INVALID: raise error('PROCESS_SNAPSHOT_UNVERIFIED')
    entry=ProcessEntry(); entry.size=C.sizeof(entry)
    try:
        if not First(snapshot,C.byref(entry)): raise error('PROCESS_SNAPSHOT_UNVERIFIED')
        while True:
            if entry.pid==pid: return False
            if not Next(snapshot,C.byref(entry)):
                if C.get_last_error()!=18: raise error('PROCESS_SNAPSHOT_UNVERIFIED')
                return True
    finally: CloseHandle(snapshot)
