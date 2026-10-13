"""Durable control transitions remain idempotent across lost replies."""
from uuid import uuid4
import pytest
from compertum.runtime.identity import resolve_project
from compertum.runtime.owners import acquire_owner,release_owner
from compertum.runtime.ipc import ProtocolDecision
from compertum.runtime.errors import RuntimeRefused
from compertum.persistence import open_store

@pytest.fixture
def coordinator(tmp_path):
    from compertum.coordinator import Coordinator
    lease=acquire_owner(resolve_project(tmp_path),'coordinator')
    try: yield Coordinator(open_store(lease,'coordinator'))
    finally: release_owner(lease)

def decision(request=None,digest='a'*64,generation=1):
    return ProtocolDecision(request or str(uuid4()),'b'*64,digest,generation)

def test_pause_confirmation_and_duplicate_receipt_are_durable(coordinator):
    d=decision()
    first=coordinator.control(d,'pause_research',{})
    assert first['confirmed'] and first['reason']=='RESEARCH_PAUSED'
    assert coordinator.control(d,'pause_research',{})==first
    assert coordinator.status()['research_state']=='PAUSED'
    assert coordinator.store.conn.execute('SELECT count(*) FROM control_requests').fetchone()[0]==1

def test_same_request_with_changed_binding_cannot_mutate(coordinator):
    d=decision();coordinator.control(d,'pause_research',{})
    for other in (decision(d.request_id,'c'*64),decision(d.request_id,generation=2)):
        with pytest.raises(RuntimeRefused,match='REQUEST_CONFLICT'):
            coordinator.control(other,'resume_research',{})
    assert coordinator.status()['research_state']=='PAUSED'

def test_resume_needs_current_measured_health(coordinator):
    with pytest.raises(RuntimeRefused,match='HEALTH_UNVERIFIED'):
        coordinator.control(decision(),'resume_research',{})
    assert coordinator.status()['order_admission']=='DISARMED'
    assert coordinator.status()['broker_state']=='NOT_CONFIGURED'
    assert coordinator.status()['strategy_state']=='NOT_EVALUATED'

def test_arbitrary_control_payload_cannot_set_authority(coordinator):
    with pytest.raises(RuntimeRefused,match='CONTROL_PAYLOAD_DENIED'):
        coordinator.control(decision(),'pause_research',{'order_admission':'ARMED'})
    assert coordinator.store.conn.execute('SELECT count(*) FROM control_requests').fetchone()[0]==0
