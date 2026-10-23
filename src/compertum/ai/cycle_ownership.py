"""Keep a saved cycle's dispatch claim exclusive across owner restarts."""
from contextlib import contextmanager
from compertum.runtime.errors import RuntimeRefused


def require_control_clear(store, cycle_id):
    if cycle_id is not None and store.get_state('research_cycle_control_pending:'+cycle_id) is not None:
        raise RuntimeRefused('CYCLE_CONTROL_PENDING')


def require_dispatch_owner(controller):
    claim = controller.storage.store.get_state('active_research_cycle')
    require_control_clear(controller.storage.store, claim)
    if claim is None:
        return
    cycle = getattr(controller.coordinator, '_research_cycle', None)
    if (cycle is None or cycle.cycle_id != claim or not cycle._dispatch_depth
            or controller not in (cycle.research, cycle.auditor, cycle.reviews)):
        raise RuntimeRefused('CYCLE_DISPATCH_OWNED')


@contextmanager
def dispatch_scope(cycle):
    require_control_clear(cycle.store, cycle.cycle_id)
    if (getattr(cycle.coordinator, '_research_cycle', None) is not cycle
            or cycle.store.get_state('active_research_cycle') != cycle.cycle_id):
        raise RuntimeRefused('CYCLE_DISPATCH_OWNED')
    cycle._dispatch_depth += 1
    try:
        yield
    finally:
        cycle._dispatch_depth -= 1
