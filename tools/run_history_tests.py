"""Run the bounded synthetic history and affected source checks."""
import builtins
import contextlib
import hashlib
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
from evidence_folder import EvidenceFolder, TextOutput, regular_folder


LABELS = ('ai-history-red01', 'ai-history-tests01', 'ai-history-tests02', 'ai-history-tests03')


class PytestOutput(TextOutput):
    """Tell pytest that the bounded log is a file, not a terminal."""

    def isatty(self):
        return False


def fresh_test_folder(root, label):
    """Claim a fresh parent so pytest cannot remove older evidence."""
    if label not in LABELS:
        raise ValueError('TEST_LABEL_DENIED')
    parent = root/'.cache/test-runs/m5-local-economics-20261017-01'
    regular_folder(parent)
    target = parent/label
    if os.path.lexists(target):
        raise FileExistsError('PRESERVE_EXISTING_TEST_FOLDER')
    target.mkdir()
    regular_folder(target)
    return target/'pytest'


def run(label):
    import pytest
    import time
    if label not in LABELS:
        raise ValueError('TEST_LABEL_DENIED')
    started = time.monotonic()
    def poll():
        if time.monotonic()-started >= 110:
            raise TimeoutError('TEST_DEADLINE')
    folder = ROOT/'artifacts/ai/history-verification-20261019-01'
    bindings = {label+'.job.json':8192, label+'-source-pins.json':8192,
        label+'-results.xml':65536, label+'-stdout.log':32768,
        label+'-stderr.log':16384, label+'.closure.json':65536}
    output = EvidenceFolder(folder, bindings, poll, limit=2097152,
        writable={label+'-source-pins.json',label+'-results.xml',label+'-stdout.log'})
    base = fresh_test_folder(ROOT, label)
    from prepare_history_verification import pins as source_pins
    pins = source_pins()
    output.save(label+'-source-pins.json', pins)
    xml = folder/(label+'-results.xml')
    original_open = builtins.open
    def bounded_open(file, mode='r', *args, **kwargs):
        if str(file) == str(xml) and mode in ('w', 'wb'):
            stream = output.open(xml.name)
            return stream if mode == 'wb' else TextOutput(stream)
        return original_open(file, mode, *args, **kwargs)
    with PytestOutput(output.open(label+'-stdout.log')) as log:
        with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log), patch('builtins.open', bounded_open):
            tests = ['tests/test_ai_research_history.py']
            if label != 'ai-history-red01':
                tests += ['tests/test_ai_review_plan_storage.py', 'tests/test_ai_manual.py',
                    'tests/test_ai_experiment_translation.py', 'tests/test_campaign_record.py',
                    'tests/test_development_seals.py']
            if label == 'ai-history-tests02':
                tests = ['tests/test_ai_research_history.py::test_sealed_history_uses_recorded_identity_while_dispatch_refuses']
            code = pytest.main(['-p', 'no:cacheprovider', '-q', *tests,
                '--basetemp='+str(base), '--junitxml='+str(xml)])
    assert all(hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==pin for name,pin in pins.items())
    output.finish()
    return code


if __name__ == '__main__':
    sys.exit(run(sys.argv[1]))
