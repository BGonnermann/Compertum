import json
import time
from io import StringIO
from types import SimpleNamespace

import pytest

from compertum.harness.agent import Agent, Limits, ToolError
from compertum.harness.display import Display
from compertum.harness.endpoint import parse
from compertum.harness.tools import WorkspaceTools


def test_endpoint_schemes():
    assert parse("http://localhost:1234/v1").ip == "127.0.0.1"
    assert parse("https://api.deepseek.com").port == 443
    with pytest.raises(ValueError):
        parse("http://api.deepseek.com")


def test_exact_edit(tmp_path):
    tools = WorkspaceTools(tmp_path, tmp_path)
    assert "wrote note.txt" in tools.run("write", {"path": "note.txt", "content": "before"}, time.monotonic() + 5)
    assert tools.run("read", {"path": "note.txt"}, 0) == "before"
    assert "edited note.txt" in tools.run("edit", {"path": "note.txt", "old": "before", "new": "after"}, 0)
    assert (tmp_path / "note.txt").read_text() == "after"
    with pytest.raises(ToolError, match="exactly once"):
        tools.run("edit", {"path": "note.txt", "old": "missing", "new": "x"}, 0)


def test_tool_refusals(tmp_path):
    tools = WorkspaceTools(tmp_path, tmp_path)
    for path in ("../outside.txt", ".env", "state/research.sqlite", "credentials/key.txt"):
        with pytest.raises(ToolError):
            tools.run("read", {"path": path}, 0)
    for path in ("AGENTS.md", "config/models.toml", "schemas/artifact_manifest.v1.json",
                 "src/compertum/ai/engine/audit.py", "src/compertum/evaluation/score.py"):
        with pytest.raises(ToolError, match="protected"):
            tools.run("write", {"path": path, "content": "x"}, 0)


def test_python_copy(tmp_path):
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


def test_large_reads(tmp_path):
    tools = WorkspaceTools(tmp_path, tmp_path)
    for path in ("src/compertum/auditor.py", "src/compertum/runtime/sandbox.py",
                 "src/compertum/ai/engine/limits.py", "src/compertum/harness/tools.py"):
        with pytest.raises(ToolError, match="protected"):
            tools.run("write", {"path": path, "content": "x"}, 0)
    (tmp_path / "large.txt").write_text("x" * (33 * 1024))
    with pytest.raises(ToolError, match="too large"):
        tools.run("read", {"path": "large.txt"}, 0)


def test_heavy_job(tmp_path):
    (tmp_path / "main.py").write_text("print('no')")
    tools = WorkspaceTools(tmp_path, tmp_path, busy=lambda: True)
    with pytest.raises(ToolError, match="JOB_SLOT_BUSY"):
        tools.run("run", {"path": "main.py"}, time.monotonic() + 10)


class Scripted:
    def __init__(self, replies):
        self.replies, self.requests = list(replies), []

    def chat(self, messages, tools, on_event=None, deadline=None):
        self.requests.append((list(messages), tools))
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def test_no_step_limit(tmp_path):
    ticks = iter(range(10000))

    def clock():
        return next(ticks) * 0.01

    (tmp_path / "notes").mkdir()
    for number in range(121):
        (tmp_path / "notes" / f"note-{number}.txt").write_text(f"note {number}")
    replies = [SimpleNamespace(content="", tool_calls=[
        {"id": f"call-{n}", "name": "read", "arguments": json.dumps({"path": f"notes/note-{n}.txt"})}])
        for n in range(120)]
    replies.append(SimpleNamespace(content="finally answered", tool_calls=[]))
    client = Scripted(replies)
    agent = Agent(client, WorkspaceTools(tmp_path, tmp_path), Limits(None, 20), Display(StringIO(), color=False),
                  tmp_path, clock=clock)
    agent.start()
    outcome = agent.run_task("Read every note")
    assert outcome.status == "done" and outcome.answer == "finally answered"
    assert outcome.steps == 121
    assert client.replies == []


def test_time_guard(tmp_path):
    """With no step limit, a task that never answers still ends at the time limit."""
    ticks = iter(range(100000))
    (tmp_path / "notes").mkdir()
    for number in range(400):
        (tmp_path / "notes" / f"note-{number}.txt").write_text(f"note {number}")
    made = iter(range(400))

    class Endless:
        replies = None

        def chat(self, messages, tools, on_event=None, deadline=None):
            n = next(made)
            return SimpleNamespace(content="", tool_calls=[{"id": f"call-{n}", "name": "read",
                                                            "arguments": json.dumps({"path": f"notes/note-{n}.txt"})}])

    agent = Agent(Endless(), WorkspaceTools(tmp_path, tmp_path), Limits(None, 60), Display(StringIO(), color=False),
                  tmp_path, clock=lambda: next(ticks) * 0.5)
    agent.start()
    outcome = agent.run_task("Read the note forever")
    assert outcome.status == "time_limit" and 1 < outcome.steps < 200


def test_step_limit_five(tmp_path):
    (tmp_path / "notes").mkdir()
    for number in range(8):
        (tmp_path / "notes" / f"note-{number}.txt").write_text(f"note {number}")
    replies = [SimpleNamespace(content="", tool_calls=[
        {"id": f"call-{n}", "name": "read", "arguments": json.dumps({"path": f"notes/note-{n}.txt"})}])
        for n in range(8)]
    client = Scripted(replies)
    agent = Agent(client, WorkspaceTools(tmp_path, tmp_path), Limits(5, 60), Display(StringIO(), color=False), tmp_path)
    agent.start()
    outcome = agent.run_task("Read the notes")
    assert outcome.status == "step_limit" and outcome.steps == 5
    assert len(client.replies) == 3
