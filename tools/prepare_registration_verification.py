"""Prepare fresh, bounded history checks without modifying consumed attempts."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
PRIOR = ROOT/'.cache/test-runs/m5-local-economics-20261017-01/ai-history-preparation01'
WORK = PRIOR.with_name('ai-registration-preparation07')
EVIDENCE = ROOT/'artifacts/ai/history-verification-20261019-01'
CAPACITY = 'ai-registration-capacity07'
LABELS = ('ai-registration-red01', 'ai-registration-tests01', 'ai-registration-tests02', 'ai-registration-tests03')


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
        'tests/helpers/model_campaign_fixture.py', 'tests/helpers/review_registration_restart.py', 'tests/test_campaign_record.py',
        'tests/test_development_seals.py', 'tests/test_prepared_campaign.py', 'tests/test_clean_registration.py', 'tests/test_clean_pair.py', 'tests/test_environment_manifest.py', 'src/compertum/ai/history.py',
        'tools/evidence_folder.py', 'tools/fresh_namespace_usage.py',
        'tools/prepare_registration_verification.py', 'tools/run_registration_tests.py', 'tests/test_ai_campaign_registration.py', 'src/compertum/coordinator.py', 'src/compertum/research.py']
    optional = ROOT/'src/compertum/ai/registration.py'
    if optional.exists():
        paths.append(str(optional.relative_to(ROOT)).replace('\\', '/'))
    paths.extend(str((WORK/name).relative_to(ROOT)).replace('\\', '/')
        for name in ('run_bounded.py', 'capacity_census.py', 'run_tests_bounded.py') if (WORK/name).exists())
    return {name: sha(ROOT/name) for name in paths}


def prepare():
    from evidence_folder import regular_folder
    regular_folder(WORK.parent)
    regular_folder(EVIDENCE.parent)
    WORK.mkdir(exist_ok=False)
    regular_folder(WORK)
    regular_folder(EVIDENCE)
    source = (PRIOR/'run_bounded.py').read_text()
    assert sha(PRIOR/'run_bounded.py') == 'f9fb1997f05600c03c7d17772db4a73979b9ad0c1f573e33783203d047b8ca18'
    source = source.replace('ai-history-capacity01', CAPACITY)
    source = change(source, "('ai-history-red01', 'ai-history-tests01', 'ai-history-tests02', 'ai-history-tests03')", repr(LABELS))
    source = change(source, 'time.monotonic()-last_capacity>=2:', 'time.monotonic()-last_capacity>=(45 if kind=='+repr('capacity')+' else 2):')
    source = change(source, "'.cache/test-runs/m5-local-economics-20261017-01',384", "'.cache/test-runs/m5-local-economics-20261017-01',448")
    census = (PRIOR/'capacity_census.py').read_text().replace('ai-history-capacity01', CAPACITY)
    census = change(census, "if name != 'src/compertum/ai/manual.py':", "if not name.startswith('src/'):")
    census = change(census, 'economic_source_bytes<=384*1024**2', 'economic_source_bytes<=448*1024**2')
    census = change(census, '384*1024**2-economic_source_bytes', '448*1024**2-economic_source_bytes')
    census = change(census, "source_namespace='.cache/test-runs/m5-local-economics-20261017-01',source_mib=384", "source_namespace='.cache/test-runs/m5-local-economics-20261017-01',source_mib=448")
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
        args=[str(WORK/'capacity_census.py'), 'capacity', label] if capacity else [str(ROOT/'tools/run_registration_tests.py'), label])
    if capacity:
        plan['current_inputs'] = {str(path.relative_to(ROOT)).replace(chr(92), '/'): sha(path) for path in (WORK/'run_bounded.py', WORK/'capacity_census.py', ROOT/'tools/evidence_folder.py', ROOT/'tools/fresh_namespace_usage.py')}
    if not capacity:
        folder = ROOT/'artifacts/m5/simulated-evidence-next-01'
        plan['fresh_capacity_sha256'] = sha(folder/(CAPACITY+'-result.json'))
        plan['fresh_closure_sha256'] = sha(folder/(CAPACITY+'.closure.json'))
    folder = ROOT/'artifacts/m5/simulated-evidence-next-01' if capacity else EVIDENCE
    raw = (json.dumps(plan, indent=2)+'\n').encode()
    if len(raw) > (4096 if capacity else 8192):
        raise ValueError('JOB_SIZE_BOUND')
    from evidence_folder import EvidenceFolder, output_bindings
    bindings = output_bindings(json.loads((ROOT/'docs/M5_EVIDENCE_FOLDER_PROPOSAL.json').read_text()), 'capacity', label) if capacity else {
        label+'.job.json':8192, label+'-source-pins.json':8192,
        label+'-results.xml':65536, label+'-stdout.log':32768,
        label+'-stderr.log':16384, label+'.closure.json':65536}
    output = EvidenceFolder(folder, bindings, lambda: None,
        limit=8388608 if capacity else 2097152, writable={label+'.job.json'})
    with output.open(label+'.job.json') as stream:
        stream.write(raw)
    output.finish()
    print(json.dumps(dict(label=label, source_files=len(plan['current_inputs']), job_bytes=len(raw))))


if __name__ == '__main__':
    prepare() if sys.argv[1] == 'prepare' else write_job(sys.argv[1])









