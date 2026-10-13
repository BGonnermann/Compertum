import importlib
from uuid import uuid4
import pytest
from test_persistence import owned
from compertum.runtime.errors import RuntimeRefused


def module(): return importlib.import_module('compertum.consumption')
def store(leases): return importlib.import_module('compertum.persistence').open_store(leases['evaluation'],'evaluation')
def inputs(): return {name:'a'*64 for name in ('input_sha256','protocol_sha256','shortlist_sha256')}


def test_consumption_is_sticky_and_same_transaction_can_only_continue(owned):
    project,leases=owned; db=store(leases); seal,evaluation=str(uuid4()),str(uuid4())
    receipt=module().consume_once(leases['evaluation'],seal,evaluation,inputs())
    assert receipt['status']=='CONSUMED'
    assert module().consume_once(leases['evaluation'],seal,evaluation,inputs()) == receipt
    with pytest.raises(RuntimeRefused,match='SEAL_ALREADY_CONSUMED'):
        module().consume_once(leases['evaluation'],seal,str(uuid4()),inputs())
    assert module().verify_consumption_guard(project)['status']=='VERIFIED'
    assert db.consumption()[0]['seal_id']==seal


def test_guard_append_or_mirror_failure_never_grants_consumption_receipt(owned,monkeypatch):
    project,leases=owned; db=store(leases); m=module()
    with monkeypatch.context() as patch:
        patch.setattr(m,'_flush_event',lambda *a: (_ for _ in ()).throw(OSError('fixture flush')))
        with pytest.raises(RuntimeRefused,match='CONSUMPTION_UNVERIFIED'):
            m.consume_once(leases['evaluation'],str(uuid4()),str(uuid4()),inputs())
    seal,evaluation=str(uuid4()),str(uuid4())
    with monkeypatch.context() as patch:
        patch.setattr(db,'mirror_consumption',lambda *a: (_ for _ in ()).throw(OSError('fixture db')))
        with pytest.raises(RuntimeRefused,match='CONSUMPTION_UNVERIFIED'):
            m.consume_once(leases['evaluation'],seal,evaluation,inputs())
    assert seal in module().verify_consumption_guard(project)['consumed']
    with pytest.raises(RuntimeRefused,match='SEAL_ALREADY_CONSUMED'):
        m.consume_once(leases['evaluation'],seal,str(uuid4()),inputs())


def test_missing_guard_is_not_reprovisioned_from_existing_database(owned):
    project,leases=owned; db=store(leases)
    directory=project.root_path/'state/evaluation-consumption'
    head=directory/'head.json'; head.rename(directory/'preserved-head.json')
    assert module().verify_consumption_guard(project)['status']=='EVALUATION_COMPROMISED'
    db.close()
    with pytest.raises(RuntimeRefused,match='EVALUATION_COMPROMISED'): store(leases)
    assert not head.exists()
