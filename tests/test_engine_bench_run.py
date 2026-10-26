"""The bench and the holdout (25 October 2026), engine environment lane: real cycles with the scripted model and the real sandbox.

A bench cycle starts with no history and no lessons, skips the agenda step, and leaves nothing for the next practice cycle or for
GEPA to learn from. A holdout run is counted before its first cycle and refused after its allowed uses.
"""
import hashlib
from types import SimpleNamespace
import pytest
deepagents=pytest.importorskip('deepagents')
from test_ai_manual import bridge  # noqa: E402,F401  (fixture)
from test_engine_limits import set_research_state  # noqa: E402
from test_engine_roles import market,role_server,root,verification  # noqa: E402,F401  (fixtures)
from test_engine_run import project,start  # noqa: E402,F401  (fixture and helper)
from compertum.ai.engine import bench  # noqa: E402
from compertum.ai.engine.cycle import market_sha256  # noqa: E402
from compertum.ai.engine.gepa_run import earlier_titles  # noqa: E402
from compertum.ai.engine.ledger import EngineLedger  # noqa: E402
from compertum.ai.engine.limits import RunLimits  # noqa: E402
from compertum.ai.engine.prompts import load_prompt  # noqa: E402
from compertum.runtime.errors import RuntimeRefused  # noqa: E402


def test_a_bench_run_sees_no_history_and_teaches_nothing(bridge,project,root,verification,market):
    b,_=bridge;set_research_state(b.store,'RUNNING');ledger=EngineLedger(b.store)
    markets=bench.set_markets('bench-1')
    first=market_sha256(SimpleNamespace(train_csv=markets[0]['train_csv'],validation_csv=markets[0]['validation_csv']))
    # Nine earlier practice cycles on the first bench market's files: a practice cycle there would see them as lessons.
    for index in range(1,10):
        ledger.record_cycle(f'cycle-{index:04d}-p',index,'END',{'status':'COMPLETED','purpose':'practice','market_sha256':first,
                            'hypotheses':[{'id':'h1','title':f'Practice idea {index}','idea':'x'}],'candidates':[],'decisions':{}})
    with role_server() as (port,state):
        result=start(bridge,project,root,verification,market,port,RunLimits(request_limit=200,cycle_limit=5),schedule=markets,purpose='bench')
    assert result['reason']=='CYCLE_LIMIT' and [c['cycle_index'] for c in result['cycles']]==[10,11,12,13,14]
    assert [c['market'] for c in result['cycles']]==[m['label'] for m in markets] and all(c['status']=='COMPLETED' for c in result['cycles'])
    rows=ledger.run_rows(result['run_id']);assert rows[0]['purpose']=='bench' and rows[0]['markets']==[m['label'] for m in markets] and rows[0]['prompts_source']=='committed'
    assert rows[0]['prompts_sha256']=={role:hashlib.sha256(load_prompt(project,role).encode('utf-8')).hexdigest() for role in ('director','researcher','mathematician','engineer')}
    starts=[c for c in ledger.cycles() if c['phase']=='START'];ends=[c for c in ledger.cycles() if c['phase']=='END' and c.get('purpose')=='bench']
    assert len(starts)==5 and all(c['purpose']=='bench' and c['summary']==ledger.blank_summary() for c in starts) and len(ends)==5
    # Cycle 10 is an agenda cycle for practice; a bench cycle skips the agenda step, so every bench cycle has the same steps.
    assert not [s for c in ends for s in ledger.steps(c['cycle_id']) if s['kind']=='agenda']
    assert not any(p['messages'][-1]['content'].startswith('Review the repeated failures') for p in state['posts'])
    # Nothing learns from the bench: the next practice summary, its lessons table and GEPA's earlier titles hold practice cycles only.
    summary=ledger.summary(first)
    assert summary['cycles_completed']==9 and [r['cycle_index'] for r in summary['recent']]==list(range(1,10))
    assert [r['idea'] for r in summary['lessons']]==[f'Practice idea {i}' for i in range(1,10)]
    assert set(earlier_titles(ledger,'none'))=={f'practice idea {i}' for i in range(1,10)}
    # The trials still count: every bench candidate is a trial in the global count, as every candidate is.
    assert ledger.total_trials()==5
    report=bench.report(result['cycles'],markets,cycles_per_market=1)
    assert [r['cycles'] for r in report['markets']]==[1,1,1,1,1] and report['bench_trials']==15
    # The scripted Engineer always trades five-session momentum: it finds both momentum markets, not the reversal, and nothing on the empty markets.
    assert [(r['statuses'],r['levels'],r.get('found'),r.get('false_discoveries')) for r in report['markets']]==[
        ({'EVALUATION_GATE_PASS':1},[10],1,None),({'EVALUATION_GATE_PASS':1},[10],1,None),({'REJECTED':1},[5],0,None),({'REJECTED':1},[5],None,0),({'REJECTED_DEFLATED':1},[7],None,0)]
    assert report['verdict']=='MEASURED' and report['patterns_found']==2 and report['false_discoveries']==0
    # A bench strategy never becomes a template or enters the vault queue, whatever it scores.
    statuses=[x['status'] for c in result['cycles'] for x in c['candidates']]
    assert 'QUEUED' not in statuses and not (project/'state'/'engine'/'promoted').exists() and ledger.queue_events()==[]
    assert all(r['candidates']==1 and r['scored']==1 for r in report['markets'])


def test_holdout_uses_are_counted_before_the_first_cycle_and_retired_after_the_limit(bridge,project,root,verification,market):
    b,_=bridge;set_research_state(b.store,'RUNNING');ledger=EngineLedger(b.store)
    for n in range(bench.HOLDOUT_USES-1):  # four earlier uses, one of them crashed with no END row
        run_id=f'run-20261025-0000bbb{n}';ledger.record_run_phase(run_id,'START',{'purpose':'holdout','holdout_set':'holdout-1'})
        if n: ledger.record_run_phase(run_id,'END',{})
    holdout=bench.set_markets('holdout-1')
    prompts={role:f'ROLE: {role}\n'+text for role,text in ((r,open(project/'config'/'engine_prompts'/f'{r}.md',encoding='utf-8').read().split('\n',1)[1]) for r in ('director','researcher','mathematician','engineer'))}
    with role_server() as (port,_):
        with pytest.raises(RuntimeRefused,match='^ENGINE_RUN_ACTIVE$'):  # the crashed use is still open: the owner closes it first
            start(bridge,project,root,verification,market,port,RunLimits(request_limit=60,cycle_limit=1),schedule=holdout,purpose='holdout',holdout_set='holdout-1')
        from compertum.ai.engine import control
        control.close_abandoned_run(b.store,'run-20261025-0000bbb0','closed (fixture)')
        result=start(bridge,project,root,verification,market,port,RunLimits(request_limit=60,cycle_limit=1),schedule=holdout,purpose='holdout',holdout_set='holdout-1',prompts=prompts)
        row=ledger.run_rows(result['run_id'])[0]
        assert row['purpose']=='holdout' and row['holdout_set']=='holdout-1' and row['holdout_use']==5 and row['holdout_uses_allowed']==5
        assert set(row['prompts_sha256'])=={'director','researcher','mathematician','engineer'} and result['cycles'][0]['market']==holdout[0]['label']
        assert ledger.holdout_uses('holdout-1')==5
        before=len(ledger.run_starts())
        with pytest.raises(RuntimeRefused,match='^ENGINE_HOLDOUT_RETIRED$'):
            start(bridge,project,root,verification,market,port,RunLimits(request_limit=60,cycle_limit=1),schedule=holdout,purpose='holdout',holdout_set='holdout-1')
        assert len(ledger.run_starts())==before  # a refused use leaves no row


@pytest.mark.parametrize('extra,code',[
    ({'purpose':'bench'},'ENGINE_RUN_PURPOSE_DENIED'),  # bench needs a schedule
    ({'purpose':'practice','schedule':'S'},'ENGINE_RUN_PURPOSE_DENIED'),  # a schedule is for bench or holdout only
    ({'purpose':'vault','schedule':'S'},'ENGINE_RUN_PURPOSE_DENIED'),
    ({'purpose':'holdout','schedule':'S'},'ENGINE_RUN_PURPOSE_DENIED'),  # holdout needs its set
    ({'purpose':'bench','schedule':'S','holdout_set':'holdout-1'},'ENGINE_RUN_PURPOSE_DENIED'),
    ({'purpose':'holdout','schedule':'S','holdout_set':'bench-1'},'ENGINE_RUN_PURPOSE_DENIED'),
    ({'purpose':'bench','schedule':'S','limits':RunLimits(request_limit=60,cycle_limit=6)},'ENGINE_RUN_LIMITS_DENIED'),  # more cycles than the schedule
    ({'purpose':'bench','schedule':'S','limits':RunLimits(request_limit=60,hour_limit=1.0)},'ENGINE_RUN_LIMITS_DENIED'),
    ({'purpose':'bench','schedule':'H'},'ENGINE_MARKET_RESERVED'),  # holdout markets in a bench run would escape the count
    ({'purpose':'holdout','schedule':'S','holdout_set':'holdout-1'},'ENGINE_MARKET_RESERVED'),
    ({'purpose':'practice','market':'H'},'ENGINE_MARKET_RESERVED'),  # a practice cycle on a holdout market would teach the engine
    ({'purpose':'bench','schedule':'NOLABEL'},'ENGINE_MARKET_DENIED'),
    ({'purpose':'bench','schedule':'TWIN'},'ENGINE_MARKET_DENIED'),  # one label, two markets
])
def test_bad_purposes_and_schedules_are_refused_before_the_start_row(bridge,project,root,verification,market,extra,code):
    b,_=bridge;set_research_state(b.store,'RUNNING');ledger=EngineLedger(b.store)
    extra=dict(extra);limits=extra.pop('limits',RunLimits(request_limit=60,cycle_limit=1))
    markets={'S':bench.set_markets('bench-1'),'H':bench.set_markets('holdout-1')}
    markets['NOLABEL']=[{k:v for k,v in m.items() if k!='label'} for m in markets['S']]
    markets['TWIN']=[markets['S'][0],{**markets['S'][1],'label':markets['S'][0]['label']}]
    if extra.get('schedule') in markets: extra['schedule']=markets[extra['schedule']]
    if extra.get('market')=='H': market=markets['H'][0];extra.pop('market')
    with role_server() as (port,state):
        with pytest.raises(RuntimeRefused,match=f'^{code}$'): start(bridge,project,root,verification,market,port,limits,**extra)
    assert ledger.run_starts()==[] and state['posts']==[]
