"""Environment evidence must be measured, read-only and honest about gaps."""

import hashlib
import importlib.util
import json
import subprocess
import sys
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch


class EnvironmentReceiptTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location(
            "environment_receipt", Path(__file__).parents[1] / "src/compertum/environment.py"
        )
        self.helper = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.helper)

    def workspace(self):
        parent = Path(__file__).parents[1] / ".cache/test-runs"
        for ancestor in (parent.parent, parent):
            if ancestor.is_symlink():
                raise RuntimeError("unsafe test namespace")
            ancestor.mkdir(exist_ok=True)
        path = parent / ("environment-" + uuid.uuid4().hex)
        path.mkdir()
        return path

    def test_collection_is_read_only_and_reports_actual_interpreter(self):
        root = self.workspace()
        (root / "docs").mkdir()
        document = root / "docs/BUILD_SPEC.md"
        document.write_bytes(b"measured spec\n")
        before = sorted(str(p.relative_to(root)) for p in root.rglob("*"))
        receipt = self.helper.collect_environment(root)
        after = sorted(str(p.relative_to(root)) for p in root.rglob("*"))
        self.assertEqual(before, after)
        self.assertEqual(document.read_bytes(), b"measured spec\n")
        self.assertEqual(receipt["python"]["version"], sys.version.split()[0])
        self.assertEqual(receipt["document_hashes"]["docs/BUILD_SPEC.md"],
                         hashlib.sha256(b"measured spec\n").hexdigest())
        self.assertIsNone(receipt["document_hashes"]["docs/M0_IMPLEMENTATION_PLAN.md"])
        self.assertEqual(receipt["native_validation"], "UNVERIFIED")
        self.assertEqual(receipt["m0_status"], "INCOMPLETE")
        self.assertEqual(receipt["home_strata"], "UNVERIFIED")
        self.assertNotIn("environment_variables", receipt)
        json.dumps(receipt, allow_nan=False)

    def test_hashing_does_not_follow_a_document_symlink(self):
        directory = self.workspace()
        root = directory / "project"
        (root / "docs").mkdir(parents=True)
        outside = directory / "outside.txt"
        outside.write_text("outside content")
        (root / "docs/BUILD_SPEC.md").symlink_to(outside)
        receipt = self.helper.collect_environment(root)
        self.assertIsNone(receipt["document_hashes"]["docs/BUILD_SPEC.md"])
        self.assertIn("docs/BUILD_SPEC.md", receipt["unreadable_or_unsafe_paths"])

    def test_hashing_does_not_follow_a_symlink_in_the_parent_path(self):
        directory = self.workspace()
        root = directory / "project"
        root.mkdir()
        outside = directory / "outside"
        outside.mkdir()
        (outside / "BUILD_SPEC.md").write_text("outside content")
        (root / "docs").symlink_to(outside, target_is_directory=True)
        receipt = self.helper.collect_environment(root)
        self.assertIsNone(receipt["document_hashes"]["docs/BUILD_SPEC.md"])
        self.assertIn("docs/BUILD_SPEC.md", receipt["unreadable_or_unsafe_paths"])

    def test_command_reports_incomplete_without_creating_an_environment(self):
        root = self.workspace()
        result = subprocess.run(
            [sys.executable, "-B", str(Path(self.helper.__file__)), "--project-root", str(root)],
            capture_output=True, text=True, check=False, timeout=20,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["m0_status"], "INCOMPLETE")
        self.assertEqual(list(root.iterdir()), [])

    def test_command_rejects_a_missing_root_without_creating_it(self):
        root = self.workspace() / "absent"
        result = subprocess.run(
            [sys.executable, "-B", str(Path(self.helper.__file__)), "--project-root", str(root)],
            capture_output=True, text=True, check=False, timeout=20,
        )
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stdout)["status"], "INVALID_PROJECT_ROOT")
        self.assertFalse(root.exists())

    def test_stale_size_cannot_exceed_total_hashing_budget(self):
        root = self.workspace()
        (root / "docs").mkdir()
        document = root / "docs/BUILD_SPEC.md"
        document.write_bytes(b"12345678")
        original_stat = Path.stat

        def stale_stat(path, *, follow_symlinks=True):
            result = original_stat(path, follow_symlinks=follow_symlinks)
            if path == document and follow_symlinks:
                values = list(result)
                values[6] = 4  # Filesystem reports a prior size; content has grown.
                return type(result)(values)
            return result

        with patch.object(self.helper, "MAX_HASH_TOTAL_BYTES", 6), patch.object(Path, "stat", stale_stat):
            receipt = self.helper.collect_environment(root)
        self.assertIsNone(receipt["document_hashes"]["docs/BUILD_SPEC.md"])
        self.assertFalse(receipt["hash_observation_complete"])

    def test_file_read_is_bounded_even_when_it_grows_after_metadata(self):
        root = self.workspace()
        (root / "docs").mkdir()
        document = root / "docs/BUILD_SPEC.md"
        document.write_bytes(b"1234")
        original_open = Path.open

        class GuardedReader:
            def __init__(self, stream):
                self.stream = stream

            def __enter__(self):
                self.stream.__enter__()
                return self

            def __exit__(self, *args):
                return self.stream.__exit__(*args)

            def read(self, size=-1):
                if not 0 <= size <= 7:  # Six admitted bytes plus one overflow byte.
                    raise AssertionError("file read exceeded the admitted memory bound")
                return self.stream.read(size)

        def growing_open(path, *args, **kwargs):
            if path == document and args and args[0] == "rb":
                with original_open(path, "wb") as stream:
                    stream.write(b"12345678")
                return GuardedReader(original_open(path, *args, **kwargs))
            return original_open(path, *args, **kwargs)

        with patch.object(self.helper, "MAX_HASH_FILE_BYTES", 6), patch.object(Path, "open", growing_open):
            receipt = self.helper.collect_environment(root)
        self.assertIsNone(receipt["document_hashes"]["docs/BUILD_SPEC.md"])
        self.assertFalse(receipt["hash_observation_complete"])

    def test_many_empty_source_files_truncate_the_observation(self):
        root = self.workspace()
        (root / "src").mkdir()
        for index in range(20):
            (root / "src" / f"source_{index}.py").write_bytes(b"")
        with patch.object(self.helper, "MAX_SCAN_ENTRIES", 4, create=True):
            receipt = self.helper.collect_environment(root)
        self.assertFalse(receipt["hash_observation_complete"])
        self.assertLessEqual(sum(key.startswith("src/") for key in receipt["source_hashes"]), 4)
        self.assertEqual(receipt["source_bundle_hash"], None)

    def test_aggregate_exhaustion_does_not_publish_a_complete_source_hash(self):
        root = self.workspace()
        (root / "docs").mkdir()
        (root / "docs/BUILD_SPEC.md").write_bytes(b"1234")
        (root / "docs/M0_IMPLEMENTATION_PLAN.md").write_bytes(b"5678")
        with patch.object(self.helper, "MAX_HASH_TOTAL_BYTES", 6):
            receipt = self.helper.collect_environment(root)
        self.assertEqual(receipt["document_hashes"]["docs/BUILD_SPEC.md"], hashlib.sha256(b"1234").hexdigest())
        self.assertIsNone(receipt["document_hashes"]["docs/M0_IMPLEMENTATION_PLAN.md"])
        self.assertFalse(receipt["hash_observation_complete"])
        self.assertIsNone(receipt["source_bundle_hash"])


if __name__ == "__main__":
    unittest.main()
