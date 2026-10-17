"""Read accessible Windows process metadata. No command text leaves this module."""
import ctypes as c
from ctypes import wintypes as w
from datetime import datetime, timezone
import os
from pathlib import Path
import sys
import time

from activity_labels import activity_label


def project_path(value, root):
    try:
        if not isinstance(value, str) or not value:
            return False
        path = Path(value.removeprefix('\\\\?\\'))
        return path.is_absolute() and path.resolve().is_relative_to(Path(root).resolve())
    except (OSError, ValueError, RuntimeError):
        return False


def observe(root, exclude_pids=None):
    result = {'status': 'Unavailable', 'processes': [], 'unreadable_candidates': 0, 'limited': False}
    if os.name != 'nt' or c.sizeof(c.c_void_p) != 8:
        return result
    excluded = {os.getpid()} if exclude_pids is None else exclude_pids
    kernel = c.WinDLL('kernel32', use_last_error=True)
    native = c.WinDLL('ntdll')

    class Entry(c.Structure):
        _fields_ = [('size', w.DWORD), ('usage', w.DWORD), ('pid', w.DWORD), ('heap', c.c_size_t),
                    ('module', w.DWORD), ('threads', w.DWORD), ('parent', w.DWORD), ('priority', w.LONG),
                    ('flags', w.DWORD), ('exe', w.WCHAR * 260)]
    class Basic(c.Structure):
        _fields_ = [('reserved', c.c_void_p), ('peb', c.c_void_p), ('reserved2', c.c_void_p * 2),
                    ('pid', c.c_size_t), ('reserved3', c.c_void_p)]
    class Unicode(c.Structure):
        _fields_ = [('length', w.USHORT), ('maximum', w.USHORT), ('buffer', c.c_void_p)]
    class Peb(c.Structure):
        _fields_ = [('reserved', c.c_byte * 4), ('reserved2', c.c_void_p * 2),
                    ('loader', c.c_void_p), ('parameters', c.c_void_p)]
    class Parameters(c.Structure):
        _fields_ = [('lengths', w.DWORD * 4), ('console', c.c_void_p), ('console_flags', w.DWORD),
                    ('standard_in', c.c_void_p), ('standard_out', c.c_void_p), ('standard_error', c.c_void_p),
                    ('directory', Unicode), ('directory_handle', c.c_void_p), ('dll_path', Unicode),
                    ('image_path', Unicode), ('command', Unicode)]
    kernel.CreateToolhelp32Snapshot.argtypes = [w.DWORD, w.DWORD]; kernel.CreateToolhelp32Snapshot.restype = w.HANDLE
    kernel.Process32FirstW.argtypes = kernel.Process32NextW.argtypes = [w.HANDLE, c.POINTER(Entry)]
    kernel.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]; kernel.OpenProcess.restype = w.HANDLE
    kernel.CloseHandle.argtypes = [w.HANDLE]
    kernel.ReadProcessMemory.argtypes = [w.HANDLE, c.c_void_p, c.c_void_p, c.c_size_t, c.POINTER(c.c_size_t)]
    kernel.GetProcessTimes.argtypes = [w.HANDLE, c.POINTER(w.FILETIME), c.POINTER(w.FILETIME), c.POINTER(w.FILETIME), c.POINTER(w.FILETIME)]
    native.NtQueryInformationProcess.argtypes = [w.HANDLE, w.ULONG, c.c_void_p, w.ULONG, c.POINTER(w.ULONG)]
    native.NtQueryInformationProcess.restype = w.LONG

    def read(handle, address, size):
        if not address or not 0 < size <= 65536:
            raise OSError('Process metadata unavailable')
        buffer = c.create_string_buffer(size); copied = c.c_size_t()
        if not kernel.ReadProcessMemory(handle, address, buffer, size, c.byref(copied)) or copied.value != size:
            raise OSError('Process metadata unavailable')
        return buffer.raw

    def string(handle, value):
        if value.length > 32768 or value.length % 2 or value.length > value.maximum:
            raise OSError('Invalid process text')
        return read(handle, value.buffer, value.length).decode('utf-16-le') if value.length else ''

    snapshot = kernel.CreateToolhelp32Snapshot(2, 0)
    if snapshot in (None, c.c_void_p(-1).value):
        return result
    deadline = time.monotonic() + 0.75
    count = 0
    try:
        entry = Entry(); entry.size = c.sizeof(Entry)
        more = kernel.Process32FirstW(snapshot, c.byref(entry))
        while more:
            name = entry.exe.lower()
            if name in {'python.exe', 'pythonw.exe', 'node.exe', 'pwsh.exe', 'powershell.exe', 'cmd.exe', 'git.exe', 'codex.exe'} and entry.pid not in excluded:
                count += 1
                if count > 128 or time.monotonic() > deadline:
                    result['limited'] = True; break
                handle = kernel.OpenProcess(0x0410, False, entry.pid)
                if not handle:
                    result['unreadable_candidates'] += 1
                else:
                    try:
                        basic = Basic(); size = w.ULONG()
                        if native.NtQueryInformationProcess(handle, 0, c.byref(basic), c.sizeof(basic), c.byref(size)) != 0:
                            raise OSError('Process identity unavailable')
                        peb = Peb.from_buffer_copy(read(handle, basic.peb, c.sizeof(Peb)))
                        parameters = Parameters.from_buffer_copy(read(handle, peb.parameters, c.sizeof(Parameters)))
                        cwd = string(handle, parameters.directory)
                        if project_path(cwd, root):
                            command = string(handle, parameters.command)
                            # Exclude the Hub itself. It is the observer, not project work.
                            if 'hub/server.py' not in command.replace('\\', '/') and 'hub\\server.py' not in command:
                                created, exited, cpu_kernel, cpu_user = (w.FILETIME() for _ in range(4))
                                if not kernel.GetProcessTimes(handle, c.byref(created), c.byref(exited), c.byref(cpu_kernel), c.byref(cpu_user)):
                                    raise OSError('Process creation time unavailable')
                                ticks = (created.dwHighDateTime << 32) | created.dwLowDateTime
                                started = datetime.fromtimestamp(ticks / 10000000 - 11644473600, timezone.utc).isoformat().replace('+00:00', 'Z')
                                label = activity_label(text=command)
                                kind = 'test' if label == 'Running test tools' else 'work'
                                result['processes'].append({'pid': entry.pid, 'identity': f'{entry.pid}-{ticks}', 'started_at': started,
                                    'state': 'Process observed', 'kind': kind, 'stage': 'verification' if kind == 'test' else 'unclassified',
                                    'label': 'Test process' if kind == 'test' else 'Project process', 'program': name})
                    except (OSError, UnicodeError, ValueError, OverflowError):
                        result['unreadable_candidates'] += 1
                    finally:
                        kernel.CloseHandle(handle)
            more = kernel.Process32NextW(snapshot, c.byref(entry))
        result['status'] = 'Partial' if result['limited'] or result['unreadable_candidates'] else 'Available'
    finally:
        kernel.CloseHandle(snapshot)
    return result
