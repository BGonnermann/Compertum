"""Native stores/DPAPI; invented account origins, clocks and reserve capacity."""
import copy,hashlib,json
from uuid import uuid4
import pytest
from compertum.data.encoding import canonical
from compertum.runtime.errors import RuntimeRefused
from compertum.runtime.service_budget import queue_for
from test_execution_health import pair,connect
from test_paper_read_owner import owner
from test_paper_read_publication import publication
from test_paper_account_binding import invented_paper_origin,propose,confirm
from test_paper_presence import account,packet,acknowledge,advance
from test_paper_portfolio import order
from test_paper_read_preparation import ACCOUNT,KEY,SECRET


@pytest.fixture
def cancellation(request,monkeypatch):
    import test_paper_read_owner as fixture
    body=fixture.body;target=order(qty='1')
    def observed(operation):return [target] if operation=='ORDERS' else body(operation)
    monkeypatch.setattr(fixture,'body',observed)
    a=request.getfixturevalue('account');_,presence=acknowledge(a)
    return a,presence,target


def prepare(fixture,**changes):
    a,presence,target=fixture;o,_,read=a
    command=dict(operation='prepare',packet_id=read['packet_id'],presence_id=presence['presence_id'],
                 purpose='CANCEL',terms=dict(symbol=target['symbol'],order_id=target['id']))
    command.update(changes);p=packet(**command)
    return p,o.a.intent_handle(p)


def inspect(o,r):return o.a.intent_handle(packet('inspect',intent_id=r['intent_id']))


def confirm_intent(o,r,**changes):
    values=dict(intent_id=r['intent_id'],intent_sha256=r['intent_sha256']);values.update(changes)
    p=packet('confirm',**values);return p,o.a.intent_handle(p)


def test_cancel_records_exact_observed_target_without_market_or_broker_effects(cancellation):
    a,presence,target=cancellation;o,_,read=a;calls=len(o.calls);quota=queue_for(o.e.lease).status()
    p,r=prepare(cancellation);v=inspect(o,r)
    assert r['intent_id']==p['request_id'] and r['status']=='INTENT_RECORDED'
    assert r['current_validity']=='NOT_ASSERTED' and v['intent_status']=='CURRENT_UNCONFIRMED'
    assert r['purpose']=='CANCEL' and r['terms']==dict(symbol=target['symbol'],order_id=target['id'])
    _,confirmation=confirm_intent(o,r);v=inspect(o,r)
    assert v['intent_status']=='CURRENT_CONFIRMED' and v['order_admission']=='BLOCKED'
    assert {'OWNERSHIP_UNVERIFIED','TARGET_RECONCILIATION_UNVERIFIED','ECONOMIC_RECONCILIATION_UNVERIFIED','EXACT_CONSUMPTION_UNVERIFIED'}<=set(v['unverified_requirements'])
    for value in (r,confirmation,v):
        assert value['transport_authorized'] is value['financial_accepted'] is False
        assert all(s not in json.dumps(value) for s in (ACCOUNT,KEY,SECRET))
    assert o.a._market is None and len(o.calls)==calls and queue_for(o.e.lease).status()==quota
    assert o.a.db.execute("SELECT 1 FROM sqlite_master WHERE name='fake_intents'").fetchone() is None
    stored=json.loads(o.a.db.execute('SELECT body FROM paper_native_intents WHERE intent_id=?',(r['intent_id'],)).fetchone()[0])
    assert stored['record_type']=='NativePaperIntent' and stored['presence_id']==presence['presence_id']
    observed=[row for _,body in o.a._preflight._records for p in [json.loads(body)] if p['operation']=='ORDERS' for row in p['observation']['rows'] if row['id']==target['id']]
    assert len(observed)==1
    assert stored['packet_id']==read['packet_id'] and stored['target_observation_sha256']==hashlib.sha256(canonical(observed[0])).hexdigest()


def test_duplicate_intent_and_confirmation_return_original_historical_receipts(cancellation):
    o=cancellation[0][0];p,r=prepare(cancellation);q,c=confirm_intent(o,r);changes=o.a.db.total_changes
    advance(o,5)
    assert o.a.intent_handle(p)==r and o.a.intent_handle(q)==c and o.a.db.total_changes==changes
    advance(o,26)
    assert inspect(o,r)['intent_status']=='INVALIDATED'
    assert o.a.intent_handle(p)==r and o.a.intent_handle(q)==c


@pytest.mark.parametrize('field',['subject','purpose','terms','packet_id','presence_id'])
def test_request_identity_cannot_be_reused_with_different_intent(cancellation,field):
    o=cancellation[0][0];p,r=prepare(cancellation);bad=copy.deepcopy(p)
    if field=='subject':bad['subject_key']='b'*64
    elif field=='purpose':bad['command'][field]='CLOSE_LONG'
    elif field=='terms':bad['command'][field]['symbol']='MSFT'
    else:bad['command'][field]=str(uuid4())
    with pytest.raises(RuntimeRefused):o.a.intent_handle(bad)
    assert o.a.intent_handle(p)==r


@pytest.mark.parametrize('change',[{'quantity':1},{'limit_price':'1'},{'confirmed':True},{'target_observation_sha256':'a'*64},
                                 {'symbol':'aapl'},{'symbol':''},{'order_id':True},{'order_id':''},
                                 {'order_id':'b72b81ab-7e3c-4d7a-84ce-34fe9affd3c2'},{'symbol':'MSFT'}])
def test_cancel_rejects_unqualified_or_cross_purpose_terms(cancellation,change):
    target=cancellation[2];terms=dict(symbol=target['symbol'],order_id=target['id']);terms.update(change)
    with pytest.raises(RuntimeRefused):prepare(cancellation,terms=terms)


@pytest.mark.parametrize('change',[{'fresh_job_id':str(uuid4())},{'created_at':'2023-11-24T14:30:00Z'},
                                 {'expires_at':'2099-01-01T00:00:00Z'},{'account_id':ACCOUNT},{'transport_authorized':True}])
def test_caller_cannot_supply_clock_identity_or_authority(cancellation,change):
    with pytest.raises(RuntimeRefused):prepare(cancellation,**change)


@pytest.mark.parametrize('fault',['subject','hash','intent'])
def test_confirmation_binds_exact_original_intent_and_operator(cancellation,fault):
    o=cancellation[0][0];_,r=prepare(cancellation)
    values=dict(intent_id=r['intent_id'],intent_sha256=r['intent_sha256']);subject='a'*64
    if fault=='subject':subject='b'*64
    elif fault=='hash':values['intent_sha256']='0'*64
    else:values['intent_id']=str(uuid4())
    with pytest.raises(RuntimeRefused):o.a.intent_handle(packet('confirm',subject=subject,**values))
    assert inspect(o,r)['intent_status']=='CURRENT_UNCONFIRMED'


def test_confirmation_does_not_extend_original_deadline(cancellation):
    from compertum.paper_contracts import timestamp
    o=cancellation[0][0];_,r=prepare(cancellation);advance(o,5);_,c=confirm_intent(o,r)
    assert c['expires_at']==r['expires_at']
    assert 0<(timestamp(r['expires_at'])-timestamp(r['created_at'])).total_seconds()<=60
    advance(o,26);assert inspect(o,r)['intent_status']=='INVALIDATED'


@pytest.mark.parametrize('fault',['context','replacement','presence','owner','health','service_gap','reverse','drift'])
def test_original_context_lifetime_and_clock_faults_permanently_invalidate(cancellation,fault):
    o=cancellation[0][0];_,r=prepare(cancellation);_,_=confirm_intent(o,r);utc,mono=o.clock.utc,o.clock.mono
    if fault=='context':o.a._account_context.close()
    elif fault=='replacement':o.a.account_context(subject='a'*64,packet_id=cancellation[0][2]['packet_id'])
    elif fault=='presence':o.a._presence.close()
    elif fault=='owner':o.a.close();o.a=o.module.PaperReadOwner(o.a.store,o.a.reserve,o.e)
    elif fault=='health':o.e.halt('INVENTED_INTENT_HEALTH_LOSS')
    elif fault=='service_gap':o.clock.utc+=16;o.clock.mono+=16
    elif fault=='reverse':o.clock.utc-=1;o.clock.mono-=1
    else:o.clock.utc+=6
    assert inspect(o,r)['intent_status']=='INVALIDATED'
    o.clock.utc,o.clock.mono=utc,mono
    assert inspect(o,r)['intent_status']=='INVALIDATED'


def test_confirmation_cannot_be_replaced_by_second_different_request(cancellation):
    o=cancellation[0][0];_,r=prepare(cancellation);p,c=confirm_intent(o,r)
    with pytest.raises(RuntimeRefused):confirm_intent(o,r)
    assert o.a.intent_handle(p)==c and inspect(o,r)['intent_status']=='CURRENT_CONFIRMED'


def test_original_presence_can_bind_a_new_packet_of_the_same_account(cancellation):
    from test_paper_read_publication import launch
    from test_paper_account_binding import call
    a,presence,target=cancellation;o,pub,old=a;new=launch((o,pub,None))
    for _ in range(10):pub.tick()
    proposal=call(pub,new,'account_propose');confirm(pub,new,proposal)
    assert new['packet_id']!=presence['packet_id']
    _,r=prepare(((o,pub,new),presence,target));confirm_intent(o,r)
    assert inspect(o,r)['intent_status']=='CURRENT_CONFIRMED'
