import json
import time
from types import SimpleNamespace

import pytest

from compertum.harness.agent import ToolError
from compertum.harness.endpoint import parse
from compertum.harness.tools import WorkspaceTools


def test_endpoint_accepts_loopback_and_https_but_not_remote_http():
    assert parse("http://localhost:1234/v1").ip == "127.0.0.1"
    assert parse("https://api.deepseek.com").port == 443
    with pytest.raises(ValueError):
        parse("http://api.deepseek.com")


def test_read_write_and_exact_edit(tmp_path):
    tools = WorkspaceTools(tmp_path, tmp_path)
    assert "wrote note.txt" in tools.run("write", {"path": "note.txt", "content": "before"}, time.monotonic() + 5)
    assert tools.run("read", {"path": "note.txt"}, 0) == "before"
    assert "edited note.txt" in tools.run("edit", {"path": "note.txt", "old": "before", "new": "after"}, 0)
    assert (tmp_path / "note.txt").read_text() == "after"
    with pytest.raises(ToolError, match="exactly once"):
        tools.run("edit", {"path": "note.txt", "old": "missing", "new": "x"}, 0)


def test_tools_refuse_outside_secret_state_and_protected_writes(tmp_path):
    tools = WorkspaceTools(tmp_path, tmp_path)
    for path in ("../outside.txt", ".env", "state/research.sqlite", "credentials/key.txt"):
        with pytest.raises(ToolError):
            tools.run("read", {"path": path}, 0)
    for path in ("AGENTS.md", "config/models.toml", "schemas/artifact_manifest.v1.json",
                 "src/compertum/ai/engine/audit.py", "src/compertum/evaluation/score.py"):
        with pytest.raises(ToolError, match="protected"):
            tools.run("write", {"path": path, "content": "x"}, 0)


def test_run_copies_only_python_into_the_sandbox(tmp_path):
    (tmp_path / "main.py").write_text("print('ok')")
    calls = []
    result = SimpleNamespace(exit_code=0, timed_out=False, stdout=b"ok\n", stderr=b"")
    def runner(*args, **kwargs):
        calls.append((args, kwargs))
        return result
    tools = WorkspaceTools(tmp_path, tmp_path, runner=runner)
    output = json.loads(tools.run("run", {"path": "main.py", "seconds": 5}, time.monotonic() + 10))
    assert output["status"] == "COMPLETED"
    args, kwargs = calls[0]
    assert args[2] == ["main.py"]
    assert (args[1] / "main.py").read_text() == "print('ok')"
    assert kwargs["seconds"] == 5
    with pytest.raises(ToolError):
        tools.run("run", {"path": "note.txt"}, time.monotonic() + 10)


def test_more_fixed_code_and_large_reads_are_refused(tmp_path):
    tools = WorkspaceTools(tmp_path, tmp_path)
    for path in ("src/compertum/auditor.py", "src/compertum/runtime/sandbox.py",
                 "src/compertum/ai/engine/limits.py", "src/compertum/harness/tools.py"):
        with pytest.raises(ToolError, match="protected"):
            tools.run("write", {"path": path, "content": "x"}, 0)
    (tmp_path / "large.txt").write_text("x" * (33 * 1024))
    with pytest.raises(ToolError, match="too large"):
        tools.run("read", {"path": "large.txt"}, 0)


def test_sandbox_refuses_an_active_heavy_job(tmp_path):
    (tmp_path / "main.py").write_text("print('no')")
    tools = WorkspaceTools(tmp_path, tmp_path, busy=lambda: True)
    with pytest.raises(ToolError, match="JOB_SLOT_BUSY"):
        tools.run("run", {"path": "main.py"}, time.monotonic() + 10)
