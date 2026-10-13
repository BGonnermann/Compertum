"""Controller error retention; native resource/worker proofs remain separate."""
from types import SimpleNamespace
import pytest
from compertum.research import ResearchController
from compertum.runtime.errors import RuntimeRefused


@pytest.mark.parametrize('later_failure',[False,True])
def test_recovery_latch_survives_later_completion(later_failure):
    c=ResearchController.__new__(ResearchController)
    original=dict(run_id='run',operation='step',phase='LAUNCH',reason='CAMPAIGN_CLEANUP_FAILED',recovery_required=True)
    c.last_operation_error=original.copy();c.active=None
    closed=[]
    def advance():
        if later_failure:raise ValueError('later_acceptance_error')
        return True
    c.pending=SimpleNamespace(run_id='run',action='complete',phase='ACCEPT',advance=advance,fail=lambda error:None,close=lambda:closed.append(True))
    c._advance_pending()
    assert c.pending is None and closed==[True] and c.last_operation_error==original
    assert c.busy
    with pytest.raises(RuntimeRefused,match='CAMPAIGN_RECOVERY_REQUIRED'):c._require_recovery_clear()
