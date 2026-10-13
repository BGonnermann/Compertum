"""Current-user DPAPI envelopes with execution-owner-scoped plaintext lifetime.

No persistence, credential discovery, network access or broker authority. Python
header strings are temporary copies; only owned mutable/native buffers are wiped.
"""
from contextlib import contextmanager
from dataclasses import dataclass
import ctypes as c
import hashlib
import os
import re

from .errors import RuntimeRefused
from .owners import _MUTEX, _owner_scope, require_live_owner

_MAGIC = b'CPAPER01'
_MAX_BLOB = 8192
_HEADER_BYTES = 76
_ORIGIN = b'https://paper-api.alpaca.markets'


class DATA_BLOB(c.Structure):
    _fields_ = [('cbData', c.c_uint32), ('pbData', c.POINTER(c.c_ubyte))]


def _wipe(buffer):
    if buffer:
        c.memset((c.c_ubyte * len(buffer)).from_buffer(buffer), 0, len(buffer))


def _native_api():
    if os.name != 'nt':
        raise RuntimeRefused('NATIVE_WINDOWS_UNAVAILABLE')
    crypt = c.WinDLL('crypt32', use_last_error=True)
    kernel = c.WinDLL('kernel32', use_last_error=True)
    protect = crypt.CryptProtectData
    protect.argtypes = [c.POINTER(DATA_BLOB), c.c_wchar_p, c.POINTER(DATA_BLOB), c.c_void_p, c.c_void_p, c.c_uint32, c.POINTER(DATA_BLOB)]
    protect.restype = c.c_int32
    unprotect = crypt.CryptUnprotectData
    unprotect.argtypes = [c.POINTER(DATA_BLOB), c.c_void_p, c.POINTER(DATA_BLOB), c.c_void_p, c.c_void_p, c.c_uint32, c.POINTER(DATA_BLOB)]
    unprotect.restype = c.c_int32
    free = kernel.LocalFree
    free.argtypes = [c.c_void_p]
    free.restype = c.c_void_p
    return protect, unprotect, free


def _crypt(buffer, entropy, *, decrypt):
    return _crypt_bounded(buffer,entropy,decrypt=decrypt,input_max=_MAX_BLOB,output_max=_MAX_BLOB,error_prefix='CREDENTIAL')


def _crypt_bounded(buffer, entropy, *, decrypt, input_max, output_max, error_prefix):
    """Copy bounded native output, wipe it before freeing, and never quote errors."""
    if type(buffer) is not bytearray or not 1 <= len(buffer) <= input_max:
        raise RuntimeRefused(error_prefix+'_INPUT_INVALID')
    protect, unprotect, free = _native_api()
    input_array = (c.c_ubyte * len(buffer)).from_buffer(buffer)
    entropy_array = (c.c_ubyte * len(entropy)).from_buffer_copy(entropy)
    source = DATA_BLOB(len(buffer), input_array)
    context = DATA_BLOB(len(entropy), entropy_array)
    output = DATA_BLOB()
    result = bytearray()
    try:
        operation = unprotect if decrypt else protect
        if not operation(c.byref(source), None, c.byref(context), None, None, 1, c.byref(output)):
            raise RuntimeRefused(error_prefix+'_CRYPTO_FAILED')
        if not output.pbData or not 1 <= output.cbData <= output_max:
            raise RuntimeRefused(error_prefix+'_CRYPTO_FAILED')
        result = bytearray(output.cbData)
        c.memmove((c.c_ubyte * len(result)).from_buffer(result), output.pbData, len(result))
    except BaseException:
        _wipe(result)
        raise
    finally:
        if output.pbData:
            c.memset(output.pbData, 0, output.cbData)
            if free(c.cast(output.pbData, c.c_void_p)):
                _wipe(result)
                raise RuntimeRefused(error_prefix+'_CLEANUP_UNVERIFIED')
    return result


def _alias(value):
    if type(value) is not str or re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}', value) is None:
        raise RuntimeRefused('CREDENTIAL_INPUT_INVALID')


def _field(value):
    if type(value) is not bytearray or not 8 <= len(value) <= 256 or re.fullmatch(rb'[A-Za-z0-9_-]+', value) is None:
        raise RuntimeRefused('CREDENTIAL_INPUT_INVALID')


def _context(project_id, account_alias):
    return _MAGIC + b'\0' + project_id.encode('ascii') + b'\0' + _ORIGIN + b'\0' + account_alias.encode('ascii')


@dataclass(frozen=True, repr=False)
class ProtectedPaperCredentials:
    project_id: str
    account_alias: str
    ciphertext: bytes

    def __post_init__(self):
        if type(self.project_id) is not str or re.fullmatch(r'[0-9a-f]{64}', self.project_id) is None:
            raise RuntimeRefused('CREDENTIAL_INPUT_INVALID')
        _alias(self.account_alias)
        if type(self.ciphertext) is not bytes or not 1 <= len(self.ciphertext) <= _MAX_BLOB:
            raise RuntimeRefused('CREDENTIAL_INPUT_INVALID')

    def __repr__(self):
        return '<ProtectedPaperCredentials redacted>'

    def __reduce_ex__(self, protocol):
        raise RuntimeRefused('CREDENTIAL_SERIALIZATION_FORBIDDEN')


class _OpenedCredentials:
    __slots__ = ('_lease', '_buffer', '_key_end', '_closed')

    def __init__(self, lease, buffer, key_end):
        self._lease = lease
        self._buffer = buffer
        self._key_end = key_end
        self._closed = False

    def __repr__(self):
        return '<OpenedPaperCredentials redacted>'

    def __reduce_ex__(self, protocol):
        raise RuntimeRefused('CREDENTIAL_SERIALIZATION_FORBIDDEN')

    def headers(self):
        with _owner_scope(self._lease):
            require_live_owner(self._lease, 'execution')
            if self._closed:
                raise RuntimeRefused('CREDENTIAL_CLOSED')
            view = memoryview(self._buffer)
            return {'APCA-API-KEY-ID': str(view[_HEADER_BYTES:self._key_end], 'ascii'),
                    'APCA-API-SECRET-KEY': str(view[self._key_end:], 'ascii')}

    def close(self):
        # Owner disposal revokes the lease before calling this method.
        with _MUTEX:
            self._closed = True
            _wipe(self._buffer)


def seal_paper_credentials(lease, account_alias, key, secret):
    with _owner_scope(lease) as state:
        require_live_owner(lease, 'execution')
        _alias(account_alias)
        _field(key)
        _field(secret)
        entropy = _context(state.project.project_id, account_alias)
        plain = bytearray(_MAGIC + hashlib.sha256(entropy).digest() + bytes(32) + len(key).to_bytes(2, 'big') + len(secret).to_bytes(2, 'big'))
        encrypted = bytearray()
        try:
            plain.extend(key)
            plain.extend(secret)
            integrity = hashlib.sha256(entropy)
            integrity.update(memoryview(plain)[72:])
            plain[40:72] = integrity.digest()
            encrypted = _crypt(plain, entropy, decrypt=False)
            return ProtectedPaperCredentials(state.project.project_id, account_alias, bytes(encrypted))
        finally:
            _wipe(plain)
            _wipe(encrypted)


@contextmanager
def open_paper_credentials(lease, protected):
    opened = None
    state = None
    plain = bytearray()
    try:
        with _owner_scope(lease) as state:
            require_live_owner(lease, 'execution')
            if type(protected) is not ProtectedPaperCredentials:
                raise RuntimeRefused('CREDENTIAL_INPUT_INVALID')
            protected.__post_init__()
            if protected.project_id != state.project.project_id:
                raise RuntimeRefused('CREDENTIAL_CONTEXT_MISMATCH')
            entropy = _context(protected.project_id, protected.account_alias)
            plain = _crypt(bytearray(protected.ciphertext), entropy, decrypt=True)
            if (not 92 <= len(plain) <= 588 or plain[:8] != _MAGIC
                    or plain[8:40] != hashlib.sha256(entropy).digest()):
                raise RuntimeRefused('CREDENTIAL_ENVELOPE_INVALID')
            integrity = hashlib.sha256(entropy)
            integrity.update(memoryview(plain)[72:])
            if plain[40:72] != integrity.digest():
                raise RuntimeRefused('CREDENTIAL_ENVELOPE_INVALID')
            key_length = int.from_bytes(plain[72:74], 'big')
            secret_length = int.from_bytes(plain[74:76], 'big')
            if (not 8 <= key_length <= 256 or not 8 <= secret_length <= 256
                    or len(plain) != _HEADER_BYTES + key_length + secret_length
                    or re.fullmatch(rb'[A-Za-z0-9_-]+', memoryview(plain)[_HEADER_BYTES:]) is None):
                raise RuntimeRefused('CREDENTIAL_ENVELOPE_INVALID')
            opened = _OpenedCredentials(lease, plain, _HEADER_BYTES + key_length)
            state.resources.append(opened)
        yield opened
    finally:
        with _MUTEX:
            if opened is not None:
                opened.close()
                if state is not None and opened in state.resources:
                    state.resources.remove(opened)
            else:
                _wipe(plain)
