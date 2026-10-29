"""Streaming Chat Completions client, adapted from Vesper core."""
from __future__ import annotations

import http.client
import json
import queue
import socket
import threading
import time
from dataclasses import dataclass, field

from compertum.ai.manual import read_json
from compertum.runtime.jobs import available_physical_memory

from .endpoint import Endpoint
from .packets import MAX_CONVERSATION, checked, encode, kib

POLL = 0.2
MAX_REPLY_BYTES = 120 * 1024
MAX_MODELS_BYTES = 65536
MAX_TOOL_CALLS = 8


class ModelError(Exception):
    pass


class DeadlineReached(Exception):
    pass


@dataclass
class Reply:
    content: str = ""
    reasoning: str = ""
    tool_calls: list[dict] = field(default_factory=list)
    finish_reason: str | None = None
    server_model: str | None = None
    usage: dict | None = None


class ModelClient:
    def __init__(self, endpoint: Endpoint, model: str, headers: dict, request_timeout: float = 300,
                 max_tokens: int = 8192, temperature: float | None = None):
        self.ep, self.model, self.headers = endpoint, model, dict(headers)
        # By default the provider chooses the temperature. Kimi k3.1-pro refuses any value except 1.
        self.request_timeout = request_timeout
        self.options: dict = {"max_tokens": max_tokens}
        if temperature is not None:
            self.options["temperature"] = temperature

    def _connection(self, timeout: float):
        kind = http.client.HTTPSConnection if self.ep.scheme == "https" else http.client.HTTPConnection
        return kind(self.ep.ip, self.ep.port, timeout=timeout)

    def _headers(self) -> dict:
        return {**self.headers, "Host": f"{self.ep.host}:{self.ep.port}", "Content-Type": "application/json"}

    def list_models(self, timeout: float = 10) -> list[str]:
        conn = self._connection(timeout)
        try:
            conn.request("GET", f"{self.ep.path}/models", headers=self._headers())
            response = conn.getresponse()
            raw = response.read(MAX_MODELS_BYTES + 1)
            if len(raw) > MAX_MODELS_BYTES:
                raise ModelError("the model list is too large")
            if response.status != 200:
                raise ModelError(f"the model server returned HTTP {response.status}")
            value = read_json(raw)
            data = value.get("data") if isinstance(value, dict) else None
            if not isinstance(data, list):
                raise ModelError("the model server returned an invalid model list")
            return sorted({m["id"] for m in data if isinstance(m, dict) and isinstance(m.get("id"), str)
                           and 1 <= len(m["id"]) <= 256})
        except (OSError, ValueError, AttributeError, http.client.HTTPException) as exc:
            raise ModelError(f"cannot reach the model server: {exc}") from None
        finally:
            conn.close()

    def chat(self, messages: list, tools: list, on_event=None, deadline: float | None = None) -> Reply:
        if available_physical_memory() < 8 * 1024**3:
            raise ModelError("AVAILABLE_RAM_FLOOR")
        try:
            checked(messages, MAX_CONVERSATION, "CONVERSATION_FULL")
        except Exception as exc:
            code = getattr(exc, "code", "the model request was refused")
            if code == "CONVERSATION_FULL":
                code = (f"CONVERSATION_FULL: the conversation holds {kib(len(encode(messages)))} of "
                        f"{kib(MAX_CONVERSATION)}; use /new")
            raise ModelError(code) from None
        body = {"model": self.model, "messages": messages, "stream": True,
                "stream_options": {"include_usage": True}, **self.options}
        if tools:
            body["tools"] = tools
        items = queue.Queue()
        stop = threading.Event()
        conn = self._connection(self.request_timeout)
        worker = threading.Thread(target=self._receive, args=(conn, body, items, stop), daemon=True)
        worker.start()
        reply, calls = Reply(), {}
        last = time.monotonic()
        try:
            while True:
                wait = POLL if deadline is None else min(POLL, deadline - time.monotonic())
                if wait <= 0:
                    raise DeadlineReached()
                try:
                    kind, item = items.get(timeout=wait)
                except queue.Empty:
                    if time.monotonic() - last > self.request_timeout:
                        raise ModelError("the model server stopped responding") from None
                    continue
                last = time.monotonic()
                if kind == "error":
                    raise ModelError(item)
                if kind == "end":
                    break
                self._add(reply, calls, item, on_event)
                if len(json.dumps([reply.content, reply.reasoning, calls]).encode()) > MAX_REPLY_BYTES:
                    raise ModelError("the model reply is too large")
        except BaseException:
            stop.set()
            _abort(conn)
            raise
        if len(calls) > MAX_TOOL_CALLS:
            raise ModelError("the model requested too many tools")
        for _, call in sorted(calls.items()):
            reply.tool_calls.append({"id": call["id"] or f"call_{len(reply.tool_calls) + 1}",
                                     "name": call["name"], "arguments": call["args"]})
        if reply.finish_reason == "length":
            raise ModelError("AI_RESPONSE_TRUNCATED")
        if reply.server_model is not None and reply.server_model != self.model:
            raise ModelError("MODEL_IDENTITY_MISMATCH")
        try:
            # A reply holds only what the model wrote, so it gets the size check. Local text gets the secret scan.
            # Scanning replies would end a task for an ordinary search such as grep password.
            checked([reply.content, reply.reasoning, reply.tool_calls], MAX_REPLY_BYTES, "AI_REPLY_BOUND", scan=False)
        except Exception as exc:
            raise ModelError(getattr(exc, "code", "the model reply was refused")) from None
        return reply

    def _receive(self, conn, body, items, stop):
        try:
            conn.request("POST", f"{self.ep.path}/chat/completions", json.dumps(body).encode(), self._headers())
            response = conn.getresponse()
            if response.status != 200:
                items.put(("error", f"the model server returned HTTP {response.status}{_reason(response.read(800))}"))
                return
            if "text/event-stream" not in (response.getheader("Content-Type") or ""):
                raw = response.read(MAX_REPLY_BYTES + 1)
                if len(raw) > MAX_REPLY_BYTES:
                    raise ModelError("the model reply is too large")
                items.put(("chunk", _as_chunk(read_json(raw))))
                items.put(("end", None))
                return
            for raw in response:
                line = raw.decode("utf-8", "replace").strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                items.put(("chunk", read_json(data.encode())))
            items.put(("end", None))
        except Exception as exc:
            if not stop.is_set():
                items.put(("error", f"the model request failed: {exc}"))
        finally:
            conn.close()

    @staticmethod
    def _add(reply, calls, chunk, on_event):
        on_event = on_event or (lambda kind, text: None)
        if not isinstance(chunk, dict):
            return
        if chunk.get("error"):
            raise ModelError("the model server reported an error")
        if isinstance(chunk.get("model"), str):
            reply.server_model = chunk["model"]
        reply.usage = chunk.get("usage") or reply.usage
        for choice in chunk.get("choices") or []:
            delta = choice.get("delta") or {}
            reasoning = delta.get("reasoning_content") or delta.get("reasoning")
            if isinstance(reasoning, str) and reasoning:
                reply.reasoning += reasoning
                on_event("reasoning", reasoning)
            if isinstance(delta.get("content"), str) and delta["content"]:
                reply.content += delta["content"]
                on_event("text", delta["content"])
            for call in delta.get("tool_calls") or []:
                slot = calls.setdefault(call.get("index", len(calls)), {"id": None, "name": "", "args": ""})
                slot["id"] = call.get("id") or slot["id"]
                function = call.get("function") or {}
                slot["name"] += function.get("name") or ""
                args = function.get("arguments")
                slot["args"] += args if isinstance(args, str) else (json.dumps(args) if args else "")
            reply.finish_reason = choice.get("finish_reason") or reply.finish_reason


def _as_chunk(data):
    choices = []
    for choice in data.get("choices") or []:
        message = dict(choice.get("message") or {})
        message["tool_calls"] = [{**call, "index": i} for i, call in enumerate(message.get("tool_calls") or [])]
        choices.append({"delta": message, "finish_reason": choice.get("finish_reason")})
    return {"model": data.get("model"), "usage": data.get("usage"), "choices": choices}


def _reason(raw):
    """Return the server's short error message, so a refused request explains itself."""
    try:
        data = json.loads(raw)
        error = data.get("error") if isinstance(data, dict) else None
        text = error.get("message") if isinstance(error, dict) else error if isinstance(error, str) else None
    except ValueError:
        text = raw.decode("utf-8", "replace")
    text = " ".join(str(text or "").split())[:300]
    return f": {text}" if text else ""


def _abort(conn):
    try:
        if conn.sock is not None:
            conn.sock.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass
    conn.close()
