import json
import subprocess
import time
from io import StringIO
from types import SimpleNamespace

import pytest

from compertum.harness import shell
from compertum.harness import tools as tool_module
from compertum.harness.agent import Agent, Limits, ToolError
from compertum.harness.display import Display
from compertum.harness.packets import MAX_CONVERSATION, SECRET_LINE, checked, hide_secrets
from compertum.harness.sessions import SessionStore
from compertum.harness.tools import SECRET_TEXT, WorkspaceTools, _git_bash

needs_bash = pytest.mark.skipif(_git_bash() is None, reason="Git Bash is not installed")


def later():
    return time.monotonic() + 60


def project(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("def alpha():\n    return 1\n\nVALUE = 'needle'\n")
    (tmp_path / "src" / "b.txt").write_text("needle in text\n")
    (tmp_path / "state").mkdir()
    (tmp_path / "state" / "hidden.py").write_text("needle\n")
    (tmp_path / ".env").write_text("needle\n")
    (tmp_path / "keys.py").write_text("api_key = 'needle'\n")
    return WorkspaceTools(tmp_path, tmp_path)


def test_search_returns_numbered_matches_and_skips_protected_files(tmp_path):
    tools = project(tmp_path)
    result = tools.run("search", {"pattern": "needle"}, later()).splitlines()
    assert result == [f"keys.py:1: {SECRET_TEXT}", "src/a.py:4: VALUE = 'needle'", "src/b.txt:1: needle in text"]
    assert tools.run("search", {"pattern": "needle", "glob": "*.py", "names_only": True}, later()) == "keys.py\nsrc/a.py"
    assert tools.run("search", {"pattern": r"def \w+", "path": "src/a.py"}, later()) == "src/a.py:1: def alpha():"
    assert tools.run("search", {"pattern": "absent"}, later()) == "no matches"
    with pytest.raises(ToolError, match="regular expression"):
        tools.run("search", {"pattern": "("}, later())
    with pytest.raises(ToolError, match="protected"):
        tools.run("search", {"pattern": "needle", "path": "state"}, later())


def test_search_skips_git_ignored_files(tmp_path):
    tools = project(tmp_path)
    (tmp_path / "build").mkdir()
    (tmp_path / "build" / "out.py").write_text("needle\n")
    (tmp_path / ".gitignore").write_text("build/\n")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    names = tools.run("search", {"pattern": "needle", "names_only": True}, later()).splitlines()
    assert names == ["keys.py", "src/a.py", "src/b.txt"]


@needs_bash
def test_bash_runs_in_the_workspace_without_secret_variables(tmp_path, monkeypatch):
    monkeypatch.setenv("COMPERTUM_TEST_API_KEY", "should-not-pass")
    monkeypatch.setenv("COMPERTUM_TEST_PLAIN", "visible")
    tools = WorkspaceTools(tmp_path, tmp_path)
    (tmp_path / "note.txt").write_text("hello\n")
    command = 'cat note.txt; echo "plain=$COMPERTUM_TEST_PLAIN key=${COMPERTUM_TEST_API_KEY:-unset}"; echo password=abc; exit 3'
    result = json.loads(tools.run("bash", {"command": command}, later()))
    assert result["exit_code"] == 3 and result["status"] == "FAILED" and not result["timed_out"]
    assert result["stdout"].splitlines() == ["hello", "plain=visible key=unset", "[line hidden: it looks like a secret]"]


@needs_bash
def test_bash_stops_slow_commands_and_keeps_the_head_and_tail(tmp_path):
    tools = WorkspaceTools(tmp_path, tmp_path)
    started = time.monotonic()
    result = json.loads(tools.run("bash", {"command": "sleep 30", "seconds": 1}, later()))
    assert result["timed_out"] and result["status"] == "FAILED" and time.monotonic() - started < 20
    result = json.loads(tools.run("bash", {"command": "echo first; head -c 200000 /dev/zero | tr '\\0' x; echo; echo last"},
                                  later()))
    output = result["stdout"]
    assert output.startswith("first\n") and output.rstrip().endswith("last")
    assert "bytes skipped" in output and len(output) < 30 * 1024


@needs_bash
def test_bash_ends_background_and_grandchild_processes(tmp_path):
    tools = WorkspaceTools(tmp_path, tmp_path)
    started = time.monotonic()
    result = json.loads(tools.run("bash", {"command": "(sleep 2; echo late > late.txt) & echo started"}, later()))
    assert result["stdout"].strip() == "started" and result["status"] == "COMPLETED"
    assert time.monotonic() - started < 10
    result = json.loads(tools.run("bash", {"command": "(sleep 2; echo late > later.txt) & sleep 30", "seconds": 1},
                                  later()))
    assert result["timed_out"]
    time.sleep(3)
    assert not (tmp_path / "late.txt").exists() and not (tmp_path / "later.txt").exists()


@needs_bash
def test_bash_binary_output_and_provider_key_names(tmp_path, monkeypatch):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "providers.toml").write_text('[providers.moon]\nbase_url = "https://x"\nkey_variable = "MOON_PAT"\n')
    monkeypatch.setenv("MOON_PAT", "should-not-pass")
    tools = WorkspaceTools(tmp_path, tmp_path)
    result = json.loads(tools.run("bash", {"command": 'echo "pat=${MOON_PAT:-unset}"'}, later()))
    assert result["stdout"].strip() == "pat=unset"
    result = json.loads(tools.run("bash", {"command": "head -c 30000 /dev/urandom"}, later()))
    assert result["exit_code"] == 0


def test_output_cut_drops_partial_lines():
    head = bytearray(b"one\ntwo\nsk-abc")
    tail = bytearray(b"defghijklmnop\nlast\n")
    assert shell._clip(head, tail, 100_000) == b"one\ntwo\n... 99987 bytes skipped ...\nlast\n"
    assert shell._clip(bytearray(b"a\n"), bytearray(b"b\n"), 4) == b"a\nb\n"


def test_bash_waits_for_an_owner_run(tmp_path):
    tools = WorkspaceTools(tmp_path, tmp_path, busy=lambda: True)
    with pytest.raises(ToolError, match="JOB_SLOT_BUSY"):
        tools.run("bash", {"command": "ls"}, later())


def test_secret_scan_reads_local_text_but_not_model_requests():
    with pytest.raises(Exception, match="AI_SENSITIVE_INPUT_DENIED"):
        checked([{"role": "tool", "tool_call_id": "x", "content": "line one\nsk-abcdefghijklmnop"}], MAX_CONVERSATION, "FULL")
    with pytest.raises(Exception, match="AI_SENSITIVE_INPUT_DENIED"):
        checked([{"role": "tool", "tool_call_id": "x", "content": "DEEPSEEK_API_KEY  REG_SZ  abcdefghijklmnopqrstu"}],
                MAX_CONVERSATION, "FULL")
    request = {"role": "assistant", "content": None, "tool_calls": [
        {"id": "x", "type": "function", "function": {"name": "bash", "arguments": '{"command": "grep -rn password src"}'}}]}
    assert checked([{"role": "system", "content": "start"}, request], MAX_CONVERSATION, "FULL")
    assert hide_secrets("ok\norigin https://u:ghp_abcdefghij1234567890@github.com/x\nmax_tokens = 16384") == \
        f"ok\n{SECRET_LINE}\nmax_tokens = 16384"


def test_search_works_in_a_workspace_that_a_parent_repository_ignores(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / ".gitignore").write_text("inner/\n")
    workspace = tmp_path / "inner"
    workspace.mkdir()
    (workspace / "a.py").write_text("needle\n")
    tools = WorkspaceTools(workspace, workspace)
    assert tools.run("search", {"pattern": "needle"}, later()) == "a.py:1: needle"


def test_warning_returns_after_a_new_conversation(tmp_path):
    output = StringIO()
    replies = iter([SimpleNamespace(content="ok", tool_calls=[])] * 2)
    agent = Agent(SimpleNamespace(chat=lambda *args: next(replies)), WorkspaceTools(tmp_path, tmp_path), Limits(4, 20),
                  Display(output, color=False), tmp_path)
    for _ in range(2):
        agent.start()
        agent.messages.append({"role": "user", "content": "z" * (MAX_CONVERSATION - 50_000)})
        agent.run_task("task")
    assert output.getvalue().count("Use /new soon.") == 2


def test_bash_refuses_low_memory_and_bad_input(tmp_path, monkeypatch):
    tools = WorkspaceTools(tmp_path, tmp_path)
    with pytest.raises(ToolError, match="1 to 8192"):
        tools.run("bash", {"command": " "}, later())
    with pytest.raises(ToolError, match="1 to 600"):
        tools.run("bash", {"command": "ls", "seconds": 0}, later())
    monkeypatch.setattr(tool_module, "available_physical_memory", lambda: 0)
    with pytest.raises(ToolError, match="AVAILABLE_RAM_FLOOR"):
        tools.run("bash", {"command": "ls"}, later())


def test_sessions_accept_records_above_the_old_event_limit(tmp_path):
    session = SessionStore(tmp_path).create()
    session.append("message", {"role": "system", "content": "start"})
    session.append("message", {"role": "tool", "tool_call_id": "x", "content": "é" * 100_000})
    loaded = SessionStore(tmp_path).load(session.identity)
    assert loaded.messages[-1]["content"] == "é" * 100_000
    with pytest.raises(Exception, match="too large"):
        session.append("message", {"role": "tool", "tool_call_id": "x", "content": "y" * MAX_CONVERSATION})


def test_agent_warns_once_when_the_conversation_is_nearly_full(tmp_path):
    output = StringIO()
    replies = iter([SimpleNamespace(content="ok", tool_calls=[]), SimpleNamespace(content="ok", tool_calls=[])])
    client = SimpleNamespace(chat=lambda *args: next(replies))
    agent = Agent(client, WorkspaceTools(tmp_path, tmp_path), Limits(4, 20), Display(output, color=False), tmp_path)
    agent.start()
    agent.messages.append({"role": "user", "content": "z" * (MAX_CONVERSATION - 50_000)})
    agent.run_task("first")
    agent.run_task("second")
    assert output.getvalue().count("Use /new soon.") == 1


def test_display_shows_bash_and_search_lines():
    output = StringIO()
    display = Display(output, color=False, animate=False)
    display.tool_call("bash", {"command": "git status\ngit diff"})
    display.tool_result(json.dumps({"status": "COMPLETED", "exit_code": 0, "timed_out": False,
                                    "stdout": "clean\n", "stderr": ""}), True, name="bash")
    display.tool_call("search", {"pattern": "def alpha", "path": "src", "glob": "*.py"})
    display.tool_result("src/a.py:1: def alpha():", True, name="search")
    assert output.getvalue().splitlines() == ["● Bash git status ⏎ git diff", "  ⎿ exit 0", "    clean",
                                              "● Search 'def alpha' in src (*.py)", "  ⎿ 1 result",
                                              "    src/a.py:1: def alpha():"]
