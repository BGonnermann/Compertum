"""Independent restrictive health/storage observer. No broker or AI calls."""
import time,threading
from .domain import atomic_json,now
from .storage import sample_storage,CAPS

def check_storage(observation,reservations=()):
    return not observation['unexpected_reparse'] and observation['free_bytes']>=50*1024**3 and all(observation['used'][k]<=CAPS[k] for k in CAPS)

class StorageWatchdog:
    def __init__(self,lease,heartbeat_path,manager_check=None):
        lease.verify();self.lease=lease;self.heartbeat_path=heartbeat_path;self.check=manager_check;self.stop=threading.Event();self.last=None;self.error=None
        self.last_scan=None;self.state_lock=threading.RLock()
        self.scanner=threading.Thread(target=self._scan,daemon=True);self.scanner.start()
        self.thread=threading.Thread(target=self._loop,daemon=True);self.thread.start()
    def _scan(self):
        while not self.stop.is_set():
            start=time.monotonic()
            try:
                status=self.check() if self.check else {'admitted':check_storage(sample_storage(self.lease.project.root_path))}
                elapsed=time.monotonic()-start
                with self.state_lock:
                    self.last=status if elapsed<=5 else {'admitted':False,'reason':'STORAGE_SCAN_DEADLINE'}
                    self.last_scan=time.monotonic()
                    if not self.last['admitted']:self.publish()
            except Exception as exc:
                with self.state_lock:
                    self.error=type(exc).__name__;self.last={'admitted':False,'reason':'STORAGE_MONITOR_UNVERIFIED'};self.publish()
            self.stop.wait(max(0,4-(time.monotonic()-start)))
    def publish(self):
        import shutil
        with self.state_lock:
            self.lease.verify();root=self.lease.project.root_path;current=time.monotonic();free=shutil.disk_usage(root).free
            age=current-self.last_scan if self.last_scan is not None else float('inf')
            unhealthy=free<50*1024**3 or self.last is None or not self.last['admitted'] or age>5
            if unhealthy:atomic_json(root/'state/watchdog/halt.json',{'at':now(),'reason':'STORAGE_UNHEALTHY'})
            atomic_json(self.heartbeat_path,{'at':now(),'monotonic':current,'free_bytes':free,'storage_healthy':not unhealthy,'generation':self.lease.generation})
    def _loop(self):
        root=self.lease.project.root_path
        while not self.stop.is_set():
            try:
                self.publish()
            except Exception as exc:
                self.error=type(exc).__name__;atomic_json(root/'state/watchdog/halt.json',{'at':now(),'reason':'STORAGE_MONITOR_UNVERIFIED'})
            self.stop.wait(1)
    def close(self):self.stop.set();self.thread.join(10);self.scanner.join(10)
