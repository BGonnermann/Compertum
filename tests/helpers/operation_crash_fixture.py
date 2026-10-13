"""Actual process exits; native owners/SQLite, explicitly simulated reserve capacity."""
import json,os,sys,time
from datetime import timedelta
from compertum.execution_contracts import instant
from pathlib import Path
from uuid import uuid4
sys.path.insert(0,str(Path(__file__).parents[1]))
from test_execution_authority import packet,profile
from compertum.runtime.identity import resolve_project
from compertum.runtime.owners import acquire_owner,release_owner
from compertum.runtime.execution_health import MutualHealth
from compertum.persistence import open_store
from compertum.storage import create_journal_reserve,open_journal_reserve
from compertum.deterministic_broker import DeterministicBroker
from compertum.fake_economic_opening import provision_opening
from compertum.fake_execution_journal import FakeIntentJournal
from compertum.fake_execution_driver import FakeExecutionDriver
from compertum.execution_operation_owner import FakeOperationOwner
import compertum.execution_authority as module
root=Path(sys.argv[1]);mode=sys.argv[2];point=sys.argv[3]
project=resolve_project(root);e=acquire_owner(project,'execution');w=acquire_owner(project,'watchdog')
health=MutualHealth(e,lambda reason:None,required=True);peer=MutualHealth(w,lambda reason:None,required=False)
health.receive(peer.receipt());peer.receive(health.receipt())
store=open_store(e,'execution');reserve=open_journal_reserve(e) if (root/'state/execution-reserve.bin').exists() else create_journal_reserve(e,65536)
module.execution_durable=lambda *args:reserve.receipt()
a=module.ExecutionAuthority(store,reserve,health)
def call(p):
    health.receive(peer.receipt());peer.receive(health.receipt());return a.handle(p)
try:
    if mode=='crash':
        b=DeterministicBroker(root/'state/fake-broker',cash='5500',positions={'AAPL':45});FakeIntentJournal(store);provision_opening(store,b,cash='5500',positions={'AAPL':45});b.close()
        call(packet('open_session',session_id=str(uuid4()),profile=profile()));call(packet('supervise'))
        saved=call(packet('prepare_plan',kind='CLOSE_LONG'));args=dict(plan_id=saved['plan_id'],plan_sha256=saved['plan_sha256'])
        call(packet('approve_plan',**args));call(packet('start_plan',**args));request=packet('advance_plan',**args)
        with (root/'fixture.json').open('w',encoding='utf-8') as f:json.dump(dict(args=args,request=request,point=point,anchor_utc=a._read_state()['anchor_utc']),f);f.flush();os.fsync(f.fileno())
        target,method={'prepared':(FakeOperationOwner,'_prepare'),'attempted':(FakeIntentJournal,'begin_attempt'),'accepted':(DeterministicBroker,'submit'),'completed':(FakeOperationOwner,'_complete')}[point]
        original=getattr(target,method)
        def crash(*args,**kwargs):original(*args,**kwargs);os._exit(23)
        setattr(target,method,crash);call(request);raise AssertionError('crash boundary not reached')
    value=json.loads((root/'fixture.json').read_text(encoding='utf-8'));old=call(value['request'])
    assert old['status']==('PENDING' if point=='completed' else 'PENDING_UNCONFIRMED')
    resumed=profile();resumed['fixture_at']=(instant(resumed['fixture_at'])+timedelta(seconds=time.time()-value['anchor_utc'])).isoformat()
    call(packet('open_session',session_id=str(uuid4()),profile=resumed));call(packet('supervise'))
    result=call(packet('reconcile_plan',**value['args']))
    b=DeterministicBroker(root/'state/fake-broker',create=False)
    try:snapshot=b.snapshot()
    finally:b.close()
    answer=dict(point=point,result=result,submissions=sum(v['kind']=='SUBMIT' for v in snapshot['calls']),acceptances=len(snapshot['orders']),positions=snapshot['positions'],simulated_reserve_capacity=True,actual_process_exit=True)
    print(json.dumps(answer),flush=True)
finally:release_owner(w);release_owner(e)
