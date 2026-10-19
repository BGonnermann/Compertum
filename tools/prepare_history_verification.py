"""Prepare fresh, bounded history checks without modifying consumed attempts."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
PRIOR = ROOT/'.cache/test-runs/m5-local-economics-20261017-01/ai-review-verification-preparation02'
WORK = PRIOR.with_name('ai-history-preparation01')
EVIDENCE = ROOT/'artifacts/ai/history-verification-20261019-01'
CAPACITY = 'ai-history-capacity01'
LABELS = ('ai-history-red01', 'ai-history-tests01', 'ai-history-tests02', 'ai-history-tests03')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def change(text, old, new):
    if text.count(old) != 1:
        raise ValueError('PREPARATION_SOURCE_CHANGED: '+old[:60])
    return text.replace(old, new)


def pins():
    paths = ['src/compertum/ai/manual.py', 'src/compertum/ai/experiment.py',
        'src/compertum/campaign_contract.py', 'src/compertum/evaluation_protocol.py',
        'src/compertum/simulation/runs.py', 'src/compertum/simulation/campaign_runs.py',
        'src/compertum/simulation/campaign_record.py', 'src/compertum/modeling/campaign.py',
        'src/compertum/development_seals.py', 'src/compertum/clean_pair.py',
        'src/compertum/clean_registration.py', 'src/compertum/evaluation_seals.py',
        'tests/test_ai_research_history.py', 'tests/test_ai_review_plan_storage.py',
        'tests/test_ai_manual.py', 'tests/test_ai_experiment_translation.py',
        'tests/helpers/ai_fixture.py', 'tests/helpers/saved_campaign_fixture.py',
        'tests/helpers/model_campaign_fixture.py', 'tests/test_campaign_record.py',
        'tests/test_development_seals.py',
        'tools/evidence_folder.py', 'tools/fresh_namespace_usage.py',
        'tools/prepare_history_verification.py', 'tools/run_history_tests.py']
    optional = ROOT/'src/compertum/ai/history.py'
    if optional.exists():
        paths.append(str(optional.relative_to(ROOT)).replace('\\', '/'))
    paths.extend(str((WORK/name).relative_to(ROOT)).replace('\\', '/')
        for name in ('run_bounded.py', 'capacity_census.py'))
    return {name: sha(ROOT/name) for name in paths}


def prepare():
    from evidence_folder import regular_folder
    regular_folder(WORK.parent)
    regular_folder(EVIDENCE.parent)
    WORK.mkdir(exist_ok=False)
    EVIDENCE.mkdir(exist_ok=False)
    regular_folder(WORK)
    regular_folder(EVIDENCE)
    source = (PRIOR/'run_bounded.py').read_text()
    assert sha(PRIOR/'run_bounded.py') == 'a628bd33ee56e987bd93462c70d3b33dc052503818e784a8e226fafe383f707c'
    source = source.replace('ai-review-capacity02', CAPACITY)
    source = change(source, "AI=ROOT/'artifacts/ai/review-plan-verification-20261018-01'",
        "OLD_AI=ROOT/'artifacts/ai/review-plan-verification-20261018-01'\nAI=ROOT/'artifacts/ai/history-verification-20261019-01'")
    source = change(source, "('ai-review-tests01','ai-review-tests02','ai-review-tests03','ai-review-map01')", repr(LABELS))
    source = change(source, "(plan['cpus'],plan['memory_mib'],plan['seconds']) != (1,128,120)",
        "(plan['cpus'],plan['memory_mib'],plan['seconds']) != (1,128 if kind=='capacity' else 4096,120)")
    source = change(source, 'usage_roots.append(AI)\nassert len(usage_roots)==30',
        'usage_roots.extend([OLD_AI,AI])\nassert len(usage_roots)==31')
    source = change(source, "evidence.unused_allowance(values[-2])\n    if values[-1]>1048576:raise RuntimeError('AI_EVIDENCE_LIMIT')",
        "evidence.unused_allowance(values[-3])\n    if values[-2]>1048576:raise RuntimeError('OLD_AI_EVIDENCE_LIMIT')\n    if values[-1]>2097152:raise RuntimeError('AI_EVIDENCE_LIMIT')")
    source = change(source, 'limit=8388608 if kind==\'capacity\' else 1048576',
        'limit=8388608 if kind==\'capacity\' else 2097152')
    census = (PRIOR/'capacity_census.py').read_text()
    assert sha(PRIOR/'capacity_census.py') == '5fc921cb4bc7e0f4cce4048be896ed2e0238c0cfaf2cb826d5fe4d2b1caa9449'
    census = census.replace('ai-review-capacity02', CAPACITY)
    census = change(census, "extra_prefixes['artifacts/ai/review-plan-verification-20261018-01']=1",
        "extra_prefixes['artifacts/ai/review-plan-verification-20261018-01']=1\nextra_prefixes['artifacts/ai/history-verification-20261019-01']=2")
    for name, value in [('run_bounded.py', source), ('capacity_census.py', census)]:
        compile(value, name, 'exec')
        with (WORK/name).open('x', encoding='utf-8') as stream:
            stream.write(value)
    write_job(CAPACITY)


def write_job(label):
    if label not in (CAPACITY, *LABELS):
        raise ValueError('LABEL_DENIED')
    capacity = label == CAPACITY
    plan = json.loads((ROOT/'artifacts/ai/review-plan-verification-20261018-01/ai-review-tests03.job.json').read_text())
    for key in ('repair_history', 'fresh_capacity_sha256', 'fresh_closure_sha256'):
        plan.pop(key, None)
    plan.update(memory_mib=128 if capacity else 4096, temp=str(WORK),
        resource_wrapper_sha256=sha(WORK/'run_bounded.py'), current_inputs=pins(),
        args=[str(WORK/'capacity_census.py'), 'capacity', label] if capacity else [str(ROOT/'tools/run_history_tests.py'), label])
    if not capacity:
        folder = ROOT/'artifacts/m5/simulated-evidence-next-01'
        plan['fresh_capacity_sha256'] = sha(folder/(CAPACITY+'-result.json'))
        plan['fresh_closure_sha256'] = sha(folder/(CAPACITY+'.closure.json'))
    folder = ROOT/'artifacts/m5/simulated-evidence-next-01' if capacity else EVIDENCE
    raw = (json.dumps(plan, indent=2)+'\n').encode()
    if len(raw) > 8192:
        raise ValueError('JOB_SIZE_BOUND')
    with (folder/(label+'.job.json')).open('xb') as stream:
        stream.write(raw)
    print(json.dumps(dict(label=label, source_files=len(plan['current_inputs']), job_bytes=len(raw))))


if __name__ == '__main__':
    prepare() if sys.argv[1] == 'prepare' else write_job(sys.argv[1])
