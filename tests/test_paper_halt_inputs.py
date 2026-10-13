"""A status message is an observation, never proof of complete current halt coverage."""
from dataclasses import replace
from datetime import timedelta
from decimal import localcontext
from uuid import UUID
import hashlib,json
import pytest
from compertum.domain import ContractError
from compertum.data.encoding import canonical
from compertum.data.calendar import session_times
from compertum.paper_market_inputs import prepare_market_plan
from compertum.paper_halt_inputs import HaltStreamPlan,HaltStatusFrame,HaltStatusInputs,prepare_halt_plan,qualify_halt_inputs

DAY='2026-10-09'
def uid(n):return str(UUID(int=n))
def stamp(seconds=0,day=DAY):return (session_times(day).decision-timedelta(minutes=5)+timedelta(seconds=seconds)).isoformat().replace('+00:00','Z')
def plan(day=DAY,tape='C',symbol='AAPL'):
 m=prepare_market_plan(project_id='a'*64,account_alias='paper-primary',symbol=symbol,session_date=day,created_at=stamp(day=day))
 return prepare_halt_plan(m,expected_tape=tape)
def event(**edit):
 v=dict(T='s',S='AAPL',sc='H',sm='Trading Halt',rc='T1',rm='News pending',t=stamp(2),z='C');v.update(edit);return v
def frame(p=None,events=None,n=1,**edit):
 p=p or plan();day=p.market_plan.to_payload()['session_date']
 data=dict(plan=p,connection_id=uid(n),connected_at=stamp(1,day),received_at=stamp(3,day),gap_before=False,raw=json.dumps([event(t=stamp(2,day))] if events is None else events,separators=(',',':')).encode())
 data.update(edit);return HaltStatusFrame(**data)
def result(p=None,frames=None,as_of=None):
 p=p or plan();return qualify_halt_inputs(p,(frame(p),) if frames is None else frames,as_of=as_of or stamp(60,p.market_plan.to_payload()['session_date']))
def payload(*a,**kw):return json.loads(result(*a,**kw).content)


def test_original_frame_and_fixed_source_never_grant_current_clear():
 p=plan();f=frame(p);r=result(p,(f,));v=r.to_payload();q=p.to_payload()
 assert q['url']=='wss://stream.data.alpaca.markets/v2/iex' and q['subscription']=={'action':'subscribe','statuses':['AAPL']}
 assert q['expected_tape']=='C' and q['transport_authorized'] is False
 assert v['latest_observed_status']=='HALTED' and v['has_blocking_observation'] is True
 assert v['current_halt_state']=='UNVERIFIED' and v['status']=='BLOCKED'
 assert all(v[k]=='UNVERIFIED' for k in ('initial_state','continuity','freshness_basis','native_provenance','feed_entitlement','identity_mapping'))
 assert all(v[k] is False for k in ('transport_authorized','financial_accepted','research_eligible'))
 assert json.loads(r.evidence_bytes())['frames'][0]['body_utf8'].encode()==f.raw
 assert v['evidence_sha256']==hashlib.sha256(r.evidence_bytes()).hexdigest()
 assert 'News pending' not in repr(f)


@pytest.mark.parametrize('tape,code,expected,blocking',[
 ('A','2','HALTED',True),('B','3','TRADING_RESUMPTION_REPORTED',False),
 ('C','H','HALTED',True),('O','P','PAUSED',True),('C','Q','QUOTE_RESUMPTION_ONLY',True),('C','T','TRADING_RESUMPTION_REPORTED',False),
 *[('A',s,'INFORMATIONAL',False) for s in ('5','6','7','8','9','A','C','D','E','F')]])
def test_tape_specific_codes(tape,code,expected,blocking):
 p=plan(tape=tape);v=payload(p,(frame(p,events=[event(z=tape,sc=code)]),))
 assert v['events'][0]['classification']==expected and v['latest_observed_status']==expected
 assert v['has_blocking_observation'] is blocking and v['current_halt_state']=='UNVERIFIED'


@pytest.mark.parametrize('events,issue',[([], 'STATUS_MESSAGES_MISSING'),([event(sc='new')],'STATUS_CODE_UNKNOWN'),([event(z='Z')],'STATUS_TAPE_UNKNOWN'),([event(z='A',sc='2')],'STATUS_TAPE_MISMATCH'),([event(S='MSFT')],'STATUS_SYMBOL_MISMATCH'),([event(T='q')],'STATUS_MESSAGE_TYPE'),([None,42,{}],'STATUS_FIELDS'),([event(sc=2)],'STATUS_FIELDS'),([event(rc=None)],'STATUS_FIELDS'),([event(t='bad')],'STATUS_TIME_INVALID'),([event(extra='surprise')],'STATUS_FIELDS_UNRECOGNIZED')])
def test_untrusted_or_missing_messages_remain_visible(events,issue):
 f=frame(events=events);r=result(frames=(f,));v=r.to_payload()
 assert len(v['events'])==len(events) and issue in v['issues'] and v['current_halt_state']=='UNVERIFIED'
 assert json.loads(r.evidence_bytes())['frames'][0]['body_utf8'].encode()==f.raw


def test_missing_frames_are_explicit():
 v=payload(frames=());assert 'STATUS_FRAMES_MISSING' in v['issues'] and v['latest_observed_status']=='UNKNOWN'


def test_resumption_never_erases_prior_halt_or_known_gap():
 p=plan();frames=(frame(p),frame(p,n=2,connected_at=stamp(4),received_at=stamp(6),gap_before=True,events=[event(sc='T',t=stamp(5))]))
 v=payload(p,frames);assert v['latest_observed_status']=='TRADING_RESUMPTION_REPORTED'
 assert v['has_blocking_observation'] and 'STATUS_STREAM_RECONNECTED' in v['issues'] and 'STATUS_STREAM_GAP' in v['issues']
 assert v['current_halt_state']=='UNVERIFIED' and len(v['events'])==2


def test_arrival_order_preserved_when_source_times_go_backwards():
 f=frame(events=[event(t=stamp(2)),event(sc='T',t=stamp(1))]);v=payload(frames=(f,))
 assert [e['classification'] for e in v['events']]==['HALTED','TRADING_RESUMPTION_REPORTED']
 assert 'STATUS_TIME_OUT_OF_ORDER' in v['issues'] and v['latest_observed_status']=='HALTED'


@pytest.mark.parametrize('changes,issue,latest',[({},'DUPLICATE_STATUS_MESSAGE','HALTED'),({'sc':'T'},'CONFLICTING_STATUS_TIME','AMBIGUOUS'),({'rc':'T12'},'CONFLICTING_STATUS_TIME','AMBIGUOUS')])
def test_equal_time_duplicate_and_conflict_not_last_writer_wins(changes,issue,latest):
 v=payload(frames=(frame(events=[event(),event(**changes)]),))
 assert len(v['events'])==2 and issue in v['issues'] and v['latest_observed_status']==latest


def test_source_and_receipt_nanoseconds_are_preserved():
 exact=stamp(3);later=exact.replace('Z','.000000001Z')
 v=payload(frames=(frame(events=[event(t=later)]),));assert 'STATUS_TIME_AFTER_RECEIPT' in v['issues']
 assert v['latest_observed_status']=='UNKNOWN'
 v=payload(frames=(frame(events=[event(t=exact)]),));assert 'STATUS_TIME_AFTER_RECEIPT' not in v['issues']
 with pytest.raises(ContractError):result(frames=(frame(received_at=later),),as_of=exact)


def test_old_message_is_described_without_inventing_freshness_policy():
 v=payload(frames=(frame(events=[event(t=stamp(0))]),),as_of=stamp(3600))
 assert v['events'][0]['age_ns']==3600*10**9 and 'STATUS_PREDATES_CONNECTION' in v['issues']
 assert v['freshness_basis']=='UNVERIFIED' and 'STATUS_FRESHNESS_UNVERIFIED' in v['issues']


@pytest.mark.parametrize('day',['2026-03-09','2026-11-27'])
def test_dst_early_close_and_same_session_are_pinned(day):
 p=plan(day);v=payload(p,(frame(p),));assert v['session_date']==day


@pytest.mark.parametrize('edit',[{'connection_id':uid(0)},{'gap_before':1},{'connected_at':stamp(-1)},{'received_at':stamp(0)},{'received_at':'2026-10-08T13:20:03Z'},{'raw':b'{}'},{'raw':b'[{"T":"s","T":"s"}]'},{'raw':b'[NaN]'},{'raw':b' '*65537},{'raw':b'['*34+b'0'+b']'*34}],ids=['uuid','bool','beforeplan','beforereceive','day','object','duplicates','nonfinite','oversize','depth'])
def test_frame_contract_rejects_invalid_capture(edit):
 with pytest.raises(ContractError):frame(**edit)


def test_count_bound_includes_all_malformed_records():
 with pytest.raises(ContractError):frame(events=[None]*101)
 p=plan();f=frame(p)
 with pytest.raises(ContractError):result(p,(f,)*9)


def test_connection_generations_and_receipt_order_are_strict():
 p=plan();f=frame(p);other=frame(p,n=2,connected_at=stamp(4),received_at=stamp(5))
 with pytest.raises(ContractError):result(p,(f,replace(f,received_at=stamp(2))))
 with pytest.raises(ContractError):result(p,(f,replace(f,connected_at=stamp(2),received_at=stamp(4))))
 with pytest.raises(ContractError):result(p,(f,other,replace(f,received_at=stamp(6))))
 with pytest.raises(ContractError):result(p,(f,replace(other,connected_at=stamp(2))))


def test_plan_and_result_constructor_cannot_be_forged():
 p=plan();v=p.to_payload();v['url']='wss://stream.data.alpaca.markets/v2/sip'
 with pytest.raises(ContractError):HaltStreamPlan(p.market_plan,canonical(v))
 with pytest.raises(ContractError):result(p,(frame(plan(symbol='MSFT')),))
 r=result();v=r.to_payload();v['current_halt_state']='CLEAR'
 with pytest.raises(ContractError):replace(r,content=canonical(v))
 with pytest.raises(ContractError):result(p,(),as_of=stamp(-1))


def test_large_untrusted_text_never_amplifies_into_diagnostic():
 f=frame(events=[event(sm='x'*50000)]);r=result(frames=(f,))
 assert len(r.content)<10000 and r.to_payload()['events'][0]['classification']=='UNKNOWN'
 assert json.loads(r.evidence_bytes())['frames'][0]['body_utf8'].encode()==f.raw


def test_replay_is_context_independent():
 r=result()
 with localcontext() as c:
  c.prec=2
  assert result()==r


def test_after_cutoff_is_new_evidence_and_does_not_rewrite_earlier_result():
 p=plan();cutoff=p.market_plan.to_payload()['history_cutoff_at'];later=cutoff.replace('Z','.000000001Z')
 f=frame(p,received_at=cutoff);before=result(p,(f,),as_of=cutoff)
 after=result(p,(replace(f,received_at=later),),as_of=stamp(301))
 assert 'STATUS_RECEIVED_AFTER_CUTOFF' not in before.to_payload()['issues']
 assert 'STATUS_RECEIVED_AFTER_CUTOFF' in after.to_payload()['issues'] and before!=after
 assert result(p,(f,),as_of=cutoff)==before


def test_wrong_session_message_remains_visible_but_cannot_set_latest():
 f=frame(events=[event(t='2026-10-08T13:20:02Z')]);v=payload(frames=(f,))
 assert len(v['events'])==1 and 'STATUS_TIME_OTHER_SESSION' in v['issues']
 assert v['latest_observed_status']=='UNKNOWN'


def test_last_arrival_is_separate_from_latest_provider_time():
 f=frame(events=[event(t=stamp(2)),event(t=stamp(1),sc='T')]);v=payload(frames=(f,))
 assert v['latest_observed_at']==stamp(2) and v['last_arrival_event_index']==1
 assert v['connection_evidence']=='DECLARED' and 'STATUS_CONTINUITY_UNVERIFIED' in v['issues']


def test_equivalent_timestamp_spellings_are_duplicate_not_conflict():
 same='2026-10-09T13:20:02.000000000+00:00'
 v=payload(frames=(frame(events=[event(),event(t=same)]),))
 assert 'DUPLICATE_STATUS_MESSAGE' in v['issues'] and 'CONFLICTING_STATUS_TIME' not in v['issues']
 assert v['latest_observed_status']=='HALTED'
 assert v['events'][0]['normalized_message_sha256']!=v['events'][1]['normalized_message_sha256']


def test_equivalent_connection_instant_preserves_raw_spelling():
 p=plan();f=frame(p);other=replace(f,connected_at='2026-10-09T13:20:01.000000000+00:00',received_at=stamp(4))
 r=result(p,(f,other));raw=json.loads(r.evidence_bytes())
 assert raw['frames'][0]['connected_at']!=raw['frames'][1]['connected_at']
 assert 'STATUS_STREAM_RECONNECTED' not in r.to_payload()['issues']
