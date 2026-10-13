"""Native owner crash/restart; real1GiBreserve, explicitly accelerated fixture clock."""
import json,os,sys
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
import compertum
sys.path.insert(0,str(Path.cwd()/'tests'))
from test_execution_authority import packet,profile,advance
from compertum.runtime.identity import resolve_project
from compertum.runtime.owners import acquire_owner,release_owner
from compertum.runtime.execution_health import MutualHealth
from compertum.persistence import open_store
from compertum.storage import create_journal_reserve,open_journal_reserve
from compertum.deterministic_broker import DeterministicBroker
from compertum.fake_economic_opening import provision_opening
from compertum.fake_execution_journal import FakeIntentJournal
import compertum.execution_authority as module
import compertum.runtime.execution_health as health_module
root=Path(sys.argv[1]).resolve();mode=sys.argv[2]
assert '.cache' in root.parts and 'test-runs' in root.parts and mode in {'create','recover'}
project=resolve_project(root);e=acquire_owner(project,'execution');w=acquire_owner(project,'watchdog')
if mode=='create':
    c=SimpleNamespace(mono=100.0,utc=1000.0)
    module.time=SimpleNamespace(monotonic=lambda:c.mono,time=lambda:c.utc)
    health_module.time=module.time
health=MutualHealth(e,lambda reason:None,required=True);peer=MutualHealth(w,lambda reason:None,required=False)
health.receive(peer.receipt());peer.receive(health.receipt());store=open_store(e,'execution')
reserve=create_journal_reserve(e,1024**3) if mode=='create' else open_journal_reserve(e)
a=module.ExecutionAuthority(store,reserve,health)
def call(p):
    health.receive(peer.receipt());peer.receive(health.receipt());return a.handle(p)
try:
    if mode=='create':
        b=DeterministicBroker(root/'state/fake-broker',cash='5500',positions={'AAPL':45});FakeIntentJournal(store);opening=provision_opening(store,b,cash='5500',positions={'AAPL':45});b.close()
        call(packet('open_session',session_id=str(uuid4()),profile=profile()));call(packet('supervise'))
        saved=call(packet('prepare_plan',kind='CLOSE_LONG'));args=dict(plan_id=saved['plan_id'],plan_sha256=saved['plan_sha256'])
        call(packet('approve_plan',**args));call(packet('start_plan',**args))
        submit=DeterministicBroker.submit
        DeterministicBroker.submit=lambda self,intent,**kw:submit(self,intent,outcome='TIMEOUT_BEFORE_ACCEPT')
        call(packet('advance_plan',**args));prior=0
        for seconds in (0,2,5,10,20,30,120):
            advance(a,health,peer,c,seconds-prior);prior=seconds;request=packet('advance_plan',**args);warning=call(request)
        assert warning['reason']=='UNRESOLVED_LIMIT' and warning['operator_action_required'] is True
        b=DeterministicBroker(root/'state/fake-broker',create=False)
        try:snapshot=b.snapshot()
        finally:b.close()
        assert len(snapshot['calls'])==7 and len(snapshot['orders'])==0
        proof=dict(args=args,request=request,warning=warning,calls=snapshot['calls'],reserve=reserve.receipt(),opening=opening,package_origin=str(Path(compertum.__file__).resolve()),accelerated_fixture_clock=True)
        with (root/'incident-fixture.json').open('x',encoding='utf-8') as f:json.dump(proof,f);f.flush();os.fsync(f.fileno())
        os._exit(23)
    proof=json.loads((root/'incident-fixture.json').read_text(encoding='utf-8'))
    assert call(proof['request'])==proof['warning']
    visible=call(packet('operation_status',plan_id=proof['args']['plan_id']))['intents'][0]
    assert visible['reason']=='UNRESOLVED_LIMIT' and visible['incident_started_at']==proof['warning']['incident_started_at']
    assert a.status()['halted'] and not a.status()['armed'] and not a.status()['supervised']
    b=DeterministicBroker(root/'state/fake-broker',create=False)
    try:assert b.snapshot()['calls']==proof['calls']
    finally:b.close()
    print(json.dumps(dict(actual_process_restart=True,exact_replay=True,status=visible,package_origin=str(Path(compertum.__file__).resolve()),reserve=reserve.receipt())),flush=True)
finally:release_owner(w);release_owner(e)
