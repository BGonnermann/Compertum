"""Stage E7, engine environment lane: one bounded GEPA run with scripted roles improves the prompts and writes candidates for the owner.

Every evaluation is a real supervised cycle (sandbox jobs included). Every reflection call goes through the E1 client under
the run's request limit. The config prompts are never touched by the run; the owner's apply command copies a candidate.
Skipped in the product environment and reported as skipped.
"""
import json
from pathlib import Path
import pytest
deepagents=pytest.importorskip('deepagents');gepa=pytest.importorskip('gepa')
from test_ai_manual import bridge  # noqa: E402,F401  (fixture)
from test_ai_models_interface import FLOOR,roles  # noqa: E402
from test_engine_acceptance import tiers  # noqa: E402,F401  (fixture)
from test_engine_limits import set_research_state  # noqa: E402
from test_engine_roles import role_server,root,verification  # noqa: E402,F401  (fixtures)
from test_engine_run import project  # noqa: E402,F401  (fixture)
from compertum.ai.engine.gepa_run import PROMPTS_DIR,apply_prompts,run_gepa  # noqa: E402
from compertum.ai.engine.ledger import EngineLedger  # noqa: E402
from compertum.ai.engine.limits import RunLimits  # noqa: E402
from compertum.ai.engine.market import market_csv,split_market_tiers,synthetic_market  # noqa: E402
from compertum.ai.engine.prompts import COMPONENT_FILES,COMPONENTS,ROLES,load_prompt  # noqa: E402
from compertum.ai.engine import roles as roles_module  # noqa: E402
from compertum.ai.models import StoreLedger  # noqa: E402
from compertum.runtime.errors import RuntimeRefused  # noqa: E402

PROJECT=Path(__file__).resolve().parents[1]


def markets_for(tiers):
    rows=synthetic_market(16,500,planted={'kind':'momentum','window':5,'strength':0.004});train,validation,_=split_market_tiers(rows)
    return [{**{k:tiers[k] for k in ('train_csv','validation_csv','validation_rows')},'label':'seed 12'},
            {'train_csv':market_csv(train),'validation_csv':market_csv(validation),'validation_rows':validation,'label':'seed 16'}]


def start(bridge,project,root,verification,markets,port,limits,**extra):
    b,_=bridge
    return run_gepa(store=b.store,lease=b.storage.lease,project_root=project,sandbox_root=root,verification=verification,roles=roles(port),markets=markets,
                    memory_floor_bytes=FLOOR,limits=limits,owner_approval='Owner OK for the GEPA fixture run',available_memory=lambda:FLOOR+1,**extra)


def test_gepa_run_improves_prompts_in_memory_and_writes_candidates_for_the_owner(bridge,project,root,verification,tiers):
    b,_=bridge;store=b.store;set_research_state(store,'RUNNING');ledger=EngineLedger(store)
    assert roles_module.ROLES==ROLES and roles_module.load_prompt is load_prompt  # one loader, re-exported
    before={role:load_prompt(project,role) for role in ROLES}
    with role_server() as (port,state):
        result=start(bridge,project,root,verification,markets_for(tiers),port,RunLimits(request_limit=200,cycle_limit=6))
    assert result['reason'] in ('CYCLE_LIMIT','GEPA_COMPLETE') and result['kind']=='gepa' and 2<=len(result['cycles'])<=6 and result['requests']==len(state['posts'])<=200
    assert result['request_invariant'] is True and all(c['status']=='COMPLETED' for c in result['cycles'])
    # Every evaluation was a real cycle on TRAIN and VALIDATION: candidates audited and queued, trials counted, no vault.
    statuses={x['status'] for c in result['cycles'] for x in c['candidates']};assert statuses<={'QUEUED','REJECTED_AUDIT','REJECTED_DEFLATED','REJECTED'} and 'QUEUED' in statuses
    assert ledger.total_trials()==sum(len(c['candidates']) for c in result['cycles']) and ledger.looks()==[]
    assert {c['market'] for c in result['cycles']}<={'seed 12','seed 16'} and all(c['run_id']==result['run_id'] for c in ledger.cycles())
    # Reflection went through the E1 client and was recorded; the proposed prompts carry the role marker.
    proposals=ledger.steps(result['run_id']+':gepa');assert proposals and all(p['kind']=='proposal' and p['phase']=='PROPOSED' and p['changed'] for p in proposals)
    reflections=[r for r in StoreLedger(store).rows() if str(r.get('purpose','')).startswith('gepa-reflect-')];assert len(reflections)==len(proposals) and all(r['status']=='COMPLETED' for r in reflections)
    # Candidates are written under state/engine/prompts; the config prompts are unchanged.
    prompts=result['prompts'];folder=Path(prompts['folder'])
    assert folder.is_relative_to(project/PROMPTS_DIR) and prompts['candidate_count']>=2 and len(prompts['mean_scores'])==prompts['candidate_count']==len(prompts['scores'])
    record=json.loads((folder/'result.json').read_bytes());assert record['run_id']==result['run_id'] and record['best_index']==prompts['best_index'] and record['reason']==result['reason']
    assert sum(len(s) for s in prompts['scores'])==len(result['cycles'])  # every evaluation scored exactly one candidate
    for index in range(prompts['candidate_count']):
        for role in ROLES: assert (folder/f'candidate-{index}'/f'{role}.md').read_text(encoding='utf-8').startswith(f'ROLE: {role}\n')
    assert (folder/'candidate-0'/'director.md').read_text(encoding='utf-8')==before['director'] and {role:load_prompt(project,role) for role in ROLES}==before
    changed=any((folder/f'candidate-{i}'/f'{role}.md').read_text(encoding='utf-8')!=before[role] for i in range(1,prompts['candidate_count']) for role in ROLES);assert changed
    # START and END rows, the summary, and the owner's apply command.
    rows=ledger.run_rows(result['run_id']);assert rows[0]['kind']=='gepa' and rows[0]['markets']==['seed 12','seed 16'] and rows[1]['reason']==result['reason'] and rows[1]['proposals']==len(proposals)
    assert rows[1]['prompt_candidates']==prompts['candidate_count'] and f"ended, reason {result['reason']}" in Path(result['summary_path']).read_text(encoding='utf-8')
    applied=apply_prompts(project,result['run_id'],1);assert set(applied['applied_sha256'])==set(COMPONENTS) and load_prompt(project,'director')!=before['director']
    assert {role:load_prompt(PROJECT,role) for role in ROLES}=={role:load_prompt(PROJECT,role) for role in ROLES}  # master's config untouched


def test_a_longer_gepa_run_rewrites_the_firms_slots_too(bridge,project,root,verification,tiers):
    """Owner direction, 26 October 2026: GEPA improves the firm, not only its prompts. In turn it rewrites the four prompts, then the routing,
    the settings, the analysis tool and the starter. Every candidate is written with all eight files; the tool and starter run only in the sandbox."""
    b,_=bridge;store=b.store;set_research_state(store,'RUNNING');ledger=EngineLedger(store)
    (project/'config'/'engine.toml').write_text('[run]\nrequest_hard_maximum = 2000\n',encoding='utf-8')  # room for eight rewrites in this test project
    with role_server() as (port,state):
        result=start(bridge,project,root,verification,markets_for(tiers),port,RunLimits(request_limit=2000,cycle_limit=40))
    assert result['reason'] in ('CYCLE_LIMIT','GEPA_COMPLETE') and all(c['status']=='COMPLETED' for c in result['cycles'])
    proposals=ledger.steps(result['run_id']+':gepa');roles=[p['role'] for p in proposals]
    assert {'routing','settings','tool','starter'}<=set(roles) and all(p['phase']=='PROPOSED' for p in proposals)
    reflections=[r for r in StoreLedger(store).rows() if str(r.get('purpose','')).startswith('gepa-reflect-')]
    assert {r['purpose']:r['role'] for r in reflections if r['purpose'] in ('gepa-reflect-tool','gepa-reflect-starter','gepa-reflect-settings')}=={
        'gepa-reflect-tool':'mathematician','gepa-reflect-starter':'engineer','gepa-reflect-settings':'director'}
    folder=Path(result['prompts']['folder'])
    for index in range(result['prompts']['candidate_count']):
        assert sorted(p.name for p in (folder/f'candidate-{index}').iterdir())==sorted(COMPONENT_FILES.values())
    tools={(folder/f'candidate-{i}'/'tool.py').read_text(encoding='utf-8') for i in range(result['prompts']['candidate_count'])}
    assert any(t.startswith("print('fixture tool'") for t in tools)  # the fenced reply was unwrapped and kept
    # Every cycle ran the tool in the sandbox under its own run ID, apart from the candidates' runs.
    assert all(ledger.runs(c['cycle_id']+'-tool') for c in result['cycles'])
    # Step S3: GEPA's run keeps its transcript, reflection calls included, and marks it as allowed for training (practice markets only).
    saved=[json.loads(line) for line in (project/'state'/'engine'/'transcripts'/f"{result['run_id']}.jsonl").read_text(encoding='utf-8').splitlines()]
    assert len(saved)==result['requests'] and all(x['training_allowed'] is True and x['run_purpose']=='gepa' for x in saved)
    assert any(str(x['purpose']).startswith('gepa-reflect-') for x in saved)


def test_gepa_run_stops_at_the_request_limit_and_records_the_reason(bridge,project,root,verification,tiers):
    b,_=bridge;store=b.store;set_research_state(store,'RUNNING');ledger=EngineLedger(store)
    with role_server() as (port,state):
        result=start(bridge,project,root,verification,markets_for(tiers),port,RunLimits(request_limit=12,cycle_limit=6))
    assert result['reason']=='REQUEST_LIMIT' and result['requests']==12==len(state['posts'])
    # The candidates seen so far are still written (the seed only), marked with the stop reason.
    assert result['prompts']['candidate_count']==1 and result['prompts']['reason']=='REQUEST_LIMIT' and result['prompts']['gepa'] is None
    rows=ledger.run_rows(result['run_id']);assert rows[1]['reason']=='REQUEST_LIMIT' and rows[1]['prompts_folder']==result['prompts']['folder']
    assert result['cycles'] and (result['cycles'][-1]['stop_code']=='AI_REQUEST_BUDGET' or rows[1]['proposals']>0)  # the limit hit inside a cycle or inside a reflection call
    with role_server(mode='badprompt') as (port,state):
        with pytest.raises(RuntimeRefused,match='^ENGINE_RUN_LIMITS_DENIED$'): start(bridge,project,root,verification,markets_for(tiers),port,RunLimits(request_limit=50,hour_limit=1))
