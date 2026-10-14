"""Real owner-scope checks with explicit post-exit fault/time injection."""
from contextlib import contextmanager
import pytest
from compertum.runtime.errors import RuntimeRefused
from test_execution_health import pair,connect
from test_paper_read_owner import owner
from test_paper_read_publication import publication,launch
from test_paper_account_binding import invented_paper_origin,propose,confirm,call
from test_paper_presence import account,acknowledge,advance,inspect
from test_paper_account_context import context
from test_paper_account_presence_proofs import presence_proof


@pytest.mark.parametrize('fault',['owner_failure','elapsed_reads'])
def test_scope_exit_finishes_before_common_classification_and_final_clocks(account,monkeypatch,fault):
    import compertum.runtime.paper_final_proof as module
    o,_,_=account;_,r=acknowledge(account);ctx=context(account)
    cp=ctx._prepare_proof();pp=presence_proof(o,r);advance(o,28)
    original=module._owner_scope;fired=[False]
    @contextmanager
    def changed(lease):
        with original(lease) as guard:yield guard
        fired[0]=True
        if fault=='owner_failure':raise RuntimeRefused('INVENTED_FINAL_OWNER_EXIT')
        o.clock.utc+=3;o.clock.mono+=3;o.c.utc+=3;o.c.mono+=3
    monkeypatch.setattr(module,'_owner_scope',changed)
    try:
        with pytest.raises(RuntimeRefused,match='INVENTED_FINAL_OWNER_EXIT' if fault=='owner_failure' else 'PAPER_PREFLIGHT_STALE'):
            module._verify_proofs(cp,pp)
    finally:monkeypatch.setattr(module,'_owner_scope',original)
    assert fired[0] and ctx._closed
    assert inspect(o,r)['presence_status']==('INVALIDATED' if fault=='owner_failure' else 'CURRENT')
