"""Coherently rewritten receipt mirrors cannot invent confirmed effects."""
import hashlib,json
import pytest
from test_execution_health import pair
from test_execution_authority import authority,packet
from test_saved_plan_controls import ready
from test_operation_progression import started,step,submissions
from compertum.events import canonical
from compertum.runtime.errors import RuntimeRefused


@pytest.mark.parametrize('change',['complete','missing_status','invented_fill'])
def test_rehashed_result_mirrors_cannot_invent_confirmation(ready,change):
    a=ready[0];saved=started(a);p=packet('advance_plan',plan_id=saved['plan_id'],plan_sha256=saved['plan_sha256']);first=a.handle(p)
    value=dict(first)
    if change=='complete':value['status']='COMPLETE'
    elif change=='missing_status':value.pop('status')
    else:value.update(status='STEP_TERMINAL',intent_status='FILLED',filled_quantity=19)
    raw=canonical(value).decode()
    with a.store.conn:
        a.store.conn.execute('UPDATE fake_plan_results SET sha256=?,body=? WHERE request_id=?',(hashlib.sha256(raw.encode()).hexdigest(),raw,first['request_id']))
        a.store.conn.execute('UPDATE fake_operator_requests SET result=? WHERE request_id=?',(raw,first['request_id']))
    with pytest.raises(RuntimeRefused,match='OPERATION_STATE_CORRUPT'):a.handle(p)
    assert len(submissions(a))==1
