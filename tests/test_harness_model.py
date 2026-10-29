import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from compertum.harness.endpoint import parse
from compertum.harness.model import ModelClient, ModelError


def server_for(handler):
    server = HTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def test_streamed_reply_and_model_list(tmp_path):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            raw = json.dumps({"data": [{"id": "scripted"}, {"id": ""}, {"id": "x" * 257}]}).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
        def do_POST(self):
            # Read the request first. Closing with unread data makes Windows reset the connection (WinError 10053).
            self.rfile.read(int(self.headers["Content-Length"]))
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            for chunk in ({"model": "scripted", "choices": [{"delta": {"content": "hello"}}]},
                          {"model": "scripted", "usage": {"prompt_tokens": 1, "completion_tokens": 1},
                           "choices": [{"delta": {}, "finish_reason": "stop"}]}):
                self.wfile.write(b"data: " + json.dumps(chunk).encode() + b"\n\n")
            self.wfile.write(b"data: [DONE]\n\n")
        def log_message(self, *args):
            pass
    server, thread = server_for(Handler)
    try:
        client = ModelClient(parse(f"http://127.0.0.1:{server.server_port}/v1"), "scripted", {})
        assert client.list_models() == ["scripted"]
        reply = client.chat([{"role": "user", "content": "hello"}], [], deadline=time.monotonic() + 5)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
    assert reply.content == "hello"
    assert reply.usage["completion_tokens"] == 1


@pytest.mark.parametrize("finish,model,code", [("length", "scripted", "AI_RESPONSE_TRUNCATED"),
                                                ("stop", "other", "MODEL_IDENTITY_MISMATCH")])
def test_bad_reply_finish_or_model_is_refused(finish, model, code):
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers["Content-Length"]))
            raw = json.dumps({"model": model, "choices": [{"message": {"role": "assistant", "content": "x"},
                                                            "finish_reason": finish}]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
        def log_message(self, *args):
            pass
    server, thread = server_for(Handler)
    try:
        client = ModelClient(parse(f"http://127.0.0.1:{server.server_port}/v1"), "scripted", {})
        with pytest.raises(ModelError, match=code):
            client.chat([{"role": "user", "content": "hello"}], [], deadline=time.monotonic() + 5)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_oversized_conversation_is_a_clean_model_error():
    client = ModelClient(parse("http://127.0.0.1:1/v1"), "scripted", {})
    with pytest.raises(ModelError, match=r"CONVERSATION_FULL: the conversation holds 586 KiB of 512 KiB; use /new"):
        client.chat([{"role": "user", "content": "x" * 600000}], [], deadline=time.monotonic() + 5)
    with pytest.raises(ModelError, match="AI_SENSITIVE_INPUT_DENIED"):
        client.chat([{"role": "user", "content": "my api_key is here"}], [], deadline=time.monotonic() + 5)
    # The old 64 KiB event limit no longer applies. This request passes the checks and fails only at the closed port.
    with pytest.raises(ModelError) as failure:
        client.chat([{"role": "user", "content": "x" * 140000}], [], deadline=time.monotonic() + 5)
    assert "CONVERSATION_FULL" not in str(failure.value) and "EVENT_INVALID" not in str(failure.value)


def test_requests_leave_temperature_to_the_provider_and_errors_give_the_reason():
    # Kimi k3.1-pro answered HTTP 400 "invalid temperature: only 1 is allowed for this model" to temperature 0.
    bodies = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            bodies.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            raw = json.dumps({"error": {"message": "invalid temperature:\n only 1 is allowed", "type": "bad"}}).encode()
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
        def log_message(self, *args):
            pass
    server, thread = server_for(Handler)
    try:
        client = ModelClient(parse(f"http://127.0.0.1:{server.server_port}/v1"), "scripted", {})
        with pytest.raises(ModelError, match=r"^the model server returned HTTP 400: invalid temperature: only 1 is allowed$"):
            client.chat([{"role": "user", "content": "hello"}], [], deadline=time.monotonic() + 5)
        fixed = ModelClient(parse(f"http://127.0.0.1:{server.server_port}/v1"), "scripted", {}, temperature=1)
        with pytest.raises(ModelError):
            fixed.chat([{"role": "user", "content": "hello"}], [], deadline=time.monotonic() + 5)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
    assert "temperature" not in bodies[0] and bodies[0]["max_tokens"] == 8192
    assert bodies[1]["temperature"] == 1
