"""Execution-owned synthetic packet sequencing; never contacts an account."""
import json,pickle
from uuid import UUID
import pytest
from compertum.runtime.errors import RuntimeRefused
from compertum.runtime.paper_read_packet import _ReadPacket
from compertum.runtime.paper_credentials import seal_paper_credentials
from compertum.runtime.owners import acquire_owner,release_owner,_LEASES
from compertum.runtime.identity import resolve_project
from test_paper_read_preparation import plan,ACCOUNT,KEY,SECRET
from test_paper_responses import account
from test_paper_portfolio import order,position

AT='2023-11-24T14:30:00Z'

@pytest.fixture
def owner(tmp_path):
    project=resolve_project(tmp_path);lease=acquire_owner(project,'execution')
    protected=seal_paper_credentials(lease,'fixture',bytearray(KEY.encode()),bytearray(SECRET.encode()))
    try:yield project,lease,protected
    finally:
        if lease in _LEASES:release_owner(lease)

def at(n):return f'2023-11-24T14:30:{n:02d}Z'
def packet(owner,**kw):
    project,lease,p=owner
    return _ReadPacket(lease,plan(project.project_id),p,started_at=kw.pop('started_at',AT),**kw)
def body(op):
    return {'ACCOUNT':account(),'CLOCK':dict(timestamp=AT,is_open=True,next_open='2023-11-27T14:30:00Z',next_close='2023-11-24T18:00:00Z'),'CALENDAR':[dict(date='2023-11-24',open='09:30',close='13:00')],'POSITIONS':[],'ORDERS':[]}[op]
def step(p,index,*,data=None,second=0):
    request=p.issue(now=at(second),request_id=str(UUID(int=index+1)))
    op=request.to_payload()['operation'];value=body(op) if data is None else data
    if op=='CLOCK' and data is None:value['timestamp']=at(second)
    p.accept(json.dumps(value).encode(),received_at=at(second))
    return request

def prefix(p,positions=None):
    for i in range(4):step(p,i,data=positions if i==3 else None)


def test_exact_empty_sequence_and_private_bootstrap(owner):
    p=packet(owner);ops=[]
    for i in range(6):
        r=step(p,i);ops.append(r.to_payload()['operation'])
        assert r.expected_account_id==(None if i==0 else ACCOUNT)
    assert ops==['ACCOUNT','CLOCK','CALENDAR','POSITIONS','ORDERS','CLOCK']
    v=p.status();assert v['state']=='PREPARATION_COMPLETE' and v['attempts']==6 and v['orders_coverage']=='OBSERVED_SHORT_TERMINAL_PAGE'
    assert v['positions']==v['orders']==0 and v['deficiencies']==[]
    assert v['native_transport_verified'] is v['financial_accepted'] is False and v['actual_flat'] is None
    assert ACCOUNT not in json.dumps(v) and ACCOUNT not in repr(p)
    assert len(p.private_evidence())==6
    with pytest.raises(RuntimeRefused):pickle.dumps(p)
    with pytest.raises(RuntimeRefused):p.issue(now=AT,request_id=str(UUID(int=99)))


def test_equal_submission_times_continue_from_exact_last_order(owner):
    p=packet(owner);prefix(p);first=[order(i) for i in range(25)];step(p,4,data=first)
    r=step(p,5,data=[order(25)]);assert r.to_payload()['parameters']['after_order_id']==first[-1]['id']
    step(p,6);v=p.status();assert v['attempts']==7 and v['orders']==26 and v['state']=='PREPARATION_COMPLETE'


def test_eight_full_pages_are_incomplete_and_stop_without_final_clock(owner):
    p=packet(owner);prefix(p)
    for page in range(8):step(p,4+page,data=[order(page*25+i) for i in range(25)])
    v=p.status();assert v['state']=='INCOMPLETE' and v['attempts']==12 and v['orders']==200 and v['orders_coverage']=='INCOMPLETE'
    assert v['reason']=='ORDER_PAGE_LIMIT'
    with pytest.raises(RuntimeRefused):p.issue(now=AT,request_id=str(UUID(int=100)))


def test_maximum_thirteen_attempts_with_short_eighth_page(owner):
    p=packet(owner);prefix(p)
    for page in range(8):step(p,4+page,data=[order(page*25+i) for i in range(25 if page<7 else 24)])
    step(p,12);assert p.status()['attempts']==13 and p.status()['state']=='PREPARATION_COMPLETE'


@pytest.mark.parametrize('kind',['oversize','duplicate','client_duplicate','backward','future','invalid_last','repeat_previous'])
def test_bad_page_is_retained_and_stops_coverage(owner,kind):
    p=packet(owner);prefix(p)
    rows=[order(i) for i in range(25)]
    if kind=='oversize':rows.append(order(25))
    elif kind=='duplicate':rows[-1]['id']=rows[0]['id']
    elif kind=='client_duplicate':rows[-1]['client_order_id']=rows[0]['client_order_id']
    elif kind=='backward':rows[-1]['submitted_at']='2023-11-24T14:28:00Z'
    elif kind=='future':rows[-1]['submitted_at']='2023-11-24T14:31:00Z'
    elif kind=='invalid_last':rows[-1]['id']='invalid'
    elif kind=='repeat_previous':
        step(p,4,data=rows);step(p,5,data=[rows[-1]]);rows=None
    if rows is not None:step(p,4,data=rows)
    v=p.status();assert v['state']=='INCOMPLETE' and v['orders_coverage']=='INCOMPLETE' and v['reason']=='ORDER_COVERAGE_INVALID'
    assert v['orders']>=25 and len(p.private_evidence())>=5


def test_unsupported_foreign_rows_remain_visible_without_clean_account_claim(owner):
    p=packet(owner);prefix(p,positions=[position(qty='0.5')]);step(p,4,data=[order(client_order_id='foreign',order_class='bracket')]);step(p,5)
    v=p.status();assert v['state']=='PREPARATION_COMPLETE' and v['positions']==v['orders']==1 and v['deficiencies'] and v['actual_flat'] is None


def test_pending_request_cannot_be_replaced_or_retried(owner):
    p=packet(owner);r=p.issue(now=AT,request_id=str(UUID(int=1)))
    with pytest.raises(RuntimeRefused,match='PAPER_PACKET_PENDING'):p.issue(now=AT,request_id=str(UUID(int=2)))
    assert p.status()['attempts']==1
    p.fail_pending();assert p.status()['reason']=='READ_ATTEMPT_FAILED'
    with pytest.raises(RuntimeRefused):p.issue(now=AT,request_id=str(UUID(int=3)))
    assert p.status()['attempts']==1


def test_reply_without_pending_request_is_refused(owner):
    p=packet(owner)
    with pytest.raises(RuntimeRefused):p.accept(b'{}',received_at=AT)
    assert p.status()['attempts']==0


def test_changed_credential_envelope_is_detected(owner):
    p=packet(owner);p.issue(now=AT,request_id=str(UUID(int=1)))
    _,lease,_=owner;p._protected=seal_paper_credentials(lease,'fixture',bytearray(KEY.encode()),bytearray(SECRET.encode()))
    with pytest.raises(RuntimeRefused):p.accept(json.dumps(account()).encode(),received_at=AT)
    assert p.status()['state']=='ABORTED' and p.status()['reason']=='PRIVATE_CONTEXT_CHANGED'


@pytest.mark.parametrize('kind',['elapsed','backward','midnight','duplicate_request'])
def test_invalid_dispatch_aborts_without_new_attempt(owner,kind):
    p=packet(owner);step(p,0);now={'elapsed':at(30),'backward':'2023-11-24T14:29:59Z','midnight':'2023-11-25T05:00:00Z','duplicate_request':AT}[kind]
    with pytest.raises(RuntimeRefused):p.issue(now=now,request_id=str(UUID(int=1 if kind=='duplicate_request' else 2)))
    assert p.status()['state']=='ABORTED' and p.status()['attempts']==1


def test_delayed_reply_then_earlier_dispatch_is_refused(owner):
    p=packet(owner);p.issue(now=AT,request_id=str(UUID(int=1)));p.accept(json.dumps(account()).encode(),received_at=at(4))
    with pytest.raises(RuntimeRefused):p.issue(now=at(3),request_id=str(UUID(int=2)))


def test_monotonic_deadline_cannot_be_evaded_by_frozen_wall_clock(owner,monkeypatch):
    import compertum.runtime.paper_read_packet as module
    clock=[10.0];monkeypatch.setattr(module.time,'monotonic',lambda:clock[0]);p=packet(owner);clock[0]=40.0
    with pytest.raises(RuntimeRefused):p.issue(now=AT,request_id=str(UUID(int=1)))
    assert p.status()['reason']=='PACKET_DEADLINE' and p.status()['attempts']==0


@pytest.mark.parametrize('clock_at',[at(0),at(7)])
def test_final_clock_stale_or_ahead_is_incomplete(owner,clock_at):
    p=packet(owner);prefix(p);step(p,4)
    value=body('CLOCK');value['timestamp']=clock_at;step(p,5,data=value,second=6)
    assert p.status()['state']=='INCOMPLETE' and p.status()['reason']=='FINAL_CLOCK_INVALID'


def test_secret_reflection_aborts_without_retaining_failed_reply(owner):
    p=packet(owner);p.issue(now=AT,request_id=str(UUID(int=1)))
    with pytest.raises(RuntimeRefused):p.accept(json.dumps(account(extra=SECRET)).encode(),received_at=AT)
    assert p.status()['state']=='ABORTED' and p.status()['responses']==0 and p.private_evidence()==()
    assert SECRET not in json.dumps(p.status())


def test_release_clears_private_records_and_forbids_further_use(owner):
    p=packet(owner);step(p,0);release_owner(owner[1])
    assert p._closed and p._records==[] and p._account_id is None and p._protected is None
    with pytest.raises(RuntimeRefused):p.status()


def test_cancel_clears_pending_and_records(owner):
    p=packet(owner);step(p,0);p.issue(now=AT,request_id=str(UUID(int=2)));p.cancel()
    assert p.status()['state']=='ABORTED' and p.status()['reason']=='OPERATOR_CANCELED' and p.private_evidence()==()
    assert p._pending is None


def test_one_packet_per_execution_owner(owner):
    p=packet(owner)
    with pytest.raises(RuntimeRefused,match='PAPER_PACKET_CAPACITY'):packet(owner)
    p.close();another=packet(owner);another.close()


def test_close_serializes_with_inflight_qualification(owner,monkeypatch):
    import threading
    import compertum.runtime.paper_read_packet as module
    p=packet(owner);p.issue(now=AT,request_id=str(UUID(int=1)))
    entered=threading.Event();resume=threading.Event();close_started=threading.Event();closed=threading.Event();errors=[]
    original=module.qualify_read_reply
    def held(*a,**kw):
        entered.set();assert resume.wait(2);return original(*a,**kw)
    def accept():
        try:p.accept(json.dumps(account()).encode(),received_at=AT)
        except Exception as e:errors.append(type(e).__name__)
    def close():close_started.set();p.close();closed.set()
    monkeypatch.setattr(module,'qualify_read_reply',held)
    worker=threading.Thread(target=accept);closer=threading.Thread(target=close);worker.start()
    try:
        assert entered.wait(2);closer.start();assert close_started.wait(2);closed.wait(.05)
    finally:
        resume.set();worker.join(2)
        if closer.ident is not None:closer.join(2)
    assert not worker.is_alive() and not closer.is_alive() and errors==[]
    assert p._closed and p._records==[] and p._account_id is None


@pytest.mark.parametrize('operation',['cancel','close','release'])
def test_cleanup_clears_all_retained_provider_identifiers(owner,operation):
    p=packet(owner);prefix(p);step(p,4,data=[order(i) for i in range(25)])
    assert p._cursor and p._order_ids and p._client_ids
    if operation=='release':release_owner(owner[1])
    else:getattr(p,operation)()
    assert not p._order_ids and not p._client_ids and p._cursor is None


@pytest.mark.parametrize('kind',['decreasing','future'])
def test_nanosecond_order_violation_is_not_rounded_away(owner,kind):
    p=packet(owner);prefix(p)
    rows=[order(0,submitted_at='2023-11-24T14:29:00.000000002Z'),order(1,submitted_at='2023-11-24T14:29:00.000000001Z')]
    if kind=='future':rows=[order(submitted_at='2023-11-24T14:30:00.000000001Z')]
    step(p,4,data=rows)
    assert p.status()['state']=='INCOMPLETE' and p.status()['reason']=='ORDER_COVERAGE_INVALID'


def test_valid_nanosecond_order_times_remain_supported(owner):
    p=packet(owner);prefix(p);step(p,4,data=[order(0,submitted_at='2023-11-24T14:29:00.000000001Z'),order(1,submitted_at='2023-11-24T09:29:00.000000002-05:00')]);step(p,5)
    assert p.status()['state']=='PREPARATION_COMPLETE'


@pytest.mark.parametrize('field',['started_at','now','received_at'])
def test_local_execution_timestamps_cannot_silently_lose_precision(owner,field):
    value='2023-11-24T14:30:00.000000001Z'
    with pytest.raises(RuntimeRefused):
        if field=='started_at':packet(owner,started_at=value)
        else:
            p=packet(owner);p.issue(now=value if field=='now' else AT,request_id=str(UUID(int=1)))
            if field=='received_at':p.accept(json.dumps(account()).encode(),received_at=value)


def test_final_clock_one_nanosecond_ahead_is_incomplete(owner):
    p=packet(owner);prefix(p);step(p,4);value=body('CLOCK');value['timestamp']='2023-11-24T14:30:00.000000001Z';step(p,5,data=value)
    assert p.status()['state']=='INCOMPLETE' and p.status()['reason']=='FINAL_CLOCK_INVALID'
