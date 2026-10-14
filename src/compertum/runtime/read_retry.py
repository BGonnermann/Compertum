"""Pure bounded HTTP-read retry timing. A decision grants no dispatch authority."""
from dataclasses import dataclass
from datetime import datetime,timezone
from .errors import RuntimeRefused
from .http_retry import _RetryAfter,_MAX_NS,_MAX_WAIT_NS

_RETRYABLE=frozenset({408,429,500,502,503,504})
_NS=10**9

@dataclass(frozen=True,slots=True)
class ReadRetryDecision:
    state:str
    not_before_ns:int|None
    reason:str|None


def _need(value):
    if not value:raise RuntimeRefused('READ_RETRY_INPUT_INVALID')


def decide_read_retry(*,status_code,completed_attempts,failed_at_ns,now_ns,deadline_ns,retry_after=None):
    """Use one monotonic clock; retain the original task deadline at the caller."""
    _need(type(status_code) is int and 100<=status_code<=599)
    _need(type(completed_attempts) is int and 1<=completed_attempts<=3)
    _need(all(type(v) is int and 0<=v<=_MAX_NS for v in (failed_at_ns,now_ns,deadline_ns)))
    _need(failed_at_ns<=now_ns)
    if retry_after is not None:
        _need(type(retry_after) is _RetryAfter)
        h=retry_after
        _need(type(h.kind) is str and h.kind in ('DELAY_SECONDS','HTTP_DATE') and type(h.observed_at) is datetime and h.observed_at.tzinfo is timezone.utc)
        _need(type(h.delay_ns) is int and 0<=h.delay_ns<=_MAX_WAIT_NS)
        _need(type(h.observed_monotonic_ns) is int and 0<=h.observed_monotonic_ns<=failed_at_ns)
        _need(type(h.not_before_ns) is int and h.not_before_ns==h.observed_monotonic_ns+h.delay_ns<=_MAX_NS)
    if status_code not in _RETRYABLE:return ReadRetryDecision('TERMINAL',None,'HTTP_STATUS_NOT_RETRYABLE')
    if completed_attempts==3:return ReadRetryDecision('TERMINAL',None,'PAGE_ATTEMPT_LIMIT')
    if now_ns>=deadline_ns:return ReadRetryDecision('TERMINAL',None,'TASK_DEADLINE')
    target=failed_at_ns+(1 if completed_attempts==1 else 4)*_NS
    _need(target<=_MAX_NS)
    if retry_after is not None:target=max(target,retry_after.not_before_ns)
    if target>=deadline_ns:return ReadRetryDecision('TERMINAL',None,'RETRY_EXCEEDS_DEADLINE')
    return ReadRetryDecision('WAITING' if now_ns<target else 'READY',target,None)
