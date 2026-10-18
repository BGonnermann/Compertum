"""Observe local pipe access without changing permissions or saved runtimes."""
import ctypes as c
import hashlib
import json
import os
import re
from pathlib import Path
import sys
import time
from uuid import uuid4

from compertum.domain import ProcessIdentity
from compertum.runtime.ipc import PeerRegistration
from compertum.runtime._pipes import NativePipeAPI, CLIENT_ACCESS, pipe_name, pipe_security
from compertum.runtime._windows import BOOL, DWORD, HANDLE, OwnedHandle, NativeCallError, SID_AND_ATTRIBUTES, TOKEN_GROUPS


def restriction_value(buffer):
    """Accept the observed byte or documented DWORD; refuse other sizes."""
    size = len(buffer)
    if size not in (1, 4):
        raise RuntimeError('TOKEN_RESTRICTION_SIZE_UNEXPECTED')
    return bool(int.from_bytes(bytes(buffer), 'little')), size


def observe(result):
    started = time.monotonic()
    api = NativePipeAPI()
    advapi = c.WinDLL('advapi32', use_last_error=True)
    get_security = advapi.GetSecurityInfo
    get_security.argtypes = [HANDLE, DWORD, DWORD, c.POINTER(HANDLE), c.POINTER(HANDLE),
                             c.POINTER(HANDLE), c.POINTER(HANDLE), c.POINTER(HANDLE)]
    get_security.restype = DWORD
    to_string = advapi.ConvertSecurityDescriptorToStringSecurityDescriptorW
    to_string.argtypes = [HANDLE, DWORD, DWORD, c.POINTER(HANDLE), c.POINTER(DWORD)]
    to_string.restype = BOOL
    open_thread = advapi.OpenThreadToken
    open_thread.argtypes = [HANDLE, DWORD, BOOL, c.POINTER(HANDLE)]
    open_thread.restype = BOOL
    duplicate = advapi.DuplicateToken
    duplicate.argtypes = [HANDLE, c.c_int, c.POINTER(HANDLE)]
    duplicate.restype = BOOL
    class Mapping(c.Structure):
        _fields_ = [('read', DWORD), ('write', DWORD), ('execute', DWORD), ('all', DWORD)]
    check = advapi.AccessCheck
    check.argtypes = [HANDLE, HANDLE, DWORD, c.POINTER(Mapping), HANDLE,
                      c.POINTER(DWORD), c.POINTER(DWORD), c.POINTER(BOOL)]
    check.restype = BOOL
    result.update(owners_started=False, permissions_changed=False,
                  saved_runtime_accessed=False, broker_actions=0, observations=[])
    with api.open_process(os.getpid()) as process:
        sid, logon = api.token_sids(process)
        creation = api.creation_time(process)
    token = HANDLE()
    # Query the effective thread token when present. Never impersonate it.
    if open_thread(HANDLE(-2), 0xA, True, c.byref(token)):
        result['token_source'] = 'thread'
    elif c.get_last_error() == 1008:
        api.checked(api.OpenProcessToken(HANDLE(-1), 0xA, c.byref(token)), 'OpenProcessToken')
        result['token_source'] = 'process'
    else:
        raise NativeCallError('OpenThreadToken', c.get_last_error())
    copied = HANDLE()
    with OwnedHandle(api, token.value) as original:
        result['phase'] = 'token_scalar_information'
        result['is_app_container'] = bool(DWORD.from_buffer(api._token_buffer(original, 29)).value)
        result['has_restrictions'], result['restriction_field_bytes'] = restriction_value(api._token_buffer(original, 21))
        result['restriction_decoding'] = 'Host byte or documented DWORD, little endian; other lengths refused.'
        user = api._token_buffer(original, 1)
        result['effective_user_matches_operator'] = api._sid_string(
            c.cast(user, c.POINTER(SID_AND_ATTRIBUTES)).contents.sid) == sid
        integrity = api._token_buffer(original, 25)
        result['integrity_rid'] = int(api._sid_string(
            c.cast(integrity, c.POINTER(SID_AND_ATTRIBUTES)).contents.sid).rsplit('-', 1)[1])
        for kind, label in ((2, 'groups'), (11, 'restricted_groups'), (30, 'capabilities')):
            result['phase'] = label
            buffer = api._token_buffer(original, kind)
            count = DWORD.from_buffer(buffer).value
            offset = TOKEN_GROUPS.groups.offset
            if count > 256 or (count and offset + count * c.sizeof(SID_AND_ATTRIBUTES) > len(buffer)):
                raise RuntimeError('TOKEN_GROUP_BOUNDS')
            groups = (SID_AND_ATTRIBUTES * count).from_buffer(buffer, offset) if count else []
            result[label] = {'count': count, 'matching_identities': [
                {'identity': 'operator' if api._sid_string(g.sid) == sid else 'logon', 'attributes': hex(g.attributes)}
                for g in groups if api._sid_string(g.sid) in (sid, logon)]}
        api.checked(duplicate(original.get(), 2, c.byref(copied)), 'DuplicateToken')
    with OwnedHandle(api, copied.value) as effective:
      result['phase'] = 'pipe_access'
      for access in (0, 1, 2, 0x80, 0x100000, 0x83, CLIENT_ACCESS):
        if time.monotonic() - started > 10:
            raise RuntimeError('DIAGNOSTIC_DEADLINE')
        route = PeerRegistration(ProcessIdentity(str(uuid4()), os.getpid(), creation, sid, 'supervisor'),
                                 logon, hashlib.sha256(b'pipe-rights-diagnostic').hexdigest(), 1, 'worker')
        item = {'requested_access': hex(access)}
        with api.server(route) as server:
            descriptor = HANDLE()
            # Read only the DACL. Never request the privileged audit information.
            code = get_security(server.get(), 6, 7, None, None, None, None, c.byref(descriptor))
            item['security_query_code'] = code
            if code == 0:
                text = HANDLE()
                try:
                    api.checked(to_string(descriptor, 1, 4, c.byref(text), None), 'ConvertSecurityDescriptor')
                    actual = c.wstring_at(text)
                    normalize = lambda value: re.sub(r'0x0+([1-9a-f])', r'0x\1', value)
                    item['dacl_matches_expected'] = normalize(actual) == normalize(pipe_security(sid, logon))
                    item['dacl_template'] = actual.replace(sid, 'OPERATOR').replace(logon, 'LOGON')
                    privileges = c.create_string_buffer(4096)
                    size, granted, allowed = DWORD(4096), DWORD(), BOOL()
                    mapping = Mapping(0x120089, 0x120116, 0x1200a0, 0x1f01ff)
                    api.checked(check(descriptor, effective.get(), access, c.byref(mapping), privileges,
                                      c.byref(size), c.byref(granted), c.byref(allowed)), 'AccessCheck')
                    item.update(access_check_allowed=bool(allowed.value), granted_access=hex(granted.value))
                finally:
                    if text.value:
                        api.LocalFree(text)
                    api.LocalFree(descriptor)
            try:
                with api.open_file(pipe_name(route), access, 0, flags=0x40100000):
                    item['open'] = 'PASSED'
            except NativeCallError as error:
                item.update(open='FAILED', operation=error.operation, winerror=error.winerror)
        result['observations'].append(item)
    result['elapsed_seconds'] = time.monotonic() - started
    return result


if __name__ == '__main__':
    destination = Path(sys.argv[1])
    if destination.exists():
        raise RuntimeError('PRESERVE_PRIOR_RESULT')
    result = {}
    try:
        observe(result)
        result['diagnostic_completed'] = True
    except Exception as error:
        result.update(diagnostic_completed=False, error_type=type(error).__name__, error=str(error))
    with destination.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2)
    print(json.dumps(result))
    sys.exit(0 if result['diagnostic_completed'] else 1)
