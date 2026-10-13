from test_persistence import api
from compertum.runtime.owners import acquire_owner,resolve_project
import pytest

def test_lost_ack_delivers_once_and_broker_message_never_replays(tmp_path):
    m=api();owner=acquire_owner(resolve_project(tmp_path),'coordinator')
    try:
        store=m.open_store(owner,'coordinator')
        event={'event_id':'delivery','kind':'TASK_STATUS','payload':{'value':1}}
        store.accept_message(event);store.accept_message(event)
        assert store.accepted_count()==1
        assert store.get('accepted_transitions')==1 and store.get('last_safe_message')==event
        with pytest.raises(ValueError):store.accept_message({'event_id':'broker','kind':'BROKER_SIDE_EFFECT','payload':{'synthetic':True}})
        store.close()
    finally:owner.close()
