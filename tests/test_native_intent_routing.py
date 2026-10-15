"""Native identity/allowlist probes; intercepted before child startup."""
import json
from types import SimpleNamespace
from uuid import uuid4
import pytest
from compertum.runtime.errors import RuntimeRefused
from test_paper_presence import Decision
from test_execution_health import pair
from test_paper_read_owner import owner

def test_intent_route_forwards_only_authenticated_identity_and_never_enables_writes(owner,monkeypatch):
    from compertum.runtime import supervisor as module
    from compertum.runtime.bootstrap import validate_worker_commands
    from compertum.domain import capability_for
    assert 'paper_intent' in module.ACTIONS and capability_for('paper_intent').exit_code==0
    for action in ('paper.arm','paper.start','paper.cancel','paper.close'):assert capability_for(action).exit_code!=0
    for role in ('execution','watchdog','evaluation'):
        with pytest.raises(RuntimeRefused):validate_worker_commands(role,frozenset({'paper_intent'}))
    s=object.__new__(module.Supervisor);s.partial_fixture=False;s.execution=SimpleNamespace(remote=object());calls=[]
    monkeypatch.setattr(module,'call_owner',lambda remote,action,payload:calls.append((action,payload)))
    decision=Decision(str(uuid4()),'c'*64);command=dict(operation='inspect',intent_id=str(uuid4()))
    s._dispatch(decision,'paper_intent',command)
    assert calls==[('paper_intent',dict(request_id=decision.request_id,subject_key=decision.subject_key,command=command))]


def test_intent_inspection_is_never_cached(owner,monkeypatch):
    from compertum.runtime import supervisor as module
    o=owner;s=object.__new__(module.Supervisor);s.store=o.manager.store;calls=[]
    with s.store.conn:s.store.conn.execute('CREATE TABLE operator_requests(request_id TEXT PRIMARY KEY,binding TEXT NOT NULL,result TEXT,error TEXT)')
    s._dispatch=lambda *args:calls.append(args) or dict(current=len(calls)==1)
    decision=Decision(str(uuid4()),'a'*64);payload=dict(operation='inspect',intent_id=str(uuid4()))
    assert s.handle(decision,'paper_intent',payload)['current']
    assert not s.handle(decision,'paper_intent',payload)['current']
    assert s.store.conn.execute('SELECT count(*) FROM operator_requests').fetchone()==(0,)


def test_trusted_native_launch_offer_matches_owner_endpoint_without_spawning_a_child(tmp_path,monkeypatch):
    from compertum.runtime import managed,managed_owner
    from compertum.runtime.identity import resolve_project
    from compertum.runtime.owners import acquire_owner,release_owner
    project=resolve_project(tmp_path);supervisor=acquire_owner(project,'supervisor');observed={}
    class StopBeforeLaunch(Exception):pass
    def offered(lease,*,role,allowed_commands):
        assert lease is supervisor and role=='execution';observed['offer']=allowed_commands
        raise StopBeforeLaunch()
    def endpoint(lease,commands):
        observed['endpoint']=commands;raise StopBeforeLaunch()
    monkeypatch.setattr(managed,'prepare_owner_channel',offered)
    monkeypatch.setattr(managed_owner,'start_role_pipe',endpoint)
    monkeypatch.setattr(managed_owner.sys,'argv',['owner','123',json.dumps(dict(root=str(tmp_path),role='execution'))])
    try:
        with pytest.raises(StopBeforeLaunch):managed.launch_owner(supervisor,'execution')
        with pytest.raises(StopBeforeLaunch):managed_owner.main()
    finally:release_owner(supervisor)
    assert observed['offer']==observed['endpoint'] and 'paper_intent' in observed['offer']

@pytest.mark.parametrize('operation',['prepare','confirm','inspect'])
def test_partial_fixture_never_routes_native_intents(owner,operation):
    from compertum.runtime.supervisor import Supervisor
    s=object.__new__(Supervisor);s.partial_fixture=True
    with pytest.raises(RuntimeRefused,match='EXECUTION_UNAVAILABLE'):
        s._dispatch(Decision(str(uuid4()),'a'*64),'paper_intent',dict(operation=operation))


def test_actual_execution_handler_routes_intents_only_after_checkpoint_release(tmp_path,monkeypatch):
    """Real nested handler; startup, health, channel and reserve are simulated."""
    from compertum.runtime import managed_owner as module,paper_read_owner
    lease=SimpleNamespace(generation=1);channel=object();events=[];constructed=[];calls=[]
    expected_destination=module.resolve_project(tmp_path).root_path/'backups/intent-handler-probe'
    class StopAfterHandler(Exception):pass
    def checkpoint(barrier,destination,maximum_bytes):
        assert destination==expected_destination and maximum_bytes==1024
        events.append(('snapshot',barrier));return dict(status='SNAPSHOT',barrier_id=barrier)
    store=SimpleNamespace(checkpoint=checkpoint)
    mutual=SimpleNamespace(tick=lambda:None)
    class Reads:
        def __init__(self,*args):assert args==(store,reserve,mutual);constructed.append(self)
        def handle(self,p):raise AssertionError('wrong read route')
        transfer=market_handle=market_transfer=presence_handle=handle
        def intent_handle(self,p):calls.append(p);return dict(observed=p)
        def tick(self):raise AssertionError('no second event loop iteration expected')
        def require_checkpoint(self):events.append(('intent_checkpoint',))
    reserve=object()
    monkeypatch.setattr(module,'acquire_owner',lambda *a:lease)
    monkeypatch.setattr(module,'release_owner',lambda value:events.append(('released',value)))
    monkeypatch.setattr(module,'start_role_pipe',lambda *a:object())
    monkeypatch.setattr(module,'_registration',lambda value:value)
    monkeypatch.setattr(module,'receive_owner_channel',lambda *a,**k:channel)
    monkeypatch.setattr(module,'open_store',lambda *a:store)
    monkeypatch.setattr(module,'create_journal_reserve',lambda *a:reserve)
    monkeypatch.setattr(module,'disarm_execution',lambda *a:None)
    monkeypatch.setattr(module,'MutualHealth',lambda *a,**k:mutual)
    monkeypatch.setattr(paper_read_owner,'PaperReadOwner',Reads)
    monkeypatch.setattr(module.sys,'argv',['owner','123',json.dumps(dict(root=str(tmp_path),role='execution',supervisor={}))])
    def serve(received,handler,**kwargs):
        assert received is channel
        barrier=str(uuid4());payloads=[dict(request_id=str(uuid4()),subject_key='a'*64,command=dict(operation=op)) for op in ('prepare','confirm','inspect')]
        request=dict(operation='snapshot',barrier_id=barrier,destination='backups/intent-handler-probe',maximum_bytes=1024)
        assert handler('checkpoint',request)['status']=='SNAPSHOT'
        for payload in payloads:
            with pytest.raises(RuntimeRefused,match='BARRIER_HELD'):handler('paper_intent',payload)
        assert not constructed and not calls
        assert handler('checkpoint',dict(operation='end',barrier_id=barrier))==dict(status='BARRIER_RELEASED')
        for payload in payloads:assert handler('paper_intent',payload)==dict(observed=payload)
        assert calls==payloads and len(constructed)==1
        handler('checkpoint',request);assert ('intent_checkpoint',) in events
        raise StopAfterHandler()
    monkeypatch.setattr(module,'serve_owner_once',serve)
    with pytest.raises(StopAfterHandler):module.main()
    assert events[-1]==('released',lease)
