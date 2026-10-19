"""Query-only identity adapter. Construction is explicit; imports do no native work."""
import ctypes as c
import os

from prepare_pipe_policy import Observation
from prepare_pipe_experiment import checked_observation


class IdentityReader:
    def __init__(self, api):
        from compertum.runtime._windows import HANDLE, DWORD, BOOL
        self.api = api
        self.open_thread = c.WinDLL('advapi32', use_last_error=True).OpenThreadToken
        self.open_thread.argtypes = [HANDLE, DWORD, BOOL, c.POINTER(HANDLE)]
        self.open_thread.restype = BOOL

    def fields(self, token):
        from compertum.runtime._windows import HANDLE, DWORD, SID_AND_ATTRIBUTES, TOKEN_GROUPS
        api = self.api
        def sid(kind):
            buf = api._token_buffer(token, kind)
            return api._sid_string(c.cast(buf, c.POINTER(SID_AND_ATTRIBUTES)).contents.sid)
        app = api._token_buffer(token, 29)
        if len(app) != 4 or DWORD.from_buffer(app).value != 1:
            raise RuntimeError('APPCONTAINER_REQUIRED')
        groups = api._token_buffer(token, 2)
        count, offset = DWORD.from_buffer(groups).value, TOKEN_GROUPS.groups.offset
        if not 1 <= count <= 256 or offset + count*c.sizeof(SID_AND_ATTRIBUTES) > len(groups):
            raise RuntimeError('TOKEN_GROUP_BOUNDS')
        values = (SID_AND_ATTRIBUTES * count).from_buffer(groups, offset)
        logons = [api._sid_string(g.sid) for g in values if g.attributes & 0xC0000000 == 0xC0000000]
        if len(logons) != 1:
            raise RuntimeError('LOGON_IDENTITY_UNVERIFIED')
        buf = api._token_buffer(token, 31)
        if len(buf) < c.sizeof(HANDLE):
            raise RuntimeError('APPLICATION_IDENTITY_UNVERIFIED')
        ptr = c.cast(buf, c.POINTER(HANDLE)).contents.value
        if not ptr:
            raise RuntimeError('APPLICATION_IDENTITY_UNVERIFIED')
        return dict(operator_sid=sid(1), logon_sid=logons[0], app_sid=api._sid_string(ptr),
                    integrity_rid=int(sid(25).rsplit('-', 1)[1]))

    def process(self, handle, pid):
        from compertum.runtime._windows import HANDLE, OwnedHandle
        token = HANDLE()
        self.api.checked(self.api.OpenProcessToken(handle.get(), 8, c.byref(token)), 'OpenProcessToken')
        with OwnedHandle(self.api, token.value) as query:
            value = Observation(pid, self.api.creation_time(handle), **self.fields(query))
        value.validate()
        if self.api.WaitForSingleObject(handle.get(), 0) != 258:
            raise RuntimeError('PROCESS_NOT_LIVE')
        return value

    def current(self, handle, expected_identity, *, retained=None):
        from compertum.runtime._windows import HANDLE, OwnedHandle, NativeCallError
        process = self.process(handle, os.getpid())
        token = HANDLE()
        if self.open_thread(HANDLE(-2), 8, True, c.byref(token)):
            with OwnedHandle(self.api, token.value) as query:
                effective = Observation(process.pid, process.creation_time, **self.fields(query))
        elif c.get_last_error() == 1008:
            effective = process
        else:
            raise NativeCallError('OpenThreadToken', c.get_last_error())
        return checked_observation(process, effective, expected_identity, retained=retained)
