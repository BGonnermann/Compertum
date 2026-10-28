import json
import os
import time

from compertum.harness.runs import OwnedProcess, process_creation
from compertum.harness.tools import WorkspaceTools


def test_harness_executes_python_only_in_the_real_sandbox(tmp_path):
    (tmp_path / "main.py").write_text("print('sandbox-ok')")
    tools = WorkspaceTools(tmp_path, tmp_path)
    result = json.loads(tools.run("run", {"path": "main.py", "seconds": 30}, time.monotonic() + 40))
    assert result["status"] == "COMPLETED"
    assert result["stdout"].strip() == "sandbox-ok"


def test_recovered_process_identity_uses_the_creation_time():
    created = process_creation(os.getpid())
    process = OwnedProcess(os.getpid(), created)
    assert process.poll() is None
    if created is not None:
        assert OwnedProcess(os.getpid(), created - 1).poll() == "UNKNOWN"
    assert OwnedProcess(2**31 - 1, 1).poll() == "LOST"
