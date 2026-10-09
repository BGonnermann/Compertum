"""Small Win32 boundary. Importing it performs no I/O or native calls.

Fixed-width integer types keep the ABI definitions explicit. Native behavior
must be verified on Windows; Linux policy tests cannot qualify this adapter.
"""
import ctypes as c
import os
import sys
from pathlib import Path
from .errors import RuntimeRefused

DWORD = c.c_uint32
BOOL = c.c_int32
HANDLE = c.c_void_p
INVALID_HANDLE = c.c_void_p(-1).value


class FILETIME(c.Structure):
    _fields_ = [("low", DWORD), ("high", DWORD)]


class FILE_ID_INFO(c.Structure):
    _fields_ = [("volume", c.c_uint64), ("file_id", c.c_ubyte * 16)]


class FILE_INFO(c.Structure):
    _fields_ = [("attributes", DWORD), ("creation", FILETIME), ("access", FILETIME),
               ("write", FILETIME), ("volume", DWORD), ("size_hi", DWORD),
               ("size_lo", DWORD), ("links", DWORD), ("index_hi", DWORD), ("index_lo", DWORD)]


class SID_AND_ATTRIBUTES(c.Structure):
    _fields_ = [("sid", HANDLE), ("attributes", DWORD)]


class TOKEN_GROUPS(c.Structure):
    _fields_ = [("count", DWORD), ("groups", SID_AND_ATTRIBUTES * 1)]


class PROCESSENTRY32W(c.Structure):
    _fields_ = [("size", DWORD), ("usage", DWORD), ("pid", DWORD), ("heap", c.c_size_t),
               ("module", DWORD), ("threads", DWORD), ("parent", DWORD), ("priority", c.c_int32),
               ("flags", DWORD), ("exe", c.c_uint16 * 260)]


class NativeCallError(RuntimeRefused):
    def __init__(self, operation, error):
        self.operation = operation
        self.winerror = error
        super().__init__(f"NATIVE_CALL_FAILED:{operation}:{error}")


class OwnedHandle:
    __slots__ = ("api", "value", "closed", "created")

    def __init__(self, api, value, created=False):
        self.api = api; self.value = value; self.closed = False; self.created = created

    def get(self):
        if self.closed: raise RuntimeRefused("HANDLE_CLOSED")
        return self.value

    def close(self):
        if not self.closed:
            self.closed = True
            self.api.checked(self.api.CloseHandle(self.value), "CloseHandle")

    def __enter__(self): return self
    def __exit__(self, *args): self.close()


class WindowsAPI:
    def __init__(self):
        if os.name != "nt" or sys.platform != "win32":
            raise RuntimeRefused("NATIVE_WINDOWS_UNAVAILABLE")
        k = c.WinDLL("kernel32", use_last_error=True)
        a = c.WinDLL("advapi32", use_last_error=True)
        def bind(dll, name, result, *args):
            fn = getattr(dll, name); fn.restype = result; fn.argtypes = list(args)
            setattr(self, name, fn)
        bind(k, "CreateFileW", HANDLE, c.c_wchar_p, DWORD, DWORD, HANDLE, DWORD, DWORD, HANDLE)
        bind(k, "CloseHandle", BOOL, HANDLE)
        bind(k, "GetHandleInformation", BOOL, HANDLE, c.POINTER(DWORD))
        bind(k, "SetHandleInformation", BOOL, HANDLE, DWORD, DWORD)
        bind(k, "GetFileInformationByHandleEx", BOOL, HANDLE, c.c_int32, HANDLE, DWORD)
        bind(k, "GetFileInformationByHandle", BOOL, HANDLE, c.POINTER(FILE_INFO))
        bind(k, "GetFinalPathNameByHandleW", DWORD, HANDLE, c.c_wchar_p, DWORD, DWORD)
        bind(k, "GetDriveTypeW", DWORD, c.c_wchar_p)
        bind(k, "ReadFile", BOOL, HANDLE, HANDLE, DWORD, c.POINTER(DWORD), HANDLE)
        bind(k, "WriteFile", BOOL, HANDLE, HANDLE, DWORD, c.POINTER(DWORD), HANDLE)
        bind(k, "FlushFileBuffers", BOOL, HANDLE)
        bind(k, "MoveFileExW", BOOL, c.c_wchar_p, c.c_wchar_p, DWORD)
        bind(k, "OpenProcess", HANDLE, DWORD, BOOL, DWORD)
        bind(k, "GetProcessId", DWORD, HANDLE)
        bind(k, "GetProcessTimes", BOOL, HANDLE, c.POINTER(FILETIME), c.POINTER(FILETIME), c.POINTER(FILETIME), c.POINTER(FILETIME))
        bind(k, "WaitForSingleObject", DWORD, HANDLE, DWORD)
        bind(k, "CreateToolhelp32Snapshot", HANDLE, DWORD, DWORD)
        bind(k, "Process32FirstW", BOOL, HANDLE, c.POINTER(PROCESSENTRY32W))
        bind(k, "Process32NextW", BOOL, HANDLE, c.POINTER(PROCESSENTRY32W))
        bind(k, "LocalFree", HANDLE, HANDLE)
        bind(a, "OpenProcessToken", BOOL, HANDLE, DWORD, c.POINTER(HANDLE))
        bind(a, "GetTokenInformation", BOOL, HANDLE, c.c_int32, HANDLE, DWORD, c.POINTER(DWORD))
        bind(a, "ConvertSidToStringSidW", BOOL, HANDLE, c.POINTER(c.c_wchar_p))

    @staticmethod
    def checked(ok, operation):
        if not ok: raise NativeCallError(operation, c.get_last_error())
        return ok

    def _handle(self, value, operation):
        if value is None or value == INVALID_HANDLE:
            raise NativeCallError(operation, c.get_last_error())
        return OwnedHandle(self, value)

    def open_file(self, path, access, share, disposition=3, flags=0x00200000):
        value = self.CreateFileW(str(path), access, share, None, disposition, flags, None)
        created = disposition in (1, 4) and c.get_last_error() != 183
        h = self._handle(value, "CreateFileW"); h.created = created
        try:
            if self.handle_flags(h) & 1: raise RuntimeRefused("INHERITED_HANDLE_DENIED")
            return h
        except BaseException:
            h.close(); raise

    def handle_flags(self, h):
        result = DWORD(); self.checked(self.GetHandleInformation(h.get(), c.byref(result)), "GetHandleInformation")
        return result.value

    def set_inheritable(self, h, inherited):
        if type(inherited) is not bool: raise RuntimeRefused("INHERITED_HANDLE_DENIED")
        self.checked(self.SetHandleInformation(h.get(), 1, int(inherited)), "SetHandleInformation")
        if bool(self.handle_flags(h) & 1) != inherited: raise RuntimeRefused("INHERITED_HANDLE_DENIED")

    def file_info(self, h):
        info = FILE_INFO(); self.checked(self.GetFileInformationByHandle(h.get(), c.byref(info)), "GetFileInformationByHandle")
        return info

    def file_identity(self, h):
        info = FILE_ID_INFO()
        self.checked(self.GetFileInformationByHandleEx(h.get(), 18, c.byref(info), c.sizeof(info)), "GetFileInformationByHandleEx")
        return info.volume, bytes(info.file_id).hex()

    def final_path(self, h):
        b = c.create_unicode_buffer(32768)
        n = self.GetFinalPathNameByHandleW(h.get(), b, len(b), 0)
        if not n or n >= len(b): raise RuntimeRefused("ROOT_PATH_UNVERIFIED")
        path = b.value
        if not path.startswith("\\\\?\\") or path.startswith("\\\\?\\UNC\\"):
            raise RuntimeRefused("LOCAL_VOLUME_REQUIRED")
        return Path(path)

    def open_directory(self, path, *, follow_root=False):
        # Retain directory handles without delete sharing to block path replacement.
        h = self.open_file(path, 0x81, 3, flags=0x02000000 | (0 if follow_root else 0x00200000))
        try:
            info = self.file_info(h)
            if not info.attributes & 0x10: raise RuntimeRefused("DIRECTORY_REQUIRED")
            if not follow_root and info.attributes & 0x400: raise RuntimeRefused("REPARSE_DENIED")
            return h
        except BaseException:
            h.close(); raise

    def open_process(self, pid):
        h = self._handle(self.OpenProcess(0x00101000, False, pid), "OpenProcess")
        try:
            if self.GetProcessId(h.get()) != pid: raise RuntimeRefused("PROCESS_ID_UNVERIFIED")
            return h
        except BaseException:
            h.close(); raise

    def creation_time(self, h):
        times = [FILETIME() for _ in range(4)]
        self.checked(self.GetProcessTimes(h.get(), *(c.byref(t) for t in times)), "GetProcessTimes")
        value = times[0].low | times[0].high << 32
        if value <= 0: raise RuntimeRefused("PROCESS_TIME_UNVERIFIED")
        return value

    def _token_buffer(self, token, kind):
        needed = DWORD()
        result = self.GetTokenInformation(token.get(), kind, None, 0, c.byref(needed))
        if result or c.get_last_error() != 122 or not 0 < needed.value <= 65536:
            raise RuntimeRefused("TOKEN_UNVERIFIED")
        b = c.create_string_buffer(needed.value)
        self.checked(self.GetTokenInformation(token.get(), kind, b, len(b), c.byref(needed)), "GetTokenInformation")
        if needed.value > len(b): raise RuntimeRefused("TOKEN_UNVERIFIED")
        return b

    def _sid_string(self, sid):
        ptr = c.c_wchar_p()
        self.checked(self.ConvertSidToStringSidW(sid, c.byref(ptr)), "ConvertSidToStringSidW")
        try: return ptr.value
        finally: self.LocalFree(c.cast(ptr, HANDLE))

    def token_sids(self, process):
        token = HANDLE()
        self.checked(self.OpenProcessToken(process.get(), 8, c.byref(token)), "OpenProcessToken")
        with OwnedHandle(self, token.value) as th:
            user = self._token_buffer(th, 1)
            sid = self._sid_string(c.cast(user, c.POINTER(SID_AND_ATTRIBUTES)).contents.sid)
            groups = self._token_buffer(th, 2)
            n = DWORD.from_buffer(groups).value; offset = TOKEN_GROUPS.groups.offset
            if n > 256 or offset + n * c.sizeof(SID_AND_ATTRIBUTES) > len(groups):
                raise RuntimeRefused("LOGON_SID_UNVERIFIED")
            entries = (SID_AND_ATTRIBUTES * n).from_buffer(groups, offset)
            logons = [self._sid_string(g.sid) for g in entries if g.attributes & 0xC0000000 == 0xC0000000]
            if len(logons) != 1: raise RuntimeRefused("LOGON_SID_UNVERIFIED")
            return sid, logons[0]

    def process_snapshot(self):
        return frozenset(self._process_parents())

    def parent_pid(self, pid):
        parents = self._process_parents()
        if type(pid) is not int or pid not in parents: raise RuntimeRefused("PROCESS_SNAPSHOT_UNVERIFIED")
        return parents[pid]

    def _process_parents(self):
        with self._handle(self.CreateToolhelp32Snapshot(2, 0), "CreateToolhelp32Snapshot") as h:
            e = PROCESSENTRY32W(); e.size = c.sizeof(e); parents = {}
            ok = self.Process32FirstW(h.get(), c.byref(e))
            if not ok and c.get_last_error() != 18: raise RuntimeRefused("PROCESS_SNAPSHOT_UNVERIFIED")
            while ok:
                parents[e.pid] = e.parent
                if len(parents) > 100000: raise RuntimeRefused("PROCESS_SNAPSHOT_UNVERIFIED")
                ok = self.Process32NextW(h.get(), c.byref(e))
            if c.get_last_error() != 18: raise RuntimeRefused("PROCESS_SNAPSHOT_UNVERIFIED")
            return parents

    def read_regular(self, path, maximum=8192):
        with self.open_file(path, 0x80000000, 7) as h:
            info = self.file_info(h)
            if info.attributes & (0x400 | 0x10) or info.links != 1: raise RuntimeRefused("REPARSE_DENIED")
            if (info.size_hi << 32 | info.size_lo) > maximum: raise RuntimeRefused("METADATA_TOO_LARGE")
            b = c.create_string_buffer(maximum + 1); n = DWORD()
            self.checked(self.ReadFile(h.get(), b, len(b), c.byref(n), None), "ReadFile")
            if n.value > maximum: raise RuntimeRefused("METADATA_TOO_LARGE")
            return b.raw[:n.value]

    def publish_metadata(self, path, data):
        import uuid
        if len(data) > 8192: raise RuntimeRefused("METADATA_TOO_LARGE")
        tmp = path.parent / (path.name + ".incoming-" + str(uuid.uuid4()))
        with self.open_file(tmp, 0xC0000000, 0, disposition=1) as h:
            b = c.create_string_buffer(data); n = DWORD()
            self.checked(self.WriteFile(h.get(), b, len(data), c.byref(n), None), "WriteFile")
            if n.value != len(data): raise RuntimeRefused("METADATA_WRITE_UNVERIFIED")
            self.checked(self.FlushFileBuffers(h.get()), "FlushFileBuffers")
        self.checked(self.MoveFileExW(str(tmp), str(path), 9), "MoveFileExW")
        if self.read_regular(path) != data: raise RuntimeRefused("METADATA_WRITE_UNVERIFIED")
