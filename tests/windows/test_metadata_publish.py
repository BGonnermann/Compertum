import threading,time
import pytest
from compertum.runtime._windows import WindowsAPI,NativeCallError


def test_metadata_publish_survives_short_delete_sharing_conflict(tmp_path):
    api=WindowsAPI();path=tmp_path/'metadata.json';api.publish_metadata(path,b'old')
    reader=api.open_file(path,0x80000000,3)
    def release():time.sleep(.1);reader.close()
    thread=threading.Thread(target=release);thread.start()
    try:api.publish_metadata(path,b'new')
    finally:thread.join(timeout=2);reader.close()
    assert api.read_regular(path)==b'new'


def test_metadata_publish_refuses_persistent_conflict_and_preserves_bytes(tmp_path):
    api=WindowsAPI();path=tmp_path/'metadata.json';api.publish_metadata(path,b'old')
    with api.open_file(path,0x80000000,3):
        began=time.monotonic()
        with pytest.raises(NativeCallError):api.publish_metadata(path,b'new')
        assert time.monotonic()-began<1.5
    assert api.read_regular(path)==b'old'
    assert any(p.read_bytes()==b'new' for p in tmp_path.glob('metadata.json.incoming-*'))
