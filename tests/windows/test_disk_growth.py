import json,subprocess,sys,time
import pytest
from compertum.runtime.identity import resolve_project
from compertum.runtime.owners import acquire_owner
from compertum.persistence import open_store
from compertum.storage import StorageManager

def test_separate_writer_and_monitor_process_refuse_admission(tmp_path):
    root=str(tmp_path)
    watcher='''
import sys,time
from pathlib import Path
from compertum.runtime.identity import resolve_project
from compertum.runtime.owners import acquire_owner
from compertum.watchdog import StorageWatchdog
from compertum.storage import sample_storage
p=resolve_project(Path(sys.argv[1]));l=acquire_owner(p,'watchdog')
wd=StorageWatchdog(l,p.root_path/'state/watchdog/heartbeat.json',lambda:{'admitted':sample_storage(p.root_path)['used']['scratch']<=8192})
try:
 while not (p.root_path/'done').exists():time.sleep(.05)
finally:wd.close();l.close()
'''
    with acquire_owner(resolve_project(tmp_path),'coordinator') as lease:
        store=open_store(lease,'coordinator');manager=StorageManager(store,category_caps={'scratch':8192});grant=manager.reserve_bytes('bounded','scratch',4096);writer=manager.open_artifact(grant,'.cache/bounded.bin')
        monitor=subprocess.Popen([sys.executable,'-B','-c',watcher,root],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        try:
            heartbeat=tmp_path/'state/watchdog/heartbeat.json';until=time.monotonic()+5
            while time.monotonic()<until:
                if heartbeat.exists() and json.loads(heartbeat.read_text())['storage_healthy']:break
                time.sleep(.05)
            assert heartbeat.exists() and json.loads(heartbeat.read_text())['storage_healthy']
            grow="from pathlib import Path;import sys;p=Path(sys.argv[1])/'.cache/bypass.bin';p.write_bytes(b'x'*16384)"
            start=time.monotonic();child=subprocess.run([sys.executable,'-B','-c',grow,root],capture_output=True,timeout=3);assert child.returncode==0
            while time.monotonic()-start<5:
                if not json.loads(heartbeat.read_text())['storage_healthy']:break
                time.sleep(.05)
            assert time.monotonic()-start<5 and not json.loads(heartbeat.read_text())['storage_healthy']
            with pytest.raises(ValueError,match='WRITE_CAPACITY'):writer.write(b'z')
            assert writer.staging.stat().st_size==0
        finally:
            writer.close();(tmp_path/'done').write_text('stop');out,err=monitor.communicate(timeout=12);assert monitor.returncode==0,err.decode();store.close()
