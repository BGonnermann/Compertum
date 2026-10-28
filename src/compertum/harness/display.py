"""A quiet terminal display with details available on demand."""
from __future__ import annotations

import json
import os
import sys


def clock(seconds):
    minutes, seconds = divmod(int(seconds), 60)
    return f"{minutes}:{seconds:02d}"


class Display:
    def __init__(self, out=None, color=None):
        self.out = out or sys.stdout
        try:
            self.out.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
        self.color = bool(color) if color is not None else self.out.isatty() and not os.environ.get("NO_COLOR")
        self._streaming = None

    def _c(self, code, text):
        return f"\x1b[{code}m{text}\x1b[0m" if self.color else text

    def line(self, text=""):
        self._end_stream()
        print(text, file=self.out, flush=True)

    def json(self, value):
        self.line(json.dumps(value, indent=2, sort_keys=True))

    def _end_stream(self):
        if self._streaming:
            print(file=self.out, flush=True)
            self._streaming = None

    def banner(self, version, rows):
        self.line(self._c("1", f"Compertum harness {version}"))
        for key, value in rows:
            self.line(f"  {key:<10}{value}")
        self.line("Type a task. /help shows the commands.")

    def error(self, text):
        self.line(self._c("31", f"Error: {text}"))

    def note(self, text):
        self.line(self._c("2", text))

    def step(self, number, maximum, elapsed):
        self.line(self._c("36", f"[asking] step {number}/{maximum} | {clock(elapsed)}"))

    def model_event(self, kind, text):
        if self._streaming != kind:
            self._end_stream()
            if kind == "reasoning":
                print(self._c("2", "thinking: "), end="", file=self.out)
            self._streaming = kind
        print(self._c("2", text) if kind == "reasoning" else text, end="", file=self.out, flush=True)

    def reply(self, reply):
        calls = len(reply.tool_calls)
        self.line(self._c("2", f"[reply] {calls} tool calls" if calls else "[reply] final answer"))

    def tool_call(self, name, args):
        shown = json.dumps(args, ensure_ascii=False) if isinstance(args, dict) else repr(args)
        self.line(self._c("33", f"[tool] {name} ") + shown[:240])

    def tool_result(self, text, ok):
        lines = text.splitlines() or [""]
        self.line(self._c("2" if ok else "31", f"[result] {len(lines)} lines" if ok else "[result] tool failed"))
        for row in lines[:3]:
            self.line(self._c("2", "  " + row[:200]))
        if len(lines) > 3:
            self.line(self._c("2", f"  ... {len(lines) - 3} more lines"))

    def outcome(self, outcome):
        steps = f"{outcome.steps} steps | {clock(outcome.seconds)}"
        self.line(self._c("1;32" if outcome.status == "done" else "1;31", f"[{outcome.status}] {steps} {outcome.detail}".rstrip()))
