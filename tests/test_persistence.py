import importlib
import pytest
from compertum.runtime.owners import acquire_owner,resolve_project

def api():
    try:return importlib.import_module('compertum.persistence')
    except ImportError:pytest.fail('owned persistence missing')

def test_wrong_owner_and_duplicate_events(tmp_path):
    m=api();owner=acquire_owner(resolve_project(tmp_path),'coordinator')
    try:
        with pytest.raises(ValueError):m.open_store(owner,'execution')
        store=m.open_store(owner,'coordinator')
        event={'event_id':'one','kind':'TASK_STATUS','payload':{'value':1}}
        first=store.commit_event(event);second=store.commit_event(event)
        assert first==second and store.event_count()==1
        changed={**event,'payload':{'value':2}}
        with pytest.raises(ValueError):store.commit_event(changed)
        store.close()
    finally:owner.close()

def test_checkpoint_contains_pending_outbox(tmp_path):
    m=api();owner=acquire_owner(resolve_project(tmp_path),'coordinator')
    try:
        store=m.open_store(owner,'coordinator')
        store.commit_event({'event_id':'pending','kind':'TASK_STATUS','payload':{}})
        cp=store.checkpoint('barrier',tmp_path/'copy.sqlite')
        assert [x['event_id'] for x in cp['pending_messages']]==['pending']
        assert len(cp['sha256'])==64
        store.close()
    finally:owner.close()

def test_lost_control_ack_uses_durable_receipt(tmp_path):
    m=api();owner=acquire_owner(resolve_project(tmp_path),'coordinator')
    try:
        store=m.open_store(owner,'coordinator')
        def change():
            store.set('count',store.get('count',0)+1);return {'count':store.get('count')}
        a=store.request_once('request','subject',owner.generation,{'action':'pause'},change)
        b=store.request_once('request','subject',owner.generation,{'action':'pause'},change)
        assert a==b=={'count':1} and store.get('count')==1
        with pytest.raises(ValueError):store.request_once('request','subject',owner.generation,{'action':'resume'},change)
        store.close()
    finally:owner.close()
