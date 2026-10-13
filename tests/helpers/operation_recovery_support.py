"""Recovery-only native fixture support. Independent invented broker, no transport."""
import json,sys,time
from pathlib import Path
from datetime import timedelta
from uuid import uuid4
sys.path.insert(0,str(Path(__file__).parents[1]))
from test_execution_authority import packet,profile
from compertum.execution_authority import ExecutionAuthority
from compertum.execution_operation_owner import FakeOperationOwner
from compertum.runtime.execution_health import MutualHealth
from compertum.runtime.errors import RuntimeRefused
from compertum.execution_contracts import instant
from compertum.deterministic_broker import DeterministicBroker
from compertum.fake_economic_opening import provision_opening
from compertum.fake_execution_journal import FakeIntentJournal
from compertum.persistence import open_store
from compertum.runtime.owners import acquire_owner,release_owner
from compertum.storage import open_journal_reserve


def owner(leases,store,reserve):
    health=MutualHealth(leases['execution'],lambda reason:None,required=True)
    peer=MutualHealth(leases['watchdog'],lambda reason:None,required=False)
    health.receive(peer.receipt());peer.receive(health.receipt())
    a=ExecutionAuthority(store,reserve,health)
    def call(p):
        health.receive(peer.receipt());peer.receive(health.receipt());return a.handle(p)
    return a,call


def prepare(root,leases,stores,reserve,collect):
    b=DeterministicBroker(root/'state/fake-broker',cash='5500',positions={'AAPL':45});FakeIntentJournal(stores['execution']);provision_opening(stores['execution'],b,cash='5500',positions={'AAPL':45});b.close()
    a,call=owner(leases,stores['execution'],reserve);p=profile()
    call(packet('open_session',session_id=str(uuid4()),profile=p));call(packet('supervise'))
    saved=call(packet('prepare_plan',kind='CLOSE_LONG'));args=dict(plan_id=saved['plan_id'],plan_sha256=saved['plan_sha256'])
    call(packet('approve_plan',**args));call(packet('start_plan',**args))
    request=packet('advance_plan',**args);original=FakeOperationOwner._prepare;held={}
    def checkpoint(self,*values):
        pending=original(self,*values);held['before']=collect();return pending
    FakeOperationOwner._prepare=checkpoint
    try:accepted=call(request)
    finally:FakeOperationOwner._prepare=original
    assert accepted['status']=='PENDING' and accepted['quantity']==19
    value=dict(args=args,request=request,accepted=accepted,profile=p,anchor_utc=a._read_state()['anchor_utc'])
    (root/'operation-fixture.json').write_text(json.dumps(value),encoding='utf-8')
    return value,held['before']


def reconcile(root,project):
    value=json.loads((root/'operation-fixture.json').read_text(encoding='utf-8'))
    leases={r:acquire_owner(project,r) for r in ('execution','watchdog')}
    try:
        store=open_store(leases['execution'],'execution');reserve=open_journal_reserve(leases['execution'])
        a,call=owner(leases,store,reserve)
        retried=call(value['request']);assert retried['status']=='PENDING_UNCONFIRMED'
        p=value['profile'];p['fixture_at']=(instant(p['fixture_at'])+timedelta(seconds=time.time()-value['anchor_utc']+180)).isoformat()
        call(packet('open_session',session_id=str(uuid4()),profile=p));call(packet('supervise'))
        try:call(packet('advance_plan',**value['args']))
        except RuntimeRefused as error:assert error.code=='PLAN_CONTEXT_CHANGED'
        else:raise AssertionError('Restored plan gained dispatch authority')
        a.plan_owner.observations.read();j=a.plan_owner.observations.journal;key=value['accepted']['intent_id']
        row=j.read('fake-account',key);assert row['status']=='UNKNOWN'
        elapsed=j.reserve_poll('fake-account',key,now=a.require_supervised()['market_at'])
        assert elapsed['status']=='UNRESOLVED_LIMIT' and not elapsed['poll']
        b=a.plan_owner.observations.broker;snapshot=b.snapshot();order=snapshot['orders'][0]
        if order['status']!='FILLED':b.fill(order['order_id'],19,'100')
        calls=b.snapshot()['calls'];before=store.conn.execute('SELECT started_at,next_index,last_elapsed FROM fake_incidents').fetchone()
        request=packet('reconcile_plan',**value['args']);result=call(request)
        assert call(request)==result and b.snapshot()['calls']==calls
        after=store.conn.execute('SELECT started_at,next_index,last_elapsed,active FROM fake_incidents').fetchone()
        snapshot=b.snapshot();final=call(packet('reconcile_plan',**value['args']))
        return dict(result=result,final=final,original_retry=retried,before_incident=before,after_incident=after,
            acceptances=len(snapshot['orders']),submissions=sum(v['kind']=='SUBMIT' for v in snapshot['calls']),lookups=sum(v['kind']=='LOOKUP' for v in snapshot['calls']),
            cash=snapshot['cash'],positions=snapshot['positions'],armed=a.status()['armed'],actual_reserve=reserve.receipt())
    finally:
        for lease in reversed(list(leases.values())):release_owner(lease)
