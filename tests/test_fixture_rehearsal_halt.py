"""Actual component close with real stores and explicitly simulated reserve/health."""
from uuid import uuid4
from compertum.data.encoding import canonical
from compertum.fake_attempt_guard import require_attempt_guard
from helpers.fixture_rehearsal_owner import RehearsalOwner
from test_fixture_order_private_factory import owner,original_owner
from test_paper_read_owner import pair

def test_halt_closes_native_component_and_prevents_dispatch(owner):
 hook=object.__new__(RehearsalOwner);hook.owner=owner.a;hook.component=owner.fixture_orders
 hook.producer=None;hook.parent=None;state={'status':'NEW'}
 before=canonical(require_attempt_guard(owner.a.store))
 hook._advance(dict(operation='halt',intent_id=str(uuid4()),activity_id=str(uuid4())),'a'*64,state)
 assert state['status']=='DONE' and state['native_component_closed'] and state['dispatch_refused']
 assert state['reinstall_refused'] and state['guard_unchanged']
 assert hook.component.closed and hook.component.active is None
 assert canonical(require_attempt_guard(owner.a.store))==before
