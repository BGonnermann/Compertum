"""Pure scheduling decisions; never native dispatch or retry authority."""
from datetime import datetime,timezone
import pytest
from compertum.runtime.errors import RuntimeRefused
from compertum.runtime.http_retry import normalize_retry_after,_RetryAfter
from compertum.runtime.read_retry import decide_read_retry
NS=10**9;NOW=datetime(2026,10,12,tzinfo=timezone.utc)
def decide(**changes):
 p=dict(status_code=503,completed_attempts=1,failed_at_ns=10*NS,now_ns=10*NS,deadline_ns=80*NS,retry_after=None);p.update(changes);return decide_read_retry(**p)
@pytest.mark.parametrize('attempt,delay',[(1,1),(2,4)])
def test_backoff_exact_boundaries(attempt,delay):
 target=(10+delay)*NS
 for now,state in [(10*NS,'WAITING'),(target-1,'WAITING'),(target,'READY'),(target+1,'READY')]:
  r=decide(completed_attempts=attempt,now_ns=now);assert (r.state,r.not_before_ns,r.reason)==(state,target,None)
@pytest.mark.parametrize('status',[408,429,500,502,503,504])
def test_only_declared_http_statuses_retry(status):assert decide(status_code=status).state=='WAITING'
@pytest.mark.parametrize('status',[200,301,400,401,403,404,409,422,501,505,599])
def test_other_http_responses_are_terminal(status):
 r=decide(status_code=status);assert (r.state,r.not_before_ns,r.reason)==('TERMINAL',None,'HTTP_STATUS_NOT_RETRYABLE')
def test_third_failed_attempt_is_terminal():
 r=decide(completed_attempts=3);assert (r.state,r.not_before_ns,r.reason)==('TERMINAL',None,'PAGE_ATTEMPT_LIMIT')
@pytest.mark.parametrize('header,target',[('0',11*NS),('7',16*NS),('Mon, 12 Oct 2026 00:00:07 GMT',16*NS)])
def test_normalized_header_and_completion_backoff_both_apply(header,target):
 h=normalize_retry_after(header,observed_at=NOW,monotonic_ns=9*NS);r=decide(retry_after=h);assert r.not_before_ns==target and r.state=='WAITING'
def test_second_backoff_can_dominate_earlier_retry_header():
 h=normalize_retry_after('1',observed_at=NOW,monotonic_ns=9*NS);assert decide(completed_attempts=2,retry_after=h).not_before_ns==14*NS
@pytest.mark.parametrize('deadline',[10*NS,11*NS])
def test_deadline_must_allow_start_strictly_before_expiry(deadline):
 r=decide(deadline_ns=deadline);assert r.state=='TERMINAL' and r.not_before_ns is None
@pytest.mark.parametrize('field,value',[('status_code',True),('status_code',99),('status_code',600),('completed_attempts',0),('completed_attempts',4),('completed_attempts',True),('now_ns',9*NS),('now_ns',1.0),('failed_at_ns',-1),('deadline_ns',2**63),('retry_after',{}),('now_ns',True)])
def test_invalid_observations_fail_closed(field,value):
 with pytest.raises(RuntimeRefused,match='READ_RETRY_INPUT_INVALID'):decide(**{field:value})
@pytest.mark.parametrize('change',[{'kind':'BAD'},{'observed_monotonic_ns':11*NS},{'not_before_ns':12*NS},{'delay_ns':-1},{'observed_at':datetime(2026,10,12)},{'delay_ns':True}])
def test_forged_normalized_observation_is_rejected(change):
 p=dict(kind='DELAY_SECONDS',delay_ns=NS,observed_at=NOW,observed_monotonic_ns=9*NS,not_before_ns=10*NS);p.update(change)
 with pytest.raises(RuntimeRefused,match='READ_RETRY_INPUT_INVALID'):decide(retry_after=_RetryAfter(**p))
def test_backoff_arithmetic_cannot_overflow():
 with pytest.raises(RuntimeRefused,match='READ_RETRY_INPUT_INVALID'):decide(failed_at_ns=2**63-2,now_ns=2**63-2,deadline_ns=2**63-1)
