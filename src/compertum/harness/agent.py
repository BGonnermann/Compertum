"""The bounded agent loop, adapted from Vesper core."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass

from compertum.ai.manual import sanitized
from compertum.runtime.errors import RuntimeRefused

from .model import DeadlineReached, ModelError
from .packets import LOCAL_ROLES, MAX_CONVERSATION, WARN_CONVERSATION, encode, guard, kib, looks_secret
from .sessions import compacted

SYSTEM = """You are Compertum's terminal agent. Work in the project workspace: {workspace}
Use search to find code and bash with ls or find to list folders. Read only the files you need.
Use read, write, and edit for project files. Use bash for git status, git diff, git log and tests.
Bash runs on the owner's PC, not in a sandbox. Follow AGENTS.md. Do not push, commit, install software,
start model servers, delete files outside the workspace, or read credentials, keys or runtime state.
Use run for AI-written Python that must execute. The run tool uses the sandbox.
Do not start research, evaluation, or GEPA runs. The owner starts those with slash commands.
When the task is done, reply with a short answer and no tool call."""
MAX_RULES = 32 * 1024
KEEP_SHARE = 0.3
REPEAT_LIMIT = 3
SUMMARY_TASK = ("Write a summary of the conversation above, for your own use later. Keep the owner's tasks and decisions, "
                "the file names, the commands, the results, and the problems that are not solved. "
                "If the conversation holds an earlier summary, merge it into the new summary. Reply with the summary only.")
SUMMARY_HEAD = "Summary of the earlier conversation, written by the agent:\n\n"


def project_rules(workspace):
    try:
        text = (workspace / "AGENTS.md").read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return ""
    return "\n\nThe project rules from AGENTS.md follow.\n\n" + guard(text[:MAX_RULES]) if text.strip() else ""


def call_key(call):
    try:
        return call["name"], encode(json.loads(call["arguments"] or "{}"))
    except ValueError:
        return call["name"], call["arguments"]


@dataclass
class Limits:
    max_steps: int | None
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
        self.warned = self._unsaved = False

    def start(self, messages=None):
        self.warned = False
        self.messages = messages or [{"role": "system", "content": SYSTEM.format(workspace=self.workspace)
                                      + project_rules(self.workspace)}]
        # A new session is saved with its first task, so opening and closing the console leaves no empty file.
        self._unsaved = not messages
        if messages:
            # Older sessions may hold text that the request check refuses. Clean it, so the session can resume.
            for message in self.messages:
                if message.get("role") in LOCAL_ROLES and isinstance(message.get("content"), str):
                    message["content"] = guard(message["content"])
            self._close_calls()

    def _append(self, message):
        self.messages.append(message)
        if self._unsaved:
            self._unsaved = False
            self.emit("message", self.messages[0])
        self.emit("message", message)

    def run_task(self, task: str) -> Outcome:
        try:
            sanitized(task.encode("utf-8"))
        except RuntimeRefused as exc:
            return Outcome("error", "", 0, 0.0, exc.code)
        if looks_secret(task):
            # Refuse here, before the task joins the conversation and blocks every later request.
            return Outcome("error", "", 0, 0.0, "AI_SENSITIVE_INPUT_DENIED: the task looks like it holds a secret")
        start = self.clock()
        deadline = start + self.limits.max_seconds
        step = repeats = 0
        last = None
        tried = False

        def end(status, answer="", detail=""):
            outcome = Outcome(status, answer, step, self.clock() - start, detail)
            try:
                self._close_calls()
                self.emit("outcome", {"status": status, "steps": step, "seconds": outcome.seconds, "detail": detail})
            except Exception as exc:  # noqa: BLE001
                # A failed save must not hide the outcome. The conversation in memory stays complete.
                self.display.note(f"The session could not save the end of this task: {getattr(exc, 'code', exc)}")
            return outcome

        try:
            # Inside the try, so a full or unwritable session ends the task with an outcome.
            self._append({"role": "user", "content": task})
            while True:
                if self.limits.max_steps is not None and step >= self.limits.max_steps:
                    return end("step_limit", detail=f"the step limit ({self.limits.max_steps}) was reached")
                if self.clock() >= deadline:
                    return end("time_limit", detail="the task time limit was reached")
                step += 1
                size = len(encode(self.messages))
                if size > WARN_CONVERSATION and not tried and not self._compact(size, deadline):
                    tried = True
                if tried and not self.warned:
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
                    signature = call_key(call)
                    repeats = repeats + 1 if signature == last else 1
                    last = signature
                    if repeats >= REPEAT_LIMIT:
                        return end("repeat_limit", detail=f"the same tool call came {REPEAT_LIMIT} times in a row")
                    result = self._call(call, deadline)
                    self._append({"role": "tool", "tool_call_id": call["id"], "content": result})
        except KeyboardInterrupt:
            return end("interrupted", detail="stopped with Ctrl+C")
        except DeadlineReached:
            return end("time_limit", detail="the task time limit was reached")
        except ModelError as exc:
            return end("error", detail=str(exc))
        except Exception as exc:  # noqa: BLE001
            # Any other failure, such as a session that cannot be saved, still ends the task with an outcome.
            return end("error", detail=f"{type(exc).__name__}: {getattr(exc, 'code', exc)}")

    def _compact(self, size, deadline):
        cut = self._cut(size)
        if cut is None:
            return False
        self.display.note(f"The conversation holds {kib(size)} of {kib(MAX_CONVERSATION)}. The agent writes a summary of the older part.")
        try:
            reply = self.client.chat(self.messages[:cut] + [{"role": "user", "content": SUMMARY_TASK}],
                                     self.tools.specs(), None, deadline)
        except ModelError as exc:
            self.display.note(f"The conversation could not be compacted: {exc}")
            return False
        text = (reply.content or "").strip()
        if not text:
            return False
        payload = {"summary": {"role": "user", "content": guard(SUMMARY_HEAD + text)}, "tail": len(self.messages) - cut}
        self.messages = compacted(self.messages, payload)
        self.emit("compact", payload)
        smaller = len(encode(self.messages))
        self.display.note(f"The summary replaced {cut - 1} older messages. The conversation now holds {kib(smaller)}.")
        return smaller <= WARN_CONVERSATION

    def _cut(self, size):
        kept = 0
        for index in range(len(self.messages) - 1, 1, -1):
            kept += len(encode(self.messages[index]))
            if kept >= size * KEEP_SHARE and self.messages[index]["role"] != "tool":
                return index
        return None

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

    def _close_calls(self):
        for i in range(len(self.messages) - 1, -1, -1):
            message = self.messages[i]
            if message["role"] == "assistant":
                answered = {r["tool_call_id"] for r in self.messages[i + 1:] if r["role"] == "tool"}
                for call in message.get("tool_calls") or []:
                    if call["id"] not in answered:
                        self._append({"role": "tool", "tool_call_id": call["id"],
                                      "content": "not run: the task was stopped"})
                return
