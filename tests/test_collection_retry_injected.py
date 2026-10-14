"""Collection state machine with injected ownership/API. Native acceptance separate."""
from contextlib import contextmanager
from types import SimpleNamespace
from uuid import UUID
import time,json
import pytest
from compertum.data.encoding import canonical
from compertum.runtime.errors import RuntimeRefused
from compertum.runtime.paper_credentials import ProtectedPaperCredentials
from compertum.runtime._winhttp_get import _HTTPResult
import compertum.runtime.paper_market_collection as producer
import compertum.runtime.paper_market_qualification as qualification
import compertum.runtime._winhttp_data as data
import compertum.runtime._winhttp_get as native
from test_market_dispatch_observer import injected
import test_paper_market_attempts as f

@pytest.fixture
def collection_fixture(injected,monkeypatch):
 lease,trace,fault=injected;lease.generation=1;lease.identity=SimpleNamespace(process_instance_id=str(UUID(int=77)))
 clock={'ns':time.monotonic_ns(),'wall':f.stamp(0),'queue':True,'responses':[],'requests':[]}
 for m in (producer,qualification):
  monkeypatch.setattr(m,'_owner_scope',data._owner_scope);monkeypatch.setattr(m,'require_live_owner',lambda *a:None)
  monkeypatch.setattr(m,'time',SimpleNamespace(monotonic=time.monotonic,monotonic_ns=lambda:clock['ns']))
 @contextmanager
 def credentials(*args):yield SimpleNamespace(headers=lambda:{'APCA-API-KEY-ID':'invented_key','APCA-API-SECRET-KEY':'invented_secret'})
 monkeypatch.setattr(producer,'open_paper_credentials',credentials);monkeypatch.setattr(qualification,'open_paper_credentials',credentials)
 monkeypatch.setattr(producer,'producer_permit',lambda c:object() if clock['queue'] else None)
 monkeypatch.setattr(producer,'bind_producer_permit',lambda *a:None);monkeypatch.setattr(producer,'cancel_producer',lambda *a:None)
 def poll(t):
  status,raw,header=clock['responses'].pop(0);clock['requests'].append(json.loads(t._request_bytes));t.status_code=status;t.retry_after=header
  t.close();t._result=_HTTPResult(status,raw,header);return t._result
 monkeypatch.setattr(native._OwnedHTTP,'poll',poll)
 protected=ProtectedPaperCredentials('a'*64,'paper-primary',b'injected_not_encrypted')
 c=producer._MarketCollection(lease,f.plan(),protected,collection_id=str(UUID(int=600)),mode='HISTORY',_test_port=12345,_test_clock=lambda:clock['wall'],_test_monotonic=lambda:0.)
 yield c,clock,fault
 if c._state in ('PAGINATION_COMPLETE','INCOMPLETE') and not c._closed:validate_snapshot(c)
 c.close()

def good(token=None):return canonical(dict(bars={'AAPL':[]},next_page_token=token))

def step(c):c.dispatch();assert c.poll()

def retry_ready(c,clock):
 assert c.status()['state']=='READY'
 assert c.dispatch()=='WAITING'
 clock['ns']=c._retry_target_ns


def test_failed_page_retries_with_new_id_and_preserves_original(collection_fixture):
 c,clock,_=collection_fixture;clock['responses']=[(429,b'{"message":"busy"}',None),(200,good(),None)]
 step(c);assert c.status()['attempts']==1;retry_ready(c,clock);step(c)
 v=c.private_snapshot().to_payload();assert v['version']==2 and v['state']=='PAGINATION_COMPLETE' and len(v['attempt_chain'])==2
 assert v['attempt_chain'][0]['reply']['body_utf8']=='{"message":"busy"}' and len(v['selected_requests'])==1
 assert len({r['request_id'] for r in clock['requests']})==2
 assert all(r['parameters'].get('page_token') is None for r in clock['requests'])


def test_two_waits_then_success_keeps_original_deadline(collection_fixture):
 c,clock,_=collection_fixture;start=c._deadline_ns
 clock['responses']=[(503,b'{"message":"busy"}',None)]*2+[(200,good(),None)]
 for seconds in (1,4):
  step(c);failed=c._chain[-1]['completed_monotonic_ns'];retry_ready(c,clock);assert clock['ns']==failed+seconds*10**9
 step(c);assert c._deadline_ns==start and c.private_snapshot().to_payload()['state']=='PAGINATION_COMPLETE'


def test_third_failure_terminal(collection_fixture):
 c,clock,_=collection_fixture;clock['responses']=[(503,b'{"message":"busy"}',None)]*3
 for _ in range(2):step(c);retry_ready(c,clock)
 step(c);v=c.private_snapshot().to_payload()
 assert v['state']=='INCOMPLETE' and v['reason']=='HTTP_REFUSED' and v['attempts']==3
 assert v['attempt_chain'][-1]['terminal_reason']=='PAGE_ATTEMPT_LIMIT'


def test_wait_and_queue_do_not_consume_attempts(collection_fixture):
 c,clock,_=collection_fixture;clock['responses']=[(429,b'{"message":"busy"}',None),(200,good(),None)]
 step(c);ids=set(c._ids);assert c.dispatch()=='WAITING' and c._ids==ids
 clock['ns']=c._retry_target_ns;clock['queue']=False
 assert c.dispatch()=='WAITING' and c._ids==ids and c.status()['attempts']==1
 clock['wall']='2026-10-09T13:25:00Z'
 with pytest.raises(RuntimeRefused):c.dispatch()
 assert c.private_snapshot().to_payload()['reason']=='INFORMATION_CUTOFF'


def test_queue_cutoff_with_zero_attempts(collection_fixture):
 c,clock,_=collection_fixture;clock['queue']=False;assert c.dispatch()=='WAITING'
 clock['wall']='2026-10-09T13:25:00Z'
 with pytest.raises(RuntimeRefused):c.dispatch()
 v=c.private_snapshot().to_payload();assert v['version']==2 and v['attempts']==0 and v['reason']=='INFORMATION_CUTOFF'

@pytest.mark.parametrize('failure,committed',[('before',False),('send',True),('cleanup',True)])
def test_constructor_failure_retains_commit_and_cleanup(collection_fixture,failure,committed):
 c,clock,fault=collection_fixture;fault['stage']=failure
 with pytest.raises(RuntimeRefused):c.dispatch()
 v=c.private_snapshot().to_payload();a=v['attempt_chain'][0]
 assert (a['dispatch_committed_ns'] is not None)==committed and a['reply'] is None
 assert a['native_closed'] is (failure!='cleanup') and c.status()['state']=='INCOMPLETE'
 if failure=='cleanup':
  validate_snapshot(c)
  with pytest.raises(RuntimeRefused,match='HTTP_CLEANUP_UNVERIFIED'):c.close()
  transport=c._cleanup_pending._transport;assert not transport.native_closed
  # Release only the injected fake handle after proving the sticky close failure.
  fault['stage']=None;transport._cleanup_failed=False;c.close()


def test_success_without_retry_keeps_v1_shape(collection_fixture):
 c,clock,_=collection_fixture;clock['responses']=[(200,good(),None)];step(c);v=c.private_snapshot().to_payload()
 assert v['version']==1 and len(v['records'])==1 and 'attempt_chain' not in v


def test_cancel_while_waiting_keeps_failed_response(collection_fixture):
 c,clock,_=collection_fixture;clock['responses']=[(503,b'{"message":"busy"}',None)];step(c);c.cancel()
 v=c.private_snapshot().to_payload();assert v['reason']=='CANCELLED' and len(v['attempt_chain'])==1


def test_capacity_refusal_occurs_before_dispatch(collection_fixture,monkeypatch):
 c,clock,_=collection_fixture;monkeypatch.setattr(producer,'can_retain_attempt',lambda *a:False)
 with pytest.raises(RuntimeRefused):c.dispatch()
 assert c.status()['attempts']==0 and not clock['requests']
 assert c.private_snapshot().to_payload()['reason']=='RETENTION_LIMIT'
def validate_snapshot(c):
 from compertum.runtime.paper_market_evidence import _validate
 from compertum.paper_market_inputs import _sha
 raw=c.private_snapshot().content;task=str(UUID(int=700))
 meta=dict(version=1,record_type='PrivateMarketEvidence',purpose='OPERATIONAL_ONLY',project_id=c._lease.project_id,account_alias='paper-primary',task_id=task,
  collection_id=c._collection_id,execution_generation=1,credential_sha256=c._credential_sha,snapshot_sha256=_sha(raw))
 return _validate([canonical(meta),raw],c._lease.project_id,'paper-primary',task,c._collection_id)


def test_live_composition_checks_full_attempt_snapshot_then_projects_success(collection_fixture):
 import compertum.runtime.paper_market_compose as compose
 c,clock,_=collection_fixture;clock['responses']=[(503,b'{"message":"busy"}',None),(200,good(),None)]
 step(c);retry_ready(c,clock);step(c)
 source=c.private_snapshot();plan,raw,value,metadata,reference,identity=compose._history_source(c._lease,c._owner_state,source)
 assert raw==source.content and len(value['attempt_chain'])==2
 assert len(compose._history_records(value))==1
 assert reference['snapshot_sha256']==source._sha256 and reference['native_provenance']=='LOOPBACK_FIXTURE'
 # Changing a failed response invalidates the full live evidence binding.
 old=c._chain[0]['reply']['body_utf8'];c._chain[0]['reply']['body_utf8']='{"message":"changed"}'
 with pytest.raises(RuntimeRefused):compose._history_source(c._lease,c._owner_state,source)
 c._chain[0]['reply']['body_utf8']=old


def test_close_after_owner_revocation_does_not_require_live_evidence_access(collection_fixture,monkeypatch):
 c,clock,_=collection_fixture;c.dispatch()
 def revoked(*a):raise RuntimeRefused('INJECTED_REVOKED')
 monkeypatch.setattr(qualification,'require_live_owner',revoked)
 c.close();assert c._closed and c._pending is None and not native._PENDING