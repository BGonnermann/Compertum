"""Prepare fresh capacity evidence for the approved supervised cycle.

Execution jobs remain unavailable until capacity and native preparation review pass.
"""
import json
import sys

import prepare_campaign_start as previous

ROOT = previous.ROOT
WORK = previous.WORK.with_name('research-cycle-preparation03')
CAPACITY = 'research-cycle-capacity03'
SOURCE_WORK = WORK.with_name('research-cycle-source-preparation11')
SUITES = {
    'cycle-control-red05': ['tests/test_research_cycle_control.py::test_waiting_control_preserves_unrelated_work',
                          'tests/test_research_cycle_control.py::test_all_approval_refusals_share_unchanged_fixture'],
    'cycle-control08': ['tests/test_research_cycle.py',
                       'tests/test_research_cycle_control.py::test_waiting_control_preserves_unrelated_work',
                       'tests/test_research_cycle_control.py::test_all_approval_refusals_share_unchanged_fixture',
                       'tests/test_research_cycle_control.py::test_stop_claim_failure_rolls_back_state',
                       'tests/test_research_cycle_control.py::test_failed_pause_latches_dispatch_across_restart'],
    'cycle-control-red03': ['tests/test_research_cycle_control.py::test_waiting_control_preserves_unrelated_work'],
    'cycle-control05': ['tests/test_research_cycle_control.py::test_waiting_control_preserves_unrelated_work'],
    'cycle-control-red02': ['tests/test_research_cycle_control.py::'+name for name in (
        'test_stop_claim_failure_rolls_back_state', 'test_pause_waiting_cycle_is_confirmed_idle',
        'test_failed_pause_latches_dispatch_across_restart')],
    'cycle-control04': ['tests/test_research_cycle_control.py::'+name for name in (
        'test_stop_claim_failure_rolls_back_state', 'test_pause_waiting_cycle_is_confirmed_idle',
        'test_failed_pause_latches_dispatch_across_restart', 'test_pause_resume_stop_keep_original_deadline')],
    'cycle-records-red01': ['tests/test_research_cycle.py'],
    'cycle-records-red02': ['tests/test_research_cycle.py'],
    'cycle-records01': ['tests/test_research_cycle.py'],
    'cycle-records-red03': [
        'tests/test_research_cycle.py::test_later_capacity_loss_refuses_mutation',
        'tests/test_research_cycle.py::test_sequence_limit_preserves_pause_and_stop'],
    'cycle-records02': ['tests/test_research_cycle.py', 'tests/test_contracts.py'],
    'cycle-control-red01': ['tests/test_research_cycle_control.py'],
    'cycle-control01': ['tests/test_research_cycle_control.py::'+name for name in (
        'test_duplicate_cycle_request_has_one_record', 'test_second_cycle_cannot_claim_run',
        'test_cycle_claim_blocks_direct_dispatch', 'test_pause_resume_stop_keep_original_deadline',
        'test_foreign_operator_cannot_pause')],
    'cycle-control02': ['tests/test_research_cycle_control.py::test_approval_refusal_has_no_cycle_effect['+fault+']'
        for fault in ('approval', 'operator', 'generation', 'fingerprint', 'input', 'plan')],
    'cycle-control03': ['tests/test_research_cycle_control.py::test_approval_refusal_has_no_cycle_effect['+fault+']'
        for fault in ('seal', 'schedule', 'allowance', 'first_start', 'deadline', 'long_deadline')],
}


def source_bindings(label):
    # Preserve complete closure records. Only diagnostic output ceilings shrink.
    return {label+'.job.json':8192, label+'-source-pins.json':8192,
        label+'-results.xml':8192, label+'-stdout.log':4096,
        label+'-stderr.log':4096, label+'.closure.json':65536}


def write_source_job(label):
    from evidence_folder import EvidenceFolder
    plan = json.loads((ROOT/'artifacts/ai/review-plan-verification-20261018-01/ai-review-tests03.job.json').read_text())
    for key in ('repair_history', 'fresh_capacity_sha256', 'fresh_closure_sha256'):
        plan.pop(key, None)
    gate = ROOT/'artifacts/m5/simulated-evidence-next-01'
    plan.update(memory_mib=4096, temp=str(SOURCE_WORK),
        resource_wrapper_sha256=previous.prior.sha(SOURCE_WORK/'run_bounded.py'),
        current_inputs=pins(), args=[str(SOURCE_WORK/'run_tests.py'), label],
        fresh_capacity_sha256=previous.prior.sha(gate/(CAPACITY+'-result.json')),
        fresh_closure_sha256=previous.prior.sha(gate/(CAPACITY+'.closure.json')))
    raw = (json.dumps(plan, indent=2)+'\n').encode()
    if len(raw) > 8192:
        raise ValueError('JOB_SIZE_BOUND')
    output = EvidenceFolder(previous.prior.EVIDENCE, source_bindings(label), lambda: None,
        limit=2097152, writable={label+'.job.json'})
    with output.open(label+'.job.json') as stream:
        stream.write(raw)
    output.finish()


def pins():
    baseline = json.loads((previous.prior.EVIDENCE / 'ai-start-tests04-source-pins.json').read_text())
    names = set(baseline) | {'tools/prepare_research_cycle.py', 'tests/test_research_cycle.py', 'tests/test_ai_manual.py'}
    names.update(path.relative_to(ROOT).as_posix() for path in
                 (SOURCE_WORK/'run_tests.py', SOURCE_WORK/'run_bounded.py'))
    for name in ('src/compertum/ai/cycle_record.py', 'schemas/research_cycle.v1.json',
                 'src/compertum/ai/cycle.py', 'src/compertum/ai/cycle_ownership.py',
                 'tests/test_research_cycle_control.py', 'src/compertum/auditor.py',
                 'src/compertum/campaign_review.py'):
        if (ROOT / name).exists():
            names.add(name)
    return {name: previous.prior.sha(ROOT / name) for name in sorted(names)}


def prepare_source(label):
    if label not in SUITES:
        raise ValueError('SOURCE_LABEL_DENIED')
    from evidence_folder import regular_folder
    regular_folder(SOURCE_WORK.parent)
    if not SOURCE_WORK.exists():
        SOURCE_WORK.mkdir()
        for name in ('run_bounded.py', 'run_tests.py'):
            source = (previous.WORK / name).read_text().replace(previous.CAPACITY, CAPACITY)
            if name == 'run_bounded.py':
                source = previous.prior.change(source, repr(tuple(previous.SUITES)), repr(tuple(SUITES)))
                source = previous.prior.change(source, "    record['phase']='initial_count'\n    capacity();last_capacity=time.monotonic()",
                    "    record['phase']='initial_count'\n    capacity();last_capacity=time.monotonic()\n"
                    "    if record['maximum_economic_source_bytes']+32*1024**2>448*1024**2:\n"
                    "        raise RuntimeError('SOURCE_TEST_SPACE_UNAVAILABLE')")
            else:
                source = previous.prior.change(source, 'SUITES = ' + repr(previous.SUITES), 'SUITES = ' + repr(SUITES))
                source = source.replace('from prepare_campaign_start import pins', 'from prepare_research_cycle import pins')
            # Fresh scripts share the same smaller output reservations as the job writer.
            start = source.index('    bindings={' if name == 'run_bounded.py' else '    bindings = {')
            end = source.index('}', start)+1
            variable = 'name' if name == 'run_bounded.py' else 'label'
            source = source[:start]+('    from prepare_research_cycle import source_bindings\n'
                '    bindings = source_bindings('+variable+')')+source[end:]
            compile(source, name, 'exec')
            with (SOURCE_WORK / name).open('x', encoding='utf-8') as stream:
                stream.write(source)
    regular_folder(SOURCE_WORK)
    previous.previous.WORK = previous.prior.WORK = SOURCE_WORK
    previous.previous.CAPACITY = previous.prior.CAPACITY = CAPACITY
    previous.previous.SUITES = SUITES
    previous.previous.pins = pins
    write_source_job(label)
    return {'label': label, 'wrapper': str(SOURCE_WORK / 'run_bounded.py'), 'kind': 'ai'}


def prepare(label):
    if label != 'capacity03':
        raise ValueError('EXECUTION_PREPARATION_NOT_REVIEWED')
    from evidence_folder import regular_folder
    regular_folder(WORK.parent)
    WORK.mkdir(exist_ok=False)
    regular_folder(WORK)
    saved = {}
    paths = []
    for directory in ('src', 'schemas', 'tests', 'tools'):
        paths.extend(p for p in (ROOT / directory).rglob('*')
                     if p.is_file() and '__pycache__' not in p.parts)
    paths.extend(p for p in previous.prior.EVIDENCE.iterdir() if p.is_file())
    paths.extend(ROOT / name for name in (
        'docs/superpowers/plans/2026-10-19-supervised-research-cycle.md',
        'docs/superpowers/specs/2026-10-19-supervised-research-cycle-design.md'))
    for path in paths:
        saved[path.relative_to(ROOT).as_posix()] = previous.prior.sha(path)
    raw = (json.dumps(saved, indent=2) + '\n').encode()
    if len(raw) > 1024 * 1024:
        raise ValueError('INPUT_FINGERPRINT_BOUND')
    with (WORK / 'starting-inputs.json').open('xb') as stream:
        stream.write(raw)
    for name in ('run_bounded.py', 'capacity_census.py', 'run_tests.py'):
        source = (previous.WORK / name).read_text().replace(previous.CAPACITY, CAPACITY)
        if name == 'run_bounded.py':
            source = previous.prior.change(source, repr(tuple(previous.SUITES)), '()')
        if name == 'capacity_census.py':
            anchor = "        charged = capacity_gate(result)"
            replacement = """        result['research_cycle_space'] = dict(
            used_bytes=economic_source_bytes,
            namespace_limit_bytes=448*1024**2,
            remaining_bytes=448*1024**2-economic_source_bytes,
            acceptance_hold_bytes=128*1024**2,
            preparation_hold_bytes=4*1024**2,
            shortfall_bytes=max(0,economic_source_bytes+132*1024**2-448*1024**2),
            evidence_used_bytes=extra_usage['artifacts/ai/history-verification-20261019-01'],
            evidence_limit_bytes=2*1024**2,
            evidence_hold_bytes=512*1024,
            evidence_remaining_bytes=2*1024**2-extra_usage['artifacts/ai/history-verification-20261019-01'],
            evidence_shortfall_bytes=max(0,extra_usage['artifacts/ai/history-verification-20261019-01']+512*1024-2*1024**2))
        # Keep the complete census even when the requested folder cannot fit.
        cycle_space = result['research_cycle_space']
        charged = capacity_gate(result)"""
            source = previous.prior.change(source, anchor, replacement)
            source = previous.prior.change(source,
                "          production_admission=False,ordinary_runtime=False,",
                "          production_admission=False,ordinary_runtime=False,\n"
                "          research_cycle_space=cycle_space,\n"
                "          research_cycle_admitted=False,\n"
                "          allocated_space_only=(cycle_space['shortfall_bytes']==0 and cycle_space['evidence_shortfall_bytes']==0),")
        compile(source, name, 'exec')
        with (WORK / name).open('x', encoding='utf-8') as stream:
            stream.write(source)
    # Reuse the reviewed bounded manifest writer. Capacity jobs pin their own
    # scripts and perform the complete census before any execution admission.
    previous.previous.WORK = previous.prior.WORK = WORK
    previous.previous.CAPACITY = previous.prior.CAPACITY = CAPACITY
    previous.previous.SUITES = {}
    previous.previous.pins = lambda: {}
    previous.previous.write_job(CAPACITY)
    return {'label': CAPACITY, 'wrapper': str(WORK / 'run_bounded.py')}


def finalize_capacity():
    """Combine the census with the stricter rounded folder charge."""
    folder = ROOT/'artifacts/m5/simulated-evidence-next-01'
    result_path = folder/(CAPACITY+'-result.json')
    closure_path = folder/(CAPACITY+'.closure.json')
    result = json.loads(result_path.read_text())
    closed = json.loads(closure_path.read_text())
    if (result['status'] != 'CAPACITY_GATE_PASSED' or closed['status'] != 'PASSED'
            or closed['exit_code'] != 0 or not closed['exit_observed'] or closed['remaining_children']):
        raise ValueError('CAPACITY_NOT_ACCEPTED')
    space = result['research_cycle_space']
    charged = max(space['used_bytes'], closed['maximum_economic_source_bytes'])
    shortfall = max(0, charged+space['acceptance_hold_bytes']+space['preparation_hold_bytes']-space['namespace_limit_bytes'])
    value = dict(status='COMPLETE_CAPACITY_AND_FOLDER_CHECK',
        census_sha256=previous.prior.sha(result_path), closure_sha256=previous.prior.sha(closure_path),
        namespace_charged_bytes=charged, native_shortfall_bytes=shortfall,
        native_admitted=shortfall == 0 and space['evidence_shortfall_bytes'] == 0,
        source_admitted=charged+32*1024**2 <= space['namespace_limit_bytes'],
        remaining_receipt_hold_bytes=space['evidence_hold_bytes'],
        note='Census folder flag alone does not admit native work. Apply the completed wrapper charge.')
    with (WORK/'completed-admission.json').open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2)
    return value


if __name__ == '__main__':
    argument = sys.argv[1]
    print(json.dumps(finalize_capacity() if argument == 'finalize-capacity03' else
                     prepare_source(argument) if argument in SUITES else prepare(argument)))
