import threading,time
import pytest
from compertum.runtime.identity import resolve_project
from compertum.runtime.owners import acquire_owner
from compertum.persistence import open_store
from compertum.storage import StorageManager
from compertum.recovery import collect_recovery_set
from compertum.domain import ContractError

def test_native_barrier_prevents_concurrent_transition(tmp_path):
    p=resolve_project(tmp_path);leases=[acquire_owner(p,r) for r in ('coordinator','evaluation','execution')];stores=[open_store(l,l.role) for l in leases]
    entered=threading.Event();released=threading.Event();original=stores[0].checkpoint
    def checkpoint(*args):
        entered.set();time.sleep(.2);assert not released.is_set();return original(*args)
    stores[0].checkpoint=checkpoint
    def writer():
        entered.wait();stores[1].set('after',True);released.set()
    t=threading.Thread(target=writer);t.start()
    try:
        m=collect_recovery_set(p,stores,StorageManager(stores[0]));t.join(3)
        assert released.is_set() and len({s['barrier_id'] for s in m['databases']})==1
        with pytest.raises(ContractError,match='INCOMPLETE'):collect_recovery_set(p,stores[:2],StorageManager(stores[0]))
    finally:
        for s in stores:s.close()
        for l in leases:l.close()
