from compertum.runtime.identity import resolve_project
from compertum.runtime.owners import acquire_owner
from compertum.persistence import open_store
from compertum.coordinator import Coordinator

def test_expired_fixture_lease_requires_explicit_resume(tmp_path):
    with acquire_owner(resolve_project(tmp_path),'coordinator') as lease:
        store=open_store(lease,'coordinator');coordinator=Coordinator(store);coordinator.health=lambda:True
        coordinator.handle({'action':'resume'});task=coordinator.handle({'action':'fixture'});task['lease_until_monotonic']=0;coordinator.save(task)
        coordinator.tick();saved=store.get('task:'+task['task_id'])
        assert saved['state']=='INTERRUPTED' and saved['attempt_history'][-1]['reason']=='LEASE_GAP' and store.get('paused') is True
        assert not (tmp_path/'artifacts').exists();store.close()
