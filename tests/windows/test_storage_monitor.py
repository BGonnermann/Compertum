from test_storage import api
from compertum.runtime.owners import acquire_owner,resolve_project
from compertum.persistence import open_store

def test_independent_growth_is_detected_without_deleting_evidence(tmp_path):
    m=api();owner=acquire_owner(resolve_project(tmp_path),'coordinator');store=open_store(owner,'coordinator')
    try:
        manager=m.StorageManager(store,free_floor=0,category_caps={'scratch':8192})
        (tmp_path/'.cache').mkdir();(tmp_path/'.cache/bypass.bin').write_bytes(b'x'*16384)
        status=manager.check_storage();assert not status['admitted'] and status['reason']=='STORAGE_LIMIT'
        assert (tmp_path/'.cache/bypass.bin').exists()
    finally:store.close();owner.close()
