"""Explicit future rejection can resolve uncertainty without inventing earlier history."""
import json
import pytest
from compertum.runtime.errors import RuntimeRefused
from test_fixture_order_source import source,record,execute
from test_fixture_order_journal import example,decode,changed

def reject(f,value):
 return f.orders.reject_unseen(client_id=value['client_order_id'],expected_heads=(f.economic._head,f.orders.snapshot()['journal_sha256']))

def test_late_explicit_rejection_preserves_the_original_unseen_attempt(source):
 value=record(source);source.clock.value='2026-10-17T19:02:00Z'
 status,raw=reject(source,value);assert status==200 and json.loads(raw)['status']=='rejected'
 current=source.orders.snapshot();assert current['transactions'][0]['at']==source.clock()
 assert current['attempts']==[value] and current['inventory']['positions']==[] and current['cash_delta']=='0'
 before=source.orders.path.read_bytes();assert execute(source,value)==(status,raw) and source.orders.path.read_bytes()==before

def test_late_cancel_rejection_keeps_the_original_resting_order(source):
 _,raw=execute(source,record(source,resting=True));order=json.loads(raw)
 cancel=record(source,cancel=order['id']);source.clock.value='2026-10-17T19:02:00Z'
 assert reject(source,cancel)[0]==409
 observed=source.orders.observations();assert observed['orders'][0]['status']=='new' and observed['cash']=='1000'
 assert source.orders.snapshot()['request_outcomes'][cancel['intent']['intent_id']]=='REJECTED'

def test_rejection_never_rewrites_an_already_accepted_effect(source):
 value=record(source);reply=execute(source,value);before=source.orders.path.read_bytes()
 source.clock.value='2026-10-17T19:02:00Z'
 assert reject(source,value)==reply and source.orders.path.read_bytes()==before

def test_late_acceptance_is_still_refused():
 raw,_,_=example(resting=True)
 raw=changed(raw,lambda tx:tx.update(at='2026-10-17T19:02:00Z'))
 with pytest.raises(RuntimeRefused):decode(raw)

def test_rejection_requires_current_exact_heads_and_no_quote(source):
 value=record(source);source.clock.value='2026-10-17T19:02:00Z'
 before=source.orders.path.read_bytes()
 with pytest.raises(RuntimeRefused):source.orders.reject_unseen(client_id=value['client_order_id'],expected_heads=('f'*64,'f'*64))
 assert source.orders.path.read_bytes()==before
 source.orders.quotes=lambda:pytest.fail('rejection requested a quote')
 assert reject(source,value)[0]==200
