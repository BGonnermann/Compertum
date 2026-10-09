import json
import os
from pathlib import Path
import subprocess
import sys
import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(os.name == "nt", reason="non-Windows CLI refusal fixture")
@pytest.mark.parametrize("args", [[], ["--run-fixtures"], ["--suite", "ipc"],
                                 ["--suite", "ipc", "--run-fixtures"], ["--suite", "all", "--run-fixtures"]])
def test_native_verification_refuses_cloud_without_creating_receipts(args):
    p = subprocess.run([sys.executable, "-B", str(ROOT / "tools/verify_native_ownership.py"), *args],
                       cwd=ROOT, text=True, capture_output=True, timeout=5)
    assert p.returncode == 3
    result = json.loads(p.stdout)
    assert result["status"] == "NATIVE_WINDOWS_UNAVAILABLE"
    assert result["native_task3"] == "UNVERIFIED"
    assert result["fixture_run"] is False
    assert result["m0"] == "INCOMPLETE"
    assert result["native_ipc"] == "UNVERIFIED"
    assert result["worker_bootstrap"] == "UNIMPLEMENTED"
