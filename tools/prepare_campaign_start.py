"""Prepare distinct start checks with the existing registration resource limits."""
import sys

import prepare_registration_completion as previous

prior = previous.prior
ROOT = previous.ROOT
WORK = previous.WORK.with_name('ai-start-preparation03')
CAPACITY = 'ai-start-capacity02'
SUITES = {
    'ai-start-red01': ['tests/test_ai_campaign_start.py::test_start_operation_exists'],
    'ai-start-tests01': ['tests/test_ai_campaign_start.py'],
    'ai-start-tests02': ['tests/test_ai_campaign_registration.py', 'tests/test_contracts.py'],
    'ai-start-tests03': ['tests/test_campaign_pending_cleanup.py', 'tests/test_campaign_record.py'],
    'ai-start-tests04': ['tests/test_ai_campaign_start.py'],
}
original_pins = previous.pins


def pins():
    configure()
    result = original_pins()
    for name in ('tools/prepare_campaign_start.py', 'tests/test_ai_campaign_start.py',
                 'src/compertum/campaign_operation.py', 'src/compertum/ai/start.py',
                 'tests/helpers/review_start_restart.py'):
        if (ROOT/name).exists():
            result[name] = prior.sha(ROOT/name)
    return result


def prepare(*, capacity=True):
    from evidence_folder import regular_folder
    regular_folder(WORK.parent)
    WORK.mkdir(exist_ok=False)
    regular_folder(WORK)
    old = previous.WORK
    for name in ('run_bounded.py', 'capacity_census.py', 'run_tests.py'):
        source = (old/name).read_text().replace('ai-registration-capacity11', CAPACITY)
        if name == 'run_bounded.py':
            source = prior.change(source, repr(tuple(previous.SUITES)), repr(tuple(SUITES)))
        if name == 'run_tests.py':
            source = prior.change(source, 'SUITES = '+repr(previous.SUITES), 'SUITES = '+repr(SUITES))
            source = source.replace('from prepare_registration_completion import pins', 'from prepare_campaign_start import pins')
        compile(source, name, 'exec')
        with (WORK/name).open('x', encoding='utf-8') as stream:
            stream.write(source)
    configure()
    if capacity:
        previous.write_job(CAPACITY)


def configure():
    previous.WORK = prior.WORK = WORK
    previous.CAPACITY = prior.CAPACITY = CAPACITY
    previous.SUITES = SUITES
    previous.pins = prior.pins = pins


if __name__ == '__main__':
    if sys.argv[1] == 'prepare':
        prepare()
    elif sys.argv[1] == 'extend':
        prepare(capacity=False)
    else:
        configure()
        previous.write_job(sys.argv[1])
