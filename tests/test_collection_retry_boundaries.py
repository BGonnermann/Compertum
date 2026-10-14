"""Additional injected producer boundaries, with every terminal snapshot revalidated."""
from datetime import datetime,timezone
from uuid import UUID
import pytest
from compertum.data.encoding import canonical
from compertum.runtime.errors import RuntimeRefused
from compertum.runtime.http_retry import normalize_retry_after
from compertum.runtime._winhttp_get import _HTTPResult
import compertum.runtime._winhttp_get as native
import compertum.runtime.paper_market_collection as producer
from test_market_dispatch_observer import injected
from test_collection_retry_injected import collection_fixture,good,step,retry_ready,validate_snapshot


def test_eight_total_attempts_across_pages_stop_without_ninth(collection_fixture):
 c,clock,_=collection_fixture
 clock['responses']=[(503,b'{"message":"busy"}',None)]+[(200,good(str(i)),None) for i in range(1,8)]
 step(c);retry_ready(c,clock)
 for _ in range(7):step(c)
 v=c.private_snapshot().to_payload();assert v['attempts']==8 and v['reason']=='PAGE_LIMIT' and len(v['selected_requests'])==7
 assert len(clock['requests'])==8
 with pytest.raises(RuntimeRefused):c.dispatch()
 assert len(clock['requests'])==8


def test_total_limit_also_stops_eligible_http_failure(collection_fixture):
 c,clock,_=collection_fixture
 clock['responses']=[(200,good(str(i)),None) for i in range(1,7)]+[(503,b'{"message":"busy"}',None)]*2
 for _ in range(7):step(c)
 retry_ready(c,clock);step(c);v=c.private_snapshot().to_payload()
 assert v['attempts']==8 and v['reason']=='PAGE_LIMIT' and v['attempt_chain'][-1]['terminal_reason']=='TOTAL_ATTEMPT_LIMIT'

@pytest.mark.parametrize('header',['3','Fri, 09 Oct 2026 13:20:03 GMT'])
def test_retry_after_exact_boundary_without_busy_sleep(collection_fixture,header):
 c,clock,_=collection_fixture
 h=normalize_retry_after(header,observed_at=datetime(2026,10,9,13,20,tzinfo=timezone.utc),monotonic_ns=clock['ns'])
 clock['responses']=[(429,b'{"message":"busy"}',h),(200,good(),None)]
 step(c);assert c._retry_target_ns==h.not_before_ns
 clock['ns']=h.not_before_ns-1;assert c.dispatch()=='WAITING' and c.status()['attempts']==1
 clock['ns']+=1;step(c);v=c.private_snapshot().to_payload()
 assert v['state']=='PAGINATION_COMPLETE' and v['attempt_chain'][0]['retry_after']['not_before_ns']==h.not_before_ns


def test_retry_after_past_deadline_stops_after_one_attempt(collection_fixture):
 c,clock,_=collection_fixture
 h=normalize_retry_after('80',observed_at=datetime(2026,10,9,13,20,tzinfo=timezone.utc),monotonic_ns=clock['ns'])
 clock['responses']=[(429,b'{"message":"busy"}',h)];step(c);v=c.private_snapshot().to_payload()
 assert v['reason']=='HTTP_REFUSED' and v['attempts']==1 and v['attempt_chain'][0]['terminal_reason']=='RETRY_EXCEEDS_DEADLINE'

@pytest.mark.parametrize('status,body',[(403,b'{"message":"forbidden"}'),(503,b'{"message":"invented_key"}'),(503,b'{'),(200,b'{"bars":[],"next_page_token":null}')])
def test_unauthorized_secret_parser_and_semantic_failures_never_retry(collection_fixture,status,body):
 c,clock,_=collection_fixture;clock['responses']=[(status,body,None)];step(c);v=c.private_snapshot().to_payload()
 assert v['state']=='INCOMPLETE' and v['attempts']==1
 assert 'invented_key' not in str(v)
 if b'invented_key' in body or body==b'{':assert v['attempt_chain'][0]['reply'] is None


def test_malformed_retry_observation_is_terminal(collection_fixture):
 c,clock,_=collection_fixture;clock['responses']=[(429,b'{"message":"busy"}','invalid')];step(c)
 assert c.private_snapshot().to_payload()['reason']=='REPLY_REFUSED'


def test_changed_result_identity_stops_without_retaining_unqualified_body(collection_fixture,monkeypatch):
 c,clock,_=collection_fixture;clock['responses']=[(503,b'{"message":"busy"}',None)]
 old=native._OwnedHTTP.poll
 def changed(t):
  r=old(t);return _HTTPResult(r.status_code,r.body,r.retry_after)
 monkeypatch.setattr(native._OwnedHTTP,'poll',changed);step(c);v=c.private_snapshot().to_payload()
 assert v['reason']=='REPLY_REFUSED' and v['attempt_chain'][0]['reply'] is None


def test_validation_finishing_after_original_deadline_is_retained_as_failure(collection_fixture,monkeypatch):
 c,clock,_=collection_fixture;clock['responses']=[(200,good(),None)];old=producer.qualify_market_inputs
 def slow(*a,**kw):
  result=old(*a,**kw);clock['ns']=c._deadline_ns;return result
 monkeypatch.setattr(producer,'qualify_market_inputs',slow);step(c);v=c.private_snapshot().to_payload()
 assert v['reason']=='TOTAL_DEADLINE' and v['selected_requests']==[] and v['attempt_chain'][0]['reply'] is not None


def test_current_actions_retries_with_exact_cursor_and_safe_projection(collection_fixture):
 old,clock,_=collection_fixture;lease=old._lease;plan=old._plan;protected=old._protected;old.close()
 c=producer._MarketCollection(lease,plan,protected,collection_id=str(UUID(int=601)),mode='CURRENT_ACTIONS',_test_port=12345,_test_clock=lambda:clock['wall'],_test_monotonic=lambda:0.)
 try:
  clock['responses']=[(503,b'{"message":"busy"}',None),(200,canonical(dict(corporate_actions={},next_page_token=None)),None)]
  step(c);retry_ready(c,clock);step(c);v=c.private_snapshot().to_payload();validate_snapshot(c)
  assert v['state']=='PAGINATION_COMPLETE' and v['mode']=='CURRENT_ACTIONS' and len(v['selected_requests'])==1
 finally:c.close()