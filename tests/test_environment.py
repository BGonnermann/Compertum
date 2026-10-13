import importlib.util
import os
from pathlib import Path
import unittest


class EnvironmentTests(unittest.TestCase):
    def test_environment_receipt_is_observed_and_does_not_dump_secrets(self):
        location = Path(__file__).parents[1] / "tools/environment_receipt.py"
        self.assertTrue(location.exists(), "environment recorder missing")
        spec = importlib.util.spec_from_file_location("environment_receipt", location)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        os.environ["M0_TEST_PRIVATE_VALUE"] = "private-fixture-value"
        try:
            receipt = module.collect_environment(Path(__file__).parents[1])
            self.assertEqual(receipt["python"]["version"], "3.14.7")
            self.assertGreater(receipt["storage"]["free_bytes"], 0)
            self.assertEqual(receipt["documents"]["docs/BUILD_SPEC.md"], "8580018ed5cabfdc1fe6f00688cc91e5762b1ced8d7ef2c7d96fef6c7a31906b")
            self.assertNotIn("private-fixture-value", str(receipt))
        finally:
            del os.environ["M0_TEST_PRIVATE_VALUE"]
