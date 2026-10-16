"""Pure invented activity records. No native lifecycle or economic qualification."""
from copy import deepcopy
from dataclasses import replace
import json,pickle
from uuid import uuid4
import pytest
from compertum.data.encoding import canonical
from compertum.domain import ContractError
from compertum.runtime.errors import RuntimeRefused

START='2023-11-24T14:35:00Z'
UNTIL='2023-11-24T14:35:01Z'
ACCOUNT='10000000-0000-4000-8000-000000000001'
ORDER='10000000-0000-4000-8000-000000000002'


def module():
    from compertum import paper_activity_records
    return paper_activity_records


def values(**changes):
    return dict(project_id='a'*64,account_alias='fixture',opening_sha256='b'*64,
        account_context_sha256='c'*64,history_sha256='d'*64,credential_sha256='e'*64,
        expected_account_id=ACCOUNT,after=START,until=UNTIL,started_at=UNTIL,
        created_at=UNTIL,request_id=str(uuid4()),page_token=None,**changes)


def request(**changes):
    v=values();v.update(changes);return module().prepare_activity_request(**v)


def fill(index=1,**changes):
    row=dict(activity_type='FILL',id=f'opaque_{index}::{uuid4()}',order_id=ORDER,
        symbol='AAPL',side='buy',qty='1',cum_qty=str(index),leaves_qty=str(25-index),
        price='100',transaction_time=UNTIL,type='fill' if index==25 else 'partial_fill')
    row.update(changes);return row


def page(rows,req=None,received_at=UNTIL):
    return module().parse_activity_page(req or request(),canonical(rows),received_at=received_at)


def test_request_is_fixed_unfiltered_private_and_inert():
    r=request();v=r.to_payload()
    assert v['method']=='GET' and v['path']=='/v2/account/activities'
    assert v['parameters']==dict(after=START,until=UNTIL,direction='asc',page_size=25)
    assert 'activity_types' not in v['target'] and 'order_id' not in v['target'] and 'category' not in v['target']
    assert v['timeout_ms']==10000 and v['maximum_pages']==8 and v['packet_timeout_seconds']==20
    assert v['transport_authorized'] is v['financial_accepted'] is False
    assert ACCOUNT.encode() not in r.content and ACCOUNT not in repr(r)
    with pytest.raises(RuntimeRefused):pickle.dumps(r)


@pytest.mark.parametrize('field,bad',[
    ('project_id','bad'),('account_alias','bad alias'),('opening_sha256','x'*64),
    ('account_context_sha256','x'*64),('history_sha256','x'*64),('credential_sha256','x'*64),
    ('expected_account_id','bad'),('request_id','bad'),('page_token','../escape'),
    ('page_token','x'*129),('after',UNTIL),('until',START),
    ('started_at',START),('created_at','2023-11-24T14:35:21Z'),
])
def test_invalid_request_refuses(field,bad):
    with pytest.raises((ContractError,ValueError,RuntimeRefused)):request(**{field:bad})


@pytest.mark.parametrize('field,bad',[
    ('target','/v2/orders'),('method','POST'),('maximum_pages',9),('financial_accepted',True),
    ('timeout_ms',10001),('scope','NATIVE_OWNERSHIP'),
])
def test_changed_request_bytes_refuse(field,bad):
    r=request();v=r.to_payload();v[field]=bad
    with pytest.raises((ContractError,ValueError,RuntimeRefused)):replace(r,content=canonical(v))


def test_activity_token_is_opaque_and_encoded():
    r=request(page_token='not_a_date::opaque-id')
    assert r.to_payload()['parameters']['page_token']=='not_a_date::opaque-id'
    assert 'not_a_date%3A%3Aopaque-id' in r.to_payload()['target']


def test_fill_preserves_exact_economic_fields_without_authority():
    row=fill();p=page([row]);v=p.to_payload()
    assert v['rows']==[row]
    assert v['native_transport_verified'] is v['financial_accepted'] is v['transport_authorized'] is False
    assert v['raw_sha256']==module().sha(canonical([row]))
    assert ORDER not in repr(p)
    with pytest.raises(RuntimeRefused):pickle.dumps(p)


@pytest.mark.parametrize('field,bad',[
    ('order_id','bad'),('symbol','invalid symbol'),('side','short'),('qty','0'),('qty','NaN'),
    ('cum_qty','0'),('leaves_qty','-1'),('price','0'),('type','correction'),
    ('transaction_time','yesterday'),('id','invalid'),('activity_type','fill'),
])
def test_malformed_fill_refuses(field,bad):
    with pytest.raises((ContractError,ValueError,RuntimeRefused)):page([fill(**{field:bad})])


@pytest.mark.parametrize('raw',[
    b'{}',b'[1]',b'[{"id":"a::b","id":"c::d"}]',b'[NaN]',b' '*65537,
],ids=lambda value:'oversized_payload' if len(value)>65536 else None)
def test_invalid_reply_refuses(raw):
    with pytest.raises((ContractError,ValueError,RuntimeRefused)):
        module().parse_activity_page(request(),raw,received_at=UNTIL)


def test_duplicate_ids_and_oversized_page_refuse():
    row=fill()
    with pytest.raises((ContractError,ValueError,RuntimeRefused)):page([row,row])
    with pytest.raises((ContractError,ValueError,RuntimeRefused)):page([fill(i) for i in range(1,27)])


@pytest.mark.parametrize('at,accepted',[
    ('2023-11-24T14:35:11Z',True),('2023-11-24T14:35:11.001Z',False),
    ('2023-11-24T14:35:00Z',False),
])
def test_original_request_timeout(at,accepted):
    if accepted:assert page([],received_at=at).to_payload()['received_at']==at
    else:
        with pytest.raises((ContractError,ValueError,RuntimeRefused)):page([],received_at=at)


def test_unknown_activity_is_retained_and_cannot_close_liabilities():
    row=dict(id='opaque::fee',activity_type='FEE',date='2023-11-25',net_amount='-0.01')
    p=page([row]);v=module().activity_traversal((p,))
    assert p.to_payload()['rows']==[row]
    assert v['traversal_complete'] and v['unsupported_activities']==1
    assert {'FEE_LIABILITIES_UNVERIFIED','ACTION_EVIDENCE_UNVERIFIED','UNSUPPORTED_ACTIVITY'}<=set(v['deficiencies'])
    assert v['financial_accepted'] is v['transport_authorized'] is False


def test_empty_page_only_completes_traversal():
    v=module().activity_traversal((page([]),))
    assert v['traversal_complete'] and v['rows']==0
    assert {'NATIVE_PROVENANCE_UNVERIFIED','OWNERSHIP_UNVERIFIED','ECONOMIC_COVERAGE_UNVERIFIED',
        'FEE_LIABILITIES_UNVERIFIED','ACTION_EVIDENCE_UNVERIFIED'}<=set(v['deficiencies'])
    assert v['actual_flat'] is None and v['financial_accepted'] is v['transport_authorized'] is False


def full_page(req=None):return page([fill(i) for i in range(1,26)],req)


def test_exact_cursor_chain_and_short_terminal_page():
    first=full_page();last=first.to_payload()['rows'][-1]['id']
    second=page([],request(page_token=last));v=module().activity_traversal((first,second))
    assert v['traversal_complete'] and v['rows']==25 and v['pages']==2


@pytest.mark.parametrize('fault',['cursor','first_cursor','context','credential','opening','interval','duplicate_id','request_id','short_page',
    'project','alias','history','account','start'])
def test_substituted_or_incomplete_pagination_refuses(fault):
    first=full_page();r=first.request.to_payload();token=first.to_payload()['rows'][-1]['id']
    opts=dict(page_token=token);rows=[]
    if fault=='cursor':opts['page_token']='wrong::token'
    elif fault=='first_cursor':first=full_page(request(page_token='wrong::first'))
    elif fault=='context':opts['account_context_sha256']='f'*64
    elif fault=='credential':opts['credential_sha256']='f'*64
    elif fault=='opening':opts['opening_sha256']='f'*64
    elif fault=='interval':opts['after']='2023-11-24T14:34:59Z'
    elif fault=='duplicate_id':rows=[first.to_payload()['rows'][0]]
    elif fault=='request_id':opts['request_id']=r['request_id']
    elif fault=='project':opts['project_id']='f'*64
    elif fault=='alias':opts['account_alias']='other'
    elif fault=='history':opts['history_sha256']='f'*64
    elif fault=='account':opts['expected_account_id']=ORDER
    elif fault=='start':opts.update(started_at='2023-11-24T14:35:02Z',created_at='2023-11-24T14:35:02Z');rows=[]
    else:first=page([])
    with pytest.raises((ContractError,ValueError,RuntimeRefused)):
        req=request(**opts)
        module().activity_traversal((first,page(rows,req,received_at=req.to_payload()['created_at'])))


def test_full_last_page_is_incomplete():
    v=module().activity_traversal((full_page(),))
    assert not v['traversal_complete'] and 'ACTIVITIES_TRUNCATED' in v['deficiencies']


def test_empty_or_excessive_page_collection_refuses():
    with pytest.raises((ContractError,ValueError,RuntimeRefused)):module().activity_traversal(())
    with pytest.raises((ContractError,ValueError,RuntimeRefused)):module().activity_traversal((page([]),)*9)


def test_backdated_fill_is_observed_without_invented_creation_time():
    p=page([fill(transaction_time='2023-11-23T14:35:00Z')]);v=module().activity_traversal((p,))
    assert v['traversal_complete'] and 'ACTIVITY_TIME_OUTSIDE_QUERY_INTERVAL' in v['deficiencies']
    assert 'created_at' not in p.to_payload()['rows'][0]


def test_inputs_remain_unchanged():
    rows=[fill()];old=deepcopy(rows);r=request();raw=r.content
    p=page(rows,r);module().activity_traversal((p,))
    assert rows==old and r.content==raw


@pytest.mark.parametrize('received,accepted',[
    ('2023-11-24T14:35:20.999Z',True),('2023-11-24T14:35:21Z',False),
])
def test_whole_traversal_keeps_original_twenty_second_deadline(received,accepted):
    first=full_page();token=first.to_payload()['rows'][-1]['id']
    req=request(page_token=token,created_at='2023-11-24T14:35:20Z')
    if accepted:assert module().activity_traversal((first,page([],req,received_at=received)))['traversal_complete']
    else:
        with pytest.raises((ContractError,ValueError,RuntimeRefused)):page([],req,received_at=received)


def test_next_request_cannot_predate_previous_reply():
    first=page([fill(i) for i in range(1,26)],received_at='2023-11-24T14:35:03Z')
    token=first.to_payload()['rows'][-1]['id']
    with pytest.raises((ContractError,ValueError,RuntimeRefused)):
        module().activity_traversal((first,page([],request(page_token=token))))


@pytest.mark.parametrize('field,bad',[
    ('raw',b'[]'),('content',b'{}'),('received_at','2023-11-24T14:35:02Z'),
])
def test_changed_page_fields_refuse(field,bad):
    p=page([fill()])
    with pytest.raises((ContractError,ValueError,RuntimeRefused)):replace(p,**{field:bad})


def test_changed_page_request_and_foreign_objects_refuse():
    p=page([fill()])
    with pytest.raises((ContractError,ValueError,RuntimeRefused)):replace(p,request=request())
    class Foreign:
        def __post_init__(self):raise AssertionError('Foreign callback')
    with pytest.raises((ContractError,ValueError,RuntimeRefused)):module().activity_traversal((Foreign(),))


@pytest.mark.parametrize('change',[
    dict(qty='2',cum_qty='1'),dict(qty='1e2'),dict(qty='1'*65),dict(id='x'*129),
    dict(extra='unknown'),dict(type='fill',leaves_qty='1'),dict(type='partial_fill',leaves_qty='0'),
])
def test_unsupported_fill_shape_and_quantities_refuse(change):
    with pytest.raises((ContractError,ValueError,RuntimeRefused)):page([fill(**change)])


def test_missing_fill_field_refuses():
    row=fill();row.pop('order_id')
    with pytest.raises((ContractError,ValueError,RuntimeRefused)):page([row])


@pytest.mark.parametrize('side',['buy','sell'])
def test_complete_and_fractional_fill_observations_are_inert(side):
    from decimal import localcontext
    with localcontext() as arithmetic:
        arithmetic.prec=2
        p=page([fill(side=side,qty='0.25',cum_qty='0.25',leaves_qty='0',type='fill')])
        assert p.to_payload()['rows'][0]['qty']=='0.25'
        assert not module().activity_traversal((p,))['financial_accepted']


@pytest.mark.parametrize('at',[START,UNTIL])
def test_transaction_time_interval_equalities_are_observations_only(at):
    p=page([fill(transaction_time=at)])
    assert 'ACTIVITY_TIME_OUTSIDE_QUERY_INTERVAL' not in module().activity_traversal((p,))['deficiencies']


def test_unknown_uppercase_type_is_preserved_without_date_invention():
    row=dict(id='unknown::id',activity_type='FUTURE_ACTIVITY',details='invented')
    p=page([row]);v=module().activity_traversal((p,))
    assert p.to_payload()['rows']==[row] and v['unsupported_activities']==1
    assert 'UNSUPPORTED_ACTIVITY' in v['deficiencies'] and 'created_at' not in row


@pytest.mark.parametrize('row',[{},dict(id='bad',activity_type='FEE'),dict(id='good::id',activity_type=1)])
def test_malformed_unsupported_activity_refuses(row):
    with pytest.raises((ContractError,ValueError,RuntimeRefused)):page([row])


def test_fill_datetime_order_is_not_lexical_id_order():
    first=fill(id='zzz::one',transaction_time=START)
    second=fill(id='aaa::two',transaction_time=UNTIL)
    assert module().activity_traversal((page([first,second]),))['traversal_complete']
    with pytest.raises((ContractError,ValueError,RuntimeRefused)):
        module().activity_traversal((page([second,first]),))


def test_eighth_full_page_remains_truncated():
    pages=[];token=None
    for _ in range(8):
        p=full_page(request(page_token=token));pages.append(p);token=p.to_payload()['rows'][-1]['id']
    v=module().activity_traversal(tuple(pages))
    assert v['pages']==8 and v['rows']==200 and not v['traversal_complete']


@pytest.mark.parametrize('field,value',[
    ('request_id',ACCOUNT),('account_alias',ACCOUNT),('page_token','opaque::'+ACCOUNT),
])
def test_private_account_reflection_in_prepared_fields_refuses(field,value):
    with pytest.raises((ContractError,ValueError,RuntimeRefused)):request(**{field:value})


def test_private_account_substitution_refuses_unchanged_request_bytes():
    r=request()
    with pytest.raises((ContractError,ValueError,RuntimeRefused)):replace(r,expected_account_id=ORDER)


@pytest.mark.parametrize('at',['2023-11-24T14:35:11.000000001Z','2023-11-24T14:35:01.000000001Z'])
def test_local_reply_precision_refuses_before_normalization(at):
    with pytest.raises((ContractError,ValueError,RuntimeRefused)):page([],received_at=at)


def test_reversed_nanosecond_fill_order_refuses():
    rows=[fill(transaction_time='2023-11-24T14:35:00.000000002Z'),
        fill(transaction_time='2023-11-24T14:35:00.000000001Z')]
    with pytest.raises((ContractError,ValueError,RuntimeRefused)):module().activity_traversal((page(rows),))


def test_nanosecond_beyond_interval_keeps_economic_blocker():
    p=page([fill(transaction_time='2023-11-24T14:35:01.000000001Z')])
    assert 'ACTIVITY_TIME_OUTSIDE_QUERY_INTERVAL' in module().activity_traversal((p,))['deficiencies']


def test_nanosecond_fill_observations_preserve_exact_times():
    rows=[fill(id='zzz::first',transaction_time='2023-11-24T14:35:00.000000001Z'),
        fill(id='aaa::second',transaction_time='2023-11-24T14:35:00.000000002Z')]
    p=page(rows);v=module().activity_traversal((p,))
    assert p.to_payload()['rows']==rows
    assert v['traversal_complete'] and 'ACTIVITY_TIME_OUTSIDE_QUERY_INTERVAL' not in v['deficiencies']
