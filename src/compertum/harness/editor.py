"""A small interactive composer with a box, hints, and Tab completion."""
from __future__ import annotations

import shutil
import sys

from .commands import DESCRIPTIONS, complete, matching_commands


def enable_vt(out):
    if not out.isatty():
        return False
    if sys.platform != "win32":
        return True
    try:
        import ctypes
        kernel = ctypes.windll.kernel32
        handle = kernel.GetStdHandle(-11)
        mode = ctypes.c_uint32()
        return bool(kernel.GetConsoleMode(handle, ctypes.byref(mode)) and kernel.SetConsoleMode(handle, mode.value | 0x0004))
    except (AttributeError, OSError, ValueError):
        return False


def windows_key():
    import msvcrt
    key = msvcrt.getwch()
    return key + msvcrt.getwch() if key in ("\x00", "\xe0") else key


class LineEditor:
    def __init__(self, out=None, sessions=(), runs=(), get_key=windows_key, width=None):
        self.out = out or sys.stdout
        self.sessions, self.runs, self.get_key = sessions, runs, get_key
        self.width = width
        self.buffer, self.cursor, self.rendered = "", 0, 0

    def _size(self):
        terminal = self.width or shutil.get_terminal_size((100, 24)).columns
        return max(40, min(terminal - 2, max(60, len(self.buffer) + 8)))

    def _lines(self):
        width = self._size()
        top = "╭─ Compertum " + "─" * max(1, width - 14) + "╮"
        inside = width - 4
        start = max(0, self.cursor - inside + 1) if self.cursor >= inside else 0
        shown = self.buffer[start:start + inside]
        middle = "│ " + shown + " " * max(0, inside - len(shown)) + " │"
        bottom = "╰" + "─" * max(1, width - 2) + "╯"
        hints = []
        for usage in matching_commands(self.buffer):
            name = usage.split(maxsplit=1)[0]
            hints.append(("  " + usage + "  " + DESCRIPTIONS[name])[:width])
        return top, middle, bottom, hints, self.cursor - start + 3

    def _render(self):
        top, middle, bottom, hints, column = self._lines()
        if self.rendered:
            self.out.write("\x1b[1A")
        self.out.write("\x1b[J")
        lines = [top, middle, bottom, *hints]
        self.out.write("\r" + "\n".join(lines))
        if len(lines) > 1:
            self.out.write(f"\x1b[{len(lines) - 2}A")
        self.out.write(f"\x1b[{column}G")
        self.out.flush()
        self.rendered = len(lines)

    def _finish(self):
        if self.rendered > 2:
            self.out.write(f"\x1b[{self.rendered - 2}B")
        self.out.write("\r\n")
        self.out.flush()
        return self.buffer

    def _complete(self):
        replacement = complete(self.buffer, self.sessions, self.runs)
        if replacement is not None:
            self.buffer, self.cursor = replacement, len(replacement)

    def read(self):
        while True:
            self._render()
            key = self.get_key()
            if key in ("\r", "\n"):
                return self._finish()
            if key == "\t":
                self._complete()
            elif key == "\x03":
                raise KeyboardInterrupt()
            elif key in ("\x04", "\x1a"):
                raise EOFError()
            elif key == "\x08":
                if self.cursor:
                    self.buffer = self.buffer[:self.cursor - 1] + self.buffer[self.cursor:]
                    self.cursor -= 1
            elif key in ("\x00K", "\xe0K"):
                self.cursor = max(0, self.cursor - 1)
            elif key in ("\x00M", "\xe0M"):
                self.cursor = min(len(self.buffer), self.cursor + 1)
            elif key in ("\x00G", "\xe0G"):
                self.cursor = 0
            elif key in ("\x00O", "\xe0O"):
                self.cursor = len(self.buffer)
            elif key in ("\x00S", "\xe0S"):
                self.buffer = self.buffer[:self.cursor] + self.buffer[self.cursor + 1:]
            elif len(key) == 1 and key.isprintable():
                self.buffer = self.buffer[:self.cursor] + key + self.buffer[self.cursor:]
                self.cursor += 1
