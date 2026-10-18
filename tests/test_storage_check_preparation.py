"""Small fixtures for storage preparation. Never enumerate the project."""
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import unittest
import uuid
import zipfile

ROOT = Path(__file__).parents[1]


def helper():
    path = ROOT / 'tools/storage_check_diagnostics.py'
    assert path.exists(), 'PREPARED_HELPER_MISSING'
    spec = importlib.util.spec_from_file_location('storage_diagnostics', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class StoragePreparationTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(os.environ['TEMP']) / ('storage-preparation-' + uuid.uuid4().hex)
        self.root.mkdir()

    def test_zip_membership_is_built_once_per_open_archive(self):
        module = helper()
        class Archive:
            calls = 0
            def namelist(self):
                self.calls += 1
                return ['a', 'b']
            def read(self, name):
                return name.encode()
        archive = Archive()
        pins = {name: hashlib.sha256(name.encode()).hexdigest() for name in ('a', 'b', 'missing')}
        module.verify_archive_members(archive, pins)
        self.assertEqual(archive.calls, 1)

    def test_zip_verification_remains_fresh_on_second_pass(self):
        module = helper()
        target = self.root / 'source.zip'
        for content, succeeds in ((b'original', True), (b'changed', False)):
            with zipfile.ZipFile(target, 'w') as archive:
                archive.writestr('a', content)
            with zipfile.ZipFile(target) as archive:
                if succeeds:
                    module.verify_archive_members(archive, {'a': hashlib.sha256(content).hexdigest()})
                else:
                    with self.assertRaises(AssertionError):
                        module.verify_archive_members(archive, {'a': hashlib.sha256(b'original').hexdigest()})

    def test_archive_read_failure_is_not_hidden(self):
        class Archive:
            def namelist(self): return ['a']
            def read(self, name): raise PermissionError('fixture')
        with self.assertRaises(PermissionError):
            helper().verify_archive_members(Archive(), {'a': 'x'})

    def test_charge_includes_every_stream_once(self):
        module = helper()
        class Rows:
            calls = 0
            def __iter__(self):
                self.calls += 1
                return iter([{'charged': 2}, {'charged': 5}])
        streams = Rows()
        charge = module.observation_charge({'charged': 11}, streams)
        self.assertEqual([charge] * 24, [18] * 24)
        self.assertEqual(streams.calls, 1)

    def test_charge_keeps_unknown_entry_fallback(self):
        self.assertEqual(helper().observation_charge({'charged': 4096}, []), 4096)

    def test_deadline_before_child_start(self):
        with self.assertRaisesRegex(RuntimeError, 'JOB_DEADLINE'):
            helper().poll_deadline(10, 120, lambda: None, clock=lambda: 130)

    def test_deadline_during_parent_count(self):
        module = helper()
        clock = iter([119, 120])
        module.poll_deadline(0, 120, lambda: None, clock=lambda: next(clock))
        with self.assertRaisesRegex(RuntimeError, 'JOB_DEADLINE'):
            module.poll_deadline(0, 120, lambda: None, clock=lambda: next(clock))

    def test_final_count_cannot_hide_successful_child_exit(self):
        module = helper()
        record = {'status': 'FAILED', 'phase': 'final_count'}
        def final_count():
            module.poll_deadline(0, 120, lambda: None, clock=lambda: 121)
        with self.assertRaisesRegex(RuntimeError, 'JOB_DEADLINE'):
            module.finish_child(record, 0, final_count, lambda: None)
        self.assertEqual(record, {'status': 'FAILED', 'exit_code': 0, 'phase': 'final_count'})

    def test_child_success_requires_final_count_and_deadline_check(self):
        calls = []
        record = {'status': 'FAILED'}
        helper().finish_child(record, 0, lambda: calls.append('count'), lambda: calls.append('check'))
        self.assertEqual(calls, ['count', 'check'])
        self.assertEqual(record, {'status': 'PASSED', 'exit_code': 0})

    def test_failed_child_remains_failed_after_final_count(self):
        record = {'status': 'FAILED'}
        helper().finish_child(record, 7, lambda: None, lambda: None)
        self.assertEqual(record, {'status': 'FAILED', 'exit_code': 7})

    def test_memory_refusal_precedes_deadline(self):
        def refuse(): raise RuntimeError('HOST_MEMORY')
        with self.assertRaisesRegex(RuntimeError, 'HOST_MEMORY'):
            helper().poll_deadline(0, 120, refuse, clock=lambda: 121)

    def test_child_deadline_keeps_its_original_anchor(self):
        with self.assertRaisesRegex(RuntimeError, 'CENSUS_110_SECOND_DEADLINE'):
            helper().poll_deadline(7, 110, lambda: None, clock=lambda: 117,
                                   error='CENSUS_110_SECOND_DEADLINE')

    def test_journal_is_exclusive_and_diagnostic(self):
        module = helper()
        path = self.root / 'progress.jsonl'
        with module.DiagnosticJournal(path, lambda: None) as journal:
            journal.emit('traversal', elapsed=5, cpu=1, metadata_calls=19)
        original = path.read_bytes()
        value = json.loads(original)
        self.assertFalse(value['complete'])
        self.assertFalse(value['production_admission'])
        self.assertTrue(value['diagnostic_only'])
        with self.assertRaises(FileExistsError):
            module.DiagnosticJournal(path, lambda: None)
        self.assertEqual(path.read_bytes(), original)

    def test_journal_stops_at_record_ceiling(self):
        module = helper()
        path = self.root / 'progress.jsonl'
        with module.DiagnosticJournal(path, lambda: None) as journal:
            for number in range(64):
                journal.emit('count', elapsed=number)
            with self.assertRaisesRegex(RuntimeError, 'DIAGNOSTIC_LIMIT'):
                journal.emit('count', elapsed=65)
        self.assertEqual(len(path.read_bytes().splitlines()), 64)
        self.assertLessEqual(path.stat().st_size, 64 * 1024)

    def test_journal_rejects_oversize_record_before_write(self):
        path = self.root / 'progress.jsonl'
        with helper().DiagnosticJournal(path, lambda: None) as journal:
            with self.assertRaisesRegex(RuntimeError, 'DIAGNOSTIC_LIMIT'):
                journal.emit('x' * 1024)
        self.assertEqual(path.read_bytes(), b'')

    def test_journal_write_failure_refuses(self):
        module = helper()
        class Broken(io.BytesIO):
            def write(self, raw): raise OSError('fixture write failure')
        with module.DiagnosticJournal(self.root / 'progress.jsonl', lambda: None) as journal:
            journal.stream.close()
            journal.stream = Broken()
            with self.assertRaises(OSError):
                journal.emit('count')

    def test_journal_checks_deadline_after_flush(self):
        calls = []
        def check():
            calls.append(1)
            if len(calls) == 2: raise RuntimeError('JOB_DEADLINE')
        path = self.root / 'progress.jsonl'
        with helper().DiagnosticJournal(path, check) as journal:
            with self.assertRaisesRegex(RuntimeError, 'JOB_DEADLINE'):
                journal.emit('final_count', exit_code=0)
        self.assertEqual(len(calls), 3)
        self.assertFalse(json.loads(path.read_bytes())['complete'])

    def test_truncated_progress_never_becomes_admission(self):
        path = self.root / 'partial.jsonl'
        with helper().DiagnosticJournal(path, lambda: None) as journal:
            journal.emit('traversal', metadata_calls=10)
        with path.open('ab') as stream:
            stream.write(b'{"complete":')
        lines = path.read_bytes().splitlines()
        self.assertFalse(json.loads(lines[0])['complete'])
        with self.assertRaises(json.JSONDecodeError):
            json.loads(lines[-1])

    def test_slow_child_journal_close_keeps_original_deadline(self):
        module = helper()
        current = [109]
        check = lambda: module.poll_deadline(0, 110, lambda: None, clock=lambda: current[0],
                                             error='CENSUS_110_SECOND_DEADLINE')
        journal = module.DiagnosticJournal(self.root/'child.jsonl', check)
        stream = journal.stream
        class SlowClose:
            def close(self):
                stream.close()
                current[0] = 111
        journal.stream = SlowClose()
        with self.assertRaisesRegex(RuntimeError, 'CENSUS_110_SECOND_DEADLINE'):
            journal.close()
        self.assertTrue(stream.closed)

    def test_slow_parent_journal_close_changes_pass_to_failure(self):
        module = helper()
        current = [119]
        check = lambda: module.poll_deadline(0, 120, lambda: None, clock=lambda: current[0])
        journal = module.DiagnosticJournal(self.root/'parent.jsonl', check)
        stream = journal.stream
        class SlowClose:
            def close(self):
                stream.close()
                current[0] = 121
        journal.stream = SlowClose()
        record = {'status': 'PASSED', 'exit_code': 0}
        module.close_diagnostics(record, journal)
        self.assertEqual(record['status'], 'FAILED')
        self.assertEqual(record['reason'], 'JOB_DEADLINE')
        self.assertEqual(record['exit_code'], 0)
        self.assertTrue(stream.closed)

    def test_full_parent_schedule_fits_diagnostic_ceiling(self):
        module = helper()
        current = [0]
        path = self.root/'parent.jsonl'
        with module.DiagnosticJournal(path, lambda: None, clock=lambda: current[0]) as journal:
            journal.emit_progress('initial_count', force=True)
            journal.emit_progress('child_setup', force=True)
            journal.emit_progress('child_running', force=True)
            for second in range(2, 120, 2):
                current[0] = second
                journal.emit_progress('periodic_count', completed_counts=second//2)
                journal.emit_progress('periodic_count', completed_counts=second//2)
            journal.emit_progress('final_count', force=True, exit_code=0)
        self.assertLessEqual(len(path.read_bytes().splitlines()), 28)
        self.assertLessEqual(path.stat().st_size, 64*1024)

    def test_parent_and_child_records_share_clock_with_different_anchors(self):
        module = helper()
        paths = [self.root/'parent.jsonl', self.root/'child.jsonl']
        for path, anchor in zip(paths, (0, 17)):
            with module.DiagnosticJournal(path, lambda: None, clock=lambda: 27) as journal:
                journal.emit('verify_release', anchor=anchor, elapsed=27-anchor)
        parent, child = [json.loads(path.read_bytes()) for path in paths]
        self.assertEqual(parent['monotonic'], child['monotonic'])
        self.assertEqual(parent['elapsed'], 27)
        self.assertEqual(child['elapsed'], 10)
        self.assertEqual(child['anchor']-parent['anchor'], 17)







if __name__ == '__main__':
    unittest.main()
