"""Pure historical attempt evidence. No native transport or credentials."""
from decimal import Decimal
from datetime import datetime,timezone,timedelta
from uuid import UUID
import pytest
from compertum.data.encoding import canonical
from compertum.paper_market_inputs import prepare_market_plan,prepare_market_request,_sha,_ns
from compertum.paper_action_inputs import prepare_action_query,_request_payload
from compertum.runtime.errors import RuntimeRefused
from compertum.runtime.paper_market_attempts import validate_attempt_chain,can_retain_attempt

NS=10**9
START=10*NS
BASE=datetime(2026,10,9,13,20,tzinfo=timezone.utc)

def stamp(seconds):return (BASE+timedelta(seconds=seconds)).isoformat().replace('+00:00','Z')

def plan():return prepare_market_plan(project_id='a'*64,account_alias='paper-primary',symbol='AAPL',session_date='2026-10-09',created_at=stamp(0))

def entry(index=1,page=1,ordinal=1,mode='HISTORY',status=200,at=1,cursor=None,next_cursor=None,outcome='SELECTED',reason=None):
 p=plan();rid=str(UUID(int=index));requested=stamp(at);received=stamp(at+.1);validated=stamp(at+.2)
 req=prepare_market_request(p,operation='HISTORY',request_id=rid,created_at=requested,page_token=cursor).to_payload() if mode=='HISTORY' else _request_payload(prepare_action_query(p),rid,requested,cursor)
 raw=canonical(dict(bars={'AAPL':[]},next_page_token=next_cursor) if mode=='HISTORY' else dict(corporate_actions={},next_page_token=next_cursor)) if status==200 else b'{"message":"temporary failure"}'
 d=dict(version=1,record_type='PrivateMarketReply',scope='PREPARATION_ONLY',request_sha256=_sha(canonical(req)),plan_sha256=p.sha256,request_id=rid,operation=mode,status=status,received_at=received,age_ns=_ns(received)-_ns(requested),raw_bytes=len(raw),raw_sha256=_sha(raw),transport_provenance='LOOPBACK_FIXTURE',credential_dispatch_binding='NOT_SENT_FIXTURE',outcome='HTTP_RESPONSE_OBSERVED' if status==200 else 'HTTP_REFUSED',semantic_qualification='NOT_PERFORMED',timestamps='DECLARED',transport_authorized=False,financial_accepted=False,research_eligible=False,entitlement='UNVERIFIED',coverage='UNVERIFIED')
 completed=START+int((Decimal(str(at))+Decimal(".2"))*NS)
 return dict(index=index,page=page,page_attempt=ordinal,request=req,pre_send_at=requested,pre_send_monotonic_ns=START+int(Decimal(str(at))*NS),dispatch_committed_ns=START+int(Decimal(str(at))*NS),completed_monotonic_ns=completed,native_closed=True,observed_status=status,reply=dict(body_utf8=raw.decode(),diagnostic=d,validated_at=validated),retry_after=None,outcome=outcome,terminal_reason=reason,retry_not_before_ns=completed+(1 if ordinal==1 else 4)*NS if outcome=='RETRY' else None)

def check(chain,mode='HISTORY',selected=None,**kw):
 if selected is None:selected=[r['request']['request_id'] for r in chain if r['outcome']=='SELECTED']
 return validate_attempt_chain(plan(),mode=mode,chain=chain,selected_requests=selected,started_at=stamp(0),started_ns=START,deadline_ns=START+80*NS,clock_basis='SYNTHETIC_FIXTURE',**kw)

@pytest.mark.parametrize('mode',['HISTORY','CURRENT_ACTIONS'])
def test_retry_keeps_failed_original_and_selects_success(mode):
 a=entry(mode=mode,status=429,outcome='RETRY');b=entry(2,ordinal=2,mode=mode,at=2.2)
 chain=[a,b];before=canonical(chain);v=check(chain,mode)
 assert canonical(chain)==before and len(v['records'])==1
 assert v['records'][0]['diagnostic']==b['reply']['diagnostic']
 assert v['records'][0]['body_utf8']==b['reply']['body_utf8']
 assert v['next_cursor'] is None and v['validated_at']==b['reply']['validated_at']
 assert a['reply']['body_utf8']=='{"message":"temporary failure"}'

def test_three_failures_terminal_and_fourth_refused():
 chain=[entry(status=503,outcome='RETRY'),entry(2,ordinal=2,status=503,at=2.2,outcome='RETRY'),entry(3,ordinal=3,status=503,at=6.4,outcome='TERMINAL',reason='PAGE_ATTEMPT_LIMIT')]
 assert check(chain)['records']==[]
 with pytest.raises(RuntimeRefused):check(chain+[entry(4,ordinal=4,at=8)])

def test_cursor_advances_only_after_selected_response():
 chain=[entry(status=503,outcome='RETRY'),entry(2,ordinal=2,at=2.2,next_cursor='next'),entry(3,page=2,at=3,cursor='next')]
 assert len(check(chain)['records'])==2
 chain[-1]['request']['parameters']['page_token']='other'
 with pytest.raises(RuntimeRefused):check(chain)

def test_eight_total_attempts_and_ninth_refused():
 chain=[entry(i,page=i,at=i,cursor=None if i==1 else str(i-1),next_cursor=str(i)) for i in range(1,9)]
 assert len(check(chain)['records'])==8
 with pytest.raises(RuntimeRefused):check(chain+[entry(9,page=9,at=9,cursor='8')])

@pytest.mark.parametrize('committed',[False,True])
def test_terminal_without_response_does_not_invent_body(committed):
 a=entry(outcome='TERMINAL',reason='DISPATCH_FAILED');a.update(reply=None,observed_status=None)
 if not committed:a.update(pre_send_at=None,pre_send_monotonic_ns=None,dispatch_committed_ns=None)
 assert check([a])['records']==[]
 assert a['reply'] is None and a['observed_status'] is None

def test_uncertain_cleanup_is_terminal_and_prevents_retry():
 a=entry(outcome='TERMINAL',reason='NATIVE_CLEANUP_UNVERIFIED');a.update(reply=None,native_closed=False)
 assert check([a])['records']==[]
 a['outcome']='RETRY';a['terminal_reason']=None
 with pytest.raises(RuntimeRefused):check([a,entry(2,ordinal=2,at=3)])

@pytest.mark.parametrize('mutation',[
 'duplicate_id','wrong_page','wrong_ordinal','early_retry','late_dispatch','backward_completion','missing_commit','status_body_mismatch',
 'raw_hash','diagnostic_extra','reply_extra','entry_extra','changed_cursor','selected_failure','dropped_selection','extra_selection',
 'retry_noneligible','retry_third','retry_uncertain_cleanup','retry_target','retry_header_target','terminal_continued','missing_reply','false_native_provenance'])
def test_tampered_chain_refused(mutation):
 a=entry(status=503,outcome='RETRY');b=entry(2,ordinal=2,at=2.2);chain=[a,b];selected=None
 if mutation=='duplicate_id':b['request']['request_id']=a['request']['request_id']
 elif mutation=='wrong_page':b['page']=2
 elif mutation=='wrong_ordinal':b['page_attempt']=1
 elif mutation=='early_retry':b['pre_send_monotonic_ns']-=1;b['dispatch_committed_ns']-=1
 elif mutation=='late_dispatch':b['dispatch_committed_ns']=START+80*NS
 elif mutation=='backward_completion':b['completed_monotonic_ns']=START
 elif mutation=='missing_commit':b['dispatch_committed_ns']=None
 elif mutation=='status_body_mismatch':b['observed_status']=429
 elif mutation=='raw_hash':a['reply']['diagnostic']['raw_sha256']='0'*64
 elif mutation=='diagnostic_extra':a['reply']['diagnostic']['extra']=1
 elif mutation=='reply_extra':a['reply']['extra']=1
 elif mutation=='entry_extra':a['extra']=1
 elif mutation=='changed_cursor':b['request']['parameters']['page_token']='other'
 elif mutation=='selected_failure':a['outcome']='SELECTED'
 elif mutation=='dropped_selection':selected=[]
 elif mutation=='extra_selection':selected=[a['request']['request_id'],b['request']['request_id']]
 elif mutation=='retry_noneligible':a['observed_status']=403;a['reply']['diagnostic']['status']=403
 elif mutation=='retry_third':a['page_attempt']=3
 elif mutation=='retry_uncertain_cleanup':a['native_closed']=False
 elif mutation=='retry_target':a['retry_not_before_ns']-=1
 elif mutation=='retry_header_target':a['retry_after']=dict(kind='DELAY_SECONDS',delay_ns=3*NS,observed_at=stamp(1.1),observed_monotonic_ns=START+1100000000,not_before_ns=START+4100000000)
 elif mutation=='terminal_continued':a['outcome']='TERMINAL';a['terminal_reason']='CANCELLED';a['retry_not_before_ns']=None
 elif mutation=='missing_reply':b['reply']=None
 else:a['reply']['diagnostic']['transport_provenance']='DATA_TLS'
 with pytest.raises(RuntimeRefused):check(chain,selected=selected)

def test_retry_after_preserved_and_honored():
 a=entry(status=429,outcome='RETRY');a['retry_after']=dict(kind='DELAY_SECONDS',delay_ns=3*NS,observed_at=stamp(1.1),observed_monotonic_ns=START+1100000000,not_before_ns=START+4100000000);a['retry_not_before_ns']=START+4100000000
 assert len(check([a,entry(2,ordinal=2,at=4.1)])['records'])==1

def test_empty_projection_valid_incomplete_shape():
 assert check([])['records']==[]

def test_capacity_refuses_before_maximum_next_response_cannot_fit():
 assert can_retain_attempt(plan(),[])
 assert not can_retain_attempt(plan(),[{'retained':'x'*600000}])

@pytest.mark.parametrize('field,value',[('index',True),('page',True),('page_attempt',True),('completed_monotonic_ns',True),('native_closed',1),('observed_status',True)])
def test_exact_types(field,value):
 a=entry();a[field]=value
 with pytest.raises(RuntimeRefused):check([a])
@pytest.mark.parametrize('delta,accepted',[(-1,True),(0,False),(1,False)])
def test_selected_completion_respects_original_monotonic_deadline(delta,accepted):
 a=entry();a['completed_monotonic_ns']=START+80*NS+delta
 if accepted:assert len(check([a])['records'])==1
 else:
  with pytest.raises(RuntimeRefused):check([a])

def test_cutoff_shortens_original_deadline_for_selection_and_retry(monkeypatch):
 import sys
 monkeypatch.setattr(sys.modules[__name__],'BASE',datetime(2026,10,9,13,24,50,tzinfo=timezone.utc))
 def shortened(chain):
  return validate_attempt_chain(plan(),mode='HISTORY',chain=chain,selected_requests=[a['request']['request_id'] for a in chain if a['outcome']=='SELECTED'],started_at=stamp(0),started_ns=START,deadline_ns=START+10*NS,clock_basis='SYNTHETIC_FIXTURE')
 a=entry(at=9.7);assert len(shortened([a])['records'])==1
 a['completed_monotonic_ns']=START+10*NS
 with pytest.raises(RuntimeRefused):shortened([a])
 terminal=entry(status=429,at=9,outcome='TERMINAL',reason='RETRY_EXCEEDS_DEADLINE')
 assert shortened([terminal])['records']==[]
 terminal.update(outcome='RETRY',terminal_reason=None,retry_not_before_ns=START+10200000000)
 with pytest.raises(RuntimeRefused):shortened([terminal])

def test_retention_reserves_escaped_body_request_diagnostic_and_metadata():
 # Real UTF-8 JSON bodies with escaped quotes occupy nearly twice their raw size
 # when retained as body_utf8. Next-attempt reservation must still fit entirely.
 body=canonical({'message':'"'*32750})
 assert 65000<len(body)<=65536
 chain=[]
 for i in range(1,9):
  a=entry(i,page=i,at=i,next_cursor=str(i),cursor=None if i==1 else str(i-1))
  a['reply']['body_utf8']=body.decode();chain.append(a)
  used=len(canonical(dict(plan=plan().to_payload(),attempt_chain=chain)))
  required=6*65536+65536+8192+16384
  assert can_retain_attempt(plan(),chain)==(i<8 and used+required<=1048576)
 assert not can_retain_attempt(plan(),chain)