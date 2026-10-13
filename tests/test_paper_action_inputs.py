"""Current action observations never certify action absence or historical availability."""
from dataclasses import replace
from datetime import timedelta
from decimal import localcontext, ROUND_DOWN
import hashlib,json
from uuid import UUID
import pytest
from compertum.data.calendar import session_times
from compertum.data.encoding import canonical
from compertum.domain import ContractError
from compertum.data.errors import DataError
from compertum.paper_market_inputs import prepare_market_plan
from compertum.paper_action_inputs import CurrentActionQuery, CurrentActionPage, CurrentActionInputs, prepare_action_query, qualify_action_inputs

DAY='2026-10-09'
def uid(n):return str(UUID(int=n))
def stamp(day=DAY,seconds=0):return (session_times(day).decision-timedelta(minutes=5)+timedelta(seconds=seconds)).isoformat().replace('+00:00','Z')
def query(day=DAY,symbol='AAPL'):
 p=prepare_market_plan(project_id='a'*64,account_alias='paper-primary',symbol=symbol,session_date=day,created_at=stamp(day))
 return prepare_action_query(p)
def event(**edit):
 v=dict(id='action-1',symbol='AAPL',cusip='037833100',process_date='2026-10-08',ex_date=DAY,record_date='2026-10-12',payable_date='2026-10-23',rate=0.25,foreign=False,special=False)
 v.update(edit);return v
def page(q=None,records=None,kind='cash_dividends',next_token=None,n=1,token=None,body=None,**edit):
 q=q or query();day=q.plan.to_payload()['session_date']
 value=dict(corporate_actions={kind:records if records is not None else [event()]},next_page_token=next_token) if body is None else body
 raw=json.dumps(value,separators=(',',':')).encode()
 values=dict(query=q,request_id=uid(n),page_token=token,requested_at=stamp(day,2*n),received_at=stamp(day,2*n+1),status=200,raw=raw)
 values.update(edit);return CurrentActionPage(**values)
def result(q=None,pages=None,as_of=None):
 q=q or query();return qualify_action_inputs(q,tuple([page(q)]) if pages is None else pages,as_of=as_of or stamp(q.plan.to_payload()['session_date'],60))
def payload(*args,**kw):return json.loads(result(*args,**kw).content)


def test_fixed_query_original_bytes_and_dated_event_remain_unqualified():
 q=query();p=page(q);r=result(q,(p,));v=json.loads(r.content)
 request=p.request_payload()
 assert request['origin']=='https://data.alpaca.markets' and request['path']=='/v1/corporate-actions' and request['method']=='GET'
 assert request['parameters']['data_quality']=='all' and request['parameters']['limit']==100
 assert request['parameters']['start']==q.plan.to_payload()['history_sessions'][0]
 assert request['parameters']['end']==DAY
 assert v['query_pages_terminal'] is True and v['events'][0]['affects_session'] is True
 assert v['events'][0]['process_date']=='2026-10-08' and v['events'][0]['economic_date']==DAY
 assert v['status']=='BLOCKED' and v['current_action_coverage']=='UNVERIFIED'
 assert v['knowledge_timing']=='UNVERIFIED' and v['native_provenance']=='UNVERIFIED'
 assert v['financial_accepted'] is False and v['transport_authorized'] is False and v['research_eligible'] is False
 retained=json.loads(r.evidence_bytes())
 assert retained['responses'][0]['body_utf8'].encode()==p.raw
 assert v['evidence_sha256']==hashlib.sha256(r.evidence_bytes()).hexdigest()
 assert 'action-1' not in repr(p)


@pytest.mark.parametrize('records',[[],[event(ex_date='2026-10-15')]])
def test_empty_or_future_events_never_prove_no_current_action(records):
 v=payload(pages=(page(records=records),))
 assert v['query_pages_terminal'] is True and v['current_action_coverage']=='UNVERIFIED'
 assert 'ACTION_COVERAGE_UNVERIFIED' in v['issues']
 if records:assert v['events'][0]['affects_session'] is False


def test_pay_date_is_distinct_from_process_and_economic_date():
 v=payload(pages=(page(records=[event(ex_date='2026-09-18',payable_date=DAY)]),))
 e=v['events'][0];assert e['payable_date']==DAY and e['economic_date']=='2026-09-18' and e['affects_session'] is True


@pytest.mark.parametrize('changes,issue',[({'ex_date':None},'MISSING_EX_DATE'),({'payable_date':None},'MISSING_PAYABLE_DATE'),({'foreign':'yes'},'ACTION_FIELDS'),({'symbol':'MSFT'},'ACTION_SYMBOL_BINDING'),({'process_date':'2020-01-01'},'ACTION_PROCESS_WINDOW')])
def test_incomplete_or_foreign_events_are_retained(changes,issue):
 p=page(records=[event(**changes)]);r=result(pages=(p,));v=json.loads(r.content)
 assert len(v['events'])==1 and issue in v['events'][0]['issues']
 assert json.loads(r.evidence_bytes())['responses'][0]['body_utf8'].encode()==p.raw


def test_unsupported_and_unparsed_records_are_not_discarded():
 p=page(kind='reverse_splits',records=[event(),{'id':'unknown-2','process_date':DAY}]);v=payload(pages=(p,))
 assert len(v['events'])==2 and all('UNSUPPORTED_ACTION_TYPE' in e['issues'] for e in v['events'])
 assert v['events'][1]['affects_session'] is None


@pytest.mark.parametrize('change,expected',[({},'DUPLICATE_ACTION_ID'),({'rate':0.75},'CONFLICTING_ACTION_ID')])
def test_duplicate_ids_preserve_both_observations(change,expected):
 p=page(records=[event(),event(**change)]);v=payload(pages=(p,))
 assert len(v['events'])==2 and expected in v['issues']


def test_successful_linked_pages_and_terminal_chain():
 q=query();pages=(page(q,next_token='next'),page(q,n=2,token='next',records=[event(id='action-2')]))
 v=payload(q,pages)
 assert v['query_pages_terminal'] is True and len(v['events'])==2


@pytest.mark.parametrize('pages,issue',[((), 'ACTION_RESPONSES_MISSING'),((page(next_token='next'),),'ACTION_QUERY_INCOMPLETE'),((page(body={'corporate_actions':{}}),),'ACTION_TERMINAL_TOKEN_MISSING'),((page(status=403,body={'message':'not allowed'}),),'ACTION_HTTP_REFUSED')])
def test_missing_denied_or_unfinished_queries_cannot_complete(pages,issue):
 v=payload(pages=pages);assert v['query_pages_terminal'] is False and issue in v['issues']


def test_bad_token_chain_and_extra_page_after_terminal_refused():
 q=query()
 with pytest.raises(ContractError):result(q,(page(q,token='unexpected'),))
 with pytest.raises(ContractError):result(q,(page(q,next_token='next'),page(q,n=2,token='other')))
 with pytest.raises(ContractError):result(q,(page(q),page(q,n=2)))
 with pytest.raises(ContractError):result(q,(page(q,next_token='next'),page(q,n=2,token='next',next_token='next')))


def test_page_cap_with_continuation_is_not_completed():
 q=query();pages=tuple(page(q,n=i+1,token=None if i==0 else str(i),next_token=str(i+1),records=[]) for i in range(8))
 assert payload(q,pages)['query_pages_terminal'] is False
 with pytest.raises(ContractError):result(q,pages+(page(q,n=9,token='8'),))


def test_late_receipt_cannot_rewrite_earlier_evidence_and_ns_boundary_is_exact():
 q=query();cutoff=q.plan.to_payload()['history_cutoff_at']
 before=page(q,requested_at=stamp(seconds=295),received_at=cutoff)
 earlier=result(q,(before,),as_of=cutoff)
 after=replace(before,received_at=cutoff.replace('Z','.000000001Z'))
 late=result(q,(after,),as_of=stamp(seconds=301))
 assert 'ACTION_RECEIVED_AFTER_CUTOFF' not in json.loads(earlier.content)['issues']
 assert 'ACTION_RECEIVED_AFTER_CUTOFF' in json.loads(late.content)['issues']
 assert result(q,(before,),as_of=cutoff)==earlier and late!=earlier


@pytest.mark.parametrize('day',['2026-03-09','2026-11-27'])
def test_dst_and_early_close_queries_use_pinned_sessions(day):
 q=query(day);p=page(q,records=[]);assert payload(q,(p,))['query_pages_terminal'] is True


@pytest.mark.parametrize('edit',[{'status':True},{'request_id':uid(0)},{'received_at':'2026-10-09T13:20:12.000000001Z'},{'received_at':'2026-10-08T13:20:03Z'},{'page_token':[]},{'raw':b'{"corporate_actions":{},"corporate_actions":{}}'},{'raw':b'{"x":NaN}'},{'raw':b'[]'},{'raw':b'x'*65537}],ids=['bool','uuid','deadline','day','token','duplicate','nonfinite','root','oversize'])
def test_bounded_response_rejections(edit):
 with pytest.raises(ContractError):page(**edit)


def test_request_and_result_binding_cannot_be_forged():
 q=query();other=query(symbol='MSFT')
 with pytest.raises(ContractError):result(q,(page(other,records=[]),))
 v=q.to_payload();v['parameters']['end']='2024-01-01'
 with pytest.raises(ContractError):CurrentActionQuery(q.plan,canonical(v))
 r=result(q);v=json.loads(r.content);v['current_action_coverage']='VERIFIED'
 with pytest.raises(ContractError):replace(r,content=canonical(v))
 with pytest.raises(ContractError):result(q,(page(q),),as_of=stamp(seconds=1))


def test_row_bound_and_historical_guard_stay_in_force():
 with pytest.raises(ContractError):result(pages=(page(records=[event(id='a'+str(i)) for i in range(101)]),))
 from compertum.data.actions import _profile
 with pytest.raises(DataError,match='PROTECTED_ACTION_DATE'):_profile(query().to_payload()['parameters'])


def test_replay_does_not_inherit_decimal_context():
 expected=result()
 with localcontext() as ctx:
  ctx.prec=2;ctx.rounding=ROUND_DOWN
  assert result()==expected

@pytest.mark.parametrize('records',[[None,42,[],{}],[event(process_date='not-a-date')],[event(ex_date='2026-02-30')]])
def test_malformed_records_remain_visible_with_unknown_session_effect(records):
 v=payload(pages=(page(records=records),))
 assert len(v['events'])==len(records)
 assert all(e['affects_session'] is None and e['issues'] for e in v['events'])


def test_unknown_group_names_cannot_hide_records_or_bypass_page_bound():
 p=page(kind='bad kind',records=[event()]);v=payload(pages=(p,))
 assert len(v['events'])==1 and 'ACTION_GROUP_FIELDS' in v['issues']
 with pytest.raises(ContractError):result(pages=(page(kind='bad kind',records=[event(id='a'+str(i)) for i in range(101)]),))


@pytest.mark.parametrize('body,issue',[
 ({'corporate_actions':{},'next_page_token':[]},'ACTION_TERMINAL_TOKEN_INVALID'),
 ({'corporate_actions':None,'next_page_token':None},'ACTION_RESPONSE_FIELDS'),
 ({'corporate_actions':{'cash_dividends':{}},'next_page_token':None},'ACTION_GROUP_FIELDS')])
def test_malformed_envelopes_preserved_but_query_not_complete(body,issue):
 p=page(body=body);r=result(pages=(p,));v=json.loads(r.content)
 assert not v['query_pages_terminal'] and issue in v['issues']
 assert json.loads(r.evidence_bytes())['responses'][0]['body_utf8'].encode()==p.raw


def test_prior_malformed_page_never_becomes_complete_at_terminal():
 q=query();v=payload(q,(page(q,body={'corporate_actions':None,'next_page_token':'next'}),page(q,n=2,token='next')))
 assert not v['query_pages_terminal'] and 'ACTION_QUERY_INCOMPLETE' in v['issues']


def test_process_order_uses_each_group_and_cross_page_range():
 q=query();first=page(q,next_token='next',records=[event(process_date='2026-10-08')])
 v=payload(q,(first,page(q,n=2,token='next',records=[event(id='a2',process_date='2026-10-07')])) )
 assert 'ACTION_PROCESS_ORDER' in v['issues'] and len(v['events'])==2
 v=payload(pages=(page(records=[event(process_date='2026-10-08'),event(id='a2',process_date='2026-10-07')]),))
 assert 'ACTION_PROCESS_ORDER' in v['events'][1]['issues']
 # Each group is sorted, but group boundaries do not imply record sort order.
 body={'corporate_actions':{'cash_dividends':[event()], 'reverse_splits':[event(id='s',process_date='2026-10-07')]},'next_page_token':None}
 assert 'ACTION_PROCESS_ORDER' not in payload(pages=(page(body=body),))['issues']


def test_duplicate_request_and_overlapping_request_times_refused():
 q=query();first=page(q,next_token='next')
 with pytest.raises(ContractError):result(q,(first,page(q,token='next')))
 with pytest.raises(ContractError):result(q,(first,page(q,n=2,token='next',requested_at=stamp(seconds=2))))
 with pytest.raises(ContractError):result(q,(),as_of=stamp(seconds=-1))
 with pytest.raises(ContractError):page(q,requested_at=stamp(seconds=-1))


def test_pay_and_economic_dates_must_both_be_known_before_false_session_effect():
 e=payload(pages=(page(records=[event(ex_date='2026-10-01',payable_date=None)]),))['events'][0]
 assert e['affects_session'] is None


def test_long_invalid_group_keeps_bounded_events_and_original_bytes():
 p=page(kind='x'*60000,records=[None]*100);r=result(pages=(p,));v=r.to_payload()
 assert len(v['events'])==100 and len(r.content)<1048576
 assert all(e['kind'] is None and e['kind_sha256']==hashlib.sha256(canonical('x'*60000)).hexdigest() and 'ACTION_GROUP_FIELDS' in e['issues'] for e in v['events'])
 assert json.loads(r.evidence_bytes())['responses'][0]['body_utf8'].encode()==p.raw
