import threading
from compertum.runtime.identity import resolve_project
from compertum.runtime.owners import acquire_owner
from compertum.persistence import open_store
from compertum.coordinator import Coordinator

def test_owner_connection_reads_and_transactions_are_serialized(tmp_path):
    with acquire_owner(resolve_project(tmp_path),'coordinator') as lease:
        store=open_store(lease,'coordinator');coordinator=Coordinator(store);errors=[]
        def writer():
            try:
                for i in range(150):
                    with store.transaction():store.set('shared',i);store.set('task:fixture',{'task_id':'fixture','state':'PAUSED'})
            except Exception as e:errors.append(type(e).__name__)
        def reader():
            try:
                for i in range(400):store.get('shared');coordinator.tasks();store.event_count();store.accepted_count()
            except Exception as e:errors.append(type(e).__name__)
        threads=[threading.Thread(target=writer),threading.Thread(target=reader)]
        for t in threads:t.start()
        for t in threads:t.join(15);assert not t.is_alive()
        assert not errors and store.get('shared')==149;store.close()
