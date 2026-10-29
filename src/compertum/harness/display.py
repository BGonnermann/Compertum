"""A quiet terminal display with details available on demand."""
from __future__ import annotations

import difflib
import json
import os
import shutil
import sys
import threading
import time
import unicodedata

SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
TOOL_LABELS = {"read": "Read", "write": "Write", "edit": "Edit", "run": "Run", "bash": "Bash", "search": "Search"}
DIFF_ROWS, OUTPUT_ROWS = 20, 4
# The changed region of a diff may hold at most this many line pairs, about 200 by 200 lines.
# Repetitive text near this limit takes about 0.1 second. Larger regions show a summary only.
DIFF_WORK = 40_000
FIRST_FRAME, FRAME = 0.15, 0.1
# Windows Terminal shows a busy ring on the tab icon for OSC 9;4;3 and clears it with OSC 9;4;0. Other terminals ignore both.
TAB_BUSY, TAB_IDLE = "\x1b]9;4;3;0\x07", "\x1b]9;4;0;0\x07"
# Model, file and program text must not reach the terminal as control sequences, for example a clipboard write.
CONTROLS = {code: f"\\x{code:02x}" for code in [*range(0x20), 0x7F, *range(0x80, 0xA0)] if code not in (0x09, 0x0A)}


def clock(seconds):
    minutes, seconds = divmod(int(seconds), 60)
    return f"{minutes}:{seconds:02d}"


def visible(text):
    """Show control characters as escapes. Keep tabs and line breaks."""
    return str(text).replace("\r\n", "\n").translate(CONTROLS)


def fit(text, columns):
    """Cut text to a number of terminal columns. Wide East Asian characters use two columns."""
    used = 0
    for index, char in enumerate(text):
        used += 2 if unicodedata.east_asian_width(char) in "WF" else 1
        if used > columns:
            return text[:index]
    return text


def diff_rows(before, after, context=1):
    """Return (sign, line number, text) rows and the added and removed counts, or None for a very large change."""
    old, new = before.splitlines(), after.splitlines()
    start = 0
    while start < min(len(old), len(new)) and old[start] == new[start]:
        start += 1
    end = 0
    while end < min(len(old), len(new)) - start and old[-1 - end] == new[-1 - end]:
        end += 1
    # Most edits change a small region. Matching only that region keeps the work small.
    low, keep = max(0, start - context), min(context, end)
    old_window, new_window = old[low:len(old) - end + keep], new[low:len(new) - end + keep]
    if len(old_window) * len(new_window) > DIFF_WORK:
        return None
    matcher = difflib.SequenceMatcher(None, old_window, new_window, autojunk=False)
    rows, added, removed = [], 0, 0
    for index, group in enumerate(matcher.get_grouped_opcodes(context)):
        if index:
            rows.append(("⋮", None, ""))
        for tag, i1, i2, j1, j2 in group:
            i1, i2, j1, j2 = i1 + low, i2 + low, j1 + low, j2 + low
            if tag == "equal":
                rows.extend((" ", j1 + k + 1, new[j1 + k]) for k in range(i2 - i1))
                continue
            rows.extend(("-", i1 + k + 1, old[i1 + k]) for k in range(i2 - i1))
            rows.extend(("+", j1 + k + 1, new[j1 + k]) for k in range(j2 - j1))
            removed, added = removed + i2 - i1, added + j2 - j1
    return rows, added, removed


def _plural(count, word):
    return f"{count} {word}{'' if count == 1 else 's'}"


def _virtual_terminal(out):
    from .editor import enable_vt
    return out.isatty() and enable_vt(out)


class Display:
    def __init__(self, out=None, color=None, animate=None):
        self.out = out or sys.stdout
        try:
            self.out.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
        # Escape codes need a console that accepted virtual-terminal mode. Scripts and logs get plain lines.
        vt = _virtual_terminal(self.out) if color is None or animate is None else False
        self.color = bool(color) if color is not None else vt and not os.environ.get("NO_COLOR")
        self.animate = bool(animate) if animate is not None else vt
        self._streaming = None
        self._lock = threading.Lock()
        self._spinner = self._stop_spin = None
        self._drawn = False
        self._busy_tab = False

    def _c(self, code, text):
        return f"\x1b[{code}m{text}\x1b[0m" if self.color else text

    def _width(self):
        return max(10, shutil.get_terminal_size((100, 24)).columns)

    def line(self, text=""):
        self._quiet()
        self._end_stream()
        print(text, file=self.out, flush=True)

    def json(self, value):
        self.line(json.dumps(value, indent=2, sort_keys=True))

    def _end_stream(self):
        if self._streaming:
            print(file=self.out, flush=True)
            self._streaming = None

    def _terminal(self, text):
        if self.animate:
            self.out.write(text)
            self.out.flush()

    def _title(self, text):
        self._terminal(f"\x1b]0;{text}\x07")

    def busy(self, label, since=0.0):
        """Animate one status line until the next output. The line disappears when it stops."""
        self._quiet()
        if not self.animate:
            return
        if not self._busy_tab:
            self._terminal(TAB_BUSY)
            self._title("Compertum · working")
            self._busy_tab = True
        stop = threading.Event()
        started = time.monotonic() - since
        self._spinner = threading.Thread(target=self._spin, args=(stop, visible(label), started), daemon=True)
        self._stop_spin = stop
        self._spinner.start()

    def _spin(self, stop, label, started):
        frame = 0
        # The short first wait keeps fast tools from flashing a spinner.
        while not stop.wait(FIRST_FRAME if frame == 0 else FRAME):
            with self._lock:
                if stop.is_set():
                    break
                status = fit(f"{label} · {clock(time.monotonic() - started)} · Ctrl+C to stop", self._width() - 3)
                text = self._c("36", SPINNER[frame % len(SPINNER)]) + " " + self._c("2", status)
                self.out.write("\r\x1b[2K" + text)
                self.out.flush()
                self._drawn = True
            frame += 1

    def _quiet(self):
        if self._spinner is None:
            return
        self._stop_spin.set()
        self._spinner.join()
        # Erase before releasing the spinner, so an interrupt here still leaves the next call to erase it.
        if self._drawn:
            self.out.write("\r\x1b[2K")
            self.out.flush()
            self._drawn = False
        self._spinner = self._stop_spin = None

    def idle(self, title="Compertum"):
        self._quiet()
        if self._busy_tab:
            self._terminal(TAB_IDLE)
            self._busy_tab = False
        self._title(title)

    def banner(self, version, rows):
        self._title("Compertum")
        self.line(self._c("1", f"Compertum harness {version}"))
        for key, value in rows:
            self.line(f"  {key:<10}{value}")
        self.line("Type a task. /help shows the commands.")

    def error(self, text):
        if self._busy_tab:
            self.idle("Compertum · error")
        self.line(self._c("31", f"Error: {visible(text)}"))

    def note(self, text):
        self.line(self._c("2", text))

    def step(self, number, maximum, elapsed):
        if self.animate:
            self.busy(f"Working · step {number}/{maximum}", since=elapsed)
        else:
            self.line(self._c("36", f"[asking] step {number}/{maximum} | {clock(elapsed)}"))

    def model_event(self, kind, text):
        self._quiet()
        if self._streaming != kind:
            self._end_stream()
            if kind == "reasoning":
                print(self._c("2", "thinking: "), end="", file=self.out)
            self._streaming = kind
        text = visible(text)
        print(self._c("2", text) if kind == "reasoning" else text, end="", file=self.out, flush=True)

    def reply(self, reply):
        if self.animate:
            self._quiet()
            self._end_stream()
            return
        calls = len(reply.tool_calls)
        self.line(self._c("2", f"[reply] {calls} tool calls" if calls else "[reply] final answer"))

    def tool_call(self, name, args):
        # Like tool_result, a display failure must never interrupt the task.
        try:
            self._tool_call(name, args)
        except Exception:  # noqa: BLE001
            self.line(self._c("1;36", "● ") + self._c("1", visible(str(name))[:60]))

    def _tool_call(self, name, args):
        path = args.get("path") if isinstance(args, dict) else None
        if name == "bash" and isinstance(args, dict) and isinstance(args.get("command"), str):
            target, label = args["command"].replace("\n", " ⏎ "), "Bash"
        elif name == "search" and isinstance(args, dict) and isinstance(args.get("pattern"), str):
            target, label = repr(args["pattern"]), "Search"
            if isinstance(path, str):
                target += f" in {path}"
            if isinstance(args.get("glob"), str):
                target += f" ({args['glob']})"
        elif isinstance(path, str):
            extra = args.get("args") if name == "run" else None
            target = path + ("".join(f" {value}" for value in extra) if isinstance(extra, list) else "")
            label = TOOL_LABELS.get(name, name)
        else:
            target = json.dumps(args, ensure_ascii=False) if isinstance(args, dict) else repr(args)
            label = visible(name)
        target = visible(target)
        self.line(self._c("1;36", "● ") + self._c("1", label) + " " + target[:240])
        self.busy(f"{label} {target[:60]}")

    def _result(self, text, code="2"):
        self.line(self._c("2", "  ⎿ ") + self._c(code, text))

    def tool_result(self, text, ok, name=None, change=None):
        # The display must never interrupt the task. A display failure falls back to a plain summary.
        try:
            self._tool_result(visible(text), ok, name, change)
        except Exception:  # noqa: BLE001
            self._result("finished; the details cannot be shown" if ok else "tool failed", "2" if ok else "31")

    def _tool_result(self, text, ok, name, change):
        if not ok:
            lines = text.splitlines() or [""]
            self._result(lines[0][:200], "31")
            for row in lines[1:OUTPUT_ROWS]:
                self.line(self._c("31", "    " + row[:200]))
            return
        if change is not None:
            self._change(*change)
            return
        if name == "read":
            self._result(f"Read {_plural(len(text.splitlines()), 'line')}")
            return
        if name in ("run", "bash") and self._run_result(text):
            return
        if name == "search":
            lines = text.splitlines()
            matches = [] if text in ("no matches", "no matching files") else lines
            self._result(f"{_plural(len(matches), 'result')}" if matches else text)
            for row in matches[:OUTPUT_ROWS]:
                self.line(self._c("2", "    " + row[:200]))
            if len(matches) > OUTPUT_ROWS:
                self.line(self._c("2", f"    ... {len(matches) - OUTPUT_ROWS} more"))
            return
        lines = text.splitlines() or [""]
        self._result(f"{_plural(len(lines), 'line')}")
        for row in lines[:3]:
            self.line(self._c("2", "    " + row[:200]))
        if len(lines) > 3:
            self.line(self._c("2", f"    ... {len(lines) - 3} more lines"))

    def _change(self, path, before, after, created=False):
        path = visible(path)
        if before is None:
            self._result(f"Wrote {_plural(len(after.splitlines()), 'line')}; the previous file cannot be shown")
            return
        diff = diff_rows(before, after)
        if diff is None:
            self._result(f"Changed {path} from {_plural(len(before.splitlines()), 'line')} to "
                         f"{len(after.splitlines())}; the diff is too large to show")
            return
        rows, added, removed = diff
        if created:
            self._result(f"Created {path} with {_plural(added, 'line')}")
        elif not added and not removed:
            self._result("No changes" if before == after else "Changed only line endings")
            return
        else:
            self._result(f"Added {_plural(added, 'line')}, removed {_plural(removed, 'line')}")
        if not rows:
            return
        digits = len(str(max(number or 0 for _, number, _ in rows)))
        width = self._width() - digits - 8
        for sign, number, text in rows[:DIFF_ROWS]:
            if sign == "⋮":
                self.line(self._c("2", " " * (digits + 5) + "⋮"))
                continue
            body = f"    {number:>{digits}} {sign} {fit(visible(text).expandtabs(4), width)}"
            self.line(self._c({"+": "32", "-": "31"}.get(sign, "2"), body))
        hidden = sum(1 for sign, _, _ in rows[DIFF_ROWS:] if sign != "⋮")
        if hidden:
            self.line(self._c("2", f"    ... {hidden} more diff lines"))

    def _run_result(self, text):
        try:
            result = json.loads(text)
            status, code = result["status"], result["exit_code"]
        except (ValueError, KeyError, TypeError):
            return False
        summary = "timed out" if result.get("timed_out") else f"exit {code}"
        self._result(summary, "32" if status == "COMPLETED" else "31")
        for key, color in (("stdout", "2"), ("stderr", "31")):
            lines = visible(result.get(key) or "").splitlines()
            for row in lines[-OUTPUT_ROWS:]:
                self.line(self._c(color, "    " + row[:200]))
            if len(lines) > OUTPUT_ROWS:
                self.line(self._c("2", f"    ... {len(lines) - OUTPUT_ROWS} earlier {key} lines"))
        return True

    def outcome(self, outcome):
        self.idle("Compertum · done" if outcome.status == "done" else f"Compertum · {outcome.status}")
        steps = f"{outcome.steps} steps | {clock(outcome.seconds)}"
        self.line(self._c("1;32" if outcome.status == "done" else "1;31", f"[{outcome.status}] {steps} {outcome.detail}".rstrip()))
