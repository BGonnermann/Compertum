"""Small maintenance fixtures. These tests do not scan the project."""
import importlib.util
import os
from pathlib import Path
import stat
import tempfile
from types import SimpleNamespace
import unittest

spec = importlib.util.spec_from_file_location('fresh_usage', Path(__file__).parents[1] / 'tools/fresh_namespace_usage.py')
usage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(usage)


class FreshNamespaceUsageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def sample(self, roots, **kwargs):
        return usage.namespace_usage(roots, lambda: None, **kwargs)

    def test_rounding_and_overlapping_roots(self):
        child = self.root / 'child'
        child.mkdir()
        (child / 'file').write_bytes(b'x' * 4097)
        calls = []
        def fresh(path, **kwargs):
            calls.append(path)
            return os.stat(path, **kwargs)
        self.assertEqual(self.sample([child, self.root], stat_path=fresh), [12288, 16384])
        self.assertEqual(len(calls), 3)
        self.assertEqual(len(set(calls)), 3)

    def test_duplicate_roots_receive_the_same_charge(self):
        self.assertEqual(self.sample([self.root, self.root]), [4096, 4096])

    def test_actual_metadata_path_keeps_entry_spelling(self):
        file = self.root / 'MiXeD'
        file.mkdir()
        (file / 'file').write_bytes(b'x')
        scanned = []
        def fresh(path, **kwargs):
            if Path(path).name.lower() == 'mixed':
                self.assertEqual(Path(path).name, 'MiXeD')
            return os.stat(path, **kwargs)
        def scan(path):
            scanned.append(path)
            return os.scandir(path)
        self.assertEqual(self.sample([self.root], stat_path=fresh, scan_directory=scan), [12288])
        self.assertEqual(scanned, [str(self.root), str(file)])
        if os.path.normcase('a') == os.path.normcase('A'):
            with self.assertRaisesRegex(ValueError, 'AMBIGUOUS_CAPPED_ROOT_SPELLING'):
                self.sample([file, str(file).swapcase()])

    def test_sibling_prefix_is_separate(self):
        first, second = self.root / 'a', self.root / 'ab'
        first.mkdir(); second.mkdir()
        (second / 'file').write_bytes(b'x')
        self.assertEqual(self.sample([first, second]), [4096, 8192])

    def test_missing_root_is_zero(self):
        self.assertEqual(self.sample([self.root / 'missing']), [0])

    def test_growth_between_samples_is_visible(self):
        file = self.root / 'file'
        file.write_bytes(b'x')
        self.assertEqual(self.sample([self.root]), [8192])
        file.write_bytes(b'x' * 4097)
        self.assertEqual(self.sample([self.root]), [12288])

    def test_growth_after_enumeration_uses_fresh_stat(self):
        file = self.root / 'file'
        file.write_bytes(b'x')
        def fresh(path, **kwargs):
            if Path(path).name == 'file':
                file.write_bytes(b'x' * 4097)
            return os.stat(path, **kwargs)
        self.assertEqual(self.sample([self.root], stat_path=fresh), [12288])

    def test_deletion_after_enumeration_is_skipped(self):
        file = self.root / 'file'
        file.write_bytes(b'x')
        def fresh(path, **kwargs):
            if Path(path).name == 'file':
                file.unlink()
            return os.stat(path, **kwargs)
        self.assertEqual(self.sample([self.root], stat_path=fresh), [4096])

    def test_replacement_after_enumeration_is_measured(self):
        file = self.root / 'file'
        file.write_bytes(b'x')
        def fresh(path, **kwargs):
            if Path(path).name == 'file':
                file.unlink(); file.mkdir()
                (file / 'replacement').write_bytes(b'x')
            return os.stat(path, **kwargs)
        self.assertEqual(self.sample([self.root], stat_path=fresh), [12288])

    def test_reparse_root_is_not_followed(self):
        fake = SimpleNamespace(st_mode=stat.S_IFDIR, st_size=99, st_file_attributes=0x410)
        def forbidden(path):
            raise AssertionError('reparse traversal')
        self.assertEqual(self.sample([self.root], stat_path=lambda *a, **k: fake, scan_directory=forbidden), [4096])

    def test_nested_cap_behind_reparse_gets_its_separate_check(self):
        child = self.root / 'child'
        child.mkdir()
        def fresh(path, **kwargs):
            if Path(path) == self.root:
                return SimpleNamespace(st_mode=stat.S_IFDIR, st_size=0, st_file_attributes=0x410)
            return os.stat(path, **kwargs)
        self.assertEqual(self.sample([self.root, child], stat_path=fresh), [4096, 4096])

    def test_permission_error_refuses_sample(self):
        def denied(*args, **kwargs):
            raise PermissionError('fixture')
        with self.assertRaises(PermissionError):
            self.sample([self.root], stat_path=denied)

    def test_poll_can_interrupt_inside_directory_enumeration(self):
        for index in range(8):
            (self.root / str(index)).write_bytes(b'x')
        calls = []
        def poll():
            calls.append(1)
            if len(calls) == 5:
                raise TimeoutError('fixture deadline')
        with self.assertRaisesRegex(TimeoutError, 'fixture deadline'):
            usage.namespace_usage([self.root], poll)


if __name__ == '__main__':
    unittest.main()
