"""The fixed test bench and the holdout (25 October 2026), product lane: markets, reference rule, drift-free measure, report,
the exclusion of evaluation cycles from everything that learns, the holdout count and the practice command path.

The bench run with the scripted model is in tests/test_engine_bench_run.py (engine environment).
"""
import json
from pathlib import Path
import shutil
import sys
from types import SimpleNamespace
import pytest
from test_ai_manual import bridge  # noqa: F401  (fixture)
from compertum.ai.engine import bench,practice
from compertum.ai.engine.deflation import deflated_sharpe,trial_variance
from compertum.ai.engine.gepa_run import earlier_titles
from compertum.ai.engine.ledger import EVALUATION_PURPOSES,EngineLedger
from compertum.ai.engine.market import score_signals
from compertum.runtime.errors import RuntimeRefused

PROJECT=Path(__file__).resolve().parents[1]


def test_bench_and_holdout_use_separate_fixed_seed_sets_with_two_empty_markets_each():
    seeds={name:{seed for _,_,seed in markets} for name,markets in bench.SETS.items()}
    assert seeds['bench-1'].isdisjoint(seeds['holdout-1'])
    used_elsewhere={12}|{12+offset for _,_,offset in practice.GEPA_MARKETS}  # the practice market and the GEPA markets
    assert all(s.isdisjoint(used_elsewhere) for s in seeds.values())
    for name in ('bench-1','holdout-1'):
        kinds=[(kind,window) for kind,window,_ in bench.SETS[name]]
        assert kinds==[('momentum',5),('momentum',10),('reversal',3),(None,0),(None,0)]
        markets=bench.set_markets(name)
        assert len({m['validation_csv'] for m in markets})==5 and all(m['set']==name and m['label'].startswith(name+': ') for m in markets)
        assert bench.set_markets(name)[0]['validation_csv']==markets[0]['validation_csv']  # deterministic
    assert bench.BENCH_SET=='bench-1' and bench.HOLDOUT_SET=='holdout-1' and bench.HOLDOUT_USES==5
    with pytest.raises(RuntimeRefused,match='^ENGINE_MARKET_DENIED$'): bench.set_markets('holdout-2')
    # Seeds 100 to 199 and 900 to 999 are reserved; every set seed is inside them, so no practice or GEPA seed can rebuild a set market.
    assert all(bench.reserved_seed(s) for v in seeds.values() for s in v) and not bench.reserved_seed(12) and not bench.reserved_seed(99) and bench.reserved_seed(999)
    assert len(bench.reserved_fingerprints())==10 and bench.set_fingerprints('bench-1').isdisjoint(bench.set_fingerprints('holdout-1'))


@pytest.mark.parametrize('name',['bench-1','holdout-1'])
def test_the_reference_rule_finds_every_planted_pattern_and_nothing_in_an_empty_market(name):
    for market in bench.set_markets(name):
        score=bench.reference_score(market)
        if market['kind'] is None:
            assert score['beats_baseline'] is False and abs(float(score['sharpe'])-float(score['benchmark_sharpe']))<0.01
        else:
            assert score['beats_baseline'] is True and float(score['sharpe'])>float(score['benchmark_sharpe'])+1.5, market['label']
            assert bench.capture(score,score)=='1.000'


def test_the_exact_planted_rule_rarely_passes_the_gate_on_150_validation_sessions():
    """The finding of 25 October 2026 that set the found rule: perfect knowledge of the pattern passes the bench-local gate (60 trials)
    on 2 of 6 patterned markets. The real gate uses the global count, above 100, so it is stricter still. Found therefore uses capture."""
    statuses={m['label']:bench.bench_deflation(bench.reference_score(m))['status'] for name in ('bench-1','holdout-1') for m in bench.set_markets(name) if m['kind']}
    assert sorted(statuses.values())==['FAIL','FAIL','FAIL','FAIL','PASS','PASS']


def test_the_bench_measure_does_not_move_with_the_global_trial_count():
    market=bench.set_markets('bench-1')[0];score=bench.reference_score(market)
    first=bench.bench_deflation(score);second=bench.bench_deflation(score)
    assert first==second and first['trials']==bench.BENCH_TRIALS==60
    inputs=score['deflation_inputs']
    global_view=[deflated_sharpe(inputs,n,trial_variance([],inputs)['trial_variance'])['deflated_sharpe'] for n in (100,1000,100000)]
    assert len(set(global_view))==3  # the real gate's value moves with the count; the bench value does not


def lookahead(market):
    """A strategy that reads the next return: it passes any Sharpe gate. Here it stands for a harness that finds an edge in nothing."""
    rows=market['validation_rows']
    return [1 if i+1<len(rows) and float(rows[i+1]['return'])>0 else 0 for i in range(len(rows))]


def candidate_cycle(market,positions,hid='h1',audit='VERIFIED_PASS',status='REJECTED_DEFLATED'):
    score=score_signals(bench.signals_text(market['validation_rows'],positions),market['validation_rows'])
    return {'market':market['label'],'status':'COMPLETED','stop_code':None,'scores':{hid:score},
            'candidates':[{'hypothesis_id':hid,'status':status,'audit':{'label':audit},'deflation':{'deflated_sharpe':'0.10000000','status':'FAIL'}}]}


def test_the_report_finds_patterns_by_the_reference_and_calls_any_find_in_an_empty_market_broken():
    markets=bench.set_markets('bench-1')
    reference=[candidate_cycle(m,bench.reference_positions(m['train_rows'],m['validation_rows'],m['kind'],m['window'])) for m in markets[:3]]
    flat=[candidate_cycle(m,[0]*len(m['validation_rows']),status='REJECTED') for m in markets[3:]]
    report=bench.report(reference+flat,markets)
    assert report['verdict']=='MEASURED' and report['patterns_found']==3 and report['patterned_markets']==3
    assert report['false_discoveries']==0 and report['empty_markets']==2 and report['bench_trials']==60
    assert [r['best_capture'] for r in report['markets'][:3]]==['1.000','1.000','1.000']
    # The global gate said FAIL (deflated Sharpe 0.10); the bench level uses the bench-local value, so 10 or 9, not 7.
    assert [r['found'] for r in report['markets'][:3]]==[1,1,1] and report['found_capture']=='0.5'
    assert [r['bench_gate_passed'] for r in report['markets'][:3]]==[1,0,0]  # the reference itself fails the gate on two markets
    assert [r['levels'] for r in report['markets']]==[[10],[9],[9],[4],[4]] and report['mean_level']=='7.20'
    # The same strategy without an Auditor pass counts as beating buy-and-hold, not as a found pattern.
    unaudited=bench.report([candidate_cycle(markets[0],bench.reference_positions(markets[0]['train_rows'],markets[0]['validation_rows'],'momentum',5),audit='VERIFIED_FAIL')],markets)
    row=unaudited['markets'][0];assert row['beat_buy_and_hold']==1 and row['audit_passed']==0 and row['found']==0 and row['levels']==[6] and unaudited['patterns_found']==0
    # Capture is the share of the reference's Sharpe advantage over buy-and-hold. Found needs at least half.
    assert bench.capture({'sharpe':'2.5','benchmark_sharpe':'0.5'},{'sharpe':'4.5'})=='0.500' and bench.capture({'sharpe':'1','benchmark_sharpe':'2'},{'sharpe':'1.5'}) is None
    assert bench.capture({'sharpe':None,'benchmark_sharpe':'0.5'},{'sharpe':'4.5'}) is None
    idle=bench.report([candidate_cycle(markets[0],[0]*len(markets[0]['validation_rows']))],markets)['markets'][0];assert idle['found']==0 and idle['beat_buy_and_hold']==0
    assert unaudited['verdict']=='INCOMPLETE: a market has no finished cycle'
    # An audited pass on a market with no pattern is a false discovery: the whole bench says BROKEN.
    broken=bench.report(reference+[candidate_cycle(markets[3],lookahead(markets[3])),flat[1]],markets)
    assert broken['false_discoveries']==1 and broken['verdict'].startswith('BROKEN') and broken['markets'][3]['false_discoveries']==1
    assert bench.report([{**flat[0],'market':'another market'}],markets)['unknown_markets']==['another market']
    json.dumps(report)


def test_the_trial_count_follows_the_cycles_per_market_and_a_real_gate_pass_on_an_empty_market_is_broken(monkeypatch):
    markets=bench.set_markets('bench-1')
    short=bench.report([],markets,cycles_per_market=1)
    assert short['bench_trials']==15 and short['cycles_per_market']==1 and short['candidates_total']==0 and bench.report([],markets)['bench_trials']==60
    # On a young ledger the real gate can be looser than the bench gate: a strategy that passed the real gate on an empty market is a false discovery.
    monkeypatch.setattr(bench,'bench_deflation',lambda score,trials=60:{'status':'FAIL','deflated_sharpe':'0.10000000'})
    for status in ('EVALUATION_GATE_PASS','QUEUED'):
        report=bench.report([candidate_cycle(markets[3],lookahead(markets[3]),status=status)],markets)
        assert report['false_discoveries']==1 and report['verdict'].startswith('BROKEN'),status


def test_audit_failures_and_missing_scores_keep_their_levels():
    market=bench.set_markets('bench-1')[0]
    assert bench.bench_level({'status':'REJECTED_AUDIT','audit':{'label':'VERIFIED_FAIL'}},{'beats_baseline':True})==3
    assert bench.bench_level({'status':'BUILD_FAILED'},None)==2
    cycle=candidate_cycle(market,bench.reference_positions(market['train_rows'],market['validation_rows'],'momentum',5))
    assert bench.bench_cycle_level(cycle)==10 and bench.bench_cycle_level({'candidates':[]})==1


def write_end(ledger,index,purpose,title):
    record={'status':'COMPLETED','market_sha256':'m'*64,'hypotheses':[{'id':'h1','title':title,'idea':'x'}],'candidates':[],'decisions':{}}
    if purpose is not None: record['purpose']=purpose
    ledger.record_cycle(f'cycle-{index:04d}-x',index,'END',record)


def test_bench_and_holdout_cycles_never_reach_the_summary_the_lessons_or_gepa_feedback(bridge):
    b,_=bridge;ledger=EngineLedger(b.store)
    write_end(ledger,1,None,'Old practice idea');write_end(ledger,2,'practice','New practice idea')
    write_end(ledger,3,'bench','Bench idea');write_end(ledger,4,'holdout','Holdout idea')
    assert EVALUATION_PURPOSES=={'bench','holdout'}
    summary=ledger.summary('m'*64)
    assert summary['cycles_completed']==2 and [r['cycle_index'] for r in summary['recent']]==[1,2]
    assert [r['idea'] for r in summary['lessons']]==['Old practice idea','New practice idea']
    assert set(earlier_titles(ledger,'none'))=={'old practice idea','new practice idea'}
    assert ledger.blank_summary()=={'cycles_completed':0,'active_freezes':0,'recent':[],'lessons':[]}


def test_holdout_uses_count_every_started_run_of_that_set(bridge):
    b,_=bridge;ledger=EngineLedger(b.store)
    ledger.record_run_phase('run-20261025-0000aaa1','START',{'purpose':'holdout','holdout_set':'holdout-1'})  # crashed: no END row, still a use
    ledger.record_run_phase('run-20261025-0000aaa2','START',{'purpose':'holdout','holdout_set':'holdout-1'});ledger.record_run_phase('run-20261025-0000aaa2','END',{})
    ledger.record_run_phase('run-20261025-0000aaa3','START',{'purpose':'bench'})
    ledger.record_run_phase('run-20261025-0000aaa4','START',{'purpose':'holdout','holdout_set':'holdout-9'})
    assert ledger.holdout_uses('holdout-1')==2 and ledger.holdout_uses('holdout-9')==1 and ledger.holdout_uses('holdout-2')==0


@pytest.fixture
def fake_run(monkeypatch):
    """The practice command path without the engine library: run_bounded is replaced, the sandbox check is real (as in test_engine_practice)."""
    seen={}
    def run_bounded(**kwargs):
        seen.update(kwargs);markets=kwargs['schedule'][:5]
        cycles=[{**candidate_cycle(m,[0]*len(m['validation_rows']),status='REJECTED'),'cycle_index':i+1} for i,m in enumerate(markets)]
        return {'run_id':'run-20261025-0123abcd','reason':'CYCLE_LIMIT','cycles':cycles,'requests':40,'elapsed_seconds':3.0,'summary_path':'s.md','models':{}}
    monkeypatch.setitem(sys.modules,'compertum.ai.engine.run',SimpleNamespace(run_bounded=run_bounded))
    return seen


def project(tmp_path):
    shutil.copyfile(PROJECT/'config/default.toml',tmp_path/'config.toml');(tmp_path/'config').mkdir()
    shutil.copyfile(PROJECT/'config/models.toml',tmp_path/'config'/'models.toml')
    shutil.copytree(PROJECT/'config'/'engine_prompts',tmp_path/'config'/'engine_prompts')
    return tmp_path


def test_the_bench_command_runs_an_interleaved_schedule_and_prints_the_report(tmp_path,fake_run):
    root=project(tmp_path)
    record=practice.run_practice(root,root/'config.toml',cycles=None,hours=None,requests=450,note='bench fixture',purpose='bench',available_memory=lambda:practice.START_FLOOR+1)
    labels=[m['label'] for m in bench.set_markets('bench-1')]
    assert [m['label'] for m in fake_run['schedule']]==labels*4 and fake_run['limits'].cycle_limit==20 and fake_run['purpose']=='bench'
    assert fake_run['holdout_set'] is None and fake_run['prompts'] is None
    assert record['kind']=='bench' and record['cycles_per_market']==4 and record['prompts_source']=='config/engine_prompts'
    assert record['report']['verdict']=='MEASURED' and record['report']['patterns_found']==0 and record['preflight']['markets']==5
    assert record['vault_sessions_held_back']==5*100
    json.dumps(record)


def test_the_holdout_command_names_its_set_and_can_measure_a_gepa_candidate(tmp_path,fake_run):
    root=project(tmp_path);folder=root/'state'/'engine'/'prompts'/'run-20261025-00001111'/'candidate-2';folder.mkdir(parents=True)
    for role in ('director','researcher','mathematician','engineer'): (folder/f'{role}.md').write_text(f'ROLE: {role}\nA candidate prompt from a GEPA fixture, long enough to pass.\n',encoding='utf-8',newline='\n')
    record=practice.run_practice(root,root/'config.toml',cycles=None,hours=None,requests=450,note='holdout fixture',purpose='holdout',cycles_per_market=1,
                                 prompts_run='run-20261025-00001111',prompts_candidate=2,available_memory=lambda:practice.START_FLOOR+1)
    assert fake_run['holdout_set']=='holdout-1' and [m['label'] for m in fake_run['schedule']]==[m['label'] for m in bench.set_markets('holdout-1')]
    assert fake_run['prompts']['engineer'].startswith('ROLE: engineer\nA candidate prompt') and record['prompts_source']=='run-20261025-00001111 candidate 2'
    # A candidate prompt with an unfilled placeholder is refused by the preflight check before the lease.
    (folder/'director.md').write_text('ROLE: director\nPick hypotheses for cycle {cycle_index} and reply with JSON only.\n',encoding='utf-8',newline='\n')
    with pytest.raises(RuntimeRefused,match='^ENGINE_PREFLIGHT_FAILED$'):
        practice.run_practice(root,root/'config.toml',cycles=None,hours=None,requests=450,note='x',purpose='holdout',prompts_run='run-20261025-00001111',prompts_candidate=2,
                              available_memory=lambda:practice.START_FLOOR+1)


@pytest.mark.parametrize('options,code',[
    ({'purpose':'vault'},'ENGINE_RUN_PURPOSE_DENIED'),
    ({'purpose':'bench','gepa':True},'ENGINE_RUN_PURPOSE_DENIED'),
    ({'purpose':'bench','cycles_per_market':0},'ENGINE_RUN_LIMITS_DENIED'),
    ({'purpose':'bench','cycles_per_market':11},'ENGINE_RUN_LIMITS_DENIED'),
    ({'purpose':'bench','prompts_run':'run-20261025-00001111'},'ENGINE_PROMPT_INVALID'),
    ({'purpose':'practice','prompts_run':'run-20261025-00001111','prompts_candidate':1},'ENGINE_PROMPT_INVALID'),
    ({'purpose':'bench','prompts_run':'run-20261025-00009999','prompts_candidate':1},'ENGINE_PROMPT_UNAVAILABLE'),
    ({'seed':901},'ENGINE_SEED_RESERVED'),  # practice market 1 would equal holdout market 1
    ({'seed':875,'gepa':True},'ENGINE_SEED_RESERVED'),  # the no-pattern GEPA market (offset 29) would be seed 904, a holdout empty market
    ({'seed':150},'ENGINE_SEED_RESERVED'),
])
def test_bad_bench_options_are_refused_before_the_lease(tmp_path,fake_run,options,code):
    root=project(tmp_path)
    with pytest.raises(RuntimeRefused,match=f'^{code}$'):
        practice.run_practice(root,root/'config.toml',cycles=1,hours=None,requests=10,note='x',available_memory=lambda:practice.START_FLOOR+1,**options)
    assert not (root/'state'/'locks').exists() and fake_run=={}


def test_the_command_line_passes_bench_and_holdout_options(tmp_path,monkeypatch,capsys):
    seen={}
    def fake(root,config,**kwargs): seen.update(kwargs);return {'kind':kwargs['purpose']}
    monkeypatch.setattr(practice,'run_practice',fake)
    assert practice.main(['--project',str(tmp_path),'holdout','--requests','450','--note','n','--cycles-per-market','2','--prompts-run','run-20261025-00001111','--prompts-candidate','3'])==0
    assert seen=={'cycles':None,'hours':None,'requests':450,'note':'n','purpose':'holdout','cycles_per_market':2,'prompts_run':'run-20261025-00001111','prompts_candidate':3}
    assert json.loads(capsys.readouterr().out)=={'kind':'holdout'}
    assert practice.main(['--project',str(tmp_path),'bench','--requests','450','--note','n'])==0 and seen['cycles_per_market']==4 and seen['prompts_run'] is None
