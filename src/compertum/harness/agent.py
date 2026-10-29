"""The bounded agent loop, adapted from Vesper core."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass

from compertum.ai.manual import sanitized
from compertum.runtime.errors import RuntimeRefused

from .model import DeadlineReached, ModelError
from .packets import MAX_CONVERSATION, WARN_CONVERSATION, encode, guard, kib, looks_secret

SYSTEM = """You are Compertum's terminal agent. Work in the project workspace: {workspace}
Use search to find code and bash with ls or find to list folders. Read only the files you need.
Use read, write, and edit for project files. Use bash for git status, git diff, git log and tests.
Bash runs on the owner's PC, not in a sandbox. Follow AGENTS.md. Do not push, commit, install software,
start model servers, delete files outside the workspace, or read credentials, keys or runtime state.
Use run for AI-written Python that must execute. The run tool uses the sandbox.
Do not start research, evaluation, or GEPA runs. The owner starts those with slash commands.
When the task is done, reply with a short answer and no tool call."""


@dataclass
class Limits:
    max_steps: int
    max_seconds: float


@dataclass
class Outcome:
    status: str
    answer: str
    steps: int
    seconds: float
    detail: str = ""


class ToolError(Exception):
    pass


class Agent:
    def __init__(self, client, tools, limits: Limits, display, workspace, clock=time.monotonic, emit=None):
        self.client, self.tools, self.limits, self.display, self.clock = client, tools, limits, display, clock
        self.workspace = workspace
        self.emit = emit or (lambda kind, payload: None)
        self.messages = []
        self.warned = False

    def start(self, messages=None):
        self.warned = False
        self.messages = messages or [{"role": "system", "content": SYSTEM.format(workspace=self.workspace)}]
        if not messages:
            self.emit("message", self.messages[0])
        else:
            # Older sessions may hold text that the request check refuses. Clean it, so the session can resume.
            for message in self.messages[1:]:
                if message.get("role") in ("user", "tool") and isinstance(message.get("content"), str):
                    message["content"] = guard(message["content"])
            self._close_open_calls()

    def _append(self, message):
        self.messages.append(message)
        self.emit("message", message)

    def run_task(self, task: str) -> Outcome:
        try:
            sanitized(task.encode("utf-8"))
        except RuntimeRefused as exc:
            return Outcome("error", "", 0, 0.0, exc.code)
        if looks_secret(task):
            # Refuse here, before the task joins the conversation and blocks every later request.
            return Outcome("error", "", 0, 0.0, "AI_SENSITIVE_INPUT_DENIED: the task looks like it holds a secret")
        self._append({"role": "user", "content": task})
        start = self.clock()
        deadline = start + self.limits.max_seconds
        step = 0

        def end(status, answer="", detail=""):
            self._close_open_calls()
            outcome = Outcome(status, answer, step, self.clock() - start, detail)
            self.emit("outcome", {"status": status, "steps": step, "seconds": outcome.seconds, "detail": detail})
            return outcome

        try:
            while True:
                if step >= self.limits.max_steps:
                    return end("step_limit", detail=f"the step limit ({self.limits.max_steps}) was reached")
                if self.clock() >= deadline:
                    return end("time_limit", detail="the task time limit was reached")
                step += 1
                size = len(encode(self.messages))
                if size > WARN_CONVERSATION and not self.warned:
                    self.warned = True
                    self.display.note(f"The conversation holds {kib(size)} of {kib(MAX_CONVERSATION)}. Use /new soon.")
                self.display.step(step, self.limits.max_steps, self.clock() - start)
                reply = self.client.chat(self.messages, self.tools.specs(), self.display.model_event, deadline)
                self.display.reply(reply)
                message = {"role": "assistant", "content": reply.content or None}
                if reply.tool_calls:
                    message["tool_calls"] = [{"id": c["id"], "type": "function",
                                              "function": {"name": c["name"], "arguments": c["arguments"]}}
                                             for c in reply.tool_calls]
                self._append(message)
                if not reply.tool_calls:
                    return end("done", reply.content)
                for call in reply.tool_calls:
                    if self.clock() >= deadline:
                        raise DeadlineReached()
                    result = self._call(call, deadline)
                    self._append({"role": "tool", "tool_call_id": call["id"], "content": result})
        except KeyboardInterrupt:
            return end("interrupted", detail="stopped with Ctrl+C")
        except DeadlineReached:
            return end("time_limit", detail="the task time limit was reached")
        except ModelError as exc:
            return end("error", detail=str(exc))

    def _call(self, call, deadline):
        name = call["name"]
        try:
            args = json.loads(call["arguments"] or "{}")
        except ValueError:
            args = None
        self.display.tool_call(name, args if isinstance(args, dict) else call["arguments"])
        if not isinstance(args, dict):
            result = "error: the arguments are not a valid JSON object"
            self.display.tool_result(result, ok=False, name=name)
            return result
        take_change = getattr(self.tools, "take_change", lambda: None)
        take_change()
        try:
            result = self.tools.run(name, args, deadline)
            ok = True
        except ToolError as exc:
            result, ok = f"error: {exc}", False
        # Every tool result passes the same secret rules as the request check, whatever the tool checked itself.
        result = guard(result)
        self.display.tool_result(result, ok, name=name, change=take_change())
        return result

    def _close_open_calls(self):
        for i in range(len(self.messages) - 1, -1, -1):
            message = self.messages[i]
            if message["role"] == "assistant":
                answered = {r["tool_call_id"] for r in self.messages[i + 1:] if r["role"] == "tool"}
                for call in message.get("tool_calls") or []:
                    if call["id"] not in answered:
                        self._append({"role": "tool", "tool_call_id": call["id"],
                                      "content": "not run: the task was stopped"})
                return
