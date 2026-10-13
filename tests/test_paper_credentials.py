"""Actual Windows DPAPI and leases; every key below is an invented marker."""
from dataclasses import replace,FrozenInstanceError
import ctypes as c
import os
import pickle
import subprocess
import sys
import pytest
from compertum.runtime.errors import RuntimeRefused
from compertum.runtime.identity import resolve_project
from compertum.runtime.owners import acquire_owner,release_owner,_LEASES
from compertum.runtime.paper_credentials import ProtectedPaperCredentials,seal_paper_credentials,open_paper_credentials,DATA_BLOB

pytestmark=pytest.mark.skipif(os.name!='nt',reason='NATIVE_WINDOWS_UNAVAILABLE')
KEY=bytearray(b'DUMMY_PAPER_KEY_123456')
SECRET=bytearray(b'DUMMY_PAPER_SECRET_123456')

@pytest.fixture
def owner(tmp_path):
    project=resolve_project(tmp_path);lease=acquire_owner(project,'execution')
    try:yield project,lease
    finally:
        if lease in _LEASES:release_owner(lease)


def sealed(lease):return seal_paper_credentials(lease,'fixture',bytearray(KEY),bytearray(SECRET))


def test_native_roundtrip_is_owner_bound_and_leaves_no_secret_file(owner):
    project,lease=owner;before={p.relative_to(project.root_path).as_posix():(p.stat().st_size if p.suffix=='.lock' else p.read_bytes()) for p in project.root_path.rglob('*') if p.is_file()}
    protected=sealed(lease)
    assert bytes(KEY) not in protected.ciphertext and bytes(SECRET) not in protected.ciphertext
    with open_paper_credentials(lease,protected) as opened:
        assert opened.headers()=={'APCA-API-KEY-ID':KEY.decode(),'APCA-API-SECRET-KEY':SECRET.decode()}
        buffer=opened._buffer
        assert bytes(KEY) in buffer and bytes(SECRET) in buffer
        assert KEY.decode() not in repr(opened) and SECRET.decode() not in repr(opened)
    assert not any(buffer)
    with pytest.raises(RuntimeRefused):opened.headers()
    assert before=={p.relative_to(project.root_path).as_posix():(p.stat().st_size if p.suffix=='.lock' else p.read_bytes()) for p in project.root_path.rglob('*') if p.is_file()}


def test_windows_data_blob_layout():
    assert DATA_BLOB.pbData.offset==(8 if c.sizeof(c.c_void_p)==8 else 4)
    assert c.sizeof(DATA_BLOB)==(16 if c.sizeof(c.c_void_p)==8 else 8)


@pytest.mark.parametrize('change',[{'account_alias':'other'},{'project_id':'f'*64}])
def test_changed_protected_context_is_denied(owner,change):
    _,lease=owner;p=replace(sealed(lease),**change)
    with pytest.raises(RuntimeRefused):
        with open_paper_credentials(lease,p):pass


@pytest.mark.parametrize('corruption',['flip','truncate','zero'])
def test_corrupted_ciphertext_cannot_expose_plaintext(owner,corruption):
    _,lease=owner;p=sealed(lease);raw=bytearray(p.ciphertext)
    if corruption=='flip':raw[len(raw)//2]^=255
    elif corruption=='truncate':raw=raw[:20]
    else:raw=bytearray(len(raw))
    with pytest.raises(RuntimeRefused):
        with open_paper_credentials(lease,replace(p,ciphertext=bytes(raw))):pass


def test_release_revokes_and_wipes_an_open_buffer(owner):
    _,lease=owner
    with open_paper_credentials(lease,sealed(lease)) as opened:
        buffer=opened._buffer;release_owner(lease)
        assert not any(buffer)
        with pytest.raises(RuntimeRefused):opened.headers()
        opened.close();opened.close()


def test_exception_exit_wipes_buffer(owner):
    _,lease=owner
    with pytest.raises(ValueError):
        with open_paper_credentials(lease,sealed(lease)) as opened:
            buffer=opened._buffer;raise ValueError('fixture failure')
    assert not any(buffer)


def test_new_execution_generation_can_open_after_actual_process_exit(tmp_path):
    code = """
from pathlib import Path
import sys
from compertum.runtime.identity import resolve_project
from compertum.runtime.owners import acquire_owner,release_owner
from compertum.runtime.paper_credentials import seal_paper_credentials
lease=acquire_owner(resolve_project(Path(sys.argv[1])),'execution')
try:
    protected=seal_paper_credentials(lease,'fixture',bytearray(b'DUMMY_PAPER_KEY_123456'),bytearray(b'DUMMY_PAPER_SECRET_123456'))
    print(protected.ciphertext.hex())
finally:release_owner(lease)
"""
    from test_fixture_processes import fixture_module
    child=fixture_module().python_process(['-B','-c',code,str(tmp_path)],env={k:v for k,v in os.environ.items() if k.upper() in {'SYSTEMROOT','WINDIR','PYTHONPATH','PYTHONDONTWRITEBYTECODE','PYTHONNOUSERSITE'}},stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    out,err=child.communicate(timeout=20)
    assert child.returncode==0,err
    project=resolve_project(tmp_path);new=acquire_owner(project,'execution')
    try:
        protected=ProtectedPaperCredentials(project.project_id,'fixture',bytes.fromhex(out.strip()))
        assert new.generation==2
        with open_paper_credentials(new,protected) as opened:assert opened.headers()['APCA-API-KEY-ID']==KEY.decode()
    finally:release_owner(new)


def test_wrong_role_is_denied_before_cryptography(tmp_path,monkeypatch):
    import compertum.runtime.paper_credentials as module
    lease=acquire_owner(resolve_project(tmp_path),'coordinator')
    def forbidden(*a,**k):raise AssertionError('crypto called for wrong role')
    monkeypatch.setattr(module,'_crypt',forbidden)
    try:
        with pytest.raises(RuntimeRefused):sealed(lease)
    finally:release_owner(lease)


@pytest.mark.parametrize('value',[b'IMMUTABLE',bytearray(),bytearray(b'x'*257),bytearray(b'has\nnewline'),bytearray(b'short'),bytearray(b'nonascii\xff')],ids=['immutable','empty','oversize','newline','short','nonascii'])
def test_bad_key_format_is_refused_without_value_in_error(owner,value):
    _,lease=owner
    with pytest.raises(RuntimeRefused) as caught:seal_paper_credentials(lease,'fixture',value,bytearray(SECRET))
    assert str(caught.value)=='CREDENTIAL_INPUT_INVALID'


def test_repr_pickle_and_immutability_do_not_publish_material(owner):
    _,lease=owner;p=sealed(lease)
    assert KEY.decode() not in repr(p) and SECRET.decode() not in repr(p)
    with pytest.raises((FrozenInstanceError,AttributeError)):p.ciphertext=b'changed'
    with pytest.raises(RuntimeRefused):pickle.dumps(p)
    with open_paper_credentials(lease,p) as opened:
        with pytest.raises(RuntimeRefused):pickle.dumps(opened)


def test_successful_native_call_with_bad_envelope_is_still_rejected_and_wiped(owner,monkeypatch):
    import compertum.runtime.paper_credentials as module
    _,lease=owner;p=sealed(lease);invalid=bytearray(b'invalid-envelope-with-synthetic-data')
    monkeypatch.setattr(module,'_crypt',lambda *a,**k:invalid)
    with pytest.raises(RuntimeRefused):
        with open_paper_credentials(lease,p):pass
    assert not any(invalid)


@pytest.mark.parametrize('succeeds',[True,False])
def test_native_output_is_zero_before_free_even_when_crypto_fails(monkeypatch,succeeds):
    import compertum.runtime.paper_credentials as module
    native=(c.c_ubyte*32)(*([90]*32));freed=[]
    def operation(source,description,entropy,reserved,prompt,flags,output):
        assert description is reserved is prompt is None and flags==1
        blob=c.cast(output,c.POINTER(DATA_BLOB)).contents
        blob.cbData=32;blob.pbData=c.cast(native,c.POINTER(c.c_ubyte))
        return int(succeeds)
    def free(pointer):
        assert pointer.value==c.addressof(native)
        assert bytes(native)==b'\0'*32
        freed.append(True)
        return None
    monkeypatch.setattr(module,'_native_api',lambda:(operation,operation,free))
    if succeeds:assert module._crypt(bytearray(b'synthetic'),b'context',decrypt=True)==bytearray(b'Z'*32)
    else:
        with pytest.raises(RuntimeRefused,match='^CREDENTIAL_CRYPTO_FAILED$'):
            module._crypt(bytearray(b'synthetic'),b'context',decrypt=True)
    assert freed==[True]


def test_failed_native_free_prevents_returning_plaintext(monkeypatch):
    import compertum.runtime.paper_credentials as module
    native=(c.c_ubyte*32)(*([90]*32));buffers=[]
    original_wipe=module._wipe
    def wipe(buffer):
        original_wipe(buffer);buffers.append(buffer)
    def operation(*args):
        blob=c.cast(args[-1],c.POINTER(DATA_BLOB)).contents
        blob.cbData=32;blob.pbData=c.cast(native,c.POINTER(c.c_ubyte));return 1
    monkeypatch.setattr(module,'_native_api',lambda:(operation,operation,lambda pointer:123))
    monkeypatch.setattr(module,'_wipe',wipe)
    with pytest.raises(RuntimeRefused,match='^CREDENTIAL_CLEANUP_UNVERIFIED$'):
        module._crypt(bytearray(b'synthetic'),b'context',decrypt=True)
    assert bytes(native)==b'\0'*32 and buffers and all(not any(b) for b in buffers)


@pytest.mark.parametrize('change',[{'project_id':'not-a-project'},{'account_alias':'bad\nalias'},{'ciphertext':bytearray(b'cipher')},{'ciphertext':b''},{'ciphertext':b'x'*8193}])
def test_malformed_protected_record_is_refused(owner,change):
    _,lease=owner
    with pytest.raises(RuntimeRefused,match='^CREDENTIAL_INPUT_INVALID$'):replace(sealed(lease),**change)


@pytest.mark.parametrize('length',[8,256])
def test_native_field_boundaries_preserve_caller_owned_inputs(owner,length):
    _,lease=owner;key=bytearray(b'K'*length);secret=bytearray(b'S'*length)
    protected=seal_paper_credentials(lease,'fixture',key,secret)
    with open_paper_credentials(lease,protected) as opened:
        assert opened.headers()=={'APCA-API-KEY-ID':'K'*length,'APCA-API-SECRET-KEY':'S'*length}
    assert key==bytearray(b'K'*length) and secret==bytearray(b'S'*length)


def test_successful_native_call_with_valid_shape_corruption_is_denied(owner,monkeypatch):
    import compertum.runtime.paper_credentials as module
    _,lease=owner;p=sealed(lease);native_crypt=module._crypt;buffers=[]
    def corrupted(*args,**kwargs):
        result=native_crypt(*args,**kwargs)
        result[-1]=ord('X') if result[-1]!=ord('X') else ord('Y')
        buffers.append(result)
        return result
    monkeypatch.setattr(module,'_crypt',corrupted)
    with pytest.raises(RuntimeRefused,match='^CREDENTIAL_ENVELOPE_INVALID$'):
        with open_paper_credentials(lease,p):pass
    assert buffers and all(not any(b) for b in buffers)
