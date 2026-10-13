"""Restricted local byte pipes with bounded, sequential overlapped operations.

Native qualification remains mandatory. A timeout never frees an OVERLAPPED
structure or its buffer while Windows may still use it. If cancellation does
not finish within one second, retain that allocation and prohibit new pipes
in this process. This is transport cancellation, not Job-tree cancellation.
"""
from contextlib import contextmanager
import ctypes as c
from dataclasses import dataclass
import math
import re
import struct
import threading
import time
from .errors import RuntimeRefused
from ._windows import WindowsAPI, DWORD, BOOL, HANDLE, NativeCallError
from .identity import PeerObservation

MAX_FRAME = 65536
CLIENT_ACCESS = 0x00100083
_UNCERTAIN = []
_INFLIGHT = {}
_UNCERTAIN_LOCK = threading.Lock()


def frame_bytes(raw):
    if not isinstance(raw, bytes) or not 1 <= len(raw) <= MAX_FRAME:
        raise RuntimeRefused("FRAME_DENIED")
    return struct.pack("<I", len(raw)) + raw


def frame_length(header):
    if not isinstance(header, bytes) or len(header) != 4: raise RuntimeRefused("FRAME_DENIED")
    n = struct.unpack("<I", header)[0]
    if not 1 <= n <= MAX_FRAME: raise RuntimeRefused("FRAME_DENIED")
    return n


def pipe_name(registration):
    from .ipc import PeerRegistration
    if not isinstance(registration, PeerRegistration): raise RuntimeRefused("INVALID_REGISTRATION")
    return ("\\\\.\\pipe\\compertum-" + registration.project_id + "-" + registration.identity.role
            + "-" + registration.identity.process_instance_id + "-" + str(registration.generation))


def pipe_security(operator_sid, logon_sid):
    if (not isinstance(operator_sid, str) or not re.fullmatch(r"S-1-(?:\d+-){1,14}\d+", operator_sid)
            or len(operator_sid) > 184 or not isinstance(logon_sid, str)
            or not re.fullmatch(r"S-1-5-5-\d+-\d+", logon_sid)):
        raise RuntimeRefused("PIPE_SID_DENIED")
    # A protected DACL with explicit data rights. FILE_APPEND_DATA is also
    # FILE_CREATE_PIPE_INSTANCE; neither it nor generic-write is admitted.
    return f"D:P(A;;0x{CLIENT_ACCESS:08x};;;{operator_sid})(A;;0x{CLIENT_ACCESS:08x};;;{logon_sid})"


def verify_peer(registration, observed):
    from .ipc import PeerRegistration
    if (not isinstance(registration, PeerRegistration) or not isinstance(observed, PeerObservation)
            or (observed.pid, observed.creation_filetime, observed.operator_sid, observed.logon_sid) !=
               (registration.identity.pid, registration.identity.creation_filetime,
                registration.identity.operator_sid, registration.logon_sid)):
        raise RuntimeRefused("PEER_MISMATCH")


def deadline_after(timeout):
    if type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0 < timeout <= 5:
        raise RuntimeRefused("PIPE_DEADLINE_DENIED")
    return time.monotonic() + timeout


def _milliseconds(deadline):
    remaining = deadline - time.monotonic()
    if remaining <= 0: raise RuntimeRefused("PIPE_DEADLINE_EXCEEDED")
    return max(1, min(5000, math.ceil(remaining * 1000)))


class SECURITY_ATTRIBUTES(c.Structure):
    _fields_ = [("length", DWORD), ("descriptor", HANDLE), ("inherit", BOOL)]


class OVERLAPPED(c.Structure):
    _fields_ = [("internal", c.c_size_t), ("internal_high", c.c_size_t),
               ("offset", DWORD), ("offset_high", DWORD), ("event", HANDLE)]


@dataclass
class _Operation:
    event: object
    overlapped: OVERLAPPED
    buffer: object


class NativePipeAPI(WindowsAPI):
    def __init__(self):
        super().__init__()
        self._admit()
        k = c.WinDLL("kernel32", use_last_error=True)
        a = c.WinDLL("advapi32", use_last_error=True)
        def bind(dll, name, result, *args):
            fn = getattr(dll, name); fn.restype = result; fn.argtypes = list(args)
            setattr(self, name, fn)
        bind(k, "CreateNamedPipeW", HANDLE, c.c_wchar_p, DWORD, DWORD, DWORD, DWORD, DWORD, DWORD,
             c.POINTER(SECURITY_ATTRIBUTES))
        bind(k, "ConnectNamedPipe", BOOL, HANDLE, c.POINTER(OVERLAPPED))
        bind(k, "DisconnectNamedPipe", BOOL, HANDLE)
        bind(k, "GetNamedPipeClientProcessId", BOOL, HANDLE, c.POINTER(DWORD))
        bind(k, "GetNamedPipeServerProcessId", BOOL, HANDLE, c.POINTER(DWORD))
        bind(k, "CreateEventW", HANDLE, HANDLE, BOOL, BOOL, c.c_wchar_p)
        bind(k, "GetOverlappedResult", BOOL, HANDLE, c.POINTER(OVERLAPPED), c.POINTER(DWORD), BOOL)
        bind(k, "CancelIoEx", BOOL, HANDLE, c.POINTER(OVERLAPPED))
        bind(a, "ConvertStringSecurityDescriptorToSecurityDescriptorW", BOOL, c.c_wchar_p, DWORD,
             c.POINTER(HANDLE), c.POINTER(DWORD))

    @staticmethod
    def _admit():
        with _UNCERTAIN_LOCK:
            if _UNCERTAIN or _INFLIGHT: raise RuntimeRefused("PIPE_CANCELLATION_UNVERIFIED")

    def _quarantine(self, pipe, operation):
        with _UNCERTAIN_LOCK:
            if not any(item[2] is operation for item in _UNCERTAIN):
                _UNCERTAIN.append((self, pipe, operation))

    def server(self, registration):
        self._admit()
        sd = HANDLE(); size = DWORD()
        self.checked(self.ConvertStringSecurityDescriptorToSecurityDescriptorW(
            pipe_security(registration.identity.operator_sid, registration.logon_sid),
            1, c.byref(sd), c.byref(size)), "ConvertStringSecurityDescriptorToSecurityDescriptorW")
        try:
            sa = SECURITY_ATTRIBUTES(c.sizeof(SECURITY_ATTRIBUTES), sd, False)
            # Duplex, overlapped, first instance; byte mode, reject remote clients.
            value = self.CreateNamedPipeW(pipe_name(registration), 3 | 0x40000000 | 0x00080000,
                                         0x8, 1, MAX_FRAME + 4, MAX_FRAME + 4, 5000, c.byref(sa))
            error = c.get_last_error()
            try: handle = self._handle(value, "CreateNamedPipeW")
            except NativeCallError:
                if error == 5: raise RuntimeRefused("PIPE_NAME_OCCUPIED") from None
                raise
            try:
                if self.handle_flags(handle) & 1: raise RuntimeRefused("INHERITED_HANDLE_DENIED")
                return handle
            except BaseException:
                handle.close(); raise
        finally: self.LocalFree(sd)

    def client(self, registration):
        self._admit()
        # Local generated name only. Busy/absent never triggers trust or a new owner.
        return self.open_file(pipe_name(registration), CLIENT_ACCESS, 0, flags=0x40000000 | 0x00100000)

    def _cancel(self, pipe, operation):
        # Cancellation is a request; completion must be observed before disposal.
        try:
            self.CancelIoEx(pipe.get(), c.byref(operation.overlapped))
            waited = self.WaitForSingleObject(operation.event.get(), 1000)
            n = DWORD()
            ok = self.GetOverlappedResult(pipe.get(), c.byref(operation.overlapped), c.byref(n), False)
            error = c.get_last_error()
            if waited != 0 or (not ok and error not in (995, 109, 232, 233)):
                raise RuntimeRefused("PIPE_CANCELLATION_UNVERIFIED")
        except BaseException:
            self._quarantine(pipe, operation)
            raise

    def _io(self, pipe, kind, buffer, count, deadline):
        self._admit(); _milliseconds(deadline)
        event = self._handle(self.CreateEventW(None, True, False, None), "CreateEventW")
        op = _Operation(event, OVERLAPPED(event=event.get()), buffer)
        transferred = DWORD(); pending = True; quarantined = False
        # Strong lifetime ownership precedes the submission call itself. This
        # process admits one native pipe operation at a time. If interrupted
        # before its result is known, the gate remains closed with storage held.
        with _UNCERTAIN_LOCK:
            if _UNCERTAIN or _INFLIGHT:
                event.close()
                raise RuntimeRefused("PIPE_CANCELLATION_UNVERIFIED")
            _INFLIGHT[id(op)] = (self, pipe, op)
        try:
            if kind == "connect": ok = self.ConnectNamedPipe(pipe.get(), c.byref(op.overlapped))
            elif kind == "read": ok = self.ReadFile(pipe.get(), buffer, count, c.byref(transferred), c.byref(op.overlapped))
            else: ok = self.WriteFile(pipe.get(), buffer, count, c.byref(transferred), c.byref(op.overlapped))
            error = c.get_last_error()
            if not ok and kind == "connect" and error == 535:
                pending = False
                return 0
            if not ok and error != 997:
                pending = False  # Win32 reports that no asynchronous I/O began.
                raise NativeCallError(kind, error)
            pending = not ok
            if pending:
                wait = self.WaitForSingleObject(event.get(), _milliseconds(deadline))
                if wait != 0: raise RuntimeRefused("PIPE_DEADLINE_EXCEEDED")
            self.checked(self.GetOverlappedResult(pipe.get(), c.byref(op.overlapped),
                                                 c.byref(transferred), False), "GetOverlappedResult")
            pending = False
            return 0 if kind == "connect" else transferred.value
        except BaseException:
            if pending:
                try: self._cancel(pipe, op)
                except BaseException:
                    quarantined = True
                    self._quarantine(pipe, op)
                    raise
            raise
        finally:
            if not quarantined:
                with _UNCERTAIN_LOCK: _INFLIGHT.pop(id(op), None)
                event.close()

    def connect(self, pipe, deadline): self._io(pipe, "connect", None, 0, deadline)

    def disconnect(self, pipe):
        ok = self.DisconnectNamedPipe(pipe.get())
        if not ok and c.get_last_error() != 233:
            raise NativeCallError("DisconnectNamedPipe", c.get_last_error())

    def _read_exact(self, pipe, count, deadline):
        result = bytearray()
        while len(result) < count:
            buffer = c.create_string_buffer(count - len(result))
            n = self._io(pipe, "read", buffer, len(buffer), deadline)
            if not 0 < n <= len(buffer): raise RuntimeRefused("PIPE_EOF")
            result.extend(buffer.raw[:n])
        return bytes(result)

    def read_frame(self, pipe, deadline):
        count = frame_length(self._read_exact(pipe, 4, deadline))
        return self._read_exact(pipe, count, deadline)

    def write_frame(self, pipe, raw, deadline):
        data = frame_bytes(raw); offset = 0
        while offset < len(data):
            buffer = c.create_string_buffer(data[offset:])
            n = self._io(pipe, "write", buffer, len(data) - offset, deadline)
            if not 0 < n <= len(data) - offset: raise RuntimeRefused("PIPE_WRITE_UNVERIFIED")
            offset += n

    @contextmanager
    def peer(self, pipe, *, server_side):
        pid = DWORD()
        fn = self.GetNamedPipeClientProcessId if server_side else self.GetNamedPipeServerProcessId
        self.checked(fn(pipe.get(), c.byref(pid)), "GetNamedPipePeerProcessId")
        if not pid.value: raise RuntimeRefused("PEER_UNVERIFIED")
        # Keep the native process object alive throughout the exchange.
        with self.open_process(pid.value) as handle:
            creation = self.creation_time(handle); sid, logon = self.token_sids(handle)
            if self.WaitForSingleObject(handle.get(), 0) != 258: raise RuntimeRefused("PEER_UNVERIFIED")
            observed = PeerObservation(pid.value, creation, sid, logon)
            yield observed
