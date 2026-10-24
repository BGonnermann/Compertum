"""Stage E6, product lane: fixed-part probe targets, forbidden-access detection, frozen files, scorecard trials, the request
invariant, promotion, and a hand-calculated Validator fixture that the Auditor's recomputation must match.
"""
from decimal import Decimal
import json
from pathlib import Path
import pytest
from test_ai_manual import bridge  # noqa: F401  (fixture)
from compertum.ai.engine.audit import (FIXED_FILES,PERTURBATIONS,check_request_invariant,engine_fixed_targets,perturbed_rows,register_scorecard_trials)
from compertum.ai.engine.execution import agent_paths,forbidden_access,remove_data_tiers
from compertum.ai.engine.ledger import EngineLedger
from compertum.ai.engine.market import score_signals
from compertum.ai.engine.promotion import promote,promoted_folder
from compertum.runtime.errors import RuntimeRefused
from compertum.runtime.sandbox import fixed_target_paths

PROJECT=Path(__file__).resolve().parents[1]


def test_fixed_targets_cover_rules_configuration_judge_code_and_store(tmp_path):
    targets=engine_fixed_targets(PROJECT)
    names={p.relative_to(PROJECT).as_posix() for p in targets}
    for name in ('docs/BUILD_SPEC.md','AGENTS.md','config/default.toml','config/engine.toml','config/models.toml','src/compertum/ai/engine/deflation.py',
                 'src/compertum/ai/engine/vault.py','src/compertum/ai/engine/limits.py','src/compertum/ai/engine/run.py','src/compertum/ai/engine/cycle.py',
                 'src/compertum/ai/engine/audit.py','src/compertum/ai/engine/market.py','src/compertum/ai/engine/ledger.py','src/compertum/ai/engine/execution.py',
                 'src/compertum/runtime/sandbox.py'):
        assert name in names
    assert len(targets)<=16 and fixed_target_paths(targets)==[str(p) for p in targets]  # the sandbox admits them as probe targets
    assert PERTURBATIONS==(1,4,8)
    assert set(FIXED_FILES)>=names-{'state/research.sqlite'}
    # The store file joins when it exists; missing files are skipped, never invented.
    assert engine_fixed_targets(tmp_path)==[]
    (tmp_path/'state').mkdir();(tmp_path/'state'/'research.sqlite').write_bytes(b'x');(tmp_path/'AGENTS.md').write_text('rules',encoding='utf-8')
    assert [p.name for p in engine_fixed_targets(tmp_path)]==['AGENTS.md','research.sqlite']


def test_forbidden_access_rerun_files_data_removal_and_perturbation(tmp_path):
    assert forbidden_access(b"Traceback...\nPermissionError: [Errno 13] Permission denied: 'C:\\\\x\\\\AGENTS.md'\n") is True
    assert forbidden_access(b'OSError: [WinError 5] Access is denied') is True
    assert forbidden_access(b'FileNotFoundError: no such file') is False and forbidden_access('text') is False and forbidden_access(b'') is False
    # Reruns and promotion use the code as submitted (the launch record), in the agent's path form.
    assert agent_paths({'main.py':'print(1)\n','pkg/util.py':'X=1\n'})=={'/main.py':'print(1)\n','/pkg/util.py':'X=1\n'}
    for bad in ({},None,'main.py'):
        with pytest.raises(RuntimeRefused,match='^ENGINE_RERUN_DENIED$'): agent_paths(bad)
    job=tmp_path/'job-1';job.mkdir()
    for name in ('train.csv','validation.csv','signals.csv','main.py'): (job/name).write_text('x',encoding='utf-8')
    assert remove_data_tiers(job)==['train.csv','validation.csv'] and sorted(p.name for p in job.iterdir())==['main.py','signals.csv'] and remove_data_tiers(job)==[]
    # The perturbation changes only the last k rows: return sign flipped, close scaled; sessions unchanged.
    rows=[{'session':i,'close':'100.000000','return':'0.01000000'} for i in range(10)]
    changed=perturbed_rows(rows,4)
    assert changed[:6]==rows[:6] and [r['session'] for r in changed]==list(range(10))
    assert [r['return'] for r in changed[6:]]==['-0.01000000']*4 and [r['close'] for r in changed[6:]]==['97.000000','96.000000','95.000000','94.000000']
    assert rows[9]=={'session':9,'close':'100.000000','return':'0.01000000'}  # the originals are untouched
    for k in (0,9,10,'1'):
        with pytest.raises(RuntimeRefused,match='^ENGINE_AUDIT_DENIED$'): perturbed_rows(rows,k)


def test_scorecard_trials_and_request_invariant(bridge):
    b,_=bridge;ledger=EngineLedger(b.store)
    card={'schema':'synthetic-campaign-scorecard-v1','family_size':12,'registered_family':[{'candidate_id':f'c{i}'} for i in range(12)],'financial_accepted':False}
    row=register_scorecard_trials(ledger,'m3-repair-20261023-02',card)
    assert row['count']==12 and ledger.total_trials()==12 and len(row['evidence']['scorecard_sha256'])==64
    with pytest.raises(RuntimeRefused,match='^ENGINE_TRIAL_DUPLICATE$'): register_scorecard_trials(ledger,'m3-repair-20261023-02',card)
    for bad in (dict(card,schema='other'),dict(card,family_size=11),dict(card,registered_family=[]),dict(card,family_size='12'),'card'):
        with pytest.raises(RuntimeRefused,match='^ENGINE_SCORECARD_DENIED$'): register_scorecard_trials(ledger,'x',bad)
    assert ledger.total_trials()==12
    assert check_request_invariant(ledger,'run-20261024-0123abcd',40,40) is True and ledger.active_freezes()==[]
    assert check_request_invariant(ledger,'run-20261024-0123abcd',41,40) is False
    frozen=ledger.active_freezes();assert len(frozen)==1 and frozen[0]['reason']=='REQUEST_LIMIT_EXCEEDED' and frozen[0]['evidence']=={'run_id':'run-20261024-0123abcd','requests':41,'request_limit':40}
    with pytest.raises(RuntimeRefused,match='^ENGINE_RECORD_DENIED$'): check_request_invariant(ledger,'r','41',40)


def test_promotion_writes_a_versioned_template_once(tmp_path):
    files={'main.py':'print("signals")\n','pkg/util.py':'X=1\n'};job=tmp_path/'job-7'
    audit={'label':'VERIFIED_PASS','integrity':True,'reasons':[],'checks':{'reproducible':True,'no_lookahead':True}}
    result=promote(tmp_path,'cycle-0001-abcdefab:h1',files,audit=audit,score={'beats_baseline':True},deflation={'status':'PASS'},source_job_folder=job)
    folder=Path(result['folder']);assert folder==promoted_folder(tmp_path,'cycle-0001-abcdefab:h1')==tmp_path/'state'/'engine'/'promoted'/'cycle-0001-abcdefab_h1'
    assert (folder/'main.py').read_text(encoding='utf-8')=='print("signals")\n' and (folder/'pkg'/'util.py').read_text(encoding='utf-8')=='X=1\n'
    manifest=json.loads((folder/'manifest.json').read_bytes())
    assert manifest['version']==1 and set(manifest['files'])=={'main.py','pkg/util.py'} and len(manifest['files']['main.py'])==64 and manifest['audit']==audit
    assert manifest['source_job_folder']==str(job)
    with pytest.raises(RuntimeRefused,match='^ENGINE_PROMOTION_DUPLICATE$'): promote(tmp_path,'cycle-0001-abcdefab:h1',files,audit=audit,score={},deflation={},source_job_folder=job)
    with pytest.raises(RuntimeRefused,match='^ENGINE_PROMOTION_DENIED$'): promote(tmp_path,'cycle-0001-abcdefab:h2',files,audit={**audit,'label':'VERIFIED_FAIL'},score={},deflation={},source_job_folder=job)
    for bad in ({},{'/main.py':'x'},{'../x.py':'x'},{'main.py':b'x'}):
        with pytest.raises(RuntimeRefused,match='^ENGINE_PROMOTION_DENIED$'): promote(tmp_path,'cycle-0001-abcdefab:h3',bad,audit=audit,score={},deflation={},source_job_folder=job)
    with pytest.raises(RuntimeRefused,match='^ENGINE_PROMOTION_DENIED$'): promoted_folder(tmp_path,'')
    assert (PROJECT/'.gitignore').read_text(encoding='utf-8').splitlines().count('state/')==1


def test_validator_matches_a_hand_calculated_fixture():
    """Six validation sessions with returns 0.01, 0.02, -0.01, 0.03, 0.00, 0.01 and positions 1, 1, 0, 1, 1, 0.

    The position chosen at session t earns the return of t+1; a position change costs 0.0005 of NAV.
    Session 1: held 1 (first change) -> NAV = 1 * (1 + 0.02 - 0.0005) = 1.0195.
    Session 2: held 1 -> NAV = 1.0195 * (1 - 0.01) = 1.009305.
    Session 3: held 0 (change) -> NAV = 1.009305 * (1 - 0.0005) = 1.0088003475.
    Session 4: held 1 (change) -> NAV = 1.0088003475 * (1 + 0.00 - 0.0005) = 1.00829594732625.
    Session 5: held 1 -> NAV = 1.00829594732625 * (1 + 0.01) = 1.0183789067995125.
    Benchmark: 1.02 * 0.99 = 1.0098; * 1.03 = 1.040094; * 1.00 = 1.040094; * 1.01 = 1.05049494.
    Position changes: 0->1, 1->0, 0->1, 1->0 = 4; the last change (session 5) has no next return, so only 3 are charged.
    """
    rows=[{'session':i,'close':'1','return':r} for i,r in enumerate(['0.01','0.02','-0.01','0.03','0.00','0.01'])]
    text='session,position\n0,1\n1,1\n2,0\n3,1\n4,1\n5,0\n'
    score=score_signals(text,rows)
    assert score['final_nav']=='1.01837891' and score['benchmark_final_nav']=='1.05049494' and score['position_changes']==4 and score['positions_held']==4
    # Independent recomputation with plain Decimal arithmetic.
    nav=Decimal(1);previous=0;positions=[1,1,0,1,1,0];returns=[Decimal(r['return']) for r in rows]
    for index in range(1,6):
        held=positions[index-1];nav=nav*(1+held*returns[index]-Decimal('0.0005')*abs(held-previous));previous=held
    assert str(nav.quantize(Decimal('0.00000001')))==score['final_nav']
    assert score['beats_baseline'] is False and score['deflation_inputs']['observations']==5
