"""Stage E5, engine environment lane: bounded runs with cycle, hour and request limits, the kill switch, freezes and the summary.

Every model reply comes from the scripted loopback server of tests/test_engine_roles.py. Engineer code really runs in the sandbox.
Skipped in the product environment (no Deep Agents) and reported as skipped.
"""
from pathlib import Path
import shutil
import pytest
deepagents=pytest.importorskip('deepagents')
from test_ai_manual import bridge  # noqa: E402,F401  (fixture)
from test_ai_models_interface import FLOOR,roles  # noqa: E402
from test_engine_limits import set_research_state  # noqa: E402
from test_engine_roles import market,role_server,root,verification  # noqa: E402,F401  (fixtures)
from compertum.ai.engine import control  # noqa: E402
from compertum.ai.engine.ledger import EngineLedger  # noqa: E402
from compertum.ai.engine.limits import RunLimits  # noqa: E402
from compertum.ai.engine.run import run_bounded  # noqa: E402
from compertum.ai.models import StoreLedger  # noqa: E402
from compertum.runtime.errors import RuntimeRefused  # noqa: E402

PROJECT=Path(__file__).resolve().parents[1]


@pytest.fixture
def project(tmp_path):
    """A project folder with the real role prompts and an owner-set hard maximum of 200. Summaries go under its state/engine."""
    shutil.copytree(PROJECT/'config'/'engine_prompts',tmp_path/'config'/'engine_prompts')
    (tmp_path/'config'/'engine.toml').write_text('[run]\nrequest_hard_maximum = 200\n',encoding='utf-8')
    return tmp_path


def start(bridge,project,root,verification,market,port,limits,**extra):
    b,_=bridge
    return run_bounded(store=b.store,lease=b.storage.lease,project_root=project,sandbox_root=root,verification=verification,roles=roles(port),market=market,
                       memory_floor_bytes=FLOOR,limits=limits,owner_approval='Owner OK for this fixture run',available_memory=extra.pop('available_memory',lambda:FLOOR+1),**extra)


def test_cycle_limit_ends_the_run_with_records_and_a_summary(bridge,project,root,verification,market):
    b,_=bridge;set_research_state(b.store,'RUNNING')
    with role_server() as (port,state):
        result=start(bridge,project,root,verification,market,port,RunLimits(request_limit=100,cycle_limit=2))
    assert result['reason']=='CYCLE_LIMIT' and len(result['cycles'])==2 and [c['cycle_index'] for c in result['cycles']]==[1,2]
    assert all(c['status']=='COMPLETED' for c in result['cycles']) and result['requests']==len(state['posts'])<=100
    ledger=EngineLedger(b.store);rows=ledger.run_rows(result['run_id'])
    assert [r['phase'] for r in rows]==['START','END'] and rows[0]['limits']['request_hard_maximum']==200 and rows[0]['first_cycle_index']==1
    assert rows[1]['reason']=='CYCLE_LIMIT' and rows[1]['cycles']==2 and rows[1]['requests']==result['requests'] and ledger.open_runs()==[]
    assert all(c['run_id']==result['run_id'] for c in ledger.cycles()) and ledger.total_trials()==2
    summary=Path(result['summary_path']).read_text(encoding='utf-8')
    assert summary.startswith('Compertum engine daily summary') and 'ended, reason CYCLE_LIMIT' in summary and '2 cycles completed in this run' in summary
    assert 'Five-session momentum (h1)' in summary and 'Mean reversion (h2): memo rejected' in summary and 'director: synthetic-model' in summary
    assert Path(result['summary_path']).is_relative_to(project/'state'/'engine')
    # A second run continues the cycle index and refuses while the first is still open.
    ledger.record_run_phase('run-20261024-0000aaaa','START',{})
    with role_server() as (port,_):
        with pytest.raises(RuntimeRefused,match='^ENGINE_RUN_ACTIVE$'): start(bridge,project,root,verification,market,port,RunLimits(request_limit=10,cycle_limit=1))
        control.close_abandoned_run(b.store,'run-20261024-0000aaaa','closed (fixture)')
        again=start(bridge,project,root,verification,market,port,RunLimits(request_limit=100,cycle_limit=1))
    assert again['cycles'][0]['cycle_index']==3 and ledger.run_rows(again['run_id'])[0]['first_cycle_index']==3


def test_request_limit_stops_the_run_and_records_the_reason(bridge,project,root,verification,market):
    b,_=bridge;set_research_state(b.store,'RUNNING')
    with role_server() as (port,state):
        result=start(bridge,project,root,verification,market,port,RunLimits(request_limit=5,cycle_limit=10))
    assert result['reason']=='REQUEST_LIMIT' and result['requests']==5 and len(state['posts'])==5 and len(result['cycles'])==1
    assert result['cycles'][0]['status']=='STOPPED_AI_REQUEST_BUDGET'
    rows=EngineLedger(b.store).run_rows(result['run_id']);assert rows[1]['reason']=='REQUEST_LIMIT' and rows[1]['requests']==5
    assert 'ended, reason REQUEST_LIMIT' in Path(result['summary_path']).read_text(encoding='utf-8')


def test_refusals_before_start_leave_no_run_row(bridge,project,root,verification,market):
    b,_=bridge;ledger=EngineLedger(b.store)
    with role_server() as (port,state):
        with pytest.raises(RuntimeRefused,match='^RESEARCH_PAUSED$'): start(bridge,project,root,verification,market,port,RunLimits(request_limit=10,cycle_limit=1))
        set_research_state(b.store,'RUNNING')
        with pytest.raises(RuntimeRefused,match='^ENGINE_REQUEST_LIMIT_DENIED$'): start(bridge,project,root,verification,market,port,RunLimits(request_limit=201,cycle_limit=1))
        with pytest.raises(RuntimeRefused,match='^ENGINE_RUN_LIMITS_DENIED$'): start(bridge,project,root,verification,market,port,RunLimits(request_limit=10))
        with pytest.raises(RuntimeRefused,match='^ENGINE_RUN_APPROVAL_DENIED$'):
            run_bounded(store=b.store,lease=b.storage.lease,project_root=project,sandbox_root=root,verification=verification,roles=roles(port),market=market,
                        memory_floor_bytes=FLOOR,limits=RunLimits(request_limit=10,cycle_limit=1),owner_approval='')
        (project/'config'/'engine.toml').write_text('[run]\nrequest_hard_maximum = 0\n',encoding='utf-8')
        with pytest.raises(RuntimeRefused,match='^ENGINE_HARD_MAXIMUM_UNSET$'): start(bridge,project,root,verification,market,port,RunLimits(request_limit=1,cycle_limit=1))
        (project/'config'/'engine.toml').write_text('[run]\nrequest_hard_maximum = 200\n',encoding='utf-8')
        frozen=ledger.freeze('AUDITOR_FAILED',{'fixture':True})
        with pytest.raises(RuntimeRefused,match='^ENGINE_FROZEN$'): start(bridge,project,root,verification,market,port,RunLimits(request_limit=10,cycle_limit=1))
        assert state['posts']==[] and ledger.open_runs()==[] and ledger.cycles()==[]
        control.clear_freeze(b.store,frozen['freeze_id'],'owner cleared (fixture)')
        result=start(bridge,project,root,verification,market,port,RunLimits(request_limit=100,cycle_limit=1))
    assert result['reason']=='CYCLE_LIMIT' and len(result['cycles'])==1


def test_kill_switch_stops_dispatch_at_the_next_request(bridge,project,root,verification,market):
    b,_=bridge;store=b.store;set_research_state(store,'RUNNING');posts=[]
    def available():
        # The owner's `research pause` lands between two requests. The next request must not start.
        if len(posts)==3: set_research_state(store,'PAUSED')
        posts.append(1);return FLOOR+1
    with role_server() as (port,state):
        result=start(bridge,project,root,verification,market,port,RunLimits(request_limit=100,cycle_limit=5),available_memory=available)
    assert result['reason']=='KILL_SWITCH' and len(state['posts'])==4 and result['requests']==4 and len(result['cycles'])==1
    assert result['cycles'][0]['status']=='STOPPED_ENGINE_STOPPED'
    rows=EngineLedger(store).run_rows(result['run_id']);assert rows[1]['reason']=='KILL_SWITCH' and rows[1]['gate_checks']>=5 and rows[1]['stop_trigger']=='RESEARCH_STATE'
    # The stop landed at the step boundary: four completed model calls, no fifth attempt, no refusal row (the request-level
    # gate is pinned in tests/test_ai_models_interface.py).
    assert [r['status'] for r in StoreLedger(store).rows()]==['COMPLETED']*4
    assert 'ended, reason KILL_SWITCH' in Path(result['summary_path']).read_text(encoding='utf-8')


def test_hour_limit_stops_the_run_between_steps(bridge,project,root,verification,market):
    b,_=bridge;set_research_state(b.store,'RUNNING');ticks=[0.0]
    def clock():
        ticks[0]+=600.0;return ticks[0]  # ten minutes pass at every look at the clock
    with role_server() as (port,state):
        result=start(bridge,project,root,verification,market,port,RunLimits(request_limit=100,hour_limit=1),clock=clock)
    # Gate checks: run start (10 min), step 1 (20), request 1 (30), step 2 (40), request 2 (50), step 3 (60 min: refused).
    assert result['reason']=='HOUR_LIMIT' and len(state['posts'])==2 and len(result['cycles'])==1 and result['cycles'][0]['status']=='STOPPED_ENGINE_HOUR_LIMIT'
    assert result['elapsed_seconds']>=3600 and EngineLedger(b.store).run_rows(result['run_id'])[1]['reason']=='HOUR_LIMIT'


def test_stop_file_stops_the_run_without_a_lease(bridge,project,root,verification,market):
    b,_=bridge;store=b.store;set_research_state(store,'RUNNING');stop=project/'state'/'engine'/'STOP';posts=[]
    def available():
        # The owner creates state/engine/STOP from another process while this run holds the coordinator owner lease.
        if len(posts)==2: stop.parent.mkdir(parents=True,exist_ok=True);stop.write_text('owner stop (fixture)',encoding='utf-8')
        posts.append(1);return FLOOR+1
    with role_server() as (port,state):
        result=start(bridge,project,root,verification,market,port,RunLimits(request_limit=100,cycle_limit=5),available_memory=available)
        assert result['reason']=='KILL_SWITCH' and len(state['posts'])==3 and result['cycles'][0]['status']=='STOPPED_ENGINE_STOPPED'
        rows=EngineLedger(store).run_rows(result['run_id']);assert rows[1]['stop_trigger']=='STOP_FILE' and rows[0]['stop_file']==str(stop)
        # The file also blocks the next run until the owner removes it.
        with pytest.raises(RuntimeRefused,match='^ENGINE_STOP_FILE_PRESENT$'): start(bridge,project,root,verification,market,port,RunLimits(request_limit=10,cycle_limit=1))
        stop.unlink()
        assert start(bridge,project,root,verification,market,port,RunLimits(request_limit=100,cycle_limit=1))['reason']=='CYCLE_LIMIT'
    with pytest.raises(RuntimeRefused,match='^AI_SENSITIVE_INPUT_DENIED$'):
        run_bounded(store=store,lease=b.storage.lease,project_root=project,sandbox_root=root,verification=verification,roles=roles(port),market=market,
                    memory_floor_bytes=FLOOR,limits=RunLimits(request_limit=10,cycle_limit=1),owner_approval='api_key=should-never-be-recorded')


def test_tenth_cycle_reviews_the_agenda_inside_a_run(bridge,project,root,verification,market):
    b,_=bridge;set_research_state(b.store,'RUNNING');ledger=EngineLedger(b.store)
    for index in range(1,10): ledger.record_cycle(f'cycle-{index:04d}-{index:08x}',index,'END',{'status':'COMPLETED','run_id':None})
    with role_server() as (port,state):
        result=start(bridge,project,root,verification,market,port,RunLimits(request_limit=100,cycle_limit=1))
    assert result['cycles'][0]['cycle_index']==10 and result['reason']=='CYCLE_LIMIT'
    steps=ledger.steps(result['cycles'][0]['cycle_id'])
    assert [s for s in steps if s['kind']=='agenda' and s['phase']=='REPLY'] and any(p['messages'][-1]['content'].startswith('Review the repeated failures') for p in state['posts'])
