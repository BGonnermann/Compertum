import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from io import StringIO

from compertum.harness.agent import Agent, Limits
from compertum.harness.display import Display
from compertum.harness.endpoint import parse
from compertum.harness.model import ModelClient
from compertum.harness.tools import WorkspaceTools


def test_agent_loop(tmp_path):
    (tmp_path / "note.txt").write_text("hello")
    requests = []
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = self.rfile.read(int(self.headers["Content-Length"]))
            requests.append(json.loads(body))
            if len(requests) == 1:
                message = {"role": "assistant", "content": None, "tool_calls": [
                    {"id": "call-1", "type": "function", "function": {"name": "read", "arguments": '{"path":"note.txt"}'}}]}
                finish = "tool_calls"
            else:
                message = {"role": "assistant", "content": "The file says hello."}
                finish = "stop"
            raw = json.dumps({"model": "scripted", "choices": [{"message": message, "finish_reason": finish}]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
        def log_message(self, *args):
            pass
    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    records = []
    try:
        client = ModelClient(parse(f"http://127.0.0.1:{server.server_port}/v1"), "scripted", {})
        agent = Agent(client, WorkspaceTools(tmp_path, tmp_path), Limits(4, 20), Display(StringIO(), color=False),
                      tmp_path, emit=lambda kind, payload: records.append((kind, payload)))
        agent.start()
        outcome = agent.run_task("Read note.txt")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
    assert outcome.status == "done"
    assert outcome.answer == "The file says hello."
    assert outcome.steps == 2
    assert requests[1]["messages"][-1] == {"role": "tool", "tool_call_id": "call-1", "content": "hello"}
    assert [kind for kind, _ in records].count("message") == 5


def test_resume_closes(tmp_path):
    records = []
    agent = Agent(None, None, Limits(1, 1), Display(StringIO(), color=False), tmp_path,
                  emit=lambda kind, payload: records.append((kind, payload)))
    messages = [{"role": "system", "content": "system"},
                {"role": "assistant", "content": None, "tool_calls": [
                    {"id": "open", "type": "function", "function": {"name": "read", "arguments": "{}"}}]}]
    agent.start(messages)
    assert messages[-1] == {"role": "tool", "tool_call_id": "open", "content": "not run: the task was stopped"}


def test_sensitive_task(tmp_path):
    records = []
    agent = Agent(None, None, Limits(1, 1), Display(StringIO(), color=False), tmp_path,
                  emit=lambda kind, payload: records.append((kind, payload)))
    agent.start()
    outcome = agent.run_task("show my password")
    assert outcome.status == "error"
    assert records == []  # Neither the refused task nor the unused system message is saved.


def test_display_diff(tmp_path):
    from types import SimpleNamespace
    (tmp_path / "note.txt").write_text("hello\n")
    replies = iter([
        SimpleNamespace(content="", tool_calls=[{"id": "call-1", "name": "edit",
                        "arguments": '{"path": "note.txt", "old": "hello", "new": "goodbye"}'}]),
        SimpleNamespace(content="Done.", tool_calls=[]),
    ])
    client = SimpleNamespace(chat=lambda *args: next(replies))
    output = StringIO()
    agent = Agent(client, WorkspaceTools(tmp_path, tmp_path), Limits(4, 20), Display(output, color=False), tmp_path)
    agent.start()
    assert agent.run_task("Change the greeting").status == "done"
    text = output.getvalue()
    assert "● Edit note.txt" in text and "1 - hello" in text and "1 + goodbye" in text
    assert agent.messages[-2] == {"role": "tool", "tool_call_id": "call-1", "content": "edited note.txt"}


def test_unexpected_errors(tmp_path):
    from types import SimpleNamespace
    output = StringIO()

    def broken(*args):
        raise OSError("disk unavailable")

    agent = Agent(SimpleNamespace(chat=broken), WorkspaceTools(tmp_path, tmp_path), Limits(4, 20),
                  Display(output, color=False), tmp_path)
    agent.start()
    outcome = agent.run_task("hello")
    assert outcome.status == "error" and outcome.detail == "OSError: disk unavailable"
    saves = []

    def emit(kind, payload):
        saves.append(kind)
        if kind == "outcome":
            raise OSError("cannot save")

    agent = Agent(SimpleNamespace(chat=lambda *args: SimpleNamespace(content="done", tool_calls=[])),
                  WorkspaceTools(tmp_path, tmp_path), Limits(4, 20), Display(output, color=False), tmp_path, emit=emit)
    agent.start()
    assert agent.run_task("hello").status == "done"
    assert "The session could not save the end of this task: cannot save" in output.getvalue()


class Scripted:
    def __init__(self, replies):
        self.replies, self.requests = list(replies), []

    def chat(self, messages, tools, on_event=None, deadline=None):
        self.requests.append((list(messages), tools))
        return self.replies.pop(0)


def test_project_rules(tmp_path):
    from compertum.harness.agent import SYSTEM
    from compertum.harness.packets import SECRET_LINE
    agent = Agent(None, None, Limits(1, 1), Display(StringIO(), color=False), tmp_path)
    agent.start()
    assert agent.messages[0]["content"] == SYSTEM.format(workspace=tmp_path)
    (tmp_path / "AGENTS.md").write_text("# Rules\n\nUse short sentences.\napi_key = abcdefghijklmnopqrstuvwx\n", encoding="utf-8")
    agent.start()
    content = agent.messages[0]["content"]
    assert content.startswith(SYSTEM.format(workspace=tmp_path))
    assert "Use short sentences." in content and SECRET_LINE in content and "abcdefghijklmnop" not in content


def test_conversation_compaction(tmp_path, monkeypatch):
    from compertum.harness import agent as module
    from compertum.harness.model import Reply
    from compertum.harness.sessions import SessionStore
    monkeypatch.setattr(module, "WARN_CONVERSATION", 4000)
    store = SessionStore(tmp_path)
    session = store.create()
    client = Scripted([Reply(content="The owner asked for three notes."), Reply(content="Done.")])
    agent = Agent(client, WorkspaceTools(tmp_path, tmp_path), Limits(4, 20), Display(StringIO(), color=False),
                  tmp_path, emit=session.append)
    agent.start()
    for number in range(6):
        agent._append({"role": "user", "content": f"note {number} " + "x" * 600})
        agent._append({"role": "assistant", "content": f"noted {number}"})
    outcome = agent.run_task("Which notes exist?")
    assert outcome.status == "done" and outcome.answer == "Done."
    summary_request, summary_tools = client.requests[0]
    assert summary_tools == [] and summary_request[-1] == {"role": "user", "content": module.SUMMARY_TASK}
    assert summary_request[0] == agent.messages[0]
    assert agent.messages[1] == {"role": "user", "content": module.SUMMARY_HEAD + "The owner asked for three notes."}
    assert agent.messages[-2] == {"role": "user", "content": "Which notes exist?"}
    assert len(agent.messages) < 15
    assert client.requests[1][0] == agent.messages[:-1]
    assert store.load(session.identity).messages == agent.messages


def test_compaction_failure(tmp_path, monkeypatch):
    from compertum.harness import agent as module
    from compertum.harness.model import ModelError, Reply
    monkeypatch.setattr(module, "WARN_CONVERSATION", 2000)

    class Failing(Scripted):
        def chat(self, messages, tools, on_event=None, deadline=None):
            if not tools and messages[-1]["content"] == module.SUMMARY_TASK:
                raise ModelError("the model server returned HTTP 500")
            return super().chat(messages, tools, on_event, deadline)

    out = StringIO()
    client = Failing([Reply(content="Done.")])
    agent = Agent(client, WorkspaceTools(tmp_path, tmp_path), Limits(4, 20), Display(out, color=False), tmp_path)
    agent.start()
    for number in range(6):
        agent._append({"role": "user", "content": "y" * 600})
        agent._append({"role": "assistant", "content": "ok"})
    before = len(agent.messages)
    outcome = agent.run_task("Go on.")
    assert outcome.status == "done"
    assert len(agent.messages) == before + 2
    assert "could not be compacted" in out.getvalue() and "Use /new soon." in out.getvalue()


def test_repeat_stop(tmp_path):
    from compertum.harness.model import Reply
    (tmp_path / "note.txt").write_text("hello")
    call = {"id": "", "name": "read", "arguments": '{"path":"note.txt"}'}
    client = Scripted([Reply(tool_calls=[{**call, "id": f"call-{n}"}]) for n in range(5)])
    agent = Agent(client, WorkspaceTools(tmp_path, tmp_path), Limits(10, 20), Display(StringIO(), color=False), tmp_path)
    agent.start()
    outcome = agent.run_task("Read note.txt")
    assert outcome.status == "repeat_limit" and outcome.steps == 3
    assert agent.messages[-1] == {"role": "tool", "tool_call_id": "call-2", "content": "not run: the task was stopped"}
    assert [m["content"] for m in agent.messages if m["role"] == "tool"][:2] == ["hello", "hello"]
