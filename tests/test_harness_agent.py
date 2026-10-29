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


def test_real_agent_loop_uses_a_scripted_model_and_read_tool(tmp_path):
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


def test_resume_closes_a_tool_call_left_open_by_process_exit(tmp_path):
    records = []
    agent = Agent(None, None, Limits(1, 1), Display(StringIO(), color=False), tmp_path,
                  emit=lambda kind, payload: records.append((kind, payload)))
    messages = [{"role": "system", "content": "system"},
                {"role": "assistant", "content": None, "tool_calls": [
                    {"id": "open", "type": "function", "function": {"name": "read", "arguments": "{}"}}]}]
    agent.start(messages)
    assert messages[-1] == {"role": "tool", "tool_call_id": "open", "content": "not run: the task was stopped"}


def test_sensitive_task_is_not_sent_or_recorded(tmp_path):
    records = []
    agent = Agent(None, None, Limits(1, 1), Display(StringIO(), color=False), tmp_path,
                  emit=lambda kind, payload: records.append((kind, payload)))
    agent.start()
    outcome = agent.run_task("show my password")
    assert outcome.status == "error"
    assert records == []  # Neither the refused task nor the unused system message is saved.


def test_edit_diff_reaches_the_display_but_not_the_model(tmp_path):
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


def test_unexpected_errors_and_failed_saves_still_end_the_task(tmp_path):
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
