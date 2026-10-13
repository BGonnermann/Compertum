import subprocess,sys,json
import pytest
from compertum.runtime.identity import resolve_project
from compertum.runtime.owners import acquire_owner,verify_prior_exit,OwnerError
from compertum.runtime import win32 as w
from compertum.persistence import open_store
from compertum.storage import StorageManager
from compertum.recovery import collect_recovery_set

def test_backup_exhaustion_before_native_snapshot(tmp_path):
    p=resolve_project(tmp_path);leases=[acquire_owner(p,r) for r in ('coordinator','evaluation','execution')];stores=[open_store(l,l.role) for l in leases]
    calls=[];original=stores[0].checkpoint
    def observed(*args):calls.append(True);return original(*args)
    stores[0].checkpoint=observed
    try:
        with pytest.raises(ValueError,match='STORAGE_LIMIT'):collect_recovery_set(p,stores,StorageManager(stores[0],category_caps={'backups':8192}))
        assert not calls and not list((tmp_path/'backups').glob('*/manifest.json'))
        stores[1].set('barrier_released',True);assert stores[1].get('barrier_released') is True
    finally:
        for s in stores:s.close()
        for l in leases:l.close()

def test_real_identity_with_injected_pid_reuse_and_access_denial(monkeypatch):
    import os
    actual=w.identity(os.getpid());old={**actual,'creation_time':actual['creation_time']-1}
    assert verify_prior_exit(old)['kind']=='PID_REUSED'
    with pytest.raises(OwnerError,match='LIVE'):verify_prior_exit(actual)
    def denied(pid):raise OSError(5,'INJECTED_ACCESS_DENIED')
    monkeypatch.setattr(w,'identity',denied)
    with pytest.raises(OwnerError,match='UNVERIFIED'):verify_prior_exit(actual)

def test_abrupt_writer_retains_reserved_bytes_on_owner_restart(tmp_path):
    script='''
import os,sys
from pathlib import Path
from compertum.runtime.identity import resolve_project
from compertum.runtime.owners import acquire_owner
from compertum.persistence import open_store
from compertum.storage import StorageManager
l=acquire_owner(resolve_project(Path(sys.argv[1])),'coordinator');s=open_store(l,'coordinator');m=StorageManager(s)
g=m.reserve_bytes('interrupted','scratch',8192);w=m.open_artifact(g,'.cache/interrupted.bin');w.write(b'ab');os._exit(17)
'''
    run=subprocess.run([sys.executable,'-B','-c',script,str(tmp_path)],capture_output=True,timeout=10);assert run.returncode==17
    with acquire_owner(resolve_project(tmp_path),'coordinator') as lease:
        store=open_store(lease,'coordinator');m=StorageManager(store);grants=m.reservations()
        assert grants[0]['state']=='OPEN' and grants[0]['written']==2
        assert (tmp_path/grants[0]['path']).read_bytes()==b'ab'
        assert m.check_storage()['observation']['used']['scratch']>=2
        assert m.check_storage()['pending']['scratch']==4096;store.close()
