"""Prepare distinct registration checks using the existing reviewed resource wrapper."""
import json
import sys
from pathlib import Path

import prepare_registration_verification as prior

ROOT = prior.ROOT
PREVIOUS = prior.WORK
WORK = PREVIOUS.with_name('ai-registration-preparation11')
CAPACITY = 'ai-registration-capacity11'
SUITES = {
    'ai-registration-tests04': ['tests/test_ai_campaign_registration.py'],
    'ai-registration-tests05': ['tests/test_contracts.py', 'tests/test_ai_research_history.py',
                                'tests/test_prepared_campaign.py'],
    'ai-registration-tests06': ['tests/test_campaign_record.py', 'tests/test_development_seals.py'],
}
original_pins = prior.pins


def pins():
    result = original_pins()
    for name in ('src/compertum/domain.py', 'tests/test_contracts.py',
                 'tools/prepare_registration_completion.py',
                 str((WORK/'run_tests.py').relative_to(ROOT)).replace('\\', '/')):
        result[name] = prior.sha(ROOT/name)
    return result


prior.WORK = WORK
prior.CAPACITY = CAPACITY
prior.LABELS = tuple(SUITES)
prior.pins = pins


def write_job(label):
    # Keep the existing bounded writer and select this attempt's test executable.
    capacity = label == CAPACITY
    if label not in (CAPACITY, *SUITES):
        raise ValueError('LABEL_DENIED')
    plan = json.loads((ROOT/'artifacts/ai/review-plan-verification-20261018-01/ai-review-tests03.job.json').read_text())
    for key in ('repair_history', 'fresh_capacity_sha256', 'fresh_closure_sha256'):
        plan.pop(key, None)
    plan.update(memory_mib=128 if capacity else 4096, temp=str(WORK),
                resource_wrapper_sha256=prior.sha(WORK/'run_bounded.py'), current_inputs=pins(),
                args=[str(WORK/'capacity_census.py'), 'capacity', label] if capacity else [str(WORK/'run_tests.py'), label])
    if capacity:
        plan['current_inputs'] = {str(p.relative_to(ROOT)).replace('\\','/'): prior.sha(p)
            for p in (WORK/'run_bounded.py', WORK/'capacity_census.py', ROOT/'tools/evidence_folder.py', ROOT/'tools/fresh_namespace_usage.py')}
    else:
        gate = ROOT/'artifacts/m5/simulated-evidence-next-01'
        plan['fresh_capacity_sha256'] = prior.sha(gate/(CAPACITY+'-result.json'))
        plan['fresh_closure_sha256'] = prior.sha(gate/(CAPACITY+'.closure.json'))
    folder = ROOT/'artifacts/m5/simulated-evidence-next-01' if capacity else prior.EVIDENCE
    raw = (json.dumps(plan, indent=2)+'\n').encode()
    if len(raw) > (4096 if capacity else 8192):
        raise ValueError('JOB_SIZE_BOUND')
    from evidence_folder import EvidenceFolder, output_bindings
    bindings = output_bindings(json.loads((ROOT/'docs/M5_EVIDENCE_FOLDER_PROPOSAL.json').read_text()), 'capacity', label) if capacity else {
        label+'.job.json':8192, label+'-source-pins.json':8192, label+'-results.xml':65536,
        label+'-stdout.log':32768, label+'-stderr.log':16384, label+'.closure.json':65536}
    output = EvidenceFolder(folder, bindings, lambda: None, limit=8388608 if capacity else 2097152,
                            writable={label+'.job.json'})
    with output.open(label+'.job.json') as stream:
        stream.write(raw)
    output.finish()
    print(json.dumps(dict(label=label, source_files=len(plan['current_inputs']), job_bytes=len(raw))))


def prepare():
    from evidence_folder import regular_folder
    regular_folder(WORK.parent)
    WORK.mkdir(exist_ok=False)
    regular_folder(WORK)
    saved = {}
    for folder in (prior.EVIDENCE, ROOT/'artifacts/ai/review-plan-verification-20261018-01', PREVIOUS):
        for p in folder.iterdir():
            if p.is_file():
                saved[str(p.relative_to(ROOT)).replace('\\','/')] = prior.sha(p)
    (WORK/'prior-evidence-pins.json').write_text(json.dumps(saved, indent=2)+'\n')
    wrapper = (PREVIOUS/'run_bounded.py').read_text().replace('ai-registration-capacity07', CAPACITY)
    wrapper = prior.change(wrapper, "('ai-registration-red01', 'ai-registration-tests01', 'ai-registration-tests02', 'ai-registration-tests03')", repr(tuple(SUITES)))
    census = (PREVIOUS/'capacity_census.py').read_text().replace('ai-registration-capacity07', CAPACITY)
    # The contract test changed with the receipt repair. Check the historical
    # release against its retained archive, as already done for source files.
    # Current contract tests have their own exact hashes in every new test job.
    census = prior.change(census, "        if not name.startswith('src/'):",
                          "        if not name.startswith('src/') and name != 'tests/test_contracts.py':")
    runner = (ROOT/'tools/run_registration_tests.py').read_text()
    runner = prior.change(runner, 'ROOT = Path(__file__).resolve().parents[1]', 'ROOT = Path('+repr(str(ROOT))+')')
    runner = prior.change(runner, "LABELS = ('ai-registration-red01', 'ai-registration-tests01', 'ai-registration-tests02', 'ai-registration-tests03')", 'SUITES = '+repr(SUITES)+'\nLABELS = tuple(SUITES)')
    runner = prior.change(runner, 'from prepare_registration_verification import pins as source_pins', 'from prepare_registration_completion import pins as source_pins')
    start = runner.index("            tests = ['tests/test_ai_campaign_registration.py::test_registration_operation_exists']")
    end = runner.index('            code = pytest.main(', start)
    runner = runner[:start]+'            tests = SUITES[label]\n'+runner[end:]
    for name, source in (('run_bounded.py',wrapper), ('capacity_census.py',census), ('run_tests.py',runner)):
        compile(source, name, 'exec')
        with (WORK/name).open('x', encoding='utf-8') as stream:
            stream.write(source)
    write_job(CAPACITY)


if __name__ == '__main__':
    prepare() if sys.argv[1] == 'prepare' else write_job(sys.argv[1])
